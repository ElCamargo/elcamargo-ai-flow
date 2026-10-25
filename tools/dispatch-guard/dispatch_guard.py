#!/usr/bin/env python3
"""Diz quais frentes estão TRAVADAS, e a diferença não está no relógio.

Duas frentes paradas há o mesmo tempo podem ser coisas opostas: uma esperando
o retorno síncrono que ela pediu — que é o comportamento certo — e outra presa
para sempre, porque disparou em segundo plano de dentro de um subagente, onde a
notificação de conclusão não chega.

**O `mtime` não separa as duas.** O arquivo não cresce enquanto o agente pensa,
e 338s parado foi travada enquanto 324s parado foi saudável, medido em
18/09/2026. O que separa é o `run_in_background` do ÚLTIMO disparo.

Quem usar a heurística óbvia — "parado há mais de N minutos, matar" — mata
frente viva no meio do trabalho dela.

    dispatch_guard.py                 as frentes deste projeto
    dispatch_guard.py --raiz <dir>    outro projeto
    dispatch_guard.py --minutos 240   janela maior de transcritos
    dispatch_guard.py --json          para quem automatiza em volta

Sai 1 se houver frente travada.

**Ela lê forma, não conteúdo.** Dos transcritos saem blocos `tool_use`, o
`run_in_background`, timestamps e o TAMANHO da última fala — nunca o texto dela.
Isso não é só privacidade: é o que torna a leitura barata, e o que impede que
conteúdo de negócio de um projeto entre no relatório de outro.

**O único campo que vem de texto humano é o `description` do disparo** — o
rótulo curto que o orquestrador deu à frente. Sem ele não há como dizer QUAL
frente travou. Fica declarado aqui em vez de escondido: se ele carregar nome de
cliente, ele sai no relatório.

**Duas bases de tempo, e elas são diferentes de propósito.** O *"parada há N s"*
sai de `mtime` contra `time.time()` — os dois em epoch, sem fuso, e por isso a
subtração é confiável. Já as horas dos disparos vêm do `timestamp` do transcrito,
que é **UTC**. Por isso elas saem rotuladas `UTC` no relatório: lidas contra um
relógio local adiantado ou atrasado, um disparo parece estar no futuro.

**O que ela NÃO mede, e é o eixo que mais importa:** se o agente *usou* o retorno
que recebeu. Disparo bloqueante garante que o retorno chegou — está no
`tool_result` da mesma chamada —, não que ele foi lido, nem que a consolidação o
levou em conta. Um step que bloqueia, recebe e ignora sai daqui como saudável.

Isso não é buraco, é **divisão de trabalho**, e a resposta existe:

| pergunta | quem responde |
| --- | --- |
| *o retorno chegou?* | **esta ferramenta** — forma, mecânico, barato |
| *o retorno foi usado?* | **o relatório do step**, que é obrigado a nomear cada frente e a declarar dimensão `nao-coberta` em vez de silêncio |
| *o segundo confere com o primeiro?* | **o humano do portão**, único que lê os dois |

Um step que bloqueia, recebe e ignora produz um relatório que **não nomeia**
aquela frente — e isso é legível por quem lê o relatório. A exigência está em
`skills/elcamargo-development-reviewer/SKILL.md`: *"nomeie a frente que ficou
sem resposta; declare a revisão incompleta naquela dimensão"*.

**Orientação a quem dispara — isto a ferramenta não tem como garantir:** escreva
no `description` o que identifica a FRENTE, nunca o cliente. O step, a trilha e
um apelido técnico da fatia. Número de card, nome de cliente, nome de pessoa e
termo de contrato ficam no PROMPT, que a ferramenta não lê. Resolve por
construção, sem depender de ninguém lembrar de sanear depois.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Um disparo sem o parâmetro é de segundo plano: o padrão da ferramenta é
# assíncrono. Omitir não é neutro, é escolher o modo que quebra.
SEGUNDO_PLANO = {True, None}

# Abaixo disto não se conclui nada: uma frente recém-disparada ainda não teve
# tempo de escrever, e travada e saudável são indistinguíveis por qualquer via.
SILENCIO_MINIMO_S = 120

# O modo do disparo NÃO basta: um agente que TERMINOU também para de crescer, e
# dispara-e-segue é um final legítimo. Duas frentes que dispararam em segundo
# plano entregaram relatório completo enquanto uma terceira travou — o que as
# separa é a última fala.
#
# Medido em 18/09/2026, 12 frentes de uma sessão real: as falas finais caem em
# 42, 86, 165 — e depois 3.802, 3.961, 4.142, 4.892, 5.318, 5.350, 5.596, 6.066,
# 8.295. **Não há nada entre 165 e 3.802.** O limiar mora no meio desse vão, e
# está declarado assim para que o próximo a medir saiba o que ele separava.
LIMIAR_DE_ENTREGA = 1000

# Agente morto pelo usuário: nem travou nem entregou, e acusá-lo é ruído.
MARCA_DE_INTERRUPCAO = "[Request interrupted"


def raiz_de_transcritos(projeto: Path) -> Path:
    """`~/.claude/projects/<caminho-com-tracos>`. O nome começa com `-`, e é por
    isso que todo glob aqui leva `./` na frente: sem ele o shell — e o `ls` —
    leem o caminho como opção.

    Todo caractere que não é letra nem dígito vira `-`, e não só a `/`: uma
    worktree em `.claude/worktrees/x` é gravada como `--claude-worktrees-x`.
    Até a 2.52.0 só a barra era trocada, e dentro de worktree — onde os times
    rodam — a ferramenta dizia *"nenhuma frente"* com seis transcritos ali."""
    marca = re.sub(r"[^A-Za-z0-9]", "-", str(projeto.resolve()))
    return Path.home() / ".claude" / "projects" / marca


def disparos_de(transcrito: Path) -> tuple[list[tuple[str, object, str]], str]:
    """Os disparos de `Agent` e a ÚLTIMA fala do agente — os dois sinais que o
    veredicto exige. Só blocos `tool_use` e `text`: o JSONL tem centenas de
    milhares de bytes, e abri-lo inteiro é o que fazia os dois lados acharem
    esta medição impossível."""
    saida = []
    ultima_fala = ""
    lancados, retornados = {}, set()
    with transcrito.open(errors="ignore") as f:
        for linha in f:
            try:
                d = json.loads(linha)
            except (ValueError, TypeError):
                continue
            conteudo = d.get("message", {}).get("content")
            if not isinstance(conteudo, list):
                continue
            for bloco in conteudo:
                if not isinstance(bloco, dict):
                    continue
                if bloco.get("type") == "tool_use" and bloco.get("name") == "Agent":
                    entrada = bloco.get("input", {})
                    item = (d.get("timestamp", "")[11:19],
                            entrada.get("run_in_background"),
                            (entrada.get("description") or "")[:38])
                    saida.append(item)
                    lancados[bloco.get("id")] = len(saida) - 1
                elif bloco.get("type") == "tool_result" and bloco.get("tool_use_id") in lancados:
                    retornados.add(lancados[bloco["tool_use_id"]])
                elif bloco.get("type") == "text" and (bloco.get("text") or "").strip():
                    ultima_fala = bloco["text"].strip()
                elif bloco.get("type") == "tool_use" and bloco.get("name") == "SubagentHandback":
                    # A devolução por ferramenta, que começou a aparecer em
                    # setembro de 2026 (11 de 198 subagentes em três dias).
                    # Lida só como texto, a entrega dela sai como fala curta.
                    ultima_fala = str((bloco.get("input") or {}).get("message") or "").strip() or ultima_fala
    return saida, ultima_fala, retornados


def auditar(projeto: Path, minutos: int) -> list[dict]:
    base = raiz_de_transcritos(projeto)
    if not base.is_dir():
        return []
    agora = time.time()
    frentes = []
    for transcrito in base.glob("*/subagents/*.jsonl"):
        parado = agora - transcrito.stat().st_mtime
        if parado > minutos * 60:
            continue
        disparos, ultima_fala, retornados = disparos_de(transcrito)
        # Um disparo BLOQUEANTE sem `tool_result` é uma chamada em voo agora: o
        # agente está parado dentro dela. É o estado saudável, e nomeá-lo evita
        # que alguém o confunda com travamento.
        em_voo = [d for i, d in enumerate(disparos)
                  if i not in retornados and d[1] not in SEGUNDO_PLANO]
        em_segundo_plano = bool(disparos) and disparos[-1][1] in SEGUNDO_PLANO
        if not disparos:
            veredicto = "sem disparo"
        elif ultima_fala.startswith(MARCA_DE_INTERRUPCAO):
            veredicto = "interrompida"
        elif len(ultima_fala) >= LIMIAR_DE_ENTREGA:
            # Entregou. Se disparou em segundo plano, entregou SEM o retorno do
            # que disparou — é risco declarado, não defeito: o step fechou sem
            # aquela dimensão.
            veredicto = "entregou sem o retorno" if em_segundo_plano else "entregou"
        elif parado < SILENCIO_MINIMO_S:
            veredicto = "cedo demais para dizer"
        elif em_segundo_plano:
            veredicto = "TRAVADA"
        elif em_voo:
            veredicto = f"esperando o retorno de {em_voo[-1][2]!r} (bloqueante)"
        else:
            veredicto = "esperando (bloqueante)"
        frentes.append({
            "frente": transcrito.stem.replace("agent-", "")[:9],
            "sessao": transcrito.parent.parent.name[:8],
            "parado_s": int(parado),
            "disparos": [{"em": e, "segundo_plano": bg, "o_que": o} for e, bg, o in disparos],
            "ultima_fala_chars": len(ultima_fala),
            "sem_retorno_de": sum(1 for _, bg, _ in disparos if bg in SEGUNDO_PLANO),
            "em_voo": [{"em": e, "o_que": o} for e, _, o in em_voo],
            "veredicto": veredicto,
        })
    return sorted(frentes, key=lambda f: -f["parado_s"])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raiz", default=".", help="o projeto (padrão: o diretório atual)")
    p.add_argument("--minutos", type=int, default=120,
                   help="só transcritos tocados nesta janela (padrão: 120)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    frentes = auditar(Path(args.raiz).expanduser(), args.minutos)

    if args.json:
        print(json.dumps(frentes, ensure_ascii=False, indent=2))
    elif not frentes:
        print(f"nenhuma frente de subagente nos últimos {args.minutos} min.")
    else:
        print(f"{len(frentes)} frente(s) de subagente, mais paradas primeiro:\n")
        for f in frentes:
            print(f"  {f['frente']}  sessão {f['sessao']}  parada há {f['parado_s']}s  "
                  f"→ {f['veredicto']}")
            for d in f["disparos"][-3:]:
                modo = "segundo plano" if d["segundo_plano"] in SEGUNDO_PLANO else "bloqueante"
                print(f"       {d['em']} UTC  {modo:14} {d['o_que']}")
        print("\nAs horas dos disparos são UTC (vêm do transcrito); o "
              "\"parada há N s\" é epoch\ncontra epoch, sem fuso.")
        print("\nO relógio NÃO separa travada de saudável, e o modo do disparo "
              "sozinho também não:\numa frente que TERMINOU para de crescer igual "
              "a uma travada. O que separa é a\núltima fala — entrega tem "
              "milhares de caracteres, espera tem dezenas.")

    sem_retorno = [f for f in frentes if f["veredicto"] == "entregou sem o retorno"]
    if sem_retorno and not args.json:
        print(f"\n{len(sem_retorno)} ENTREGOU SEM O RETORNO:")
        for f in sem_retorno:
            n = f["sem_retorno_de"]
            print(f"  {f['frente']}: entregou sem o retorno de {n} subfrente(s).")
        print("  O que essas subfrentes iam produzir pode ter sido feito pelo "
              "agente,\n  ou pode estar afirmado sem elas. "
              "CONFIRA O CONTEÚDO, NÃO A PROCEDÊNCIA.")

    travadas = [f for f in frentes if f["veredicto"] == "TRAVADA"]
    if travadas and not args.json:
        print(f"\n{len(travadas)} TRAVADA(S): disparou em segundo plano de dentro "
              "de um subagente,\ne a notificação de conclusão não chega ali. "
              "Ela não vai voltar sozinha.")
        print("Antes de redisparar, veja se o dossiê chegou a ser escrito: se a "
              "frente\nmorreu ANTES dele, a redescoberta não é de graça.")
    return 1 if travadas else 0


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
