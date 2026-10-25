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


def superficie(texto: str, config: str = "", raiz: str = ".") -> tuple[int, str]:
    buf, antigo = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(texto)
    try:
        with contextlib.redirect_stdout(buf):
            codigo = P.cmd_superficie(Args(base="-", raiz=raiz, config=config))
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
    # O eixo que ela NAO le' tem de aparecer na frase, porque o verde dela vai
    # para o HISTORICO da atividade e sobrevive a` sessao. Em 22/09/2026 uma
    # entrega acrescentou uma linha a` allowlist de chamador de SERVICO --
    # array de dados literais, fora dos sete padroes por desenho -- e a
    # conferencia fechou com `ok` e "o diff nao toca superficie de
    # autorizacao". A ferramenta estava certa em nao medir; a frase e' que
    # afirmava mais do que ela sabia.
    print("\nA negativa nomeia o eixo que ela mediu")
    _alvo = diff("a/backend/libs/common/src/service-caller-allowlist.ts",
                 "  'POST pedidos/frete/resolve',")
    codigo, saida = superficie(_alvo)
    ok(codigo == 0, "allowlist de servico nao casa com os sete padroes -- e "
       "isso esta' certo, esta' fora do escopo por desenho", saida)
    ok("POR PERFIL" in saida,
       "mas a frase DIZ de que autorizacao ela esta' falando", saida)
    ok("chamador de servi" in saida and "N\u00c3O s\u00e3o lidos aqui" in saida,
       "e nomeia o eixo cego, com o caso que a mordeu", saida)

    # O que vai para o HISTORICO, que e' o que sobrevive: a tela pode explicar
    # a vontade, o `--detalhe` e' o que a proxima pessoa le'.
    _registros = []
    _registrar_real = P.registrar
    P.registrar = lambda *a, **kw: _registros.append(a)
    try:
        superficie(_alvo)
    finally:
        P.registrar = _registrar_real
    ok(len(_registros) == 1 and _registros[0][2] == "ok",
       "o veredicto segue `ok` -- ela nao reprova o que nao mediu",
       repr(_registros))
    ok("por perfil" in _registros[0][3].lower(),
       "e o detalhe REGISTRADO carrega o limite, nao so' a tela",
       repr(_registros))

    # ----------------------------------------------------------------
    # A saida que o comentario prometia desde sempre, e que nao existia: o
    # projeto acrescenta o eixo DELE. Achado em 22/09/2026, conferindo o
    # defeito da frase -- `[perfis] padroes` estava escrito no codigo e nada o
    # lia. Prosa ocupando o lugar do mecanismo, a mesma familia.
    print("\nO projeto ACRESCENTA padroes, e eles somam aos sete")
    _cfg = tmp / "com-padroes.toml"
    _cfg.write_text(
        "[perfis]\ncomando = \"\"\n\n"
        "[[perfis.padroes]]\n"
        "arquivo = 'service-caller-allowlist'\n"
        "rotulo = \"allowlist de chamador de servico\"\n",
        encoding="utf-8")
    codigo, saida = superficie(_alvo, config=str(_cfg))
    ok(codigo == 1 and "OBRIGATÓRIO" in saida,
       "com o padrao declarado, a MESMA entrega que passava agora e' pega",
       saida)
    ok("allowlist de chamador de servico" in saida,
       "e aparece pelo rotulo que o projeto deu", saida)

    # ACRESCENTA, nao troca: um projeto que declara UM padrao nao pode perder
    # os sete de pilha sem perceber -- seria o mesmo defeito noutro lugar.
    codigo, saida = superficie(
        diff("a/api/x.controller.ts", "  @RequirePermissions('faq.read')"),
        config=str(_cfg))
    ok(codigo == 1 and "chave exigida por rota" in saida,
       "e os sete de pilha continuam valendo: soma, nao troca", saida)

    # E a frase da negativa acompanha o que o projeto declarou -- fixa em "por
    # perfil" ela ficaria errada PARA MENOS aqui.
    codigo, saida = superficie(diff("a/web/z.tsx", "  const x = 1;"),
                               config=str(_cfg))
    ok(codigo == 0 and "1 padrão(ões)" in saida,
       "a negativa conta os padroes declarados, em vez de falar so' de perfil",
       saida)

    # Regex que nao compila RECUSA. Ignorar a linha seria pior que nao ter a
    # saida: o projeto declarou um eixo, a ferramenta nao o mediria, e o
    # veredicto sairia `ok` com a cara de quem conferiu tudo.
    _ruim = tmp / "regex-ruim.toml"
    _ruim.write_text("[[perfis.padroes]]\nregex = '(nao fecha'\n", encoding="utf-8")
    try:
        superficie(_alvo, config=str(_ruim))
        ok(False, "regex que nao compila recusa a rodada")
    except P.PerfilError as exc:
        ok("não compila" in str(exc), "regex que nao compila recusa a rodada",
           str(exc))

    _sem = tmp / "sem-regex.toml"
    _sem.write_text("[[perfis.padroes]]\nrotulo = \"so o nome\"\n", encoding="utf-8")
    try:
        superficie(_alvo, config=str(_sem))
        ok(False, "bloco sem `regex` nem `arquivo` recusa, em vez de passar como se somasse")
    except P.PerfilError:
        ok(True, "bloco sem `regex` nem `arquivo` recusa, em vez de passar como se somasse")

    # O config se acha sozinho a partir da raiz. Exigir a bandeira repetiria o
    # defeito que esta saida veio consertar: o projeto declara o eixo, alguem
    # esquece `--config`, e a ferramenta volta a responder so' sobre perfil --
    # com a mesma cara de conferencia completa.
    _proj = tmp / "projeto"
    (_proj / ".agents").mkdir(parents=True)
    (_proj / ".agents" / "config.toml").write_text(
        "[[perfis.padroes]]\n"
        "arquivo = 'service-caller-allowlist'\n"
        "rotulo = \"allowlist de chamador de servico\"\n", encoding="utf-8")
    codigo, saida = superficie(_alvo, raiz=str(_proj))
    ok(codigo == 1, "sem --config, o `.agents/config.toml` da raiz vale", saida)
    ok("padrão(ões) do projeto" in saida and ".agents" in saida,
       "e a saida DIZ de qual config vieram os padroes", saida)
    # O controle: na raiz sem config, a mesma entrega volta a passar -- e' o
    # que separa a descoberta de um acaso.
    codigo, saida = superficie(_alvo, raiz=str(tmp / "sem-agents"))
    ok(codigo == 0, "controle: raiz sem config nao inventa padrao", saida)

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
