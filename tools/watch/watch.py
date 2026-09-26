#!/usr/bin/env python3
"""Diz quais subagentes estão trabalhando e quais travaram.

Um agente parado numa chamada de ferramenta **parece** um agente trabalhando: os
dois não respondem. A diferença é observável e barata — um agente que trabalha
escreve no transcrito a cada chamada de ferramenta, e um agente travado não
escreve mais nada.

Isto existe porque a espera educada custou 52 minutos e seis frentes de revisão:
o `Revisor da Entrega` rodou tudo, todas as frentes voltaram, e ele travou na
consolidação. Quem esperava não tinha como saber, e continuou esperando.

    watch.py                      olha os agentes desta sessão
    watch.py --dir <tasks>        olha outro diretório de tarefas
    watch.py --ate-travar         fica olhando até algum travar, e aí sai

Sai com 1 quando há agente travado, para servir de condição em laço.

**O que isto NÃO prova:** que o agente está produzindo algo útil. Prova que ele
está vivo. Um agente em laço infinito escreve o tempo todo e passa aqui.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Um agente que trabalha escreve a cada chamada de ferramenta. Medido nesta POC:
# a chamada mais lenta entre escritas foi o gate pré-QA do frontend, com 1min30 —
# e o passo mais lento que existe é a suíte de Playwright inteira. Cinco minutos
# de silêncio já é fora da curva; vinte é a execução que travou.
ATENCAO_S = 5 * 60
TRAVADO_S = 20 * 60

# Além disto não é travamento vivo, é história: agente de ontem que ninguém está
# esperando. Some da vista por padrão, senão a lista enche de coisa que não é
# problema — a primeira versão listou trinta e um agentes de dias atrás.
TETO_S = 4 * 3600

# `end_turn` na ultima linha diz que o agente fechou o turno — nao que ele
# acabou. Um agente que fecha um turno e continua trabalhando escreve a linha
# seguinte em segundos, e entre uma e outra o arquivo mente.
#
# Aconteceu: o vigia deu por concluida uma frente que estava editando arquivo
# naquele instante, e so' a lista de tarefas em curso desmentiu. A carencia
# resolve sem inventar sinal novo — quem fechou o turno de verdade nao escreve
# mais nada, e quem vai continuar escreve logo.
CARENCIA_FIM_S = 2 * 60


def e_agente(arquivo: Path) -> bool:
    """Distingue transcrito de agente de saída de comando em background.

    O mesmo diretório guarda os dois, e comando em background não tem estado de
    "travado": ele roda até acabar. Julgá-lo pela régua de agente encheu a
    primeira execução de falso positivo.
    """
    try:
        with arquivo.open(encoding="utf-8", errors="replace") as f:
            return '"agentId"' in f.readline()
    except OSError:
        return False


def descricao(arquivo: Path) -> str:
    """O pedido que abriu o agente, em uma linha.

    Só a **primeira** linha do arquivo é lida. O resto é o transcrito inteiro, e
    lê-lo por inteiro para descobrir um rótulo custaria mais contexto do que o
    problema que esta ferramenta resolve.
    """
    try:
        with arquivo.open(encoding="utf-8", errors="replace") as f:
            primeira = f.readline()
        dado = json.loads(primeira)
        conteudo = dado.get("message", {}).get("content", "")
        if isinstance(conteudo, list):
            conteudo = " ".join(c.get("text", "") for c in conteudo
                                if isinstance(c, dict))
        linha = str(conteudo).strip().splitlines()[0] if conteudo else ""
        return linha[:58] or "—"
    except Exception:
        return "—"


def concluido(arquivo: Path) -> bool:
    """O agente terminou, ou parou no meio?

    Sem esta distinção a ferramenta é inútil: um agente que **terminou** também
    para de escrever, e a primeira versão marcou como TRAVADO trinta agentes que
    haviam entregado o trabalho dias antes.

    O marcador é o `stop_reason` da última mensagem do assistente. `end_turn`
    quer dizer que ele fechou o turno por vontade própria — entregou. Qualquer
    outra coisa na última linha significa que ele parou no meio de alguma coisa.
    """
    try:
        ultima = ""
        with arquivo.open("rb") as f:
            # Ler só o fim: o transcrito inteiro é grande, e o que interessa é a
            # última linha.
            f.seek(0, 2)
            tamanho = f.tell()
            f.seek(max(0, tamanho - 65536))
            ultima = f.read().decode("utf-8", "replace").strip().splitlines()[-1]
        dado = json.loads(ultima)
        return (dado.get("type") == "assistant"
                and dado.get("message", {}).get("stop_reason") == "end_turn")
    except Exception:
        return False


def _dur(segundos: float) -> str:
    if segundos < 60:
        return f"{segundos:.0f}s"
    if segundos < 3600:
        return f"{segundos / 60:.0f}min"
    return f"{segundos / 3600:.1f}h"


def olhar(pasta: Path, minimo_s: float = 0,
          incluir_concluidos: bool = False,
          alvos: set[str] | None = None) -> list[dict]:
    saida = []
    alvos = alvos or set()
    agora = time.time()
    for arquivo in sorted(pasta.glob("*.output")):
        if alvos and arquivo.stem not in alvos:
            continue
        if not e_agente(arquivo):
            continue
        try:
            st = arquivo.stat()
        except OSError:
            continue
        parado = agora - st.st_mtime
        if parado < minimo_s:
            continue
        if concluido(arquivo) and parado >= CARENCIA_FIM_S:
            if not incluir_concluidos:
                continue
            estado = "concluído"
        elif parado > TETO_S and not alvos and not incluir_concluidos:
            continue
        else:
            estado = ("trabalhando" if parado < ATENCAO_S
                      else "atenção" if parado < TRAVADO_S else "TRAVADO")
        saida.append({"id": arquivo.stem, "parado": parado, "estado": estado,
                      "descricao": descricao(arquivo), "caminho": arquivo})
    return saida


def pasta_da_sessao() -> Path | None:
    """Descobre o diretório de tarefas pelo scratchpad da sessão, se houver."""
    for var in ("CLAUDE_SCRATCHPAD", "CLAUDE_SESSION_DIR"):
        valor = os.environ.get(var)
        if valor:
            candidato = Path(valor).parent / "tasks"
            if candidato.is_dir():
                return candidato
    return None


def imprimir(itens: list[dict], pasta: Path) -> int:
    print(f"Vigia de subagentes — {pasta}")
    print()
    if not itens:
        print("  Nenhum agente em curso — todos entregaram, ou não há nenhum.")
        return 0
    for i in itens:
        print(f"  {i['id'][:10]}…  {i['descricao']:<58}  "
              f"{_dur(i['parado']):>7} sem escrever  {i['estado']}")
    travados = [i for i in itens if i["estado"] == "TRAVADO"]
    print()
    if travados:
        print(f"  {len(travados)} travado(s). Um agente que trabalha escreve a "
              "cada chamada de ferramenta.")
        print("  Mate, recolha o que ele persistiu, e redispare dizendo de onde "
              "continuar.")
    print()
    print("O que isto NÃO prova: que o agente está produzindo algo útil. Prova")
    print("que ele está vivo — laço infinito escreve o tempo todo e passa aqui.")
    print("E o que ela NÃO distingue: agente morto por interrupção também para")
    print("no meio, e de fora isso é igual a travado. Confira a lista de tarefas")
    print("em curso antes de matar de novo o que já morreu.")
    print(f"Nos primeiros {CARENCIA_FIM_S // 60}min apos fechar um turno, o agente")
    print("aparece como trabalhando — e' quando nao da' para saber se ele acabou")
    print("ou vai continuar. As duas leituras concordam que ele nao travou.")
    return 1 if travados else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dir", help="diretório de tarefas da sessão")
    p.add_argument("--recentes", type=float, default=0, metavar="MIN",
                   help="só os que estão parados há pelo menos MIN minutos")
    p.add_argument("--agente", action="append", metavar="ID", default=[],
                   help="olha só estes agentes, mesmo que antigos (repetível)")
    p.add_argument("--todos", action="store_true",
                   help="mostra também os que já entregaram")
    p.add_argument("--ate-travar", action="store_true",
                   help="olha a cada intervalo até algum travar")
    p.add_argument("--intervalo", type=float, default=5, metavar="MIN",
                   help="intervalo de --ate-travar (padrão: 5min)")
    args = p.parse_args(argv)

    pasta = Path(args.dir).expanduser() if args.dir else pasta_da_sessao()
    if pasta is None or not pasta.is_dir():
        print("erro: não achei o diretório de tarefas. Passe --dir <caminho>.",
              file=sys.stderr)
        return 2

    if not args.ate_travar:
        return imprimir(olhar(pasta, args.recentes * 60, args.todos, set(args.agente)), pasta)

    while True:
        itens = olhar(pasta, args.recentes * 60, args.todos,
                      set(args.agente))
        vivos = [i for i in itens if i["estado"] != "TRAVADO"]
        codigo = imprimir(itens, pasta)
        if codigo == 1 or not vivos:
            return codigo
        time.sleep(args.intervalo * 60)


if __name__ == "__main__":
    sys.exit(main())
