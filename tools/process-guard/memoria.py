#!/usr/bin/env python3
"""Quem está comendo a memória da máquina, agrupado, e o limite do Docker.

    python3 memoria.py          (ou `fila_pesada.py memoria`)

Em 18/11/2026 o backoffice pediu isto: a fila recusava por memória e
mostrava os cinco maiores processos pelo nome (`node`, `claude`,
`com.apple.Virtualization.VirtualMachine`), sem dizer de qual sessão ou
worktree cada um era, nem que a VM do Docker era 1,6 GB do total.

Três leituras:

1. **Os processos da máquina, agrupados.** App pelo pacote `.app` (Chrome,
   Teams e os helpers deles viram uma linha), a VM do Docker junto com o app
   do Docker, cada sessão do Claude Code e cada processo solto (node, python,
   java) pela pasta onde roda, cortada no worktree.
2. **Os contêineres do Docker, por projeto do compose**, com a pasta de onde
   subiram. Pasta que já não existe é worktree apagado com a pilha de pé.
3. **O limite de memória da VM do Docker**, lido do `settings-store.json`
   do Docker Desktop, e quanto caberia pelo que os contêineres usam agora.

## O que isto NÃO prova

**Que o grupo maior é o culpado.** RSS é a memória residente agora: memória
comprimida e a que já foi para o swap não aparecem, e páginas divididas entre
processos contam duas vezes. É a lista de onde olhar, não o veredito.

**Que o limite sugerido aguenta o pico.** Ele sai do uso de agora (× 1,5,
mais 0,5 GB do sistema da VM). Uma carga de banco no meio de um teste de
integração pode passar disso. Mudar o limite é decisão da pessoa, no Docker
Desktop; esta ferramenta não muda nada.

Stdlib only. Só lê.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path

# Processo sem `.app` que pesa: menos que isto não vale um `lsof`.
MINIMO_PARA_PASTA_KB = 30 * 1024
VM_DO_DOCKER = "com.apple.Virtualization.VirtualMachine"
CONFIG_DOCKER = (Path.home() / "Library" / "Group Containers"
                 / "group.com.docker" / "settings-store.json")


def _saida(cmd: list[str], timeout: float = 10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def gb(kb: float) -> str:
    return f"{kb / 1048576:.1f} GB"


# ------------------------------------------------------------- os processos

def ler_processos() -> list[dict]:
    fora = []
    for linha in _saida(["ps", "-axo", "pid=,rss=,comm="]).splitlines():
        campos = linha.split(None, 2)
        if len(campos) == 3 and campos[0].isdigit() and campos[1].isdigit():
            fora.append({"pid": int(campos[0]), "kb": int(campos[1]),
                         "caminho": campos[2]})
    return fora


def app_de(caminho: str) -> str | None:
    """O pacote `.app` mais de fora do caminho, sem o `.app`."""
    for parte in caminho.split("/"):
        if parte.endswith(".app"):
            return parte[:-4]
    return None


def curto(pasta: str, casa: str | None = None) -> str:
    """A pasta como a pessoa a reconhece: `~` no lugar da casa, e cortada no
    worktree quando é um (`.../.claude/worktrees/1103-x/frontend` vira
    `.../.claude/worktrees/1103-x`)."""
    casa = casa if casa is not None else str(Path.home())
    m = re.match(r"(.*/(?:\.claude/)?worktrees/[^/]+)", pasta)
    if m:
        pasta = m.group(1)
    if casa and (pasta == casa or pasta.startswith(casa + "/")):
        pasta = "~" + pasta[len(casa):]
    partes = pasta.split("/")
    if len(partes) > 6:
        pasta = "…/" + "/".join(partes[-4:])
    return pasta


def grupo_de(caminho: str, pasta: str | None, casa: str | None = None) -> str:
    if VM_DO_DOCKER in caminho:
        return "Docker (VM e app)"
    if "/claude-code/" in caminho:
        return "Claude Code em " + (curto(pasta, casa) if pasta else "?")
    app = app_de(caminho)
    if app == "Docker":
        return "Docker (VM e app)"
    if app:
        return app
    nome = os.path.basename(caminho)
    return f"{nome} em {curto(pasta, casa)}" if pasta else nome


def pastas_de(pids: list[int]) -> dict[int, str]:
    """A pasta de trabalho de cada processo, numa chamada só de `lsof`."""
    if not pids:
        return {}
    texto = _saida(["lsof", "-a", "-d", "cwd", "-Fn", "-p",
                    ",".join(str(p) for p in pids)], timeout=15)
    fora, atual = {}, None
    for linha in texto.splitlines():
        if linha.startswith("p") and linha[1:].isdigit():
            atual = int(linha[1:])
        elif linha.startswith("n") and atual is not None:
            fora[atual] = linha[1:]
    return fora


def agrupar(processos: list[dict], pastas: dict[int, str],
            casa: str | None = None) -> list[tuple[int, str, int]]:
    """(kb, grupo, quantos processos), do maior para o menor."""
    soma: dict[str, list[int]] = {}
    for p in processos:
        g = grupo_de(p["caminho"], pastas.get(p["pid"]), casa)
        s = soma.setdefault(g, [0, 0])
        s[0] += p["kb"]
        s[1] += 1
    return sorted(((kb, g, n) for g, (kb, n) in soma.items()), reverse=True)


def quem_come(n: int = 8) -> list[str]:
    processos = ler_processos()
    candidatos = [p["pid"] for p in processos
                  if p["kb"] >= MINIMO_PARA_PASTA_KB
                  and ("/claude-code/" in p["caminho"] or not app_de(p["caminho"]))
                  and VM_DO_DOCKER not in p["caminho"]]
    grupos = agrupar(processos, pastas_de(candidatos))
    return [f"{gb(kb):>7}  {g}" + (f"  ({q} processos)" if q > 1 else "")
            for kb, g, q in grupos[:n]]


# ----------------------------------------------------------------- o Docker

def mb_de(uso: str) -> float | None:
    """`856.7MiB / 3.826GiB` → 856.7. A parte antes da barra, em MB."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]i?B|B)", uso)
    if not m:
        return None
    fator = {"B": 1 / 1048576, "KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1,
             "MB": 1, "GiB": 1024, "GB": 1024, "TiB": 1048576, "TB": 1048576}
    return float(m.group(1)) * fator.get(m.group(2), 1)


def conteineres() -> list[dict] | None:
    """Cada contêiner rodando, com memória, projeto e pasta. `None` sem Docker."""
    ps = _saida(["docker", "ps", "--format",
                 '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t'
                 '{{.Label "com.docker.compose.project.working_dir"}}\t{{.Image}}'])
    if not ps.strip():
        return None
    stats = _saida(["docker", "stats", "--no-stream", "--format",
                    "{{.Name}}\t{{.MemUsage}}"], timeout=20)
    uso = {}
    for linha in stats.splitlines():
        nome, _, mem = linha.partition("\t")
        uso[nome] = mb_de(mem)
    fora = []
    for linha in ps.splitlines():
        campos = (linha.split("\t") + ["", "", "", ""])[:4]
        fora.append({"nome": campos[0], "projeto": campos[1], "pasta": campos[2],
                     "imagem": campos[3], "mb": uso.get(campos[0])})
    return fora


def por_projeto(lista: list[dict]) -> list[dict]:
    grupos: dict[str, dict] = {}
    for c in lista:
        chave = c["projeto"] or f"{c['nome']} ({c['imagem']}, sem compose)"
        g = grupos.setdefault(chave, {"projeto": chave, "pasta": c["pasta"],
                                      "mb": 0.0, "quantos": 0})
        g["mb"] += c["mb"] or 0.0
        g["quantos"] += 1
    return sorted(grupos.values(), key=lambda g: -g["mb"])


def limite_do_docker(arquivo: Path = CONFIG_DOCKER) -> int | None:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    valor = dados.get("MemoryMiB") if isinstance(dados, dict) else None
    return int(valor) if isinstance(valor, (int, float)) and valor > 0 else None


def sugerir_limite(uso_mb: float) -> int:
    """O uso de agora × 1,5, mais 0,5 GB da VM, em degraus de 512 MB, e nunca
    abaixo de 2 GB."""
    return max(2048, math.ceil((uso_mb * 1.5 + 512) / 512) * 512)


def recomendacao(uso_mb: float, limite_mb: int | None) -> str:
    sugerido = sugerir_limite(uso_mb)
    base = (f"os contêineres usam {uso_mb / 1024:.1f} GB; caberiam em "
            f"{sugerido / 1024:.1f} GB (uso × 1,5 + 0,5 GB da VM)")
    if limite_mb is None:
        return base + "; o limite da VM não foi lido (Docker Desktop > Settings > Resources)."
    if sugerido < limite_mb:
        return (f"{base}. A VM está com limite de {limite_mb / 1024:.1f} GB e prende o que "
                "tocou: baixar para "
                f"{sugerido / 1024:.1f} GB em Docker Desktop > Settings > Resources > Memory "
                f"limit tira até {(limite_mb - sugerido) / 1024:.1f} GB do alcance dela. "
                "Quem muda é a pessoa.")
    if sugerido > limite_mb:
        return (f"{base}. A VM tem só {limite_mb / 1024:.1f} GB: está apertada. Pare "
                "as pilhas que não estão em uso antes de subir o limite.")
    return f"{base}. O limite de {limite_mb / 1024:.1f} GB está no ponto."


# ---------------------------------------------------------------- a leitura

def relatorio() -> list[str]:
    linhas = ["quem come a memória (RSS agora, agrupado):", *("  " + x for x in quem_come())]
    lista = conteineres()
    if lista is None:
        linhas += ["", "docker: não respondeu (parado, ou sem `docker` no PATH)."]
        return linhas
    linhas += ["", "contêineres do Docker, por projeto do compose:"]
    for g in por_projeto(lista):
        sumiu = g["pasta"] and not Path(g["pasta"]).exists()
        linhas.append(
            f"  {g['mb']:>6.0f} MB  {g['projeto']}"
            + (f"  ({g['quantos']} contêineres)" if g["quantos"] > 1 else "")
            + (f"\n             pasta {curto(g['pasta'])} JÁ NÃO EXISTE: worktree "
               "apagado com a pilha de pé (`docker compose -p "
               f"{g['projeto']} down`, se a pessoa quiser)" if sumiu else ""))
    uso = sum(c["mb"] or 0.0 for c in lista)
    linhas += ["", "limite do Docker: " + recomendacao(uso, limite_do_docker())]
    return linhas


if __name__ == "__main__":
    print("\n".join(relatorio()))
