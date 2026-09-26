#!/usr/bin/env python3
"""Turn a Markdown report into the PDF the human boundary expects.

Markdown is the canonical format across the whole flow: every skill writes it,
every other skill reads it. Only at the boundary with a person — the report that
goes back to the business analyst, the attachment on the card — does it become a
PDF. That is what this module does.

The structure is enforced, not suggested. `objetivo` and `conclusao` are
required front matter and land on the first page, before section 1, following
the pyramid: answer first, evidence after. A skill that cannot state its
conclusion in one sentence has not finished thinking.

Supported Markdown: headings, paragraphs, bullet and numbered lists, tables,
fenced code, horizontal rules, callouts (`> [!ok]`), and inline `**bold**`,
`*italic*`, `` `code` ``.
"""

from __future__ import annotations

import re
import unicodedata

from reportlab.lib.units import mm

import style
from style import CORES_CAIXA, Doc


class ReportError(RuntimeError):
    """Represent a report that must be fixed rather than rendered wrong."""


# Front matter ---------------------------------------------------------------

OBRIGATORIOS = ("titulo", "objetivo", "conclusao")


# Os dois indicadores de bloco do YAML. Escrever `objetivo: >` e continuar nas
# linhas indentadas e' a forma normal de por' um paragrafo no front matter, e sem
# isto o `>` virava a PRIMEIRA LETRA do texto — impresso no PDF que vai ao
# cliente, junto com as aspas em volta do titulo, na capa.
#
# HAVIA DOIS PARSERS de front matter neste tool, com o mesmo defeito. O conserto
# foi aplicado no de `specification.py` primeiro, o PDF saiu igualzinho, e so'
# entao ficou claro que quem le' o relatorio e' ESTE. Os helpers moram aqui, e
# `especificacao` os importa — um lugar so'.
_BLOCO = {">", ">-", ">+", "|", "|-", "|+"}


def valor_de_front_matter(bruto: str) -> str:
    return "" if bruto in _BLOCO else bruto


def desaspar(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def separar_front_matter(texto: str) -> tuple[dict[str, str], str]:
    if not texto.startswith("---\n"):
        raise ReportError(
            "O relatório precisa de front matter delimitado por `---`, com pelo "
            f"menos: {', '.join(OBRIGATORIOS)}."
        )
    fim = texto.find("\n---\n", 4)
    if fim == -1:
        raise ReportError("Front matter não fechado por `---`.")

    meta: dict[str, str] = {}
    chave_atual = None
    for linha in texto[4:fim].splitlines():
        if not linha.strip():
            continue
        if linha[0].isspace() and chave_atual:  # continuation of a long value
            meta[chave_atual] = (meta[chave_atual] + " " + linha.strip()).strip()
            continue
        chave, sep, valor = linha.partition(":")
        if not sep:
            continue
        chave_atual = chave.strip()
        meta[chave_atual] = valor_de_front_matter(valor.strip())

    meta = {k: desaspar(v) for k, v in meta.items()}
    faltando = [c for c in OBRIGATORIOS if not meta.get(c)]
    if faltando:
        raise ReportError(
            f"Front matter sem: {', '.join(faltando)}. "
            "`objetivo` e `conclusao` são obrigatórios porque a conclusão vem "
            "antes da evidência — é o que torna o relatório legível por quem "
            "decide."
        )
    return meta, texto[fim + 5:]


# Character sanitising -------------------------------------------------------
#
# ReportLab's built-in fonts use WinAnsiEncoding (cp1252). A character outside
# it renders as a filled black rectangle — silently, in the finished PDF, which
# is where the Linx team found theirs. So substitute what has an obvious
# equivalent, and report the rest instead of shipping a page of black boxes.

SUBSTITUICOES = {
    "→": "->", "←": "<-", "↔": "<->", "⇒": "=>", "⇐": "<=",
    "↑": "^", "↓": "v", "⟶": "->", "⟵": "<-",
    "✓": "OK", "✔": "OK", "✗": "X", "✘": "X", "★": "*", "☆": "*",
    "≥": ">=", "≤": "<=", "≠": "!=", "≈": "~", "×": "x",
    "“": '"', "”": '"', "‘": "'", "’": "'", "″": '"', "′": "'",
    " ": " ", " ": " ", " ": " ", "​": "",
}


def sanitizar(texto: str) -> tuple[str, set[str]]:
    """Return the text safe for WinAnsi, plus whatever could not be mapped."""
    out, perdidos = [], set()
    for ch in texto:
        if ch in SUBSTITUICOES:
            out.append(SUBSTITUICOES[ch])
            continue
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            perdidos.add(ch)
            # Fall back to the accent-stripped form when there is one; it is
            # wrong-ish but readable, where the raw char is a black box.
            decomposto = unicodedata.normalize("NFKD", ch)
            simples = "".join(c for c in decomposto if not
                              unicodedata.combining(c))
            try:
                simples.encode("cp1252")
                out.append(simples)
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out), perdidos


# Inline markup --------------------------------------------------------------

_RE_CODIGO = re.compile(r"`([^`]+)`")
_RE_NEGRITO = re.compile(r"\*\*(.+?)\*\*", re.S)
_RE_ITALICO = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.S)
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def inline(texto: str) -> str:
    """Convert inline Markdown to the mini-HTML a ReportLab Paragraph takes."""
    t = (texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    t = _RE_CODIGO.sub(
        lambda m: f'<font face="Courier" size="8.5">{m.group(1)}</font>', t)
    t = _RE_NEGRITO.sub(r"<b>\1</b>", t)
    t = _RE_ITALICO.sub(r"<i>\1</i>", t)
    t = _RE_LINK.sub(r"\1", t)  # a printed PDF has nowhere to click to
    t = t.replace("\\|", "|")
    return t


# Block parsing --------------------------------------------------------------

_RE_TITULO = re.compile(r"^(#{1,4})\s+(.*)$")
_RE_BULLET = re.compile(r"^([ \t]*)[-*+]\s+(.*)$")
_RE_NUMERO = re.compile(r"^([ \t]*)\d+[.)]\s+(.*)$")
_RE_CALLOUT = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
_RE_REGUA = re.compile(r"^([-*_])\1{2,}$")


def _linhas_tabela(linha: str) -> list[str]:
    """Split a table row on unescaped pipes."""
    interior = linha.strip()
    if interior.startswith("|"):
        interior = interior[1:]
    if interior.endswith("|") and not interior.endswith("\\|"):
        interior = interior[:-1]
    celulas, atual, i = [], [], 0
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


def _eh_separador(celulas: list[str]) -> bool:
    return all(set(c) <= {"-", ":", " "} and c for c in celulas)


def render_corpo(doc: Doc, corpo: str) -> None:
    """Append the Markdown body to the document, block by block."""
    linhas = corpo.split("\n")
    i = 0
    paragrafo: list[str] = []

    def liberar_paragrafo() -> None:
        nonlocal paragrafo
        if paragrafo:
            doc.texto(inline(" ".join(paragrafo).strip()))
            paragrafo = []

    while i < len(linhas):
        linha = linhas[i]
        crua = linha.rstrip()

        if not crua.strip():
            liberar_paragrafo()
            i += 1
            continue

        # fenced code
        if crua.lstrip().startswith("```"):
            liberar_paragrafo()
            i += 1
            bloco = []
            while i < len(linhas) and not linhas[i].lstrip().startswith("```"):
                bloco.append(linhas[i])
                i += 1
            i += 1
            if bloco:
                texto = "<br/>".join(
                    l.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace(" ", "&nbsp;")
                    for l in bloco)
                doc.texto(texto, style.MONO)
            continue

        # heading
        if m := _RE_TITULO.match(crua):
            liberar_paragrafo()
            nivel, texto = len(m.group(1)), m.group(2).strip()
            if nivel == 1:
                doc.titulo(inline(texto))      # cover already carries the name
            elif nivel == 2:
                doc.titulo(inline(texto))
            elif nivel == 3:
                doc.subtitulo(inline(texto))
            else:
                doc.subsubtitulo(inline(texto))
            i += 1
            continue

        # horizontal rule
        if _RE_REGUA.match(crua.strip()):
            liberar_paragrafo()
            doc.espaco(2 * mm)
            doc.add(style.regua())
            doc.espaco(2 * mm)
            i += 1
            continue

        # callout / blockquote
        if crua.lstrip().startswith(">"):
            liberar_paragrafo()
            linhas_bloco, tipo, titulo = [], "nota", ""
            if m := _RE_CALLOUT.match(crua.strip()):
                tipo = m.group(1).lower()
                titulo = m.group(2).strip()
            else:
                linhas_bloco.append(crua.lstrip()[1:].strip())
            i += 1
            while i < len(linhas) and linhas[i].lstrip().startswith(">"):
                linhas_bloco.append(linhas[i].lstrip()[1:].strip())
                i += 1
            # Consecutive `>` lines are one paragraph; a blank `>` separates
            # two. Treating each source line as its own paragraph would break
            # a wrapped sentence into stacked fragments.
            bloco, atual = [], []
            for l in linhas_bloco:
                if l:
                    atual.append(l)
                elif atual:
                    bloco.append(" ".join(atual))
                    atual = []
            if atual:
                bloco.append(" ".join(atual))
            cor = CORES_CAIXA.get(tipo, style.AZUL)
            doc.espaco(2 * mm)
            doc.add(style.caixa(inline(titulo) if titulo else "",
                                 [inline(b) for b in bloco], cor))
            doc.espaco(3 * mm)
            continue

        # table
        if crua.strip().startswith("|"):
            liberar_paragrafo()
            dados = []
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                celulas = _linhas_tabela(linhas[i])
                if not _eh_separador(celulas):
                    dados.append([inline(c) for c in celulas])
                i += 1
            if dados:
                doc.espaco(2 * mm)
                doc.add(style.tabela(dados))
                doc.espaco(3 * mm)
            continue

        # lists
        if _RE_BULLET.match(crua) or _RE_NUMERO.match(crua):
            liberar_paragrafo()
            itens, ordenada = [], bool(_RE_NUMERO.match(crua))
            while i < len(linhas):
                m = _RE_BULLET.match(linhas[i]) or _RE_NUMERO.match(linhas[i])
                if not m:
                    if (linhas[i].strip() and linhas[i][:1].isspace()
                            and itens):
                        itens[-1] += " " + linhas[i].strip()  # continuation
                        i += 1
                        continue
                    break
                itens.append(m.group(2).strip())
                i += 1
            if itens:
                doc.add(style.bullets([inline(x) for x in itens], ordenada))
                doc.espaco(2 * mm)
            continue

        paragrafo.append(crua.strip())
        i += 1

    liberar_paragrafo()


# Assembly -------------------------------------------------------------------


def construir(texto: str, rodape: str = "") -> tuple[Doc, set[str]]:
    """Build the document from the full Markdown source."""
    meta, corpo = separar_front_matter(texto)

    limpo, perdidos = sanitizar(texto)
    meta, corpo = separar_front_matter(limpo)

    doc = Doc(
        rodape=rodape or meta.get("rodape", ""),
        cabecalho=meta["titulo"],
        titulo_pdf=meta["titulo"],
        autor=meta.get("autor", "Elcamargo"),
        assunto=meta.get("tipo", ""),
    )

    identificacao = " · ".join(
        parte for parte in (
            f"Atividade {meta['atividade']}" if meta.get("atividade") else "",
            f"Versão {meta['versao']}" if meta.get("versao") else "",
            meta.get("data", ""),
            meta.get("autor", ""),
        ) if parte
    )
    doc.capa(inline(meta["titulo"]), inline(meta.get("subtitulo", "")),
             identificacao)

    # The pyramid, mechanically: objective and conclusion before section 1.
    doc.espaco(10 * mm)
    doc.add(style.tabela(
        [["Objetivo", inline(meta["objetivo"])],
         ["Conclusão", f"<b>{inline(meta['conclusao'])}</b>"]],
        larguras=[30 * mm, style.LARGURA_UTIL - 30 * mm],
        cabecalho=False,
    ))

    # The document circulates; a revision has to say what moved.
    if meta.get("mudancas"):
        doc.espaco(5 * mm)
        doc.add(style.caixa(
            f"O que mudou nesta versão ({meta.get('versao', '?')})",
            [inline(meta["mudancas"])], style.AMBAR))

    doc.quebra()
    render_corpo(doc, corpo)
    return doc, perdidos
