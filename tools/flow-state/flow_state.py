#!/usr/bin/env python3
"""Track where each activity stands in the Elcamargo AI development flow.

State lives in one file per activity under `<.agents>/atividades/<id>.md`, never
in a shared list, so two worktrees running in parallel never contend for the
same file. `Atividades_em_andamento_com_IA.md` is a generated index: it is
derived from those files and can be rebuilt at any time with `indice`.

Every mutation takes an exclusive lock. One file per activity stops two writers
from sharing a file; it does not stop two writers from reading the same state
and overwriting each other. `os.replace` is atomic, not a lock.

`<.agents>` always resolves to the main repository, even when the caller runs
inside a worktree — see `resolve_agents_dir`.

Stdlib only, by design: this tool ships inside a zip and must run anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows: no flock -- msvcrt.locking cobre o mesmo caso.
    import msvcrt
    fcntl = None  # type: ignore[assignment]

# The canonical flow. This constant is the machine-readable source of truth;
# FLOW.md is its prose counterpart and must be kept in step with it.
# `nome` é o ENDEREÇO — o que se invoca, e o que fica gravado no arquivo de
# estado. `cargo` é o que se LÊ: quem faz aquele trabalho, dito como se diria de
# uma pessoa. Os dois existem porque servem a leitores diferentes, e usar o
# endereço como rótulo obriga quem lê a traduzir `elcamargo-system-analysis-reviewer`
# para "quem confere a especificação" toda vez.
STEPS: dict[int, dict[str, str]] = {
    1: {"nome": "elcamargo-activity-management", "tipo": "skill",
        "cargo": "Gestor da Atividade"},
    2: {"nome": "elcamargo-business-analysis-reviewer", "tipo": "skill",
        "cargo": "Revisor de Negócio"},
    3: {"nome": "elcamargo-system-analyst", "tipo": "skill",
        "cargo": "Analista de Sistema"},
    4: {"nome": "elcamargo-system-analysis-reviewer", "tipo": "skill",
        "cargo": "Revisor da Especificação"},
    5: {"nome": "Revisão humana da especificação", "tipo": "humano",
        "cargo": "Portão humano · Especificação"},
    6: {"nome": "elcamargo-ux-reviewer", "tipo": "skill",
        "cargo": "Designer de Telas"},
    7: {"nome": "Revisão humana das telas", "tipo": "humano",
        "cargo": "Portão humano · Telas"},
    8: {"nome": "elcamargo-developer", "tipo": "skill",
        "cargo": "Desenvolvedor"},
    9: {"nome": "elcamargo-development-reviewer", "tipo": "skill",
        "cargo": "Revisor da Entrega"},
    10: {"nome": "Validação humana da entrega", "tipo": "humano",
         "cargo": "Portão humano · Entrega"},
}

# Which steps each track runs. A track is chosen once, at step 1, and recorded
# in the activity file so later steps cannot silently drift into another track.
TRILHAS: dict[str, list[int]] = {
    "completa": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "sistema": [1, 3, 4, 5, 6, 7, 8, 9, 10],
    # Correção pontual não passa por especificação nem por tela, então também
    # não passa pelos portões que existem para validá-las.
    "curta": [1, 8, 9, 10],
}

# Steps cuja ausência tira do fluxo justamente o que ele existe para dar. Podem
# ser desligados — é decisão do projeto — mas nunca em silêncio.
STEPS_DE_VERIFICACAO = {4, 9}
STEPS_DE_PORTAO = {n for n, d in STEPS.items() if d["tipo"] == "humano"}

STATUS_ABERTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"

INDEX_NAME = "Atividades_em_andamento_com_IA.md"
LOCK_NAME = ".flow-state.lock"

# Every separator `str.splitlines` recognises. Neutralising only "\n" is not
# enough: a note pasted from an Azure card carries CRLF, and everything after
# the first "\r" would be silently dropped on the next write — or, worse, be
# read back as a Markdown heading and truncate the table it landed in.
SEPARADORES = "\n\r\v\f\x1c\x1d\x1e\x85  "
_RE_QUEBRA = re.compile(f"[{re.escape(SEPARADORES)}]+")

# An id becomes a file name. Anything that could climb out of the directory, or
# hide the activity from a non-recursive glob, is refused.
_RE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class FlowStateError(RuntimeError):
    """Represent a condition that must stop the flow instead of being guessed."""


# --------------------------------------------------------------------------
# Location
# --------------------------------------------------------------------------


def _parece_agents(caminho: Path) -> bool:
    """Is this really a flow `.agents`, or just a directory with the name?"""
    return ((caminho / "elcamargo-flow").is_dir()
            or (caminho / "config.toml").is_file()
            or (caminho / "atividades").is_dir())


def resolve_agents_dir() -> Path:
    """Return the `.agents` directory of the main repository.

    Three cases, in this order:

    1. `ELCAMARGO_AGENTS_DIR`, when the caller knows better than we do.
    2. The caller is already inside `.agents`. This is checked *before* asking
       git, because `.agents` is itself an independent repository (it holds the
       backup history), so from inside it `--git-common-dir` describes that
       repository and not the project.
    3. Ask git. A worktree has its own working directory and does not carry
       `.agents`, which is untracked; `--git-common-dir` points at the main
       repository's `.git` from anywhere, so its parent is the one directory
       every worktree agrees on.

    Whatever the route, the result is checked for actually being ours. A
    directory that merely happens to be named `.agents` — an unrelated
    ancestor, a stale env var — is refused rather than silently written into.
    """
    override = os.environ.get("ELCAMARGO_AGENTS_DIR")
    if override:
        agents = Path(override).expanduser().resolve()
        if not agents.is_dir():
            raise FlowStateError(
                f"ELCAMARGO_AGENTS_DIR aponta para {agents}, que não existe."
            )
        return agents  # an explicit override is trusted as given

    cwd = Path.cwd().resolve()
    for candidato in (cwd, *cwd.parents):
        if candidato.name == ".agents" and _parece_agents(candidato):
            return candidato

    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError as exc:
        raise FlowStateError("Não encontrei o comando `git`.") from exc
    except subprocess.CalledProcessError as exc:
        detalhe = (exc.stderr or "").strip().splitlines()
        raise FlowStateError(
            "git não resolveu o repositório"
            + (f": {detalhe[0]}" if detalhe else "")
            + ". Rode a partir do projeto, ou defina ELCAMARGO_AGENTS_DIR."
        ) from exc

    agents = Path(resultado.stdout.strip()).parent / ".agents"
    if not agents.is_dir():
        raise FlowStateError(
            f"Não encontrei {agents}. O pacote precisa de um .agents na raiz "
            "do projeto."
        )
    if not _parece_agents(agents):
        raise FlowStateError(
            f"{agents} existe mas não parece um .agents do fluxo — não tem "
            "elcamargo-flow/, config.toml nem atividades/. Rode o install.sh "
            "ou defina ELCAMARGO_AGENTS_DIR."
        )
    return agents


def steps_assets(agents: Path | None = None) -> list[int]:
    """Os steps que este projeto declarou usar. Sem declaração, todos.

    Um time onde o UX é de outra pessoa legitimamente não roda o step 6. O que
    não é legítimo é desligar verificação em silêncio, e por isso a lista do que
    ficou de fora acompanha a atividade e todo relatório dela.
    """
    try:
        import config as _cfg  # tardio: config.py importa deste módulo
        declarados = _cfg.obter("fluxo.steps", None, agents)
    except Exception:
        declarados = None
    if not declarados:
        return sorted(STEPS)
    try:
        assets = sorted({int(s) for s in declarados} & set(STEPS))
    except (TypeError, ValueError):
        raise FlowStateError(
            "`fluxo.steps` no config precisa ser uma lista de números de step."
        ) from None
    if 1 not in assets:
        raise FlowStateError(
            "`fluxo.steps` não pode desligar o step 1: é ele que abre a "
            "atividade e decide a trilha."
        )
    return assets


def steps_desligados(agents: Path | None = None) -> list[int]:
    return sorted(set(STEPS) - set(steps_assets(agents)))


def avisar_desligados(agents: Path | None = None) -> list[str]:
    """Avisos altos para o que foi desligado e não deveria passar batido."""
    desligados = set(steps_desligados(agents))
    avisos = []
    portoes = sorted(desligados & STEPS_DE_PORTAO)
    if portoes:
        avisos.append(
            "PORTÃO HUMANO DESLIGADO: "
            + "; ".join(rotulo(n) for n in portoes)
            + ". São a parte mais barata e mais valiosa do fluxo — minutos de "
              "uma pessoa contra horas construídas sobre base errada."
        )
    verificacao = sorted(desligados & STEPS_DE_VERIFICACAO)
    if verificacao:
        avisos.append(
            "VERIFICAÇÃO DESLIGADA: "
            + "; ".join(rotulo(n) for n in verificacao)
            + ". Sem ela o fluxo mantém a cerimônia e perde a conferência — o "
              "que é pior que não usar o fluxo, porque parece rigoroso."
        )
    return avisos


def raiz_do_projeto(agents: Path) -> Path:
    """The MAIN working tree. `.agents` sits at its root.

    Use this only for things that belong to the repository as a whole. For
    anything about the work in progress — branch, installed dependencies, the
    files being changed — use `raiz_de_trabalho`, which follows the caller.
    """
    return agents.parent


def raiz_de_trabalho(agents: Path) -> Path:
    """The working tree the caller is actually in.

    A skill run inside a worktree works on THAT tree: its branch, its
    dependencies, its files. Asking the main tree instead describes a place the
    work never touched — a mistake made twice while building this, in
    `contexto_git` and in the dependency check, which is why it lives in one
    function now.

    The exception is `.agents` itself, an independent repository holding the
    backup history. From inside it, fall back to the main tree.
    """
    cwd = Path.cwd().resolve()
    if agents in (cwd, *cwd.parents):
        return raiz_do_projeto(agents)
    topo = _git(["rev-parse", "--show-toplevel"], cwd)
    return Path(topo) if topo else raiz_do_projeto(agents)


def atividades_dir(agents: Path) -> Path:
    d = agents / "atividades"
    d.mkdir(parents=True, exist_ok=True)
    return d


def validar_id(ident: str) -> str:
    if not _RE_ID.match(ident or ""):
        raise FlowStateError(
            f"Identificador inválido: {ident!r}. Use letras, números, ponto, "
            "hífen ou sublinhado — sem barra, espaço ou `..`, porque o "
            "identificador vira nome de arquivo."
        )
    return ident


def activity_path(agents: Path, ident: str) -> Path:
    return atividades_dir(agents) / f"{validar_id(ident)}.md"


def _git(args: list[str], cwd: Path) -> str:
    """Run git in the project, never in whatever directory the caller is in.

    A skill's natural working directory is inside `.agents`, which is its own
    repository. Asking git there reports the backup repo's branch — which is
    not the branch the activity is being built on.
    """
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def contexto_git(agents: Path) -> dict[str, str]:
    """Branch and worktree the activity is actually being built on.

    Read from the caller's directory, not from the project root: a skill run
    inside a worktree builds on THAT worktree's branch, and recording the main
    one describes a place the work never touched.

    The exception is `.agents` itself, an independent repository holding the
    backup history — from inside it git describes that repo, so fall back to
    the project root.

    Branch and worktree are read and dropped together: half a location
    describes a place that never existed.
    """
    raiz = raiz_de_trabalho(agents)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], raiz)
    worktree = _git(["rev-parse", "--show-toplevel"], raiz)
    return {"branch": branch, "worktree": worktree} if branch and worktree else {}


def agora() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Mutual exclusion
# --------------------------------------------------------------------------


@contextmanager
def trava(agents: Path):
    """Serialise every mutation across processes.

    One global lock rather than one per activity: the index is rebuilt from all
    activities on every write, so any two mutations conflict through it anyway.
    The operations are short and few, so the contention costs nothing.
    """
    agents.mkdir(parents=True, exist_ok=True)
    with open(agents / LOCK_NAME, "w") as fh:
        if fcntl is not None:
            fcntl.flock(fh, fcntl.LOCK_EX)
        else:
            # Windows. `msvcrt.locking` nao espera: erra na hora se outro
            # processo tem a trava. O laco e' a espera que o flock ja da'.
            # ponytail: espera ativa de 100 ms; o lock e' segurado por
            # escritas curtas, entao ninguem gira aqui por muito tempo.
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_UN)
            else:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


# --------------------------------------------------------------------------
# Text safety
# --------------------------------------------------------------------------


def uma_linha(texto: str) -> str:
    """Collapse every line separator so a value cannot break its container."""
    return _RE_QUEBRA.sub(" ", texto or "").strip()


def escapar_celula(texto: str) -> str:
    """Keep a pipe in a note from breaking the Markdown table it lands in.

    The inverse is `desescapar_celula`; `dividir_celulas` knows not to split on
    the escaped form. Backslash is escaped first so the round trip is faithful.
    """
    return (uma_linha(texto).replace("\\", "\\\\").replace("|", "\\|"))


def desescapar_celula(texto: str) -> str:
    out, i = [], 0
    while i < len(texto):
        if texto[i] == "\\" and i + 1 < len(texto):
            out.append(texto[i + 1])
            i += 2
        else:
            out.append(texto[i])
            i += 1
    return "".join(out).strip()


def dividir_celulas(linha: str) -> list[str]:
    """Split a Markdown table row on its unescaped pipes."""
    celulas, atual, i = [], [], 0
    interior = linha.strip()
    if interior.startswith("|"):
        interior = interior[1:]
    if interior.endswith("|") and not interior.endswith("\\|"):
        interior = interior[:-1]
    while i < len(interior):
        if interior[i] == "\\" and i + 1 < len(interior):
            atual.append(interior[i:i + 2])
            i += 2
        elif interior[i] == "|":
            celulas.append("".join(atual))
            atual = []
            i += 1
        else:
            atual.append(interior[i])
            i += 1
    celulas.append("".join(atual))
    return [c.strip() for c in celulas]


def escrever_atomico(path: Path, conteudo: str) -> None:
    """Write through a temporary file so a reader never sees a half state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(conteudo)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)  # never leave a stray .tmp behind


# --------------------------------------------------------------------------
# Activity file
# --------------------------------------------------------------------------
#
# Markdown with a flat `chave: valor` front matter. Flat on purpose: it keeps
# the parser short and the file readable by a human who opens it with no
# tooling at all.


class Atividade:
    def __init__(self, meta: dict[str, str],
                 history: list[tuple[str, ...]],
                 artefatos: list[tuple[str, ...]],
                 conferencias: list[tuple[str, ...]] | None = None) -> None:
        self.meta = meta
        self.history = history
        self.artefatos = artefatos
        # A terceira tabela existe porque uma obrigação escrita em prosa não
        # acontece. A instrução "entrar com ator sem a permissão" viveu meses na
        # frente de execução e nunca aconteceu uma vez — ninguém registrava, e
        # portanto ninguém sabia. Aqui a conferência mecânica deixa rastro, e o
        # `concluir` lê o rastro.
        self.conferencias = conferencias or []

    # -- parsing ----------------------------------------------------------

    @classmethod
    def ler(cls, path: Path) -> "Atividade":
        if not path.exists():
            raise FlowStateError(
                f"Atividade não encontrada em {path}. Rode `iniciar` antes."
            )
        texto = path.read_text(encoding="utf-8")
        meta, corpo = cls._split_front_matter(texto, path)
        atividade = cls(
            meta,
            cls._parse_tabela(corpo, "Histórico", ["Quando", "Step", "Nota"]),
            cls._parse_tabela(corpo, "Artefatos", ["Tipo", "Caminho"]),
            cls._parse_tabela(corpo, "Conferências",
                              ["Quando", "Ferramenta", "Veredicto", "Detalhe"]),
        )
        atividade.validar(path)
        return atividade

    def validar(self, path: Path) -> None:
        """Refuse a file whose fields cannot be trusted, with the reason.

        A hand-edited or truncated file must fail here, naming itself, rather
        than surfacing as a KeyError three frames away — and never while a
        listing is walking every other activity.
        """
        for chave in ("id", "step", "trilha", "status"):
            if not self.meta.get(chave):
                raise FlowStateError(f"{path.name}: falta `{chave}` no front matter.")
        if self.meta["trilha"] not in TRILHAS:
            raise FlowStateError(
                f"{path.name}: trilha desconhecida {self.meta['trilha']!r}."
            )
        try:
            step = int(self.meta["step"])
        except ValueError:
            raise FlowStateError(
                f"{path.name}: `step` não é um número ({self.meta['step']!r})."
            ) from None
        if step not in STEPS:
            raise FlowStateError(f"{path.name}: step {step} não existe no fluxo.")

    @staticmethod
    def _split_front_matter(texto: str, path: Path) -> tuple[dict[str, str], str]:
        if not texto.startswith("---\n"):
            raise FlowStateError(f"{path.name}: sem front matter.")
        fim = texto.find("\n---\n", 4)
        if fim == -1:
            raise FlowStateError(f"{path.name}: front matter não fechado.")
        meta: dict[str, str] = {}
        for linha in texto[4:fim].splitlines():
            if not linha.strip() or ":" not in linha:
                continue
            chave, _, valor = linha.partition(":")
            meta[chave.strip()] = valor.strip()
        return meta, texto[fim + 5:]

    @staticmethod
    def _parse_tabela(corpo: str, titulo: str,
                      cabecalho: list[str]) -> list[tuple[str, ...]]:
        """Read back a Markdown table written by `_render_tabela`.

        Splits on unescaped pipes only. A note containing `|` is stored as
        `\\|`; splitting on it naively yields the wrong column count and the
        row would be dropped without a trace.
        """
        linhas = corpo.splitlines()
        try:
            inicio = next(i for i, l in enumerate(linhas)
                          if l.strip().lower() == f"## {titulo}".lower())
        except StopIteration:
            return []
        registros: list[tuple[str, ...]] = []
        for linha in linhas[inicio + 1:]:
            s = linha.strip()
            if s.startswith("## "):
                break
            if not s.startswith("|"):
                continue
            # Structure is decided on the raw text, before unescaping: the
            # escape in `_render_tabela` is exactly what distinguishes a data
            # row reading `---` from the separator, and unescaping first would
            # throw that mark away and drop the row.
            cruas = dividir_celulas(s)
            if len(cruas) != len(cabecalho):
                continue
            if set("".join(cruas)) <= {"-", " ", ":"}:  # separator row
                continue
            if cruas == cabecalho:
                continue
            registros.append(tuple(desescapar_celula(c) for c in cruas))
        return registros

    # -- rendering --------------------------------------------------------

    def escrever(self, path: Path) -> None:
        titulo = uma_linha(self.meta.get("titulo", ""))
        blocos = [
            self._render_front_matter(),
            f"# {self.meta['id']}" + (f" — {titulo}" if titulo else ""),
            "",
            "## Histórico",
            "",
            self._render_tabela(["Quando", "Step", "Nota"], self.history),
            "",
            "## Artefatos",
            "",
            self._render_tabela(["Tipo", "Caminho"], self.artefatos)
            if self.artefatos else "_Nenhum artefato registrado._",
            "",
            "## Conferências",
            "",
            self._render_tabela(["Quando", "Ferramenta", "Veredicto", "Detalhe"],
                                self.conferencias)
            if self.conferencias else "_Nenhuma conferência registrada._",
            "",
        ]
        escrever_atomico(path, "\n".join(blocos))

    def _render_front_matter(self) -> str:
        ordem = ["id", "titulo", "complementares", "trilha", "step", "step_nome",
                 "status",
                 "steps_desligados", "branch", "worktree", "criado_em",
                 "atualizado_em", "concluido_em"]
        vistas = set()
        linhas = ["---"]
        for chave in [*ordem, *self.meta]:
            if chave in vistas or chave not in self.meta:
                continue
            vistas.add(chave)
            # Values are flattened: a title carrying a newline — or a literal
            # `---` — would otherwise close the front matter early and take
            # trilha, step and status with it.
            linhas.append(f"{chave}: {uma_linha(str(self.meta[chave]))}")
        linhas += ["---", ""]
        return "\n".join(linhas)

    @staticmethod
    def _render_tabela(cabecalho: list[str],
                       linhas: list[tuple[str, ...]]) -> str:
        out = ["| " + " | ".join(cabecalho) + " |",
               "| " + " | ".join("---" for _ in cabecalho) + " |"]
        for linha in linhas:
            celulas = [escapar_celula(c) for c in linha]
            # A data row that renders exactly like the separator row, or like
            # the header, is skipped on re-read and the entry vanishes. Escape
            # one character: the text is identical after unescaping, and the
            # row is no longer mistaken for structure.
            parece_separador = (any(celulas)
                                and set("".join(celulas)) <= {"-", " ", ":"})
            parece_cabecalho = [desescapar_celula(c) for c in celulas] == cabecalho
            if parece_separador or parece_cabecalho:
                primeira = next((i for i, c in enumerate(celulas) if c), None)
                if primeira is not None:
                    celulas[primeira] = "\\" + celulas[primeira]
            out.append("| " + " | ".join(celulas) + " |")
        return "\n".join(out)

    # -- flow -------------------------------------------------------------

    @property
    def trilha(self) -> list[int]:
        """Os steps da trilha, filtrados pelo que o projeto declarou usar.

        A trilha gravada na atividade não muda quando o projeto muda de
        política: o que muda é o caminho efetivo, e o que ficou de fora está
        registrado em `steps_desligados` no front matter.
        """
        declarada = TRILHAS[self.meta["trilha"]]
        desligados = {int(n) for n in
                      (self.meta.get("steps_desligados") or "").replace(",", " ").split()
                      if n.isdigit()}
        efetiva = [s for s in declarada if s not in desligados]
        return efetiva or declarada

    @property
    def step(self) -> int:
        return int(self.meta["step"])

    def proximo_step(self) -> int | None:
        seguintes = [s for s in self.trilha if s > self.step]
        return seguintes[0] if seguintes else None


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_caminho(args: argparse.Namespace) -> int:
    print(resolve_agents_dir())
    return 0


def cmd_fluxo(args: argparse.Namespace) -> int:
    try:
        assets = set(steps_assets())
    except FlowStateError:
        assets = set(STEPS)
    print("Steps do fluxo:\n")
    for numero, dados in STEPS.items():
        if numero not in assets and not getattr(args, "todos", False):
            continue
        marca = "HUMANO" if dados["tipo"] == "humano" else "skill "
        estado = "" if numero in assets else "   [DESLIGADO NO PROJETO]"
        endereco = "" if dados["tipo"] == "humano" else f"  ({dados['nome']})"
        print(f"  {numero:>2}  [{marca}]  {dados['cargo']}{endereco}{estado}")
    print("\nTrilhas:\n")
    for nome, steps in TRILHAS.items():
        efetiva = [s for s in steps if s in assets]
        print(f"  {nome:<9} {' → '.join(str(s) for s in efetiva)}")
    for aviso in avisar_desligados():
        print(f"\n  {aviso}")
    return 0


def cmd_iniciar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    ident = validar_id(args.id)
    if args.trilha not in TRILHAS:
        raise FlowStateError(
            f"Trilha inválida: {args.trilha}. Use uma de: {', '.join(TRILHAS)}."
        )

    with trava(agents):
        path = activity_path(agents, ident)
        anterior = None
        if path.exists():
            if not args.reabrir:
                raise FlowStateError(
                    f"A atividade {ident} já existe em {path}. Use `status` "
                    "para vê-la, ou --reabrir para reabrir o fluxo."
                )
            try:
                anterior = Atividade.ler(path)
            except FlowStateError:
                anterior = None  # unreadable: start clean, say so below

        inicio = TRILHAS[args.trilha][0]
        agora_str = agora()
        meta = {
            "id": ident,
            "titulo": args.titulo,
            "trilha": args.trilha,
            "step": str(inicio),
            "step_nome": STEPS[inicio]["nome"],
            "status": STATUS_ABERTO,
            "steps_desligados": " ".join(str(n) for n in steps_desligados(agents)),
            "criado_em": (anterior.meta.get("criado_em", agora_str)
                          if anterior else agora_str),
            "atualizado_em": agora_str,
            **contexto_git(agents),
        }
        if args.branch:
            meta["branch"] = args.branch

        # Cards complementares. A atividade continua tendo UM dono — a branch, o
        # arquivo de estado e o nome saem do principal —, e os outros viajam
        # junto porque o PR fecha os três e a especificação é uma só.
        #
        # Guardados no front matter, e não numa tabela, porque são identidade da
        # atividade e não evento dela: quem abre o arquivo precisa ver na
        # primeira tela o que este trabalho fecha.
        if getattr(args, "complementares", None):
            outros = [validar_id(c) for c in args.complementares]
            repetidos = [c for c in outros if c == ident]
            if repetidos:
                raise FlowStateError(
                    f"{ident} é o card principal e não pode ser complementar "
                    "de si mesmo."
                )
            if len(set(outros)) != len(outros):
                raise FlowStateError("Há card complementar repetido na lista.")
            meta["complementares"] = " ".join(outros)

        # Reopening keeps the history. Losing the record of what already
        # happened is the one thing the state file exists to prevent.
        history = list(anterior.history) if anterior else []
        artefatos = list(anterior.artefatos) if anterior else []
        nota = args.nota or (
            f"Reaberta na trilha {args.trilha}." if anterior
            else f"Atividade aberta na trilha {args.trilha}.")
        history.append((agora_str, rotulo(inicio), nota))

        if meta.get("complementares"):
            history.append((
                agora_str, rotulo(inicio),
                f"Card principal {ident}; complementares "
                f"{meta['complementares']}. O PR fecha os "
                f"{1 + len(meta['complementares'].split())}."))

        if desligados := steps_desligados(agents):
            history.append((agora_str, rotulo(inicio),
                              "Steps desligados no projeto: "
                              + " ".join(str(n) for n in desligados)))
        Atividade(meta, history, artefatos).escrever(path)
        avisos = regenerar_indice(agents) + avisar_desligados(agents)

    print(f"Atividade {ident} {'reaberta' if anterior else 'aberta'} em {path}")
    print(f"  trilha: {args.trilha} "
          f"({' → '.join(str(s) for s in TRILHAS[args.trilha])})")
    print(f"  step:   {rotulo(inicio)}")
    if anterior:
        print(f"  histórico preservado: {len(history) - 1} entrada(s)")
    relatar(avisos)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    if not args.id:
        return cmd_listar(args)
    atividade = Atividade.ler(activity_path(agents, args.id))
    meta = atividade.meta
    print(f"{meta['id']} — {meta.get('titulo', '')}")
    if meta.get("complementares"):
        # Na primeira tela, e não enterrado: quem retoma a atividade precisa
        # saber que o PR fecha mais de um card antes de decidir qualquer coisa.
        print(f"  fecha também: {meta['complementares']}")
    print(f"  status:   {meta.get('status')}")
    print(f"  trilha:   {meta.get('trilha')}")
    print(f"  step:     {rotulo(atividade.step)}")
    proximo = atividade.proximo_step()
    print(f"  próximo:  {rotulo_com_endereco(proximo) if proximo else '— fim da trilha —'}")
    for chave, label in (("branch", "branch  "), ("worktree", "worktree")):
        if meta.get(chave):
            print(f"  {label}: {meta[chave]}")
    if atividade.artefatos:
        print("  artefatos:")
        for tipo, caminho in atividade.artefatos:
            print(f"    {tipo}: {caminho}")
    return 0


def cmd_avancar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()

    with trava(agents):
        # Read inside the lock: two worktrees that both read before either
        # writes would each overwrite the other's transition, and both would
        # report success.
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)

        if atividade.meta.get("status") == STATUS_CONCLUIDO and not args.forcar:
            raise FlowStateError(
                f"A atividade {args.id} está concluída. Use --forcar para "
                "reabrir o fluxo."
            )

        proximo = atividade.proximo_step()
        destino = args.step if args.step is not None else proximo
        if destino is None:
            raise FlowStateError(
                f"A atividade {args.id} já está no último step da trilha "
                f"{atividade.meta['trilha']}. Use `concluir`."
            )
        if destino not in STEPS:
            raise FlowStateError(
                f"Step inexistente: {destino}. Use `fluxo` para ver a lista."
            )

        if not args.forcar:
            if destino not in atividade.trilha:
                raise FlowStateError(
                    f"O step {destino} não faz parte da trilha "
                    f"{atividade.meta['trilha']} ({atividade.trilha}). "
                    "Use --forcar se a trilha mudou de propósito."
                )
            if destino <= atividade.step:
                raise FlowStateError(
                    f"A atividade já está no step {atividade.step}; {destino} "
                    "é um retrocesso. Use --forcar se for volta de correção."
                )
            # The gate. Jumping from 4 to 6 would step over the human review at
            # 5, which is the whole point of having it.
            if destino != proximo:
                pulados = [s for s in atividade.trilha
                           if atividade.step < s < destino]
                humanos = [s for s in pulados if STEPS[s]["tipo"] == "humano"]
                raise FlowStateError(
                    f"Ir do step {atividade.step} para o {destino} pula "
                    f"{', '.join(rotulo(s) for s in pulados)}."
                    + (" Há portão humano no caminho." if humanos else "")
                    + f" O próximo da trilha é {rotulo(proximo)}. "
                      "Use --forcar e explique em --nota se for deliberado."
                )
        elif not args.nota:
            raise FlowStateError(
                "--forcar exige --nota: sair da trilha sem registrar o motivo "
                "torna o histórico inútil justamente onde ele importa."
            )

        # Orçamento: política declarada pelo PROJETO, lida de um JSON já
        # gravado — não coleta nada e não pode demorar. Quem forçou já decidiu,
        # e a nota dele registra o porquê.
        aviso_orcamento = "" if args.forcar else conferir_orcamento(agents, args.id)

        agora_str = agora()
        atividade.meta["step"] = str(destino)
        atividade.meta["step_nome"] = STEPS[destino]["nome"]
        atividade.meta["atualizado_em"] = agora_str
        atividade.meta.update(contexto_git(agents))
        if args.trilha:
            if args.trilha not in TRILHAS:
                raise FlowStateError(f"Trilha inválida: {args.trilha}.")
            atividade.meta["trilha"] = args.trilha
        atividade.history.append((agora_str, rotulo(destino), args.nota or ""))
        atividade.escrever(path)
        avisos = regenerar_indice(agents)

    atualizar_metricas(args.id)
    print(f"{args.id}: agora em {rotulo(destino)}")
    if aviso_orcamento:
        print(aviso_orcamento)
    if STEPS[destino]["tipo"] == "humano":
        print("  Este step é humano. Pare e peça a validação antes de seguir.")
    relatar(avisos)
    return 0


def atualizar_metricas(ident: str) -> None:
    """Recolhe as métricas desta atividade, em silêncio e sem poder atrapalhar.

    Fica preso à passagem de step e ao `concluir` porque é lá que o número
    muda de verdade — e porque uma métrica que só existe quando alguém lembra
    de gerar é uma métrica que não existe. Mesma razão da âncora.

    Três garantias, todas por causa de erro conhecido:

    Roda SÓ esta atividade. Coletar o projeto inteiro leva ~45 s aqui; por
    atividade, ~3 s. Preso ao `avancar`, o total transformaria cada passagem
    de step numa espera.

    Nunca reprova. Um `avancar` que falha porque o coletor de métrica tropeçou
    trocaria o estado do fluxo — que é a fonte de verdade — por um relatório.

    Não imprime nada em caminho feliz. O `avancar` já diz o que importa.
    """
    import subprocess
    ferramenta = Path(__file__).resolve().parents[1] / "metrics" / "metrics.py"
    if not ferramenta.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(ferramenta), "coletar",
             "--atividade", str(ident), "--silencioso"],
            capture_output=True, timeout=60, check=False)
    except Exception:
        pass


def conferir_orcamento(agents: Path, ident: str) -> str:
    """O gasto medido passou do orçamento que o projeto declarou?

    Devolve texto de aviso quando há algo a dizer sem barrar, `""` quando não
    há nada, e levanta `FlowStateError` quando estourou.

    Três recusas deliberadas no desenho, e cada uma tem número atrás:

    **Por atividade, não por step** — embora a frente aberta pedisse por step.
    O `metrics.py` só atribui step aos SUBAGENTES: `por_step` é preenchido
    dentro do laço de subagente, e os turnos do orquestrador não têm step. No
    painel medido eles são **27,7% do gasto**. Orçamento por step veria menos
    do que se gasta, e número que sai menor do que é é a direção proibida.

    **Em dólar, não em token.** São quatro contadores com preços até 50x
    diferentes entre si — 1,83 bilhão de cache lido contra 3,97 M de saída,
    medidos na mesma atividade. Somar os quatro dá um número dominado pelo
    cache barato, e alguém queimaria saída à vontade sem mover o total. Dólar
    é a soma ponderada pelo preço, e é por isso que a unidade é ele.

    **Não barra o `concluir`.** Travar o fechamento deixaria a atividade presa
    em andamento, que é pior que estourar o orçamento — e o `concluir` é o
    aceite de uma pessoa, não passagem automática.

    E ela nunca derruba o `avancar` por conta própria: config ausente, JSON
    corrompido ou chave mal declarada resultam em "não confere", nunca em
    exceção. Quem reprova declaração malformada é o `doctor.py`. O `avancar` é
    a espinha do fluxo; um conferidor de orçamento não pode quebrá-la.
    """
    try:
        import config as C
        teto = C.obter("metricas.orcamento_usd", None, agents)
    except Exception:
        return ""                      # projeto sem config: não há orçamento
    if teto is None or teto == "":
        return ""
    try:
        teto = float(teto)
    except (TypeError, ValueError):
        return ("  [orçamento não conferido] `[metricas] orcamento_usd` não é "
                "número. Rode `doctor.py conferir`.")
    if teto <= 0:
        return ""

    alvo = agents / "metrics" / f"{ident}.json"
    if not alvo.is_file():
        return ""                      # nada coletado ainda: normal no começo
    try:
        registro = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    # O zero silencioso, na porta do orçamento. Uma atividade que a coleta não
    # conseguiu atribuir reporta US$ 0,00 — e passaria por BAIXO de qualquer
    # teto, para sempre. Não conferir é correto; não DIZER que não conferiu
    # seria a mesma falsa completude que o `sem-prova` existe para acusar.
    if registro.get("atribuicao") == "sem-prova":
        motivo = registro.get("motivo_atribuicao") or "motivo não registrado"
        return ("  [orçamento não conferido] a última coleta não conseguiu "
                "atribuir trabalho\n"
                "      a esta atividade, então o custo dela sai US$ 0,00 e "
                "passaria por baixo\n"
                f"      de qualquer teto. Motivo: {motivo}")

    gasto = float(registro.get("custo_usd") or 0.0)
    if gasto <= teto:
        return ""

    quando = registro.get("gerado_em") or datetime.fromtimestamp(
        alvo.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    excesso = gasto - teto
    raise FlowStateError(
        f"{ident} passou do orçamento declarado.\n\n"
        f"      gasto na última coleta   US$ {gasto:>12,.2f}\n"
        f"      orçamento declarado      US$ {teto:>12,.2f}\n"
        f"      passou                   US$ {excesso:>12,.2f}  "
        f"(+{excesso * 100 / teto:.1f}%)\n\n"
        f"      Coletado em {quando} — o número é da última coleta, não de\n"
        f"      agora. Rode `metrics.py coletar --atividade {ident}` para\n"
        "      conferir antes de decidir.\n\n"
        "      Para seguir mesmo assim:\n"
        f"          flow_state.py avancar {ident} --forcar --nota \"<por quê>\""
    )


def cmd_artefato(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        tipo, caminho = uma_linha(args.tipo), uma_linha(args.caminho)
        if not tipo or not caminho:
            raise FlowStateError("--tipo e --caminho não podem ser vazios.")
        par = (tipo, caminho)
        if par not in atividade.artefatos:
            atividade.artefatos.append(par)
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    print(f"{args.id}: artefato {tipo} registrado — {caminho}")
    relatar(avisos)
    return 0


def cmd_pf(args: argparse.Namespace) -> int:
    """Declara o tamanho da atividade em pontos de função.

    Dois números, e o arquivo da atividade guarda os dois:

    `--declarado` é o do analista, contado da especificação funcional, antes
    de existir código. `--aferido` é o do step 9, contado da entrega, com o
    inventário do que foi contado ao lado.

    **`--aferido` exige `--inventario`, e a exigência é mecânica de
    propósito.** Uma obrigação escrita em prosa não acontece — é a mesma razão
    da tabela de *Conferências*. Este número entra no denominador de todo h/PF
    citado depois; sem a conta que o sustenta ele é palpite com casas decimais,
    e um palpite ali falsifica toda produtividade que se cite do painel.

    A ferramenta continua NÃO medindo ponto de função: ela guarda o que foi
    declarado, por quem, e onde está a conta. Quem divergir dos dois números
    decide por si — o `metrics.py` acusa a divergência e não desempata.
    """
    def inteiro(rotulo: str, bruto: str | None) -> int | None:
        if bruto is None:
            return None
        texto = uma_linha(bruto)
        if not texto.isdigit():
            raise FlowStateError(
                f"{rotulo} precisa ser um inteiro não negativo, e veio `{texto}`.")
        return int(texto)

    declarado = inteiro("--declarado", args.declarado)
    aferido = inteiro("--aferido", args.aferido)
    if declarado is None and aferido is None:
        raise FlowStateError("nada a declarar: passe --declarado, --aferido, ou os dois.")
    inventario = uma_linha(args.inventario or "")
    if aferido is not None and not inventario:
        raise FlowStateError(
            "--aferido exige --inventario: um PF sem a conta que o sustenta é\n"
            "palpite, e ele entra no denominador de todo h/PF citado depois.")

    with trava(agents := resolve_agents_dir()):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        if declarado is not None:
            atividade.meta["pf"] = str(declarado)
        if aferido is not None:
            atividade.meta["pf_aferido"] = str(aferido)
            atividade.meta["pf_inventario"] = inventario
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    partes = [f"declarado {declarado}" if declarado is not None else "",
              f"aferido {aferido}" if aferido is not None else ""]
    print(f"{args.id}: PF — " + ", ".join(p for p in partes if p))
    atualizar_metricas(args.id)
    relatar(avisos)
    return 0


VEREDICTOS = ("exigida", "ok", "falhou", "nao-coberta")


def pendencias(atividade: "Atividade") -> list[tuple[str, str]]:
    """Ferramentas exigidas que não fecharam, e as que fecharam mal.

    A regra é a mesma do fluxo inteiro: uma dimensão pode ficar **não coberta**
    desde que seja **declarada**. O que não pode é sumir. `nao-coberta` passa e
    aparece; `exigida` sem `ok` e `falhou` seguram.
    """
    ultimo: dict[str, tuple[str, str]] = {}
    for linha in atividade.conferencias:
        if len(linha) >= 3:
            ultimo[linha[1]] = (linha[2], linha[3] if len(linha) > 3 else "")
    return [(ferramenta, detalhe)
            for ferramenta, (veredicto, detalhe) in sorted(ultimo.items())
            if veredicto in ("exigida", "falhou")]


def cmd_conferencia(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    veredicto = uma_linha(args.veredicto)
    if veredicto not in VEREDICTOS:
        raise FlowStateError(
            f"veredicto desconhecido: {veredicto!r}. Use um de: "
            + ", ".join(VEREDICTOS) + ". `nao-coberta` existe para a dimensão "
            "que não deu para cobrir — ela passa, e aparece."
        )
    ferramenta = uma_linha(args.ferramenta)
    if not ferramenta:
        raise FlowStateError("--ferramenta não pode ser vazia.")
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        atividade.conferencias.append(
            (agora(), ferramenta, veredicto, uma_linha(args.detalhe or "")))
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    print(f"{args.id}: conferência {ferramenta} → {veredicto}")
    relatar(avisos)
    return 0


def cmd_concluir(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)

        if atividade.meta.get("status") == STATUS_CONCLUIDO:
            raise FlowStateError(f"A atividade {args.id} já está concluída.")
        ultimo = atividade.trilha[-1]
        if atividade.step != ultimo:
            if not args.forcar:
                raise FlowStateError(
                    f"A atividade está em {rotulo(atividade.step)}; o último "
                    f"step da trilha é {rotulo(ultimo)}. Use --forcar se ela "
                    "foi encerrada antes do fim, e explique em --nota."
                )
            if not args.nota:
                raise FlowStateError(
                    "--forcar exige --nota: encerrar antes do fim da trilha sem "
                    "dizer por quê apaga a única explicação que restaria."
                )

        abertas = pendencias(atividade)
        if abertas and not args.forcar:
            linhas = "\n".join(
                f"    {ferramenta}: {detalhe or 'sem detalhe'}"
                for ferramenta, detalhe in abertas)
            raise FlowStateError(
                "Conferência mecânica pendente:\n" + linhas + "\n\n"
                "  Uma delas foi EXIGIDA e não fechou, ou fechou reprovando. "
                "Rode a ferramenta e registre o resultado, ou declare a "
                "dimensão como `nao-coberta` — que passa e fica escrita. "
                "`--forcar` com `--nota` também encerra, e deixa dito por quê."
            )

        agora_str = agora()
        atividade.meta["status"] = STATUS_CONCLUIDO
        atividade.meta["atualizado_em"] = agora_str
        atividade.meta["concluido_em"] = agora_str
        atividade.history.append(
            (agora_str, "concluída", args.nota or "Fluxo encerrado."))
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    atualizar_metricas(args.id)
    print(f"{args.id}: concluída.")
    relatar(avisos)
    return 0


def cmd_listar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    atividades, avisos = carregar_todas(agents)
    if not atividades:
        print("Nenhuma atividade registrada.")
        relatar(avisos)
        return 0
    abertas = [a for a in atividades if a.meta["status"] != STATUS_CONCLUIDO]
    concluidas = [a for a in atividades if a.meta["status"] == STATUS_CONCLUIDO]
    if abertas:
        print("Em andamento:\n")
        for a in abertas:
            print(f"  {a.meta['id']:<12} {rotulo(a.step):<48} "
                  f"{a.meta.get('titulo', '')}")
    if concluidas and getattr(args, "todas", False):
        print("\nConcluídas:\n")
        for a in concluidas:
            print(f"  {a.meta['id']:<12} {a.meta.get('titulo', '')}")
    elif concluidas:
        print(f"\n({len(concluidas)} concluída(s); use --todas para listar.)")
    relatar(avisos)
    return 0


def cmd_tempo(args: argparse.Namespace) -> int:
    """Onde o tempo foi, step a step.

    O fluxo tem dez etapas e três portões humanos. Se ele vira gargalo, é aqui
    que se vê — e a resposta útil separa o que a IA gastou do que ficou
    esperando uma pessoa, porque são problemas diferentes com soluções
    diferentes.
    """
    agents = resolve_agents_dir()
    atividade = Atividade.ler(activity_path(agents, args.id))
    marcos = []
    for quando, rotulo_step, nota in atividade.history:
        try:
            t = datetime.strptime(quando, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                t = datetime.strptime(quando, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
        marcos.append((t, rotulo_step, nota))

    if len(marcos) < 2:
        print(f"{args.id}: histórico curto demais para medir "
              f"({len(marcos)} marco(s)).")
        return 0

    print(f"{atividade.meta['id']} — {atividade.meta.get('titulo', '')}")
    print(f"trilha {atividade.meta.get('trilha')}\n")
    print(f"  {'step':<46} {'duração':>10}  {'tipo':<7}")
    print(f"  {'-' * 46} {'-' * 10}  {'-' * 7}")

    total_ia = total_humano = 0.0
    for (inicio, rotulo_step, _), (fim, _, _) in zip(marcos, marcos[1:]):
        segundos = (fim - inicio).total_seconds()
        numero = rotulo_step.split(" ")[0]
        tipo = "?"
        # O histórico guarda o rótulo do dia em que a transição aconteceu. Ele
        # envelhece: um step renomeado deixa linhas antigas com o nome velho, e
        # a tabela passa a listar o mesmo trabalho com dois nomes. Quando o
        # número resolve, o cargo vem de STEPS.
        legivel = rotulo_step
        if numero.isdigit() and int(numero) in STEPS:
            tipo = STEPS[int(numero)]["tipo"]
            legivel = rotulo(int(numero))
        if tipo == "humano":
            total_humano += segundos
        else:
            total_ia += segundos
        print(f"  {legivel[:46]:<46} {_dur(segundos):>10}  {tipo:<7}")

    total = total_ia + total_humano
    print(f"\n  {'IA':<46} {_dur(total_ia):>10}  "
          f"{total_ia / total * 100:.0f}%" if total else "")
    print(f"  {'espera humana':<46} {_dur(total_humano):>10}  "
          f"{total_humano / total * 100:.0f}%" if total else "")
    print(f"  {'total':<46} {_dur(total):>10}")
    print("\n  Espera humana longa não é lentidão do fluxo — é o portão "
          "fazendo o trabalho dele.")
    print("  Tempo de IA longo é o que vale investigar.")
    print("\n  Atenção: isto mede tempo DECORRIDO entre as transições, não "
          "tempo de trabalho.")
    print("  Um step que ficou aberto enquanto a sessão fazia outra coisa "
          "aparece longo\n  sem ter sido. Para o portão humano a medida é "
          "exata — esperar É o trabalho dele.")
    return 0


def _dur(segundos: float) -> str:
    if segundos < 90:
        return f"{segundos:.0f}s"
    if segundos < 5400:
        return f"{segundos / 60:.1f}min"
    return f"{segundos / 3600:.1f}h"


def cmd_indice(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        avisos = regenerar_indice(agents)
    print(f"Índice regerado em {agents / INDEX_NAME}")
    relatar(avisos)
    return 0


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------


def carregar_todas(agents: Path) -> tuple[list[Atividade], list[str]]:
    """Read every activity, reporting — never raising on — the broken ones.

    One hand-edited file must not take down a listing that spans the others,
    and must not stop an unrelated activity from advancing.
    """
    atividades, avisos = [], []
    for path in sorted(atividades_dir(agents).glob("*.md")):
        try:
            atividades.append(Atividade.ler(path))
        except FlowStateError as exc:
            avisos.append(str(exc))
        except Exception as exc:  # malformed beyond what validation predicts
            avisos.append(f"{path.name}: ilegível ({exc.__class__.__name__}).")
    return atividades, avisos


def relatar(avisos: list[str]) -> None:
    for aviso in avisos:
        print(f"  aviso: {aviso}", file=sys.stderr)


def regenerar_indice(agents: Path) -> list[str]:
    """Rebuild the human-facing index from the activity files.

    Derived, never authoritative: deleting it loses nothing. Call inside the
    lock — it reads every activity and writes one file.
    """
    atividades, avisos = carregar_todas(agents)
    abertas = [a for a in atividades if a.meta["status"] != STATUS_CONCLUIDO]
    concluidas = [a for a in atividades if a.meta["status"] == STATUS_CONCLUIDO]

    linhas = [
        "# Atividades em andamento com IA",
        "",
        "Arquivo **gerado** por `elcamargo-flow/tools/flow-state/flow_state.py`.",
        "Não edite à mão: a fonte de verdade é `atividades/<id>.md`.",
        "Para reconstruir: `flow_state.py indice`.",
        "",
        f"Atualizado em {agora()}.",
        "",
        "## Em andamento",
        "",
    ]
    if abertas:
        linhas += ["| Atividade | Step | Trilha | Branch | Título |",
                   "| --- | --- | --- | --- | --- |"]
        for a in abertas:
            linhas.append("| {} | {} | {} | {} | {} |".format(*(
                escapar_celula(v) for v in (
                    a.meta["id"], rotulo(a.step), a.meta["trilha"],
                    a.meta.get("branch", ""), a.meta.get("titulo", "")))))
    else:
        linhas.append("_Nenhuma._")

    linhas += ["", "## Concluídas", ""]
    if concluidas:
        linhas += ["| Atividade | Título | Encerrada em |", "| --- | --- | --- |"]
        for a in concluidas:
            linhas.append("| {} | {} | {} |".format(*(
                escapar_celula(v) for v in (
                    a.meta["id"], a.meta.get("titulo", ""),
                    a.meta.get("concluido_em",
                               a.meta.get("atualizado_em", ""))))))
    else:
        linhas.append("_Nenhuma._")

    if avisos:
        linhas += ["", "## Arquivos ilegíveis", ""]
        linhas += [f"- {a}" for a in avisos]
    linhas.append("")

    escrever_atomico(agents / INDEX_NAME, "\n".join(linhas))
    return avisos


def rotulo(step: int | None) -> str:
    """`3 · Analista de Sistema` — o cargo, que é o que se lê."""
    return "—" if step is None else f"{step} · {STEPS[step]['cargo']}"


def rotulo_com_endereco(step: int) -> str:
    """`3 · Analista de Sistema  (elcamargo-system-analyst)`.

    Para onde o endereço é acionável: quem lê precisa saber o que rodar, e o
    cargo sozinho não diz. Nos steps humanos não há endereço a mostrar.
    """
    dados = STEPS[step]
    if dados["tipo"] == "humano":
        return f"{step} · {dados['cargo']}"
    return f"{step} · {dados['cargo']}  ({dados['nome']})"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flow_state.py",
        description="Estado das atividades no fluxo de desenvolvimento com IA.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("caminho", help="imprime o .agents resolvido")
    s.set_defaults(func=cmd_caminho)

    s = sub.add_parser("fluxo", help="lista os steps e as trilhas")
    s.add_argument("--todos", action="store_true",
                   help="mostra também os steps desligados no projeto")
    s.set_defaults(func=cmd_fluxo)

    s = sub.add_parser("iniciar", help="abre uma atividade")
    s.add_argument("id", help="número do card, ou um identificador sem card")
    s.add_argument("--titulo", required=True)
    s.add_argument("--trilha", default="completa", choices=sorted(TRILHAS))
    s.add_argument("--branch", default="")
    s.add_argument("--nota", default="")
    s.add_argument("--complementares", nargs="*", default=[], metavar="ID",
                   help="cards que este trabalho fecha junto com o principal")
    s.add_argument("--reabrir", action="store_true",
                   help="reabre uma atividade existente, preservando o histórico")
    s.set_defaults(func=cmd_iniciar)

    s = sub.add_parser("status", help="mostra uma atividade, ou todas se sem id")
    s.add_argument("id", nargs="?")
    s.add_argument("--todas", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("avancar", help="registra a entrada num step")
    s.add_argument("id")
    s.add_argument("--step", type=int, default=None,
                   help="destino; sem isso vai para o próximo da trilha")
    s.add_argument("--nota", default="")
    s.add_argument("--trilha", default="", choices=["", *sorted(TRILHAS)],
                   help="muda a trilha; exige --forcar")
    s.add_argument("--forcar", action="store_true",
                   help="permite retroceder, pular step ou sair da trilha; "
                        "exige --nota")
    s.set_defaults(func=cmd_avancar)

    s = sub.add_parser("artefato", help="registra um artefato produzido")
    s.add_argument("id")
    s.add_argument("--tipo", required=True)
    s.add_argument("--caminho", required=True)
    s.set_defaults(func=cmd_artefato)

    s = sub.add_parser("pf", help="declara o tamanho em pontos de função")
    s.add_argument("id")
    s.add_argument("--declarado", default=None,
                   help="o do analista, contado da especificação funcional")
    s.add_argument("--aferido", default=None,
                   help="o do step 9, contado da entrega; exige --inventario")
    s.add_argument("--inventario", default=None,
                   help="caminho do inventário que sustenta o --aferido")
    s.set_defaults(func=cmd_pf)

    s = sub.add_parser("conferencia",
                       help="registra o resultado de uma conferência mecânica")
    s.add_argument("id")
    s.add_argument("--ferramenta", required=True,
                   help="catraca, perfis, destino, honestidade, citacoes…")
    s.add_argument("--veredicto", required=True,
                   help=" | ".join(VEREDICTOS))
    s.add_argument("--detalhe", default="", help="uma linha dizendo o que saiu")
    s.set_defaults(func=cmd_conferencia)

    s = sub.add_parser("concluir", help="encerra a atividade")
    s.add_argument("id")
    s.add_argument("--nota", default="")
    s.add_argument("--forcar", action="store_true",
                   help="encerra antes do último step da trilha")
    s.set_defaults(func=cmd_concluir)

    s = sub.add_parser("listar", help="lista as atividades")
    s.add_argument("--todas", action="store_true")
    s.set_defaults(func=cmd_listar)

    s = sub.add_parser("tempo", help="onde o tempo foi, step a step")
    s.add_argument("id")
    s.set_defaults(func=cmd_tempo)

    s = sub.add_parser("indice", help="regera Atividades_em_andamento_com_IA.md")
    s.set_defaults(func=cmd_indice)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FlowStateError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
