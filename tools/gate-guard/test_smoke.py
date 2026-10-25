#!/usr/bin/env python3
"""Fumaça do lembrete do step 8: o JSON do Stop, e quando ele fala ou cala."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
GUARD = AQUI / "gate_guard.py"
FLOW = AQUI.parent / "flow-state" / "flow_state.py"
falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)


def main() -> int:
    raiz = Path(tempfile.mkdtemp(prefix="gate-guard-"))
    agents = raiz / ".agents"
    (agents / "atividades").mkdir(parents=True)
    (agents / "config.toml").write_text(
        '[projeto]\nnome = "t"\n[gates]\nlint = "true"\n', encoding="utf-8")
    (agents / ".sessao-atual").write_text("sessao-A", encoding="utf-8")
    marcas = raiz / "marcas"
    marcas.mkdir()
    env = dict(os.environ, ELCAMARGO_AGENTS_DIR=str(agents),
               ELCAMARGO_ORQ_DIR=str(marcas))

    def flow(*args: str) -> None:
        subprocess.run([sys.executable, str(FLOW), *args], env=env, cwd=raiz,
                       capture_output=True, text=True, check=True, timeout=60)

    def stop(evento: dict) -> tuple[int, str]:
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(evento),
                           capture_output=True, text=True, env=env, timeout=30)
        return r.returncode, r.stderr

    flow("iniciar", "G1", "--titulo", "t", "--trilha", "curta")
    flow("avancar", "G1", "--step", "8", "--forcar", "--nota", "teste")
    transcrito = raiz / "t.jsonl"
    transcrito.write_text('{"msg": "implementei o G1"}\n', encoding="utf-8")
    S = {"session_id": "sessao-A", "cwd": str(raiz), "transcript_path": str(transcrito)}

    print("Cala quando não é com ela")
    checar(stop({**S, "stop_hook_active": True})[0] == 0, "continuação de hook passa")
    checar(stop({**S, "session_id": "outra"})[0] == 0, "outra sessão passa")
    vazio = raiz / "vazio.jsonl"
    vazio.write_text("{}\n", encoding="utf-8")
    checar(stop({**S, "transcript_path": str(vazio)})[0] == 0,
           "conversa que não fala da atividade passa")
    checar(stop({**S, "agent_id": "x", "agent_type": "elcamargo-ai-flow:elcamargo-code-reviewer",
                 "agent_transcript_path": str(transcrito)})[0] == 0,
           "frente do step 9 passa")
    (marcas / "sessao-A").write_text("{}", encoding="utf-8")
    checar(stop(S)[0] == 0, "janela orquestradora passa")
    (marcas / "sessao-A").unlink()
    checar(stop({"session_id": "sessao-A"})[0] == 0 and stop({})[0] == 0,
           "entrada incompleta passa")

    print("\nFala uma vez quando o portão não rodou")
    rc, err = stop({**S, "agent_id": "y", "agent_type": "elcamargo-ai-flow:elcamargo-step-runner",
                    "agent_transcript_path": str(transcrito)})
    checar(rc == 2 and "G1" in err and "`lint` não rodou" in err,
           "step-runner no 8 com portão sem rodar: bloqueia e nomeia")
    checar("encerre de novo" in err, "diz como sair se parou para perguntar")
    checar(stop(S)[0] == 0, "as mesmas faltas não se repetem")

    print("\nCala quando a tabela deixa passar")
    flow("gates", "G1")
    checar(stop(S)[0] == 0, "portão verde: passa")

    if falhas:
        print(f"\n{len(falhas)} falha(s).")
        return 1
    print("\nTudo passou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
