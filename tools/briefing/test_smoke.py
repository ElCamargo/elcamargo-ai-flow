#!/usr/bin/env python3
"""Teste de fumaça do dossiê. Repositório git de verdade, em temporário."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import briefing as B  # noqa: E402

falhas = 0


def ok(cond, rotulo, detalhe=""):
    global falhas
    if cond:
        print(f"  [ok] {rotulo}")
    else:
        falhas += 1
        print(f"  [XX] {rotulo}" + (f"\n       {detalhe}" if detalhe else ""))


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def montar() -> Path:
    r = Path(tempfile.mkdtemp(prefix="briefing-teste-"))
    sh("git", "init", "-q", "-b", "main", cwd=r)
    sh("git", "config", "user.email", "t@t", cwd=r)
    sh("git", "config", "user.name", "t", cwd=r)
    (r / "src").mkdir()
    (r / "src" / "servico.ts").write_text(
        "export class Servico {\n"
        "  async listar(): Promise<void> {}\n"
        "}\n", encoding="utf-8")
    (r / "src" / "chamador.ts").write_text(
        "import { Servico } from './servico';\n"
        "new Servico().listar();\n", encoding="utf-8")
    # Documento e tradução citam o nome sem serem chamadores.
    (r / "doc.md").write_text("Este documento fala de listar e renomear.\n",
                              encoding="utf-8")
    (r / "trad.json").write_text('{"renomear": "x", "listar": "y"}\n', encoding="utf-8")
    sh("git", "add", "-A", cwd=r)
    sh("git", "commit", "-qm", "base", cwd=r)
    return r


def rodar(raiz: Path, **kw):
    class Args:
        base = "main"
        saida = None
    for k, v in kw.items():
        setattr(Args, k, v)
    anterior = Path.cwd()
    os.chdir(raiz)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            B.principal(Args())
        return buf.getvalue()
    finally:
        os.chdir(anterior)


# --------------------------------------------------------------------------
print("Regressão: trabalho não commitado")
# --------------------------------------------------------------------------
raiz = montar()
alvo = raiz / "src" / "servico.ts"
alvo.write_text(
    "export class Servico {\n"
    "  async listar(): Promise<void> {}\n"
    "  async renomear(id: string): Promise<void> {\n"
    "    const linhas = await this.repo.find();\n"
    "    const resumo = linhas.length;\n"
    "  }\n"
    "}\n", encoding="utf-8")
saida = rodar(raiz)
ok("renomear" in saida, "método novo ainda não commitado aparece no dossiê")
ok("```diff" in saida and "async renomear" in saida, "o diff mostra a alteração solta")
ok("fora do commit" in saida, "o dossiê declara que a árvore está suja")

# --------------------------------------------------------------------------
print("\nRegressão: variável local não é símbolo")
# --------------------------------------------------------------------------
ok("**`linhas`**" not in saida and "**`resumo`**" not in saida,
   "const dentro de método não vira símbolo de API", saida[:200])
ok("**`renomear`**" in saida, "assinatura de método vira símbolo")

# --------------------------------------------------------------------------
print("\nRegressão: arquivo não rastreado")
# --------------------------------------------------------------------------
(raiz / "src" / "novo.ts").write_text("export const NOVO = 1;\n", encoding="utf-8")
saida = rodar(raiz)
ok("src/novo.ts" in saida, "arquivo não rastreado aparece na tabela")
ok("não aparecem no diff" in saida.lower(),
   "e o dossiê avisa que ele não está no diff, em vez de omitir em silêncio")

# --------------------------------------------------------------------------
print("\nQuem referencia")
# --------------------------------------------------------------------------
# `listar` mudou de assinatura, e src/chamador.ts a chama.
alvo.write_text(
    "export class Servico {\n"
    "  async listar(pagina: number): Promise<void> {}\n"
    "  async renomear(id: string): Promise<void> {\n"
    "    const linhas = await this.repo.find();\n"
    "  }\n"
    "}\n", encoding="utf-8")
saida = rodar(raiz)
ok("src/chamador.ts" in saida, "o chamador de um símbolo tocado é listado", saida)
ok("doc.md" not in saida and "trad.json" not in saida,
   "markdown e json citando o nome não contam como chamador", saida)

# --------------------------------------------------------------------------
print("\nO dossiê não julga")
# --------------------------------------------------------------------------
proibidas = ["problema", "risco", "atenção:", "cuidado", "suspeito", "bug",
             "vulnerabil", "recomend", "deveria", "gravidade", "severidade"]
corpo = saida.lower().split("## contexto", 1)[-1]
achadas = [p for p in proibidas if p in corpo]
ok(not achadas, "nenhum vocabulário de julgamento no dossiê", f"achou {achadas}")
ok("não há nenhum achado aqui" in saida.lower(), "e ele declara isso ao leitor")

# --------------------------------------------------------------------------
print("\nRecusas")
# --------------------------------------------------------------------------
def erro(fn, trecho):
    try:
        fn()
        return False, "não levantou"
    except B.BriefingError as e:
        return trecho.lower() in str(e).lower(), str(e)

limpo = montar()
cond, msg = erro(lambda: rodar(limpo), "nenhum arquivo mudou")
ok(cond, "diff vazio recusa em vez de produzir dossiê de nada", msg)

cond, msg = erro(lambda: rodar(raiz, base="nao-existe"), "não achei a base")
ok(cond, "base inexistente recusa e sugere as que existem", msg)

fora = Path(tempfile.mkdtemp(prefix="sem-git-"))
anterior = Path.cwd()
os.chdir(fora)
try:
    cond, msg = erro(lambda: B.raiz_de_trabalho(), "repositório git")
    ok(cond, "fora de repositório git recusa", msg)
finally:
    os.chdir(anterior)

# --------------------------------------------------------------------------
print("\nTruncagem é declarada")
# --------------------------------------------------------------------------
grande = montar()
sh("git", "checkout", "-qb", "trabalho", cwd=grande)
(grande / "src" / "grande.ts").write_text(
    "\n".join(f"export const N{i} = {i};" for i in range(B.LIMITE_DIFF + 200)),
    encoding="utf-8")
sh("git", "add", "-A", cwd=grande)
sh("git", "commit", "-qm", "arquivo grande", cwd=grande)
saida = rodar(grande)
ok("Truncado" in saida, "diff acima do limite avisa que foi truncado")
ok("Não conclua nada sobre o" in saida, "e instrui a não concluir sobre o que não viu")

print()
if falhas:
    print(f"{falhas} FALHA(S)")
    sys.exit(1)
print("tudo passou")
