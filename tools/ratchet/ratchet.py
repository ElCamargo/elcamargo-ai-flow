#!/usr/bin/env python3
"""Separa o teste que a entrega quebrou do teste que já falhava.

Um portão que devolve vermelho não diz qual dos dois é. Na POC isso apareceu
três vezes: um aviso de lint marcado "pré-existente" à mão porque alguém por
acaso sabia, 126 de 152 invariantes visuais ignoradas sem que ninguém contasse,
e a volta 2 reprocessando o mesmo passivo da volta 1.

A catraca guarda o conjunto de falhas conhecidas e compara:

    novo         está falhando e não estava na linha de base  -> reprova
    conhecido    já falhava antes                             -> não reprova
    consertado   estava na base e passou                      -> a base ENCOLHE

O terceiro é o que a faz catraca: ela só aperta. Uma falha que foi consertada
sai da base e não pode voltar em silêncio. Admitir falha nova na base é decisão
explícita, com motivo escrito — `--admitir`.

    ratchet.py gravar   --base catraca.json --portao lint --formato eslint saida.txt
    ratchet.py conferir --base catraca.json --portao lint saida.txt
    ratchet.py apertar  --base catraca.json --portao lint saida.txt

A saída do portão vem por arquivo ou por `-` (stdin).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path


class CatracaError(Exception):
    pass


VERSION = 1


# --------------------------------------------------------------------------
# A identidade de uma falha conhecida
# --------------------------------------------------------------------------
# NÃO ENTRA NELA NADA QUE UMA EDIÇÃO LEGÍTIMA MUDE — e o número da linha é o
# exemplo canônico. O relatório de uma revisão real registrou um aviso
# pré-existente como `app-shell.tsx:176`; a entrega inseriu código acima dele e
# hoje o mesmo aviso, do mesmo código, mora na linha 185. Uma catraca que
# guardasse a linha diria "falha nova" e devolveria a entrega por um aviso que
# ninguém tocou.
#
# Para teste, a identidade é `arquivo > suíte > nome`. Para lint, é
# `arquivo :: regra` — sem linha, sem coluna, sem a mensagem, que muda quando a
# regra é reescrita numa atualização de dependência.


def _relativo(caminho: str, raiz: Path) -> str:
    try:
        # `as_posix` e nao `str`: no Windows o separador e' `\`, e a base
        # gravada por uma maquina nao bateria com a de outra.
        return Path(caminho).resolve().relative_to(Path(raiz).resolve()).as_posix()
    except (ValueError, OSError):
        return caminho.lstrip("./").replace("\\", "/")


# ` FAIL  arquivo.spec.ts > suíte > nome do teste`
RE_VITEST = re.compile(r"^\s*FAIL\s+(?P<id>\S.*?)\s*$")
# `FAIL apps/api/src/x.spec.ts` e, abaixo, `  ● suíte › nome`
RE_JEST_ARQUIVO = re.compile(r"^(?:FAIL|PASS)\s+(?P<arquivo>\S+)")
RE_JEST_TESTE = re.compile(r"^\s*●\s+(?P<nome>\S.*?)\s*$")
# `  185:5  warning  mensagem longa  nome/da-regra`
RE_ESLINT_ACHADO = re.compile(
    r"^\s+\d+:\d+\s+(?P<nivel>error|warning)\s+(?P<msg>.+?)(?:\s{2,}(?P<regra>\S+))?\s*$")


def parse_vitest(linhas: list[str], raiz: Path) -> dict[str, int]:
    """Cada linha `FAIL` do bloco de falhas é um teste, uma vez."""
    achados: dict[str, int] = {}
    for linha in linhas:
        m = RE_VITEST.match(linha)
        if not m:
            continue
        ident = re.sub(r"\s+", " ", m.group("id")).strip()
        # ` FAIL  arquivo.spec.ts [ arquivo.spec.ts ]` é erro de coleta: o
        # arquivo inteiro não subiu. Vale como falha, com a duplicata fora.
        ident = re.sub(r"\s*\[\s*(.+?)\s*\]$", "", ident)
        achados[ident] = 1
    return achados


def parse_jest(linhas: list[str], raiz: Path) -> dict[str, int]:
    """`●` traz o nome do teste; o arquivo vem do último `FAIL` acima dele."""
    achados: dict[str, int] = {}
    arquivo = "?"
    for linha in linhas:
        m = RE_JEST_ARQUIVO.match(linha)
        if m:
            arquivo = _relativo(m.group("arquivo"), raiz)
            continue
        m = RE_JEST_TESTE.match(linha)
        if not m:
            continue
        nome = m.group("nome").replace("›", ">")
        # `● Console` é ruído de log, não falha.
        if nome.strip().lower().startswith("console"):
            continue
        achados[f"{arquivo} > {re.sub(r'\s+', ' ', nome).strip()}"] = 1
    return achados


def parse_eslint(linhas: list[str], raiz: Path) -> dict[str, int]:
    """Conta por `arquivo :: regra`, porque a mesma regra reincide no arquivo."""
    achados: dict[str, int] = {}
    arquivo = "?"
    for linha in linhas:
        if linha.strip() and not linha[0].isspace() and not linha.lstrip().startswith("✖"):
            if "/" in linha or re.search(r"\.\w{2,4}$", linha.strip()):
                arquivo = _relativo(linha.strip(), raiz)
                continue
        m = RE_ESLINT_ACHADO.match(linha)
        if not m:
            continue
        regra = m.group("regra") or m.group("msg").strip()[:60]
        chave = f"{arquivo} :: {regra}"
        achados[chave] = achados.get(chave, 0) + 1
    return achados


def parse_lighthouse(linhas: list[str], raiz: Path) -> dict[str, int]:
    """Portao de tela: as auditorias BINARIAS que reprovaram, por caminho.

    A entrada e' o JSON de `lighthouse --output=json`. Ela chega como linhas
    porque `extrair` e' o mesmo para todo formato; juntar de volta custa nada e
    evita um segundo caminho de leitura so' para este.

    A identidade e' `caminho da URL :: id da auditoria` -- e o caminho entra
    **sem host e sem porta**, pela razao de sempre: a mesma tela em
    `localhost:8731` e em homologacao e' a mesma tela, e a catraca nao pode
    chamar de nova uma falha que so' mudou de ambiente.

    **So' `binary` com score 0 conta.** Os outros modos ficam fora, e cada um
    por um motivo diferente:

    `numeric` e' medida continua -- na captura, LCP saiu 767,18 ms. Catraca
    sobre medida oscila com a rede e a CPU de quem roda, e devolveria a entrega
    por ruido: a mesma familia do numero de linha na identidade.

    `metricSavings` e' o caso perigoso, porque **parece falha**. Na captura,
    `unsized-images` -- "imagens sem `width` e `height`", que e' defeito de
    verdade -- veio com score **0,5**. Score fracionario e' medida, nao
    veredicto, e o teste de fumaca prende exatamente esse caso.

    `informative`, `notApplicable` e `manual` nao afirmam nada sobre a pagina.

    O QUE ISTO NAO COBRE, e fica dito: **regressao de performance.** O score de
    performance e' dominado por rede e CPU de quem roda -- a pagina que a
    captura quebrou de proposito, sem `title`, sem `lang` e com imagem sem
    `alt`, tirou `performance = 1`. Piso por categoria seria portao que passa
    no Mac de quem escreveu e reprova no runner de CI.
    """
    try:
        dados = json.loads("\n".join(linhas))
    except json.JSONDecodeError as exc:
        raise CatracaError(
            f"a saida nao e' o JSON do lighthouse: {exc}. "
            "Gere com `lighthouse <url> --output=json`.") from exc
    if not isinstance(dados, dict) or "audits" not in dados:
        raise CatracaError(
            "JSON sem a chave `audits` -- isto nao parece saida do lighthouse.")

    bruta = dados.get("finalDisplayedUrl") or dados.get("finalUrl") or ""
    caminho = urllib.parse.urlparse(bruta).path or "/"
    achados: dict[str, int] = {}
    for ident, auditoria in (dados.get("audits") or {}).items():
        if not isinstance(auditoria, dict):
            continue
        if auditoria.get("scoreDisplayMode") != "binary":
            continue
        if auditoria.get("score") != 0:
            continue
        # Uma auditoria pode reprovar em N nos do DOM. O numero de nos muda com
        # o conteudo da pagina e nao e' o defeito -- o defeito e' a auditoria.
        achados[f"{caminho} :: {ident}"] = 1
    return achados


def parse_generico(linhas: list[str], raiz: Path, padrao: str) -> dict[str, int]:
    """Um regex com grupo `id`, para o portão cuja saída ninguém capturou ainda."""
    try:
        rx = re.compile(padrao)
    except re.error as exc:
        raise CatracaError(f"padrão inválido: {exc}") from exc
    if "id" not in (rx.groupindex or {}):
        raise CatracaError("o padrão precisa de um grupo nomeado `id`")
    achados: dict[str, int] = {}
    for linha in linhas:
        m = rx.search(linha)
        if m:
            chave = re.sub(r"\s+", " ", m.group("id")).strip()
            achados[chave] = achados.get(chave, 0) + 1
    return achados


FORMATOS = {"vitest": parse_vitest, "jest": parse_jest, "eslint": parse_eslint,
            "lighthouse": parse_lighthouse}

# `playwright` e `tsc` NÃO estão aqui de propósito. Os QUATRO acima foram
# escritos contra saída real, capturada rodando cada runner com uma falha de
# mentira — o do lighthouse saiu de `npx lighthouse@latest` 13.4.1 contra uma
# página sem `title`, sem `lang` e com imagem sem `alt`. Os outros dois eu saberia escrever de memória, e memória é
# procedência `leitura` — que é exatamente o que esta casa não aceita como prova.
# Até alguém capturar a saída deles, use `--padrao` e escreva o regex à vista da
# saída que você tem na mão.


def extrair(texto: str, formato: str, raiz: Path, padrao: str | None) -> dict[str, int]:
    linhas = texto.splitlines()
    if padrao:
        return parse_generico(linhas, raiz, padrao)
    if formato not in FORMATOS:
        raise CatracaError(
            f"formato desconhecido: {formato}. Conhecidos: "
            + ", ".join(sorted(FORMATOS)) + " — ou use --padrao")
    return FORMATOS[formato](linhas, raiz)


# --------------------------------------------------------------------------
# o arquivo da catraca
# --------------------------------------------------------------------------
def ler_base(caminho: Path) -> dict:
    if not caminho.is_file():
        return {"versao": VERSION, "portoes": {}}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatracaError(f"catraca ilegível em {caminho}: {exc}") from exc
    dados.setdefault("portoes", {})
    return dados


def gravar_base(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")


def commit_atual(raiz: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def entrada(args) -> str:
    if args.saida_do_portao == "-":
        return sys.stdin.read()
    p = Path(args.saida_do_portao)
    if not p.is_file():
        raise CatracaError(f"saída do portão não encontrada: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def _contexto(args):
    raiz = Path(args.raiz).resolve()
    return raiz, extrair(entrada(args), args.formato, raiz, args.padrao)


# --------------------------------------------------------------------------
# deixar rastro no estado da atividade
# --------------------------------------------------------------------------
# Sem isto a conferência é uma frase na skill, e frase na skill não acontece:
# "entrar com ator sem a permissão" viveu meses na frente de execução sem nunca
# ter acontecido, porque ninguém registrava e portanto ninguém sabia.
#
# `--registrar <id>` grava o veredicto na atividade, e o `concluir` do
# flow_state recusa encerrar com conferência exigida em aberto.
def registrar(id_atividade: str, ferramenta: str, veredicto: str,
              detalhe: str = "") -> None:
    if not id_atividade:
        return
    flow_state = Path(__file__).resolve().parent.parent / "flow-state" / "flow_state.py"
    if not flow_state.is_file():
        print(f"  [aviso] não achei {flow_state}; nada foi registrado")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(flow_state), "conferencia", id_atividade,
             "--ferramenta", ferramenta, "--veredicto", veredicto,
             "--detalhe", detalhe[:200]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [aviso] não consegui registrar: {exc}")
        return
    if r.returncode != 0:
        print(f"  [aviso] registro recusado: {(r.stderr or r.stdout).strip()[:160]}")
        return
    # Registro silencioso é a mesma doença que esta tabela existe para curar:
    # quem roda precisa VER que ficou escrito.
    print(f"  registrado em {id_atividade}: {ferramenta} → {veredicto}")


# --------------------------------------------------------------------------
# comandos
# --------------------------------------------------------------------------
def cmd_gravar(args) -> int:
    raiz, agora = _contexto(args)
    base = Path(args.base)
    dados = ler_base(base)
    ja = dados["portoes"].get(args.portao)

    if ja and not args.admitir:
        print(f"[ALTO] o portão `{args.portao}` já tem linha de base "
              f"({len(ja.get('falhas', {}))} falhas, do commit {ja.get('base', '?')})")
        print()
        print("  `gravar` de novo apagaria o passivo conhecido e o substituiria")
        print("  pelo de hoje — é o gesto que faz uma regressão virar linha de")
        print("  base em silêncio, e é o único jeito de a catraca afrouxar.")
        print()
        print("  Para conferir contra a base:   ratchet.py conferir ...")
        print("  Para encolher a base:          ratchet.py apertar ...")
        print("  Para admitir falha nova nela:  --admitir \"<por quê>\"")
        return 1

    dados["versao"] = VERSION
    dados["portoes"][args.portao] = {
        "formato": args.padrao and "padrão" or args.formato,
        "padrao": args.padrao or None,
        "base": commit_atual(raiz),
        "comando": args.comando or None,
        "admitido": args.admitir or None,
        "falhas": agora,
    }
    gravar_base(base, dados)
    total = sum(agora.values())
    print(f"Linha de base do portão `{args.portao}`: {len(agora)} falha(s) "
          f"conhecida(s)" + (f", {total} ocorrências" if total != len(agora) else ""))
    for k in sorted(agora):
        print(f"    {k}" + (f"  ×{agora[k]}" if agora[k] > 1 else ""))
    print()
    if args.admitir:
        print(f"Admitido: {args.admitir}")
    print("Passivo conhecido não reprova. Falha nova reprova.")
    return 0


def _comparar(base_falhas: dict[str, int], agora: dict[str, int]):
    novos, a_mais, conhecidos, consertados = [], [], [], []
    for k, n in sorted(agora.items()):
        antes = base_falhas.get(k, 0)
        if antes == 0:
            novos.append(k)
        elif n > antes:
            a_mais.append(f"{k}  {antes} → {n}")
        else:
            conhecidos.append(k if n == antes else f"{k}  {antes} → {n}")
    for k, antes in sorted(base_falhas.items()):
        if agora.get(k, 0) < antes:
            consertados.append(k if k not in agora else f"{k}  {antes} → {agora[k]}")
    return novos, a_mais, conhecidos, consertados


def cmd_conferir(args) -> int:
    raiz, agora = _contexto(args)
    dados = ler_base(Path(args.base))
    porta = dados["portoes"].get(args.portao)
    if porta is None:
        print(f"[ALTO] o portão `{args.portao}` não tem linha de base")
        print()
        print("  Sem base, toda falha é nova e toda falha antiga reprova a")
        print("  entrega de quem não a causou. Grave a base no commit em que a")
        print("  branch nasceu:")
        print(f"    ratchet.py gravar --base {args.base} --portao {args.portao} ...")
        registrar(args.registrar, f"catraca:{args.portao}", "exigida",
                  "portão sem linha de base — não dá para saber de quem é o vermelho")
        return 2

    base_falhas = porta.get("falhas", {})
    novos, a_mais, conhecidos, consertados = _comparar(base_falhas, agora)

    if novos:
        print(f"[ALTO] falha nova ({len(novos)})")
        print("  não estava na linha de base — esta entrega a introduziu")
        for k in novos:
            print(f"    {k}")
        print()
    if a_mais:
        print(f"[ALTO] falha conhecida que aumentou ({len(a_mais)})")
        print("  a mesma regra no mesmo arquivo, mais vezes que antes")
        for k in a_mais:
            print(f"    {k}")
        print()
    if consertados:
        print(f"[APERTA] falha da base que parou de falhar ({len(consertados)})")
        print("  a catraca só aperta: tire-as da base agora, senão elas podem")
        print("  voltar depois sem ninguém notar")
        for k in consertados:
            print(f"    {k}")
        print(f"    → ratchet.py apertar --base {args.base} --portao {args.portao} ...")
        print()

    print(f"Portão `{args.portao}` contra a base de {porta.get('base', '?')}: "
          f"{len(novos) + len(a_mais)} nova(s), {len(conhecidos)} conhecida(s), "
          f"{len(consertados)} consertada(s)")
    if porta.get("admitido"):
        print(f"  base admitida com motivo: {porta['admitido']}")
    print()
    print("O que isto NÃO prova: que a falha conhecida é aceitável. Ela não")
    print("reprova esta entrega porque não é dela — continua sendo de alguém.")

    reprova = bool(novos or a_mais)
    registrar(
        args.registrar, f"catraca:{args.portao}",
        "falhou" if reprova else "ok",
        f"{len(novos) + len(a_mais)} nova(s), {len(conhecidos)} conhecida(s), "
        f"{len(consertados)} consertada(s)")
    return 1 if reprova else 0


def cmd_apertar(args) -> int:
    raiz, agora = _contexto(args)
    base = Path(args.base)
    dados = ler_base(base)
    porta = dados["portoes"].get(args.portao)
    if porta is None:
        raise CatracaError(f"o portão `{args.portao}` não tem linha de base")

    antes = porta.get("falhas", {})
    # SÓ ENCOLHE. Uma falha que hoje falha e não estava na base é regressão, e
    # `apertar` não pode ser o caminho por onde ela entra — senão a catraca vira
    # um carimbo que registra o que quer que esteja quebrado hoje.
    novo = {k: min(n, agora[k]) for k, n in antes.items() if agora.get(k, 0) > 0}
    saiu = [k for k in antes if k not in novo]
    reduziu = [f"{k}  {antes[k]} → {novo[k]}" for k in novo if novo[k] < antes[k]]
    ignorados = [k for k in agora if k not in antes]

    porta["falhas"] = novo
    porta["base"] = commit_atual(raiz)
    gravar_base(base, dados)

    print(f"Catraca do portão `{args.portao}`: {len(antes)} → {len(novo)} falha(s)")
    for k in saiu:
        print(f"    saiu   {k}")
    for k in reduziu:
        print(f"    menos  {k}")
    if ignorados:
        print()
        print(f"[ALTO] {len(ignorados)} falha(s) que falham hoje e NÃO entraram na base")
        print("  a catraca só encolhe. Estas são regressão, e o lugar delas é o")
        print("  conserto — ou `gravar --admitir \"<por quê>\"`, que é decisão de gente")
        for k in ignorados:
            print(f"    {k}")
    print()
    return 1 if ignorados else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    def comum(c):
        c.add_argument("saida_do_portao", help="arquivo com a saída do portão, ou `-`")
        c.add_argument("--base", required=True, help="arquivo JSON da catraca")
        c.add_argument("--portao", required=True, help="nome do portão: lint, test-api…")
        c.add_argument("--formato", default="", help=", ".join(sorted(FORMATOS)))
        c.add_argument("--padrao", default="", help="regex com grupo `id`, no lugar do formato")
        c.add_argument("--raiz", default=".", help="raiz do repositório")
        c.add_argument("--registrar", default="",
                       help="id da atividade: grava o veredicto no estado")

    g = sub.add_parser("gravar", help="registra a linha de base do portão")
    comum(g)
    g.add_argument("--comando", default="", help="o comando que produziu a saída")
    g.add_argument("--admitir", default="", help="motivo para admitir falha nova na base")
    g.set_defaults(fn=cmd_gravar)

    c = sub.add_parser("conferir", help="o que é novo, o que já falhava")
    comum(c)
    c.set_defaults(fn=cmd_conferir)

    a = sub.add_parser("apertar", help="tira da base o que parou de falhar")
    comum(a)
    a.set_defaults(fn=cmd_apertar)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except CatracaError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


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
    sys.exit(main())
