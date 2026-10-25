#!/usr/bin/env python3
"""O que a pessoa que entregou isto deixou para trás?

    prior_work.py --base origin/main
    prior_work.py --base origin/main --json

A trilha `revisao` tem três casos, e o que ela faz muda em cada um: o dev usou o
fluxo, especificou fora dele, ou não documentou nada. Ver
`references/foreign-review.md`.

**Por que isto é comando e não instrução.** No primeiro uso real da trilha, em
11/09/2026, quem descobriu o caso foi a porta — ela leu a branch e entregou ao
step 1 com a resposta pronta. Funcionou, e a sessão que conduziu escreveu a
frase que originou este arquivo: *"se alguém entrar direto pelo step 1, ninguém
descobre nada."*

A doutrina põe a descoberta no step 1; o mecanismo estava na porta. Divergência
entre doutrina e implementação é o tipo de coisa que passa despercebida
enquanto o caminho feliz é o único exercitado — e é a mesma correção que a
tabela de Conferências fez para a conferência mecânica: **obrigação escrita em
prosa não acontece; mecanismo acontece.**

## O que ele NÃO responde

**Se o que foi documentado presta.** Ele acha documento, não julga documento.
Uma SDD errada e uma SDD certa produzem o mesmo caso `especificou-fora`.

**Se o arquivo de atividade é desta entrega.** Uma branch pode carregar o estado
de outra atividade que nunca foi limpo. Ele diz onde achou; conferir é de quem
lê.

**O caso, quando o `--base` está errado.** Base errada produz diff errado, e daí
o veredicto é sobre outra coisa. Por isso a base é exigida e não adivinhada.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))

import config as cfg  # noqa: E402
from flow_state import (FlowStateError, raiz_de_trabalho,  # noqa: E402
                        resolve_agents_dir)

USOU_O_FLUXO = "usou-o-fluxo"
ESPECIFICOU_FORA = "especificou-fora"
NAO_DOCUMENTOU = "nao-documentou"


def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=True, timeout=120).stdout
    except subprocess.CalledProcessError as exc:
        raise FlowStateError(
            f"`git {' '.join(args)}` falhou: "
            f"{(exc.stderr or '').strip()[:200]}") from exc
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise FlowStateError(f"`git {' '.join(args)}` não rodou: {exc}") from exc


def tocados(raiz: Path, base: str) -> list[str]:
    saida = _git(["diff", "--name-only", f"{base}...HEAD"], raiz)
    return [l.strip() for l in saida.splitlines() if l.strip()]


def atividades_na_arvore(raiz: Path) -> list[str]:
    """Arquivos de estado que EXISTEM nesta árvore, tocados pelo diff ou não.

    Tocados pelo diff seria o teste mais estreito e erraria o caso comum: uma
    entrega longa costuma ter o arquivo de atividade criado num commit anterior
    ao recorte que se está revisando.
    """
    alvo = raiz / ".agents" / "atividades"
    if not alvo.is_dir():
        return []
    return sorted(p.name for p in alvo.glob("*.md"))


def pasta_de_specs(agents: Path | None) -> str:
    try:
        return (cfg.obter("docs.specs", "", agents) or "").strip("/")
    except Exception:  # noqa: BLE001 — config ausente não impede o diagnóstico
        return ""


def especificacoes(tocados_: list[str], specs: str) -> list[str]:
    """Documento de especificação no diff.

    Com `docs.specs` declarado, é a pasta do projeto que manda. Sem ela, o
    palpite é estreito de propósito: `.md` sob um caminho que contenha `spec`
    ou `sdd`. Palpite largo — todo `.md` — classificaria como
    `especificou-fora` qualquer entrega que mexeu num README.
    """
    achados = []
    for caminho in tocados_:
        if not caminho.lower().endswith((".md", ".pdf", ".docx")):
            continue
        baixo = caminho.lower()
        if specs and baixo.startswith(specs.lower() + "/"):
            achados.append(caminho)
        elif not specs and ("spec" in baixo or "sdd" in baixo):
            achados.append(caminho)
    return achados


def diagnosticar(raiz: Path, base: str, agents: Path | None) -> dict:
    arquivos = tocados(raiz, base)
    atividades = atividades_na_arvore(raiz)
    specs = pasta_de_specs(agents)
    docs = especificacoes(arquivos, specs)

    if atividades:
        caso = USOU_O_FLUXO
    elif docs:
        caso = ESPECIFICOU_FORA
    else:
        caso = NAO_DOCUMENTOU
    return {"caso": caso, "base": base, "arquivos_no_diff": len(arquivos),
            "atividades": atividades, "especificacoes": docs,
            "docs_specs_declarado": specs}


COMO_AGIR = {
    USOU_O_FLUXO: (
        "O step 4 confronta a baseline com a TABELA DE CONFERÊNCIAS dele: o que "
        "foi conferido já está declarado, inclusive as `não-coberta`. O step 9 "
        "concentra as frentes no que ficou descoberto. É o caso mais barato.\n"
        "  Confira que o arquivo é DESTA entrega: branch carrega estado de "
        "atividade antiga que ninguém limpou."),
    ESPECIFICOU_FORA: (
        "O step 4 confere a SDD dele contra a baseline, item a item. É o caso "
        "mais caro: há documento a ler.\n"
        "  Ela é OBJETO DE REVISÃO, nunca fonte da verdade — uma SDD que leu o "
        "card errado produz código fiel ao erro."),
    NAO_DOCUMENTOU: (
        "O step 4 registra a ausência como achado — \"entregou sem "
        "especificar\" é informação para o portão 10 — e passa direto. O step 9 "
        "confere o código contra a baseline do card.\n"
        "  A ausência de documento é achado, não obstáculo: o que ele fez é "
        "conferível contra o card do mesmo jeito."),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="prior_work.py",
        description="Em qual dos três casos da trilha `revisao` esta entrega está?")
    p.add_argument("--base", required=True,
                   help="a referência de onde a branch saiu, ex. origin/main")
    p.add_argument("--raiz", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        agents = resolve_agents_dir()
        raiz = Path(args.raiz).resolve() if args.raiz else raiz_de_trabalho(agents)
        d = diagnosticar(raiz, args.base, agents)
    except FlowStateError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0

    print(f"CASO DETECTADO  {d['caso']}")
    print(f"  base          {d['base']}   ({d['arquivos_no_diff']} arquivo(s) no diff)")
    if d["atividades"]:
        print(f"  atividades    {', '.join(d['atividades'])}")
    if d["especificacoes"]:
        mostra = d["especificacoes"][:5]
        resto = len(d["especificacoes"]) - len(mostra)
        print(f"  specs no diff {', '.join(mostra)}" + (f" (e mais {resto})" if resto else ""))
    if not d["docs_specs_declarado"]:
        print("  aviso         `docs.specs` não declarado no config: a busca por")
        print("                especificação caiu no palpite estreito (`spec`/`sdd`")
        print("                no caminho). Declare para não depender de palpite.")
    print()
    print("O que isso muda:")
    print("  " + COMO_AGIR[d["caso"]])
    print()
    print("Registre no histórico da atividade — a descoberta é do step 1, e")
    print("quem retomar a revisão depois precisa achar isto escrito.")
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
    sys.exit(main())
