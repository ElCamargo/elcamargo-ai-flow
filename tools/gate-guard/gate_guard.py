#!/usr/bin/env python3
"""Lembrete no fim do step 8: a janela não encerra com portão vermelho calada.

Lê o JSON do Stop ou do SubagentStop no stdin. Se esta sessão está numa
atividade parada no step 8, e o fim da conversa fala dela, e a tabela
Conferências ainda não deixa passar para o 9, sai com 2 e diz o que falta.

A TRAVA DE VERDADE É O `avancar`, que recusa o 8→9 mesmo com `--forcar`. Este
hook só lembra, e lembra UMA VEZ por conjunto de faltas: a janela que parou
para perguntar algo à pessoa encerra de novo e passa. Insistir a cada parada
transformaria uma pergunta legítima num laço de oito continuações.

Sai calado (0) em tudo que não for isso: outro step, outra sessão, janela
orquestradora, projeto sem `.agents`, entrada ilegível. Um lembrete que quebra
a janela por erro próprio é pior que lembrete nenhum.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

PACOTE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACOTE / "tools" / "flow-state"))

MARCAS = Path(os.environ.get("ELCAMARGO_ORQ_DIR")
              or Path.home() / ".claude" / "elcamargo-flow" / "orquestradoras")
# O fim do transcrito basta: o que importa é se a conversa recente é desta
# atividade, não a história inteira da janela.
CAUDA = 400_000


def ler_entrada() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}


def orquestradora(sessao: str) -> bool:
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", sessao)
    return (MARCAS / nome).exists()


def cauda(caminho: str) -> str:
    if not caminho:
        return ""
    try:
        with open(caminho, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - CAUDA))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def frente_do_step_9(tipo: str) -> bool:
    # As frentes de revisão terminam com SubagentStop também; não são do 8.
    return bool(re.search(r"elcamargo-[a-z-]*reviewer$", tipo or ""))


def no_step_8(agents: Path, sessao: str):
    import flow_state as F
    pasta = F.atividades_dir(agents)
    for arq in sorted(pasta.glob("*.md")):
        try:
            atividade = F.Atividade.ler(arq)
        except (F.FlowStateError, OSError, ValueError):
            continue
        meta = atividade.meta
        if str(meta.get("step")) != "8" or meta.get("status") == F.STATUS_CONCLUIDO:
            continue
        if sessao not in str(meta.get("sessoes") or "").split():
            continue
        yield atividade


def ja_lembrado(agents: Path, ident: str, faltas: list[str]) -> bool:
    """Grava a impressão das faltas; True se esta mesma lista já foi dita."""
    import flow_state as F
    impressao = hashlib.sha256("\n".join(faltas).encode()).hexdigest()[:16]
    alvo = F.gates_dir(agents, ident) / ".lembrado"
    try:
        if alvo.read_text(encoding="utf-8").strip() == impressao:
            return True
    except OSError:
        pass
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(impressao, encoding="utf-8")
    except OSError:
        pass
    return False


def principal(evento: dict) -> int:
    if evento.get("stop_hook_active"):
        return 0
    sessao = str(evento.get("session_id") or "")
    if not sessao:
        return 0
    subagente = bool(evento.get("agent_id"))
    if not subagente and orquestradora(sessao):
        return 0  # a orquestradora não roda step; quem roda é o step-runner
    if subagente and frente_do_step_9(str(evento.get("agent_type") or "")):
        return 0
    try:
        if evento.get("cwd"):
            os.chdir(evento["cwd"])
        import flow_state as F
        agents = F.resolve_agents_dir()
    except Exception:
        return 0
    texto = cauda(str(evento.get("agent_transcript_path") or "")
                  if subagente else str(evento.get("transcript_path") or ""))
    avisos = []
    for atividade in no_step_8(agents, sessao):
        ident = atividade.meta["id"]
        if ident not in texto:
            continue  # a sessão passou pela atividade, mas não está nela agora
        try:
            faltas = F.falta_para_sair_do_8(atividade, agents)
        except Exception:
            continue
        if faltas and not ja_lembrado(agents, ident, faltas):
            avisos.append((ident, faltas))
    if not avisos:
        return 0
    linhas = []
    for ident, faltas in avisos:
        linhas.append(f"[elcamargo] {ident} está no step 8 e a tabela Conferências "
                      "ainda não deixa passar para o 9:")
        linhas += [f"  - {f}" for f in faltas]
    linhas += [
        "Rode `flow_state gates <id>` e corrija o que ficar vermelho. Portão que "
        "não se aplica a esta entrega: `flow_state conferencia <id> --ferramenta "
        "gate:<nome> --veredicto nao-coberta --detalhe '<por quê>'`.",
        "Se você parou para perguntar algo à pessoa, encerre de novo: este aviso "
        "não se repete para as mesmas faltas. O `avancar` para o 9 continua "
        "recusando enquanto elas existirem.",
    ]
    print("\n".join(linhas), file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    try:
        sys.exit(principal(ler_entrada()))
    except Exception:
        sys.exit(0)
