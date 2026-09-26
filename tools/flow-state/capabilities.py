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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from flow_state import (FlowStateError, raiz_de_trabalho,  # noqa: E402
                        raiz_do_projeto, resolve_agents_dir)

# Figma read-tool budgets, by seat. From the official rate-limit table. The
# deciding factor is the SEAT, not the plan — and the limit follows the plan
# where the file lives, not where the user is.
ORCAMENTO_FIGMA = {
    "dev": "200-600 chamadas por dia",
    "full": "200-600 chamadas por dia",
    "collab": "6-20 chamadas por MÊS",
    "view": "6-20 chamadas por MÊS",
}


def _comando(*args: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
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
    """O gargalo real do step 6, e o mais fácil de descobrir tarde demais.

    Não dá para consultar o seat daqui: quem responde `whoami` é o MCP, dentro
    da sessão. O que este comando faz é dizer o que a sessão precisa perguntar,
    e qual estratégia cada resposta implica.
    """
    return {
        "disponivel": None,  # só a sessão sabe
        "detalhe": "Descubra na sessão, antes de qualquer leitura.",
        "como_descobrir": "Chame o tool `whoami` do MCP da Figma. Ele devolve "
                          "plano e seat.",
        "orcamentos": ORCAMENTO_FIGMA,
        "estrategia": {
            "dev/full": "Orçamento largo. Navegue com get_metadata, leia o que "
                        "precisar, baixe assets, use get_code_connect_map.",
            "collab/view": "Orçamento de 6 a 20 chamadas por MÊS. Uma navegação, "
                           "uma leitura da tela alvo, e pare. Nunca varra o "
                           "arquivo. Considere pedir export manual ao usuário.",
            "sem_mcp": "Vá pelo screen-drawer. Não é degradação do fluxo: é o "
                       "outro caminho previsto do step 6.",
        },
        "aviso": "O limite segue o plano onde o ARQUIVO mora, não o seu seat.",
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
        "detalhe": f"grafo em {grafo.parent.name}/, "
                   f"{'fresco' if fresco else 'DESATUALIZADO'}",
        "atualizado_em": datetime.fromtimestamp(idade).strftime("%Y-%m-%d %H:%M"),
        "regra": "PISTA, não evidência. Confirme no arquivo antes de citar.",
    }
    if not fresco:
        dados["aviso"] = (
            f"O grafo é anterior ao último commit. {len(mudados)} arquivo(s) "
            "mudaram desde então. Rode `graphify . --update` ANTES de consultar, "
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


def coletar() -> dict:
    agents = resolve_agents_dir()
    return {
        "agents": str(agents),
        "projeto": str(raiz_do_projeto(agents)),
        "trabalhando_em": str(raiz_de_trabalho(agents)),
        "capacidades": {
            "python": capacidade_python(),
            "git": capacidade_git(agents),
            "dependencias": capacidade_dependencias(agents),
            "gates": capacidade_gates(agents),
            "relatorio": capacidade_relatorio(),
            "figma": capacidade_figma(),
        "grafo": capacidade_grafo(agents),
            "navegador": capacidade_navegador(),
            "steps": capacidade_steps(agents),
        },
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
        marca = {True: "sim ", False: "NÃO ", None: "?   "}[info.get("disponivel")]
        print(f"  [{marca}] {nome:<10} {info.get('detalhe', '')}")
        for chave in ("nota", "aviso", "fallback", "como_resolver",
                      "como_descobrir", "skill_do_projeto"):
            if info.get(chave):
                print(f"             {chave}: {info[chave]}")
        for chave in ("orcamentos", "estrategia", "comandos", "desligados"):
            if info.get(chave):
                print(f"             {chave}:")
                for k, v in info[chave].items():
                    print(f"               {k}: {v}")
        if info.get("assets"):
            print(f"             assets: {info['assets']}")

    if not apenas:
        print("\nNenhum 'NÃO' acima impede o fluxo. Cada um tem caminho "
              "alternativo previsto,\ne a regra é sempre a mesma: degrade e "
              "diga o que não foi feito, nunca finja.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="capabilities.py",
        description="O que esta máquina e este usuário conseguem fazer.")
    p.add_argument("capacidade", nargs="?",
                   help="uma só: python, git, gates, relatorio, figma, "
                        "navegador, steps")
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
    sys.exit(main())
