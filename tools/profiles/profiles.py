#!/usr/bin/env python3
"""Perfis de acesso: a entrega mexeu em autorização? E quem provou que sim?

A frente de execução já mandava *"entrar com ator sem a permissão"*. Numa
atividade real a resposta foi: **"não há ator só-leitura no banco, e criar um
exigiria conta e senha"** — e a dimensão foi declarada não coberta. Obrigação
escrita sem mecanismo por trás produz isso toda vez.

    superficie   o diff toca autorização? Se toca, a passada por perfis deixa
                 de ser recomendação e vira obrigação
    conferir     o relatório prova o que diz? Toda negação precisa de uma
                 permissão do MESMO perfil na mesma sessão

A segunda é a que decide se isto vale. **Um teste negativo passa trivialmente
quando a conta está quebrada:** "não consegui editar" é verde tanto para "a
permissão foi negada" quanto para o login que falhou, a conta que expirou, a
role que foi renomeada, o seed que não rodou. Sem o par, a matriz de perfis é
uma máquina de verde falso — e pior que não ter, porque parece cobertura.

Uso:
    profiles.py superficie --base main [--raiz .]
    profiles.py conferir relatorio.md [--config <config.toml>]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path


class PerfilError(Exception):
    pass


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def normalizar(t: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(t)).strip().lower()


# --------------------------------------------------------------------------
# deixar rastro no estado da atividade
# --------------------------------------------------------------------------
# Sem isto a conferência é uma frase na skill, e frase na skill não acontece:
# "entrar com ator sem a permissão" viveu meses na frente de execução sem nunca
# ter acontecido, porque ninguém registrava e portanto ninguém sabia.
#
# `--registrar <id>` grava o veredicto na atividade, e o `concluir` do
# flow_state recusa encerrar com conferência exigida em aberto.
def registrar(id_atividade: str, ferramenta: str, veredicto: str,
              detalhe: str = "") -> None:
    if not id_atividade:
        return
    flow_state = Path(__file__).resolve().parent.parent / "flow-state" / "flow_state.py"
    if not flow_state.is_file():
        print(f"  [aviso] não achei {flow_state}; nada foi registrado")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(flow_state), "conferencia", id_atividade,
             "--ferramenta", ferramenta, "--veredicto", veredicto,
             "--detalhe", detalhe[:200]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [aviso] não consegui registrar: {exc}")
        return
    if r.returncode != 0:
        print(f"  [aviso] registro recusado: {(r.stderr or r.stdout).strip()[:160]}")
        return
    # Registro silencioso é a mesma doença que esta tabela existe para curar:
    # quem roda precisa VER que ficou escrito.
    print(f"  registrado em {id_atividade}: {ferramenta} → {veredicto}")


# --------------------------------------------------------------------------
# superfície de autorização
# --------------------------------------------------------------------------
# Os padrões são desta pilha — NestJS de um lado, React do outro. O que não
# muda é o critério: um trecho só entra aqui se decidir **quem pode**, e não se
# decidir o que aparece por outro motivo. `if (loading)` esconde botão e não é
# autorização.
#
# Este comentário prometia, desde sempre, que o projeto podia *"trocá-los em
# `[perfis] padroes`"* — **e nada no código lia isso**. A saída anunciada não
# existia; quem precisasse de outro eixo teria de editar o pacote. Achado em
# 22/09/2026, conferindo o defeito vizinho da frase absoluta: os dois são a
# mesma família, prosa ocupando o lugar do mecanismo.
#
# Agora existe, e ACRESCENTA em vez de trocar — ver `ler_padroes_do_config`.
PADROES = [
    (r"@RequirePermissions\s*\(", "chave exigida por rota"),
    (r"@UseGuards\s*\(", "pilha de guardas"),
    (r"implements\s+CanActivate", "guarda nova"),
    (r"\bglobalPermissions\b", "leitura de permissão global"),
    (r"\bpermissions\s*\.\s*includes\s*\(", "checagem de permissão"),
    (r"\bcanSee[A-Z]\w*", "visibilidade por permissão na tela"),
    (r"\bhasPermission\s*\(", "checagem de permissão"),
]

# Teste que fala de permissão não é superfície nova: é a rede em volta dela.
# Contá-lo faria toda entrega que ACRESCENTA cobertura de autorização parecer
# uma entrega que MUDA autorização — e a obrigação dispararia justamente para
# quem acabou de cumpri-la.
RE_TESTE = re.compile(r"\.(spec|test)\.[jt]sx?$|(^|/)(e2e|__tests__)/")

# Documento não decide nada. Na primeira calibração contra um diff real, metade
# dos arquivos acusados eram `.md`: uma especificação que DESCREVE a regra de
# permissão casa com todos os padrões e não enforça coisa nenhuma. Acusá-la faz
# a obrigação disparar para quem escreveu documentação — que é o oposto do que
# se quer.
RE_DOCUMENTO = re.compile(r"\.(md|mdx|txt|adoc|rst|json|ya?ml|csv)$", re.I)


def diff_do_git(base: str, raiz: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "diff", f"{base}...HEAD", "-U0"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PerfilError(f"git indisponível: {exc}") from exc
    if r.returncode != 0:
        raise PerfilError(f"git diff falhou: {r.stderr.strip()[:200]}")
    return r.stdout


def achar_superficie(diff: str,
                     extras: list[tuple[str, str, str]] | None = None
                     ) -> tuple[dict[str, list[str]], list[str]]:
    """Arquivos de produção que ganharam linha de autorização, e os de teste.

    `extras` são os padrões que o projeto declarou; eles ACRESCENTAM aos sete
    de pilha. Ver `ler_padroes_do_config`.
    """
    producao: dict[str, list[str]] = {}
    testes: list[str] = []
    arquivo = "?"
    # Os sete de pilha casam LINHA; os do projeto podem casar linha, caminho
    # ou os dois. Normalizados aqui para o laço não conhecer a diferença.
    todos = ([(corpo_re, "", rot) for corpo_re, rot in PADROES]
             + list(extras or []))
    for linha in diff.splitlines():
        if linha.startswith("+++ b/"):
            arquivo = linha[6:].strip()
            continue
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        corpo = linha[1:]
        if RE_DOCUMENTO.search(arquivo):
            continue
        for padrao, padrao_arquivo, rotulo in todos:
            if padrao_arquivo and not re.search(padrao_arquivo, arquivo):
                continue
            if not padrao or re.search(padrao, corpo):
                if RE_TESTE.search(arquivo):
                    if arquivo not in testes:
                        testes.append(arquivo)
                else:
                    producao.setdefault(arquivo, [])
                    if rotulo not in producao[arquivo]:
                        producao[arquivo].append(rotulo)
                break
    return producao, testes


def cmd_superficie(args) -> int:
    raiz = Path(args.raiz).resolve()
    diff = sys.stdin.read() if args.base == "-" else diff_do_git(args.base, raiz)
    # O CONFIG SE ACHA SOZINHO. Exigir `--config` aqui repetiria o defeito que
    # esta saída veio consertar: o projeto declara o eixo dele, alguém esquece
    # a bandeira, e a ferramenta volta a responder só sobre perfil — com a
    # mesma cara de conferência completa. Explícito continua vencendo.
    escolhido = Path(args.config) if getattr(args, "config", "") else None
    if escolhido is None:
        provavel = raiz / ".agents" / "config.toml"
        escolhido = provavel if provavel.is_file() else None
    extras = ler_padroes_do_config(escolhido)
    if extras:
        print(f"[{len(extras)} padrão(ões) do projeto, de {escolhido}]")
        print()
    producao, testes = achar_superficie(diff, extras)
    # O que a negativa pode afirmar depende do que o projeto declarou. Fixar a
    # frase em "por perfil" ficaria ERRADA PARA MENOS no projeto que
    # acrescentou eixos — e a mesma frase precisa continuar certa nos dois.
    if extras:
        medido = (f"POR PERFIL, nem os {len(extras)} padrão(ões) que o projeto "
                  "declara em `[[perfis.padroes]]`")
        medido_curto = (f"por perfil, nem os {len(extras)} padrão(ões) "
                        "declarados pelo projeto")
    else:
        medido = "POR PERFIL"
        medido_curto = "por perfil (decorador, guarda, checagem de permissão)"

    if not producao:
        # A NEGATIVA NOMEIA O EIXO QUE ELA MEDIU, e isso não é estilo.
        #
        # Os sete `PADROES` são todos de autorização POR PERFIL DE USUÁRIO. Em
        # 22/09/2026 uma entrega acrescentou uma linha à allowlist de chamador
        # de SERVIÇO — array de dados literais, que não casa com nenhum deles —
        # e este ramo fechou a conferência com `ok` e a frase *"o diff não toca
        # superfície de autorização"*. Achado pela frente de execução, ao ler a
        # tabela da atividade; nenhuma das quatro frentes de leitura viu.
        #
        # A ferramenta está CERTA em não medir aquele eixo: ele está fora do
        # escopo dela por desenho. O defeito era a frase — negativa ABSOLUTA
        # sobre medição PARCIAL. E o dano não fica na tela: `registrar` grava
        # o mesmo texto no histórico da atividade, onde ele sobrevive à sessão
        # e vira o "não há" que ninguém mais confere.
        #
        # É a família do zero que se lê como confirmação: "não achei DISTO" e
        # "não há" são respostas a perguntas diferentes.
        print(f"A entrega não toca superfície de autorização {medido}.")
        if testes:
            print(f"({len(testes)} arquivo(s) de teste falam de permissão — "
                  "rede em volta, não superfície nova.)")
        print()
        print("A passada por perfis fica como recomendação, e não reprova.")
        registrar(args.registrar, "perfis", "ok",
                  f"o diff não toca superfície de autorização {medido_curto}")
        print()
        print("O que isto NÃO prova, e são duas coisas:")
        print("  1. que a autorização existente está certa. Ele lê o diff, e")
        print("     defeito que já estava lá não aparece aqui.")
        print("  2. que a entrega não alarga acesso por OUTRO eixo. Allowlist")
        print("     de chamador de serviço, credencial entre sistemas, regra")
        print("     de rede e escopo de token não passam por perfil de usuário")
        print("     e NÃO são lidos aqui. Se o diff mexe em quem-chama-quem,")
        print("     esta linha verde não fala sobre isso.")
        if not extras:
            print()
            print("     O projeto pode acrescentar os eixos dele em")
            print("     `[[perfis.padroes]]` do config: `arquivo` casa o")
            print("     caminho, `regex` casa a linha, `rotulo` dá o nome.")
            print("     Eles SOMAM aos sete de pilha, e entram nesta frase.")
        return 0

    print(f"[OBRIGATÓRIO] a entrega toca autorização em {len(producao)} arquivo(s)")
    print("  a frente de execução precisa exercitar pelo menos dois perfis:")
    print("  o que pode e o que não pode. Ver references/access-profiles.md")
    print()
    for arquivo in sorted(producao):
        print(f"    {arquivo}")
        print(f"        {', '.join(producao[arquivo])}")
    if testes:
        print()
        print(f"  {len(testes)} arquivo(s) de teste também falam de permissão, e não")
        print("  contam como superfície: são a rede em volta dela.")
    print()
    print("O que isto NÃO prova: que a mudança de autorização está errada. Ele")
    print("diz que ela existe, e que ninguém deveria entregá-la sem exercitar.")
    registrar(args.registrar, "perfis", "exigida",
              f"o diff toca autorização por perfil em {len(producao)} arquivo(s)")
    return 1


# --------------------------------------------------------------------------
# o relatório da passada
# --------------------------------------------------------------------------
RE_SEPARADOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

# `negado` e `permitido` por radical, como em outcome.py, e com a mesma recusa
# a classificar negação: "nao permitido" some com o que aconteceu.
ESPERADOS = {"negad": "negado", "recusad": "negado", "bloquead": "negado",
             "permitid": "permitido", "aceit": "permitido", "liberad": "permitido"}
RE_NEGACAO = r"\b(?:nao|sem|nunca)\b(?:\s+\w+){{0,2}}\s+\w*{radical}\w*"

# Frases com que um relatório confessa que não mediu. Elas não podem contar como
# observação: "não consegui entrar" e "a permissão foi negada" produzem a mesma
# tela vazia, e só a segunda é evidência.
# DUAS ARMADILHAS DE PORTUGUES, as duas derrubadas por teste antes de sair:
#
#   `n/?a\b`  casa com **"na"** — "200, seis categorias na tela" virava
#              confissao de nao-medicao. `na` e' das palavras mais comuns da
#              lingua, e o padrao acusava justamente a observacao bem escrita.
#   `todo\b`  casa com **"todo"** — "todo o menu aparece" e' medicao, nao TODO.
#
# Nenhuma das duas voltou. O padrao aqui so' aceita frase que confessa, e nao
# sigla que colide.
RE_NAO_MEDIU = re.compile(
    r"\bnao (?:consegui|verifiquei|deu|foi possivel|testei|rodei|exercitei)|"
    r"\bnao verificad|\bsem prova|\bnao exercit|\bnao medi|"
    r"\bpendente\b|\ba fazer\b|\bnao aplicavel\b")


def celulas(linha: str) -> list[str]:
    b = linha.strip()
    if b.startswith("|"):
        b = b[1:]
    if b.endswith("|"):
        b = b[:-1]
    return [c.strip() for c in b.split("|")]


def indice(cabecalho: list[str], *nomes: str) -> int | None:
    for n, t in enumerate(cabecalho):
        if any(nome in normalizar(t) for nome in nomes):
            return n
    return None


def classificar(texto: str) -> tuple[str | None, bool]:
    """(esperado, foi_escrito_por_negacao)"""
    t = normalizar(texto)
    achados, negados = [], []
    for radical, nome in ESPERADOS.items():
        if not re.search(rf"\w*{re.escape(radical)}\w*", t):
            continue
        alvo = negados if re.search(RE_NEGACAO.format(radical=re.escape(radical)), t) else achados
        if nome not in alvo:
            alvo.append(nome)
    achados = [a for a in achados if a not in negados]
    if len(achados) == 1:
        return achados[0], False
    if not achados and negados:
        return None, True
    return None, False


def ler_perfis_do_config(caminho: Path | None) -> list[str]:
    if caminho is None or not caminho.is_file():
        return []
    texto = caminho.read_text(encoding="utf-8")
    m = re.search(r"^\[perfis\]\s*$(.*?)(^\[|\Z)", texto, re.M | re.S)
    if not m:
        return []
    return re.findall(r"^\s*\[perfis\.atores\.([A-Za-z0-9_-]+)\]", texto, re.M)


def ler_padroes_do_config(caminho: Path | None
                          ) -> list[tuple[str, str, str]]:
    """Os padrões que o PROJETO acrescenta, de `[[perfis.padroes]]`.

    ```toml
    [[perfis.padroes]]
    arquivo = 'service-caller-allowlist'
    rotulo = "allowlist de chamador de serviço"
    ```

    **Dois eixos, e pelo menos um é obrigatório.** `regex` casa com a LINHA
    acrescentada; `arquivo` casa com o CAMINHO. Os sete de pilha são todos de
    linha — decorador, guarda, chamada —, e o caso que motivou esta saída não
    é: a allowlist de chamador de serviço é um **array de dados literais**, e
    o que a identifica é o arquivo em que ela mora. Uma saída que só soubesse
    casar linha não resolveria o caso que a pediu.

    Dando os dois, os DOIS precisam casar.

    **Acrescenta, não troca.** Trocar é o que o comentário antigo prometia, e
    seria o mesmo defeito noutro lugar: um projeto que declarasse UM padrão
    perderia os sete de pilha sem perceber, e a ferramenta voltaria a dizer
    "não toca" sobre o que deixou de olhar.

    **Regex que não compila RECUSA a rodada.** Ignorar a linha seria pior que
    não ter a saída: o projeto declarou um eixo, a ferramenta não o mediria, e
    o veredicto sairia `ok` com a cara de quem conferiu tudo.
    """
    if caminho is None or not caminho.is_file():
        return []
    texto = caminho.read_text(encoding="utf-8")
    saida: list[tuple[str, str]] = []
    for m in re.finditer(r"^\s*\[\[perfis\.padroes\]\]\s*$(.*?)(?=^\s*\[|\Z)",
                         texto, re.M | re.S):
        bloco = m.group(1)
        def campo(nome: str) -> str:
            c = re.search(rf"^\s*{nome}\s*=\s*(\"(?:[^\"\\\\]|\\\\.)*\"|'[^']*')\s*$",
                          bloco, re.M)
            if not c:
                return ""
            bruto = c.group(1)
            return bruto[1:-1] if bruto[0] == "'" else bruto[1:-1].replace('\\"', '"')
        regex, arquivo, rotulo = (campo("regex"), campo("arquivo"),
                                  campo("rotulo"))
        if not regex and not arquivo:
            raise PerfilError(
                "[[perfis.padroes]] sem `regex` nem `arquivo`. Um bloco que "
                "não diz o que procurar não acrescenta eixo nenhum, e passaria "
                "como se acrescentasse."
            )
        for bruto in (regex, arquivo):
            if not bruto:
                continue
            try:
                re.compile(bruto)
            except re.error as exc:
                raise PerfilError(
                    f"[[perfis.padroes]] com regex que não compila: "
                    f"{bruto!r} — {exc}.\n  Recuso a rodada em vez de ignorar "
                    "a linha: o projeto declarou um eixo, e um `ok` sem ele "
                    "seria o veredicto certo para uma conferência que não "
                    "aconteceu."
                ) from exc
        saida.append((regex, arquivo,
                      rotulo or "padrão declarado pelo projeto"))
    return saida


def cmd_conferir(args) -> int:
    doc = Path(args.relatorio)
    if not doc.is_file():
        raise PerfilError(f"relatório não encontrado: {doc}")
    linhas = doc.read_text(encoding="utf-8").splitlines()

    # perfil -> {"permitido": [...], "negado": [...], "sem_observacao": [...],
    #            "confessou": [...]}
    tabela: dict[str, dict[str, list[str]]] = {}
    negacoes, linhas_lidas = [], 0

    i = 0
    while i < len(linhas):
        if (linhas[i].lstrip().startswith("|") and i + 1 < len(linhas)
                and RE_SEPARADOR.match(linhas[i + 1])):
            cab = celulas(linhas[i])
            i_perfil = indice(cab, "perfil", "ator")
            i_esp = indice(cab, "esperado", "previsto")
            i_obs = indice(cab, "observado", "medido", "resultado")
            i_acao = indice(cab, "acao", "gesto", "o que")
            i += 2
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                cel = celulas(linhas[i])
                n = i + 1
                i += 1
                if i_perfil is None or i_esp is None or len(cel) <= max(i_perfil, i_esp):
                    continue
                perfil = cel[i_perfil].strip().strip("`* ")
                if not perfil or set(perfil) <= set("-—– "):
                    continue
                linhas_lidas += 1
                reg = tabela.setdefault(perfil, {"permitido": [], "negado": [],
                                                 "sem_observacao": [], "confessou": []})
                acao = cel[i_acao].strip() if i_acao is not None and len(cel) > i_acao else f"linha {n}"
                esperado, por_negacao = classificar(cel[i_esp])
                if por_negacao:
                    negacoes.append(f"{perfil} · {acao} (linha {n}): {cel[i_esp]}")
                    continue
                if esperado is None:
                    continue
                obs = cel[i_obs].strip() if i_obs is not None and len(cel) > i_obs else ""
                if not obs:
                    reg["sem_observacao"].append(f"{perfil} · {acao} (linha {n})")
                    continue
                if RE_NAO_MEDIU.search(normalizar(obs)):
                    reg["confessou"].append(f"{perfil} · {acao} (linha {n}): {obs[:60]}")
                    continue
                reg[esperado].append(acao)
        else:
            i += 1

    if not tabela:
        print("Nenhuma tabela de perfis neste relatório.")
        print()
        print("Ela precisa de `Perfil`, `Ação`, `Esperado` e `Observado`.")
        print("Ver references/access-profiles.md.")
        return 1

    graves = 0

    def bloco(itens, rotulo, explicacao, nivel="ALTO"):
        nonlocal graves
        if not itens:
            return
        if nivel == "ALTO":
            graves += 1
        print(f"[{nivel}] {rotulo} ({len(itens)})")
        for l in explicacao:
            print(f"  {l}")
        for it in itens:
            print(f"    {it}")
        print()

    # A regra que faz a matriz valer alguma coisa.
    sem_par = [f"{p}: {len(r['negado'])} negação(ões) e nenhuma permissão"
               for p, r in sorted(tabela.items()) if r["negado"] and not r["permitido"]]
    bloco(sem_par, "perfil que só provou o que NÃO pode",
          ["uma negação sozinha não distingue 'a permissão foi negada' de 'o",
           "login falhou', 'a conta expirou', 'a role sumiu'. O mesmo ator, na",
           "mesma sessão, precisa conseguir alguma coisa — senão a conta quebrada",
           "deixa a matriz inteira verde"])

    bloco(sum((r["sem_observacao"] for r in tabela.values()), []),
          "linha sem o que foi observado",
          ["`Esperado` é a hipótese; sem `Observado` não houve medição"])

    bloco(sum((r["confessou"] for r in tabela.values()), []),
          "linha cujo observado confessa que não mediu",
          ["não é achado, é dimensão não coberta — e não pode contar como prova.",
           "Nomeie e siga, como se faz com a frente que não respondeu"])

    bloco(negacoes, "esperado escrito por negação",
          ["'não permitido' diz o que não se esperava e some com o que se",
           "esperava. Escreva `negado`, e o que deveria aparecer ao lado"])

    declarados = ler_perfis_do_config(Path(args.config) if args.config else None)
    ausentes = [p for p in declarados if p not in tabela]
    bloco(ausentes, "perfil declarado no config e nunca exercitado",
          ["ele existe no projeto e esta passada não o tocou. Se foi de",
           "propósito, diga por quê no relatório"], nivel="MEDIO")

    print(f"{len(tabela)} perfil(is), {linhas_lidas} linha(s)")
    for p, r in sorted(tabela.items()):
        par = "com par" if r["permitido"] and r["negado"] else (
            "só permissões" if r["permitido"] else "só negações")
        print(f"    {p:<24} {len(r['permitido'])} permitida(s), "
              f"{len(r['negado'])} negada(s)   {par}")
    print()
    print("O que isto NÃO prova: que o esperado estava certo. Ele confere que")
    print("houve medição e que a negação tem contraprova. Se o perfil deveria")
    print("poder e você escreveu `negado`, ele concorda com você e erra junto.")
    registrar(args.registrar, "perfis", "falhou" if graves else "ok",
              f"{len(tabela)} perfil(is), {linhas_lidas} linha(s)")
    return 1 if graves else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("superficie", help="o diff toca autorização?")
    s.add_argument("--base", default="main", help="ref base, ou `-` para diff no stdin")
    s.add_argument("--raiz", default=".", help="raiz do repositório")
    s.add_argument("--registrar", default="",
                   help="id da atividade: grava o veredicto no estado")
    s.add_argument("--config", default="",
                   help="config.toml, para os padrões que o projeto acrescenta")
    s.set_defaults(fn=cmd_superficie)

    c = sub.add_parser("conferir", help="o relatório prova o que diz?")
    c.add_argument("relatorio")
    c.add_argument("--config", default="", help="config.toml, para saber os perfis declarados")
    c.add_argument("--registrar", default="",
                   help="id da atividade: grava o veredicto no estado")
    c.set_defaults(fn=cmd_conferir)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except PerfilError as exc:
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
