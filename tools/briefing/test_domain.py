#!/usr/bin/env python3
"""Teste de fumaça do mapa do terreno."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import domain as D  # noqa: E402
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
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def montar() -> Path:
    r = Path(tempfile.mkdtemp(prefix="dominio-teste-"))
    (r / "src" / "entities").mkdir(parents=True)
    (r / "src" / "migrations").mkdir(parents=True)
    (r / "docs" / "adr").mkdir(parents=True)
    (r / "src" / "entities" / "catalog-item.entity.ts").write_text(
        "@Entity('catalog_items')\n"
        "export class CatalogItemEntity {\n"
        "  @PrimaryGeneratedColumn('uuid')\n"
        "  id!: string;\n"
        "  @Column({ name: 'client_id', type: 'uuid' })\n"
        "  clientId!: string;\n"
        "}\n", encoding="utf-8")
    (r / "src" / "migrations" / "1000-Base.ts").write_text(
        "await q.query(`CREATE TABLE public.catalog_items (id uuid)`);\n"
        "await q.query('CREATE UNIQUE INDEX ci_uq ON public.catalog_items(client_id, lower(name))');\n"
        "await q.query('CREATE TABLE public.unrelated (id uuid)');\n", encoding="utf-8")
    (r / "src" / "grupos.controller.ts").write_text(
        "@Controller('catalog-items')\n"
        "export class GruposController {\n"
        "  @Get()\n  list() {}\n"
        "  @Patch(':id')\n  rename() {}\n"
        "}\n", encoding="utf-8")
    (r / "src" / "grupos.service.ts").write_text(
        "export class CatalogItemsService {\n"
        "  async list(clientId: string): Promise<Item[]> {}\n"
        "  private async helper(): Promise<void> {}\n"
        "  async rename(id: string): Promise<void> {\n"
        "    throw new ConflictException({ code: 'CATALOG_ITEM_NAME_TAKEN' });\n"
        "  }\n"
        "}\n", encoding="utf-8")
    (r / "docs" / "adr" / "0001-catalog-item.md").write_text("ADR sobre catalogItem\n",
                                                               encoding="utf-8")
    sh("git", "init", "-q", "-b", "main", cwd=r)
    sh("git", "config", "user.email", "t@t", cwd=r)
    sh("git", "config", "user.name", "t", cwd=r)
    sh("git", "add", "-A", cwd=r)
    sh("git", "commit", "-qm", "base", cwd=r)
    return r


def rodar(raiz: Path, **kw):
    class Args:
        termo = "catalog item"
        pasta = None
        saida = None
    for k, v in kw.items():
        setattr(Args, k, v)
    anterior = Path.cwd()
    os.chdir(raiz)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            D.principal(Args())
        return buf.getvalue()
    finally:
        os.chdir(anterior)


# --------------------------------------------------------------------------
print("Formas do termo")
# --------------------------------------------------------------------------
formas = D.termos("catalog item")
ok("CatalogItem" in formas and "catalogItem" in formas
   and "catalog_item" in formas and "catalog-item" in formas,
   "gera camelCase, PascalCase, snake_case e kebab-case", f"{formas}")
ok("catalog" not in formas,
   "NÃO inclui a primeira palavra sozinha — foi o que inflou o mapa para 42 KB",
   f"{formas}")
ok(D.alargar("catalog item") == ["catalog"], "o alargamento existe, separado")

# --------------------------------------------------------------------------
print("\nMapa de um domínio real")
# --------------------------------------------------------------------------
raiz = montar()
saida = rodar(raiz)
ok("catalog-item.entity.ts" in saida, "acha a entidade")
ok("clientId: string" in saida, "extrai a coluna com o decorator")
ok("GET    /catalog-items" in saida and "PATCH  /catalog-items/:id" in saida,
   "monta a rota juntando @Controller e @Get", saida)
ok("list(clientId: string)" in saida, "lista método público")
ok("helper" not in saida, "e não lista método privado", saida)
ok("CATALOG_ITEM_NAME_TAKEN" in saida, "coleta o código de erro do domínio")

# --------------------------------------------------------------------------
print("\nMigration: só o SQL que toca o domínio")
# --------------------------------------------------------------------------
ok("lower(name)" in saida, "traz o índice único com lower(name)")
ok("public.unrelated" not in saida,
   "e não traz SQL de tabela que não é do domínio", saida)

# --------------------------------------------------------------------------
print("\nA base")
# --------------------------------------------------------------------------
ok("Branch de trabalho" in saida and "Branch padrão" in saida,
   "declara a branch de trabalho e a padrão")

sh("git", "checkout", "-qb", "feature", cwd=raiz)
(raiz / "src" / "novo-catalog-item.ts").write_text("// catalogItem\n", encoding="utf-8")
sh("git", "add", "-A", cwd=raiz)
sh("git", "commit", "-qm", "avanca", cwd=raiz)
saida2 = rodar(raiz)
ok("1 commits à frente" in saida2,
   "mede a distância até a branch padrão — a base que a análise pressupõe", saida2)

# --------------------------------------------------------------------------
print("\nAlargamento é declarado, nunca silencioso")
# --------------------------------------------------------------------------
saida3 = rodar(raiz, termo="catalog inexistente")
ok("alargada" in saida3.lower(), "avisa que alargou o termo", saida3[:300])
ok("mais largo que o assunto" in saida3, "e diz o que isso custa")

# --------------------------------------------------------------------------
print("\nRecusas e limites")
# --------------------------------------------------------------------------
def erro(fn, trecho):
    try:
        fn()
        return False, "não levantou"
    except B.BriefingError as e:
        return trecho.lower() in str(e).lower(), str(e)

cond, msg = erro(lambda: rodar(raiz, termo="xyzzy plugh"), "nenhum arquivo cita")
ok(cond, "termo sem nenhuma ocorrência recusa em vez de entregar mapa vazio", msg)
cond, msg = erro(lambda: D.termos("   "), "vazio")
ok(cond, "termo em branco recusa", msg)

# --------------------------------------------------------------------------
print("\nO mapa não julga e declara o que não cobre")
# --------------------------------------------------------------------------
proibidas = ["deveria", "recomend", "risco", "problema", "melhor seria"]
corpo = saida.lower().split("## a base", 1)[-1]
ok(not [p for p in proibidas if p in corpo], "sem vocabulário de julgamento")
ok("um índice, não evidência" in saida, "declara que é índice, não evidência")
ok("O que este mapa não cobre" in saida, "e enumera os próprios limites")

print()
if falhas:
    print(f"{falhas} FALHA(S)")
    sys.exit(1)
print("tudo passou")
