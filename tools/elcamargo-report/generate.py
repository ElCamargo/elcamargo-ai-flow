#!/usr/bin/env python3
"""Render a Markdown report to PDF.

    ~/.cache/elcamargo-flow/venv/bin/python generate.py entrada.md
    ~/.cache/elcamargo-flow/venv/bin/python generate.py entrada.md -o saida.pdf --conferir

`--conferir` renders each page to PNG so the caller can look at the result
before it goes to a person. Layout defects — an orphan heading, a table cut in
half, a widow at the top of a page — are invisible in the source and obvious in
the image. The Linx team pays this bill by rendering; so do we.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from markdown_pdf import ReportError, construir  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))


def carregar_documento() -> dict:
    """The `[documento]` block of the project config, for the house layout."""
    try:
        import config as cfg_mod
        return cfg_mod.obter("documento", {}) or {}
    except Exception as exc:
        raise ReportError(
            "Não consegui ler `[documento]` do config.toml do projeto, que é "
            f"o que preenche cliente, integrantes e classificação: {exc}"
        ) from None


def conferir(pdf: Path, destino: Path | None = None, escala: float = 1.4) -> list[Path]:
    """Render every page to PNG for visual inspection."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ReportError(
            "--conferir precisa de pypdfium2:\n"
            "  ~/.cache/elcamargo-flow/venv/bin/python -m pip install pypdfium2"
        ) from None

    destino = destino or pdf.parent / f"{pdf.stem}-paginas"
    destino.mkdir(parents=True, exist_ok=True)
    documento = pdfium.PdfDocument(str(pdf))
    largura = len(str(len(documento)))
    saidas = []
    for i, pagina in enumerate(documento, 1):
        imagem = pagina.render(scale=escala).to_pil()
        caminho = destino / f"pagina-{i:0{largura}}.png"
        imagem.save(caminho)
        saidas.append(caminho)
    return saidas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="generate.py",
        description="Renderiza um relatório Markdown em PDF.",
    )
    p.add_argument("entrada", type=Path, help="arquivo .md com front matter")
    p.add_argument("-o", "--saida", type=Path, default=None,
                   help="PDF de saída (padrão: mesmo nome, .pdf)")
    p.add_argument("--rodape", default="",
                   help="sobrescreve o rodapé do front matter")
    p.add_argument("--conferir", action="store_true",
                   help="renderiza as páginas em PNG para inspeção visual")
    p.add_argument("--estrito", action="store_true",
                   help="falha se algum caractere não couber na fonte")
    p.add_argument("--padrao", choices=("relatorio", "especificacao"),
                   default=None,
                   help="layout: `relatorio` (interno) ou `especificacao` "
                        "(padrão de documentação Elcamargo). Sem isso, "
                        "decide pelo `tipo_documento` do front matter.")
    p.add_argument("--logo-cliente", default=None,
                   help="logo do cliente na capa; sem isso usa "
                        "documento.logo_cliente do config")
    args = p.parse_args(argv)

    try:
        if not args.entrada.exists():
            raise ReportError(f"Não encontrei {args.entrada}.")

        fonte = args.entrada.read_text(encoding="utf-8")
        padrao = args.padrao or (
            "especificacao"
            if "tipo_documento: especificacao" in fonte.split("---")[1]
            else "relatorio")

        if padrao == "especificacao":
            import specification
            cfg = carregar_documento()
            if not cfg.get("cliente"):
                raise ReportError(
                    "`documento.cliente` não está no config.toml. A capa e a "
                    "página de abertura são endereçadas a ele."
                )
            logo = args.logo_cliente or cfg.get("logo_cliente")
            if logo and not Path(logo).is_absolute():
                # Paths in config.toml are written relative to the project
                # root, not to whatever directory the skill happens to be in.
                import flow_state
                raiz = flow_state.raiz_do_projeto(flow_state.resolve_agents_dir())
                logo = str(raiz / logo)
            doc, perdidos = specification.montar(fonte, cfg, logo)
        else:
            doc, perdidos = construir(fonte, args.rodape)
        saida = args.saida or args.entrada.with_suffix(".pdf")
        saida.parent.mkdir(parents=True, exist_ok=True)
        doc.gerar(str(saida))

        tamanho = saida.stat().st_size
        print(f"{saida}  ({tamanho:,} bytes)".replace(",", "."))

        if perdidos:
            lista = " ".join(sorted(perdidos))
            aviso = (f"aviso: {len(perdidos)} caractere(s) fora da fonte "
                     f"foram aproximados: {lista}")
            print(aviso, file=sys.stderr)
            if args.estrito:
                raise ReportError(
                    "--estrito: corrija os caracteres acima na origem."
                )

        if args.conferir:
            paginas = conferir(saida)
            print(f"{len(paginas)} página(s) renderizada(s) em "
                  f"{paginas[0].parent}")
        return 0

    except ReportError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


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
