#!/usr/bin/env python3
"""Duas lentes que faltavam: o teste é honesto, e a prova é de verdade?

Gate verde não é requisito provado. Numa entrega real, onze testes verdes
provavam nada — descobriu-se por mutação, não por leitura. E um portão fechou
verde anunciando `145 passaram, 0 falharam` com **152 ignorados** na mesma linha.

    testes    varre os arquivos de teste: `.only` esquecido, pulo estático,
              asserção trivialmente verdadeira, teste sem asserção nenhuma, e
              o arquivo que simula o próprio módulo que testa
    saida     lê o rodapé de uma rodada e diz quantos NÃO rodaram

TUDO AQUI É PROCEDÊNCIA `estrutural`. Padrão, contagem e ausência dizem **onde
olhar**, não o que reprovar — ver `references/severity.md`. Um achado desta
ferramenta só reprova depois de promovido por leitura ou por execução; sozinho,
ele viaja como achado aberto.

Uso:
    honesty.py testes [arquivos...] [--raiz .]
    honesty.py saida --formato vitest|jest saida.txt
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


class LenteError(Exception):
    pass


# --------------------------------------------------------------------------
# O que separa pulo honesto de pulo escondido
# --------------------------------------------------------------------------
# `test.skip(Boolean(condicao), motivo)` é guarda declarada: o teste existe,
# roda quando dá, e diz por que não deu. `it.skip('nome', () => …)` é outra
# coisa: nunca roda, e o relatório de cobertura conta o arquivo como coberto.
#
# Num repositório real a diferença é 13 ocorrências do primeiro e zero do
# segundo. Uma lente que não distinguisse os dois acusaria treze falsos logo na
# primeira execução — e uma lente que erra na primeira execução ninguém roda de
# novo. O que separa: o primeiro argumento é literal de texto, ou é expressão?
RE_PULO = re.compile(
    r"\b(?:it|test|describe)\.(?P<tipo>skip|todo|failing)\s*\(\s*(?P<arg>.?)")
RE_PULO_ANTIGO = re.compile(r"(?<![\w.])(?P<nome>xit|xdescribe|xtest)\s*\(")
RE_ONLY = re.compile(r"\b(?:it|test|describe)\.only\s*\(")

# Declaração de um caso de teste, para fatiar o arquivo em blocos.
RE_CASO = re.compile(
    r"^\s*(?:it|test)\s*(?:\.\s*(?:each|concurrent|sequential)\s*(?:\(|`)[^\n]*)?"
    r"\s*\(\s*(?P<nome>[`'\"])(?P<titulo>[^`'\"]{0,120})")

# O PREFIXO, e não a palavra exata. Na primeira calibração contra um
# repositório real esta lente achou três casos "sem asserção" — e os TRÊS eram
# falsos: os testes afirmam através de um helper chamado `expectRefusal`, com as
# asserções dentro dele. Cem por cento de falso positivo na primeira execução, e
# uma lente que erra na primeira execução ninguém roda de novo.
#
# `check` ficou de fora do prefixo de propósito: `checkout`, `checkboxes` e
# `checkMigrations` são chamadas comuns e não afirmam nada.
RE_ASSERCAO = re.compile(
    r"\b(?:expect|assert|should|verif)\w*\s*\(|\bexpect\s*\.\s*(?:assertions|hasAssertions)")
# TRÊS exclusões, e as três saíram de calibrar contra um repositório real. A
# lente errou três vezes seguidas antes de acertar — 3 achados, todos falsos;
# depois 35, todos falsos; depois 5, todos falsos:
#
#   `toHaveBeenCalledWith` — afirmar COM QUE argumento o colaborador foi chamado
#   é asserção de comportamento.
#
#   `.not.toHaveBeenCalled()` — é a única forma de provar "não faz nada".
#   "Ignora o evento sem occurredAt, sem tocar no banco" se prova exatamente
#   assim, e de nenhum outro jeito. (35 falsos)
#
#   `toHaveBeenCalledTimes(n)` — quando o comportamento É a contagem, ela é a
#   asserção: "recria o canal fechado" quer dizer `createConfirmChannel` duas
#   vezes; "pede a próxima página" quer dizer o callback uma vez. (5 falsos)
#
# O que sobra é estreito de propósito: `expect(espiao).toHaveBeenCalled()`, sem
# contagem e sem argumento, como única afirmação do caso.
RE_SO_CHAMADA = re.compile(
    r"\.\s*(?:(?P<neg>not)\s*\.\s*)?toHaveBeenCalled\s*\(\s*\)")

# `expect(true).toBe(true)`, `expect(1).toBe(1)`, `expect('a').toEqual('a')`.
RE_TRIVIAL = re.compile(
    r"expect\s*\(\s*(?P<a>true|false|null|undefined|-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\")\s*\)"
    r"\s*\.\s*(?:to(?:Be|Equal|StrictEqual)|toBe(?:Truthy|Falsy))\s*\(\s*(?P<b>[^)]*?)\s*\)")

RE_AUTO_MOCK = re.compile(r"\b(?:vi|jest)\s*\.\s*mock\s*\(\s*['\"](?P<alvo>[^'\"]+)['\"]")

EXT_TESTE = (".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx",
             ".spec.js", ".test.js", ".spec.mjs", ".test.mjs")


def arquivos_de_teste(raiz: Path, dados: list[str]) -> list[Path]:
    if dados:
        return [Path(d) for d in dados]
    try:
        r = subprocess.run(["git", "-C", str(raiz), "ls-files"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0:
            raise LenteError("git ls-files falhou; passe os arquivos na linha de comando")
    except (OSError, subprocess.SubprocessError) as exc:
        raise LenteError(f"git indisponível: {exc}") from exc
    return [raiz / linha for linha in r.stdout.splitlines()
            if linha.endswith(EXT_TESTE)]


def blocos(texto: str):
    """Cada caso de teste e o texto até o próximo. Grosseiro de propósito.

    Um parser de verdade custaria uma dependência, e o pacote roda com zero
    instalação. O corte é aproximado: uma função auxiliar declarada entre dois
    casos entra no bloco do primeiro. Isso produz falso NEGATIVO — o bloco parece
    ter asserção que é de outro —, e falso negativo é o erro certo para uma
    lente que já é `estrutural`.
    """
    linhas = texto.splitlines()
    marcas = [(n, m.group("titulo").strip())
              for n, linha in enumerate(linhas)
              if (m := RE_CASO.match(linha))]
    for i, (n, titulo) in enumerate(marcas):
        fim = marcas[i + 1][0] if i + 1 < len(marcas) else len(linhas)
        yield n + 1, titulo, "\n".join(linhas[n:fim])


def varrer(caminho: Path, raiz: Path) -> dict[str, list[str]]:
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise LenteError(f"não consegui ler {caminho}: {exc}") from exc
    try:
        rel = str(caminho.resolve().relative_to(raiz))
    except (ValueError, OSError):
        rel = str(caminho)

    achados: dict[str, list[str]] = {k: [] for k in
                                     ("only", "pulo_estatico", "pulo_condicional",
                                      "trivial", "sem_assercao", "so_chamada",
                                      "auto_mock")}

    for n, linha in enumerate(texto.splitlines(), 1):
        if RE_ONLY.search(linha):
            achados["only"].append(f"{rel}:{n}")
        for m in RE_PULO.finditer(linha):
            estatico = m.group("arg") in ("'", '"', "`") or m.group("tipo") == "todo"
            chave = "pulo_estatico" if estatico else "pulo_condicional"
            achados[chave].append(f"{rel}:{n}  .{m.group('tipo')}")
        for m in RE_PULO_ANTIGO.finditer(linha):
            achados["pulo_estatico"].append(f"{rel}:{n}  {m.group('nome')}")
        for m in RE_TRIVIAL.finditer(linha):
            a, b = m.group("a"), m.group("b").strip()
            if not b or a == b or (b in ("", "true") and a == "true"):
                achados["trivial"].append(f"{rel}:{n}  {m.group(0)[:60]}")

    # O arquivo simula o módulo que ele testa? `faq.service.spec.ts` que faz
    # `vi.mock('./faq.service')` prova o dublê, não o serviço.
    alvo = caminho.name
    for sufixo in EXT_TESTE:
        if alvo.endswith(sufixo):
            alvo = alvo[: -len(sufixo)]
            break
    for m in RE_AUTO_MOCK.finditer(texto):
        simulado = Path(m.group("alvo")).name
        if simulado and simulado.split(".")[0] == alvo.split(".")[0]:
            achados["auto_mock"].append(f"{rel}  simula `{m.group('alvo')}`")

    for n, titulo, bloco in blocos(texto):
        assercoes = len(RE_ASSERCAO.findall(bloco))
        so_fiacao = sum(1 for m in RE_SO_CHAMADA.finditer(bloco) if not m.group("neg"))
        if not assercoes:
            achados["sem_assercao"].append(f"{rel}:{n}  {titulo[:60]}")
        elif so_fiacao >= assercoes:
            # TODAS as asserções do bloco são de fiação. Uma só, ao lado de
            # outras, é complemento legítimo e não vira achado.
            achados["so_chamada"].append(f"{rel}:{n}  {titulo[:60]}")
    return achados


def cmd_testes(args) -> int:
    raiz = Path(args.raiz).resolve()
    alvos = arquivos_de_teste(raiz, args.arquivos)
    if not alvos:
        print("Nenhum arquivo de teste encontrado.")
        return 0

    total: dict[str, list[str]] = {}
    for caminho in alvos:
        for chave, itens in varrer(caminho, raiz).items():
            total.setdefault(chave, []).extend(itens)

    graves = 0

    def bloco(chave, nivel, rotulo, explicacao, teto=12):
        nonlocal graves
        itens = total.get(chave) or []
        if not itens:
            return
        if nivel == "ALTO":
            graves += 1
        print(f"[{nivel}] {rotulo} ({len(itens)})")
        for linha in explicacao:
            print(f"  {linha}")
        for i in itens[:teto]:
            print(f"    {i}")
        if len(itens) > teto:
            print(f"    … e mais {len(itens) - teto}")
        print()

    bloco("only", "ALTO", "`.only` commitado",
          ["um `.only` faz todo o resto do arquivo não rodar, e a suíte",
           "continua verde. É o jeito mais barato de desligar testes sem que",
           "ninguém veja"])
    bloco("auto_mock", "ALTO", "o teste simula o próprio módulo que testa",
          ["o que passa é o dublê. Trocar a implementação por `return null` não",
           "quebraria este teste"])
    bloco("trivial", "ALTO", "asserção trivialmente verdadeira",
          ["`expect(true).toBe(true)` passa com a implementação removida"])
    bloco("pulo_estatico", "MEDIO", "pulo estático: o teste nunca roda",
          ["`it.skip('nome', …)` e `it.todo` não rodam em ambiente nenhum, e a",
           "suíte fecha verde. Se é intencional, o motivo tem que estar escrito",
           "no artefato — não só no código"])
    bloco("sem_assercao", "MEDIO", "caso de teste sem asserção nenhuma",
          ["prova que o caminho não lança. Pode ser o que se queria; declare"])
    bloco("so_chamada", "MEDIO", "o caso só afirma que algo foi chamado",
          ["`toHaveBeenCalled` prova a fiação, não o comportamento. O valor de",
           "retorno e o efeito continuam sem prova"])

    condicionais = total.get("pulo_condicional") or []
    if condicionais:
        print(f"Pulos condicionais com motivo: {len(condicionais)} — não são achado.")
        print("  `test.skip(condição, motivo)` é guarda declarada: o teste existe,")
        print("  roda quando dá, e diz por que não deu.")
        print()

    if not graves and not any(total.get(k) for k in ("pulo_estatico", "sem_assercao",
                                                     "so_chamada")):
        print(f"{len(alvos)} arquivo(s) de teste, nada a apontar.")
        print()

    print("Procedência de tudo acima: `estrutural`. Padrão e ausência dizem onde")
    print("olhar. Promova indo ler ou indo rodar — a mutação é o teste de verdade:")
    print("quebre a implementação de propósito e veja se algum teste reprova.")
    return 1 if graves else 0


# --------------------------------------------------------------------------
# o rodapé da rodada
# --------------------------------------------------------------------------
# Capturados de `npx vitest run` e `npx jest` neste projeto, com um `.skip` e um
# `.todo` de mentira. Os dois fecharam VERDE — "Test Files 1 passed",
# "Test Suites: 1 passed" — com dois de três casos sem rodar.
RE_VITEST_RODAPE = re.compile(r"^\s*Tests\s+(?P<corpo>.+?)\s*\((?P<total>\d+)\)\s*$")
RE_JEST_RODAPE = re.compile(r"^\s*Tests:\s+(?P<corpo>.+?)\s*$")
RE_PARTE = re.compile(r"(?P<n>\d+)\s+(?P<rotulo>[a-zA-Z]+)")


def ler_rodape(texto: str, formato: str) -> dict[str, int] | None:
    rx = RE_VITEST_RODAPE if formato == "vitest" else RE_JEST_RODAPE
    achado = None
    for linha in texto.splitlines():
        m = rx.match(linha)
        if m:
            achado = m
    if achado is None:
        return None
    partes = {m.group("rotulo").lower(): int(m.group("n"))
              for m in RE_PARTE.finditer(achado.group("corpo"))}
    if formato == "vitest":
        partes["total"] = int(achado.group("total"))
    return partes


def cmd_saida(args) -> int:
    if args.formato not in ("vitest", "jest"):
        raise LenteError("formato precisa ser `vitest` ou `jest` — os dois cujo "
                         "rodapé foi capturado de saída real")
    p = Path(args.saida_da_rodada)
    texto = sys.stdin.read() if args.saida_da_rodada == "-" else (
        p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None)
    if texto is None:
        raise LenteError(f"saída não encontrada: {p}")

    partes = ler_rodape(texto, args.formato)
    if partes is None:
        print("[MEDIO] não achei o rodapé de contagem nesta saída")
        print("  sem ele não dá para saber quantos rodaram. Confira se a saída")
        print("  foi truncada, ou se o repórter do projeto é outro")
        return 0

    total = partes.get("total", 0)
    passaram = partes.get("passed", 0)
    falharam = partes.get("failed", 0)
    nao_rodaram = sum(partes.get(k, 0) for k in ("skipped", "todo", "pending"))

    print(f"{total} caso(s): {passaram} passaram, {falharam} falharam, "
          f"{nao_rodaram} não rodaram")
    print()
    if nao_rodaram:
        fatia = 100 * nao_rodaram / total if total else 0
        print(f"[MEDIO] {nao_rodaram} de {total} não rodaram ({fatia:.0f}%)")
        print("  a rodada fecha verde do mesmo jeito — 'passaram, 0 falharam' é")
        print("  verdade e não é a história inteira. Numa entrega real o portão")
        print("  visual anunciou 145 passaram e 0 falharam, com 152 ignorados")
        print("  na mesma linha, e a decisão foi tomada em cima do verde")
        print()
        print("  Leve o número ao portão humano. Ele não reprova sozinho —")
        print("  procedência `estrutural` —, mas quem decide tem direito a ele")
        print()
    print("O que isto NÃO prova: que os que rodaram provam alguma coisa. Para")
    print("isso, quebre a implementação de propósito e veja se algum reprova.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    t = sub.add_parser("testes", help="varre os arquivos de teste")
    t.add_argument("arquivos", nargs="*", help="vazio = todo teste rastreado pelo git")
    t.add_argument("--raiz", default=".", help="raiz do repositório")
    t.set_defaults(fn=cmd_testes)

    s = sub.add_parser("saida", help="quantos casos não rodaram")
    s.add_argument("saida_da_rodada", help="arquivo com a saída, ou `-`")
    s.add_argument("--formato", required=True, help="vitest | jest")
    s.set_defaults(fn=cmd_saida)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except LenteError as exc:
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
