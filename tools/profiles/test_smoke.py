#!/usr/bin/env python3
"""Fumaca de profiles.py — e os falsos que a calibracao derrubou.

A deteccao de superficie errou uma vez contra um diff real: metade dos arquivos
acusados eram `.md`. Uma especificacao que DESCREVE a regra de permissao casa com
todos os padroes e nao enforca coisa nenhuma. Esse caso virou teste negativo
permanente, junto com os arquivos de teste.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles as P  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class Args:
    def __init__(self, **kw):
        self.__dict__.setdefault("config", "")
        self.__dict__.setdefault("raiz", ".")
        self.__dict__.setdefault("registrar", "")
        self.__dict__.update(kw)


def diff(arquivo: str, *linhas: str) -> str:
    return f"+++ b/{arquivo}\n" + "".join(f"+{l}\n" for l in linhas)


def superficie(texto: str) -> tuple[int, str]:
    buf, antigo = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(texto)
    try:
        with contextlib.redirect_stdout(buf):
            codigo = P.cmd_superficie(Args(base="-", raiz="."))
    finally:
        sys.stdin = antigo
    return codigo, buf.getvalue()


CABECA = "| Perfil | Ação | Esperado | Observado |\n| --- | --- | --- | --- |\n"


def conferir(corpo: str, tmp: Path, config: str = "") -> tuple[int, str]:
    alvo = tmp / "relatorio.md"
    alvo.write_text(corpo, encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = P.cmd_conferir(Args(relatorio=str(alvo), config=config))
    return codigo, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="perfis-"))

    # ----------------------------------------------------------------
    print("\nSuperficie de autorizacao: o que ela PRECISA pegar")
    for arquivo, linha, rotulo in [
        ("a/api/x.controller.ts", "  @RequirePermissions('faq.read')", "chave por rota"),
        ("a/api/x.controller.ts", "@UseGuards(JwtAuthGuard, PermsGuard)", "pilha de guardas"),
        ("a/libs/g.guard.ts", "export class G implements CanActivate {", "guarda nova"),
        ("a/web/shell.tsx", "  const pode = session.user.globalPermissions.includes('x');", "permissao global"),
        ("a/web/shell.tsx", "  const canSeeFaq = perms.includes('faq.read');", "visibilidade na tela"),
        ("a/web/y.tsx", "  if (hasPermission('faq.write')) {", "hasPermission"),
    ]:
        codigo, saida = superficie(diff(arquivo, linha))
        ok(codigo == 1 and "OBRIGATÓRIO" in saida, f"pega {rotulo}", saida)

    print("\nO que ela NAO PODE pegar")
    codigo, saida = superficie(diff("a/docs/SPEC-002.md",
                                    "A tela le `globalPermissions` e esconde o botao.",
                                    "@UseGuards(JwtAuthGuard) protege a rota."))
    ok(codigo == 0 and "não toca superfície" in saida,
       "documento descreve permissao e nao decide nada (o falso da 1a calibracao)", saida)

    codigo, saida = superficie(diff("a/api/x.controller.spec.ts",
                                    "    expect(permissionsOf('list')).toEqual(['faq.read']);",
                                    "  const u = { globalPermissions: [] };"))
    ok(codigo == 0 and "rede em volta" in saida,
       "teste que fala de permissao e' a rede, nao a superficie", saida)

    codigo, saida = superficie(diff("a/web/z.tsx", "  if (loading) return <Spinner />;"))
    ok(codigo == 0, "esconder por carregamento nao e' autorizacao", saida)

    codigo, saida = superficie(diff("a/api/x.controller.ts", "  @RequirePermissions('faq.read')")
                               + diff("a/api/x.controller.spec.ts", "  globalPermissions: []"))
    ok(codigo == 1 and "1 arquivo(s)" in saida and "1 arquivo(s) de teste" in saida,
       "producao e teste no mesmo diff sao contados separados", saida)

    # ----------------------------------------------------------------
    print("\nA regra que faz a matriz valer: toda negacao precisa de um par")
    codigo, saida = conferir(CABECA + (
        "| somente-leitura | editar categoria | negado | botão ausente; PATCH direto → 403 |\n"
        "| somente-leitura | excluir categoria | negado | ação ausente no menu |\n"), tmp)
    ok(codigo == 1 and "só provou o que NÃO pode" in saida,
       "perfil com duas negacoes e nenhuma permissao reprova", saida)
    ok("conta quebrada" in saida, "e explica por que isso nao e' evidencia", saida)

    codigo, saida = conferir(CABECA + (
        "| somente-leitura | listar FAQ | permitido | 200, seis categorias na tela |\n"
        "| somente-leitura | editar categoria | negado | botão ausente; PATCH direto → 403 |\n"), tmp)
    ok(codigo == 0 and "com par" in saida,
       "o mesmo ator provando que consegue algo fecha o par", saida)

    # ----------------------------------------------------------------
    print("\nObservado vazio, e observado que confessa nao ter medido")
    codigo, saida = conferir(CABECA + (
        "| master | criar categoria | permitido | |\n"), tmp)
    ok(codigo == 1 and "sem o que foi observado" in saida,
       "Esperado sem Observado e' hipotese, nao medicao", saida)

    codigo, saida = conferir(CABECA + (
        "| master | criar categoria | permitido | 201, categoria na lista |\n"
        "| master | excluir sem chave | negado | não consegui entrar com esse ator |\n"), tmp)
    ok(codigo == 1 and "confessa que não mediu" in saida,
       "'nao consegui' e' dimensao nao coberta, nao prova", saida)
    ok("não é achado" in saida, "e a ferramenta diz o que fazer com ela", saida)

    print("\nAs duas armadilhas de portugues")
    codigo, saida = conferir(CABECA + (
        "| master | listar | permitido | 200, seis categorias na tela |\n"
        "| master | ver menu | permitido | todo o menu aparece, com os seis itens |\n"), tmp)
    ok("confessa que não mediu" not in saida,
       "`na tela` nao e' `n/a`, e `todo o menu` nao e' `TODO`", saida)

    codigo, saida = conferir(CABECA + (
        "| master | listar | permitido | não verifiquei em navegador |\n"), tmp)
    ok("confessa que não mediu" in saida,
       "mas a confissao de verdade continua sendo pega", saida)

    print("\nEsperado escrito por negacao")
    codigo, saida = conferir(CABECA + (
        "| somente-leitura | editar | não permitido | botão ausente |\n"
        "| somente-leitura | listar | permitido | 200 |\n"), tmp)
    ok("escrito por negação" in saida,
       "'nao permitido' some com o que se esperava", saida)

    # ----------------------------------------------------------------
    print("\nPerfil declarado no config e nunca exercitado")
    cfg = tmp / "config.toml"
    cfg.write_text("[perfis]\ncomando = \"npm run perfil\"\n\n"
                   "[perfis.atores.master]\nchaves = []\n\n"
                   "[perfis.atores.somente-leitura]\nchaves = []\n\n"
                   "[perfis.atores.sem-faq]\nchaves = []\n\n[stack]\n", encoding="utf-8")
    ok(sorted(P.ler_perfis_do_config(cfg)) == ["master", "sem-faq", "somente-leitura"],
       "le os atores declarados", str(P.ler_perfis_do_config(cfg)))

    codigo, saida = conferir(CABECA + (
        "| master | criar categoria | permitido | 201 |\n"), tmp, config=str(cfg))
    ok("nunca exercitado" in saida and "somente-leitura" in saida and "sem-faq" in saida,
       "nomeia quem ficou de fora", saida)
    ok(codigo == 0, "e nao reprova por isso — e' MEDIO, pode ser deliberado", saida)

    print("\nRelatorio sem tabela de perfis nenhuma")
    codigo, saida = conferir("Rodei o caminho feliz e deu tudo certo.\n", tmp)
    ok(codigo == 1 and "Nenhuma tabela de perfis" in saida,
       "a ausencia da tabela e' o achado", saida)

    print("\nE uma tabela que nao e' de perfis e' ignorada")
    codigo, saida = conferir(
        "| Rota | Estado | Tempo |\n| --- | --- | --- |\n| /faq | ok | 1.2s |\n\n"
        + CABECA + "| master | listar | permitido | 200 |\n", tmp)
    ok("1 perfil(is), 1 linha(s)" in saida,
       "so a tabela com Perfil e Esperado entra na conta", saida)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaca de profiles.py: tudo verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
