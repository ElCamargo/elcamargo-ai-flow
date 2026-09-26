#!/usr/bin/env python3
"""Assemble a functional specification in the Elcamargo house layout.

Input is the same Markdown every skill already writes; what changes is the
wrapper: cover, addressee page, confidentiality term, table of contents, and
the eight fixed sections of the standard.

Section numbering is generated here — unlike a free-form report, where the
author numbers by hand to keep numbering stable across revisions. In a
specification the section list is fixed, so numbering is stable by
construction.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, NextPageTemplate, PageBreak, Paragraph, Spacer

import elcamargo_standard as pp
from markdown_pdf import (ReportError, desaspar, inline,  # noqa: F401
                          sanitizar, valor_de_front_matter,
                          separar_front_matter)

# The eight sections of the standard, in order. The first takes the document's
# own title; the rest are fixed.
SECOES = [
    ("contexto", None),
    ("regras", "Regras de Negócio"),
    ("rf", "[RF] REQUISITOS FUNCIONAIS"),
    ("rnf", "[RNF] REQUISITOS NÃO FUNCIONAIS"),
    ("ca", "[CA] CRITÉRIOS DE ACEITE"),
    ("ct", "[CT] CASOS DE TESTE"),
    ("prototipos", "Protótipos"),
    ("consideracoes", "Considerações Gerais"),
]

OBRIGATORIOS = ("titulo",)


def _paragrafo(doc_flow: list, texto: str) -> None:
    doc_flow.append(Paragraph(inline(texto), pp.P))


def montar(texto: str, cfg: dict, logo_cliente: str | None = None):
    """Build the specification from Markdown plus the project's `[documento]`."""
    limpo, perdidos = sanitizar(texto)
    meta, corpo = _front_matter(limpo)

    operador = (cfg.get("operador", "") or "").split("<")[0].strip()
    ferramenta = meta.get("gerado_por", "")
    esp = pp.Especificacao(
        cfg,
        titulo=meta["titulo"],
        subtitulo=meta.get("produto", cfg.get("produto", "")),
        logo_cliente=logo_cliente,
        assinatura=" · ".join(x for x in (operador, ferramenta) if x),
    )
    f = esp.flowables
    cliente = cfg.get("cliente", "")
    fornecedor = cfg.get("fornecedor", {}).get("nome", "Elcamargo")

    # 1. Cover, drawn entirely by the page template.
    f.append(NextPageTemplate("corpo"))
    f.append(PageBreak())

    # 2. Addressee, members, version control.
    f.append(Paragraph("À", pp.PB))
    f.append(Spacer(1, 4 * mm))
    f.append(Paragraph(cliente, pp.PB))
    f.append(Spacer(1, 4 * mm))
    for paragrafo in pp.ABERTURA:
        _paragrafo(f, paragrafo)
    f.append(Spacer(1, 10 * mm))
    f.append(pp.versalete("Informações sobre a Especificação Funcional", 14))
    f.append(Spacer(1, 5 * mm))
    f.append(Paragraph("Integrantes do Projeto", pp.SUB))
    f.append(Spacer(1, 2 * mm))
    integrantes = cfg.get("integrantes", {})
    f.append(pp.tabela_integrantes(
        cliente, integrantes.get("cliente", []),
        fornecedor, integrantes.get("fornecedor", [])))
    f.append(Spacer(1, 12 * mm))
    f.append(pp.versalete("Controle de Versões", 14))
    f.append(Spacer(1, 3 * mm))
    f.append(pp.tabela_versoes(_versoes(meta, cfg)))
    f.append(PageBreak())

    # 3. Confidentiality.
    f.append(Paragraph("Termo de Responsabilidade e Confidencialidade", pp.SECAO))
    f.append(Spacer(1, 3 * mm))
    for paragrafo in pp.TERMO:
        _paragrafo(f, paragrafo.format(fornecedor=fornecedor))
    if cfg.get("operador") and meta.get("gerado_por"):
        # Belongs on this page, not under the version table: the page is
        # already about who answers for the document.
        f.append(Spacer(1, 6 * mm))
        _paragrafo(f, "Este documento foi produzido com assistência de IA e "
                      "revisado antes de circular. A skill que o gerou e a "
                      "pessoa que o revisou constam no controle de versões e "
                      "respondem por ele em conjunto.")
    f.append(PageBreak())

    # 4. Contents.
    f.append(pp.versalete("Sumário", 15))
    f.append(pp.regua_fina())
    f.append(Spacer(1, 3 * mm))
    f.append(pp.sumario())
    f.append(PageBreak())

    # 5. Body.
    _corpo(f, corpo, meta["titulo"])
    return esp, perdidos


def _front_matter(texto: str) -> tuple[dict, str]:
    if not texto.startswith("---\n"):
        raise ReportError("A especificação precisa de front matter com `titulo`.")
    fim = texto.find("\n---\n", 4)
    if fim == -1:
        raise ReportError("Front matter não fechado por `---`.")
    meta, chave = {}, None
    for linha in texto[4:fim].splitlines():
        if not linha.strip():
            continue
        if linha[0].isspace() and chave:
            meta[chave] = (meta[chave] + " " + linha.strip()).strip()
            continue
        k, sep, v = linha.partition(":")
        if sep:
            chave = k.strip()
            meta[chave] = valor_de_front_matter(v.strip())
    meta = {k: desaspar(v) for k, v in meta.items()}
    faltando = [c for c in OBRIGATORIOS if not meta.get(c)]
    if faltando:
        raise ReportError(f"Front matter sem: {', '.join(faltando)}.")
    return meta, texto[fim + 5:]


def _versoes(meta: dict, cfg: dict) -> list[list]:
    """Version history: `versoes` as `1.0 | data | nome | comentário` lines.

    When a row names nobody, it is signed by both the person accountable for
    the document and the skill that produced it. Neither alone is the truth:
    the skill wrote it, the person reviewed it before it went out.
    """
    operador = (cfg.get("operador", "") or "").split("<")[0].strip()
    ferramenta = meta.get("gerado_por", "")
    assinatura = ((operador, ferramenta) if operador and ferramenta
                  else operador or ferramenta)

    linhas: list[list] = []
    for entrada in meta.get("versoes", "").split(";"):
        partes = [p.strip() for p in entrada.split("|")]
        if len(partes) == 4 and any(partes):
            linhas.append([partes[0], partes[1],
                           partes[2] or assinatura, partes[3]])
    if not linhas:
        linhas = [[meta.get("versao", "1.0"), meta.get("data", ""),
                   meta.get("autor") or assinatura,
                   meta.get("comentario", "Criação do documento.")]]
    return linhas


def _corpo(f: list, corpo: str, titulo: str) -> None:
    """Render the eight sections, numbering them as it goes."""
    blocos = _fatiar(corpo)
    numero = 0
    for chave, rotulo in SECOES:
        conteudo = blocos.get(chave, "").strip()
        if not conteudo and chave not in ("contexto", "regras"):
            continue
        numero += 1
        nome = rotulo or titulo
        cabeca = pp.secao(f"{numero} {nome}")
        # The heading travels with its first block. A section title alone at
        # the foot of a page reads as a mistake, and is invisible in the source.
        bloco: list = []
        _render(bloco, conteudo)
        if bloco:
            primeiro = bloco[0]
            # Merge instead of nesting: a KeepTogether inside another cannot be
            # measured by the outer one, which then pushes the whole section to
            # the next page and leaves most of this one blank.
            interno = (list(primeiro._content)
                       if isinstance(primeiro, KeepTogether) else [primeiro])
            f.append(KeepTogether([cabeca, *interno]))
            f.extend(bloco[1:])
        else:
            f.append(cabeca)


def _fatiar(corpo: str) -> dict[str, str]:
    """Split the body on `## <chave>` markers matching SECOES."""
    aceitos = {c for c, _ in SECOES}
    blocos, atual, buffer = {}, "contexto", []
    for linha in corpo.split("\n"):
        s = linha.strip()
        if s.startswith("## "):
            chave = s[3:].strip().lower()
            if chave in aceitos:
                blocos[atual] = "\n".join(buffer)
                atual, buffer = chave, []
                continue
        buffer.append(linha)
    blocos[atual] = "\n".join(buffer)
    return blocos


def _render(f: list, texto: str) -> None:
    """Render one section: item headings, paragraphs, lists, tables, code."""
    linhas = texto.split("\n")
    i, paragrafo = 0, []

    def liberar():
        nonlocal paragrafo
        if paragrafo:
            f.append(Paragraph(inline(" ".join(paragrafo).strip()), pp.P))
            paragrafo = []

    while i < len(linhas):
        crua = linhas[i].rstrip()
        s = crua.strip()

        if not s:
            liberar()
            i += 1
            continue

        if s.startswith("```"):
            liberar()
            i += 1
            bloco = []
            while i < len(linhas) and not linhas[i].lstrip().startswith("```"):
                bloco.append(linhas[i])
                i += 1
            i += 1
            if bloco:
                f.append(Paragraph("<br/>".join(
                    l.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace(" ", "&nbsp;")
                    for l in bloco), pp.MONO))
            continue

        if s.startswith("|"):
            liberar()
            dados = []
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                celulas = [c.strip() for c in
                           linhas[i].strip().strip("|").split("|")]
                if not all(set(c) <= {"-", ":", " "} and c for c in celulas):
                    dados.append([inline(c) for c in celulas])
                i += 1
            if dados:
                f.append(Spacer(1, 2 * mm))
                f.append(pp.tabela_corpo(dados))
                f.append(Spacer(1, 3 * mm))
            continue

        if s.startswith("### "):
            # `### RN-01 - Título` — the item heading of the standard. It must
            # never be stranded at the foot of a page, so it travels with its
            # first paragraph.
            liberar()
            titulo_item = s[4:].strip()
            seguinte, salto = _proximo_paragrafo(linhas, i + 1)
            item = [Paragraph(inline(titulo_item), pp.ITEM)]
            if seguinte:
                item.append(Paragraph(inline(seguinte), pp.P))
            f.append(KeepTogether(item))
            i = salto
            continue

        if s.startswith("#### "):
            liberar()
            f.append(Paragraph(inline(s[5:].strip()), pp.SUB))
            i += 1
            continue

        if s[:2] in ("- ", "* ") or (s[:1].isdigit() and s[1:3] in (". ", ") ")):
            liberar()
            itens = []
            while i < len(linhas):
                t = linhas[i].strip()
                if t[:2] in ("- ", "* "):
                    itens.append(t[2:])
                elif t[:1].isdigit() and t[1:3] in (". ", ") "):
                    itens.append(t[3:])
                else:
                    break
                i += 1
            for item in itens:
                f.append(Paragraph(
                    f"•&nbsp;&nbsp;{inline(item)}",
                    pp._estilo("LI", leftIndent=10, spaceAfter=2)))
            f.append(Spacer(1, 2 * mm))
            continue

        paragrafo.append(s)
        i += 1

    liberar()


def _proximo_paragrafo(linhas: list[str], inicio: int) -> tuple[str, int]:
    """The first paragraph after an item heading, and where to resume."""
    i, buffer = inicio, []
    while i < len(linhas):
        s = linhas[i].strip()
        if not s:
            if buffer:
                break
            i += 1
            continue
        if s.startswith(("#", "|", "```", "- ", "* ")):
            break
        buffer.append(s)
        i += 1
    return " ".join(buffer), i
