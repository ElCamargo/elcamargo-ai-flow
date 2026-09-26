#!/usr/bin/env python3
"""Dossiê de fatos da entrega, preparado uma vez para todas as frentes de revisão.

Na POC as cinco frentes do step 9 gastaram 310 mil tokens para revisar 36 linhas
de diff. A maior parte não foi revisão: foi cada uma redescobrir o mesmo — rodar
o mesmo `git diff`, abrir os mesmos arquivos, procurar quem chama o mesmo
método, e descobrir de novo como se roda o lint deste projeto.

Este dossiê faz esse levantamento UMA vez. Cada revisor lê um arquivo em vez de
fazer oito idas e voltas.

## O que este dossiê NÃO contém, e por quê

Nenhum achado. Nenhum "olhe para isto". Nenhuma ordem de prioridade.

As cinco frentes valem porque julgam de forma independente — foi assim que dois
vazamentos entre clientes apareceram numa entrega com onze testes verdes. Um
dossiê que dissesse "atenção ao filtro por cliente" faria as cinco olharem para
o mesmo lugar e chegarem à mesma conclusão, e a independência viraria eco.

Fato entra. Julgamento é de cada uma.

    python3 briefing.py --base main
    python3 briefing.py --base main --saida /tmp/briefing.md
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

LIMITE_DIFF = 3000        # linhas; acima disso trunca e avisa
LIMITE_ARQUIVO = 600      # linhas de arquivo mostradas por inteiro
LIMITE_REFERENCIAS = 12   # chamadores listados por símbolo

EXTENSOES_CODIGO = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".java",
                    ".kt", ".cs", ".php", ".rs", ".swift", ".sql"}


class BriefingError(Exception):
    pass


def git(args: list[str], raiz: Path) -> str:
    r = subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout


def raiz_de_trabalho() -> Path:
    """A árvore em que quem chamou está — não a principal.

    Numa worktree de POC o `--git-common-dir` aponta para o repositório
    principal, e o dossiê sairia descrevendo o código errado. Já aconteceu duas
    vezes no fluxo, em ferramentas diferentes.
    """
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise BriefingError("não estou dentro de um repositório git")
    return Path(r.stdout.strip())


def carregar_config(raiz: Path) -> dict:
    """Acha o config do projeto, inclusive quando se roda de dentro de um worktree.

    Numa worktree, `.agents` não está ao lado do código: ele vive na raiz do
    repositório PRINCIPAL. Subir um nível não chega lá — a worktree costuma
    morar em `.claude/worktrees/<nome>`, dois ou três níveis abaixo.

    Sem isto, o dossiê declarava "o projeto não declara portões" para um
    projeto com `[gates]` no config, e quatro frentes de revisão foram
    procurar lint e teste à mão. Um levantamento que existe para evitar
    redescoberta causando redescoberta.
    """
    candidatos = [raiz / ".agents" / "config.toml",
                  raiz.parent / ".agents" / "config.toml"]
    # A raiz do repositório principal, que é onde .agents mora numa worktree.
    comum = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=raiz, capture_output=True, text=True)
    if comum.returncode == 0 and comum.stdout.strip():
        principal = Path(comum.stdout.strip()).parent
        candidatos.append(principal / ".agents" / "config.toml")
    for candidato in candidatos:
        if candidato.exists():
            return tomllib.loads(candidato.read_text(encoding="utf-8"))
    return {}


@dataclass
class Arquivo:
    caminho: str
    situacao: str      # A M D R
    adicionadas: int
    removidas: int


def ponto_de_partida(raiz: Path, base: str) -> str:
    """Onde a entrega começou: o merge-base entre a base e HEAD.

    Comparar contra o merge-base e NÃO contra HEAD é o que faz o dossiê
    enxergar trabalho ainda não commitado. Na POC o diff revisado estava todo
    fora do índice: um dossiê montado com `base...HEAD` teria saído vazio e
    cinco revisores aprovariam o nada.
    """
    mb = git(["merge-base", base, "HEAD"], raiz).strip()
    return mb or base


def nao_rastreados(raiz: Path) -> list[str]:
    """Arquivos que o git ainda não conhece.

    `git diff` não os mostra. Um arquivo novo e não adicionado sumiria do
    dossiê sem aviso — e some justamente quando é o arquivo principal da
    entrega.
    """
    saida = git(["ls-files", "--others", "--exclude-standard"], raiz)
    return [l for l in saida.splitlines() if l.strip()]


def arquivos_mudados(raiz: Path, base: str) -> list[Arquivo]:
    numstat = git(["diff", "--numstat", base], raiz)
    status = git(["diff", "--name-status", base], raiz)
    situacoes = {}
    for linha in status.splitlines():
        partes = linha.split("\t")
        if len(partes) >= 2:
            situacoes[partes[-1]] = partes[0][:1]
    saida = []
    for linha in numstat.splitlines():
        partes = linha.split("\t")
        if len(partes) < 3:
            continue
        mais, menos, caminho = partes[0], partes[1], partes[-1]
        saida.append(Arquivo(
            caminho=caminho,
            situacao=situacoes.get(caminho, "?"),
            adicionadas=0 if mais == "-" else int(mais),
            removidas=0 if menos == "-" else int(menos),
        ))
    return saida


# O que interessa a um revisor é a SUPERFÍCIE que mudou e quem depende dela.
# Variável local nunca qualifica. A primeira versão capturava `const rows =` e
# `const summary =` dentro de métodos, e cada nome comum trazia trinta arquivos
# homônimos: o dossiê ficava maior que a exploração que ele deveria evitar.

RE_EXPORTADO = re.compile(
    r"^\+\s*export\s+(?:default\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var|type|interface|enum)\s+"
    r"([A-Za-z_$][\w$]*)"
)
# Declaração no nível zero de indentação: é do módulo, não de dentro de nada.
RE_TOPO = re.compile(
    r"^\+(?:async\s+)?(?:def|class|function|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
# Assinatura de método de classe. Exige que a linha TERMINE como assinatura —
# com `{`, `;` ou tipo de retorno — para não casar com `const x = fn(`.
RE_METODO = re.compile(
    r"^\+\s{2,8}(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+)*"
    # O fim aceita `{`, `{}`, `;` ou nada: um método vazio numa linha só
    # (`async listar(): Promise<void> {}`) não casava e o símbolo sumia.
    r"([a-zA-Z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[^={]+?)?\s*(?:\{\s*\}?|;)?\s*$"
)

PALAVRAS_RESERVADAS = {"if", "for", "while", "switch", "catch", "return", "await",
                       "typeof", "new", "delete", "throw", "constructor", "super",
                       "function", "class", "const", "let", "var", "import",
                       "export", "default", "describe", "it", "test", "expect",
                       "beforeEach", "afterEach", "beforeAll", "afterAll"}

# Acima disto o nome quase certamente é palavra comum, e a lista de "quem
# referencia" vira ruído em vez de informação.
LIMITE_HOMONIMO = 25


def simbolos_tocados(diff: str) -> list[str]:
    nomes: list[str] = []
    for linha in diff.splitlines():
        if "=" in linha.split("(")[0]:
            # `const rows = this.repo.find(` — atribuição, não declaração de API.
            if not RE_EXPORTADO.match(linha):
                continue
        for padrao in (RE_EXPORTADO, RE_TOPO, RE_METODO):
            m = padrao.match(linha)
            if m:
                nome = m.group(1)
                if nome not in PALAVRAS_RESERVADAS and len(nome) > 2:
                    nomes.append(nome)
                break
    vistos: list[str] = []
    for n in nomes:
        if n not in vistos:
            vistos.append(n)
    return vistos


def quem_referencia(raiz: Path, simbolo: str, excluir: set[str]) -> list[str]:
    """Quem chama o símbolo, restrito a código.

    Documentação e JSON citando a palavra não são chamadores. Sem esse filtro,
    um método chamado `summary` trazia specs em markdown e arquivos de tradução
    junto com os chamadores de verdade, e a lista deixava de informar.
    """
    pathspec = [f"*{e}" for e in sorted(EXTENSOES_CODIGO)]
    r = subprocess.run(
        ["git", "grep", "-l", "-w", simbolo, "--", *pathspec,
         ":!*node_modules*", ":!*dist*", ":!*build*"],
        cwd=raiz, capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [l for l in r.stdout.splitlines() if l and l not in excluir]


def testes_relacionados(raiz: Path, arquivos: list[Arquivo]) -> list[str]:
    """Arquivos de teste que existem para os arquivos tocados."""
    achados: list[str] = []
    todos = git(["ls-files"], raiz).splitlines()
    for a in arquivos:
        p = Path(a.caminho)
        raiz_nome = p.stem
        for t in todos:
            if t == a.caminho:
                continue
            tp = Path(t)
            if not re.search(r"\.(test|spec)\.|(^|/)(tests?|__tests__|spec)/", t):
                continue
            if raiz_nome in tp.stem or raiz_nome == tp.stem.split(".")[0]:
                if t not in achados:
                    achados.append(t)
    return achados


def principal(args) -> int:
    raiz = raiz_de_trabalho()
    cfg = carregar_config(raiz)

    base = args.base
    if not base:
        ref = git(["symbolic-ref", "refs/remotes/origin/HEAD"], raiz).strip()
        base = ref.rsplit("/", 1)[-1] if ref else "main"
    if not git(["rev-parse", "--verify", base], raiz).strip():
        raise BriefingError(
            f"não achei a base '{base}'. Passe --base com uma ref que existe "
            f"(branches: {', '.join(git(['branch', '--format=%(refname:short)'], raiz).split()[:8])})"
        )

    partida = ponto_de_partida(raiz, base)
    arquivos = arquivos_mudados(raiz, partida)
    soltos = nao_rastreados(raiz)
    for caminho in soltos:
        alvo = raiz / caminho
        try:
            n = len(alvo.read_text(encoding="utf-8", errors="replace").splitlines())
        except (OSError, UnicodeError):
            n = 0
        arquivos.append(Arquivo(caminho=caminho, situacao="U", adicionadas=n, removidas=0))

    if not arquivos:
        raise BriefingError(
            f"nenhum arquivo mudou desde {base}. Confira a base: revisar "
            "um diff vazio produz cinco relatórios dizendo que está tudo bem."
        )

    diff = git(["diff", partida], raiz)
    linhas_diff = diff.splitlines()
    truncado = len(linhas_diff) > LIMITE_DIFF

    L: list[str] = []
    w = L.append

    w("# Dossiê da entrega")
    w("")
    w("Levantamento de **fatos**, preparado uma vez para todas as frentes de revisão.")
    w("")
    w("**Não há nenhum achado aqui, de propósito.** Este dossiê não diz onde olhar")
    w("nem o que é problema. As frentes valem porque julgam de forma independente;")
    w("um dossiê que apontasse faria todas olharem para o mesmo lugar.")
    w("")
    w("Se algo que você precisa não está aqui, vá buscar — isto encurta a")
    w("redescoberta, não substitui a sua leitura.")
    w("")

    # ---- contexto
    ramo = git(["rev-parse", "--abbrev-ref", "HEAD"], raiz).strip()
    commits = git(["log", "--oneline", f"{partida}..HEAD"], raiz).splitlines()
    sujo = bool(git(["status", "--porcelain"], raiz).strip())
    w("## Contexto")
    w("")
    w(f"| | |")
    w(f"| --- | --- |")
    w(f"| Repositório | `{raiz}` |")
    w(f"| Branch | `{ramo}` |")
    w(f"| Base | `{base}` |")
    w(f"| Commits | {len(commits)} |")
    total_mais = sum(a.adicionadas for a in arquivos)
    total_menos = sum(a.removidas for a in arquivos)
    w(f"| Diff | {len(arquivos)} arquivos, +{total_mais} −{total_menos} |")
    w(f"| Estado | {'com alterações fora do commit' if sujo else 'árvore limpa'} |")
    w("")
    if sujo:
        w("O diff abaixo compara a **árvore de trabalho** com o ponto de partida, e")
        w("portanto inclui o que ainda não foi commitado. É isso que está sendo")
        w("entregue.")
        w("")
    if commits:
        for c in commits[:15]:
            w(f"- `{c}`")
        if len(commits) > 15:
            w(f"- … e mais {len(commits) - 15}")
        w("")

    # ---- arquivos
    w("## Arquivos tocados")
    w("")
    w("| Situação | Arquivo | + | − |")
    w("| --- | --- | ---: | ---: |")
    nome_situacao = {"A": "novo", "M": "alterado", "D": "removido",
                     "R": "renomeado", "U": "não rastreado"}
    for a in sorted(arquivos, key=lambda x: -(x.adicionadas + x.removidas)):
        w(f"| {nome_situacao.get(a.situacao, a.situacao)} | `{a.caminho}` "
          f"| {a.adicionadas} | {a.removidas} |")
    if soltos:
        w("")
        w(f"**{len(soltos)} arquivo(s) não rastreado(s).** Eles NÃO aparecem no diff")
        w("abaixo — `git diff` não conhece arquivo que o git não rastreia. Se algum")
        w("deles é parte da entrega, abra e leia; se não é, alguém esqueceu de")
        w("limpar. As duas coisas importam.")
    w("")

    # ---- testes
    testes = testes_relacionados(raiz, arquivos)
    caminhos_mudados = {a.caminho for a in arquivos}
    w("## Testes que existem para os arquivos tocados")
    w("")
    if testes:
        for t in testes:
            marca = " *(alterado nesta entrega)*" if t in caminhos_mudados else ""
            w(f"- `{t}`{marca}")
    else:
        w("Nenhum arquivo de teste encontrado com nome correspondente.")
        w("Isso é um fato sobre nomes de arquivo, não uma conclusão sobre cobertura.")
    w("")

    # ---- símbolos e chamadores
    simbolos = simbolos_tocados(diff)
    if simbolos:
        w("## Símbolos introduzidos ou alterados, e quem os referencia")
        w("")
        w("Levantado por `git grep -w` no nome. Homônimo entra; confira antes de usar.")
        w("")
        for s in simbolos[:25]:
            refs = quem_referencia(raiz, s, caminhos_mudados)
            w(f"**`{s}`**")
            if len(refs) > LIMITE_HOMONIMO:
                w(f"  - {len(refs)} arquivos citam este nome. É comum demais para a")
                w("    lista servir de alguma coisa — quase tudo ali é homônimo.")
                w(f"    Se precisar, refine: `git grep -w {s} -- <pasta>`")
            elif refs:
                for r in refs[:LIMITE_REFERENCIAS]:
                    w(f"  - `{r}`")
                if len(refs) > LIMITE_REFERENCIAS:
                    w(f"  - … e mais {len(refs) - LIMITE_REFERENCIAS}")
            else:
                w("  - nenhuma referência fora dos arquivos desta entrega")
            w("")
        if len(simbolos) > 25:
            w(f"… e mais {len(simbolos) - 25} símbolos não listados.")
            w("")

    # ---- gates
    gates = cfg.get("gates", {})
    w("## Portões declarados pelo projeto")
    w("")
    if gates:
        w("| Portão | Comando |")
        w("| --- | --- |")
        for k, v in gates.items():
            w(f"| {k} | `{v}` |")
        w("")
        w("Rode os que forem do seu escopo. Falha de portão é fato, não opinião —")
        w("cole a saída.")
    else:
        w("O projeto não declara portões em `config.toml`. Descubra pelo")
        w("`package.json`, `Makefile` ou equivalente, e **diga o que você usou**.")
    w("")

    # ---- documentos
    docs = cfg.get("docs", {})
    w("## Documentos do projeto")
    w("")
    linhas_doc = []
    def registrar(rotulo: str, valor):
        for v in ([valor] if isinstance(valor, str) else list(valor or [])):
            caminho = raiz / v
            existe = caminho.exists()
            linhas_doc.append(f"| {rotulo} | `{v}` | {'existe' if existe else 'AUSENTE'} |")
    if docs:
        w("| | Caminho | |")
        w("| --- | --- | --- |")
        registrar("specs", docs.get("specs", ""))
        registrar("convenções", docs.get("convencoes", []))
        registrar("ADRs", docs.get("adrs", ""))
        registrar("fora de escopo", docs.get("fora_de_escopo", ""))
        for l in linhas_doc:
            w(l)
    else:
        w("Nada declarado em `config.toml`.")
    w("")

    stack = cfg.get("stack", {})
    if stack:
        w("## Stack declarada")
        w("")
        for k, v in stack.items():
            w(f"- **{k}**: {', '.join(v) if isinstance(v, list) else v}")
        w("")

    # ---- diff
    w("## Diff completo")
    w("")
    if truncado:
        w(f"> **Truncado.** O diff tem {len(linhas_diff)} linhas e este dossiê mostra")
        w(f"> as primeiras {LIMITE_DIFF}. O resto NÃO está aqui — rode")
        w(f"> `git diff {partida}` para ver inteiro. Não conclua nada sobre o")
        w("> que não apareceu.")
        w("")
    w("```diff")
    L.extend(linhas_diff[:LIMITE_DIFF])
    w("```")
    w("")

    texto = "\n".join(L)
    if args.saida:
        destino = Path(args.saida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        print(f"Dossiê escrito em {destino}")
        print(f"  {len(arquivos)} arquivos, +{total_mais} −{total_menos}, "
              f"{len(simbolos)} símbolos, {len(testes)} testes relacionados")
        if truncado:
            print(f"  ATENÇÃO: diff truncado em {LIMITE_DIFF} de {len(linhas_diff)} linhas")
        print()
        print("Passe o caminho às frentes de revisão. Cada uma lê este arquivo em vez")
        print("de refazer o levantamento.")
    else:
        print(texto)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="briefing", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=None,
                   help="ref de comparação (padrão: a branch padrão do remoto)")
    p.add_argument("--saida", default=None, help="grava em arquivo em vez de stdout")
    args = p.parse_args(argv)
    try:
        return principal(args)
    except BriefingError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
