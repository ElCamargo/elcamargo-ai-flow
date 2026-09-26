#!/usr/bin/env python3
"""Confere o que uma especificação afirma sobre o repositório e sobre si mesma.

Uma verificação que a auditoria por subagente fazia em uma hora e que aqui
custa segundos:

    codigo   toda citação `arquivo.ts:NN` existe, a linha existe, e o trecho
             entre aspas ao lado dela aparece mesmo lá

Ela não julga conteúdo. Confere que a spec não afirma sobre o código coisa que o
código não diz — que foi de onde saiu boa parte dos achados de uma revisão real:
citação com o intervalo errado, trecho lembrado de memória, arquivo que mudou de
lugar.

Havia uma segunda verificação planejada, e ela foi derrubada. O porquê está
escrito no corpo deste arquivo, para ninguém tentar os mesmos dois caminhos.

Uso:
    citations.py codigo spec.md [--raiz .] [--estrito]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path


class ConferenciaError(Exception):
    pass


# --------------------------------------------------------------------------
# comum
# --------------------------------------------------------------------------
def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    """Colapsa espaço e tira acento, para comparar citação com fonte."""
    return re.sub(r"\s+", " ", sem_acento(texto)).strip().lower()


# Extensões que valem como citação de código. Sem esta lista, `IAM-008:42`
# e `CAM-001:168` — que são citação de documento por seção — entrariam como
# arquivo inexistente, e a ferramenta acusaria dezenas de falsos.
EXTENSOES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".sql",
             ".json", ".yaml", ".yml", ".md", ".css", ".sh")

# `caminho/arquivo.ext:12` ou `caminho/arquivo.ext:12-34`, dentro ou fora de
# crase. O caminho precisa ter extensão conhecida — ver acima.
RE_CITACAO = re.compile(
    r"(?P<caminho>[A-Za-z0-9_./@-]+(?:" + "|".join(re.escape(e) for e in EXTENSOES) + r"))"
    r":(?P<inicio>\d+)(?:\s*[-–—]\s*(?P<fim>\d+))?"
)

# Trecho entre aspas curvas ou retas, em itálico markdown ou não.
RE_ASPAS = re.compile(r"[\"“](?P<texto>[^\"”\n]{12,400})[\"”]")

# Distância máxima entre a citação e a aspa que ela introduz. Ver o
# comentário em cmd_codigo: a folga larga produz falso positivo.
JANELA_DO_TRECHO = 60


_INDICE: dict[str, list[Path]] = {}


def indexar(raiz: Path) -> dict[str, list[Path]]:
    """Mapa nome-do-arquivo -> caminhos, a partir do que o git rastreia.

    `rglob` não serve aqui, e o motivo custou uma rodada: um repositório com
    worktrees tem **cópias inteiras de si mesmo** dentro de si, e todo nome
    solto resolve para meia dúzia de caminhos. Numa spec real isso produziu 24
    falsos "nome que não resolve" — para arquivos que existem, são únicos, e a
    ferramenta simplesmente não sabia qual era o de verdade.

    `git ls-files` devolve só o que está rastreado na árvore de trabalho atual:
    sem worktree, sem `node_modules`, sem lixo local. E é uma chamada, não uma
    varredura de disco.
    """
    if not _INDICE:
        import subprocess
        r = subprocess.run(["git", "-C", str(raiz), "ls-files"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise ConferenciaError(
                f"`git ls-files` falhou em {raiz}. A conferência de citação "
                "precisa saber quais arquivos o repositório tem.")
        for rel in r.stdout.splitlines():
            _INDICE.setdefault(Path(rel).name, []).append(raiz / rel)
    return _INDICE


def achar_arquivo(raiz: Path, caminho: str) -> Path | None:
    """Resolve o caminho citado. Aceita caminho de repositório e nome solto."""
    direto = raiz / caminho
    if direto.is_file():
        return direto
    if "/" in caminho:
        return None
    # Nome solto (`dialog.tsx:19`): só vale se resolver para UM arquivo.
    achados = indexar(raiz).get(caminho, [])
    return achados[0] if len(achados) == 1 else None


def cmd_codigo(args) -> int:
    doc = Path(args.documento).expanduser()
    raiz = Path(args.raiz).expanduser().resolve()
    if not doc.is_file():
        raise ConferenciaError(f"não achei {doc}")
    texto = doc.read_text(encoding="utf-8")
    linhas = texto.splitlines()

    quebradas: list[str] = []
    fora: list[str] = []
    ambiguas: list[str] = []
    citacoes = 0
    conferidas = 0

    for n, linha in enumerate(linhas, 1):
        for m in RE_CITACAO.finditer(linha):
            caminho = m.group("caminho")
            # Um `.md` do próprio conjunto de specs é citação de documento, não
            # de código: conferir a linha dele acusaria toda spec que evolui.
            if caminho.endswith(".md") and not args.estrito:
                continue
            citacoes += 1
            alvo = achar_arquivo(raiz, caminho)
            if alvo is None:
                if "/" in caminho:
                    quebradas.append(f"§{n}  {caminho}:{m.group('inicio')}"
                                     f"  — arquivo não existe")
                else:
                    ambiguas.append(f"§{n}  {caminho}"
                                    f"  — nome solto que não resolve para um arquivo só")
                continue
            total = len(alvo.read_text(encoding="utf-8", errors="replace").splitlines())
            inicio = int(m.group("inicio"))
            fim = int(m.group("fim") or inicio)
            if inicio < 1 or fim > total:
                quebradas.append(
                    f"§{n}  {caminho}:{m.group('inicio')}"
                    f"{'-' + m.group('fim') if m.group('fim') else ''}"
                    f"  — o arquivo tem {total} linhas")
                continue
            conferidas += 1

            # A citação afirma um trecho? Confira que ele está mesmo lá.
            #
            # A janela é curta de propósito. Com 500 caracteres, duas coisas
            # viravam falso positivo numa spec real, e as duas apareceram na
            # primeira execução: aspas que são ênfase do autor e não citação da
            # fonte, e aspas que pertencem a OUTRA citação mais adiante na
            # mesma célula de tabela. O padrão da casa é citação colada —
            # `arquivo.ts:16-21` declara "…" —, e é só isso que a janela pega.
            resto = linha[m.end():m.end() + JANELA_DO_TRECHO]
            # Outra citação no meio: a aspa é dela, não desta.
            proxima = RE_CITACAO.search(resto)
            if proxima:
                resto = resto[:proxima.start()]
            # Barra de tabela no meio: mudou de célula, mudou de assunto.
            resto = resto.split("|")[0]
            aspas = RE_ASPAS.search(resto)
            if not aspas:
                continue
            trecho = normalizar(aspas.group("texto"))
            if len(trecho) < 12:
                continue
            janela = "\n".join(
                alvo.read_text(encoding="utf-8", errors="replace").splitlines()
                [max(0, inicio - 4):fim + 3])
            if trecho not in normalizar(janela):
                fora.append(f"§{n}  {caminho}:{inicio}"
                            f"  — o trecho citado não aparece nessas linhas\n"
                            f"        \"{aspas.group('texto')[:110]}…\"")

    print(f"Documento  {doc}")
    print(f"Raiz       {raiz}")
    print(f"Citações   {citacoes} de código, {conferidas} com arquivo e linha válidos")
    print()

    achados = 0
    if quebradas:
        achados += 1
        print(f"[ALTO] citação que não resolve ({len(quebradas)})")
        print("  o arquivo não existe, ou a linha está fora dele — quem seguir a")
        print("  citação não acha o que a spec afirma")
        for q in quebradas:
            print(f"    {q}")
        print()
    if fora:
        achados += 1
        print(f"[ALTO] trecho citado que não está na linha citada ({len(fora)})")
        print("  o arquivo existe e a linha existe, mas o texto entre aspas não")
        print("  aparece ali — ou a linha mudou, ou a citação foi escrita de memória")
        for f in fora:
            print(f"    {f}")
        print()
    if ambiguas:
        print(f"[MEDIO] nome solto que não resolve ({len(ambiguas)})")
        print("  pode ser arquivo que não existe, ou nome repetido no repositório")
        for a in ambiguas:
            print(f"    {a}")
        print()

    if not achados and not ambiguas:
        print("Nenhuma citação de código quebrada.")
        print()
    print("O que isto NÃO prova: que a conclusão tirada da citação está certa.")
    print("Linha certa com leitura errada continua sendo trabalho seu.")
    return 1 if achados else 0


# --------------------------------------------------------------------------
# A verificação que NÃO existe aqui, e por quê
# --------------------------------------------------------------------------
# Faltou de propósito uma segunda conferência: "o número declarado bate com a
# realidade?". Ela nasceu de um defeito real — uma spec dizia "15 baselines" em
# negrito e "21" três frases abaixo, na mesma célula —, e foi tentada de dois
# jeitos. Os dois inundaram, e a ferramenta foi derrubada em vez de afinada.
#
#   1. O MESMO SUBSTANTIVO COM DOIS NÚMEROS no documento inteiro.
#      Numa spec real: 29 conflitos, todos legítimos. Em português se conta
#      tudo, e `itens` sozinho aparecia com nove números diferentes — 2 campos,
#      5 campos, 120 itens, 233 itens, cada um falando de outra coisa.
#
#   2. A CONTAGEM DECLARADA CONTRA A LISTA LOGO ABAIXO.
#      Pior: 34 achados em 38 declarações. A causa é estrutural — uma spec
#      densa é quase toda tabela, e todo número dentro de uma célula tem "uma
#      tabela logo abaixo", que é a continuação da própria tabela em que ele
#      está.
#
# O que faria essa verificação funcionar é entender a que lista o número se
# refere, e isso é leitura, não regra. Fica como trabalho do revisor.
#
# Está escrito aqui para ninguém tentar os dois mesmos caminhos de novo achando
# que são óbvios. Eles são — e não funcionam.


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("codigo", help="citações de código que não resolvem")
    c.add_argument("documento")
    c.add_argument("--raiz", default=".", help="raiz do repositório")
    c.add_argument("--estrito", action="store_true",
                   help="confere também citação de linha em .md")
    c.set_defaults(fn=cmd_codigo)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ConferenciaError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
