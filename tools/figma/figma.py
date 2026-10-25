#!/usr/bin/env python3
"""Leitura do Figma pela API REST, em camadas e barata.

Por que REST e não MCP: a API `GET` **não consegue escrever**. Num arquivo da
empresa, com gente trabalhando dentro, essa garantia vale mais que qualquer
conveniência. E não é teoria — na primeira tentativa de renomear um arquivo
pelo editor, um duplo clique que não pegou fez o texto digitado virar atalhos
de teclado na tela de desenho. Nada foi criado porque o arquivo era vazio e
meu; noutro arquivo teria sido diferente.

O segundo motivo é custo. Um arquivo de design inteiro em JSON são megabytes.
Esta ferramenta lê em camadas:

    projetos   lista os arquivos de uma pasta — sem abrir nenhum
    paginas    só as páginas de um arquivo (profundidade 1)
    comentarios  os comentários — num projeto real, requisito
    arvore     um nó, na profundidade que você pedir
    resumo     o que o step 6 precisa: telas, textos, cores, componentes
    imagem     PNG de um nó, para ler o que o JSON não conta

Comece sempre pelo mais raso. Descer direto na árvore inteira gasta em uma
chamada o que a atividade toda deveria gastar.

    python3 figma.py projetos 251745185
    python3 figma.py paginas <chave>
    python3 figma.py resumo <chave> --no 12:345
    python3 figma.py imagem <chave> --no 12:345 --saida tela.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.figma.com"
CAMINHO_TOKEN = Path.home() / ".config" / "elcamargo-flow" / "figma-token"
LIMITE_RESUMO = 400


class FigmaError(Exception):
    pass


def token() -> str:
    """O token, do ambiente ou do arquivo dedicado. Nunca de dentro do repositório."""
    valor = os.environ.get("FIGMA_TOKEN", "").strip()
    if valor:
        return valor
    if CAMINHO_TOKEN.exists():
        modo = oct(CAMINHO_TOKEN.stat().st_mode)[-3:]
        if modo != "600":
            raise FigmaError(
                f"{CAMINHO_TOKEN} está com permissão {modo}. Um token legível por "
                f"outros não serve.\n  Corrija:  chmod 600 {CAMINHO_TOKEN}"
            )
        valor = CAMINHO_TOKEN.read_text(encoding="utf-8").strip()
        if valor:
            return valor
    raise FigmaError(
        "não achei o token do Figma.\n"
        "  Gere um em Figma > Settings > Security > Personal access tokens,\n"
        "  com escopo de LEITURA de conteúdo de arquivo, e guarde assim — o\n"
        "  comando não ecoa o valor na tela nem no histórico:\n\n"
        f"    mkdir -p {CAMINHO_TOKEN.parent} && printf 'Cole o token: ' && \\\n"
        f"      read -rs T && printf '%s' \"$T\" > {CAMINHO_TOKEN} && \\\n"
        f"      chmod 600 {CAMINHO_TOKEN} && unset T\n"
    )


def pedir(caminho: str, parametros: dict | None = None) -> dict:
    url = f"{API}{caminho}"
    if parametros:
        url += "?" + urllib.parse.urlencode(parametros)
    req = urllib.request.Request(url, headers={"X-Figma-Token": token()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 1200, não 300: a resposta do Figma diz QUAL escopo falta, e essa
        # frase vem no fim. Cortar em 300 escondia exatamente a parte acionável
        # e deixava a mensagem com cara de "confira alguma coisa".
        corpo = e.read().decode("utf-8", "replace")[:1200]
        if e.code == 403:
            raise FigmaError(
                f"403 do Figma. O token não alcança este recurso.\n  {corpo}\n\n"
                "  A resposta acima nomeia o escopo que falta. Escopo se marca ao\n"
                "  GERAR o token — não dá para acrescentar depois; é gerar outro."
            )
        if e.code == 404:
            raise FigmaError(f"404: chave ou nó inexistente.\n  {corpo}")
        if e.code == 429:
            raise FigmaError("429: limite de chamadas atingido. Espere antes de insistir.")
        raise FigmaError(f"HTTP {e.code}: {corpo}")
    except urllib.error.URLError as e:
        raise FigmaError(f"não consegui falar com a API do Figma: {e.reason}")


# --------------------------------------------------------------------------
def cmd_projetos(args) -> int:
    dados = pedir(f"/v1/projects/{args.projeto}/files")
    arquivos = dados.get("files", [])
    if not arquivos:
        raise FigmaError(f"a pasta {args.projeto} não devolveu nenhum arquivo")
    print(f"Pasta {args.projeto} — {len(arquivos)} arquivo(s)")
    print()
    print(f"  {'chave':<24} {'modificado em':<22} nome")
    for f in sorted(arquivos, key=lambda x: x.get("last_modified", ""), reverse=True):
        print(f"  {f.get('key',''):<24} {f.get('last_modified','')[:19]:<22} {f.get('name','')}")
    print()
    print("Nenhum arquivo foi aberto para montar esta lista.")
    return 0


def cmd_paginas(args) -> int:
    dados = pedir(f"/v1/files/{args.chave}", {"depth": 1})
    doc = dados.get("document", {})
    paginas = doc.get("children", [])
    print(f"Arquivo   {dados.get('name','?')}")
    print(f"Versão    {dados.get('version','?')}   modificado {dados.get('lastModified','?')[:19]}")
    print(f"Páginas   {len(paginas)}")
    print()
    for p in paginas:
        print(f"  {p.get('id',''):<12} {p.get('name','')}")
    print()
    print("Profundidade 1: só as páginas. Para descer, use `arvore` ou `resumo`")
    print("com o id de uma página — nunca o arquivo inteiro.")
    return 0


def cmd_comentarios(args) -> int:
    """Os comentários do arquivo.

    Numa spec real deste projeto, nove comentários do UX foram tratados como
    REQUISITO — "comentários do UX considerados como requisito: #34, #35, …".
    Uma leitura de Figma que ignora os comentários perde a metade da conversa:
    o desenho mostra o quê, e o comentário costuma explicar o porquê e o que
    ficou pendente.
    """
    dados = pedir(f"/v1/files/{args.chave}/comments")
    fios = dados.get("comments", [])
    if not fios:
        print("Nenhum comentário neste arquivo.")
        return 0

    # Resposta vem achatada: cada item traz parent_id quando é resposta.
    raizes = [c for c in fios if not c.get("parent_id")]
    respostas: dict[str, list] = {}
    for c in fios:
        if c.get("parent_id"):
            respostas.setdefault(c["parent_id"], []).append(c)

    abertos = [c for c in raizes if not c.get("resolved_at")]
    print(f"# Comentários · {len(raizes)} fio(s), {len(abertos)} em aberto")
    print()
    print("**Comentário do UX costuma ser requisito**, não conversa paralela.")
    print("O desenho mostra o quê; o comentário explica o porquê e o pendente.")
    print()

    for c in sorted(raizes, key=lambda x: x.get("created_at", "")):
        if args.abertos and c.get("resolved_at"):
            continue
        autor = (c.get("user") or {}).get("handle", "?")
        quando = (c.get("created_at") or "")[:10]
        estado = "resolvido" if c.get("resolved_at") else "ABERTO"
        ancora = ""
        meta = c.get("client_meta") or {}
        if isinstance(meta, dict) and meta.get("node_id"):
            ancora = f"  no nó `{meta['node_id']}`"
        print(f"### #{c.get('order_id','?')} · {estado} · {autor} · {quando}{ancora}")
        print()
        for linha in (c.get("message") or "").splitlines():
            print(f"> {linha}")
        for r in sorted(respostas.get(c["id"], []), key=lambda x: x.get("created_at", "")):
            ra = (r.get("user") or {}).get("handle", "?")
            print(f">")
            print(f"> **{ra}:** {' '.join((r.get('message') or '').split())}")
        print()
    return 0


def cmd_arvore(args) -> int:
    dados = pedir(f"/v1/files/{args.chave}/nodes",
                  {"ids": args.no, "depth": args.profundidade})
    print(json.dumps(dados, ensure_ascii=False, indent=2)[:args.limite])
    return 0


# --------------------------------------------------------------------------
def cor(pintura: list | None) -> str:
    if not pintura:
        return ""
    for p in pintura:
        if p.get("type") == "SOLID" and p.get("visible", True):
            c = p.get("color", {})
            r, g, b = (round(c.get(k, 0) * 255) for k in ("r", "g", "b"))
            a = p.get("opacity", c.get("a", 1))
            return f"#{r:02X}{g:02X}{b:02X}" + ("" if a >= 1 else f" @{a:.2f}")
    return ""


def andar(no: dict, saida: list, nivel: int = 0, limite: int = LIMITE_RESUMO) -> None:
    if len(saida) >= limite:
        return
    tipo = no.get("type", "")
    nome = no.get("name", "")
    caixa = no.get("absoluteBoundingBox") or {}
    dim = ""
    if caixa:
        dim = f"{round(caixa.get('width',0))}×{round(caixa.get('height',0))}"
    detalhe = []
    if tipo == "TEXT" and no.get("characters"):
        texto = " ".join(no["characters"].split())
        detalhe.append(f'"{texto[:80]}"')
    preenchimento = cor(no.get("fills"))
    if preenchimento and tipo != "TEXT":
        detalhe.append(preenchimento)
    if no.get("componentId"):
        detalhe.append("instância")
    linha = f"{'  ' * nivel}{tipo:<10} {nome[:40]:<40} {dim:<10} {' '.join(detalhe)}"
    saida.append(linha.rstrip())
    for filho in no.get("children", []):
        andar(filho, saida, nivel + 1, limite)


def cmd_resumo(args) -> int:
    dados = pedir(f"/v1/files/{args.chave}/nodes",
                  {"ids": args.no, "depth": args.profundidade})
    nos = dados.get("nodes", {})
    if not nos:
        raise FigmaError(f"o nó {args.no} não existe neste arquivo")
    print(f"# Resumo · {dados.get('name','?')}")
    print()
    print("Extraído por leitura da API, sem abrir o editor. **É índice, não")
    print("evidência**: confirme na imagem o que for decidir a partir daqui.")
    print()
    for ident, envelope in nos.items():
        doc = envelope.get("document", {})
        print(f"## {doc.get('name','?')}  `{ident}`")
        print()
        linhas: list[str] = []
        andar(doc, linhas, 0, args.limite_nos)
        print("```")
        for l in linhas:
            print(l)
        print("```")
        if len(linhas) >= args.limite_nos:
            print()
            print(f"**Cortado em {args.limite_nos} nós.** O que não apareceu NÃO está")
            print("aqui — desça por um nó filho em vez de aumentar o limite.")
        print()
    return 0


def cmd_imagem(args) -> int:
    dados = pedir(f"/v1/images/{args.chave}",
                  {"ids": args.no, "format": args.formato, "scale": args.escala})
    if dados.get("err"):
        raise FigmaError(f"o Figma recusou a renderização: {dados['err']}")
    urls = dados.get("images", {})
    destino = Path(args.saida).expanduser()
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritos = []
    for ident, url in urls.items():
        if not url:
            print(f"aviso: o nó {ident} não rendeu imagem", file=sys.stderr)
            continue
        with urllib.request.urlopen(url, timeout=120) as r:
            dados_img = r.read()
        alvo = destino if len(urls) == 1 else destino.with_name(
            f"{destino.stem}-{ident.replace(':', '-')}{destino.suffix}")
        alvo.write_bytes(dados_img)
        escritos.append((alvo, len(dados_img)))
    if not escritos:
        raise FigmaError("nenhuma imagem foi gerada")
    for alvo, tamanho in escritos:
        print(f"{alvo}  ({tamanho // 1024} KB)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="figma", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("projetos", help="lista os arquivos de uma pasta, sem abrir nenhum")
    a.add_argument("projeto")
    a.set_defaults(func=cmd_projetos)

    b = sub.add_parser("paginas", help="só as páginas de um arquivo")
    b.add_argument("chave")
    b.set_defaults(func=cmd_paginas)

    k = sub.add_parser("comentarios", help="os comentários — costumam ser requisito")
    k.add_argument("chave")
    k.add_argument("--abertos", action="store_true", help="só os não resolvidos")
    k.set_defaults(func=cmd_comentarios)

    c = sub.add_parser("arvore", help="JSON cru de um nó")
    c.add_argument("chave")
    c.add_argument("--no", required=True)
    c.add_argument("--profundidade", type=int, default=2)
    c.add_argument("--limite", type=int, default=40_000)
    c.set_defaults(func=cmd_arvore)

    d = sub.add_parser("resumo", help="o que o step 6 precisa, em markdown")
    d.add_argument("chave")
    d.add_argument("--no", required=True)
    d.add_argument("--profundidade", type=int, default=6)
    d.add_argument("--limite-nos", type=int, default=LIMITE_RESUMO)
    d.set_defaults(func=cmd_resumo)

    e = sub.add_parser("imagem", help="PNG de um nó")
    e.add_argument("chave")
    e.add_argument("--no", required=True)
    e.add_argument("--saida", required=True)
    e.add_argument("--formato", default="png", choices=["png", "jpg", "svg", "pdf"])
    e.add_argument("--escala", default="2")
    e.set_defaults(func=cmd_imagem)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except FigmaError as exc:
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
