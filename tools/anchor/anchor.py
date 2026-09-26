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
"""
from __future__ import annotations

import argparse
import re
import sys
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


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raiz", default=".")
    args = p.parse_args(argv)

    agents = achar_agents(Path(args.raiz).resolve())
    if agents is None:
        return 0

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
    # Um hook que falha atrapalha TODA mensagem. Ele nunca deve ser o motivo de
    # uma sessão quebrar: qualquer erro sai como silêncio.
    try:
        sys.exit(principal())
    except Exception:  # noqa: BLE001
        sys.exit(0)
