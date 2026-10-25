#!/usr/bin/env python3
"""A âncora: lembra a sessão, a cada mensagem, de onde a atividade está.

Skill é conselho. Uma vez carregada, a sessão anda sozinha, e o arquivo de
estado só é lido quando alguma skill resolve ler — o que na prática significa
que o fluxo é abandonado no meio e ninguém percebe. Foi a reclamação que
originou este arquivo: *"mesmo dizendo que quero analisar os 3 cards ele vai
seguindo e deixa o flow de lado."*

Isto não é mais uma instrução. **Quem executa é o harness**, num hook de
`UserPromptSubmit`, antes de o modelo ver a mensagem. Não tem como esquecer,
porque não depende de lembrar.

É a mesma correção que a tabela de Conferências fez para a conferência mecânica,
e que o `[perfis] comando` fez para "entrar com ator sem a permissão": obrigação
escrita em prosa não acontece; mecanismo acontece.

## O que ele imprime

Nada, quando não há atividade em andamento. **Silêncio é o comportamento
correto na maior parte das sessões** — uma âncora que fala sempre vira ruído, e
ruído se aprende a ignorar.

Uso (o hook chama sem argumento):
    anchor.py
    anchor.py --raiz <dir>
    anchor.py --raiz <dir> --contexto   # PreToolUse de Bash: quem chama o flow_state
"""
from __future__ import annotations

import argparse
import json
import re
import select
import sys
import time
from pathlib import Path

# Um teto para não despejar o board inteiro no contexto a cada mensagem.
TETO = 3


def achar_agents(inicio: Path) -> Path | None:
    for d in [inicio, *inicio.parents]:
        alvo = d / ".agents" / "atividades"
        if alvo.is_dir():
            return d / ".agents"
    return None


def front_matter(texto: str) -> dict[str, str]:
    if not texto.startswith("---\n"):
        return {}
    fim = texto.find("\n---\n", 4)
    if fim == -1:
        return {}
    meta = {}
    for linha in texto[4:fim].splitlines():
        chave, sep, valor = linha.partition(":")
        if sep and not chave[:1].isspace():
            meta[chave.strip()] = valor.strip()
    return meta


def ler_evento() -> dict:
    """O JSON que o harness manda ao hook, ou vazio. Nunca trava, nunca levanta.

    `sys.stdin.read()` sozinho TRAVA quando a entrada é um cano sem dados e sem
    fechar — e este hook roda em TODA mensagem, então travar aqui é travar a
    sessão. `select` com espera zero responde "há byte para ler?" sem bloquear.
    """
    try:
        if sys.stdin.isatty() or not select.select([sys.stdin], [], [], 0)[0]:
            return {}
        bruto = sys.stdin.read()
        evento = json.loads(bruto) if bruto else {}
    except (ValueError, OSError, TypeError):
        return {}
    return evento if isinstance(evento, dict) else {}


def _gravar(alvo: Path, texto: str) -> None:
    try:
        temp = alvo.with_suffix(".tmp")
        temp.write_text(texto, encoding="utf-8")
        temp.replace(alvo)
    except OSError:
        return


def anotar_contexto(agents: Path, evento: dict) -> None:
    """Grava QUAL CONTEXTO está prestes a chamar o `flow_state`.

    Contexto é sessão mais subagente. O `.sessao-atual` não basta para a trava
    do step 9: no modo orquestrador o 8 e o 9 rodam na MESMA sessão, cada um
    num subagente, e isso está certo. O que separa os dois é o `agent_id`, que
    o harness só manda no evento quando a chamada nasce dentro de um subagente
    — e o `UserPromptSubmit`, onde a sessão é anotada, nem roda em subagente.

    Por isso este é PreToolUse de Bash: o registro precisa ser da chamada que
    vem logo depois. Grava em TODO Bash, e não só no que cita o `flow_state`:
    as skills chamam `python3 $F avancar`, e filtrar pelo texto do comando
    deixaria a trava cega justamente no jeito documentado de chamar. O
    `flow_state` desconfia de registro com mais de dois minutos.

    O que ele NÃO resolve: dois contextos chamando o `flow_state` no mesmo
    instante, no mesmo projeto, escrevem um por cima do outro. O erro possível
    é a trava deixar passar, não acusar quem não devia: para acusar, o registro
    teria de vir do contexto que fez o step 8, e esse já terminou.
    """
    if evento.get("tool_name") != "Bash":
        return
    sessao = str(evento.get("session_id") or "").strip()[:64]
    if not sessao:
        return
    _gravar(agents / ".contexto-atual", json.dumps({
        "sessao": sessao,
        "agente": str(evento.get("agent_id") or "").strip()[:64],
        "quando": time.time(),
    }))


def anotar_sessao(agents: Path, evento: dict | None = None) -> None:
    """Grava qual sessão está falando agora, para o `flow_state` saber.

    O hook recebe `session_id` no JSON de entrada — é a única fonte
    **autoritativa** disso: não há variável de ambiente, e adivinhar pelo
    transcrito mais recente seria heurística onde existe registro.

    Por que isso vale um arquivo. Em 11/09/2026 mediu-se que o custo de uma
    revisão inteira foi somado à atividade VIZINHA: o `gitBranch` da sessão era
    a branch em que o checkout principal por acaso estava, e a métrica atribuiu
    por ele. O id da sessão bate com o nome do arquivo de transcrito, exato — e
    é a prova que não depende de onde o checkout está nem de a worktree existir.

    O que ele NÃO resolve: duas sessões no mesmo projeto ao mesmo tempo
    escrevem aqui uma por cima da outra. Cada uma grava no instante em que
    fala, e o `flow_state` lê no instante em que roda — então dentro de um
    turno está certo, e entre turnos de sessões concorrentes pode errar. Por
    isso o que o `flow_state` guarda é uma LISTA: erro aqui acrescenta uma
    sessão à atividade, não troca a dona dela.
    """
    if evento is None:
        evento = ler_evento()
    sessao = str(evento.get("session_id") or "").strip()
    if not sessao:
        return
    _gravar(agents / ".sessao-atual", sessao)


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raiz", default=".")
    p.add_argument("--contexto", action="store_true",
                   help="PreToolUse de Bash: grava quem vai rodar o comando, e só")
    args = p.parse_args(argv)

    if args.contexto:
        # Silêncio sempre: um PreToolUse que fala aparece em toda chamada.
        evento = ler_evento()
        # O `cwd` do evento primeiro: é onde o Bash vai rodar, e uma worktree
        # dentro do projeto acha o `.agents` subindo dela.
        for inicio in (evento.get("cwd") or "", args.raiz):
            agents = achar_agents(Path(inicio).resolve()) if inicio else None
            if agents is not None:
                anotar_contexto(agents, evento)
                break
        return 0

    agents = achar_agents(Path(args.raiz).resolve())
    if agents is None:
        return 0
    anotar_sessao(agents)

    abertas = []
    for arquivo in sorted((agents / "atividades").glob("*.md")):
        try:
            meta = front_matter(arquivo.read_text(encoding="utf-8"))
        except OSError:
            continue
        if meta.get("status") != "em_andamento":
            continue
        abertas.append(meta)

    if not abertas:
        return 0

    abertas.sort(key=lambda m: m.get("atualizado_em", ""), reverse=True)
    linhas = ["Atividades em andamento no elcamargo-ai-flow:"]
    for meta in abertas[:TETO]:
        alvo = f"  {meta.get('id', '?')} — {meta.get('titulo', '')}".rstrip()
        linhas.append(alvo)
        detalhe = [f"step {meta.get('step', '?')} · {meta.get('step_nome', '')}".strip(),
                   f"trilha {meta.get('trilha', '?')}"]
        if meta.get("complementares"):
            detalhe.append(f"fecha também {meta['complementares']}")
        if meta.get("branch"):
            detalhe.append(f"branch {meta['branch']}")
        linhas.append("      " + " · ".join(detalhe))
    if len(abertas) > TETO:
        linhas.append(f"  (e mais {len(abertas) - TETO})")

    # O ponto todo: a frase que impede a deriva. Sem ela isto é um relatório
    # bonito que a sessão lê e ignora.
    linhas.append(
        "Se o pedido é sobre uma delas, siga o fluxo pelo step em que ela está "
        "— não recomece nem improvise fora dele. `/elcamargo-ai-flow` resolve "
        "onde retomar."
    )
    print("\n".join(linhas))
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
    # Um hook que falha atrapalha TODA mensagem. Ele nunca deve ser o motivo de
    # uma sessão quebrar: qualquer erro sai como silêncio.
    try:
        sys.exit(principal())
    except Exception:  # noqa: BLE001
        sys.exit(0)
