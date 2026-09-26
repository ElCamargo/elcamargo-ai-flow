#!/usr/bin/env python3
"""Mapa do terreno: o que já existe em volta do domínio que a atividade toca.

O step 3 gastou 284 mil tokens e 91 chamadas de ferramenta para especificar 18
requisitos. A maior parte não foi especificação: foi descobrir onde as coisas
moram — qual entidade, qual migration, qual serviço, qual spec anterior, qual
ADR, e se a branch de trabalho tem mesmo a base que a análise supõe.

Isso é varredura, e varredura é da máquina.

    python3 domain.py --termo "catalog item"
    python3 domain.py --termo "catalog item" --saida /tmp/terreno.md
    python3 domain.py --termo catalogo --pasta backend/src/modules/catalog

## O que este mapa NÃO é

Não é análise, não é recomendação, e **não é evidência**. É um índice: diz onde
procurar, não o que concluir. Toda afirmação que sair daqui e for para a SDD
precisa ser confirmada no arquivo, com caminho e linha.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flow-state"))
from config import pathspec_ignorar as ignorar  # noqa: E402
from briefing import (BriefingError, EXTENSOES_CODIGO, carregar_config, git,  # noqa: E402
                      raiz_de_trabalho)

LIMITE_POR_GRUPO = 12
LIMITE_DETALHE = 25


def termos(termo: str) -> list[str]:
    """Do termo do usuário para as formas que o código usa.

    "catalog item" precisa achar catalogItem, CatalogItem, catalog_item,
    catalog-item. Sem isso o mapa sai vazio num repositório que fala o
    assunto o tempo todo.
    """
    partes = [p for p in re.split(r"[\s_\-]+", termo.strip()) if p]
    if not partes:
        raise BriefingError("o termo veio vazio")
    baixo = [p.lower() for p in partes]
    camel = baixo[0] + "".join(p.capitalize() for p in baixo[1:])
    saida = {
        "".join(p.capitalize() for p in baixo),   # CatalogItem
        camel,                                     # catalogItem
        "_".join(baixo),                           # catalog_item
        "-".join(baixo),                           # catalog-item
        " ".join(baixo),                           # catalog item
    }
    return sorted(saida, key=len, reverse=True)


def alargar(termo: str) -> list[str]:
    """Só a primeira palavra. Usado quando o termo completo não acha nada.

    Nunca junto com o termo completo: "catalog item" alargado para "catalog"
    trouxe 189 arquivos e 42 KB num repositório onde o domínio real tem uma
    dúzia. Um mapa desse tamanho custa mais que a exploração que ele evita.
    """
    partes = [p for p in re.split(r"[\s_\-]+", termo.strip()) if p]
    return [partes[0].lower()] if partes else []


PAPEIS = [
    ("migration", r"(^|/)migrations?/"),
    ("entidade", r"(^|/)entities?/|\.entity\.(ts|js)$"),
    ("controller", r"\.controller\.(ts|js)$"),
    ("serviço", r"\.service\.(ts|js)$"),
    ("teste", r"\.(spec|test)\.[jt]sx?$|(^|/)(tests?|__tests__)/"),
    ("componente", r"(^|/)components?/.*\.(tsx|jsx|vue|svelte)$"),
    ("spec", r"(^|/)docs?/.*spec|(^|/)specs?/"),
    ("adr", r"(^|/)(adr|adrs|decisions?)/"),
    ("i18n", r"(^|/)(i18n|locales?|messages|translations?)/"),
    ("doc", r"\.mdx?$"),
]


def papel(caminho: str) -> str:
    for nome, padrao in PAPEIS:
        if re.search(padrao, caminho, re.IGNORECASE):
            return nome
    return "outro"


def buscar(raiz: Path, alvos: list[str]) -> dict[str, set[str]]:
    """Arquivos que citam qualquer forma do termo, agrupados por papel."""
    achados: dict[str, set[str]] = defaultdict(set)
    for alvo in alvos:
        r = subprocess.run(
            ["git", "grep", "-l", "-i", "-F", alvo, "--",
             *ignorar([":!*.lock", ":!*-lock.json"])],
            cwd=raiz, capture_output=True, text=True)
        for linha in r.stdout.splitlines():
            if linha.strip():
                achados[papel(linha)].add(linha)
    return achados


RE_COLUNA = re.compile(
    r"^\s*(?:@Column|@PrimaryColumn|@PrimaryGeneratedColumn|@ManyToOne|@OneToMany"
    r"|@ManyToMany|@OneToOne|@JoinColumn|@Index|@Unique)\b(.*)$")
RE_CAMPO = re.compile(r"^\s*(?:readonly\s+)?([a-zA-Z_$][\w$]*)\s*!?\??\s*:\s*([^;=]+)")
RE_METODO_PUB = re.compile(
    r"^\s{2}(?:public\s+|async\s+)*([a-zA-Z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*([^{;]+))?")
RE_ROTA = re.compile(r"^\s*@(Get|Post|Put|Patch|Delete)\s*\(\s*(['\"`])?([^'\"`)]*)")
RE_SQL = re.compile(r"(CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)|ALTER\s+TABLE|DROP\s+\w+)"
                    r"[^\n;']{0,160}", re.IGNORECASE)
RE_CODIGO_ERRO = re.compile(r"code:\s*['\"]([A-Z][A-Z0-9_]{4,})['\"]")


def ler(raiz: Path, caminho: str) -> list[str]:
    try:
        return (raiz / caminho).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def detalhar_entidade(raiz: Path, caminho: str) -> list[str]:
    saida, pendente = [], None
    for linha in ler(raiz, caminho):
        m = RE_COLUNA.match(linha)
        if m:
            pendente = linha.strip()[:100]
            continue
        if pendente:
            c = RE_CAMPO.match(linha)
            if c:
                saida.append(f"{c.group(1)}: {c.group(2).strip()}   `{pendente}`")
            pendente = None
    return saida


def detalhar_servico(raiz: Path, caminho: str) -> list[str]:
    saida = []
    for linha in ler(raiz, caminho):
        m = RE_METODO_PUB.match(linha)
        if not m or "=" in linha.split("(")[0]:
            continue
        nome = m.group(1)
        if nome in {"constructor", "if", "for", "while", "catch", "switch", "return"}:
            continue
        if re.search(r"^\s{2}private\s", linha):
            continue
        args = re.sub(r"\s+", " ", m.group(2))[:70]
        ret = (m.group(3) or "").strip()[:40]
        saida.append(f"{nome}({args})" + (f": {ret}" if ret else ""))
    return saida


def detalhar_controller(raiz: Path, caminho: str) -> list[str]:
    saida, base = [], ""
    for linha in ler(raiz, caminho):
        b = re.match(r"^\s*@Controller\s*\(\s*['\"`]?([^'\"`)]*)", linha)
        if b:
            base = b.group(1).strip("/")
        m = RE_ROTA.match(linha)
        if m:
            rota = (m.group(3) or "").strip("/")
            caminho_completo = "/".join(p for p in (base, rota) if p)
            saida.append(f"{m.group(1).upper():<6} /{caminho_completo}")
    return saida


def detalhar_migration(raiz: Path, caminho: str, alvos: list[str]) -> list[str]:
    texto = "\n".join(ler(raiz, caminho))
    saida = []
    for m in RE_SQL.finditer(texto):
        trecho = re.sub(r"\s+", " ", m.group(0)).strip()
        if any(a.lower() in trecho.lower() for a in alvos):
            saida.append(trecho[:150])
    return saida


def estado_da_base(raiz: Path) -> list[str]:
    """A branch de trabalho tem mesmo a base que a análise supõe?

    Numa execução real a análise pressupunha um painel que existia só numa
    branch de feature não mesclada, 32 commits à frente. Especificar contra a
    branch padrão teria quebrado no primeiro import.
    """
    linhas = []
    ramo = git(["rev-parse", "--abbrev-ref", "HEAD"], raiz).strip()
    ref = git(["symbolic-ref", "refs/remotes/origin/HEAD"], raiz).strip()
    padrao = ref.rsplit("/", 1)[-1] if ref else "main"
    linhas.append(f"| Branch de trabalho | `{ramo}` |")
    linhas.append(f"| Branch padrão | `{padrao}` |")
    if ramo and padrao and ramo != padrao:
        cont = git(["rev-list", "--left-right", "--count", f"{padrao}...HEAD"], raiz).split()
        if len(cont) == 2:
            linhas.append(f"| Distância | {cont[1]} commits à frente, "
                          f"{cont[0]} atrás de `{padrao}` |")
    branches = git(["branch", "-a", "--sort=-committerdate",
                    "--format=%(refname:short)"], raiz).splitlines()[:10]
    if branches:
        linhas.append(f"| Branches recentes | {', '.join(b for b in branches[:6] if b)} |")
    return linhas


def principal(args) -> int:
    raiz = raiz_de_trabalho()
    cfg = carregar_config(raiz)
    alvos = termos(args.termo)
    achados = buscar(raiz, alvos)
    alargado = False
    if not sum(len(v) for v in achados.values()):
        largos = alargar(args.termo)
        if largos and largos != alvos:
            achados = buscar(raiz, largos)
            if sum(len(v) for v in achados.values()):
                alvos, alargado = largos, True

    if args.pasta:
        achados = {k: {c for c in v if c.startswith(args.pasta)}
                   for k, v in achados.items()}
        achados = {k: v for k, v in achados.items() if v}

    total = sum(len(v) for v in achados.values())
    if not total:
        raise BriefingError(
            f"nenhum arquivo cita '{args.termo}' em nenhuma das formas "
            f"({', '.join(alvos)}). Ou o termo está errado, ou o domínio ainda "
            "não existe no código — as duas coisas mudam o que você vai escrever."
        )

    L: list[str] = []
    w = L.append
    w(f"# Mapa do terreno · {args.termo}")
    w("")
    w("Levantamento de **fatos** sobre o que já existe em volta deste domínio.")
    w("")
    w("**Isto é um índice, não evidência.** Diz onde procurar, não o que concluir.")
    w("Toda afirmação que sair daqui e entrar na especificação precisa ser")
    w("confirmada no arquivo, com caminho e linha.")
    w("")
    w(f"Formas procuradas: {', '.join(f'`{a}`' for a in alvos)}")
    if alargado:
        w("")
        w(f"**O termo completo não achou nada, então a busca foi alargada para a**")
        w(f"**primeira palavra.** O mapa está mais largo que o assunto: parte do que")
        w("está aqui é de outro subdomínio. Confirme antes de usar.")
    w("")

    w("## A base")
    w("")
    w("| | |")
    w("| --- | --- |")
    L.extend(estado_da_base(raiz))
    w("")
    w("Confira se o que a análise pressupõe existe **nesta** base. Um módulo que")
    w("vive só numa branch não mesclada é dependência dura, não detalhe.")
    w("")

    w("## Onde o domínio aparece")
    w("")
    w("| Papel | Arquivos |")
    w("| --- | ---: |")
    for nome, _ in PAPEIS + [("outro", "")]:
        if achados.get(nome):
            w(f"| {nome} | {len(achados[nome])} |")
    w(f"| **total** | **{total}** |")
    w("")

    def secao(nome: str, titulo: str, detalhador=None, limite=LIMITE_DETALHE):
        arquivos = sorted(achados.get(nome, []))
        if not arquivos:
            return
        w(f"## {titulo}")
        w("")
        for caminho in arquivos[:LIMITE_POR_GRUPO]:
            w(f"**`{caminho}`**")
            if detalhador:
                itens = detalhador(caminho)
                for i in itens[:limite]:
                    w(f"  - `{i}`")
                if len(itens) > limite:
                    w(f"  - … e mais {len(itens) - limite}")
                if not itens:
                    w("  - (nada extraído automaticamente — abra o arquivo)")
            w("")
        if len(arquivos) > LIMITE_POR_GRUPO:
            w(f"… e mais {len(arquivos) - LIMITE_POR_GRUPO} arquivos neste papel, "
              "não listados.")
            w("")

    secao("entidade", "Entidades e colunas", lambda c: detalhar_entidade(raiz, c))
    secao("migration", "Migrations que tocam o domínio",
          lambda c: detalhar_migration(raiz, c, alvos), limite=15)
    secao("controller", "Endpoints", lambda c: detalhar_controller(raiz, c))
    secao("serviço", "Serviços e métodos públicos", lambda c: detalhar_servico(raiz, c))

    for nome, titulo in (("spec", "Especificações anteriores"), ("adr", "ADRs"),
                         ("componente", "Componentes de tela"), ("teste", "Testes"),
                         ("i18n", "Arquivos de tradução")):
        arquivos = sorted(achados.get(nome, []))
        if not arquivos:
            continue
        w(f"## {titulo}")
        w("")
        for c in arquivos[:LIMITE_POR_GRUPO]:
            w(f"- `{c}`")
        if len(arquivos) > LIMITE_POR_GRUPO:
            w(f"- … e mais {len(arquivos) - LIMITE_POR_GRUPO}")
        w("")

    # Códigos de erro: o vocabulário que a tela e o teste consomem.
    codigos: dict[str, set[str]] = defaultdict(set)
    for grupo in ("serviço", "controller"):
        for caminho in sorted(achados.get(grupo, []))[:LIMITE_POR_GRUPO]:
            for linha in ler(raiz, caminho):
                for m in RE_CODIGO_ERRO.finditer(linha):
                    codigos[m.group(1)].add(caminho)
    if codigos:
        w("## Códigos de erro já usados no domínio")
        w("")
        for codigo in sorted(codigos)[:30]:
            w(f"- `{codigo}`")
        w("")
        w("Reusar um código existente mantém a tela e o teste falando a mesma")
        w("língua. Criar um novo para o mesmo caso quebra os dois.")
        w("")

    # Decisões de fora de escopo que casam com o domínio.
    fora = cfg.get("docs", {}).get("fora_de_escopo")
    if fora and (raiz / fora).is_dir():
        casam = [p for p in sorted((raiz / fora).glob("**/*.md"))
                 if any(a.lower() in p.read_text(encoding="utf-8", errors="replace").lower()
                        for a in alvos)]
        w("## Memória de rejeição que cita o domínio")
        w("")
        if casam:
            for p in casam:
                w(f"- `{p.relative_to(raiz)}`")
            w("")
            w("**Leia antes de especificar.** Um item já rejeitado não se recusa")
            w("sozinho: vira pendência com a decisão antiga citada.")
        else:
            w(f"Nenhum arquivo em `{fora}` cita este domínio. Isso não é o mesmo")
            w("que nada ter sido rejeitado — case por conceito, não por palavra.")
        w("")

    w("## O que este mapa não cobre")
    w("")
    w("- **Comportamento.** Ele lista assinaturas, não o que elas fazem.")
    w("- **Corretude.** Um método listado pode estar quebrado.")
    w("- **O que não tem o termo no nome.** Um serviço que trata o domínio com")
    w("  outro vocabulário não aparece aqui. Se o mapa parecer pequeno demais")
    w("  para o assunto, ele está.")
    w("")

    texto = "\n".join(L)
    if len(texto) > 25_000:
        texto += (
            "\n> **Este mapa passou de 25 KB.** Isso quase sempre significa termo\n"
            "> largo demais, não domínio grande. Rode de novo com `--pasta` ou com\n"
            "> um termo mais específico — um mapa que custa mais que a exploração\n"
            "> que ele evita não serve para nada.\n")
    if args.saida:
        destino = Path(args.saida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        print(f"Mapa escrito em {destino}")
        print(f"  {total} arquivos em {len(achados)} papéis, "
              f"{len(codigos)} códigos de erro")
    else:
        print(texto)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="domain", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--termo", required=True,
                   help="o domínio, na língua do negócio ou do código")
    p.add_argument("--pasta", default=None, help="restringe a um prefixo de caminho")
    p.add_argument("--saida", default=None)
    args = p.parse_args(argv)
    try:
        return principal(args)
    except BriefingError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
