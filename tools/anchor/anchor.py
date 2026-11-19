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


# A partir de quanto contexto vale oferecer o `/compact` na troca de atividade.
# Abaixo disso, compactar custa mais (o resumo, e o cache que se refaz) do que
# o que a janela relê.
LIMIAR_TROCA = 100_000
# O fim do transcrito basta: a última resposta e o último marco de compactação
# estão lá. Ler o arquivo inteiro a cada mensagem seria o hook pesando.
CAUDA = 8 * 1024 * 1024
# Comando da porta com card: os números ali são atividade mesmo sem arquivo.
PORTA = re.compile(r"^\s*/(?:elcamargo-ai-flow:)?elcamargo-")
CARD = re.compile(r"(?<![\w.-])\d{4,6}(?![\w.-])")


def contexto_da_janela(transcrito: Path) -> int | None:
    """Quantos tokens a janela principal relê a cada resposta, pelo transcrito.

    É a soma de entrada, escrita e leitura de cache da última resposta da
    janela (subagente fica de fora: `isSidechain`). Se depois dela houve
    compactação, vale o `postTokens` do marco — senão a janela recém-compactada
    pareceria ainda cheia, e o aviso viria logo depois de a pessoa segui-lo.
    """
    try:
        with transcrito.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - CAUDA))
            linhas = f.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for linha in reversed(linhas):
        if '"compact_boundary"' not in linha and '"usage"' not in linha:
            continue
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
            return int((r.get("compactMetadata") or {}).get("postTokens") or 0)
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        u = (r.get("message") or {}).get("usage") or {}
        if u:
            return sum(int(u.get(k) or 0) for k in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return None


def atividades_citadas(prompt: str, ids: set[str]) -> set[str]:
    """As atividades que a mensagem nomeia: as que existem, e card novo na porta."""
    citadas = {i for i in ids
               if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", prompt)}
    if PORTA.match(prompt):
        citadas |= set(CARD.findall(prompt))
    return citadas


def _maquina_compacta() -> bool | None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doctor"))
        import compactacao  # noqa: PLC0415
        return compactacao.ligada()
    except Exception:  # noqa: BLE001
        return None


def aviso_de_troca(agents: Path, evento: dict, ids: set[str]) -> str | None:
    """Oferece `/compact` quando a janela troca de atividade carregando muito.

    Medido de 02 a 15/11/2026: a janela principal foi 19% do custo, com
    contexto médio de 141 mil — quase tudo de atividades que já tinham saído
    dela. Cada resposta relê esse contexto, e a atividade nova não precisa de
    nada dele: o estado de cada uma está no arquivo dela.

    Por isso é na TROCA, e não por tamanho: dentro da mesma atividade o
    contexto ainda serve, e a compactação automática já cuida do teto. E é
    oferta, não ordem — a janela centralizadora é escolha da pessoa.

    Avisa uma vez por enchente: depois de avisar, só volta a avisar quando o
    contexto tiver caído abaixo do limiar. A janela que orquestra várias
    atividades troca o tempo todo, e um aviso a cada troca vira ruído.
    """
    sessao = re.sub(r"[^A-Za-z0-9_.-]", "_", str(evento.get("session_id") or ""))[:64]
    prompt = str(evento.get("prompt") or "")
    if not sessao or not prompt:
        return None
    citadas = atividades_citadas(prompt, ids)
    if len(citadas) != 1:
        return None
    nova = citadas.pop()

    pasta = agents / ".janelas"
    registro = pasta / f"{sessao}.json"
    try:
        dados = json.loads(registro.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    anterior = dados.get("atividade")
    contexto = None
    if evento.get("transcript_path"):
        contexto = contexto_da_janela(Path(str(evento["transcript_path"])))

    avisar = (bool(anterior) and anterior != nova and contexto is not None
              and contexto >= LIMIAR_TROCA and not dados.get("avisou"))
    dados["atividade"] = nova
    if contexto is not None and contexto < LIMIAR_TROCA:
        dados["avisou"] = False
    if avisar:
        dados["avisou"] = True
    try:
        pasta.mkdir(exist_ok=True)
        _gravar(registro, json.dumps(dados))
        # Uma por sessão, e sessão morre: limpa o que ninguém toca há 30 dias.
        limite = time.time() - 30 * 86400
        for velho in pasta.glob("*.json"):
            if velho.stat().st_mtime < limite:
                velho.unlink()
    except OSError:
        pass
    if not avisar:
        return None

    texto = (
        f"[janela] Esta janela relê ~{contexto // 1000} mil tokens a cada resposta, "
        f"quase tudo da atividade {anterior}. A {nova} não precisa disso: o estado de "
        "cada atividade está no arquivo dela. Antes de começar, ofereça à pessoa, em "
        "uma linha, rodar `/compact` — a janela continua a mesma, só mais leve. Se "
        "ela preferir seguir, siga sem insistir."
    )
    if _maquina_compacta() is False:
        texto += (" Esta máquina também só compacta sozinha perto de 1 milhão; diga "
                  "que `python3 " + str(Path(__file__).resolve().parents[1] / "doctor"
                                         / "compactacao.py") + " ligar` compacta em 200 mil.")
    return texto


def principal(argv=None, evento: dict | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raiz", default=".")
    p.add_argument("--contexto", action="store_true",
                   help="PreToolUse de Bash: grava quem vai rodar o comando, e só")
    args = p.parse_args(argv)
    if evento is None:
        evento = ler_evento()

    if args.contexto:
        # Silêncio sempre: um PreToolUse que fala aparece em toda chamada.
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
    anotar_sessao(agents, evento)

    abertas = []
    ids: set[str] = set()
    for arquivo in sorted((agents / "atividades").glob("*.md")):
        try:
            texto = arquivo.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = front_matter(texto)
        ids.add(meta.get("id") or arquivo.stem)
        # Sem Histórico é relatório salvo em `atividades/`, não atividade: o
        # mesmo corte do `painel` e do `listar` (flow_state.separar_relatorios).
        if meta.get("status") != "em_andamento" or "\n## Histórico" not in texto:
            continue
        abertas.append(meta)

    troca = aviso_de_troca(agents, evento, ids)
    if not abertas:
        if troca:
            print(troca)
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
    if troca:
        linhas.append(troca)
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
