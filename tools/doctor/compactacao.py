#!/usr/bin/env python3
"""Confere, e liga quando a pessoa manda, a compactação antecipada da máquina.

O Claude Code compacta a conversa sozinho perto do limite do modelo, e nestes
modelos o limite é 1 milhão. Até lá, cada resposta relê o contexto inteiro. Foi
o que mais custou em 25 e 26/09/2026: 61% acima de 200 mil, 32% acima de 400
mil. Com `autoCompactWindow: 200000` no `~/.claude/settings.json`, medido de 02
a 15/11/2026, nenhuma janela principal passou de 177 mil.

A configuração é DA MÁQUINA, não do projeto: reinstalar o pacote não a leva
junto. Por isso existe este arquivo — o `install.sh` e a âncora perguntam a ele,
e quem liga é a pessoa, com `ligar`.

    compactacao.py conferir          imprime o estado; sai 0 ligada, 1 desligada
    compactacao.py ligar [--valor N] grava no settings.json, com backup ao lado

Nomes conferidos no binário do Claude Code, não na documentação resumida:
`autoCompactWindow` (settings) e `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (variável,
que tem precedência). `CLAUDE_CODE_DISABLE_1M_CONTEXT` sozinha não basta.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

CHAVE = "autoCompactWindow"
VARIAVEL = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
PADRAO = 200_000


def settings() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "settings.json"


def _ler(alvo: Path) -> dict | None:
    """O JSON do settings, `{}` se não existe, `None` se está ilegível."""
    if not alvo.exists():
        return {}
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def estado(alvo: Path | None = None) -> tuple[int | None, str]:
    """(valor em tokens, de onde veio). Valor `None` é compactação só no limite."""
    valor = os.environ.get(VARIAVEL)
    if valor:
        return _numero(valor), f"variável {VARIAVEL}"
    dados = _ler(alvo or settings()) or {}
    if dados.get(CHAVE):
        return _numero(dados[CHAVE]), f"{CHAVE} no settings.json"
    valor = (dados.get("env") or {}).get(VARIAVEL)
    if valor:
        return _numero(valor), f"{VARIAVEL} no env do settings.json"
    return None, "nada configurado"


def _numero(valor) -> int | None:
    texto = str(valor).strip().lower().replace("_", "")
    mult = 1
    if texto.endswith("k"):
        texto, mult = texto[:-1], 1000
    elif texto.endswith("m"):
        texto, mult = texto[:-1], 1_000_000
    try:
        return int(float(texto) * mult)
    except ValueError:
        return None


def ligada(alvo: Path | None = None) -> bool:
    return estado(alvo)[0] is not None


def ligar(valor: int = PADRAO, alvo: Path | None = None) -> str:
    alvo = alvo or settings()
    dados = _ler(alvo)
    if dados is None:
        # Ilegível: não reescrever. Perder a config de alguém para gravar uma
        # chave seria o pior desfecho possível.
        raise SystemExit(f"{alvo} está ilegível — não mexi. Corrija o JSON e rode de novo.")
    if dados.get(CHAVE) == valor:
        return f"já estava: {CHAVE} = {valor} em {alvo}"
    backup = None
    if alvo.exists():
        base = f"{alvo.name}.bak-{time.strftime('%Y-%m-%d-%H%M%S')}-antes-autocompact"
        backup, n = alvo.with_name(base), 1
        while backup.exists():
            # Dois `ligar` no mesmo segundo: o segundo backup NÃO pode cobrir
            # o primeiro, que é o único com o arquivo original.
            n += 1
            backup = alvo.with_name(f"{base}-{n}")
        shutil.copy2(alvo, backup)
    dados[CHAVE] = valor
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temp = alvo.with_suffix(".tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(alvo)
    feito = f"{CHAVE} = {valor} gravado em {alvo}"
    if backup:
        feito += f"\n  backup: {backup}"
    return feito + "\n  Vale para as sessões que abrirem daqui em diante."


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("conferir")
    lg = sub.add_parser("ligar")
    lg.add_argument("--valor", type=int, default=PADRAO)
    args = p.parse_args(argv)

    if args.cmd == "ligar":
        print(ligar(args.valor))
        return 0
    valor, origem = estado()
    if valor is None:
        print(f"compactação só perto de 1 milhão ({origem}). "
              f"Para compactar em {PADRAO // 1000} mil: python3 {Path(__file__).resolve()} ligar")
        return 1
    print(f"compactação em {valor // 1000} mil ({origem})")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
