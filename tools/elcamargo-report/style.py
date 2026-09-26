#!/usr/bin/env python3
"""Visual language of the Elcamargo reports: palette, styles and blocks.

This module carries no document content, only how a document looks. Content
comes from Markdown — see `markdown_pdf.py`.

Requires ReportLab, which is only needed at the human boundary. Install it in a
throwaway venv so the project's own environment stays untouched:

    python3 -m venv ~/.cache/elcamargo-flow/venv
    ~/.cache/elcamargo-flow/venv/bin/python -m pip install reportlab pypdfium2
"""

from __future__ import annotations

import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, ListFlowable,
                                KeepTogether, ListItem, PageBreak, PageTemplate,
                                Paragraph,
                                Spacer, Table, TableStyle)

# Palette --------------------------------------------------------------------

AZUL = colors.HexColor("#1F3B57")       # primary: headings, table header
AZUL_CLARO = colors.HexColor("#E8EEF4")  # zebra stripe
CINZA = colors.HexColor("#5B6770")       # secondary text
CINZA_BORDA = colors.HexColor("#C8D0D8")
VERDE = colors.HexColor("#1E7A4B")
AMBAR = colors.HexColor("#B7791F")
VERMELHO = colors.HexColor("#B02A2A")
BRANCO = colors.white

# Callout keyword -> colour. Used by `> [!ok]` style blocks in Markdown.
CORES_CAIXA = {
    "ok": VERDE,
    "atencao": AMBAR,
    "erro": VERMELHO,
    "nota": AZUL,
}

LARGURA_UTIL = A4[0] - 40 * mm

# Styles ---------------------------------------------------------------------

_base = getSampleStyleSheet()

P = ParagraphStyle("P", parent=_base["BodyText"], fontName="Helvetica",
                   fontSize=9.5, leading=14, alignment=TA_JUSTIFY,
                   spaceAfter=5)
PB = ParagraphStyle("PB", parent=P, fontName="Helvetica-Bold")
NOTA = ParagraphStyle("NOTA", parent=P, fontSize=8, leading=11,
                      textColor=CINZA, alignment=TA_LEFT)
MONO = ParagraphStyle("MONO", parent=P, fontName="Courier", fontSize=8,
                      leading=11, alignment=TA_LEFT, backColor=AZUL_CLARO,
                      borderPadding=4, spaceBefore=4, spaceAfter=6)
H1 = ParagraphStyle("H1", parent=P, fontName="Helvetica-Bold", fontSize=14,
                    leading=18, textColor=AZUL, alignment=TA_LEFT,
                    spaceBefore=12, spaceAfter=6, keepWithNext=1)
H2 = ParagraphStyle("H2", parent=P, fontName="Helvetica-Bold", fontSize=11,
                    leading=15, textColor=AZUL, alignment=TA_LEFT,
                    spaceBefore=9, spaceAfter=4, keepWithNext=1)
H3 = ParagraphStyle("H3", parent=P, fontName="Helvetica-BoldOblique",
                    fontSize=9.5, leading=13, textColor=CINZA,
                    alignment=TA_LEFT, spaceBefore=7, spaceAfter=3,
                    keepWithNext=1)
CEL = ParagraphStyle("CEL", parent=P, fontSize=8.5, leading=11,
                     alignment=TA_LEFT, spaceAfter=0)
CEL_CAB = ParagraphStyle("CEL_CAB", parent=CEL, fontName="Helvetica-Bold",
                         textColor=BRANCO)
CAPA_TITULO = ParagraphStyle("CAPA_TITULO", parent=P, fontName="Helvetica-Bold",
                             fontSize=22, leading=27, textColor=AZUL,
                             alignment=TA_LEFT, spaceAfter=6)
CAPA_SUB = ParagraphStyle("CAPA_SUB", parent=P, fontSize=13, leading=17,
                          textColor=CINZA, alignment=TA_LEFT, spaceAfter=4)


# Blocks ---------------------------------------------------------------------


def larguras_por_conteudo(dados: list[list[str]], colunas: int,
                          minimo: float = 14 * mm) -> list[float]:
    """Distribute the available width by how much text each column carries.

    Equal columns waste the page: a `#` column holding "1".."5" does not need
    the same room as one holding a sentence. Weight by the longest cell, damped
    by a square root so one very long cell cannot starve its neighbours, then
    clamp to a floor so a narrow column stays readable.
    """
    larguras_texto = []
    for c in range(colunas):
        maior = 1
        for linha in dados:
            if c < len(linha):
                maior = max(maior, len(_sem_marcacao(str(linha[c]))))
        larguras_texto.append(maior ** 0.5)

    total = sum(larguras_texto)
    brutas = [LARGURA_UTIL * p / total for p in larguras_texto]

    # Raise anything under the floor, then take the difference back from the
    # columns that are above it, proportionally.
    faltante = sum(max(0.0, minimo - l) for l in brutas)
    if faltante:
        folgadas = [i for i, l in enumerate(brutas) if l > minimo]
        excedente = sum(brutas[i] - minimo for i in folgadas) or 1.0
        for i, l in enumerate(brutas):
            if l < minimo:
                brutas[i] = minimo
        for i in folgadas:
            brutas[i] -= faltante * (brutas[i] - minimo) / excedente
    return brutas


def _sem_marcacao(texto: str) -> str:
    """Length as the reader sees it: markup tags do not occupy the column."""
    return re.sub(r"<[^>]+>", "", texto)


def tabela(dados: list[list[str]], larguras: list[float] | None = None,
           cabecalho: bool = True) -> Table:
    """Build a table with a blue header row and zebra striping.

    `dados[0]` is the header when `cabecalho` is true. Cells are wrapped in
    Paragraphs so long text breaks instead of overflowing the column.
    """
    if not dados:
        raise ValueError("tabela() precisa de ao menos uma linha.")

    colunas = max(len(linha) for linha in dados)
    if larguras is None:
        larguras = larguras_por_conteudo(dados, colunas)

    corpo = []
    for i, linha in enumerate(dados):
        preenchida = list(linha) + [""] * (colunas - len(linha))
        estilo = CEL_CAB if (cabecalho and i == 0) else CEL
        corpo.append([Paragraph(str(c), estilo) for c in preenchida])

    t = Table(corpo, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    comandos = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if cabecalho:
        comandos.append(("BACKGROUND", (0, 0), (-1, 0), AZUL))
        for i in range(2, len(corpo), 2):
            comandos.append(("BACKGROUND", (0, i), (-1, i), AZUL_CLARO))
    else:
        for i in range(1, len(corpo), 2):
            comandos.append(("BACKGROUND", (0, i), (-1, i), AZUL_CLARO))
    t.setStyle(TableStyle(comandos))
    return t


def caixa(titulo: str, paragrafos: list[str], cor=AZUL) -> Table:
    """A highlighted block: coloured left rule, tinted background."""
    conteudo = []
    if titulo:
        conteudo.append(Paragraph(titulo, ParagraphStyle(
            "CaixaTitulo", parent=PB, textColor=cor, spaceAfter=3)))
    for texto in paragrafos:
        conteudo.append(Paragraph(texto, ParagraphStyle(
            "CaixaTexto", parent=P, spaceAfter=2)))

    t = Table([[conteudo]], colWidths=[LARGURA_UTIL])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, cor),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def bullets(itens: list, ordenada: bool = False) -> ListFlowable:
    """A bullet or numbered list. Items may be strings or nested flowables."""
    elementos = []
    for item in itens:
        if isinstance(item, str):
            elementos.append(ListItem(Paragraph(item, P), leftIndent=12))
        else:
            elementos.append(ListItem(item, leftIndent=12))
    return ListFlowable(
        elementos,
        bulletType="1" if ordenada else "bullet",
        start="1" if ordenada else None,
        bulletFontName="Helvetica",
        bulletFontSize=9.5,
        leftIndent=14,
        bulletOffsetY=0,
    )


def regua() -> Table:
    """A horizontal rule, as a bottom-bordered empty row."""
    t = Table([[""]], colWidths=[LARGURA_UTIL], rowHeights=[1])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, CINZA_BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# Document -------------------------------------------------------------------


class Doc:
    """An A4 report with a running header and numbered footer."""

    def __init__(self, rodape: str = "", titulo_pdf: str = "",
                 autor: str = "", assunto: str = "",
                 cabecalho: str = "") -> None:
        self.rodape = rodape
        self.cabecalho = cabecalho
        self.titulo_pdf = titulo_pdf
        self.autor = autor
        self.assunto = assunto
        self.flowables: list = []
        self._titulo_pendente = None

    # -- content ----------------------------------------------------------
    #
    # A heading is held back until the block that follows it arrives, and the
    # two are then bound with KeepTogether. `keepWithNext` alone does not
    # survive every flowable type, and the failure is an orphan heading alone
    # at the foot of a page — invisible in the source, obvious to the reader.

    def add(self, flowable) -> None:
        if self._titulo_pendente is not None:
            pendente, self._titulo_pendente = self._titulo_pendente, None
            self.flowables.append(KeepTogether([pendente, flowable]))
        else:
            self.flowables.append(flowable)

    def _add_direto(self, flowable) -> None:
        """Append without consuming a pending heading (spacers, rules)."""
        self.flowables.append(flowable)

    def _liberar_titulo(self) -> None:
        if self._titulo_pendente is not None:
            self.flowables.append(self._titulo_pendente)
            self._titulo_pendente = None

    def capa(self, titulo: str, subtitulo: str = "",
             identificacao: str = "") -> None:
        self.add(Spacer(1, 45 * mm))
        self.add(Paragraph(titulo, CAPA_TITULO))
        if subtitulo:
            self.add(Paragraph(subtitulo, CAPA_SUB))
        self.add(Spacer(1, 5 * mm))
        self.add(regua())
        if identificacao:
            self.add(Spacer(1, 4 * mm))
            self.add(Paragraph(identificacao, NOTA))

    def titulo(self, texto: str) -> None:
        self._pendurar(Paragraph(texto, H1))

    def subtitulo(self, texto: str) -> None:
        self._pendurar(Paragraph(texto, H2))

    def subsubtitulo(self, texto: str) -> None:
        self._pendurar(Paragraph(texto, H3))

    def _pendurar(self, paragrafo) -> None:
        self._liberar_titulo()  # two headings in a row: the first stands alone
        self._titulo_pendente = paragrafo

    def texto(self, conteudo: str, estilo: ParagraphStyle = P) -> None:
        self.add(Paragraph(conteudo, estilo))

    def espaco(self, altura: float = 4 * mm) -> None:
        self._add_direto(Spacer(1, altura))

    def quebra(self) -> None:
        self._liberar_titulo()
        self._add_direto(PageBreak())

    # -- rendering --------------------------------------------------------

    def _decorar(self, canvas, doc) -> None:
        canvas.saveState()
        if self.cabecalho and doc.page > 1:
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(CINZA)
            canvas.drawString(20 * mm, A4[1] - 13 * mm, self.cabecalho)
            canvas.setStrokeColor(CINZA_BORDA)
            canvas.setLineWidth(0.4)
            canvas.line(20 * mm, A4[1] - 15 * mm, A4[0] - 20 * mm,
                        A4[1] - 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        if self.rodape:
            canvas.drawString(20 * mm, 12 * mm, self.rodape)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    def gerar(self, destino: str) -> str:
        self._liberar_titulo()  # a heading with nothing after it still prints
        doc = BaseDocTemplate(
            destino,
            pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
            title=self.titulo_pdf, author=self.autor, subject=self.assunto,
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                      id="corpo")
        doc.addPageTemplates([
            PageTemplate(id="padrao", frames=[frame], onPage=self._decorar)
        ])
        doc.build(self.flowables)
        return destino
