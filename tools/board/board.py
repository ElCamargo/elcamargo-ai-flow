#!/usr/bin/env python3
"""Lê o board do projeto — Azure Boards, GitHub, ou nenhum.

O pacote não lia board. Quem lia era a skill de Git do projeto, quando havia
uma: o step 1 declara que "se houver skill declarada, ela manda". Isso funciona
no Acme, que tem a sua, e deixa sem caminho **qualquer projeto que não
tenha** — que é a maioria de quem instala o pacote.

Esta ferramenta é o caminho de quem não tem. Onde houver `[git] skill`, ela
continua mandando; esta é o padrão, não a substituta.

CINCO VERBOS, E NENHUM SEXTO. `criar` não existe, e não é esquecimento: o
board é do solicitante, e abrir item lá é decisão de gestão. Se a demanda
merecer card, o fluxo diz isso e deixa a decisão com a pessoa.

O quinto verbo é o `marcar`, de 15/09/2026, e ele nasce com a mesma cerca:
**etiqueta e comentário, nada mais.** Não muda estado, não muda responsável,
não fecha nem reabre. Ele existe porque as trilhas `backend` e `frontend`
entregam um card em duas vezes, e entre uma e outra o card fica esperando —
`Aguardando frontend`. Etiqueta posta à mão é etiqueta que um dia não se põe,
e quem lê o board é justamente quem não está no fluxo para saber disso.

A saída é a MESMA dos dois boards. Sem isso o step 1 teria que saber de onde o
card veio, e o acoplamento só teria mudado de lugar.

    board.py ler 1061
    board.py comentarios 1061
    board.py listar
    board.py marcar 1061 --tag 'Aguardando frontend' --porque '<justificativa>'
    board.py marcar 1061 --tag 'Aguardando frontend' --porque '<...>' --remover
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "flow-state")))

VERBOS = ("ler", "comentarios", "listar", "vincular", "marcar")


class BoardError(Exception):
    """Erro que a pessoa consegue consertar, e cuja mensagem diz como."""


def executar_cli(argv: list[str], **kw) -> str:
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **kw)
    if r.returncode != 0:
        raise BoardError(f"`{argv[0]}` falhou: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout


def sem_html(texto: str) -> str:
    """A descrição do Azure vem em HTML. Ninguém lê `<div>` num card.

    E o step que recebe isso vai escrever SDD a partir do texto — deixar a
    marcação passar faz a especificação nascer com lixo dentro.
    """
    if not texto:
        return ""
    texto = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", texto, flags=re.I)
    texto = re.sub(r"<li[^>]*>", "- ", texto, flags=re.I)
    texto = re.sub(r"<[^>]+>", "", texto)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(texto)).strip()


class Board:
    """Base. Quatro verbos, e a forma de saída é igual para todos."""

    nome = "?"
    cli = "?"
    instalar = ""
    # Foi exercitado contra o serviço de verdade, ou só contra saída injetada?
    # Declarar isso no código, e não só na prosa, é a mesma regra do quarto
    # veredicto: cobertura incompleta é aceita **desde que declarada**.
    validado_contra_servico_real = False

    def __init__(self, cfg: dict, executar: Callable[..., str] = executar_cli):
        self.cfg = cfg
        self._executar = executar

    def _rodar(self, argv: list[str]) -> str:
        try:
            return self._executar(argv)
        except FileNotFoundError:
            raise BoardError(
                f"o `{self.cli}` não está instalado, e o board deste projeto é "
                f"`{self.nome}`.\n  {self.instalar}\n"
                f"  Ou declare `[board] tipo = \"nenhum\"` e cole o texto do card "
                f"à mão — o fluxo aceita, e diz que aceitou.") from None

    def _json(self, argv: list[str]) -> Any:
        saida = self._rodar(argv)
        if not saida.strip():
            return {}
        try:
            return json.loads(saida)
        except json.JSONDecodeError as exc:
            raise BoardError(f"`{self.cli}` não devolveu JSON: {exc}") from exc

    def ler(self, ident: str) -> dict:
        raise NotImplementedError

    def comentarios(self, ident: str) -> list[dict]:
        raise NotImplementedError

    def listar(self, filtro: str = "") -> list[dict]:
        raise NotImplementedError

    def vincular(self, ident: str, url: str, texto: str) -> None:
        raise NotImplementedError

    def marcar(self, ident: str, tag: str, porque: str,
               remover: bool = False) -> None:
        """Põe ou tira UMA etiqueta, e escreve no card por que ela está lá.

        O quinto verbo, e ele nasce com a mesma cerca do `criar` que não
        existe: **etiqueta e comentário, nada mais.** Não muda estado, não
        muda responsável, não fecha nem reabre. O board é do solicitante, e o
        que o fluxo pode dizer lá é o que ele mesmo fez.

        Ele existe por causa das trilhas `backend` e `frontend`, de
        15/09/2026: a metade de trás fecha sozinha, e o card fica esperando a
        da frente. Se a etiqueta fosse posta à mão, o board mentiria no dia em
        que alguém esquecesse — e quem lê o board é quem não está no fluxo.

        A justificativa NÃO é opcional: etiqueta sem motivo escrito obriga
        quem a encontra a perguntar a alguém.
        """
        raise NotImplementedError


class AzureBoards(Board):
    # O CORPO DO CARD MUDA DE CAMPO CONFORME O TIPO DO ITEM.
    #
    # Medido lendo o bug 1091 do board real: ele NAO tem `System.Description`.
    # O texto dele vive em `Microsoft.VSTS.TCM.ReproSteps`, que e' o campo de
    # Bug. O leitor devolvia corpo VAZIO, em silencio — e um step que recebe
    # corpo vazio escreve SDD sobre nada, sem nunca saber que o card tinha
    # texto. Zero que se le' como medicao, outra vez.
    CAMPOS_DE_CORPO = ("System.Description",
                       "Microsoft.VSTS.TCM.ReproSteps",
                       "Microsoft.VSTS.TCM.SystemInfo")

    nome = "azure"
    cli = "az"
    validado_contra_servico_real = True
    instalar = "Instale o Azure CLI e rode `az login`: https://aka.ms/azure-cli"

    # ITEM E' ESCOPADO POR ORGANIZACAO, CONSULTA E' POR PROJETO.
    #
    # Medido contra o board real: `az boards work-item show --project "X"`
    # responde `unrecognized arguments`. Perguntei ao `--help` em vez de
    # continuar adivinhando, e ele foi direto: `show`, `comment list` e
    # `update` aceitam `--org` e NAO aceitam `--project` — o id de work item ja'
    # e' unico na organizacao. So' o `query` aceita os dois.
    #
    # Por isso `projeto` e' exigido apenas onde ele e' usado: pedi-lo para ler
    # um card faria o fluxo travar por uma chave que aquele comando ignora.

    def _org(self) -> list[str]:
        org = self.cfg.get("org", "")
        if not org:
            raise BoardError(
                "board `azure` exige `[board] org` declarado.\n"
                "  Rode `/config board`, ou declare à mão no `.agents/config.toml`.")
        return ["--org", f"https://dev.azure.com/{org}"]

    def _org_projeto(self) -> list[str]:
        projeto = self.cfg.get("projeto", "")
        if not projeto:
            raise BoardError(
                "listar o board `azure` exige `[board] projeto` declarado.\n"
                "  Ler um card por id não exige — a consulta, sim.")
        return [*self._org(), "--project", projeto]

    def ler(self, ident: str) -> dict:
        d = self._json(["az", "boards", "work-item", "show", "--id", str(ident),
                        "--output", "json", *self._org()])
        f = d.get("fields", {}) or {}
        atribuido = f.get("System.AssignedTo") or {}
        return {
            "id": str(d.get("id", ident)),
            "titulo": f.get("System.Title", ""),
            "estado": f.get("System.State", ""),
            "tipo": f.get("System.WorkItemType", ""),
            "corpo": next(
                (t for t in (sem_html(f.get(c, "")) for c in self.CAMPOS_DE_CORPO) if t),
                ""),
            "responsavel": (atribuido.get("displayName", "")
                            if isinstance(atribuido, dict) else str(atribuido)),
            "url": (f"https://dev.azure.com/{self.cfg.get('org','')}/"
                    f"{self.cfg.get('projeto','')}/_workitems/edit/{ident}"),
        }

    def comentarios(self, ident: str) -> list[dict]:
        # `az boards work-item` NAO tem subcomando `comment` — medido contra o
        # CLI real, que responde "'comment' is misspelled or not recognized".
        # Os subcomandos sao relation, create, delete, show e update. Comentario
        # sai pela passagem REST do proprio `az`.
        d = self._json(["az", "devops", "invoke",
                        "--area", "wit", "--resource", "comments",
                        "--route-parameters", f"project={self.cfg.get('projeto','')}",
                        f"workItemId={ident}",
                        # `7.1-preview.3` faz o `az` tentar converter "7.1.3"
                        # para float e estourar. A forma que ele digere e'
                        # `<versao>-preview`, sem o sufixo numerico. E a versao
                        # sem `-preview` e' recusada: o recurso ainda e' preview.
                        "--api-version", "7.1-preview",
                        "--output", "json", *self._org()])
        itens = d.get("comments", d) if isinstance(d, dict) else d
        return [{"autor": ((c.get("createdBy") or {}).get("displayName", "")),
                 "texto": sem_html(c.get("text", ""))}
                for c in (itens or [])]

    def listar(self, filtro: str = "") -> list[dict]:
        consulta = filtro or (
            "SELECT [System.Id] FROM WorkItems "
            "WHERE [System.State] <> 'Closed' ORDER BY [System.ChangedDate] DESC")
        d = self._json(["az", "boards", "query", "--wiql", consulta,
                        "--output", "json", *self._org_projeto()])
        return [{"id": str(i.get("id", "")),
                 "titulo": (i.get("fields", {}) or {}).get("System.Title", ""),
                 "estado": (i.get("fields", {}) or {}).get("System.State", "")}
                for i in (d or [])]

    def vincular(self, ident: str, url: str, texto: str) -> None:
        self._rodar(["az", "boards", "work-item", "update", "--id", str(ident),
                     "--discussion", f"{texto} {url}".strip(), *self._org()])

    def marcar(self, ident: str, tag: str, porque: str,
               remover: bool = False) -> None:
        # NAO EXERCITADO CONTRA O AZURE DE VERDADE. O `validado_contra_servico_real`
        # desta classe vale para `ler`, `comentarios` e `listar`, que foram
        # medidos contra o board real -- e foi assim que se descobriu que
        # `--project` nao existe no `show` e que o corpo de Bug vive em
        # `ReproSteps`. O `marcar` saiu da documentacao do `az`, e a forma de
        # `--fields "System.Tags=..."` mais `--discussion` na mesma chamada nao
        # passou por execucao. O primeiro uso real confere isso antes de
        # confiar: a hipotese que mais arrisca e' a das duas escritas numa
        # chamada so'.
        #
        # `System.Tags` é um campo de texto, e `update` SUBSTITUI o valor. Ler
        # antes não é zelo: escrever só a etiqueta nova apagaria todas as
        # outras do card de outra pessoa, em silêncio, e o `az` não avisa.
        d = self._json(["az", "boards", "work-item", "show", "--id", str(ident),
                        "--output", "json", *self._org()])
        atuais = [t.strip() for t in
                  ((d.get("fields", {}) or {}).get("System.Tags", "") or "").split(";")
                  if t.strip()]
        iguais = [t for t in atuais if t.lower() == tag.lower()]
        if remover:
            if not iguais:
                return
            novas = [t for t in atuais if t.lower() != tag.lower()]
        else:
            if iguais:
                novas = atuais
            else:
                novas = atuais + [tag]
        argv = ["az", "boards", "work-item", "update", "--id", str(ident),
                "--fields", "System.Tags=" + "; ".join(novas),
                "--discussion", porque, *self._org()]
        self._rodar(argv)


class GitHub(Board):
    """Issues por `gh`. Projects v2 é GraphQL — o `gh` fala os dois.

    NÃO TESTADO CONTRA UM GITHUB DE VERDADE. A forma da saída saiu da
    documentação do `gh`, e os testes injetam essa forma. O primeiro uso real
    deve conferir os nomes de campo antes de confiar no resultado.
    """

    nome = "github"
    cli = "gh"
    validado_contra_servico_real = False
    instalar = "Instale o GitHub CLI e rode `gh auth login`: https://cli.github.com"

    def _repo(self) -> str:
        org, repo = self.cfg.get("org", ""), self.cfg.get("repo", "")
        if not org or not repo:
            raise BoardError(
                "board `github` exige `[board] org` e `[board] repo` declarados.\n"
                "  Rode `/config board`, ou declare à mão no `.agents/config.toml`.")
        return f"{org}/{repo}"

    def ler(self, ident: str) -> dict:
        d = self._json(["gh", "issue", "view", str(ident), "--repo", self._repo(),
                        "--json", "number,title,state,body,assignees,labels,url"])
        atribuidos = d.get("assignees") or []
        rotulos = [r.get("name", "") for r in (d.get("labels") or [])]
        return {
            "id": str(d.get("number", ident)),
            "titulo": d.get("title", ""),
            "estado": d.get("state", ""),
            # O GitHub não tem "tipo de item": o mais próximo é o rótulo. Dizer
            # isso é melhor que inventar um tipo que o board não tem.
            "tipo": rotulos[0] if rotulos else "issue",
            "corpo": d.get("body", "") or "",
            "responsavel": atribuidos[0].get("login", "") if atribuidos else "",
            "url": d.get("url", f"https://github.com/{self._repo()}/issues/{ident}"),
        }

    def comentarios(self, ident: str) -> list[dict]:
        d = self._json(["gh", "issue", "view", str(ident), "--repo", self._repo(),
                        "--json", "comments"])
        return [{"autor": ((c.get("author") or {}).get("login", "")),
                 "texto": c.get("body", "")}
                for c in (d.get("comments") or [])]

    def listar(self, filtro: str = "") -> list[dict]:
        argv = ["gh", "issue", "list", "--repo", self._repo(), "--state", "open",
                "--json", "number,title,state", "--limit", "40"]
        if filtro:
            argv += ["--search", filtro]
        return [{"id": str(i.get("number", "")), "titulo": i.get("title", ""),
                 "estado": i.get("state", "")}
                for i in (self._json(argv) or [])]

    def vincular(self, ident: str, url: str, texto: str) -> None:
        self._rodar(["gh", "issue", "comment", str(ident), "--repo", self._repo(),
                     "--body", f"{texto}\n\n{url}".strip()])

    def marcar(self, ident: str, tag: str, porque: str,
               remover: bool = False) -> None:
        # Aqui o `gh` soma e subtrai rótulo em vez de substituir a lista, então
        # não há o que preservar. Rótulo que não existe no repositório faz o
        # `gh` recusar — e recusar é melhor que criar rótulo no repositório de
        # outra pessoa sem ninguém ter pedido.
        self._rodar(["gh", "issue", "edit", str(ident), "--repo", self._repo(),
                     "--remove-label" if remover else "--add-label", tag])
        self._rodar(["gh", "issue", "comment", str(ident), "--repo", self._repo(),
                     "--body", porque])


class Nenhum(Board):
    """Sem board. O fluxo não trava — a pessoa cola o texto.

    É o mesmo desenho do backend `manual` de anexo: ausência declarada é
    aceita; o que não se aceita é inventar o conteúdo de um card.
    """

    nome = "nenhum"
    cli = "-"

    def _explicar(self):
        raise BoardError(
            "este projeto declara `[board] tipo = \"nenhum\"`.\n"
            "  Cole o texto do card — corpo E comentários — que eu sigo daqui.\n"
            "  Nunca invento o conteúdo de um card que não consigo ler.")

    def ler(self, ident: str) -> dict:
        self._explicar()

    def comentarios(self, ident: str) -> list[dict]:
        self._explicar()

    def listar(self, filtro: str = "") -> list[dict]:
        self._explicar()

    def vincular(self, ident: str, url: str, texto: str) -> None:
        print(f"  [manual] vincule à mão em {ident}: {texto} {url}".rstrip())

    def marcar(self, ident: str, tag: str, porque: str,
               remover: bool = False) -> None:
        verbo = "TIRE" if remover else "PONHA"
        print(f"  [manual] {verbo} a etiqueta `{tag}` no card {ident}, "
              f"e escreva lá: {porque}")


BACKENDS = {"azure": AzureBoards, "github": GitHub, "nenhum": Nenhum}


def criar_board(cfg: dict, executar: Callable[..., str] = executar_cli) -> Board:
    tipo = (cfg or {}).get("tipo", "") or ""
    if tipo not in BACKENDS:
        raise BoardError(
            f"`[board] tipo = \"{tipo}\"` não existe. Os aceitos são: "
            f"{', '.join(sorted(BACKENDS))}.\n"
            f"  Rode `/config board` para declarar — o `detectar` já descobre o "
            f"tipo pelo host do `git remote`.")
    return BACKENDS[tipo](cfg or {}, executar=executar)


def _cfg_do_projeto(raiz: str) -> dict:
    """A config `[board]` do projeto que `--raiz` aponta.

    `resolve_agents_dir()` NAO recebe raiz: ela resolve pelo cwd, pelo
    `.agents` em que se esta, ou pelo git. Chama-la com argumento levantava
    `TypeError` -- ou seja, `--raiz` com qualquer valor diferente de `.`
    quebrava em traceback desde 04/09/2026, em todos os verbos. Achado em
    15/09/2026, exercitando o `marcar` novo de fora do projeto.

    O caminho certo e' entrar na raiz e deixar a resolucao normal acontecer: e'
    o que qualquer um dos tres casos dela ja faz, e nao ha um quarto para
    "raiz passada por bandeira".
    """
    from config import obter  # noqa: E402  (import tardio: o pacote pode rodar solto)
    from flow_state import resolve_agents_dir  # noqa: E402
    anterior = Path.cwd()
    try:
        if raiz != ".":
            os.chdir(raiz)
        agents = resolve_agents_dir()
    finally:
        os.chdir(anterior)
    return obter("board", {}, agents) or {}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lê o board do projeto. Não cria card.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nome in ("ler", "comentarios"):
        s = sub.add_parser(nome)
        s.add_argument("id")
        s.add_argument("--raiz", default=".")
    s = sub.add_parser("listar")
    s.add_argument("--filtro", default="")
    s.add_argument("--raiz", default=".")
    s = sub.add_parser("marcar")
    s.add_argument("id")
    s.add_argument("--tag", required=True)
    s.add_argument("--porque", required=True,
                   help="a justificativa, escrita no card. Não é opcional")
    s.add_argument("--remover", action="store_true")
    s.add_argument("--raiz", default=".")

    args = p.parse_args(argv)
    try:
        b = criar_board(_cfg_do_projeto(args.raiz))
        if args.cmd == "ler":
            saida: Any = b.ler(args.id)
        elif args.cmd == "comentarios":
            saida = b.comentarios(args.id)
        elif args.cmd == "marcar":
            b.marcar(args.id, args.tag, args.porque, args.remover)
            saida = {"card": args.id, "tag": args.tag,
                     "acao": "removida" if args.remover else "posta"}
        else:
            saida = b.listar(args.filtro)
        print(json.dumps(saida, ensure_ascii=False, indent=2))
        return 0
    except BoardError as exc:
        print(f"\n  [erro] {exc}\n", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        # `resolve_agents_dir` levanta `FlowStateError`, que nao e' `BoardError`
        # e escapava como traceback -- a mensagem dela DIZ o que fazer ("rode a
        # partir do projeto, ou defina ELCAMARGO_AGENTS_DIR") e ficava
        # enterrada em dez linhas de pilha.
        print(f"\n  [erro] {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Windows: com a saída em pipe, `print` usa a codificação da região
    # (cp1252) e ESTOURA em `→`, que este pacote usa às pencas. Ver
    # `references/windows.md`.
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    raise SystemExit(main())
