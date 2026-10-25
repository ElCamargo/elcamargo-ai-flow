#!/usr/bin/env python3
"""Fumaça da trava da orquestradora: o JSON que o Claude Code manda, e a saída."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "guard.py"
falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)


def rodar(acao: str, evento: dict, marcas: str) -> tuple[int, str, str]:
    env = dict(os.environ, ELCAMARGO_ORQ_DIR=marcas)
    r = subprocess.run([sys.executable, str(GUARD), acao], input=json.dumps(evento),
                       capture_output=True, text=True, env=env, timeout=30)
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    marcas = tempfile.mkdtemp(prefix="orq-")
    S = {"session_id": "sessao-A", "cwd": marcas}
    pre = lambda nome, entrada, **extra: rodar("pre", {**S, "tool_name": nome, "tool_input": entrada, **extra}, marcas)

    print("Janela comum: nada muda")
    rc, out, err = pre("Read", {"file_path": "/repo/src/app.ts"})
    checar(rc == 0 and not out and not err, "Read de código passa calado")
    rc, out, _ = rodar("retomou", {**S, "source": "compact"}, marcas)
    checar(rc == 0 and not out, "compactação não imprime nada")
    rc, out, _ = rodar("prompt", {**S, "prompt": "oi, tudo bem?"}, marcas)
    checar(rc == 0 and not out, "mensagem comum não marca")

    print("\nA pessoa liga o modo")
    rc, out, _ = rodar("prompt", {**S, "prompt": "/elcamargo-ai-flow orquestrar"}, marcas)
    checar(rc == 0 and "ORQUESTRA" in out and "elcamargo-step-runner" in out,
           "o comando marca e imprime as regras")
    checar((Path(marcas) / "sessao-A").exists(), "a marca fica em arquivo, fora da conversa")

    print("\nRecusa o que é trabalho de step")
    for nome, entrada, descricao in [
        ("Read", {"file_path": "/repo/src/app.ts"}, "ler código"),
        ("Grep", {"pattern": "foo", "path": "/repo/src"}, "buscar em código"),
        ("Edit", {"file_path": "/repo/.agents/x.md"}, "editar, mesmo em .agents"),
        ("Agent", {"subagent_type": "general-purpose", "prompt": "steps 2 a 4"}, "general-purpose conduzindo step"),
        ("Agent", {"prompt": "sem tipo"}, "Agent sem tipo, que vira general-purpose"),
        ("Skill", {"skill": "elcamargo-ai-flow:elcamargo-system-analyst"}, "skill de step na própria janela"),
        ("Skill", {"skill": "elcamargo-ai-flow", "args": "orquestrar sair"}, "o modelo tentando sair sozinho"),
        ("mcp__Claude_Browser__navigate", {"url": "http://localhost"}, "navegador"),
        ("WebFetch", {"url": "https://x"}, "pesquisa"),
        ("Bash", {"command": "grep -rn foo src/"}, "grep em código"),
        ("Bash", {"command": "tail -20 /tmp/frente.output"}, "espiar frente com tail"),
        ("Bash", {"command": "sleep 60 && ls"}, "esperar com sleep"),
        ("Bash", {"command": "cd /repo && npm test"}, "rodar suíte"),
        ("Bash", {"command": "git diff main -- src/"}, "ler código pelo git diff"),
        ("Bash", {"command": "python3 $P/tools/watch/watch.py"}, "watch.py"),
    ]:
        rc, _, err = pre(nome, entrada)
        checar(rc == 2 and "recusado" in err, f"recusa: {descricao}")
    rc, _, err = pre("Read", {"file_path": "/repo/src/app.ts"})
    checar("orquestrar sair" in err, "a recusa diz como sair, e que é da pessoa")

    print("\nDeixa passar o que é de quem orquestra")
    for nome, entrada, descricao in [
        ("Agent", {"subagent_type": "elcamargo-ai-flow:elcamargo-step-runner"}, "disparar step-runner"),
        ("Skill", {"skill": "elcamargo-ai-flow"}, "a porta do fluxo"),
        ("Read", {"file_path": "/repo/.agents/atividades/1054.md"}, "ler o estado da atividade"),
        ("Bash", {"command": "python3 $F listar"}, "flow_state"),
        ("Bash", {"command": "interfone caixa backoffice --sessao x | head -5"}, "interfone, com filtro depois do pipe"),
        ("Bash", {"command": "git status --short && git log --oneline -3"}, "git status e log"),
        ("Bash", {"command": 'PACOTE="${CLAUDE_PLUGIN_ROOT:-}"\n[ -d "$PACOTE" ] || '
                  'PACOTE="$(ls -d "$HOME"/.claude/plugins/cache/*/elcamargo-ai-flow/*/ 2>/dev/null | sort -V | tail -1)"'},
         "o resolvedor do pacote, que tem ls e tail"),
        ("Bash", {"command": "interfone enviar a b 'x' <<'EOF'\nls tudo\nfind coisa\nEOF"},
         "mensagem por heredoc, com linha começando por ls"),
        ("Bash", {"command": "cat <<'EOF' | interfone enviar a b 'x'\ngrep aqui\nEOF"}, "cat de heredoc"),
        ("AskUserQuestion", {}, "perguntar à pessoa"),
        ("mcp__ccd_session__mark_chapter", {}, "ferramenta da app que não é trabalho"),
    ]:
        rc, _, err = pre(nome, entrada)
        checar(rc == 0 and not err, f"passa: {descricao}")

    print("\nSubagente trabalha livre, mesmo na janela marcada")
    rc, _, err = pre("Read", {"file_path": "/repo/src/app.ts"}, agent_id="a123")
    checar(rc == 0 and not err, "chamada com agent_id passa")

    print("\nCompactação devolve as regras e o estado")
    rc, out, _ = rodar("retomou", {**S, "source": "compact"}, marcas)
    checar(rc == 0 and "ORQUESTRA" in out and "flow_state nota" in out, "regras voltam depois de compactar")
    rc, out, _ = rodar("retomou", {"session_id": "outra", "source": "compact"}, marcas)
    checar(not out, "outra sessão, sem marca, não recebe nada")

    print("\nA pessoa desliga")
    rc, out, _ = rodar("prompt", {**S, "prompt": "/elcamargo-ai-flow orquestrar sair"}, marcas)
    checar("retirada" in out and not (Path(marcas) / "sessao-A").exists(), "o comando de sair tira a marca")
    rc, _, err = pre("Read", {"file_path": "/repo/src/app.ts"})
    checar(rc == 0 and not err, "depois de sair, ler código volta a passar")

    print("\nO contrato de casos não se edita à mão, em janela nenhuma")
    contrato = "/repo/.agents/atividades/X1-casos.json"
    rc, _, err = pre("Edit", {"file_path": contrato}, agent_id="dev")
    checar(rc == 2 and "matrix.py casos" in err, "subagente editando o contrato: recusado")
    rc, _, _ = rodar("pre", {"session_id": "sessao-B", "cwd": marcas, "tool_name": "Write",
                             "tool_input": {"file_path": contrato}}, marcas)
    checar(rc == 2, "janela comum escrevendo o contrato: recusado")
    rc, _, _ = pre("Read", {"file_path": contrato}, agent_id="dev")
    checar(rc == 0, "ler o contrato passa")
    rc, _, _ = pre("Edit", {"file_path": "/repo/.agents/atividades/X1.md"}, agent_id="dev")
    checar(rc == 0, "outro arquivo de atividade, dentro de subagente, passa")

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("tudo passou")
    return 0


if __name__ == "__main__":
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
