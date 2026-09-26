#!/usr/bin/env python3
"""The Elcamargo functional-specification layout.

Reproduces the house standard: full-bleed cover, addressee page with project
members and version control, confidentiality term, table of contents with real
page numbers, and the running header and footer on every page.

Everything that identifies a project — client name, members, logo — comes from
`[documento]` in the project's `config.toml`. The package itself carries only
Elcamargo's own brand assets, so the same generator serves any client.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ATIVOS = Path(__file__).resolve().parents[2] / "assets"

# Palette read off the reference document.
TINTA = colors.HexColor("#14232B")        # body text
GRAFITE = colors.HexColor("#3D4A52")      # headings
CINZA = colors.HexColor("#6B767E")        # secondary
CINZA_FAIXA = colors.HexColor("#D9D9D9")  # table stripe
CINZA_LINHA = colors.HexColor("#A6A6A6")
LINK = colors.HexColor("#2E6E8E")
CAPA_FUNDO = colors.HexColor("#0B1E2D")
CIANO = colors.HexColor("#22D3D8")        # cover rule

MARGEM = 20 * mm
LARGURA_UTIL = A4[0] - 2 * MARGEM


# Fonts ----------------------------------------------------------------------
#
# The house documents are written in Word and set in Aptos. Aptos ships with
# Microsoft Office and is not ours to redistribute, so it is used from wherever
# Office installed it and never bundled in the package. Without Office the
# document still renders, in Helvetica.

_CAMINHOS_APTOS = [
    Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
    Path("C:/Windows/Fonts"),
]

FONTE = "Helvetica"
FONTE_B = "Helvetica-Bold"
FONTE_I = "Helvetica-Oblique"
FONTE_BI = "Helvetica-BoldOblique"


def registrar_fontes() -> bool:
    """Register Aptos when present. Returns whether it was found."""
    global FONTE, FONTE_B, FONTE_I, FONTE_BI
    arquivos = {"Aptos": "Aptos.ttf", "Aptos-Bold": "Aptos-Bold.ttf",
                "Aptos-Italic": "Aptos-Italic.ttf",
                "Aptos-BoldItalic": "Aptos-Bold-Italic.ttf"}
    for base in _CAMINHOS_APTOS:
        if not (base / "Aptos.ttf").exists():
            continue
        try:
            for nome, arquivo in arquivos.items():
                caminho = base / arquivo
                if not caminho.exists():
                    return False
                pdfmetrics.registerFont(TTFont(nome, str(caminho)))
            pdfmetrics.registerFontFamily(
                "Aptos", normal="Aptos", bold="Aptos-Bold",
                italic="Aptos-Italic", boldItalic="Aptos-BoldItalic")
        except Exception:
            return False
        FONTE, FONTE_B = "Aptos", "Aptos-Bold"
        FONTE_I, FONTE_BI = "Aptos-Italic", "Aptos-BoldItalic"
        return True
    return False


TEM_APTOS = registrar_fontes()


# Styles ---------------------------------------------------------------------

def _estilo(nome: str, **kw) -> ParagraphStyle:
    base = dict(fontName=FONTE, fontSize=10.5, leading=18, textColor=TINTA,
                alignment=TA_JUSTIFY, spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(nome, **base)


P = _estilo("P")
PB = _estilo("PB", fontName=FONTE_B)
ITEM = _estilo("ITEM", fontName=FONTE_B, alignment=TA_LEFT, spaceBefore=6,
               spaceAfter=2, keepWithNext=1)
SECAO = _estilo("SECAO", fontName=FONTE_B, fontSize=15, leading=20,
                textColor=GRAFITE, alignment=TA_LEFT, spaceBefore=14,
                spaceAfter=8, keepWithNext=1)
SUB = _estilo("SUB", fontName=FONTE_BI, fontSize=11, leading=15,
              alignment=TA_LEFT, spaceBefore=10, spaceAfter=4, keepWithNext=1)
NOTA = _estilo("NOTA", fontSize=8, leading=11, textColor=CINZA,
               alignment=TA_LEFT, spaceAfter=0)
CEL = _estilo("CEL", fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=0)
CEL_B = _estilo("CEL_B", fontName=FONTE_B, fontSize=10, leading=14,
                alignment=TA_LEFT, spaceAfter=0)
CEL_ORG = _estilo("CEL_ORG", fontName=FONTE_I, fontSize=10, leading=14,
                  alignment=TA_LEFT, spaceAfter=0)
EMAIL = _estilo("EMAIL", fontSize=10, leading=14, textColor=LINK,
                alignment=TA_LEFT, spaceAfter=0)
CAPA_TIT = _estilo("CAPA_TIT", fontName=FONTE, fontSize=25, leading=30,
                   textColor=colors.white, alignment=TA_RIGHT, spaceAfter=0)
CAPA_SUB = _estilo("CAPA_SUB", fontSize=15, leading=24, textColor=colors.white,
                   alignment=TA_RIGHT, spaceAfter=0)
MONO = _estilo("MONO", fontName="Courier", fontSize=8.5, leading=12,
               alignment=TA_LEFT, backColor=colors.HexColor("#F0F2F4"),
               borderPadding=5, spaceBefore=4, spaceAfter=6)


def versalete(texto: str, tamanho: float = 15) -> Paragraph:
    """Render a heading the way the house style does: small caps.

    Word applies real small caps; ReportLab has no such switch, so the first
    letter of each word is set at full size and the rest smaller. The result
    matches the reference closely enough to sit beside it.
    """
    partes = []
    for palavra in texto.split(" "):
        if not palavra:
            continue
        partes.append(
            f'<font size="{tamanho}">{palavra[0].upper()}</font>'
            f'<font size="{tamanho * 0.78:.1f}">{palavra[1:].upper()}</font>')
    return Paragraph(" ".join(partes), _estilo(
        "VERSALETE", fontName=FONTE_B, fontSize=tamanho, leading=tamanho * 1.3,
        textColor=GRAFITE, alignment=TA_LEFT, spaceBefore=10, spaceAfter=6,
        keepWithNext=1))


# Blocks ---------------------------------------------------------------------


def tabela_integrantes(cliente: str, pessoas_cliente: list[str],
                       fornecedor: str, pessoas_fornecedor: list[str]) -> Table:
    """The project members block: one row per organisation."""
    def celula(pessoas: list[str]) -> list:
        saida = []
        for i, pessoa in enumerate(pessoas):
            nome, _, email = pessoa.partition("<")
            if i:
                saida.append(Spacer(1, 5))
            saida.append(Paragraph(nome.strip(), CEL))
            if email:
                saida.append(Paragraph(
                    f'<u>{email.rstrip(">").strip()}</u>', EMAIL))
        return saida

    dados = [[Paragraph(cliente, CEL_ORG), celula(pessoas_cliente)],
             [Paragraph(fornecedor, CEL_ORG), celula(pessoas_fornecedor)]]
    t = Table(dados, colWidths=[LARGURA_UTIL * 0.28, LARGURA_UTIL * 0.72])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, -1), "MIDDLE"),
        ("VALIGN", (1, 0), (1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), CINZA_FAIXA),
        ("BOX", (1, 0), (1, -1), 0.5, CINZA_LINHA),
        ("LINEBELOW", (1, 0), (1, 0), 0.5, CINZA_LINHA),
        ("LINEABOVE", (0, 0), (0, 0), 0.5, CINZA_LINHA),
        ("LINEBELOW", (0, -1), (0, -1), 0.5, CINZA_LINHA),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def tabela_versoes(linhas: list[list]) -> Table:
    """Version control: plain header, striped rows.

    A cell may be a pair `(pessoa, ferramenta)`. Both are named because both
    answer for the document: the skill wrote it, the person reviewed it before
    it circulated.
    """
    def celula(valor, estilo=CEL):
        if isinstance(valor, (tuple, list)):
            pessoa, ferramenta = valor
            return [Paragraph(str(pessoa), estilo),
                    Paragraph(str(ferramenta), NOTA)]
        return Paragraph(str(valor), estilo)

    dados = [[Paragraph(c, CEL_B) for c in ("Versão", "Data", "Nome",
                                            "Comentários")]]
    dados += [[celula(c) for c in linha] for linha in linhas]
    larguras = [LARGURA_UTIL * p for p in (0.13, 0.17, 0.25, 0.45)]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    comandos = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TINTA),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(dados), 2):
        comandos.append(("BACKGROUND", (0, i), (-1, i), CINZA_FAIXA))
    t.setStyle(TableStyle(comandos))
    return t


def tabela_corpo(dados: list[list[str]], cabecalho: bool = True) -> Table:
    """A table inside the body, in the same restrained house estilo."""
    colunas = max(len(l) for l in dados)
    larguras = _larguras(dados, colunas)
    corpo = [[Paragraph(str(c), CEL_B if (cabecalho and i == 0) else CEL)
              for c in list(linha) + [""] * (colunas - len(linha))]
             for i, linha in enumerate(dados)]
    t = Table(corpo, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    comandos = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if cabecalho:
        comandos.append(("BACKGROUND", (0, 0), (-1, 0), CINZA_FAIXA))
    t.setStyle(TableStyle(comandos))
    return t


def _larguras(dados: list[list[str]], colunas: int,
              minimo: float = 16 * mm) -> list[float]:
    """Width by content, damped, with a floor. See the report generator."""
    import re
    pesos = []
    for c in range(colunas):
        maior = max((len(re.sub(r"<[^>]+>", "", str(l[c])))
                     for l in dados if c < len(l)), default=1)
        pesos.append(max(maior, 1) ** 0.5)
    brutas = [LARGURA_UTIL * p / sum(pesos) for p in pesos]
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


def sumario() -> TableOfContents:
    t = TableOfContents()
    t.levelStyles = [_estilo("TOC0", fontName=FONTE_I, fontSize=11, leading=21,
                             alignment=TA_LEFT, spaceAfter=0, firstLineIndent=0,
                             leftIndent=0)]
    t.dotsMinLevel = 0
    return t


def secao(texto: str) -> Paragraph:
    """A numbered section heading, in the small caps the house style uses.

    Carries the plain text as `_toc_texto` so the table of contents shows what
    was written, not the small-caps markup that renders it.
    """
    paragrafo = versalete(texto, 15)
    paragrafo._toc_texto = texto
    return paragrafo


def regua_fina() -> Table:
    t = Table([[""]], colWidths=[LARGURA_UTIL], rowHeights=[1])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, CINZA_LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# Document -------------------------------------------------------------------


class Especificacao:
    """A document in the Elcamargo functional-specification layout."""

    def __init__(self, doc: dict, titulo: str, subtitulo: str = "",
                 logo_cliente: str | None = None,
                 assinatura: str = "") -> None:
        self.assinatura = assinatura
        self.cfg = doc
        self.titulo = titulo
        self.subtitulo = subtitulo or doc.get("produto", "")
        self.logo_cliente = logo_cliente
        self.flowables: list = []
        self.total_paginas = 0
        self._entradas_toc: list[tuple[int, str, int]] = []

    # -- page furniture ---------------------------------------------------

    def _capa(self, canvas, doc) -> None:
        canvas.saveState()
        fundo = ATIVOS / "cover-background.jpg"
        if fundo.exists():
            canvas.drawImage(str(fundo), 0, 0, width=A4[0], height=A4[1],
                             preserveAspectRatio=False, mask="auto")
        else:
            canvas.setFillColor(CAPA_FUNDO)
            canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        # A dark scrim: the photograph varies, the text must not.
        canvas.setFillColor(colors.Color(0.04, 0.12, 0.18, alpha=0.55))
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)

        if self.logo_cliente and Path(self.logo_cliente).exists():
            self._centrar(canvas, self.logo_cliente, A4[1] - 78 * mm, 46 * mm)
        marca = ATIVOS / "logo-elcamargo.png"
        if marca.exists():
            self._centrar(canvas, str(marca), A4[1] - 140 * mm, 62 * mm)

        canvas.setFillColor(colors.white)
        canvas.setFont(FONTE, 25)
        canvas.drawRightString(A4[0] - MARGEM, 88 * mm, "Especificação Funcional")
        canvas.setStrokeColor(CIANO)
        canvas.setLineWidth(2)
        canvas.line(A4[0] - MARGEM - 110 * mm, 82 * mm, A4[0] - MARGEM, 82 * mm)
        canvas.setFont(FONTE, 15)
        canvas.drawRightString(A4[0] - MARGEM, 70 * mm, self.subtitulo)
        canvas.drawRightString(A4[0] - MARGEM, 60 * mm, self.titulo)
        canvas.restoreState()

    @staticmethod
    def _centrar(canvas, caminho: str, y: float, largura: float) -> None:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(caminho)
        lw, lh = img.getSize()
        altura = largura * lh / lw
        canvas.drawImage(img, (A4[0] - largura) / 2, y, width=largura,
                         height=altura, mask="auto")

    def _pagina(self, canvas, doc) -> None:
        canvas.saveState()
        classificacao = self.cfg.get("classificacao", "")
        forn = self.cfg.get("fornecedor", {})

        canvas.setFont(FONTE, 8)
        canvas.setFillColor(TINTA)
        if classificacao:
            canvas.drawString(MARGEM, A4[1] - 12 * mm, classificacao)

        marca = ATIVOS / "header-mark.png"
        if marca.exists():
            from reportlab.lib.utils import ImageReader
            img = ImageReader(str(marca))
            lw, lh = img.getSize()
            largura = 22 * mm
            canvas.drawImage(img, MARGEM + 4 * mm, A4[1] - 27 * mm,
                             width=largura, height=largura * lh / lw,
                             mask="auto")
        canvas.setStrokeColor(CINZA_LINHA)
        canvas.setLineWidth(0.5)
        canvas.line(MARGEM, A4[1] - 28 * mm, A4[0] - MARGEM, A4[1] - 28 * mm)
        canvas.setFont(FONTE, 8.5)
        canvas.setFillColor(CINZA)
        canvas.drawRightString(A4[0] - MARGEM, A4[1] - 26.5 * mm,
                               forn.get("nome", ""))

        canvas.line(MARGEM, 28 * mm, A4[0] - MARGEM, 28 * mm)
        canvas.setFont(FONTE, 8)
        canvas.setFillColor(CINZA)
        razao = forn.get("razao_social", "")
        cnpj = forn.get("cnpj", "")
        canvas.drawString(MARGEM + 4 * mm, 24 * mm,
                          f"{razao} – CNPJ: {cnpj}" if cnpj else razao)
        canvas.drawString(MARGEM + 4 * mm, 20.5 * mm, forn.get("endereco", ""))

        texto = self.cfg.get("classificacao_texto", "")
        if texto:
            canvas.setFillColor(TINTA)
            canvas.setFont(FONTE, 7.5)
            for i, linha in enumerate(_quebrar(canvas, texto, LARGURA_UTIL,
                                               FONTE, 7.5)):
                canvas.drawString(MARGEM, 15 * mm - i * 4 * mm, linha)
        canvas.restoreState()

    # -- build ------------------------------------------------------------

    def _numero(self, canvas, numero: int, total: int) -> None:
        """`N de M`, right-aligned in the footer, with N in bold."""
        canvas.saveState()
        canvas.setFillColor(TINTA)
        largura_n = canvas.stringWidth(str(numero), FONTE_B, 8.5)
        sufixo = f" de {total}"
        largura_s = canvas.stringWidth(sufixo, FONTE, 8.5)
        x = A4[0] - MARGEM - largura_n - largura_s
        canvas.setFont(FONTE_B, 8.5)
        canvas.drawString(x, 20.5 * mm, str(numero))
        canvas.setFont(FONTE, 8.5)
        canvas.drawString(x + largura_n, 20.5 * mm, sufixo)
        canvas.restoreState()

    def gerar(self, destino: str) -> str:
        doc = BaseDocTemplate(
            destino, pagesize=A4,
            leftMargin=MARGEM, rightMargin=MARGEM,
            topMargin=32 * mm, bottomMargin=32 * mm,
            title=f"{self.cfg.get('cliente', '')} - Especificação Funcional - "
                  f"{self.subtitulo} - {self.titulo}".strip(" -"),
            author=self.assinatura or self.cfg.get(
                "fornecedor", {}).get("nome", "Elcamargo"),
            subject=self.titulo,
        )
        doc.addPageTemplates([
            PageTemplate(id="capa", frames=[Frame(0, 0, A4[0], A4[1],
                                                  id="capa")],
                         onPage=self._capa),
            PageTemplate(id="corpo",
                         frames=[Frame(doc.leftMargin, doc.bottomMargin,
                                       doc.width, doc.height, id="corpo")],
                         onPage=self._pagina),
        ])

        class _Doc(type(doc)):
            def afterFlowable(self, flowable):
                # Feed the table of contents with real page numbers.
                texto = getattr(flowable, "_toc_texto", None)
                if texto:
                    self.notify("TOCEntry", (0, texto, self.page - 1))

        doc.__class__ = _Doc
        # One build. The page total is not known until the last page is laid
        # out, so the footer number is drawn by the canvas at save time — not
        # by rebuilding, which would reuse spent flowables and blow up the
        # layout.
        doc.multiBuild(self.flowables, canvasmaker=_canvas_numerado(self))
        return destino


def _canvas_numerado(especificacao):
    """A canvas that defers page furniture until the page total is known."""
    from reportlab.pdfgen import canvas as _canvas

    class CanvasNumerado(_canvas.Canvas):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for i, estado in enumerate(self._paginas, start=1):
                self.__dict__.update(estado)
                if i > 1:  # the cover carries no number
                    especificacao._numero(self, i - 1, total - 1)
                super().showPage()
            super().save()

    return CanvasNumerado


def _quebrar(canvas, texto: str, largura: float, fonte: str,
             tamanho: float) -> list[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for palavra in palavras:
        teste = f"{atual} {palavra}".strip()
        if canvas.stringWidth(teste, fonte, tamanho) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def estilo_secao_toc() -> ParagraphStyle:
    """Section headings carry this style so `afterFlowable` can spot them."""
    return _estilo("SECAO_TOC", fontName=FONTE_B, fontSize=15, leading=20,
                   textColor=GRAFITE, alignment=TA_LEFT, spaceBefore=14,
                   spaceAfter=8, keepWithNext=1)


TERMO = (
    "Esta especificação funcional contém informações confidenciais e de "
    "propriedade exclusiva da {fornecedor}, sendo caracterizado como segredo "
    "de negócio. Todas as informações nele contidas devem ser tratadas com o "
    "mais alto grau de confidencialidade pelo cliente, sendo vedada sua "
    "revelação, reprodução, duplicação ou utilização, total ou parcial, para "
    "quaisquer finalidades distintas da avaliação deste material pela empresa.",
    "É expressamente proibido o compartilhamento das informações descritas "
    "neste documento com terceiros, salvo mediante aprovação prévia e expressa "
    "dos representantes legais da {fornecedor}, observadas as condições "
    "estabelecidas em tal autorização.",
)

ABERTURA = (
    "É com satisfação que apresentamos a seguir nossa especificação funcional "
    "do projeto com os requisitos funcional e regras aplicadas ao entregável.",
    "O presente documento define o escopo de negócio do projeto, conforme "
    "entendimento das informações apresentadas.",
)
