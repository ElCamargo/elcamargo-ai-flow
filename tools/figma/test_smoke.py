#!/usr/bin/env python3
"""Teste de fumaça do leitor de Figma. Sem rede: só o que é lógica local."""
from __future__ import annotations

import contextlib
import io
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import figma as F  # noqa: E402

falhas = 0


def ok(cond, rotulo, detalhe=""):
    global falhas
    if cond:
        print(f"  [ok] {rotulo}")
    else:
        falhas += 1
        print(f"  [XX] {rotulo}" + (f"\n       {detalhe}" if detalhe else ""))


def erro(fn, trecho):
    try:
        fn()
        return False, "não levantou"
    except F.FigmaError as e:
        return trecho.lower() in str(e).lower(), str(e)


# --------------------------------------------------------------------------
print("O token nunca vem do repositório")
# --------------------------------------------------------------------------
tmp = Path(tempfile.mkdtemp(prefix="figma-teste-"))
original_caminho = F.CAMINHO_TOKEN
original_env = os.environ.get("FIGMA_TOKEN")

try:
    F.CAMINHO_TOKEN = tmp / "ausente"
    os.environ.pop("FIGMA_TOKEN", None)
    cond, msg = erro(F.token, "não achei o token")
    ok(cond, "sem token, recusa e ensina a guardar sem ecoar", msg[:60])
    ok("read -rs" in msg, "e a instrução usa read -rs, que não ecoa nem grava no histórico")

    os.environ["FIGMA_TOKEN"] = "figd_do_ambiente"
    ok(F.token() == "figd_do_ambiente", "o ambiente tem precedência")
    os.environ.pop("FIGMA_TOKEN")

    frouxo = tmp / "frouxo"
    frouxo.write_text("figd_qualquer")
    frouxo.chmod(0o644)
    F.CAMINHO_TOKEN = frouxo
    cond, msg = erro(F.token, "permissão 644")
    ok(cond, "token legível por outros é recusado", msg[:70])
    ok("chmod 600" in msg, "e a mensagem traz o comando exato da correção")

    frouxo.chmod(0o600)
    ok(F.token() == "figd_qualquer", "com 600, lê normalmente")

    sujo = tmp / "sujo"
    sujo.write_text("  figd_com_espaco\n\n")
    sujo.chmod(0o600)
    F.CAMINHO_TOKEN = sujo
    ok(F.token() == "figd_com_espaco", "espaço e quebra de linha em volta são removidos")

    vazio = tmp / "vazio"
    vazio.write_text("   \n")
    vazio.chmod(0o600)
    F.CAMINHO_TOKEN = vazio
    cond, _ = erro(F.token, "não achei o token")
    ok(cond, "arquivo existente mas vazio conta como ausente")
finally:
    F.CAMINHO_TOKEN = original_caminho
    if original_env is None:
        os.environ.pop("FIGMA_TOKEN", None)
    else:
        os.environ["FIGMA_TOKEN"] = original_env

# --------------------------------------------------------------------------
print("\nExtração de cor")
# --------------------------------------------------------------------------
ok(F.cor([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0}}]) == "#FF0000",
   "sólido vira hexadecimal")
ok(F.cor([{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0}, "opacity": 0.5}])
   == "#000000 @0.50", "opacidade aparece quando não é 1")
ok(F.cor([{"type": "SOLID", "visible": False, "color": {"r": 1, "g": 1, "b": 1}},
          {"type": "SOLID", "color": {"r": 0, "g": 1, "b": 0}}]) == "#00FF00",
   "preenchimento invisível é pulado")
ok(F.cor([{"type": "GRADIENT_LINEAR"}]) == "", "gradiente não vira cor sólida falsa")
ok(F.cor(None) == "" and F.cor([]) == "", "ausência de preenchimento não quebra")

# --------------------------------------------------------------------------
print("\nCaminhada pela árvore")
# --------------------------------------------------------------------------
arvore = {
    "type": "CANVAS", "name": "Pedidos",
    "children": [
        {"type": "FRAME", "name": "Painel", "absoluteBoundingBox": {"width": 1440.4, "height": 1024},
         "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1}}],
         "children": [
             {"type": "TEXT", "name": "titulo",
              "characters": "Painel   de\nPedidos", "fills": []},
             {"type": "INSTANCE", "name": "Botao", "componentId": "1:2"},
         ]},
    ],
}
linhas: list[str] = []
F.andar(arvore, linhas)
texto = "\n".join(linhas)
ok("1440×1024" in texto, "dimensão é arredondada e legível", texto)
ok('"Painel de Pedidos"' in texto,
   "o texto do nó é normalizado numa linha só", texto)
ok("instância" in texto, "instância de componente é marcada", texto)
ok("#FFFFFF" in texto, "a cor do frame aparece", texto)
ok(texto.count("\n") == 3, "um nó por linha, nada duplicado", texto)

fundo = {"type": "FRAME", "name": "raiz", "children": [
    {"type": "FRAME", "name": f"n{i}", "children": []} for i in range(50)]}
curtas: list[str] = []
F.andar(fundo, curtas, limite=10)
ok(len(curtas) <= 11, "o limite de nós é respeitado", f"{len(curtas)} linhas")

# --------------------------------------------------------------------------
print("\nA saída avisa quando corta")
# --------------------------------------------------------------------------
fonte = Path(F.__file__).read_text(encoding="utf-8")
ok("O que não apareceu NÃO está" in fonte,
   "o resumo declara que o cortado não está lá, em vez de deixar parecer completo")
ok("é índice, não" in fonte or "índice, não" in fonte,
   "e declara que é índice, não evidência")

# --------------------------------------------------------------------------
print("\nErros da API traduzidos")
# --------------------------------------------------------------------------
for codigo, esperado in ((403, "escopo"), (404, "inexistente"), (429, "limite")):
    ok(f"e.code == {codigo}" in fonte or f"{codigo}:" in fonte,
       f"HTTP {codigo} tem tratamento próprio ({esperado})")
ok("[:1200]" in fonte,
   "o corpo do erro não é cortado em 300 — a frase que nomeia o escopo vem no fim")

print()
if falhas:
    print(f"{falhas} FALHA(S)")
    sys.exit(1)
print("tudo passou")
