#!/usr/bin/env python3
"""Métricas do fluxo, do projeto até o agente, com drill-down.

O que ela mede, e por quê
------------------------

Uma atividade rodada pelo fluxo deixa rastro em três lugares que ninguém junta
à mão: o arquivo da atividade (steps, conferências, artefatos), os transcritos
de sessão em disco (tokens, turnos, relógio, um arquivo por subagente) e o Git
(o tamanho da entrega). Esta ferramenta junta os três e grava o resultado, para
que a pergunta "quanto custou, e onde" tenha resposta sem arqueologia.

Cinco níveis, e cada um soma exatamente o de baixo:

    projeto  ->  atividade  ->  step  ->  agente  ->  conferência

O que ela NÃO prova
-------------------

**Não mede pontos de função.** PF é contagem de praticante lendo a entrega, e
não sai de transcrito nenhum. Quem quiser produtividade por PF declara o número
em `pf` no arquivo da atividade; sem ele, a métrica de PF simplesmente não
aparece — em vez de aparecer errada.

**A hora humana é um modelo, não um cronômetro.** Ela mede o intervalo entre o
fim de uma resposta e a mensagem seguinte da pessoa, com teto, mais um custo de
reentrada por interação. O teto existe porque latência crua não distingue
"lendo por oito minutos" de "almoçando e respondendo em trinta segundos". Os
dois parâmetros ficam no config, e o relatório imprime qual usou.

**O custo em dinheiro é de tabela de API.** Quem roda por assinatura não paga
isso; é teto, e o relatório diz isso na cara.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))
from flow_state import (  # noqa: E402
    STEPS, Atividade, FlowStateError, percurso, resolve_agents_dir)
import config as C  # noqa: E402

# PREÇO POR MILHÃO DE TOKENS, **POR MODELO**.
#
# Consultado em 04/09/2026 na documentação de preço da Anthropic. Fica aqui, e
# não no config, porque é do modelo e não do projeto — mas `[metricas] precos`
# continua sobrescrevendo, para quem tiver desconto negociado.
#
# POR QUE POR MODELO, E NÃO UMA TABELA SÓ. A tabela anterior era
# `entrada 15.0 / cache_escrita 18.75 / cache_leitura 1.50 / saida 75.0` — que
# é o preço do **Opus 4.1 e do Opus 4, ambos aposentados**. Os transcritos
# mostram `claude-opus-5`, que custa 5 e 25, com cache lido a 0,50. Todo custo
# que este coletor reportou até aqui saiu ~3x INFLADO, e o número foi para uma
# apresentação de gestão. Uma tabela única não erra só quando o preço muda —
# ela erra sempre que uma frente roda em modelo diferente, que é exatamente o
# que se quer poder avaliar.
#
# CACHE DE ESCRITA: o Claude Code usa TTL de 1 hora, que custa 2x a entrada. A
# de 5 minutos custa 1,25x. O transcrito NÃO diz qual foi usada — por isso o
# padrão é declarado em `TTL_DE_CACHE` e impresso no rodapé, em vez de
# escolhido em silêncio.
PRECOS_POR_MODELO = {
    #                    entrada  cache 5m  cache 1h  cache lido  saída
    "claude-fable-5-1":  (10.0,   12.50,    20.0,     0.25,       50.0),
    "claude-fable-5":    (10.0,   12.50,    20.0,     1.00,       50.0),
    "claude-opus-5":     ( 5.0,    6.25,    10.0,     0.50,       25.0),
    "claude-opus-4-8":   ( 5.0,    6.25,    10.0,     0.50,       25.0),
    "claude-opus-4-7":   ( 5.0,    6.25,    10.0,     0.50,       25.0),
    "claude-opus-4-6":   ( 5.0,    6.25,    10.0,     0.50,       25.0),
    "claude-opus-4-5":   ( 5.0,    6.25,    10.0,     0.50,       25.0),
    "claude-sonnet-5":   ( 2.0,    2.50,     4.0,     0.20,       10.0),
    "claude-sonnet-4-6": ( 3.0,    3.75,     6.0,     0.30,       15.0),
    "claude-sonnet-4-5": ( 3.0,    3.75,     6.0,     0.30,       15.0),
    "claude-haiku-4-5":  ( 1.0,    1.25,     2.0,     0.10,        5.0),
}

# Claude Code usa cache de 1 hora. Declarado, e não suposto.
TTL_DE_CACHE = "1h"

# Turno cujo modelo não está na tabela cai aqui. NÃO é zero — zero esconderia
# gasto — e não é o mais caro — isso inventaria gasto. É um modelo declarado, e
# o registro diz quais modelos caíram nele.
PADRAO_DE_PRECO = "claude-opus-5"


def precos_do_modelo(modelo: str, ttl: str = TTL_DE_CACHE) -> dict:
    linha = PRECOS_POR_MODELO.get(modelo) or PRECOS_POR_MODELO[PADRAO_DE_PRECO]
    entrada, c5m, c1h, lido, saida = linha
    return {"entrada": entrada, "cache_escrita": c1h if ttl == "1h" else c5m,
            "cache_leitura": lido, "saida": saida}


def custo_do_modelo(uso: dict, modelo: str, ttl: str = TTL_DE_CACHE) -> float:
    return custo(uso, precos_do_modelo(modelo, ttl))


def _juntar_modelos(a: dict, b: dict) -> dict:
    juntos = {m: {"turnos": v["turnos"], "uso": dict(v["uso"])} for m, v in a.items()}
    for m, v in b.items():
        alvo = juntos.setdefault(m, {"turnos": 0, "uso": {}})
        alvo["turnos"] += v["turnos"]
        alvo["uso"] = somar(alvo["uso"], v["uso"])
    return juntos


# Mantida para quem sobrescreve em `[metricas] precos`, e para o rodapé.
PRECOS_PADRAO = precos_do_modelo(PADRAO_DE_PRECO)

CHAVES_USO = {
    "input_tokens": "entrada",
    "cache_creation_input_tokens": "cache_escrita",
    "cache_read_input_tokens": "cache_leitura",
    "output_tokens": "saida",
}

# Teto por interação e custo de reentrada, em minutos. Ver docstring.
TETO_LEITURA_MIN = 10
REENTRADA_MIN = 3
# 365 × 24 ÷ 12. A assinatura é cobrada por mês de calendário, e o rateio por
# hora precisa de um mês de tamanho fixo — senão fevereiro sai mais caro por
# hora que março, e a comparação entre atividades passa a depender do mês.
HORAS_POR_MES = 730
# Estimativa APF: horas por ponto de função, nas duas produtividades que a
# Elcamargo usa para orçar. Não são medida — são a régua de mercado contra a
# qual o medido é comparado.
PRODUTIVIDADES_APF = (6, 10)


# ---------------------------------------------------------------------------
# achar os transcritos


def slug_do_projeto(raiz: Path) -> str:
    r"""O nome que o harness dá à pasta de sessões: `/` E `.` viram `-`.

    O `.` faltava, e o defeito era da pior espécie — silencioso e para baixo.
    Um projeto cujo caminho tenha ponto, `~/dev/my.app`, produzia um slug que
    não existe em disco: `pastas_de_sessao` não achava nada, e a métrica saía
    **zero com cara de resultado**.

    Confirmado contra a pasta real de uma worktree, não deduzido:
    `<raiz>/.claude/worktrees/x` vira `<slug>--claude-worktrees-x`, com DOIS
    traços — um do `/`, outro do `.`.

    A regra do harness é mais larga que `/` e `.`: **todo** caractere que não
    é letra nem dígito vira `-`. No Windows isso é o que faz a métrica sair de
    zero — `C:\dev\My_Projects\App` só acha a pasta como
    `C--dev-My-Projects-App`, com o `:`, as barras invertidas e o `_`
    convertidos. Conferido contra `~/.claude/projects` de uma máquina Windows.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(raiz.resolve()))


def raiz_principal(raiz: Path) -> Path:
    """A raiz do repositório, mesmo chamada de dentro de uma worktree.

    Sem isto o pacote respondia DUAS coisas diferentes para "que projeto é
    este": `resolve_agents_dir` perguntava ao `--git-common-dir` (e por isso
    escrevia sempre no `.agents` da raiz), e `pastas_de_sessao` respondia pelo
    diretório atual. As duas discordavam dentro de uma worktree, **e a
    discordância era silenciosa**.

    O estrago medido em 12/09/2026, no `acme-backoffice`:

        da raiz principal        13 pastas, 52 transcritos
        de dentro de worktree     2 pastas, 39 transcritos

    Onze pastas somem porque `alvo` vira o slug DA WORKTREE, e a regra de
    prefixo `alvo + "--"` — a única que alcança worktree já podada — deixa de
    casar com qualquer coisa. Dói mais justamente nas atividades antigas e
    grandes, que são as que rodaram em worktree podada.

    E o resultado saía com a cara do certo: como o `.agents` é o da raiz, a
    rodada feita de dentro da worktree **sobrescreve o `projeto.json` da raiz**.
    Quem abre o arquivo vê o caminho do repositório principal e não tem como
    saber que a coleta enxergou dois treze avos do corpus. O único vestígio é o
    campo `raiz`, e ele foi lido como se fosse a raiz.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            comum = Path(r.stdout.strip())
            if comum.name == ".git":
                return comum.parent.resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return raiz.resolve()


def pastas_de_sessao(raiz: Path) -> list[Path]:
    """As pastas de sessão DESTE repositório, worktrees inclusive.

    Ela pergunta ao Git quais são as worktrees, em vez de adivinhar por prefixo
    de nome — e a heurística que ela substitui caiu num caso real. Os
    repositórios `acme-loja` e `acme-loja-admin` são
    IRMÃOS, e o slug do segundo é `<slug do primeiro>-admin`. Uma worktree
    também é `<slug>-<algo>`. **Pelo nome, irmão e worktree são
    indistinguíveis**, e `startswith` fazia um projeto engolir as sessões do
    vizinho: custo inflado com trabalho que não era dele, em silêncio.

    `git worktree list` responde com autoridade, e de graça ganha o caso que o
    prefixo nunca alcançaria: worktree criada FORA da raiz do projeto.

    Mais as pastas que começam com `<slug>--`, de dois traços. Elas recuperam a
    worktree que já foi PODADA e cujas sessões continuam no disco — o Git não
    a lista mais, e sem isso o trabalho feito nela desapareceria da conta. E o
    irmão não entra por aqui: dois traços só nascem de `/.`, um subdiretório
    OCULTO da raiz, e é onde o harness põe as worktrees dele. Um repositório
    irmão é `<slug>-<nome>`, de um traço só.

    O que ela continua não achando: worktree fora da raiz que também já foi
    podada. Nem o Git nem o nome dizem que ela existiu.
    """
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []
    # O alvo é a RAIZ do repositório, nunca o diretório de onde se chamou — ver
    # `raiz_principal`. A pasta da própria chamada entra também, para o caso de
    # alguém coletar fora de um repositório Git.
    principal = raiz_principal(raiz)
    alvo = slug_do_projeto(principal)
    nomes = {alvo, slug_do_projeto(raiz)}
    try:
        r = subprocess.run(
            ["git", "-C", str(principal), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if r.returncode == 0:
            for linha in r.stdout.splitlines():
                if linha.startswith("worktree "):
                    nomes.add(slug_do_projeto(Path(linha[9:])))
    except (OSError, subprocess.SubprocessError):
        pass          # sem Git, sobram o alvo e as podadas de dois traços
    return [p for p in base.iterdir() if p.is_dir()
            and (p.name in nomes or p.name.startswith(alvo + "--"))]


def _num(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _quando(registro: dict):
    if "quando" in registro:
        return registro["quando"]          # já analisado uma vez, no Corpus
    t = registro.get("timestamp")
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# o corpus: cada transcrito lido uma vez por rodada


CAMPOS_USADOS = ("type", "promptId", "isSidechain", "gitBranch", "cwd")


def _compactar(o: dict) -> dict:
    """Só os campos que alguma métrica usa, com o relógio já analisado.

    O conteúdo da mensagem é a parte grande de um transcrito, e dele só
    interessam duas coisas: o texto (para saber se a mensagem foi decisão de
    gente ou injeção de skill) e quantas perguntas de portão houve. Guardar o
    resto seria carregar o corpus inteiro na memória para não usar.
    """
    msg = o.get("message") or {}
    conteudo = msg.get("content")
    blocos = conteudo if isinstance(conteudo, list) else []
    if isinstance(conteudo, str):
        texto = conteudo[:400]
    else:
        texto = " ".join(b.get("text", "") for b in blocos
                         if isinstance(b, dict) and b.get("type") == "text")[:400]
    perguntas = sum(
        len(b.get("input", {}).get("questions", []) or [])
        for b in blocos
        if isinstance(b, dict) and b.get("type") == "tool_use"
        and b.get("name") == "AskUserQuestion")
    u = msg.get("usage") or {}
    compacto = {k: o[k] for k in CAMPOS_USADOS if k in o}
    compacto["quando"] = _quando(o)
    compacto["uso"] = {nossa: _num(u.get(bruta)) for bruta, nossa in CHAVES_USO.items()}
    # A chave de UMA resposta de API. Sem ela não há como saber que dois
    # registros são o mesmo turno — e eles são, com frequência: ver `Corpus`.
    compacto["resposta"] = msg.get("id") or ""
    # `<synthetic>` aparece em mensagem que o harness fabrica — ela não custa
    # token nenhum, e tratá-la como modelo poluiria a mistura.
    modelo = msg.get("model") or ""
    compacto["modelo"] = "" if modelo.startswith("<") else modelo
    compacto["texto"] = texto
    # Só a linha de comando que cita a ferramenta do fluxo. É dela que sai a
    # PROVA de que esta sessão operou esta atividade neste instante — e é
    # esparsa, que é o que a janela por ilhas precisa. Guardar o comando
    # inteiro carregaria o corpus de `npm run build`.
    compacto["comandos"] = " ".join(
        str(b.get("input", {}).get("command", ""))[:300]
        for b in blocos
        if isinstance(b, dict) and b.get("type") == "tool_use"
        and "flow_state.py" in str(b.get("input", {}).get("command", "")))[:600]
    compacto["perguntas"] = perguntas
    return compacto


class Corpus:
    """Os transcritos desta rodada, cada arquivo analisado UMA vez.

    Eram 2N passadas de `json.loads` sobre o corpus inteiro: uma em `_provas` e
    uma no laço principal, por atividade. Com 14 atividades, 28 passadas — os
    ~45 s medidos numa coleta completa, contra ~3 s de uma atividade só. A
    conta explica o número, e explica por que o gancho, que roda
    `--atividade`, já custava 3 s: ele sempre fez 2 passadas, não 28.

    **Não é cache, e a diferença é o ponto.** Ele não sobrevive à rodada, logo
    não tem chave de invalidação para errar. Um cache por (arquivo, mtime,
    tamanho) resolveria o mesmo tempo e traria de volta a família de defeito
    mais cara deste pacote: transcrito acrescido dentro da mesma
    granularidade de mtime serviria número velho em silêncio, e persistiria
    entre rodadas — que é pior que lento.
    """

    def __init__(self) -> None:
        self._por_arquivo: dict[Path, list[dict]] = {}
        self._portador: dict[str, dict] = {}
        self.arquivos_lidos = 0
        self.turnos_repetidos = 0

    def registros(self, caminho: Path) -> list[dict]:
        if caminho not in self._por_arquivo:
            lidos = self._ler(caminho)
            self._deduplicar(lidos)
            self._por_arquivo[caminho] = lidos
            self.arquivos_lidos += 1
        return self._por_arquivo[caminho]

    def _deduplicar(self, registros: list[dict]) -> None:
        """Um turno é uma RESPOSTA de API, não um registro no arquivo.

        Três mecanismos põem a mesma resposta no corpus mais de uma vez, e os
        três foram medidos em 19/09/2026, num corpus de 257.819 registros:

        1. **um registro por bloco de conteúdo** — `thinking`, `text` e
           `tool_use` viram três registros, com `uuid` DIFERENTE e o `usage`
           INTEIRO em cada um. É a maior fatia, e é a que sobrevive a qualquer
           deduplicação por `uuid`;
        2. **instantâneos de streaming** — o mesmo par (`uuid`, `message.id`)
           reaparece com `saida` crescendo: 5, depois 561. Entrada e cache
           ficam constantes; medido, `saida` é o ÚNICO campo que varia;
        3. **sessão retomada e arquivo que repete a si mesmo** — cópias
           idênticas, e as tardias vêm com o `usage` ZERADO.

        Somar tudo inflava os tokens em **5,14x**. Deduplicar por `uuid`, que
        era a correção proposta, ainda deixava **1,82x** de pé, porque não
        alcança o mecanismo 1 — e teria publicado um número que parece
        consertado.

        **A regra: a chave é `message.id`, e vence o maior `saida`.** Ela cobre
        os três de uma vez, inclusive a armadilha do zerado — guardar a última
        ocorrência trocaria um número inflado por um deflacionado, que é pior,
        porque não acende luz nenhuma.

        **O registro repetido NÃO é descartado**, só perde o `uso` e ganha
        `repetido`. Ele continua carregando `comandos`, `texto` e relógio, que
        são a prova de vínculo entre sessão e atividade — jogá-lo fora
        consertaria o custo quebrando a atribuição.
        """
        for o in registros:
            if o.get("type") != "assistant":
                continue
            chave = o.get("resposta")
            if not chave:
                continue                  # sem chave, não há como saber: conta
            anterior = self._portador.get(chave)
            if anterior is None:
                self._portador[chave] = o
                continue
            self.turnos_repetidos += 1
            # Vence o maior `saida`. Empate mantém o portador atual, que é o de
            # relógio mais antigo dentro de uma leitura — e a soma não depende
            # disso: o máximo é o mesmo em qualquer ordem.
            if o["uso"].get("saida", 0.0) > anterior["uso"].get("saida", 0.0):
                anterior["uso"] = {k: 0.0 for k in anterior["uso"]}
                anterior["repetido"] = True
                self._portador[chave] = o
            else:
                o["uso"] = {k: 0.0 for k in o["uso"]}
                o["repetido"] = True

    @staticmethod
    def _ler(caminho: Path) -> list[dict]:
        registros = []
        for linha in caminho.open(encoding="utf-8", errors="replace"):
            try:
                registros.append(_compactar(json.loads(linha)))
            except json.JSONDecodeError:
                continue          # linha corrompida não derruba o arquivo
        return registros


# ---------------------------------------------------------------------------
# ler um transcrito


def papel_do_agente(prompt: str) -> tuple[int | None, str]:
    """De qual step o subagente é, e em que papel.

    A ordem importa e já errou uma vez: procurar `auditor` antes de `**step N**`
    joga o titular do step 3 no balde de auditor, porque o prompt dele cita a
    palavra. O papel titular é reconhecido pelo destaque em negrito, que é como
    as skills abrem o prompt do subagente.
    """
    # Dois dígitos, e o número conferido contra o fluxo: com `(\d)` o
    # `**step 10**` virava step 1, e o custo do portão 10 caía na conta do
    # Gestor da Atividade sem nada acusar.
    m = re.search(r"\*\*step\s*(\d{1,2})", prompt)
    if m and int(m.group(1)) in STEPS:
        return int(m.group(1)), "titular"
    n = re.search(r"step\s*(\d{1,2})", prompt, re.I)
    step = int(n.group(1)) if n and int(n.group(1)) in STEPS else None
    if re.search(r"auditor|completude|adversarial|revise uma volta", prompt, re.I):
        return step, "auditor"
    if re.search(r"frente de|screen-drawer|frente \*\*", prompt, re.I):
        return step or 9, "frente"
    return step, "dirigido"


def primeiro_prompt(caminho: Path, corpus: "Corpus") -> str:
    for o in corpus.registros(caminho):
        if o.get("type") == "user" and o["texto"]:
            return o["texto"]
    return ""


def janela_da_atividade(campos: dict) -> tuple[datetime | None, datetime | None]:
    """O intervalo que a própria atividade declara, em UTC.

    `criado_em` e `concluido_em` (ou `atualizado_em`) são gravados em hora
    local pelo `flow_state.py`; os transcritos são UTC. Converter aqui, e não
    comparar ingênuo, foi o que impediu a janela de nascer três horas fora.
    """
    def ler(chave: str):
        bruto = (campos.get(chave) or "").strip()
        if not bruto:
            return None
        try:
            return datetime.strptime(bruto, "%Y-%m-%d %H:%M:%S").astimezone()
        except ValueError:
            return None
    inicio = ler("criado_em")
    # `atualizado_em` NÃO serve de teto. Qualquer toque no arquivo o move para
    # agora — inclusive um `avancar` de teste, ou um `artefato` registrado dias
    # depois. Medido: um `avancar` acidental numa atividade parada esticou a
    # janela dela até hoje e fez a atividade engolir 8 mil turnos de trabalho
    # de outro assunto, triplicando o custo dela no painel.
    #
    # Só `concluido_em` é teto, porque só ele significa "acabou".
    fim = ler("concluido_em")
    return inicio, fim


def prazo_esta_aberto(registro: dict) -> bool:
    """O prazo deste registro parou numa entrega, ou só no último registro?

    A chave `prazo_aberto` nasceu na 2.5.0. Registro coletado antes dela não a
    tem, e ninguém vai recoletar o histórico inteiro para ler um rótulo certo:
    o recuo é `concluido_em`, que está no esquema desde o começo e responde a
    mesma pergunta. Um registro velho de atividade concluída continua lendo
    fechado.
    """
    marca = registro.get("prazo_aberto")
    if marca is not None:
        return bool(marca)
    return not (registro.get("concluido_em") or "").strip()


# Verbos do `flow_state.py` que ESCREVEM estado. Quem os roda estava conduzindo
# a atividade; `status` e `listar` aparecem em sessão que só olhou o board.
VERBOS_QUE_OPERAM = ("iniciar", "avancar", "conferencia", "artefato",
                     "concluir", "corrigir", "pf")


def operou_a_atividade(registro: dict, ident: str) -> bool:
    """Esta sessão OPEROU a atividade neste instante?

    A prova de uma sessão declarada não pode ser "este registro é dela" — isso
    é todo registro, e a janela por ilhas precisa de prova ESPARSA para
    separar o trabalho de uma atividade do da seguinte.

    Medido em 11/09/2026, e é por isso que esta função existe: com a sessão
    inteira virando prova, duas atividades declarando a MESMA sessão, com datas
    disjuntas, reivindicaram cada uma a sessão inteira — a soma deu 36.138
    turnos onde a sessão tinha 24.780. E o caso é a maioria, não a exceção: das
    sessões que escrevem estado, 41% no backoffice e 80% no app operam mais
    de uma atividade. Numa janela só, em sequência — que é como trabalha quem
    tem máquina fraca.

    O comando com o id é o registro do instante em que a sessão agiu sobre a
    atividade. Esparso por natureza, e ainda assim registro e não inferência.
    """
    comandos = registro.get("comandos") or ""
    if not ident or ident not in comandos or "flow_state.py" not in comandos:
        return False
    return any(f" {verbo} " in comandos or comandos.rstrip().endswith(f" {verbo}")
               for verbo in VERBOS_QUE_OPERAM)


def prova_de_vinculo(registro: dict, branch: str, worktree: str, ident: str,
                     sessoes: set | None = None) -> bool:
    """Este registro é, sem dúvida, desta atividade?

    Três provas, e nenhuma sozinha basta para o transcrito inteiro:

    `gitBranch` é do repositório PRINCIPAL, não da worktree. Medido: numa
    atividade que rodou em worktree por 27 h, a branch dela só apareceu na
    última tarde, quando o repositório principal por acaso a checou. Filtrar
    por branch cortava 23 das 41 interações humanas.

    `cwd` acerta a worktree, mas o orquestrador trabalha da raiz e um subagente
    inteiro — o Analista de Sistema, 725 turnos — rodou lá também.

    **A terceira, prometida neste docstring desde sempre, não existe — e foi
    MEDIDA antes de ser descartada.** `ident` chega como argumento e não é
    usado. A ideia era o id da atividade num comando do fluxo; ela falha das
    duas formas possíveis:

    - **Larga** (`id` junto de `flow_state.py`): o projeto quase dobrou, de
      46.565 turnos para 84.611, com a `1061` saltando de 4.821 para 16.618.
      Uma sessão que dá uma olhada no board passa a herdar a atividade inteira.
    - **Estreita** (só verbos que escrevem estado): ainda inflava a `1061` para
      14.300 **e** derrubava a revisão para 247 turnos, longe dos milhares que
      ela teve.

    O motivo é estrutural: esta função responde pela SESSÃO inteira, não pelo
    registro. Um comando basta para a sessão toda contar — o que é razoável
    para branch e `cwd`, e frágil demais para "citou o id". Achado por `acme-backoffice-0f` em
    11/09/2026, ao regerar as métricas e ver a primeira revisão da trilha
    `revisao` sair como *não atribuída*: zero turno, zero custo, zero hora
    humana, para a atividade que gerou oito correções no pacote.

    **Na trilha `revisao` as duas primeiras são impossíveis por construção.** A
    branch gravada é remota — e quem a gravou foi a correção da 2.26.1, o
    conserto certo para o `branch: HEAD` da worktree detached; medido, nenhum
    dos 99.427 registros com `gitBranch` deste repositório começa com
    `origin/`. E a worktree da revisão se remove ao fim, por doutrina; mesmo
    antes disso o orquestrador trabalha da raiz.

    A terceira sobrevive às duas: o id está escrito em todo comando
    `flow_state.py` que a sessão roda. Ela exige as DUAS coisas no mesmo
    comando — o id e o nome da ferramenta —, porque id curto sozinho casaria
    com prosa.

    Por isso as três só servem para dizer que a SESSÃO tocou a atividade. Quem
    recorta é a janela declarada no arquivo dela.
    """
    # A PROVA QUE NÃO É INFERÊNCIA vem antes das outras duas, e dispensa as
    # duas quando existe: `sessoes` no arquivo da atividade é o que o
    # `flow_state.py` gravou a cada escrita de estado, e o id da sessão bate
    # com o nome do arquivo de transcrito, exato. Ver `_anotar_sessao`.
    #
    # Ela é tratada em `ler_transcrito`, que conhece o arquivo; aqui só sobram
    # as duas inferências, para as atividades abertas antes da 2.29.0.
    if branch and registro.get("gitBranch") == branch:
        return True
    # `origin/X` e `X` são a mesma branch. O front-matter grava a remota quando
    # a árvore é detached; o transcrito só conhece a local.
    if branch.startswith("origin/") and registro.get("gitBranch") == branch[7:]:
        return True
    cwd = registro.get("cwd") or ""
    if worktree and cwd.startswith(worktree):
        return True
    return False


def ler_transcrito(caminho: Path, janela: "Vizinhanca | None" = None,
                   vinculo: tuple[str, str, str] | None = None,
                   corpus: "Corpus | None" = None) -> dict:
    """Tokens, turnos, relógio e interações humanas de um arquivo de sessão.

    `janela` recorta por tempo; `vinculo` é (branch, worktree, id) e serve só
    para responder se esta sessão tocou a atividade em algum momento. Um
    transcrito quase nunca é de uma atividade só — a pessoa troca de assunto na
    mesma sessão — e sem os dois a atividade herdaria a conversa inteira.

    O `corpus` é quem já leu o arquivo. Sem ele, lê-se um só, para quem chamar
    esta função isolada.
    """
    uso = {k: 0.0 for k in PRECOS_PADRAO}
    turnos = 0
    momentos: list[datetime] = []
    humanas: list[tuple[datetime, str]] = []
    respostas: list[datetime] = []
    perguntas = 0
    prompts_vistos: set[str] = set()
    tocou = vinculo is None
    # A prova que não é inferência: a atividade DECLARA quais sessões
    # trabalharam nela, e o nome do arquivo de transcrito É o id da sessão.
    # Quando ela declara, as duas inferências não são consultadas — elas
    # existem para atividades abertas antes de este campo existir.
    if vinculo and len(vinculo) > 3 and vinculo[3]:
        tocou = caminho.stem in vinculo[3]
        # Um subagente vive num arquivo próprio, dentro de `<sessão>/subagents`;
        # o id dele não é o da sessão. Ele herda a sessão que o disparou, que é
        # a pasta avô.
        if not tocou and caminho.parent.name == "subagents":
            tocou = caminho.parent.parent.name in vinculo[3]
        if not tocou:
            return {"uso": uso, "turnos": 0, "momentos": [], "humanas": [],
                    "respostas": [], "perguntas_portao": 0, "tocou": False,
                    "por_modelo": {}}

    por_modelo: dict[str, dict] = {}
    for o in (corpus or Corpus()).registros(caminho):
        if vinculo and not tocou and prova_de_vinculo(o, *vinculo[:3]):
            tocou = True
        quando = o["quando"]
        if janela is not None and not janela.contem(quando):
            continue
        tipo = o.get("type")

        if tipo == "assistant":
            if o.get("repetido"):
                continue      # mesmo turno, outro registro — ver `Corpus`
            uso = somar(uso, o["uso"])
            # O gasto de cada turno vai para o balde DO MODELO daquele turno.
            # Somar tudo num balde só cobraria Opus por turno de Haiku — e o
            # erro cresce justamente quando a cascata de modelo funciona.
            m = o.get("modelo") or ""
            if m:
                balde = por_modelo.setdefault(m, {"turnos": 0, "uso": {}})
                balde["turnos"] += 1
                balde["uso"] = somar(balde["uso"], o["uso"])
            turnos += 1
            if quando:
                momentos.append(quando)
                if not o.get("isSidechain"):
                    respostas.append(quando)
            perguntas += o["perguntas"]
            continue

        if tipo != "user" or o.get("isSidechain") or not o.get("promptId"):
            continue
        pid = o["promptId"]
        if pid in prompts_vistos:
            continue
        s = o["texto"].strip()
        # Injeção de skill, imagem colada e comando local não são decisão de
        # ninguém: entram no transcrito como mensagem de usuário e inflariam a
        # conta de interações, que é o denominador do custo de reentrada.
        if not s or s.startswith("[Image") or s.startswith("Base directory") \
                or s.startswith("<") or "local-command" in s:
            continue
        prompts_vistos.add(pid)
        if quando:
            humanas.append((quando, s))
            momentos.append(quando)

    return {
        "uso": uso,
        "por_modelo": por_modelo,
        "turnos": turnos,
        "momentos": momentos,
        "humanas": humanas,
        "respostas": respostas,
        "perguntas_portao": perguntas,
        "tocou": tocou,
    }


def tempo_humano(humanas: list[tuple[datetime, str]], respostas: list[datetime],
                 teto_min: int, reentrada_min: int) -> dict:
    """Leitura e decisão medidas, mais reentrada de contexto por interação."""
    marcos = sorted(respostas)
    leitura = 0.0
    contadas = 0
    intervalos: list[list[str]] = []
    for quando, _ in sorted(humanas):
        anteriores = [m for m in marcos if m <= quando]
        if not anteriores:
            continue
        gap = min((quando - anteriores[-1]).total_seconds(), teto_min * 60)
        leitura += gap
        contadas += 1
        # O intervalo JA' CAPADO, gravado no registro. Sem ele a hora humana de
        # um CONJUNTO de atividades paralelas não é calculável: o agregado não
        # diz quais foram os intervalos, e somar agregados conta a mesma pessoa
        # duas vezes no mesmo minuto. Ver `cmd_conjunto`.
        intervalos.append([(quando - timedelta(seconds=gap)).isoformat(),
                           quando.isoformat()])
    return {
        "interacoes": contadas,
        "leitura_h": round(leitura / 3600, 3),
        "reentrada_h": round(contadas * reentrada_min / 60, 3),
        "total_h": round(leitura / 3600 + contadas * reentrada_min / 60, 3),
        "intervalos": intervalos,
    }


def custo(uso: dict, precos: dict) -> float:
    return round(sum(uso.get(k, 0.0) * precos.get(k, 0.0) for k in precos) / 1_000_000, 2)


def somar(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0.0) + b.get(k, 0.0) for k in set(a) | set(b)}


# ---------------------------------------------------------------------------
# ler a atividade


def ler_atividade(caminho: Path) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    campos: dict[str, str] = {}
    if texto.startswith("---"):
        fim = texto.find("\n---", 3)
        for linha in texto[3:fim].splitlines():
            if ":" in linha:
                k, _, v = linha.partition(":")
                campos[k.strip()] = v.strip()
    conf: dict[str, int] = {}
    ferramentas: dict[str, dict[str, int]] = {}
    if "## Conferências" in texto:
        for linha in texto.split("## Conferências")[1].splitlines():
            if not linha.startswith("| 20"):
                continue
            partes = [p.strip() for p in linha.split("|")]
            if len(partes) < 5:
                continue
            ferramenta, veredicto = partes[2], partes[3]
            conf[veredicto] = conf.get(veredicto, 0) + 1
            ferramentas.setdefault(ferramenta, {})
            ferramentas[ferramenta][veredicto] = \
                ferramentas[ferramenta].get(veredicto, 0) + 1
    artefatos = 0
    caminhos: list[str] = []
    if "## Artefatos" in texto:
        bloco = texto.split("## Artefatos")[1].split("## Conferências")[0]
        for l in bloco.splitlines():
            if not l.startswith("| ") or "| ---" in l:
                continue
            artefatos += 1
            # A coluna do caminho, guardada inteira: uma linha traz mais de um
            # arquivo ("matriz-A.md, matriz-B.md"), e quem separa é quem lê.
            partes = [x.strip() for x in l.split("|")]
            if len(partes) >= 4:
                caminhos.append(partes[2])
    # O Histórico, lido pelo mesmo parser que o escreve: é onde moram as
    # voltas e os portões, e até a 2.56.0 esta função o pulava inteiro.
    historico = Atividade._parse_tabela(texto, "Histórico",
                                        ["Quando", "Step", "Nota"])
    return {
        "campos": campos,
        "percurso": percurso(historico),
        "conferencias": conf,
        "por_ferramenta": ferramentas,
        "artefatos": max(artefatos - 1, 0),
        "caminhos_de_artefato": caminhos[1:] if caminhos else [],
    }


def entrega_da_branch(raiz: Path, branch: str, base: str = "main",
                      desde: str = "") -> dict:
    """Tamanho da entrega — e o caminho muda quando a branch já foi mesclada.

    O jeito óbvio, `base...branch`, é o certo **enquanto a branch está viva**.
    Depois que ela entra na base, ele devolve VAZIO: a branch virou ancestral,
    e não há três pontos a comparar. O registro saía com `0 commits, 0 arquivos,
    +0` — e zero aqui se lê como "não entregou nada", que é o contrário de
    "entregou e foi mesclado".

    Medido no `acme-backoffice`: SEIS das onze atividades — todas as
    concluídas e mescladas — reportavam entrega zerada, e o total do projeto
    somava só as branches ainda abertas.

    Para a branch mesclada não existe mais o ponto de partida: o que sobra é o
    conjunto de commits DELA, e ele precisa de uma data — `criado_em` da
    atividade. Os dois caminhos medem coisas diferentes, e por isso o registro
    guarda **qual foi usado**:

    | `metodo` | O que ele mede |
    | --- | --- |
    | `diff` | o efeito LÍQUIDO da branch contra a base |
    | `commits` | o que os commits da atividade escreveram, retrabalho incluído |

    Uma linha corrigida duas vezes conta duas no `commits` e uma no `diff`.
    Comparar os dois números entre atividades sem olhar o método compara
    grandezas diferentes — e é por isso que ele é impresso, e não implícito.
    """
    def git(*args) -> str:
        try:
            r = subprocess.run(["git", "-C", str(raiz), *args],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def ok(*args) -> bool:
        try:
            return subprocess.run(["git", "-C", str(raiz), *args],
                                  capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def somar(saida: str) -> dict:
        m = re.search(r"(\d+) files? changed(?:, (\d+) insertions?...)?"
                      r"(?:, (\d+) deletions?...)?", saida)
        if not m:
            return {"arquivos": 0, "insercoes": 0, "remocoes": 0}
        return {"arquivos": int(m.group(1)), "insercoes": int(m.group(2) or 0),
                "remocoes": int(m.group(3) or 0)}

    if not branch:
        return {"metodo": "indisponivel",
                "motivo": "a atividade não declara `branch`"}
    if not git("rev-parse", "--verify", "--quiet", branch):
        return {"metodo": "indisponivel",
                "motivo": f"a branch `{branch}` não existe neste clone — "
                          f"nem local, nem buscada"}

    # Atividade que trabalhou DIRETO na base. `base...base` é vazio pela mesma
    # aritmética, e sem um ponto de partida não há entrega a isolar.
    if branch == base:
        if not desde:
            return {"metodo": "indisponivel",
                    "motivo": f"a atividade trabalhou direto em `{base}` e não "
                              f"declara `criado_em`"}
        mesclada = True
    else:
        mesclada = ok("merge-base", "--is-ancestor", branch, base)

    if not mesclada:
        alvo = f"{base}...{branch}"
        def stat(*extra) -> dict:
            return somar(git("diff", "--shortstat", alvo, *extra))
        total = stat()
        total["commits"] = len([x for x in
                                git("log", "--oneline", f"{base}..{branch}").splitlines() if x])
        total["testes"] = stat("--", "*spec.ts", "*spec.tsx", "*test.ts", "*test.tsx")
        total["docs"] = stat("--", "docs/")
        total["metodo"] = "diff"
        return total

    # Mesclada: sem data não há como separar os commits desta atividade dos de
    # todas as outras que também vivem na base. Aí a entrega fica AUSENTE, com
    # o motivo — nunca zerada.
    if not desde:
        return {"metodo": "indisponivel",
                "motivo": f"branch `{branch}` já está em `{base}` e a atividade "
                          f"não declara `criado_em` — sem ele não dá para separar "
                          f"os commits dela"}

    def commits(*extra) -> list[str]:
        # `--first-parent` segue SO' a linha da propria branch. Sem ele, um
        # `merge main` feito dentro da branch traz junto todos os commits da
        # base — o `1061` reportava 105 commits e +52.201 linhas, contra os
        # 23 que ele de fato escreveu.
        return [x for x in git("log", branch, "--first-parent", "--no-merges",
                               f"--since={desde}", "--format=%H", *extra).splitlines() if x]

    shas = commits()
    if not shas:
        # Zero commits aqui NÃO é medida de zero: é o isolamento que falhou.
        # Acontece quando o trabalho entrou na base por merge — `--no-merges`
        # descarta o merge e `--first-parent` não desce no lado dele. Devolver
        # `0 arquivos, +0` diria "não entregou nada" sobre uma atividade que
        # entregou e foi mesclada, que é o defeito inteiro que este caminho
        # existe para consertar.
        return {"metodo": "indisponivel",
                "motivo": f"nenhum commit próprio de `{branch}` desde {desde[:10]} — "
                          f"o trabalho provavelmente entrou por merge, e o merge "
                          f"não diz o que é desta atividade"}

    def stat(*extra) -> dict:
        soma = {"arquivos": 0, "insercoes": 0, "remocoes": 0}
        for sha in shas:
            um = somar(git("show", "--shortstat", "--format=", sha, *extra))
            for k in soma:
                soma[k] += um[k]
        return soma

    total = stat()
    total["commits"] = len(shas)
    total["testes"] = stat("--", "*spec.ts", "*spec.tsx", "*test.ts", "*test.tsx")
    total["docs"] = stat("--", "docs/")
    total["metodo"] = "commits"
    return total


# ---------------------------------------------------------------------------
# coletar


HORAS_DE_SILENCIO = 4
MARGEM_DE_PONTA_MIN = 30


def _provas(raiz: Path, vinculo: tuple, inicio: datetime | None,
            corpus: "Corpus") -> list[datetime]:
    """Todo instante em que alguma sessão provou estar nesta atividade."""
    achadas: list[datetime] = []
    declaradas = vinculo[3] if len(vinculo) > 3 else None
    for pasta in pastas_de_sessao(raiz):
        for sessao in sorted(pasta.glob("*.jsonl")):
            # Quando a atividade declara as sessões, o arquivo inteiro entra ou
            # fica de fora pelo nome — que É o id da sessão.
            if declaradas and sessao.stem not in declaradas:
                continue
            for o in corpus.registros(sessao):
                if declaradas:
                    # Sessão declarada: a prova é o COMANDO que operou a
                    # atividade, não o mero pertencimento à sessão.
                    if not operou_a_atividade(o, vinculo[2]):
                        continue
                elif not prova_de_vinculo(o, *vinculo[:3]):
                    continue
                quando = o["quando"]
                if quando and not (inicio and quando < inicio):
                    achadas.append(quando)
    achadas.sort()
    return achadas


class Vizinhanca:
    """Um registro conta se houver PROVA a menos de `silencio_h` dele.

    Intervalo único não serve. Duas coisas quebraram a versão com intervalo:

    A worktree continua no disco depois do merge e continua sendo usada para
    outro assunto — o "último toque" esticava a janela por mais um dia.

    E `atualizado_em` se move a cada escrita no arquivo, então uma atividade
    parada há dias podia, por um comando qualquer, passar a reivindicar tudo
    que aconteceu desde que ela nasceu.

    Proximidade resolve os dois sem precisar de teto declarado: o trabalho da
    atividade forma ilhas no tempo, e cada ilha carrega o que está perto dela.
    Um silêncio de `silencio_h` separa uma ilha da próxima.
    """

    def __init__(self, provas: list[datetime], inicio: datetime | None,
                 silencio_h: int = HORAS_DE_SILENCIO,
                 margem_min: int = MARGEM_DE_PONTA_MIN):
        self.provas = provas
        self.inicio = inicio
        self.limite = silencio_h * 3600
        self.margem = margem_min * 60

    def __bool__(self) -> bool:
        return bool(self.provas)

    def contem(self, quando: datetime | None) -> bool:
        """Interpola entre provas; quase não extrapola além delas.

        A diferença é tudo. Com raio simétrico de 4 h em torno de cada prova,
        MEDIDO, toda atividade inflou: uma ilha de prova puxava oito horas de
        trabalho vizinho que era de outro assunto, e uma atividade parada
        passou de 2.321 para 10.357 turnos.

        O que é legítimo é o MEIO: entre duas provas próximas estão os turnos
        do orquestrador, que rodam da raiz do projeto e por isso não deixam
        prova própria — 928 deles numa atividade medida, mais de um terço.

        Fora das pontas, só uma margem curta, para a cauda de turnos que fecha
        o último passo.
        """
        if quando is None:
            return True          # registro sem relógio não se recusa por tempo
        if self.inicio and quando < self.inicio:
            return False
        if not self.provas:
            return False
        import bisect
        primeira, ultima = self.provas[0], self.provas[-1]
        if quando < primeira:
            return (primeira - quando).total_seconds() <= self.margem
        if quando > ultima:
            return (quando - ultima).total_seconds() <= self.margem
        i = bisect.bisect_left(self.provas, quando)
        if i < len(self.provas) and self.provas[i] == quando:
            return True
        antes, depois = self.provas[i - 1], self.provas[i]
        # Buraco maior que o silêncio não é "meio da atividade": é intervalo
        # entre duas ilhas dela, e o que aconteceu ali foi outra coisa.
        return (depois - antes).total_seconds() <= self.limite

    def extremos(self) -> tuple[datetime | None, datetime | None]:
        return (self.provas[0], self.provas[-1]) if self.provas else (None, None)


def memoria_amostrada(agents: Path, ident: str) -> dict | None:
    """O pico que o amostrador gravou, se alguém o ligou.

    `None` quer dizer NÃO MEDIDO, e o painel precisa mostrar isso como lacuna.
    Zero diria "mediu e não achou nada", que é outra afirmação.
    """
    if not ident:
        return None
    alvo = agents / f".memoria-{ident}.json"
    try:
        d = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {k: d.get(k) for k in
            ("soma_rss_gb", "maior_gb", "maior_processo", "amostras",
             "inicio", "fim")}


def coletar_atividade(raiz: Path, agents: Path, caminho: Path,
                      precos: dict, teto_min: int, reentrada_min: int,
                      corpus: "Corpus | None" = None,
                      assinaturas_usd_mes: float | None = None) -> dict:
    corpus = corpus or Corpus()
    dados = ler_atividade(caminho)
    campos = dados["campos"]
    ident = campos.get("id") or caminho.stem
    branch = campos.get("branch", "")
    worktree = campos.get("worktree", "")
    # Uma worktree que é a própria raiz não distingue nada: usá-la como prova
    # faria toda sessão do projeto contar como desta atividade.
    if worktree and Path(worktree).resolve() == raiz.resolve():
        worktree = ""
    # A quarta posição é o conjunto de sessões que a atividade declara. Quando
    # ela existe, manda: registro ganha de inferência.
    declaradas = {s for s in str(campos.get("sessoes") or "").split() if s}
    vinculo = (branch, worktree, ident, declaradas)
    nascimento, encerrada = janela_da_atividade(campos)
    sessoes_usadas = 0

    # O `concluir` NÃO fecha a conta. Numa atividade medida ele rodou às 17h38,
    # o merge saiu às 18h02 e o conserto do que escapou entrou às 23h21 — tudo
    # na mesma worktree, tudo custo desta atividade. Cortar no `concluir`
    # jogava fora oito interações humanas, e subestimar a hora humana INFLA o
    # ganho da ferramenta: é o erro que não se pode cometer.
    #
    # A ponta inicial, ao contrário, não estica para trás: antes do `iniciar`
    # a atividade não existia.
    provas_de_sessao = _provas(raiz, vinculo, nascimento, corpus)
    provas = list(provas_de_sessao)
    if encerrada and encerrada not in provas:
        provas = sorted(provas + [encerrada])
    janela = Vizinhanca(provas, nascimento)

    # ZERO SILENCIOSO, e o falso que quase entrou no lugar dele.
    #
    # Medido: uma atividade sem `branch` e sem `worktree` no front-matter faz
    # `prova_de_vinculo` devolver False para todo registro, toda sessão é
    # descartada por `tocou`, e o registro sai com 0 turnos e US$ 0,00 — com
    # US$ 36,00 de trabalho da mesma pessoa no disco, no mesmo dia. O painel
    # mostrava como se nada tivesse acontecido.
    #
    # O falso que quase virou o detector: `janela vazia`. Não serve. Com
    # `concluido_em` a janela sai PREENCHIDA — `09:05 -> 09:05`, medido —
    # porque o `concluir` entra como prova sintética. O detector ingênuo daria
    # justamente a atividade CONCLUÍDA por boa. Só prova de SESSÃO atribui.
    #
    # E a causa é nomeada, porque o conserto é diferente em cada caso: uma se
    # conserta no front-matter, a outra não se conserta — nada rodou, ou os
    # transcritos foram apagados.
    if not branch and not worktree:
        atribuicao = "sem-prova"
        motivo = ("sem `branch` nem `worktree` no front-matter — nada liga "
                  "esta atividade a uma sessão")
    elif not provas_de_sessao:
        onde = " nem ".join(p for p in (
            f"a branch `{branch}`" if branch else "",
            f"a worktree `{worktree}`" if worktree else "") if p)
        atribuicao = "sem-prova"
        motivo = f"nenhuma sessão tocou {onde}"
    else:
        atribuicao, motivo = "ok", ""

    uso_total = {k: 0.0 for k in precos}
    modelos: dict[str, dict] = {}
    turnos = 0
    momentos: list[datetime] = []
    humanas: list[tuple[datetime, str]] = []
    respostas: list[datetime] = []
    perguntas = 0
    por_step: dict[int, dict] = {}
    agentes: list[dict] = []

    for pasta in pastas_de_sessao(raiz):
        for sessao in sorted(pasta.glob("*.jsonl")):
            principal = ler_transcrito(sessao, janela, vinculo, corpus)
            if not principal["tocou"]:
                continue
            if principal["turnos"] == 0 and not principal["humanas"]:
                continue
            sessoes_usadas += 1
            uso_total = somar(uso_total, principal["uso"])
            modelos = _juntar_modelos(modelos, principal["por_modelo"])
            turnos += principal["turnos"]
            momentos += principal["momentos"]
            humanas += principal["humanas"]
            respostas += principal["respostas"]
            perguntas += principal["perguntas_portao"]

            # Subagentes: um arquivo cada, sem `gitBranch` próprio. Eles herdam
            # a atividade da sessão que os disparou — por isso só entram quando
            # a sessão-mãe tocou esta branch.
            subs = sessao.parent / sessao.stem / "subagents"
            if not subs.is_dir():
                continue
            for arq in sorted(subs.glob("*.jsonl")):
                # Subagente não carrega branch nem janela própria: ele herda a
                # sessão que o disparou, e a janela recorta o resto.
                sub = ler_transcrito(arq, janela, None, corpus)
                if sub["turnos"] == 0:
                    continue
                prompt = primeiro_prompt(arq, corpus)
                step, papel = papel_do_agente(prompt)
                uso_total = somar(uso_total, sub["uso"])
                modelos = _juntar_modelos(modelos, sub["por_modelo"])
                turnos += sub["turnos"]
                momentos += sub["momentos"]
                # Quanto tempo de RELÓGIO a frente ocupou a máquina. O custo
                # em token diz o que ela gastou de modelo; isto diz o que ela
                # segurou de máquina — e é o que decide se três levas cabem num
                # notebook, que é a pergunta que o `DESIGN-maquina-fraca.md`
                # abriu e ninguém conseguia responder.
                #
                # Sai do primeiro e do último registro do transcrito: é tempo
                # DECORRIDO, não tempo de CPU. Uma frente parada esperando
                # `npm install` conta igual a uma calculando — e para "cabe na
                # máquina?" é o decorrido que importa.
                dur = (max(sub["momentos"]) - min(sub["momentos"])).total_seconds() \
                    if sub["momentos"] else 0.0
                agentes.append({
                    "id": arq.stem.replace("agent-", "")[:8],
                    "step": step,
                    "papel": papel,
                    "turnos": sub["turnos"],
                    "duracao_s": round(dur, 1),
                    "tokens": {k: int(v) for k, v in sub["uso"].items()},
                    "custo_usd": custo(sub["uso"], precos),
                    "prompt": prompt[:120].replace("\n", " "),
                })
                if step is not None:
                    alvo = por_step.setdefault(
                        step, {"agentes": 0, "turnos": 0, "duracao_s": 0.0,
                               "janela_s": 0.0,
                               "uso": {k: 0.0 for k in precos},
                               "_momentos": []})
                    alvo["agentes"] += 1
                    alvo["turnos"] += sub["turnos"]
                    alvo["duracao_s"] = round(alvo["duracao_s"] + dur, 1)
                    alvo["_momentos"] += sub["momentos"]
                    alvo["uso"] = somar(alvo["uso"], sub["uso"])

    # Prazo é até a ENTREGA, e a cauda é separada. Somar as duas numa métrica
    # só deu 40 h onde a entrega saiu em 26 — porque o conserto do que escapou
    # entrou horas depois e o número não distinguia "demorou a entregar" de
    # "voltou a mexer". Quem lê um painel de prazo quer a primeira.
    #
    # E o prazo diz se FECHOU. Sem `concluido_em` a entrega vira o último
    # registro do transcrito — o prazo passa a ser "até agora", e a cauda sai
    # zero POR DEFINIÇÃO, não por medição. Medido em 03/09: três frentes em
    # paralelo, todas `em_andamento` no step 3, e as três telas prometiam
    # "do primeiro registro à ENTREGA" com "cauda: 0.0 h" logo abaixo. Nenhuma
    # tinha entregue. Quem lesse via um prazo fechado e um "não houve
    # retrabalho", e os dois eram falsos.
    prazo = cauda = 0.0
    prazo_aberto = not bool(encerrada)
    if momentos:
        abertura, fechamento = min(momentos), max(momentos)
        fechou = bool(encerrada and encerrada >= abertura)
        prazo_aberto = not fechou
        entrega = encerrada if fechou else fechamento
        prazo = round((entrega - abertura).total_seconds() / 3600, 2)
        if fechamento > entrega:
            cauda = round((fechamento - entrega).total_seconds() / 3600, 2)

    humano = tempo_humano(humanas, respostas, teto_min, reentrada_min)
    humano["perguntas_portao"] = perguntas

    def inteiro(chave: str):
        v = (campos.get(chave) or "").strip()
        return int(v) if v.isdigit() else None

    pf = inteiro("pf")
    pf_aferido = inteiro("pf_aferido")
    registro = {
        "id": ident,
        # Quando ESTA atividade foi coletada. O `projeto.json` tem o dele, mas
        # quem lê um registro solto — o orçamento do `avancar`, por exemplo —
        # precisa saber de quando é o número sem abrir outro arquivo.
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "atribuicao": atribuicao,
        "motivo_atribuicao": motivo,
        "titulo": campos.get("titulo", ""),
        "trilha": campos.get("trilha", ""),
        # Sem `--risco` no `iniciar`, a atividade conta como `padrao` no fluxo;
        # aqui fica vazio, para a métrica não afirmar o que ninguém declarou.
        "risco": (campos.get("risco") or "").strip() or None,
        "step": campos.get("step", ""),
        "status": campos.get("status", ""),
        "branch": branch,
        "criado_em": campos.get("criado_em", ""),
        "concluido_em": campos.get("concluido_em", ""),
        # O caminho que a atividade fez (voltas, devoluções, portões, tempo
        # por step) e, se ela é conserto de bug que escapou, de qual entrega.
        "percurso": dados["percurso"],
        "corrige": (campos.get("corrige") or "").strip() or None,
        "pf": pf,
        "pf_aferido": pf_aferido,
        "pf_inventario": (campos.get("pf_inventario") or "").strip() or None,
        "divergencia_pf": None,
        "prazo_h": prazo,
        "prazo_aberto": prazo_aberto,
        "cauda_h": cauda,
        # A assinatura é custo de TEMPO, não de consumo: ela é cobrada por mês
        # corrido, aconteça o que acontecer dentro dele. Por isso o rateio é
        # pelo prazo, e não pela fatia de token — que só fecharia no fim do mês
        # e faria o número de uma atividade depender das outras.
        "assinatura_mensal_usd": assinaturas_usd_mes,
        "assinatura_usd": (round(assinaturas_usd_mes / HORAS_POR_MES * prazo, 2)
                           if assinaturas_usd_mes else None),
        "humano": humano,
        "tokens": {k: int(v) for k, v in uso_total.items()},
        "custo_usd": custo(uso_total, precos),
        # O gasto pela tabela DE CADA MODELO, ao lado do total. Quando os dois
        # divergem, é porque a atividade rodou em mais de um modelo — e é esse
        # número, e não o total, que responde se a cascata compensou.
        "por_modelo": {
            m: {"turnos": v["turnos"],
                "tokens": {k: int(x) for k, x in v["uso"].items()},
                "custo_usd": custo_do_modelo(v["uso"], m)}
            for m, v in sorted(modelos.items(), key=lambda kv: -kv[1]["turnos"])
        } or None,
        "custo_por_modelo_usd": round(
            sum(custo_do_modelo(v["uso"], m) for m, v in modelos.items()), 2) or None,
        "ttl_de_cache": TTL_DE_CACHE,
        "turnos": turnos,
        "agentes": len(agentes),
        "sessoes": sessoes_usadas,
        "janela": [j.isoformat() if j else None for j in janela.extremos()],
        "achados": achados_da_atividade(
            raiz, dados.get("caminhos_de_artefato", [])),
        # A memória não sai do transcrito — ele guarda token, turno e horário,
        # nunca RSS. Pico só existe enquanto o processo existe, então quem mede
        # é o amostrador do `process_guard.py medir`, durante a execução.
        # Ausente, o campo fica `None` e o painel diz NÃO MEDIDO: é diferente de
        # medido e baixo, e confundir os dois é o que faz alguém concluir que a
        # máquina deu conta quando ninguém olhou.
        "memoria": memoria_amostrada(agents, campos.get("id", "")),
        "conferencias": dados["conferencias"],
        "por_ferramenta": dados["por_ferramenta"],
        "artefatos": dados["artefatos"],
        "entrega": entrega_da_branch(raiz, branch,
                                    desde=campos.get("criado_em", "")),
        # `duracao_s` SOMA as frentes; `janela_s` mede do primeiro ao último
        # registro do step. Os dois existem porque a diferença entre eles é o
        # paralelismo: seis frentes de 10 min em paralelo somam 60 e ocupam a
        # máquina por 10. Publicar só a soma faria o step parecer seis vezes
        # mais longo do que foi; só a janela esconderia o que custou.
        "steps": [
            {"step": s, "agentes": v["agentes"], "turnos": v["turnos"],
             "duracao_s": v.get("duracao_s", 0.0),
             "janela_s": round(
                 (max(v["_momentos"]) - min(v["_momentos"])).total_seconds(), 1)
                 if v.get("_momentos") else 0.0,
             "tokens": {k: int(x) for k, x in v["uso"].items()},
             "custo_usd": custo(v["uso"], precos)}
            for s, v in sorted(por_step.items())
        ],
        "detalhe_agentes": sorted(agentes, key=lambda a: -a["custo_usd"]),
    }
    # Dois PF, e NENHUM eleito o verdadeiro.
    #
    # O declarado sai do card, antes de existir código; o aferido sai do
    # inventário do step 9, depois da entrega. Quando divergem, o que divergiu
    # foi o ESCOPO — e nem o transcrito nem o Git dizem qual dos dois estava
    # certo. Então a ferramenta não desempata: acusa, nomeia o sentido, aponta
    # o inventário e deixa a soma visível. Mesmo padrão do `_sobreposicoes`.
    if pf and pf_aferido:
        delta = pf_aferido - pf
        registro["divergencia_pf"] = {
            "absoluta": delta,
            "percentual": round(delta * 100 / pf, 1),
            "sentido": ("iguais" if delta == 0 else
                        "declarado menor" if delta > 0 else "declarado maior"),
        }
    # h/PF sai para os dois, com sufixo, porque citar um h/PF sem dizer de qual
    # PF ele saiu é o mesmo que citar o número sozinho.
    for sufixo, base in (("", pf), ("_aferido", pf_aferido)):
        if base and humano["total_h"]:
            registro[f"h_por_pf_humano{sufixo}"] = round(humano["total_h"] / base, 4)
            registro[f"h_por_pf_prazo{sufixo}"] = (round(prazo / base, 4)
                                                   if prazo else None)
    return registro


# ---------------------------------------------------------------- os achados
# A apresentação defende custo e prazo, e nenhum dos dois responde a quem acha
# que pensar menos entrega mais rápido: o custo de um erro de análise NÃO
# aparece na tarefa em que ele foi cometido. Aparece semanas depois, num card
# de bug que ninguém liga à especificação que o causou.
#
# O fluxo apanha esses erros e os corrige. Ele só não contava.
#
# O QUE ESTA DIMENSÃO NÃO FAZ, e é o mais importante dela: não estima
# retrabalho evitado. "Cada defeito custa 8 h, foram 13, economizamos 104 h" é
# um número que NÃO EXISTE — ninguém mediu aquelas 8 h, e parte dos treze seria
# apanhada por uma pessoa de qualquer forma. Publicar um multiplicador
# inventado ao lado de números medidos contamina os dois, e é o mesmo erro que
# este coletor já recusa em PF, em preço de assinatura e em atividade que
# divide branch.


def _outcome():
    """Importa o classificador do `outcome.py` em vez de escrever outro.

    Duas leituras da mesma tabela divergindo seria pior que não ter a métrica:
    a célula é escrita por gente, e "corrigido", "corrigida" e "corrigido na
    volta 2" são a mesma coisa — regra que o `outcome.py` já resolve.
    """
    caminho = Path(__file__).resolve().parents[1] / "outcome"
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))
    import outcome
    return outcome


def achados_de_um_arquivo(caminho: Path) -> dict | None:
    O = _outcome()
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    severidade: dict[str, int] = {}
    destino: dict[str, int] = {}
    total = volta_2 = 0
    for _, cabecalho, corpo in O.tabelas(linhas):
        i_sev = O.indice_da_coluna(cabecalho, "severidade")
        i_dest = O.indice_da_coluna(cabecalho, "destino")
        if i_sev is None or i_dest is None:
            continue
        # A volta 2 tem tabela própria, e o cabeçalho dela diz isso — "O que a
        # volta 2 achou". É a única marca ESTRUTURAL que separa as duas voltas.
        segunda = any("volta 2" in O.normalizar(c) for c in cabecalho)
        for _, celulas in corpo:
            if len(celulas) <= max(i_sev, i_dest):
                continue
            if not O.RE_IDENT.match(celulas[0]):
                continue
            total += 1
            volta_2 += 1 if segunda else 0
            sevs, _, _ = O.classificar(celulas[i_sev], O.SEVERIDADES)
            for nome in sevs or ["nao-declarada"]:
                severidade[nome] = severidade.get(nome, 0) + 1
            dests, _, _ = O.classificar(celulas[i_dest], O.DESTINOS)
            for nome in dests or ["nao-declarado"]:
                destino[nome] = destino.get(nome, 0) + 1
    if not total:
        return None
    return {"total": total, "volta_2": volta_2,
            "severidade": severidade, "destino": destino}


def achados_da_atividade(raiz: Path, artefatos: list[str]) -> dict | None:
    """Soma os achados dos relatórios que a atividade registrou como artefato.

    Sem artefato de relatório a dimensão fica AUSENTE, e não zerada: `0
    achados` se leria como "revisamos e não achamos nada", que é o contrário de
    "não há relatório para ler".
    """
    juntos: dict = {"total": 0, "volta_2": 0, "severidade": {}, "destino": {},
                    "arquivos": []}
    for bruto in artefatos:
        for pedaco in re.split(r"[,\s]+", bruto or ""):
            pedaco = pedaco.strip("`(),")
            if not pedaco.endswith(".md"):
                continue
            caminho = Path(pedaco) if Path(pedaco).is_absolute() else raiz / pedaco
            achado = achados_de_um_arquivo(caminho)
            if not achado:
                continue
            juntos["total"] += achado["total"]
            juntos["volta_2"] += achado["volta_2"]
            for eixo in ("severidade", "destino"):
                for k, v in achado[eixo].items():
                    juntos[eixo][k] = juntos[eixo].get(k, 0) + v
            juntos["arquivos"].append(pedaco)
    return juntos if juntos["total"] else None


def agregar_percurso(todas: list[dict]) -> dict:
    """Voltas, portões e bugs que escaparam, somados sobre TODAS as atividades.

    Não depende de atribuição: sai do arquivo da atividade, não do
    transcrito — a mesma regra das conferências.

    **Bug que escapou** é atividade aberta com `iniciar --corrige <origem>`. É
    contado na ORIGEM, e por trilha da origem: a pergunta que o número
    responde é "a trilha curta cobra o preço depois?", e ela só se responde
    olhando de onde o defeito saiu, não onde foi consertado.

    O que NÃO prova: bug consertado sem `--corrige` não entra — a taxa é um
    piso, não a taxa. E entrega sem bug não é entrega sem defeito; pode ser
    entrega que ninguém usou ainda.
    """
    com = [a for a in todas if a.get("percurso")]
    voltas: dict[str, int] = {}
    portoes: dict[str, dict[str, int]] = {}
    motivos = {"escopo": 0, "defeito": 0}
    for a in com:
        p = a["percurso"]
        for par, n in p.get("voltas", {}).items():
            voltas[par] = voltas.get(par, 0) + n
        for step, v in p.get("portoes", {}).items():
            alvo = portoes.setdefault(step, {"aprovado": 0, "devolvido": 0})
            alvo["aprovado"] += v.get("aprovado", 0)
            alvo["devolvido"] += v.get("devolvido", 0)
        for d in p.get("devolucoes", []):
            motivos[d.get("motivo", "defeito")] = \
                motivos.get(d.get("motivo", "defeito"), 0) + 1
    for v in portoes.values():
        vistos = v["aprovado"] + v["devolvido"]
        v["taxa_de_devolucao"] = round(v["devolvido"] / vistos, 3) if vistos else None

    por_id = {a["id"]: a for a in todas}
    escapes: dict[str, list[str]] = {}
    fora: list[str] = []
    for a in todas:
        origem = a.get("corrige")
        if not origem:
            continue
        if origem in por_id:
            escapes.setdefault(origem, []).append(a["id"])
        else:
            fora.append(a["id"])
    def agrupar(chave) -> dict[str, dict]:
        grupos: dict[str, dict] = {}
        for a in todas:
            if a.get("status") != "concluido":
                continue
            g = grupos.setdefault(chave(a), {"concluidas": 0,
                                             "com_bug_depois": 0, "bugs": 0})
            g["concluidas"] += 1
            if a["id"] in escapes:
                g["com_bug_depois"] += 1
                g["bugs"] += len(escapes[a["id"]])
        for g in grupos.values():
            g["taxa_com_bug"] = (round(g["com_bug_depois"] / g["concluidas"], 3)
                                 if g["concluidas"] else None)
        return dict(sorted(grupos.items()))

    por_trilha = agrupar(lambda a: a.get("trilha") or "?")
    # O risco é a pergunta do item 5: o `alto` escapa menos que o `padrao`?
    # `nao-declarado` é tudo que abriu antes da 2.59.0, ou sem `--risco`.
    por_risco = agrupar(lambda a: a.get("risco") or "nao-declarado")

    return {
        "leia": "voltas são devoluções por defeito entre steps de IA (9→8, "
                "4→3); devoluções saem de portão humano, com o motivo lido da "
                "nota. Bugs contam só o que foi aberto com `--corrige`: é um "
                "piso.",
        "atividades_medidas": len(com),
        "sem_percurso": sorted(a["id"] for a in todas if not a.get("percurso")),
        "voltas": dict(sorted(voltas.items(), key=lambda kv: -kv[1])),
        "atividades_com_volta": sum(1 for a in com
                                    if a["percurso"].get("voltas_total")),
        "portoes": dict(sorted(portoes.items(), key=lambda kv: int(kv[0]))),
        "devolucoes_por_motivo": motivos,
        "reaberturas": sum(a["percurso"].get("reaberturas", 0) for a in com),
        "bugs_que_escaparam": escapes,
        "bugs_com_origem_fora": sorted(fora),
        "por_trilha": por_trilha,
        "por_risco": por_risco,
    }


def _sobreposicoes(todas: list[dict]) -> list[dict]:
    """Pares de atividades cujas janelas se cruzam — logo, dividem custo.

    **A branch não é o eixo, e exigi-la deixava tudo passar.** Quem decide se um
    registro conta para uma atividade é a `Vizinhanca`, que olha só o RELÓGIO:
    branch nenhuma entra nessa decisão. Exigir `a.branch == b.branch` aqui
    procurava o defeito num eixo em que ele não acontece — e atividade sem
    branch no front-matter nunca era sequer comparada.

    Medido em 12/09/2026, no `acme-backoffice`: `sobreposicoes` saía
    **vazio** enquanto o custo publicado passava em 3,3x o teto físico do
    próprio corpus. Dos 107.352 registros reivindicados, **72.542 (68%) eram
    reivindicados por mais de uma atividade** — até seis delas sobre o mesmo
    registro —, e a soma das reivindicações dava **1,88x** a união.

    Os pares campeões não dividiam branch: `1091` com `cam020` (22.723
    registros) e com `cam037` (21.191). Um detector com filtro de branch não
    tinha como vê-los.
    """
    achados = []
    for i, a in enumerate(todas):
        for b in todas[i + 1:]:
            ja, jb = a.get("janela") or [], b.get("janela") or []
            if len(ja) != 2 or len(jb) != 2 or not all(ja) or not all(jb):
                continue
            if ja[0] <= jb[1] and jb[0] <= ja[1]:
                menor = min(a["custo_usd"], b["custo_usd"])
                achados.append({
                    "atividades": [a["id"], b["id"]],
                    "branch": a.get("branch") or b.get("branch") or "",
                    "mesma_branch": bool(a.get("branch"))
                    and a.get("branch") == b.get("branch"),
                    "custo_contado_duas_vezes_usd": round(menor, 2),
                })
    return achados


def teto_do_corpus(raiz: Path, corpus: "Corpus", precos: dict) -> dict:
    """O custo de TUDO que foi lido, sem atribuir nada a ninguém.

    É um teto físico: inclui até o trabalho que não pertence a atividade
    alguma. Nenhuma soma por atividade pode passar dele — se passar, há turno
    contado mais de uma vez, e não há hipótese alternativa.

    Vale por ser **independente da atribuição**: não depende de acreditar em
    nenhuma rodada, e por isso derruba conclusão tirada de comparar duas
    rodadas entre si. Foi assim que o número de 12/09/2026 caiu — US$ 27.860 de
    teto contra US$ 90.628 publicados.
    """
    uso = {k: 0.0 for k in precos}
    registros = 0
    vistos: set = set()
    for pasta in pastas_de_sessao(raiz):
        # Os transcritos de SUBAGENTE entram, e a ausência deles era o defeito
        # que tornava esta função uma promessa falsa. Medido em 21/09/2026: o
        # teto lia 22 arquivos no `app` enquanto a coleta por atividade
        # lia 792, e o corpus invisível era **metade do custo** — 49,4% ali,
        # 47,5% no `backoffice`.
        #
        # A consequência é pior que um número baixo. O docblock acima promete
        # que nenhuma soma por atividade pode passar do teto e que, se passar,
        # "não há hipótese alternativa". **Havia**, e era esta: a atividade
        # somava um corpus que o teto não lia. O alarme de sobre-atribuição
        # acusava contagem dupla onde havia só assimetria de leitura.
        for arquivo in sorted(list(pasta.glob("*.jsonl"))
                              + list(pasta.glob("*/subagents/*.jsonl"))):
            vistos.add(arquivo.resolve())
            for o in corpus.registros(arquivo):
                u = o.get("uso")
                if not isinstance(u, dict) or o.get("repetido"):
                    continue      # o repetido já teve o `uso` zerado; contá-lo
                registros += 1    # aqui inflaria o número que o teto publica
                for k in uso:
                    uso[k] += _num(u.get(k))
    # SEGUNDA VARREDURA, e ela existe porque a primeira já foi cega uma vez.
    # `rglob` desce a árvore inteira sem saber o que espera achar; a varredura
    # de cima sabe, e é justamente o que a fazia perder `subagents/`.
    #
    # Trocar a CHAVE de agregação não teria pego aquilo: `message.id` e
    # `requestId` concordaram em 0,00% enquanto as duas somavam 48% a menos,
    # porque o defeito é anterior ao ponto em que elas divergem. **Duas medidas
    # que compartilham um estágio não conferem aquele estágio.** A leitura é da
    # sessão `acme-backoffice`, 21/09/2026.
    raizes = pastas_de_sessao(raiz)
    no_disco = sum(1 for p_ in raizes for _ in p_.rglob("*.jsonl"))
    cego = {"lidos": len(vistos), "no_disco": no_disco} if no_disco != len(vistos) else None
    # **As duas varreduras compartilham a RAIZ**, e isso é o limite delas: as
    # estratégias são independentes, o ponto de partida não. Raiz incompleta —
    # sessão gravada fora da árvore esperada, projeto que ninguém enumerou — e
    # as duas concordam com a luz apagada.
    #
    # É a terceira vez que a mesma regra aparece nesta série, e cada conserto
    # só mudou o estágio compartilhado de lugar: primeiro duas máquinas com a
    # mesma ferramenta, depois duas chaves com o mesmo coletor, agora dois
    # varredores com a mesma raiz.
    #
    # Por isso as raízes saem SEMPRE, e não só quando a luz acende: "793 e 793"
    # sem dizer sob qual diretório convida a mesma leitura que um fator de
    # inflação sem o corpus declarado. Número sem o denominador à vista.
    return {"custo_usd": round(custo(uso, precos), 2),
            "registros_com_uso": registros,
            "turnos_repetidos_descartados": corpus.turnos_repetidos,
            "arquivos_lidos": len(vistos),
            "arquivos_no_disco": no_disco,
            "raizes_varridas": sorted(str(p_) for p_ in raizes),
            "corpus_nao_lido": cego,
            "tokens": uso}


def conferir_invariante(projeto: dict, teto: dict) -> dict | None:
    """A soma atribuída passou do teto? Então há contagem repetida.

    Não corrige o número — **declara**. Inventar um rateio para os registros
    disputados seria escolher um dono por conveniência, e o pacote não sabe de
    quem é o turno do orquestrador que rodou entre duas atividades. O que ele
    pode fazer, e passou a fazer, é não deixar o número sair calado.
    """
    soma, limite = projeto.get("custo_usd") or 0.0, teto.get("custo_usd") or 0.0
    if not limite or soma <= limite:
        return None
    return {
        "soma_atribuida_usd": round(soma, 2),
        "teto_do_corpus_usd": round(limite, 2),
        "vezes": round(soma / limite, 2),
        "o_que_significa": (
            "a soma por atividade passou o custo de TUDO que foi lido; "
            "há turno contado mais de uma vez. O total do projeto está "
            "INFLADO e não deve ser citado."),
    }


def bloco_apf(atribuidas: list[dict]) -> dict | None:
    """A régua APF do PROJETO, e o subconjunto em que ela é comparável.

    APF é estimativa de mercado em **hora de equipe**: PF × horas por PF. O
    que este coletor mede é outra coisa — hora humana (modelada, com teto),
    prazo de relógio e dólar de tabela. Nenhum dos três **é** a grandeza da
    APF; o mais próximo é a hora humana, e é contra ela que a régua encosta.

    O que este bloco existe para impedir: somar o PF de TODAS as atividades e
    confrontar com a hora humana das ATRIBUÍDAS. Os dois lados viriam de
    conjuntos diferentes, e o erro cairia sempre para o mesmo lado — mais PF
    estimado sobre menos hora medida INFLA o ganho da ferramenta, que é a
    única direção que este coletor declara não poder errar.

    Então a comparação usa só as atividades que têm **as duas coisas**:
    prova de atribuição e PF. As que ficaram de fora vão nomeadas junto, pela
    mesma razão de sempre — um total que não diz o que não cobre se lê como
    se cobrisse tudo.
    """
    base = [a for a in atribuidas if (a.get("pf_aferido") or a.get("pf"))]
    if not base:
        return None
    origens = {"aferido" if a.get("pf_aferido") else "declarado" for a in base}
    pf = sum(int(a.get("pf_aferido") or a.get("pf")) for a in base)
    humano_h = round(sum(float(a["humano"]["total_h"]) for a in base), 2)
    prazo_h = round(sum(float(a.get("prazo_h") or 0) for a in base), 2)

    def fator(total: float) -> dict:
        return {str(prod): round(pf * prod / total, 1) if total else None
                for prod in PRODUTIVIDADES_APF}

    return {
        "pf": pf,
        "origem": origens.pop() if len(origens) == 1 else "misto",
        "atividades": sorted(a["id"] for a in base),
        "fora": sorted(a["id"] for a in atribuidas
                       if not (a.get("pf_aferido") or a.get("pf"))),
        "humano_h": humano_h,
        "prazo_somado_h": prazo_h,
        "custo_usd": round(sum(float(a.get("custo_usd") or 0) for a in base), 2),
        "em_andamento": sorted(a["id"] for a in base if prazo_esta_aberto(a)),
        "horas": {str(prod): pf * prod for prod in PRODUTIVIDADES_APF},
        # DOIS fatores, e nunca um. A estimativa APF dividida pela hora humana
        # dá um número grande — na primeira montagem, 106x —, porque a hora
        # humana conta só o tempo em que a pessoa está na frente da tela. Ela é
        # verdadeira e é a metade da história: enquanto ela não estava lá, a
        # máquina estava, por 57 h de relógio e por dinheiro.
        #
        # Um fator só, publicado sem o outro, é o tipo de número que se repete
        # numa reunião e cai na primeira pergunta. Os dois juntos são
        # defensáveis, e a diferença entre eles É a informação.
        "fator_humano": fator(humano_h),
        "fator_prazo": fator(prazo_h),
    }


def cmd_coletar(args) -> int:
    raiz = Path(args.raiz).resolve()
    agents = resolve_agents_dir()
    if not C.obter("metricas.ligado", True, agents):
        # Desligado por declaração do projeto. Sai limpo e calado: quem
        # desligou não quer um aviso a cada `avancar`. O estado fica visível
        # no `doctor.py conferir`, que é onde se pergunta o que está ligado.
        #
        # O padrão é LIGADO porque é o que a 1.1.0 já fazia: virar para
        # `false` desligaria em silêncio, no upgrade, uma capacidade que hoje
        # funciona. Isto é decisão de produto, não regra tirada de erro
        # medido — e fica escrito como decisão para ninguém procurar a medição.
        return 0
    precos = {**PRECOS_PADRAO, **(C.obter("metricas.precos", {}, agents) or {})}
    def numero(chave: str, padrao: int) -> int:
        """Um `0` declarado vale 0.

        Era `int(valor or padrao)`, e o `or` engolia o zero: o config dizia
        `teto_leitura_min = 0`, o coletor usava 10 e o rodapé imprimia
        "teto de 10 min". Medido. Config que não faz o que diz é pior que
        config ausente, porque quem declarou acredita ter declarado.

        Quem quer o padrão remove a chave. E o `doctor.py` reprova teto <= 0,
        porque teto zerado apaga a medida de leitura e a hora humana sai
        MENOR do que é — a direção que infla o ganho da ferramenta.
        """
        valor = C.obter(f"metricas.{chave}", None, agents)
        return padrao if valor is None or valor == "" else int(valor)

    teto = numero("teto_leitura_min", TETO_LEITURA_MIN)
    reent = numero("reentrada_min", REENTRADA_MIN)

    # As assinaturas são uma LISTA de mensalidades, não um preço vezes um
    # número de contas. Medido no primeiro caso real: as duas contas em uso
    # eram de planos DIFERENTES — uma Max 20× e um assento Team. Um
    # multiplicador teria cobrado o preço da primeira duas vezes.
    #
    # Sem a chave, não há custo de assinatura no registro. Preço não se
    # adivinha, pela mesma razão que ponto de função não se mede: a ferramenta
    # lê o que foi declarado, e o que não foi declarado fica ausente em vez de
    # sair errado.
    bruto = C.obter("metricas.assinaturas_usd_mes", None, agents)
    assinaturas = None
    if isinstance(bruto, (list, tuple)) and bruto:
        try:
            assinaturas = round(sum(float(v) for v in bruto), 2)
        except (TypeError, ValueError):
            assinaturas = None

    destino = agents / "metrics"
    destino.mkdir(parents=True, exist_ok=True)

    arquivos = sorted((agents / "atividades").glob("*.md"))
    if args.atividade:
        arquivos = [a for a in arquivos if a.stem == args.atividade]
        if not arquivos:
            raise FlowStateError(f"atividade `{args.atividade}` não existe")

    # Um corpus para a RODADA, não por atividade: é o que faz a coleta
    # completa custar uma passada em vez de 2N. Ver `class Corpus`.
    corpus = Corpus()
    coletadas = []
    for arq in arquivos:
        reg = coletar_atividade(raiz, agents, arq, precos, teto, reent, corpus,
                                assinaturas_usd_mes=assinaturas)
        (destino / f"{reg['id']}.json").write_text(
            json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        coletadas.append(reg)
        if not args.silencioso:
            print(f"  {reg['id']:<26} {reg['turnos']:>6} turnos  "
                  f"US$ {reg['custo_usd']:>9,.2f}  {reg['humano']['total_h']:>6.2f} h humanas")

    # O projeto sempre é regravado inteiro, mesmo quando só uma atividade foi
    # coletada: o total tem que refletir o disco, e não a última rodada.
    todas = []
    for arq in sorted(destino.glob("*.json")):
        if arq.name == "projeto.json":
            continue
        try:
            todas.append(json.loads(arq.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    # O que sai do TRANSCRITO só entra no total se a atividade foi atribuída:
    # somar zero por ela embute um zero que não é zero. O que NÃO depende de
    # atribuição — conferências e artefatos, que saem do arquivo da atividade,
    # e a entrega, que sai do Git — continua somando por todas. Excluir isso
    # também jogaria fora dado correto por causa de um front-matter incompleto.
    atribuidas = [a for a in todas if a.get("atribuicao") != "sem-prova"]
    nao = [a for a in todas if a.get("atribuicao") == "sem-prova"]

    # `raiz` é o REPOSITÓRIO, não o diretório da chamada. Gravar o cwd fez um
    # `projeto.json` do backoffice sair com `raiz` apontando para uma worktree
    # de revisão, e quem leu entendeu que as duas rodadas tinham a mesma raiz —
    # não tinham, e a diferença de cobertura foi atribuída a não determinismo.
    # `chamado_de` fica ao lado, porque a informação é útil e o engano vinha de
    # ela ocupar o campo errado.
    principal = raiz_principal(raiz)
    pastas_vistas = pastas_de_sessao(raiz)
    projeto = {
        "projeto": C.obter("projeto.nome", principal.name, agents) or principal.name,
        "raiz": str(principal),
        "chamado_de": str(raiz.resolve()),
        "cobertura": {
            "pastas": len(pastas_vistas),
            "transcritos": sum(len(list(p_.glob("*.jsonl"))) for p_ in pastas_vistas),
            "nomes": sorted(p_.name for p_ in pastas_vistas),
        },
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parametros": {"precos": precos, "teto_leitura_min": teto,
                       "reentrada_min": reent},
        "atividades": len(todas),
        "atividades_no_total": len(atribuidas),
        "nao_atribuidas": [a["id"] for a in nao],
        "concluidas": sum(1 for a in todas if a.get("status") == "concluido"),
        # Três números do mesmo arquivo contam conjuntos DIFERENTES, e o nome
        # `atividades_no_total` se lê como "total de atividades" — não é: é
        # quantas entraram no total de CUSTO. Em 20/09/2026 uma sessão do
        # backoffice leu 46 / 49 / 51 e concluiu, com razão, que o arquivo não
        # reconcilia: `concluidas` conta sobre TODAS e `atividades_no_total`
        # sobre as atribuídas. A aritmética estava certa; o que faltava era
        # dizer o denominador de cada uma.
        "denominadores": {
            "leia": "custo, tokens, turnos, agentes e hora humana somam SÓ as "
                    "atividades com prova de atribuição. `concluidas` e `pf` "
                    "contam TODAS. Comparar os dois é comparar conjuntos "
                    "diferentes.",
            "atividades": len(todas),
            "com_prova_de_atribuicao": len(atribuidas),
            "sem_prova": len(nao),
            "concluidas_de_todas": sum(1 for a in todas
                                       if a.get("status") == "concluido"),
            "concluidas_com_prova": sum(1 for a in atribuidas
                                        if a.get("status") == "concluido"),
        },
        "tokens": {k: sum(a["tokens"].get(k, 0) for a in atribuidas) for k in precos},
        "custo_usd": round(sum(a["custo_usd"] for a in atribuidas), 2),
        "turnos": sum(a["turnos"] for a in atribuidas),
        "agentes": sum(a["agentes"] for a in atribuidas),
        "humano_h": round(sum(a["humano"]["total_h"] for a in atribuidas), 2),
        "interacoes": sum(a["humano"]["interacoes"] for a in atribuidas),
        "pf": sum(a["pf"] for a in todas if a.get("pf")) or None,
        "pf_aferido": sum(a["pf_aferido"] for a in todas
                          if a.get("pf_aferido")) or None,
        "apf": bloco_apf(atribuidas),
        "conferencias": {},
        "entrega": {"arquivos": 0, "insercoes": 0, "remocoes": 0, "commits": 0},
        "lista": sorted(todas, key=lambda a: -a["custo_usd"]),
    }
    for a in todas:
        for v, n in (a.get("conferencias") or {}).items():
            projeto["conferencias"][v] = projeto["conferencias"].get(v, 0) + n
        for k in ("arquivos", "insercoes", "remocoes", "commits"):
            projeto["entrega"][k] += (a.get("entrega") or {}).get(k, 0)

    # Duas atividades na MESMA branch com janelas que se cruzam contam o mesmo
    # trabalho duas vezes, e o total do projeto passa a somar mais do que
    # aconteceu. Medido no primeiro uso: `poc-step3` e `poc-step4` devolveram
    # números idênticos, ao centavo.
    #
    # Não dá para desempatar sozinho — o transcrito não diz de qual das duas é
    # cada turno. Então não se inventa um critério: acusa, nomeia o par, e
    # deixa a soma visível para quem lê decidir o que fazer.
    # Mesma regra do `nao_atribuidas`: o que não deu para medir é NOMEADO, e o
    # total diz que é de menos. Somar zero por elas embutiria um zero que não
    # é zero.
    # UM TOTAL NÃO PODE MISTURAR TABELAS DE PREÇO DIFERENTES, e ele misturava.
    #
    # `coletar --atividade X` recolhe só X e reagrega o projeto a partir dos
    # JSON que já estavam no disco — inclusive os gravados por versões
    # anteriores do pacote. Medido no `acme-backoffice`: o total dizia
    # US$ 10.544,99 somando um registro novo com dez feitos pela 2.13.0, que
    # cobrava pela tabela do Opus 4.1 APOSENTADO. O custo por turno saía 2,73×
    # o real — e o número foi lido como se fosse de hoje.
    #
    # `por_modelo` nasceu na 2.14.0, junto com o preço por modelo. Registro sem
    # ele foi cobrado pela tabela única antiga, e é isso que o marca.
    antigos = sorted(a["id"] for a in atribuidas if not a.get("por_modelo"))
    projeto["registros_de_versao_antiga"] = antigos
    projeto["entrega_indisponivel"] = sorted(
        a["id"] for a in todas
        if (a.get("entrega") or {}).get("metodo") == "indisponivel")
    projeto["sobreposicoes"] = _sobreposicoes(atribuidas)
    projeto["percurso"] = agregar_percurso(todas)
    # A invariante que faltava, e que teria pego o número de 12/09/2026 no dia
    # em que ele foi publicado: soma por atividade não pode passar o custo do
    # que foi lido. Ela não conserta — declara, e alto.
    projeto["teto_do_corpus"] = teto_do_corpus(raiz, corpus, precos)
    estouro = conferir_invariante(projeto, projeto["teto_do_corpus"])
    if estouro:
        projeto["sobre_atribuicao"] = estouro
        print()
        print("  !! SOBRE-ATRIBUIÇÃO: o total do projeto está INFLADO")
        print(f"     soma por atividade  US$ {estouro['soma_atribuida_usd']:,.2f}")
        print(f"     teto do corpus lido US$ {estouro['teto_do_corpus_usd']:,.2f}"
              f"   ({estouro['vezes']}x)")
        print("     Há turno contado mais de uma vez. NÃO cite o total até que")
        print("     a sobreposição esteja resolvida — veja `sobreposicoes`.")
    (destino / "projeto.json").write_text(
        json.dumps(projeto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.silencioso:
        print(f"\n  {len(todas)} atividade(s) em {destino}")
        print(f"  {corpus.arquivos_lidos} transcrito(s) lidos uma vez nesta rodada")
        # Duas rodadas com coberturas de fator 4 saíam indistinguíveis na tela.
        # Número sem alcance não é resultado: é opinião com casas decimais.
        pastas = pastas_de_sessao(raiz)
        principal = raiz_principal(raiz)
        print(f"  {len(pastas)} pasta(s) de sessão, a partir de {principal}")
        for pasta in sorted(pastas):
            quantos = len(list(pasta.glob("*.jsonl")))
            print(f"      {quantos:4} {pasta.name}")
    return 0


# ---------------------------------------------------------------------------
# relatar


def _nome_curto(cargo: str) -> str:
    prefixo = "Portão humano · "
    return ("Portão · " + cargo[len(prefixo):].lower()
            if cargo.startswith(prefixo) else cargo)


# Derivado de `STEPS`, e não copiado à mão: a cópia era a terceira lista dos
# mesmos dez nomes, e a próxima renomeação acertaria duas.
NOMES_STEP = {n: _nome_curto(d["cargo"]) for n, d in STEPS.items()}


def _barra(fracao: float, largura: int = 18) -> str:
    cheio = int(round(fracao * largura))
    return "█" * cheio + "·" * (largura - cheio)


def cmd_relatar(args) -> int:
    agents = resolve_agents_dir()
    destino = agents / "metrics"
    alvo = destino / "projeto.json"
    if not alvo.exists():
        raise FlowStateError(
            f"nada coletado ainda em {destino}.\n"
            f"Rode: metrics.py coletar --raiz {args.raiz}")
    projeto = json.loads(alvo.read_text(encoding="utf-8"))

    if not args.atividade:
        p = projeto
        print(f"\nProjeto — {p['projeto']}")
        print(f"          {p['atividades']} atividade(s), {p['concluidas']} concluída(s)"
              f"   ·   gerado em {p['gerado_em']}\n")
        print(f"  {'':26} {'turnos':>7} {'agentes':>8} {'US$':>10} {'humanas':>9} {'prazo':>8}")
        atribuidas = [a for a in p["lista"] if a.get("atribuicao") != "sem-prova"]
        pico = max((a["custo_usd"] for a in atribuidas), default=1) or 1
        for a in p["lista"]:
            if a.get("atribuicao") == "sem-prova":
                # Nenhum número nesta linha, de propósito: zero formatado se
                # lê como medição, e a diferença entre "custou zero" e "não
                # sei de quem foi" é a única coisa que esta linha existe para
                # dizer. `0.00` alinhado numa coluna de custo apaga isso.
                print(f"  {a['id'][:26]:<26} {'não atribuída':>44}")
                continue
            # `+` no prazo da atividade aberta. Sem a marca, um prazo que
            # ainda cresce alinha na mesma coluna de um que acabou, e a lista
            # convida a comparar os dois como se fossem a mesma grandeza.
            marca = "+" if prazo_esta_aberto(a) else " "
            print(f"  {a['id'][:26]:<26} {a['turnos']:>7} {a['agentes']:>8} "
                  f"{a['custo_usd']:>10,.2f} {a['humano']['total_h']:>8.2f}h "
                  f"{a['prazo_h']:>7.1f}h{marca} {_barra(a['custo_usd']/pico)}")
        rotulo = ("TOTAL" if len(atribuidas) == p["atividades"]
                  else f"TOTAL ({len(atribuidas)} de {p['atividades']})")
        print(f"\n  {rotulo:<26} {p['turnos']:>7} {p['agentes']:>8} "
              f"{p['custo_usd']:>10,.2f} {p['humano_h']:>8.2f}h")
        abertas = [a for a in atribuidas if prazo_esta_aberto(a)]
        if abertas:
            print(f"\n  + {len(abertas)} de {len(atribuidas)} em andamento: o prazo delas "
                  f"vai até agora,\n    não até a entrega, e vai crescer.")
        nao = [a for a in p["lista"] if a.get("atribuicao") == "sem-prova"]
        if nao:
            print(f"\n  [ATENÇÃO] {len(nao)} atividade(s) ficaram fora do total, por falta de")
            print("            prova de atribuição — o total acima é DE MENOS, não de zero:")
            for a in nao:
                print(f"              {a['id']:<18} {a.get('motivo_atribuicao', '')}")
        conf = p["conferencias"]
        if conf:
            print("\n  conferências: " + "  ".join(f"{v} {n}" for v, n in sorted(conf.items())))
        e = p["entrega"]
        print(f"  entrega:      {e['arquivos']} arquivos, +{e['insercoes']} −{e['remocoes']}, "
              f"{e['commits']} commits")
        antigos = p.get("registros_de_versao_antiga") or []
        if antigos:
            print(f"\n  [ATENÇÃO] {len(antigos)} registro(s) foram coletados por uma versão "
                  f"ANTERIOR do\n            pacote, que cobrava pela tabela do Opus 4.1 "
                  f"aposentado — até 2,7× o\n            preço real. O custo acima MISTURA "
                  f"as duas tabelas:")
            print("              " + ", ".join(antigos))
            print(f"            Conserto: `metrics.py coletar --raiz {args.raiz}` "
                  f"sem `--atividade`,\n            que recolhe todas com a tabela de hoje.")
        indisp = p.get("entrega_indisponivel") or []
        if indisp:
            print(f"                a entrega de {len(indisp)} atividade(s) não deu para medir, "
                  f"e o total\n                acima é DE MENOS: "
                  + ", ".join(indisp))
        sob = p.get("sobreposicoes") or []
        if sob:
            duplo = sum(s["custo_contado_duas_vezes_usd"] for s in sob)
            print(f"\n  [ATENÇÃO] {len(sob)} par(es) dividem branch e janela — o TOTAL acima")
            print(f"            soma até US$ {duplo:,.2f} duas vezes:")
            for s in sob:
                print(f"              {' + '.join(s['atividades'])}   ({s['branch']})")
        _imprimir_percurso_do_projeto(p.get("percurso"))
        print(f"\n  Drill-down:   metrics.py relatar --atividade <id>")
        print(_rodape(p))
        return 0

    arq = destino / f"{args.atividade}.json"
    if not arq.exists():
        raise FlowStateError(f"atividade `{args.atividade}` não foi coletada")
    a = json.loads(arq.read_text(encoding="utf-8"))

    print(f"\nAtividade — {a['id']} · {a['titulo']}")
    print(f"            trilha {a['trilha']} · step {a['step']} · {a['status']}"
          f" · {a['branch']}\n")
    if a.get("atribuicao") == "sem-prova":
        print("  não consegui atribuir trabalho nenhum a esta atividade.")
        print(f"  Motivo: {a.get('motivo_atribuicao', '')}")
        print()
        print("  Não mostro custo, prazo nem hora humana: os três sairiam zero, e")
        print("  zero aqui não significa que nada aconteceu — significa que não sei")
        print("  de quem foi o que aconteceu.")
        if not a.get("branch"):
            print()
            print("  Conserto: declare `branch` (e `worktree`, se houver) no front-matter")
            print(f"  de .agents/atividades/{a['id']}.md, e colete de novo.")
        # O percurso sai do arquivo da atividade, não do transcrito: falta de
        # atribuição não o apaga, e é justamente aqui que ele ainda diz algo.
        _imprimir_percurso_da_atividade(a, projeto)
        print(_rodape(json.loads((destino / "projeto.json").read_text(encoding="utf-8"))))
        return 0

    h = a["humano"]
    aberto = prazo_esta_aberto(a)
    linhas = [
        ("turnos de assistente", f"{a['turnos']:,}"),
        ("agentes", f"{a['agentes']}"),
        ("custo em tabela de API", f"US$ {a['custo_usd']:,.2f}"),
        *([("custo de assinatura, rateado pelo prazo",
            f"US$ {a['assinatura_usd']:,.2f}")] if a.get("assinatura_usd") else []),
        ("prazo, do primeiro registro até agora" if aberto else
         "prazo, do primeiro registro à entrega", f"{a['prazo_h']:.1f} h"),
        ("hora humana (leitura + reentrada)", f"{h['total_h']:.2f} h"),
    ]
    # Sem entrega não há cauda de que falar. A linha inteira sai, em vez de
    # sair zerada: `0.0 h` sob o rótulo "trabalho depois da entrega" se lê como
    # "não houve retrabalho", e a diferença entre isso e "não houve entrega" é
    # a única coisa que esta linha existe para dizer.
    if not aberto:
        linhas.append(("cauda, trabalho depois da entrega",
                       f"{a.get('cauda_h', 0):.1f} h"))
    linhas += [
        ("interações humanas", f"{h['interacoes']}"),
        ("perguntas de portão respondidas", f"{h['perguntas_portao']}"),
    ]
    pm = a.get("por_modelo") or {}
    if pm:
        linhas.append(("modelos usados", f"{len(pm)}"))
        for m, v in pm.items():
            curto = m.replace("claude-", "")
            linhas.append((f"  {curto}",
                           f"{v['turnos']:,} turnos · US$ {v['custo_usd']:,.2f}"))

    ach = a.get("achados") or {}
    if ach:
        sev, dest = ach.get("severidade", {}), ach.get("destino", {})
        linhas.append(("achados da revisão", f"{ach['total']}"))
        linhas.append(("  bloqueia · alta · baixa",
                       f"{sev.get('bloqueia', 0)} · {sev.get('alta', 0)} · "
                       f"{sev.get('baixa', 0)}"))
        linhas.append(("  corrigido · descartado · aceito · aberto",
                       f"{dest.get('corrigido', 0)} · {dest.get('descartado', 0)} · "
                       f"{dest.get('aceito', 0)} · {dest.get('aberto', 0)}"))
        if ach.get("volta_2"):
            linhas.append(("  achados da segunda volta", f"{ach['volta_2']}"))
    div = a.get("divergencia_pf") or {}
    tem_pf = bool(a.get("pf") or a.get("pf_aferido"))

    def hpf(chave: str) -> str:
        v = a.get(chave)
        return f"{v:.3f}" if v else "—"

    linhas.append(("pontos de função declarados (analista)",
                   str(a["pf"]) if a.get("pf") else "não declarado"))
    linhas.append(("pontos de função aferidos (inventário)",
                   str(a["pf_aferido"]) if a.get("pf_aferido") else "não aferido"))
    if div:
        linhas.append(("divergência de tamanho",
                       f"{div['absoluta']:+d} PF ({div['percentual']:+.1f}%)"))
    linhas.append(("h/PF humano — declarado · aferido",
                   f"{hpf('h_por_pf_humano')} · {hpf('h_por_pf_humano_aferido')}"))
    linhas.append(("h/PF de prazo — declarado · aferido",
                   f"{hpf('h_por_pf_prazo')} · {hpf('h_por_pf_prazo_aferido')}"))
    # A estimativa APF é a régua de mercado, não medida nossa: PF × horas por
    # PF. Ela só existe onde há PF DECLARADO — sem ele seria multiplicação de
    # nada, e um número inventado ao lado dos medidos contamina os dois.
    base_pf = a.get("pf_aferido") or a.get("pf")
    if base_pf:
        de_onde = "aferido" if a.get("pf_aferido") else "declarado"
        for prod in PRODUTIVIDADES_APF:
            linhas.append((f"estimativa APF, produtividade {prod} ({de_onde})",
                           f"{base_pf * prod:,} h"))
    for k, v in linhas:
        print(f"  {k:<42} {v:>14}")

    if len(pm) > 1:
        print()
        print("  Mais de um modelo nesta atividade. O custo de cada um sai da")
        print(f"  tabela DELE, e não de uma média — e o cache de escrita usa TTL")
        print(f"  de {a.get('ttl_de_cache', TTL_DE_CACHE)}, que é o do Claude Code.")

    if ach:
        print()
        print("  Os achados dizem o que a revisão APANHOU, e onde. Eles NÃO dizem")
        print("  quanto retrabalho foi evitado: ninguém mediu o custo de um defeito")
        print("  que não chegou a acontecer, e parte deles seria apanhada por uma")
        print("  pessoa de qualquer forma. Esta ferramenta não modela retrabalho.")
        if ach.get("volta_2"):
            print()
            print(f"  Dos {ach['total']}, {ach['volta_2']} vieram da SEGUNDA volta — a que")
            print("  revisa o texto que as correções escreveram. Quantos deles foram")
            print("  INTRODUZIDOS ao corrigir, e quantos a primeira volta deixou passar,")
            print("  só quem escreveu o relatório sabe separar — e por isso não está aqui.")

    if a.get("assinatura_usd"):
        print()
        print(f"  Assinatura: US$ {a['assinatura_mensal_usd']:,.2f} por mês declarados em")
        print(f"  `[metricas] assinaturas_usd_mes`, rateados por {HORAS_POR_MES} h de mês —")
        print("  ela é cobrada por tempo corrido, não por token consumido.")

    if aberto:
        print()
        print("  Prazo AINDA ABERTO: esta atividade não tem `concluido_em`, então o")
        print("  número acima vai do primeiro registro até o último que existe — não")
        print("  até uma entrega. Ele vai crescer. A cauda não aparece: sem entrega")
        print("  ela seria zero por definição, e zero aqui se leria como 'não houve")
        print("  retrabalho'.")

    if not tem_pf:
        print()
        print("  h/PF indisponível: `pf` não declarado no front-matter, e nenhum")
        print("  inventário de aferção. A ferramenta não MEDE ponto de função —")
        print("  ela lê o que foi declarado. Sem número, a linha fica vazia em")
        print("  vez de sair errada.")
    elif div and div["sentido"] != "iguais":
        print()
        print(f"  [ATENÇÃO] declarado e aferido divergem em {div['absoluta']:+d} PF "
              f"({div['percentual']:+.1f}%) —")
        print(f"            {div['sentido']} que o entregue. Os dois NÃO são")
        print("            desempatados: nem o transcrito nem o Git dizem qual estava")
        if a.get("pf_inventario"):
            print(f"            certo. Confira {a['pf_inventario']} antes de citar h/PF.")
        else:
            print("            certo, e não há inventário apontado para conferir.")

    if a["steps"] and not args.step:
        print(f"\n  {'step':<32} {'agentes':>8} {'turnos':>8} {'US$':>10}")
        pico = max((s["custo_usd"] for s in a["steps"]), default=1) or 1
        for s in a["steps"]:
            nome = NOMES_STEP.get(s["step"], "?")
            print(f"  {str(s['step']) + ' · ' + nome:<32} {s['agentes']:>8} "
                  f"{s['turnos']:>8} {s['custo_usd']:>10,.2f}  {_barra(s['custo_usd']/pico)}")
        print(f"\n  Drill-down:   metrics.py relatar --atividade {a['id']} --step <n>")

    if args.step:
        n = int(args.step)
        do_step = [g for g in a["detalhe_agentes"] if g["step"] == n]
        print(f"\n  Step {n} · {NOMES_STEP.get(n, '?')} — {len(do_step)} agente(s)\n")
        print(f"  {'agente':<10} {'papel':<10} {'turnos':>7} {'US$':>9}  prompt")
        for g in do_step:
            print(f"  {g['id']:<10} {g['papel']:<10} {g['turnos']:>7} "
                  f"{g['custo_usd']:>9,.2f}  {g['prompt'][:58]}")

    if a["conferencias"] and not args.step:
        print("\n  conferências: " + "  ".join(f"{v} {n}" for v, n in sorted(a["conferencias"].items())))
        piores = [(f, d) for f, d in a["por_ferramenta"].items()
                  if d.get("falhou") or d.get("nao-coberta") or d.get("exigida")]
        for f, d in sorted(piores):
            print(f"      {f:<28} " + "  ".join(f"{v}={n}" for v, n in sorted(d.items())))

    if not args.step:
        _imprimir_percurso_da_atividade(a, projeto)

    print(_rodape(json.loads((destino / "projeto.json").read_text(encoding="utf-8"))))
    return 0


def _fmt_duracao(segundos: float) -> str:
    m = int(round(segundos / 60))
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _imprimir_percurso_do_projeto(pp: dict | None) -> None:
    """O bloco de percurso do `relatar` sem `--atividade`.

    Some inteiro quando não há o que dizer — um `projeto.json` coletado
    antes da 2.57.0 não tem a chave, e zero voltas impresso ali se leria como
    "nenhuma volta", quando é "ninguém contou".
    """
    if not pp or not pp.get("atividades_medidas"):
        return
    print(f"\n  Percurso ({pp['atividades_medidas']} atividade(s) com histórico lido)")
    if pp["voltas"]:
        print(f"    voltas de correção:  "
              + ", ".join(f"{par} ×{n}" for par, n in pp["voltas"].items())
              + f"   — em {pp['atividades_com_volta']} atividade(s)")
    else:
        print("    voltas de correção:  nenhuma")
    for step, v in pp["portoes"].items():
        taxa = v.get("taxa_de_devolucao")
        print(f"    portão {step:>2}: {v['aprovado']} aprovação(ões), "
              f"{v['devolvido']} devolução(ões)"
              + (f"  ({taxa:.0%} devolvido)" if taxa is not None else ""))
    mot = pp["devolucoes_por_motivo"]
    if mot.get("escopo") or mot.get("defeito"):
        print(f"    devoluções por motivo: {mot.get('defeito', 0)} defeito, "
              f"{mot.get('escopo', 0)} escopo")
    if pp.get("reaberturas"):
        print(f"    reaberturas: {pp['reaberturas']}")
    esc = pp.get("bugs_que_escaparam") or {}
    if esc or pp.get("bugs_com_origem_fora"):
        total = sum(len(v) for v in esc.values()) + len(pp.get("bugs_com_origem_fora") or [])
        print(f"    bugs que escaparam (abertos com --corrige): {total}")
        for t, v in pp["por_trilha"].items():
            if v["concluidas"]:
                print(f"      trilha {t:<10} {v['com_bug_depois']} de {v['concluidas']} "
                      f"entrega(s) voltaram com bug")
        for r, v in (pp.get("por_risco") or {}).items():
            if v["concluidas"]:
                print(f"      risco  {r:<10} {v['com_bug_depois']} de {v['concluidas']} "
                      f"entrega(s) voltaram com bug")
        if pp.get("bugs_com_origem_fora"):
            print("      com origem que não está neste projeto: "
                  + ", ".join(pp["bugs_com_origem_fora"]))
        print("      É um PISO: bug consertado sem `--corrige` não entra na conta.")
    if pp.get("sem_percurso"):
        print(f"    sem histórico lido (registro antigo — colete de novo): "
              + ", ".join(pp["sem_percurso"]))


def _imprimir_percurso_da_atividade(a: dict, projeto: dict) -> None:
    p = a.get("percurso")
    if not p:
        print("\n  Percurso: este registro é anterior à 2.57.0 — colete de novo.")
        return
    print("\n  Percurso")
    if p["voltas"]:
        print("    voltas de correção:  "
              + ", ".join(f"{par} ×{n}" for par, n in p["voltas"].items()))
    for d in p["devolucoes"]:
        print(f"    portão {d['de']} devolveu ao step {d['para']} (por {d['motivo']})")
    for step, v in p["portoes"].items():
        print(f"    portão {step:>2}: {v['aprovado']} aprovação(ões), "
              f"{v['devolvido']} devolução(ões)")
    if p.get("reaberturas"):
        print(f"    reaberta {p['reaberturas']} vez(es)")
    t = p.get("tempo_s") or {}
    if t.get("ia") or t.get("humano"):
        print(f"    tempo de relógio nos steps: IA {_fmt_duracao(t.get('ia', 0))}, "
              f"portões {_fmt_duracao(t.get('humano', 0))}")
    if a.get("corrige"):
        print(f"    corrige {a['corrige']}: defeito que escapou da entrega dela")
    filhos = ((projeto.get("percurso") or {}).get("bugs_que_escaparam") or {}).get(a["id"])
    if filhos:
        print(f"    bugs que escaparam desta entrega: {', '.join(filhos)}")


def _uniao_de_intervalos(intervalos: list[list[str]]) -> float:
    """Segundos cobertos pela UNIÃO, não pela soma.

    É a conta que impede a pessoa de ser contada duas vezes. Se você leu a
    atividade A de 10:00 às 10:08 e a B de 10:05 às 10:12, o seu tempo foi
    12 minutos — não 8 + 7 = 15.
    """
    pares = []
    for par in intervalos:
        if not par or len(par) != 2 or not all(par):
            continue
        try:
            a, b = datetime.fromisoformat(par[0]), datetime.fromisoformat(par[1])
        except ValueError:
            continue
        if b > a:
            pares.append((a, b))
    pares.sort()
    total = 0.0
    fim_atual = None
    inicio_atual = None
    for a, b in pares:
        if fim_atual is None or a > fim_atual:
            if fim_atual is not None:
                total += (fim_atual - inicio_atual).total_seconds()
            inicio_atual, fim_atual = a, b
        elif b > fim_atual:
            fim_atual = b
    if fim_atual is not None:
        total += (fim_atual - inicio_atual).total_seconds()
    return total


def cmd_conjunto(args) -> int:
    """As atividades que rodaram em PARALELO, medidas como conjunto.

    Existe porque uma atividade por vez não responde a pergunta que importa
    quando três correm juntas: **quanto o paralelismo comprou.** E porque a
    resposta ingênua — somar os relatórios — sai errada para o lado que agrada.

    O que soma: tokens, custo, turnos, agentes. É consumo, e aconteceu.

    **O que NÃO soma, e é o ponto:**

    `prazo` é relógio de parede, e as atividades se sobrepõem. Somar daria o
    que teria custado em SÉRIE — que é justamente o numerador do ganho, não o
    prazo. Os dois são impressos, e a razão entre eles é o ganho.

    `hora humana` é a pior de somar, porque a pessoa é **uma**. Três atividades
    paralelas somadas contariam você três vezes no mesmo minuto — e subestimar
    esforço humano infla o ganho da ferramenta, que é o erro que este coletor
    declara não poder cometer. Aqui ela sai da UNIÃO dos intervalos, e a soma
    aparece ao lado só para mostrar quanto se evitou de contar duas vezes.

    O `reentrada` continua por interação: cada mensagem que você digitou é um
    retorno de contexto que aconteceu de fato, e trocar de atividade não o
    torna mais barato.
    """
    registros = []
    faltando = []
    for alvo in args.alvos:
        caminho = Path(alvo)
        if not caminho.is_file():
            # Também aceita id solto, resolvido no `.agents` corrente.
            try:
                caminho = resolve_agents_dir() / "metrics" / f"{alvo}.json"
            except FlowStateError:
                caminho = Path(alvo)
        if not caminho.is_file():
            faltando.append(alvo)
            continue
        try:
            registros.append(json.loads(caminho.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            faltando.append(alvo)
    if faltando:
        raise FlowStateError("não consegui ler: " + ", ".join(faltando))
    if not registros:
        raise FlowStateError("passe ao menos um registro coletado.")

    nao = [r for r in registros if r.get("atribuicao") == "sem-prova"]
    usados = [r for r in registros if r.get("atribuicao") != "sem-prova"]
    if not usados:
        raise FlowStateError(
            "nenhuma das atividades passadas tem prova de atribuição — "
            "o conjunto sairia inteiro em zero.")

    turnos = sum(int(r.get("turnos") or 0) for r in usados)
    agentes = sum(int(r.get("agentes") or 0) for r in usados)
    custo = round(sum(float(r.get("custo_usd") or 0) for r in usados), 2)
    somado = round(sum(float(r.get("prazo_h") or 0) for r in usados), 2)

    pontas = [p for r in usados for p in (r.get("janela") or []) if p]
    parede = 0.0
    if len(pontas) >= 2:
        try:
            marcos = sorted(datetime.fromisoformat(p) for p in pontas)
            parede = round((marcos[-1] - marcos[0]).total_seconds() / 3600, 2)
        except ValueError:
            parede = 0.0

    intervalos = [i for r in usados for i in (r.get("humano") or {}).get("intervalos", [])]
    interacoes = sum(int((r.get("humano") or {}).get("interacoes") or 0) for r in usados)
    # A reentrada usa o PADRÃO do pacote, e não o config de um projeto: o
    # conjunto atravessa `.agents/`, e não há um config que valha para todos.
    # Se os projetos declaram valores diferentes, este número usa o padrão — e
    # é por isso que ele é impresso, em vez de ficar implícito.
    reent = REENTRADA_MIN
    uniao_h = round(_uniao_de_intervalos(intervalos) / 3600
                    + interacoes * reent / 60, 3)
    soma_h = round(sum(float((r.get("humano") or {}).get("total_h") or 0)
                       for r in usados), 3)

    projetos = {r.get("raiz") or "" for r in usados}
    print(f"\nConjunto — {len(usados)} atividade(s)")
    print(f"  {'turnos':<38} {turnos:>12,}   soma")
    print(f"  {'agentes':<38} {agentes:>12}   soma")
    print(f"  {'custo em tabela de API':<38} {'US$ ' + format(custo, ',.2f'):>12}   soma")
    # A assinatura NÃO soma, e por uma razão diferente da hora humana: ela é
    # cobrada por tempo corrido, e o tempo corrido não dobra porque você abriu
    # duas janelas. Somar o rateio das paralelas cobraria a mesma assinatura
    # duas vezes no mesmo mês. Por isso ela é rateada pela PAREDE.
    mensais = {float(r["assinatura_mensal_usd"]) for r in usados
               if r.get("assinatura_mensal_usd")}
    if mensais and parede > 0:
        mensal = max(mensais)
        print(f"  {'custo de assinatura no período':<38} "
              f"{'US$ ' + format(round(mensal / HORAS_POR_MES * parede, 2), ',.2f'):>12}"
              f"   pela PAREDE")
        if len(mensais) > 1:
            valores = ", ".join(f"US$ {v:,.2f}" for v in sorted(mensais))
            print(f"    [ATENÇÃO] os registros declaram mensais diferentes ({valores}).")
            print(f"    Usei o maior. A assinatura é da pessoa, não do projeto —")
            print(f"    dois `.agents/` discordando é config para acertar.")
    print()
    print(f"  {'prazo somado':<38} {somado:>10.1f} h   o que custaria em série")
    print(f"  {'prazo de parede':<38} {parede:>10.1f} h   o que custou de fato")
    if parede > 0 and somado > 0:
        print(f"  {'GANHO DE PARALELISMO':<38} {somado / parede:>10.2f}x")
    else:
        print(f"  {'GANHO DE PARALELISMO':<38} {'indisponível':>12}   sem janela nos registros")
    # Prazo somado e prazo de parede crescem os dois enquanto houver frente
    # aberta. A razão entre eles continua legível, mas é retrato da hora em
    # que se coletou — não o resultado do conjunto.
    abertas = [r for r in usados if prazo_esta_aberto(r)]
    if abertas:
        print(f"  {len(abertas)} de {len(usados)} em andamento: os dois prazos ainda "
              f"crescem, e o\n  ganho acima é retrato, não resultado.")
    print()
    print(f"  {'hora humana (UNIÃO)':<38} {uniao_h:>10.2f} h")
    print(f"  {'  a soma seria':<38} {soma_h:>10.2f} h   e contaria você mais de uma")
    print(f"  {'  interações':<38} {interacoes:>12}")
    print(f"  {'  reentrada usada':<38} {str(reent) + ' min':>12}   padrão do pacote")

    if nao:
        print()
        print(f"  [ATENÇÃO] {len(nao)} atividade(s) ficaram FORA do conjunto, por falta")
        print("            de prova de atribuição — o total acima é DE MENOS:")
        for r in nao:
            print(f"              {r.get('id', '?'):<18} {r.get('motivo_atribuicao', '')}")

    print()
    print("  O que isto NÃO prova: que o paralelismo foi de graça. A razão mede")
    print("  relógio, não conflito — duas atividades que se atrapalham produzem o")
    print("  mesmo ganho de prazo e um retrabalho que este número não vê.")
    return 0


def cmd_painel(args) -> int:
    import panel as P

    agents = resolve_agents_dir()
    destino = agents / "metrics"
    alvo = destino / "projeto.json"
    if not alvo.exists():
        raise FlowStateError(
            f"nada coletado ainda em {destino}.\n"
            f"Rode: metrics.py coletar --raiz {args.raiz}")
    projeto = json.loads(alvo.read_text(encoding="utf-8"))
    atividades = {}
    for arq in sorted(destino.glob("*.json")):
        if arq.name == "projeto.json":
            continue
        try:
            reg = json.loads(arq.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        atividades[reg["id"]] = reg
    saida = Path(args.saida).resolve() if args.saida else destino / "painel.html"
    P.gerar(saida, projeto, atividades, NOMES_STEP)
    print(f"  painel gravado em {saida}")
    print(f"  {len(atividades)} atividade(s), coletadas em {projeto.get('gerado_em')}")
    return 0


def _avisar_publicado_velho(raiz: Path, agents: Path) -> None:
    """Diz que o resumo versionado ficou para trás do que acabou de ser medido.

    Compara o relógio do arquivo publicado com o do `projeto.json`. Não tenta
    consertar: publicar é decisão declarada em `[metricas] publicar_no_repo`, e
    ela continua valendo. O que não pode é a divergência ser **invisível**.
    """
    alvo = agents / "metrics" / "projeto.json"
    pasta = C.obter("metricas.publicar_em", "docs", agents) or "docs"
    publicado = raiz / pasta / "metricas.md"
    if not alvo.exists() or not publicado.exists():
        return
    if publicado.stat().st_mtime >= alvo.stat().st_mtime:
        return
    from datetime import datetime as _dt
    quando = _dt.fromtimestamp(publicado.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    print(f"  [métricas] medi, mas NÃO publiquei: `[metricas] publicar_no_repo` "
          f"está desligado.\n             `{pasta}/metricas.md` e o bloco do README "
          f"seguem em {quando},\n             mais velhos que a medida que acabei "
          f"de gravar. Para alinhar:\n             metrics.py publicar --raiz .")


def cmd_publicar(args) -> int:
    """Move um RESUMO das métricas para dentro do versionamento do projeto.

    Existe por causa de uma consequência do `install.sh`: ele põe `.agents/` em
    `.git/info/exclude`, porque ferramental de IA não é entregável do cliente.
    Correto — e o efeito colateral é que o painel existe no disco de quem rodou
    e mais ninguém o abre. Um gestor não tem como olhar o andamento sem pedir a
    alguém que rode um comando.

    Então a fronteira é atravessada de propósito, e com três limites:

    **Só o resumo.** Hora humana POR ATIVIDADE não sai — num arquivo versionado,
    ao lado do nome da branch, ela vira nota de desempenho individual. O total
    do projeto fica; a linha por atividade, não. Detalhe por step e por agente
    também não: responde "onde foi o custo", que é pergunta de quem opera.

    **Nunca por conta própria.** `[metricas] publicar_no_repo` é `false` por
    padrão, e sem ele o gancho do `avancar` não escreve nada no repositório de
    ninguém. Rodar o comando à mão vale como a declaração daquela vez — quem
    digitou pediu.

    **Escreve e indexa; não commita.** Mesmo idioma do `attach.py`: `git add`
    grava o blob, e criar commit no meio de um `avancar` mexeria no histórico
    sem ninguém ter pedido. O comando de commit sai impresso, pronto.
    """
    import publish as P

    raiz = Path(args.raiz).resolve()
    agents = resolve_agents_dir()
    # `--auto` obedece o config; `--calado` cala a saída. São separados porque
    # o `avancar` quer os dois e o `concluir` quer só o primeiro: ele indexa
    # arquivos, e indexar em silêncio deixaria o `git status` da pessoa com
    # coisa que ela não pôs lá.
    if args.auto and not C.obter("metricas.publicar_no_repo", False, agents):
        # As outras duas recusas de publicar — trilha `revisao` e worktree —
        # FALAM. Esta era muda, e a assimetria tinha consequência medida em
        # 20/09/2026 no `acme-backoffice`: o `concluir` regravou o
        # `projeto.json` e deixou o README publicando a coleta do dia anterior,
        # ao lado dele. Quem leu o README acreditou numa coleta que o JSON já
        # contradizia.
        #
        # **Só fala quando há o que envelhecer.** Se ninguém nunca publicou, o
        # aviso seria ruído em todo `concluir` de todo projeto que escolheu não
        # publicar — e essa escolha é legítima e é o padrão.
        if not args.calado:
            _avisar_publicado_velho(raiz, agents)
        return 0
    quieto = args.calado
    alvo = agents / "metrics" / "projeto.json"
    if not alvo.exists():
        if args.auto:
            return 0
        raise FlowStateError(
            f"nada coletado ainda em {agents / 'metrics'}.\n"
            f"Rode: metrics.py coletar --raiz {args.raiz}")
    projeto = json.loads(alvo.read_text(encoding="utf-8"))

    pasta = args.pasta or C.obter("metricas.publicar_em", "docs", agents) or "docs"
    feito = P.publicar(projeto, raiz, pasta, no_readme=not args.sem_readme)

    escritos = [feito["markdown"], feito["html"]]
    if feito["readme"]:
        escritos.append(feito["readme"])
    indexados, recusados = [], []
    if args.indexar:
        for arq in escritos:
            r = subprocess.run(["git", "-C", str(raiz), "add", "--", str(arq)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            (indexados if r.returncode == 0 else recusados).append(
                (arq, (r.stderr or "").strip()))

    # A ÚNICA coisa que fura o silêncio: a primeira escrita num README que não
    # é do pacote. Regenerar entre marcas é rotina e não merece linha nenhuma;
    # acrescentar um bloco a um arquivo que alguém escreveu à mão acontece uma
    # vez, e acontecer em silêncio seria o pacote se impondo sem dizer.
    if feito["readme_acao"] in ("criou", "acrescentou"):
        alvo = feito["readme"].relative_to(raiz)
        print(f"  {feito['readme_acao']} o bloco de métricas em {alvo} — daqui em "
              f"diante ele é substituído só entre as marcas.")
    if quieto:
        return 0

    print()
    for arq in escritos:
        rel = arq.relative_to(raiz) if arq.is_relative_to(raiz) else arq
        print(f"  gravado   {rel}")
    if feito["readme_acao"] == "criou":
        print("            (o README não existia — criei um com o bloco dentro)")
    elif feito["readme_acao"] == "acrescentou":
        print("            (o README não tinha as marcas — acrescentei o bloco ao fim;")
        print("             daqui em diante a publicação substitui só entre elas)")
    if recusados:
        print()
        for arq, erro in recusados:
            print(f"  [ATENÇÃO] o Git recusou indexar {arq.name}: {erro or 'sem motivo dito'}")
    if indexados:
        print(f"\n  {len(indexados)} arquivo(s) indexados. O commit é seu:")
        print(f"    git -C {raiz} commit -m 'docs(metricas): andamento do projeto'")
        print("\n  Não commito por você: criar commit no meio de outra coisa mexe no")
        print("  histórico sem ninguém ter pedido. Mesmo idioma do `attach.py`.")
    if not C.obter("metricas.publicar_no_repo", False, agents):
        print("\n  Isto NÃO vai se repetir sozinho: `[metricas] publicar_no_repo` está")
        print("  em `false`, que é o padrão. Ligue-a para o `avancar` regenerar estes")
        print("  arquivos a cada passagem de step, e o `concluir` indexá-los.")
    return 0


def _rodape(projeto: dict) -> str:
    p = projeto.get("parametros", {})
    return (f"\n  O que isto NÃO prova: o custo é de tabela de API — quem roda por "
            f"assinatura\n  não paga isso, é teto. A hora humana é modelo: teto de "
            f"{p.get('teto_leitura_min', '?')} min por\n  interação mais "
            f"{p.get('reentrada_min', '?')} min de reentrada. PF não é medido, é declarado.\n")


# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="metrics.py",
        description="Métricas do fluxo, do projeto ao agente, com drill-down.")
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("coletar", help="lê transcritos e atividades, grava os JSON")
    c.add_argument("--raiz", default=".")
    c.add_argument("--atividade", default=None, help="só esta; sem isto, todas")
    c.add_argument("--silencioso", action="store_true")
    c.set_defaults(func=cmd_coletar)

    r = sub.add_parser("relatar", help="mostra o nível pedido")
    r.add_argument("--raiz", default=".")
    r.add_argument("--atividade", default=None)
    r.add_argument("--step", default=None)
    r.set_defaults(func=cmd_relatar)

    j = sub.add_parser("conjunto",
                       help="as atividades que rodaram em paralelo, como conjunto")
    j.add_argument("alvos", nargs="+",
                   help="ids ou caminhos de JSON já coletados, de quantos .agents/ forem")
    j.add_argument("--raiz", default=".")
    j.set_defaults(func=cmd_conjunto)

    b = sub.add_parser("publicar",
                       help="grava o resumo DENTRO do repositório (docs/ + README)")
    b.add_argument("--raiz", default=".")
    b.add_argument("--pasta", default=None,
                   help="padrão: `[metricas] publicar_em`, ou `docs`")
    b.add_argument("--sem-readme", action="store_true", dest="sem_readme",
                   help="não mexe no README; só grava a pasta")
    b.add_argument("--indexar", action="store_true",
                   help="`git add` no que gravou. Nunca commita.")
    b.add_argument("--auto", action="store_true",
                   help="uso interno do fluxo: só publica se o config mandar")
    b.add_argument("--calado", action="store_true",
                   help="não imprime nada em caminho feliz")
    b.set_defaults(func=cmd_publicar)

    n = sub.add_parser("painel", help="gera o HTML com drill-down clicável")
    n.add_argument("--raiz", default=".")
    n.add_argument("--saida", default=None,
                   help="padrão: <.agents>/metricas/painel.html")
    n.set_defaults(func=cmd_painel)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except FlowStateError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


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
    raise SystemExit(main())
