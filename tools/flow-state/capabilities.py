#!/usr/bin/env python3
"""Report what this machine and this user can actually do.

The flow runs on different machines, for people with different accounts and
different access. A skill that assumes a capability it does not have fails in
the middle of an activity; a skill that asks first degrades on purpose.

    python3 capabilities.py            # relatório legível
    python3 capabilities.py --json     # para consumo por script
    python3 capabilities.py figma      # uma capacidade só, para decisão rápida

Nothing here is a hard requirement. Every "não" is a documented fallback, not a
blocker: no Figma means the screen drawer path, no ReportLab means Markdown
without PDF, no browser means no visual check.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from flow_state import (FlowStateError, raiz_de_trabalho, raiz_do_projeto,  # noqa: E402
                        raiz_do_projeto, resolve_agents_dir)

# O token de leitura do Figma. Mesmo caminho que `tools/figma/figma.py` usa —
# declarado aqui de novo de propósito: este módulo não importa aquele, e uma
# constante duplicada é mais barata que um import que amarra a detecção à
# ferramenta detectada.
CAMINHO_TOKEN_FIGMA = Path.home() / ".config" / "elcamargo-flow" / "figma-token"

# Figma MCP read-tool budgets, by seat. From the official rate-limit table.
# Valem para o MCP, que é o caminho da ESCRITA. A leitura por REST não passa
# por aqui — ela responde ao que a conta do token alcança.
ORCAMENTO_FIGMA_MCP = {
    "dev": "200-600 chamadas por dia",
    "full": "200-600 chamadas por dia",
    "collab": "6-20 chamadas por MÊS",
    "view": "6-20 chamadas por MÊS",
}


def _comando(*args: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def capacidade_python() -> dict:
    return {"disponivel": True, "detalhe": sys.version.split()[0],
            "nota": "tomllib exige 3.11+"}


# O venv do ReportLab NÃO mora em `/tmp`, e isto custou uma execução para
# aprender: o macOS tem faxineiro de `/tmp`, e no meio de uma atividade o venv
# apareceu meio apagado — `reportlab/lib/` só com `__pycache__`, e o `pip` do
# próprio venv sem executar. O sintoma não é "não instalado": é instalado e
# quebrado, que é pior, porque a mensagem de erro fala de import e não de
# faxina.
#
# `~/.cache` é do usuário, não é limpo por ninguém, e continua fora do projeto —
# que era a razão de usar `/tmp` para começo de conversa.
VENV_RELATORIO = Path.home() / ".cache" / "elcamargo-flow" / "venv"


def capacidade_relatorio() -> dict:
    """ReportLab, para gerar PDF na fronteira com humano."""
    candidatos = (str(VENV_RELATORIO / "bin" / "python"),
                  "/tmp/venv_report/bin/python",  # herdado; some sozinho
                  sys.executable)
    for venv in candidatos:
        ok, _ = _comando(venv, "-c", "import reportlab")
        if ok:
            return {"disponivel": True, "detalhe": venv,
                    "nota": "PDF disponível"}
    return {
        "disponivel": False,
        "detalhe": "reportlab ausente, ou o venv foi apagado pelo sistema",
        "fallback": "Entregue o relatório em Markdown. O PDF só é necessário "
                    "na fronteira com humano; o fluxo inteiro funciona sem ele.",
        "como_resolver": f"python3 -m venv {VENV_RELATORIO} && "
                         f"{VENV_RELATORIO}/bin/python -m pip install "
                         "reportlab pypdfium2",
    }


def capacidade_figma() -> dict:
    """Ler o Figma NÃO exige MCP: é REST com token pessoal, pelo `figma.py`.

    Esta função dizia o contrário, e o custo foi medido. Em 08/09/2026 uma
    frente irmã parou o step 6 "por falta de MCP da Figma": tentou o MCP, tentou
    o Chrome, tentou o navegador interno e parou no muro de login — com o token
    instalado na mesma máquina desde 28/08, e o `figma.py` capaz de ler aquele
    arquivo em um comando. Quem a mandou para lá foi a estratégia que se lia
    aqui, `sem_mcp: "Vá pelo screen-drawer"`, **que era falsa**.

    O que a REST garante e nenhum MCP garante: `GET` **não consegue escrever**.
    Num arquivo da empresa, com gente trabalhando dentro, essa diferença é tudo.

    Por isso a detecção mudou de eixo. Antes se perguntava "há MCP na sessão?",
    que este processo não tem como saber. Agora se pergunta "há token nesta
    máquina?", que ele sabe — e é o pré-requisito do caminho que o fluxo usa.
    """
    comandos = {
        "1 · raso": "figma.py paginas <chave>",
        "2 · requisito": "figma.py comentarios <chave> --abertos",
        "3 · a tela": "figma.py resumo <chave> --no <id> --profundidade 3",
        "4 · o visual": "figma.py imagem <chave> --no <id> --saida tela.png",
    }
    base = {
        "comandos": comandos,
        "estrategia": {
            "leitura": "REST, pelo `tools/figma/figma.py`. Sem MCP, sem app "
                       "desktop, sem navegador logado. Comece raso e desça: "
                       "descer direto na árvore inteira gasta numa chamada o "
                       "que a atividade toda deveria gastar.",
            "escrita": "Aí sim exige o MCP da Figma (`use_figma`), e é decisão "
                       "separada — ver a ação `figma_escrita`, que nasce off.",
            "sem_token": "Instale o token; é uma vez por máquina. Só se não der "
                         "é que o step 6 vai pelo `screen-drawer` — que não é "
                         "degradação, é o outro caminho previsto. Mas ir por "
                         "ele TENDO link de Figma e podendo ler é perder o "
                         "protótipo real.",
        },
        "aviso": "NUNCA caia para o navegador quando a leitura falhar. `GET` "
                 "não escreve; o editor escreve. O plano B é pedir export ao "
                 "usuário.",
        "orcamentos_do_mcp": ORCAMENTO_FIGMA_MCP,
    }

    if os.environ.get("FIGMA_TOKEN", "").strip():
        return dict(base, disponivel=True,
                    detalhe="token em $FIGMA_TOKEN — leitura por REST",
                    nota="Token presente prova que HÁ credencial, não que ela "
                         "alcança ESTE arquivo. Um 403 nomeia o escopo que "
                         "falta, e escopo se marca ao gerar o token.")

    if CAMINHO_TOKEN_FIGMA.exists():
        modo = oct(CAMINHO_TOKEN_FIGMA.stat().st_mode)[-3:]
        if modo != "600":
            return dict(base, disponivel=False,
                        detalhe=f"token com permissão {modo} — não serve",
                        como_resolver=f"chmod 600 {CAMINHO_TOKEN_FIGMA}")
        if CAMINHO_TOKEN_FIGMA.read_text(encoding="utf-8").strip():
            return dict(base, disponivel=True,
                        detalhe=f"token em {CAMINHO_TOKEN_FIGMA} — leitura por REST",
                        nota="Token presente prova que HÁ credencial, não que "
                             "ela alcança ESTE arquivo. Um 403 nomeia o escopo "
                             "que falta, e escopo se marca ao gerar o token.")

    return dict(base, disponivel=False,
                detalhe="sem token do Figma nesta máquina",
                como_resolver=(
                    "Gere em Figma > Settings > Security > Personal access "
                    "tokens, com escopo de LEITURA de conteúdo de arquivo, e: "
                    f"mkdir -p {CAMINHO_TOKEN_FIGMA.parent} && printf 'Cole o "
                    f"token: ' && read -rs T && printf '%s' \"$T\" > "
                    f"{CAMINHO_TOKEN_FIGMA} && chmod 600 {CAMINHO_TOKEN_FIGMA} "
                    "&& unset T"),
                fallback="Sem token, o step 6 vai pelo `screen-drawer`.")


def capacidade_figma_mcp() -> dict:
    """Escrever no Figma exige o MCP, e só a sessão sabe se ele existe.

    Esta função existe porque a anterior não podia servir às duas ações. Na
    2.20.0 eu fiz `capacidade_figma()` detectar o token da REST — conserto certo
    para a LEITURA — e a ação `figma_escrita`, que herdava dali, passou a
    responder:

        [sim ] figma_escrita   token em ~/.config/... — leitura por REST
                      política: on · exigido pelo projeto

    Um token prova leitura. Não diz nada sobre o `use_figma`, que é o único
    caminho de escrita. A frente do app bateu nisso em 08/09/2026, no step
    6: o portão da política abria, e nada conseguia executar. Ela conferiu antes
    de agir; se tivesse acreditado na linha, teria prometido publicar uma tela.

    `None` aqui é a resposta honesta, e é diferente de `False`: não é "não dá",
    é "este processo não tem como saber". Quem sabe é a sessão, olhando as
    próprias ferramentas.
    """
    return {
        "disponivel": None,  # só a sessão sabe
        "detalhe": "escrever exige o MCP da Figma — confirme na sessão",
        "como_descobrir": "Procure a ferramenta `use_figma` (ou `mcp__figma__*`) "
                          "entre as suas. Se não houver, não há como escrever, e "
                          "a política do projeto não muda isso.",
        "aviso": "Política `on` autoriza OFERECER, não escrever. O consentimento "
                 "de quem está na sessão se pede toda vez — e não se pede quando "
                 "não há com o que executar.",
        "fallback": "Sem MCP, o step 6 fecha normalmente sem publicar: o "
                    "entregável é o protótipo no repositório. Declare no "
                    "artefato de decisões de UX e na nota do `avancar`.",
        "orcamentos": ORCAMENTO_FIGMA_MCP,
        "estrategia": {
            "antes do primeiro traço": "Sonda de reconhecimento, página própria, "
                                       "gate contra a linha de base — "
                                       "`references/specialties/figma-writing.md`. "
                                       "Nenhum passo é opcional.",
            "nunca": "Página que o UX mantém. Arquivo de Figma não tem "
                     "`git revert`.",
        },
    }


def capacidade_grafo(agents: Path) -> dict:
    """Grafo de conhecimento do repositório (graphify), se houver.

    É acelerador, nunca dependência. O pacote precisa funcionar inteiro com
    zero instalação — é o que permite zipar e mandar. Quando o grafo existe e
    está fresco, ele responde barato o que o mapa do terreno não alcança:
    travessia transitiva, caminho entre dois conceitos, comunidades.

    O que ele devolve é PISTA, nunca evidência. Ver
    `references/knowledge-graph.md`.
    """
    projeto = raiz_de_trabalho(agents)
    tem_binario = shutil.which("graphify") is not None
    grafo = projeto / "graphify-out" / "graph.json"
    # O grafo não é versionado (`graphify-out/` vai no .gitignore), então ele
    # mora na árvore principal e uma worktree nasce sem ele. Até 2.53.0 esta
    # função olhava só a worktree — que é onde os times rodam — e o fluxo dizia
    # "sem grafo" com o grafo a um diretório de distância. O frescor continua
    # medido na árvore do chamador: commit da branch depois do grafo o envelhece.
    emprestado = False
    if not grafo.exists():
        principal = raiz_do_projeto(agents) / "graphify-out" / "graph.json"
        if principal.exists():
            grafo, emprestado = principal, True

    if not tem_binario and not grafo.exists():
        return {
            "disponivel": False,
            "detalhe": "graphify não instalado e sem grafo neste projeto",
            "nota": "Opcional. O fluxo inteiro funciona sem ele — o mapa do "
                    "terreno (tools/briefing/domain.py) não depende de nada.",
            "como_instalar": "uv tool install graphifyy && graphify .",
        }

    if not grafo.exists():
        return {
            "disponivel": False,
            "detalhe": "graphify instalado, sem grafo neste projeto",
            "como_construir": "graphify . — extração de código é AST "
                              "determinística, sem LLM e sem chave de API",
        }

    idade = grafo.stat().st_mtime
    ultimo = _comando("git", "-C", str(projeto), "log", "-1", "--format=%ct")[1]
    mudados = []
    try:
        desde = datetime.fromtimestamp(idade).strftime("%Y-%m-%dT%H:%M:%S")
        ok_cmd, saida = _comando("git", "-C", str(projeto), "log", "--name-only",
                                 "--format=", f"--since={desde}")
        if ok_cmd:
            mudados = sorted({l for l in saida.splitlines() if l.strip()})
    except (OSError, ValueError):
        pass

    fresco = True
    if ultimo.isdigit() and float(ultimo) > idade:
        fresco = False

    dados = {
        "disponivel": True,
        "detalhe": f"grafo em {grafo.parent.name}/"
                   f"{' da árvore principal' if emprestado else ''}, "
                   f"{'fresco' if fresco else 'DESATUALIZADO'}",
        "caminho": str(grafo),
        "atualizado_em": datetime.fromtimestamp(idade).strftime("%Y-%m-%d %H:%M"),
        "regra": "PISTA, não evidência. Confirme no arquivo antes de citar.",
    }
    if not fresco:
        dados["aviso"] = (
            f"O grafo é anterior ao último commit. {len(mudados)} arquivo(s) "
            "mudaram desde então. Rode `graphify update .` ANTES de consultar, "
            "ou não consulte: um grafo velho responde com confiança sobre código "
            "que não existe mais."
        )
        if mudados[:8]:
            dados["mudaram_desde"] = ", ".join(mudados[:8])
    return dados


def capacidade_navegador() -> dict:
    """Para renderizar o protótipo e conferir as telas."""
    return {
        "disponivel": None,
        "detalhe": "Depende da sessão ter as ferramentas de preview.",
        "fallback": "Sem navegador, entregue o protótipo sem screenshot e diga "
                    "que a conferência visual não foi feita. Não afirme que a "
                    "tela está correta sem tê-la visto.",
    }


def capacidade_dependencias(agents: Path) -> dict:
    """As dependências do projeto estão instaladas AQUI?

    Uma worktree nova não carrega `node_modules`, e o fluxo assume ambiente
    pronto. Pior: quando a worktree fica dentro do repositório, o Node resolve
    subindo a árvore e encontra o `node_modules` do principal — então `npm
    install` diz "up to date" sem instalar nada, e só o primeiro comando que
    procura um pacote em `<raiz>/node_modules` revela o problema.
    """
    raiz = raiz_de_trabalho(agents)
    manifestos = [p for p in raiz.rglob("package.json")
                  if "node_modules" not in p.parts
                  and len(p.relative_to(raiz).parts) <= 2]
    if not manifestos:
        return {"disponivel": None, "detalhe": "projeto sem package.json",
                "nota": "Se a stack não é Node, confira as dependências dela "
                        "antes de prometer que os gates rodam."}
    faltando = [str(m.parent.relative_to(raiz) or ".")
                for m in manifestos if not (m.parent / "node_modules").is_dir()]
    if not faltando:
        return {"disponivel": True,
                "detalhe": f"{len(manifestos)} pacote(s) com node_modules"}
    return {
        "disponivel": False,
        "detalhe": "sem node_modules em: " + ", ".join(faltando),
        "fallback": "Os gates NÃO rodam. Não prometa que rodaram, e não conclua "
                    "sobre o que não conseguiu executar.",
        "como_resolver": " && ".join(f"npm --prefix {d} install" for d in faltando),
        "aviso": "`npm install` pode responder 'up to date' sem instalar, quando "
                 "a worktree está dentro do repositório e o Node acha o "
                 "node_modules do principal subindo a árvore. Confira o "
                 "diretório, não a mensagem.",
    }


def capacidade_gates(agents: Path) -> dict:
    try:
        import config as cfg
        gates = cfg.obter("gates", {}, agents) or {}
    except Exception as exc:
        return {"disponivel": False, "detalhe": f"config ilegível: {exc}"}
    declarados = {k: v for k, v in gates.items() if v}
    if not declarados:
        return {
            "disponivel": False,
            "detalhe": "nenhum gate declarado",
            "fallback": "O quality-reviewer improvisa o que der para exercitar "
                        "— e reporta a ausência de gate como achado, porque um "
                        "projeto sem portão é risco de qualidade por si só.",
        }
    return {"disponivel": True, "detalhe": ", ".join(sorted(declarados)),
            "comandos": declarados}


def capacidade_git(agents: Path) -> dict:
    raiz = raiz_de_trabalho(agents)
    ok, _ = _comando("git", "-C", str(raiz), "rev-parse", "--git-dir")
    if not ok:
        return {"disponivel": False, "detalhe": "não é repositório Git"}
    ferramentas = [f for f in ("gh", "glab", "az") if shutil.which(f)]
    try:
        import config as cfg
        skill = cfg.obter("git.skill", "", agents)
    except Exception:
        skill = ""
    return {
        "disponivel": True,
        "detalhe": f"CLIs: {', '.join(ferramentas) or 'nenhuma'}",
        "skill_do_projeto": skill or None,
        "fallback": None if skill else
        "Sem skill de Git declarada, o step 1 assume o papel inteiro — ver o "
        "comportamento padrão no SKILL.md dele.",
    }


def capacidade_steps(agents: Path) -> dict:
    """Quais steps este projeto declarou usar."""
    from flow_state import STEPS, steps_assets, steps_desligados
    assets = steps_assets(agents)
    desligados = steps_desligados(agents)
    return {
        "disponivel": True,
        "detalhe": f"{len(assets)} de {len(STEPS)} steps assets",
        "assets": assets,
        "desligados": {str(n): STEPS[n]["nome"] for n in desligados},
    }


# ---------------------------------------------------------------------- política
#
# Duas perguntas diferentes, e elas divergem:
#
#   PODER    esta máquina, esta conta, este seat conseguem?  (as funções acima)
#   POLÍTICA este projeto QUER?                              (`[capacidades]`)
#
# O Figma é o caso que obriga a separação: o MCP pode estar autenticado — poder
# sim — e o projeto continuar não querendo que ninguém escreva no arquivo que o
# UX mantém. Sem este eixo, entre "consegue" e "faz" havia só uma frase de skill
# pedindo autorização: negociação em tempo de execução, não política de projeto.
#
# A lista é FECHADA de propósito. Chave fora dela é quase sempre erro de
# digitação, e só com lista fechada dá para provar que cada ação é lida por
# alguma skill. Ver `references/capacidades.md`.

ACOES = {
    "grafo": "auto",
    "figma_leitura": "auto",
    "figma_escrita": "off",   # nasce off: escrever no arquivo de outra pessoa
    "navegador": "auto",
}
VALORES = ("auto", "on", "off")

# Ações cujo valor não é auto/on/off: elas escolhem ENTRE coisas, e não se
# ligam ou desligam. A `perna_sombra` (2.55.0) escolhe o modelo da sombra. Fora
# desta tabela, o doutor acusava `perna_sombra = "sonnet"`, o valor que liga a
# ação, como chave desconhecida.
ACOES_DE_ESCOLHA = {
    "perna_sombra": ("off", "sonnet"),
}


def politica(acao: str, agents: Path | None = None) -> str:
    """O que o projeto declarou para esta ação. Ausente = o padrão do pacote."""
    if acao not in ACOES:
        raise FlowStateError(
            f"Ação desconhecida: {acao}. A lista é fechada: "
            f"{', '.join(sorted(ACOES))}."
        )
    # Sem `config.toml` valem os padrões do pacote — a mesma tolerância do
    # `steps_assets`, e a razão de o pacote poder ser zipado e rodar sem nada
    # declarado. Um projeto sem config não fica sem política: fica com a nossa.
    try:
        import config as _cfg  # tardio: config.py importa deste pacote
        bruto = _cfg.obter(f"capacidades.{acao}", ACOES[acao], agents)
    except FlowStateError:
        bruto = ACOES[acao]
    valor = str(bruto).strip().lower()
    if valor not in VALORES:
        raise FlowStateError(
            f"`capacidades.{acao} = {bruto!r}` não é um valor válido. "
            f"Use um de: {', '.join(VALORES)}."
        )
    return valor


def efetivo(acao: str, disponivel: bool | None, agents: Path | None = None) -> dict:
    """Cruza poder e política, e devolve a decisão junto com o porquê.

    `permitido` é a resposta curta para quem só quer saber se pode agir.
    `porque` existe porque um "não" sem motivo faz a sessão tentar de novo por
    outro caminho — e a razão muda o que ela deve fazer: falta de acesso pede
    fallback, política pede parar e declarar.
    """
    pol = politica(acao, agents)
    if pol == "off":
        return {"politica": pol, "disponivel": disponivel, "permitido": False,
                "porque": "desligado no config do projeto"}
    if disponivel is False:
        return {"politica": pol, "disponivel": disponivel, "permitido": False,
                "porque": ("exigido em `on` e indisponível nesta máquina"
                           if pol == "on" else
                           "indisponível nesta máquina — degrade e declare")}
    # `None` não é `True`. Devolver `permitido: True` para capacidade DESCONHECIDA
    # imprimia `[sim ]` — e foi assim que uma frente leu "pode escrever" onde o
    # certo era "a política deixa; veja se você tem com o quê". `?` é a resposta,
    # e ela manda a sessão confirmar em vez de agir.
    if disponivel is None:
        return {"politica": pol, "disponivel": None, "permitido": None,
                "porque": ("exigido pelo projeto — confirme a capacidade na sessão"
                           if pol == "on" else
                           "a política deixa; confirme a capacidade na sessão")}
    return {"politica": pol, "disponivel": disponivel, "permitido": True,
            "porque": ("exigido pelo projeto" if pol == "on"
                       else "usa se der, e declara quando não der")}


def acoes_desligadas(agents: Path | None = None) -> list[str]:
    return [a for a in sorted(ACOES) if politica(a, agents) == "off"]


def avisar_desligadas(agents: Path | None = None) -> list[str]:
    """O que precisa acompanhar a atividade, no mesmo idioma dos steps.

    Ação desligada não é falha — é escolha. Mas some do relatório se ninguém
    disser, e aí a entrega parece completa quando não é.
    """
    desligadas = acoes_desligadas(agents)
    if not desligadas:
        return []
    return ["AÇÃO DESLIGADA NO PROJETO: " + ", ".join(desligadas)
            + ". Não é falha, é escolha declarada — e ela acompanha a "
              "atividade e todo relatório dela, como step desligado acompanha."]


def coletar() -> dict:
    agents = resolve_agents_dir()
    caps = {
        "python": capacidade_python(),
        "git": capacidade_git(agents),
        "dependencias": capacidade_dependencias(agents),
        "gates": capacidade_gates(agents),
        "relatorio": capacidade_relatorio(),
        "figma": capacidade_figma(),
        "figma_mcp": capacidade_figma_mcp(),
        "grafo": capacidade_grafo(agents),
        "navegador": capacidade_navegador(),
        "steps": capacidade_steps(agents),
    }
    # A política mora por AÇÃO, e uma capacidade detectada pode servir a duas:
    # o Figma é um arquivo só, e ler e escrever são decisões separadas.
    #
    # A AÇÃO herda o que a capacidade descobriu. Sem isso, quem roda
    # `capabilities.py figma_leitura` — que é exatamente o que a skill do step 6
    # manda rodar — via só a política, e nada sobre como ler nem sobre o que
    # fazer quando não dá. Foi assim que uma frente irmã leu `[sim]` como
    # disponibilidade, tentou ler sem ter com o quê, e caiu no navegador.
    HERDA = ("detalhe", "nota", "aviso", "como_resolver", "fallback", "comandos",
             "estrategia")
    # `figma_escrita` NÃO bebe de `figma`: o token que a leitura detecta não diz
    # nada sobre o MCP, e herdar dali fazia a escrita responder `[sim]` com um
    # detalhe que dizia "leitura por REST". Duas ações, duas fontes.
    for acao, de_onde in (("grafo", "grafo"), ("figma_leitura", "figma"),
                          ("figma_escrita", "figma_mcp"),
                          ("navegador", "navegador")):
        fonte = caps.get(de_onde, {})
        caps[acao] = dict(caps.get(acao, {}), **efetivo(acao, fonte.get("disponivel"),
                                                        agents))
        for chave in HERDA:
            if fonte.get(chave) and chave not in caps[acao]:
                caps[acao][chave] = fonte[chave]
        caps[acao].setdefault("detalhe", f"política do projeto para {acao}")
    return {
        "agents": str(agents),
        "projeto": str(raiz_do_projeto(agents)),
        "trabalhando_em": str(raiz_de_trabalho(agents)),
        "capacidades": caps,
        "acoes_desligadas": acoes_desligadas(agents),
        "avisos": avisar_desligadas(agents),
    }


def imprimir(dados: dict, apenas: str | None = None) -> None:
    caps = dados["capacidades"]
    if apenas:
        if apenas not in caps:
            raise FlowStateError(
                f"Capacidade desconhecida: {apenas}. "
                f"Use uma de: {', '.join(caps)}."
            )
        caps = {apenas: caps[apenas]}
    else:
        print(f"Projeto:     {dados['projeto']}")
        if dados["trabalhando_em"] != dados["projeto"]:
            print(f"Worktree:    {dados['trabalhando_em']}")
        print()

    for nome, info in caps.items():
        # Onde há política, é ela que decide o marcador: "o MCP funciona" não
        # responde a pergunta que a sessão faz, que é "posso agir?".
        decide = info["permitido"] if "permitido" in info else info.get("disponivel")
        marca = {True: "sim ", False: "NÃO ", None: "?   "}[decide]
        print(f"  [{marca}] {nome:<14} {info.get('detalhe', '')}")
        if "permitido" in info:
            print(f"                 política: {info['politica']} · "
                  f"{info['porque']}")
        for chave in ("nota", "aviso", "fallback", "como_resolver",
                      "como_descobrir", "skill_do_projeto"):
            if info.get(chave):
                print(f"             {chave}: {info[chave]}")
        for chave in ("orcamentos", "orcamentos_do_mcp", "estrategia",
                      "comandos", "desligados"):
            if info.get(chave):
                print(f"             {chave}:")
                for k, v in info[chave].items():
                    print(f"               {k}: {v}")
        if info.get("assets"):
            print(f"             assets: {info['assets']}")

    if not apenas:
        for aviso in dados.get("avisos", []):
            print(f"\n  {aviso}")
        print("\nNenhum 'NÃO' acima impede o fluxo. Cada um tem caminho "
              "alternativo previsto,\ne a regra é sempre a mesma: degrade e "
              "diga o que não foi feito, nunca finja.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="capabilities.py",
        description="O que esta máquina e este usuário conseguem fazer.")
    p.add_argument("capacidade", nargs="?",
                   help="uma só: python, git, gates, relatorio, figma, "
                        "navegador, steps — ou uma AÇÃO: grafo, "
                        "figma_leitura, figma_escrita")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        dados = coletar()
        if args.json:
            saida = (dados if not args.capacidade
                     else dados["capacidades"].get(args.capacidade))
            if saida is None:
                raise FlowStateError(f"Capacidade desconhecida: {args.capacidade}.")
            print(json.dumps(saida, indent=2, ensure_ascii=False))
        else:
            imprimir(dados, args.capacidade)
        return 0
    except FlowStateError as exc:
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
