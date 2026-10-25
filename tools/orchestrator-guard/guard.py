#!/usr/bin/env python3
"""Trava da janela orquestradora: ela distribui steps e não faz o trabalho deles.

Três entradas, todas lidas do JSON que o Claude Code manda no stdin:

    guard.py prompt   UserPromptSubmit  a PESSOA liga ou desliga o modo
    guard.py pre      PreToolUse        recusa, na janela marcada, o que é trabalho de step;
                                        e, em qualquer janela, editar o contrato de casos
    guard.py retomou  SessionStart      depois de compactar ou retomar, devolve regras e estado

Fora de uma janela marcada, e em qualquer chamada de subagente, sai calado:
custo zero de contexto para quem não usa o modo.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PACOTE = Path(__file__).resolve().parents[2]
FLOW_STATE = PACOTE / "tools" / "flow-state" / "flow_state.py"
MARCAS = Path(os.environ.get("ELCAMARGO_ORQ_DIR")
              or Path.home() / ".claude" / "elcamargo-flow" / "orquestradoras")

# Só a mensagem digitada pela pessoa liga ou desliga. O modelo não digita
# mensagem de usuário, então não tem como sair da trava sozinho.
COMANDO = re.compile(r"^\s*/(?:elcamargo-ai-flow:)?elcamargo-ai-flow\s+orquestrar(\s+sair)?\b")

REGRAS = """[orquestradora] Esta janela ORQUESTRA: distribui steps e não faz o trabalho deles.
- Estado: `python3 {f} listar` e `status <id>`. Nunca a memória da conversa.
- Um step por disparo: Agent com subagent_type `elcamargo-ai-flow:elcamargo-step-runner`,
  prompt com a atividade, o step e a worktree. Várias atividades: em segundo plano.
- Leia só o retorno curto. Código, navegador e espiar frente (tail/ls/sleep): a trava recusa.
- Retorno com pendência ou portão: pergunte à pessoa citando o id, e grave a decisão com
  `flow_state nota <id>` ANTES de seguir. O que não está em arquivo some na compactação.
- No máximo um step 9 rodando por vez.
- Retorno com 403 do guardrail: não retome. `doc_mask.py devolucoes --raiz <worktree>` e
  disparo novo apontando a pasta que ele imprimir; a pasta você não lê.
- Sair do modo: só a pessoa, com `/elcamargo-ai-flow orquestrar sair`."""

SAIR = "Sair do modo é da pessoa: `/elcamargo-ai-flow orquestrar sair`."

# Primeiro comando de um pipeline que é trabalho de step: ler código, espiar,
# esperar, construir. Depois de um `|` o mesmo comando é filtro e passa — cortar
# saída com `| head` é o que se quer aqui.
LEITURA = re.compile(r"^(?:sudo\s+)?(cat|head|tail|less|more|sed|awk|grep|egrep|rg|find|wc|stat|"
                     r"diff|sleep|watch|ls|tree|npm|pnpm|yarn|npx|node|bun|jest|vitest|tsc|pytest|"
                     r"docker|make|gradle|mvn|dotnet|curl|wget)\b")
GIT_LEITURA = re.compile(r"^git\s+(?:-C\s+\S+\s+)?(diff|show|blame|grep|cat-file)\b")
LIVRE = (".agents/", ".agents\\", "plugins/cache", "plugins\\cache")
MCP_TRABALHO = re.compile(r"Browser|chrome|figma|Simulator|36bcd1f9", re.I)
ESCRITA = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BUSCA = {"Read", "Grep", "Glob", "NotebookRead"}
CASOS = re.compile(r"(?:^|/)atividades/[^/]+-casos\.json$")


def ler_entrada() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def marca(sessao: str) -> Path:
    return MARCAS / re.sub(r"[^A-Za-z0-9_.-]", "_", sessao)


def marcada(evento: dict) -> bool:
    sessao = evento.get("session_id")
    return bool(sessao) and marca(sessao).exists()


def regras() -> str:
    return REGRAS.format(f=FLOW_STATE)


def estado(cwd: str | None) -> str:
    try:
        saida = subprocess.run([sys.executable, str(FLOW_STATE), "listar"], cwd=cwd or None,
                               capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    linhas = [l for l in saida.splitlines() if l.strip()]
    return "\n".join(linhas[:20])


def cmd_prompt(evento: dict) -> int:
    m = COMANDO.match(evento.get("prompt") or "")
    sessao = evento.get("session_id")
    if not m or not sessao:
        return 0
    if m.group(1):
        marca(sessao).unlink(missing_ok=True)
        print("[orquestradora] Marca retirada: esta janela voltou a ser comum.")
        return 0
    MARCAS.mkdir(parents=True, exist_ok=True)
    marca(sessao).write_text(json.dumps({"cwd": evento.get("cwd")}), encoding="utf-8")
    print(regras())
    return 0


def cmd_retomou(evento: dict) -> int:
    if not marcada(evento):
        return 0
    print(regras())
    atual = estado(evento.get("cwd"))
    if atual:
        print("\nEstado agora (flow_state listar):\n" + atual)
    return 0


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?^\s*\1\s*$", re.S | re.M)
PALAVRA_DE_SHELL = re.compile(r"^(?:do|then|else|time|nohup|exec|!)\s+")


def primeiros_comandos(comando: str) -> list[str]:
    """O primeiro comando de cada pipeline. `a && b | c` devolve `a` e `b`.

    O corpo de heredoc sai antes: é texto (uma mensagem do interfone, um
    script), e uma linha dele começando com `ls` não é comando.
    """
    sem_corpo = HEREDOC.sub("<<HEREDOC\n", comando)
    trechos = [p.split("|")[0].strip() for p in re.split(r"&&|\|\||;|\n", sem_corpo)]
    return [PALAVRA_DE_SHELL.sub("", t) for t in trechos if t]


def motivo_bash(comando: str) -> str | None:
    for trecho in primeiros_comandos(comando):
        if any(livre in trecho for livre in LIVRE) or re.match(r"^cat\s*(<<|>)", trecho):
            continue
        if "watch.py" in trecho:
            return "espiar frente é releitura do contexto inteiro a cada espiada"
        if LEITURA.match(trecho) or GIT_LEITURA.match(trecho):
            return f"`{trecho.split()[0]}` fora de `.agents/` é trabalho de step"
    return None


def motivo(evento: dict) -> str | None:
    nome = evento.get("tool_name") or ""
    entrada = evento.get("tool_input") or {}
    if nome in ("Agent", "Task"):
        tipo = entrada.get("subagent_type") or "general-purpose"
        if tipo.endswith("elcamargo-step-runner"):
            return None
        return (f"`{tipo}` não é o agente de step. Dispare `elcamargo-ai-flow:elcamargo-step-runner`, "
                "um step por disparo, com a atividade e o step no prompt")
    if nome == "Skill":
        skill = (entrada.get("skill") or "").split(":")[-1]
        if skill == "elcamargo-ai-flow" and "sair" not in (entrada.get("args") or ""):
            return None
        return (f"rodar `{skill}` aqui põe o step inteiro no contexto desta janela. "
                "Dispare o step em `elcamargo-ai-flow:elcamargo-step-runner`")
    if nome in BUSCA:
        alvo = " ".join(str(entrada.get(k) or "") for k in ("file_path", "path", "pattern", "notebook_path"))
        if any(livre in alvo for livre in LIVRE):
            return None
        return "ler código é trabalho de step; o estado da atividade está em `.agents/`"
    if nome in ESCRITA:
        return "escrever é trabalho de step; o estado muda pelo `flow_state`"
    if nome in ("WebFetch", "WebSearch"):
        return "pesquisar é trabalho de step"
    if nome.startswith("mcp__") and MCP_TRABALHO.search(nome):
        return "navegador, Figma e simulador são trabalho de step"
    if nome == "Bash":
        return motivo_bash(entrada.get("command") or "")
    return None


def contrato_de_casos(evento: dict) -> bool:
    """Edição à mão do contrato de casos. Quem escreve `passa` é o script."""
    if evento.get("tool_name") not in ESCRITA:
        return False
    entrada = evento.get("tool_input") or {}
    caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
    return bool(CASOS.search(caminho.replace("\\", "/")))


def cmd_pre(evento: dict) -> int:
    # Vale em qualquer janela e dentro de subagente: o step 8 roda justamente
    # num subagente, e é ali que marcar o próprio teste como verde tentaria.
    if contrato_de_casos(evento):
        print("[elcamargo] recusado: o contrato de casos não se edita à mão. "
              "`matrix.py casos gerar|vermelho|verde` escreve, a partir da SDD e da "
              "saída do teste.", file=sys.stderr)
        return 2
    # `agent_id` só vem quando a chamada nasce dentro de um subagente: o
    # step-runner e as frentes trabalham livres, a trava é só da janela.
    if evento.get("agent_id") or not marcada(evento):
        return 0
    razao = motivo(evento)
    if razao is None:
        return 0
    print(f"[orquestradora] recusado: {razao}. {SAIR}", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    acoes = {"prompt": cmd_prompt, "pre": cmd_pre, "retomou": cmd_retomou}
    if len(argv) != 1 or argv[0] not in acoes:
        print("uso: guard.py prompt|pre|retomou  (JSON do hook no stdin)", file=sys.stderr)
        return 1
    return acoes[argv[0]](ler_entrada())


if __name__ == "__main__":
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main(sys.argv[1:]))
