#!/usr/bin/env python3
"""Smoke test for the report generator.

    /tmp/venv_report/bin/python test_smoke.py

Renders into a temp directory and inspects the resulting PDF, so it never
writes near the user's real reports.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import style  # noqa: E402
from markdown_pdf import (ReportError, construir, inline,  # noqa: E402
                          sanitizar, separar_front_matter)

falhas: list[str] = []

CABECALHO = """---
titulo: Relatório de teste
objetivo: Verificar o gerador.
conclusao: Funciona.
---
"""


def checar(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


def erra(fn, descricao: str) -> None:
    try:
        fn()
        checar(False, descricao)
    except ReportError:
        checar(True, descricao)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="elcamargo-report-"))
    try:
        print("Front matter")
        erra(lambda: separar_front_matter("# sem front matter"),
             "sem front matter é recusado")
        erra(lambda: separar_front_matter("---\ntitulo: x\n---\ncorpo"),
             "sem objetivo e conclusao é recusado")
        erra(lambda: separar_front_matter("---\ntitulo: x\nobjetivo: y\n"),
             "front matter não fechado é recusado")
        meta, corpo = separar_front_matter(CABECALHO + "corpo")
        checar(meta["titulo"] == "Relatório de teste", "lê o título")
        checar(corpo.strip() == "corpo", "separa o corpo")
        meta, _ = separar_front_matter(
            "---\ntitulo: t\nobjetivo: primeira\n  continuação\n"
            "conclusao: c\n---\n")
        checar(meta["objetivo"] == "primeira continuação",
               "valor continuado em várias linhas")

        print("\nSanitização de caracteres")
        limpo, perdidos = sanitizar("seta → e check ✓ e maior ≥")
        checar("->" in limpo and "OK" in limpo and ">=" in limpo,
               "substitui setas e símbolos por equivalentes ASCII")
        checar(not perdidos, "substituídos não entram na lista de perdidos")
        limpo, perdidos = sanitizar("acentuação çãé e travessão — ok")
        checar(limpo == "acentuação çãé e travessão — ok",
               "acentuação PT-BR e travessão passam intactos")
        checar(not perdidos, "nada perdido em texto PT-BR")
        limpo, perdidos = sanitizar("emoji 🚀 aqui")
        checar("🚀" in perdidos, "caractere fora da fonte é reportado")
        checar("🚀" not in limpo, "e não vai para o PDF virar retângulo preto")

        print("\nMarcação inline")
        checar(inline("**forte**") == "<b>forte</b>", "negrito")
        checar(inline("*fraco*") == "<i>fraco</i>", "itálico")
        checar("Courier" in inline("`cod`"), "código monoespaçado")
        checar(inline("a < b & c") == "a &lt; b &amp; c",
               "escapa caractere de marcação")
        checar(inline("[texto](http://x)") == "texto",
               "link vira só o texto: em papel não há onde clicar")

        print("\nLargura de coluna")
        larguras = style.larguras_por_conteudo(
            [["#", "Descrição bem mais longa que a primeira coluna"],
             ["1", "conteúdo"]], 2)
        checar(larguras[0] < larguras[1],
               "coluna curta fica mais estreita que a longa")
        checar(abs(sum(larguras) - style.LARGURA_UTIL) < 0.5,
               "as larguras somam a largura útil")
        larguras = style.larguras_por_conteudo([["a", "b", "c"]], 3)
        checar(all(l >= 13.9 * 72 / 25.4 for l in larguras),
               "nenhuma coluna fica abaixo do piso")

        print("\nRenderização")
        fonte = CABECALHO.replace("Relatório de teste", "Documento completo") + """
## 1. Seção

Parágrafo com **negrito**, *itálico* e `código`.

| Col | Descrição |
| --- | --- |
| 1 | um |
| 2 | dois |

- item um
- item dois

> [!erro] Um problema
> Primeira linha do parágrafo
> continuação da mesma frase.

```
codigo aqui
```

---

## 2. Outra seção

Fim.
"""
        doc, perdidos = construir(fonte, "rodapé de teste")
        pdf = tmp / "saida.pdf"
        doc.gerar(str(pdf))
        checar(pdf.exists() and pdf.stat().st_size > 2000, "PDF gerado")

        import pypdfium2 as pdfium
        documento = pdfium.PdfDocument(str(pdf))
        checar(len(documento) >= 2, "capa e corpo em páginas separadas")
        texto = "".join(p.get_textpage().get_text_range()
                        for p in documento)
        checar("Objetivo" in texto and "Conclusão" in texto,
               "objetivo e conclusão aparecem antes do corpo")
        checar("continuação da mesma frase" in texto.replace("\r\n", " ")
               .replace("\n", " "),
               "linhas do callout formam um parágrafo só")
        checar("codigo aqui" in texto, "bloco de código renderiza")
        checar("rodapé de teste" in texto, "rodapé aplicado")

        print("\nTítulo órfão")
        # A heading placed just above the page break must travel with its
        # content instead of being stranded at the foot of the page.
        recheio = "\n\n".join(f"Parágrafo de enchimento número {i}." * 3
                              for i in range(28))
        fonte_orfa = (CABECALHO + recheio +
                      "\n\n## Título no limite\n\nConteúdo que o acompanha.\n")
        doc2, _ = construir(fonte_orfa)
        pdf2 = tmp / "orfa.pdf"
        doc2.gerar(str(pdf2))
        d2 = pdfium.PdfDocument(str(pdf2))
        paginas = [p.get_textpage().get_text_range() for p in d2]
        pagina_titulo = next(i for i, t in enumerate(paginas)
                             if "Título no limite" in t)
        checar("Conteúdo que o acompanha" in paginas[pagina_titulo],
               "título e conteúdo caem na mesma página")

        print("\nPadrão Elcamargo")
        import specification
        import elcamargo_standard as pp
        cfg = {
            "cliente": "ClienteTeste", "produto": "Plataforma X",
            "classificacao": "Pública", "classificacao_texto": "Uso público.",
            "fornecedor": {"nome": "Elcamargo",
                           "razao_social": "Elcamargo Soluções em Tecnologia",
                           "cnpj": "00.000.000/0001-00", "endereco": "Rua X"},
            "integrantes": {"cliente": ["Fulano <f@cliente.com>"],
                            "fornecedor": ["Beltrano (PM) <b@exemplo.com>"]},
            "operador": "Sicrano da Silva <s@exemplo.com>",
        }
        fonte_spec = """---
tipo_documento: especificacao-funcional
titulo: Modulo de Teste
gerado_por: elcamargo-business-analysis-reviewer
versoes: 1.0 | 01/01/2026 | Autor | Criacao.; 1.1 | 02/01/2026 |  | Ajuste.
---

Paragrafo de contexto do modulo.

## regras

### RN-01 - Primeira Regra

Texto da primeira regra.

Segundo paragrafo da regra.

## rf

### RF-01 - Primeiro Requisito

Texto do requisito.

## ct

### CT-01 - Primeiro Teste

Validar alguma coisa.

| Cenario | Esperado |
| --- | --- |
| a | b |

## consideracoes

Nada a acrescentar.
"""
        erra(lambda: specification.montar("sem front matter", cfg),
             "especificação sem front matter é recusada")
        erra(lambda: specification.montar("---\nprodutos: x\n---\n", cfg),
             "especificação sem `titulo` é recusada")

        esp, _ = specification.montar(fonte_spec, cfg)
        pdf3 = tmp / "spec.pdf"
        esp.gerar(str(pdf3))
        # 5 KB, e nao 20: o piso antigo contava com a capa ilustrada, e este
        # fork nao tem `assets/`. O que prova o documento sao as afirmacoes de
        # conteudo abaixo; o tamanho so' descarta PDF vazio.
        checar(pdf3.exists() and pdf3.stat().st_size > 5000,
               "especificação gerada")
        d3 = pdfium.PdfDocument(str(pdf3))
        paginas = [p.get_textpage().get_text_range() for p in d3]
        tudo = " ".join(paginas).replace("\n", " ")
        checar(len(d3) >= 5, "capa, abertura, termo, sumário e corpo")
        checar("ClienteTeste" in paginas[1],
               "o cliente do config endereça a abertura")
        checar("Beltrano" in paginas[1], "integrantes vêm do config")
        checar("1.1" in paginas[1], "controle de versões lista as duas versões")
        checar("Confidencialidade" in paginas[2], "termo de confidencialidade")

        # Responsabilidade compartilhada: a skill escreveu, a pessoa revisou,
        # e o documento nomeia os dois.
        abertura = paginas[1].replace("\n", " ")
        checar("Autor" in abertura,
               "uma versão com nome explícito o mantém")
        checar("Sicrano da Silva" in abertura,
               "a versão sem nome é assinada pela pessoa responsável")
        # O nome da skill quebra em duas linhas na coluna estreita; o que
        # importa é que ele esteja lá, não como o PDF o quebrou.
        # Tambem sai a marca de quebra que o reportlab insere no meio da
        # palavra e que o pdfium extrai como U+FFFE: e' decisao de
        # tipografia, nao parte do nome. Ela aparece ou nao conforme o
        # comprimento do nome, entao a asercao nao pode depender dela.
        compacto = "".join(abertura.split()).replace("￾", "-")
        checar("elcamargo-business-analysis-reviewer" in compacto,
               "e também pela skill que a gerou")
        responsabilidade = paginas[2].replace("\n", " ")
        checar("assistência de IA" in responsabilidade
               and "em conjunto" in responsabilidade,
               "a nota de responsabilidade fica na página do termo")
        checar(len(paginas[2]) < len(paginas[1]) * 2,
               "a nota não ganhou uma página só para ela")
        checar("SUMÁRIO" in paginas[3].upper(), "sumário")
        checar("1 Modulo de Teste" in paginas[3].replace("  ", " "),
               "o sumário usa o título do documento na seção 1")
        import re
        rodapes = [re.findall(r"(\d+)\s*de\s*(\d+)", pg) for pg in paginas]
        checar(not rodapes[0], "a capa não é numerada")
        total = len(d3) - 1
        checar(all(r and r[0] == (str(i), str(total))
                   for i, r in enumerate(rodapes[1:], start=1)),
               f"rodapé numera 1..{total} de {total}, sem contar a capa")
        for marcador in ("RN-01", "RF-01", "CT-01"):
            checar(marcador in tudo, f"{marcador} aparece no corpo")
        checar("Cenario" in tudo, "tabela do corpo renderiza")

        print("\nTítulo de seção órfão")
        recheio = "\n\n".join(f"Paragrafo de enchimento {i}." * 4
                               for i in range(26))
        fonte_orfa = fonte_spec.replace("Paragrafo de contexto do modulo.",
                                        recheio)
        esp2, _ = specification.montar(fonte_orfa, cfg)
        pdf4 = tmp / "spec-orfa.pdf"
        esp2.gerar(str(pdf4))
        paginas = [p.get_textpage().get_text_range()
                   for p in pdfium.PdfDocument(str(pdf4))]
        alvo = next((i for i, t in enumerate(paginas)
                     if "REGRAS" in t.upper() and "NEGÓCIO" in t.upper()
                     and i > 3), None)
        checar(alvo is not None and "RN-01" in paginas[alvo],
               "título de seção não fica órfão no rodapé")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


    print("\nFront matter: aspas e bloco YAML nao vazam para o PDF")
    import markdown_pdf as _MP  # noqa: E402
    _obrig = _MP.OBRIGATORIOS
    _MP.OBRIGATORIOS = ("titulo",)
    try:
        meta, _ = _MP.separar_front_matter('---\ntitulo: "Com aspas"\n---\ncorpo\n')
        checar(meta["titulo"] == "Com aspas", "aspas duplas em volta do titulo nao saem na capa")
        meta, _ = _MP.separar_front_matter("---\ntitulo: 'Simples'\n---\ncorpo\n")
        checar(meta["titulo"] == "Simples", "aspas simples tambem")
        meta, _ = _MP.separar_front_matter("---\ntitulo: Sem aspas\n---\ncorpo\n")
        checar(meta["titulo"] == "Sem aspas", "e valor sem aspas nao perde letra")
        meta, _ = _MP.separar_front_matter(
            "---\ntitulo: T\nobjetivo: >\n  Primeira linha\n  segunda\n---\ncorpo\n")
        checar(meta["objetivo"] == "Primeira linha segunda", "`>` do YAML e' indicador de bloco, nao a primeira letra do texto")
        meta, _ = _MP.separar_front_matter("---\ntitulo: T\nnota: 3 > 2\n---\ncorpo\n")
        checar(meta["nota"] == "3 > 2", "mas `>` no meio do valor continua sendo texto")
    finally:
        _MP.OBRIGATORIOS = _obrig

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Tudo passou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
