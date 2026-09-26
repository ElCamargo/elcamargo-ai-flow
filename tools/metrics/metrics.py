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
from flow_state import FlowStateError, resolve_agents_dir  # noqa: E402
import config as C  # noqa: E402

# Tabela de preço por milhão de tokens. Fica aqui, e não no config, porque é do
# modelo e não do projeto — mas `[metricas] precos` sobrescreve quando alguém
# rodar com outro modelo ou quando a tabela mudar.
PRECOS_PADRAO = {
    "entrada": 15.0,
    "cache_escrita": 18.75,
    "cache_leitura": 1.50,
    "saida": 75.0,
}

CHAVES_USO = {
    "input_tokens": "entrada",
    "cache_creation_input_tokens": "cache_escrita",
    "cache_read_input_tokens": "cache_leitura",
    "output_tokens": "saida",
}

# Teto por interação e custo de reentrada, em minutos. Ver docstring.
TETO_LEITURA_MIN = 10
REENTRADA_MIN = 3


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
    alvo = slug_do_projeto(raiz)
    nomes = {alvo}
    try:
        r = subprocess.run(
            ["git", "-C", str(raiz), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=15)
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
    compacto["texto"] = texto
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
    que o `STATE.md` cataloga: transcrito acrescido dentro da mesma
    granularidade de mtime serviria número velho em silêncio, e persistiria
    entre rodadas — que é pior que lento.
    """

    def __init__(self) -> None:
        self._por_arquivo: dict[Path, list[dict]] = {}
        self.arquivos_lidos = 0

    def registros(self, caminho: Path) -> list[dict]:
        if caminho not in self._por_arquivo:
            self._por_arquivo[caminho] = self._ler(caminho)
            self.arquivos_lidos += 1
        return self._por_arquivo[caminho]

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
    m = re.search(r"\*\*step\s*(\d)", prompt)
    if m:
        return int(m.group(1)), "titular"
    n = re.search(r"step\s*(\d)", prompt, re.I)
    step = int(n.group(1)) if n else None
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


def prova_de_vinculo(registro: dict, branch: str, worktree: str, ident: str) -> bool:
    """Este registro é, sem dúvida, desta atividade?

    Três provas, e nenhuma sozinha basta para o transcrito inteiro:

    `gitBranch` é do repositório PRINCIPAL, não da worktree. Medido: numa
    atividade que rodou em worktree por 27 h, a branch dela só apareceu na
    última tarde, quando o repositório principal por acaso a checou. Filtrar
    por branch cortava 23 das 41 interações humanas.

    `cwd` acerta a worktree, mas o orquestrador trabalha da raiz e um subagente
    inteiro — o Analista de Sistema, 725 turnos — rodou lá também.

    Por isso as três só servem para dizer que a SESSÃO tocou a atividade. Quem
    recorta é a janela declarada no arquivo dela.
    """
    if branch and registro.get("gitBranch") == branch:
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

    for o in (corpus or Corpus()).registros(caminho):
        if vinculo and not tocou and prova_de_vinculo(o, *vinculo):
            tocou = True
        quando = o["quando"]
        if janela is not None and not janela.contem(quando):
            continue
        tipo = o.get("type")

        if tipo == "assistant":
            uso = somar(uso, o["uso"])
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
    if "## Artefatos" in texto:
        bloco = texto.split("## Artefatos")[1].split("## Conferências")[0]
        artefatos = sum(1 for l in bloco.splitlines()
                        if l.startswith("| ") and "| ---" not in l) - 1
    return {
        "campos": campos,
        "conferencias": conf,
        "por_ferramenta": ferramentas,
        "artefatos": max(artefatos, 0),
    }


def entrega_da_branch(raiz: Path, branch: str, base: str = "main") -> dict:
    """Tamanho da entrega, pelo diff de três pontos contra a base."""
    def git(*args) -> str:
        try:
            r = subprocess.run(["git", "-C", str(raiz), *args],
                               capture_output=True, text=True, timeout=30)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    if not branch or not git("rev-parse", "--verify", "--quiet", branch):
        return {}
    alvo = f"{base}...{branch}"
    def stat(*extra) -> dict:
        saida = git("diff", "--shortstat", alvo, *extra)
        m = re.search(r"(\d+) files? changed(?:, (\d+) insertions?...)?"
                      r"(?:, (\d+) deletions?...)?", saida)
        if not m:
            return {"arquivos": 0, "insercoes": 0, "remocoes": 0}
        return {"arquivos": int(m.group(1)),
                "insercoes": int(m.group(2) or 0),
                "remocoes": int(m.group(3) or 0)}
    total = stat()
    total["commits"] = len([x for x in git("log", "--oneline", f"{base}..{branch}").splitlines() if x])
    total["testes"] = stat("--", "*spec.ts", "*spec.tsx", "*test.ts", "*test.tsx")
    total["docs"] = stat("--", "docs/")
    return total


# ---------------------------------------------------------------------------
# coletar


HORAS_DE_SILENCIO = 4
MARGEM_DE_PONTA_MIN = 30


def _provas(raiz: Path, vinculo: tuple[str, str, str],
            inicio: datetime | None, corpus: "Corpus") -> list[datetime]:
    """Todo instante em que alguma sessão provou estar nesta atividade."""
    achadas: list[datetime] = []
    for pasta in pastas_de_sessao(raiz):
        for sessao in sorted(pasta.glob("*.jsonl")):
            for o in corpus.registros(sessao):
                if not prova_de_vinculo(o, *vinculo):
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


def coletar_atividade(raiz: Path, agents: Path, caminho: Path,
                      precos: dict, teto_min: int, reentrada_min: int,
                      corpus: "Corpus | None" = None) -> dict:
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
    vinculo = (branch, worktree, ident)
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
                turnos += sub["turnos"]
                momentos += sub["momentos"]
                agentes.append({
                    "id": arq.stem.replace("agent-", "")[:8],
                    "step": step,
                    "papel": papel,
                    "turnos": sub["turnos"],
                    "tokens": {k: int(v) for k, v in sub["uso"].items()},
                    "custo_usd": custo(sub["uso"], precos),
                    "prompt": prompt[:120].replace("\n", " "),
                })
                if step is not None:
                    alvo = por_step.setdefault(
                        step, {"agentes": 0, "turnos": 0,
                               "uso": {k: 0.0 for k in precos}})
                    alvo["agentes"] += 1
                    alvo["turnos"] += sub["turnos"]
                    alvo["uso"] = somar(alvo["uso"], sub["uso"])

    # Prazo é até a ENTREGA, e a cauda é separada. Somar as duas numa métrica
    # só deu 40 h onde a entrega saiu em 26 — porque o conserto do que escapou
    # entrou horas depois e o número não distinguia "demorou a entregar" de
    # "voltou a mexer". Quem lê um painel de prazo quer a primeira.
    prazo = cauda = 0.0
    if momentos:
        abertura, fechamento = min(momentos), max(momentos)
        entrega = encerrada if encerrada and encerrada >= abertura else fechamento
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
        "step": campos.get("step", ""),
        "status": campos.get("status", ""),
        "branch": branch,
        "criado_em": campos.get("criado_em", ""),
        "concluido_em": campos.get("concluido_em", ""),
        "pf": pf,
        "pf_aferido": pf_aferido,
        "pf_inventario": (campos.get("pf_inventario") or "").strip() or None,
        "divergencia_pf": None,
        "prazo_h": prazo,
        "cauda_h": cauda,
        "humano": humano,
        "tokens": {k: int(v) for k, v in uso_total.items()},
        "custo_usd": custo(uso_total, precos),
        "turnos": turnos,
        "agentes": len(agentes),
        "sessoes": sessoes_usadas,
        "janela": [j.isoformat() if j else None for j in janela.extremos()],
        "conferencias": dados["conferencias"],
        "por_ferramenta": dados["por_ferramenta"],
        "artefatos": dados["artefatos"],
        "entrega": entrega_da_branch(raiz, branch),
        "steps": [
            {"step": s, "agentes": v["agentes"], "turnos": v["turnos"],
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


def _sobreposicoes(todas: list[dict]) -> list[dict]:
    """Pares de atividades que dividem branch e janela — logo, dividem custo."""
    achados = []
    for i, a in enumerate(todas):
        for b in todas[i + 1:]:
            if not a.get("branch") or a["branch"] != b.get("branch"):
                continue
            ja, jb = a.get("janela") or [], b.get("janela") or []
            if len(ja) != 2 or len(jb) != 2 or not all(ja) or not all(jb):
                continue
            if ja[0] <= jb[1] and jb[0] <= ja[1]:
                menor = min(a["custo_usd"], b["custo_usd"])
                achados.append({
                    "atividades": [a["id"], b["id"]],
                    "branch": a["branch"],
                    "custo_contado_duas_vezes_usd": round(menor, 2),
                })
    return achados


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
        reg = coletar_atividade(raiz, agents, arq, precos, teto, reent, corpus)
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

    projeto = {
        "projeto": C.obter("projeto.nome", raiz.name, agents) or raiz.name,
        "raiz": str(raiz),
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parametros": {"precos": precos, "teto_leitura_min": teto,
                       "reentrada_min": reent},
        "atividades": len(todas),
        "atividades_no_total": len(atribuidas),
        "nao_atribuidas": [a["id"] for a in nao],
        "concluidas": sum(1 for a in todas if a.get("status") == "concluido"),
        "tokens": {k: sum(a["tokens"].get(k, 0) for a in atribuidas) for k in precos},
        "custo_usd": round(sum(a["custo_usd"] for a in atribuidas), 2),
        "turnos": sum(a["turnos"] for a in atribuidas),
        "agentes": sum(a["agentes"] for a in atribuidas),
        "humano_h": round(sum(a["humano"]["total_h"] for a in atribuidas), 2),
        "interacoes": sum(a["humano"]["interacoes"] for a in atribuidas),
        "pf": sum(a["pf"] for a in todas if a.get("pf")) or None,
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
    projeto["sobreposicoes"] = _sobreposicoes(atribuidas)
    (destino / "projeto.json").write_text(
        json.dumps(projeto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.silencioso:
        print(f"\n  {len(todas)} atividade(s) em {destino}")
        print(f"  {corpus.arquivos_lidos} transcrito(s) lidos uma vez nesta rodada")
    return 0


# ---------------------------------------------------------------------------
# relatar


NOMES_STEP = {
    1: "Gestor da Atividade", 2: "Revisor de Negócio", 3: "Analista de Sistema",
    4: "Revisor da Especificação", 5: "Portão · especificação",
    6: "Designer de Telas", 7: "Portão · telas", 8: "Desenvolvedor",
    9: "Revisor da Entrega", 10: "Portão · entrega",
}


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
            print(f"  {a['id'][:26]:<26} {a['turnos']:>7} {a['agentes']:>8} "
                  f"{a['custo_usd']:>10,.2f} {a['humano']['total_h']:>8.2f}h "
                  f"{a['prazo_h']:>7.1f}h  {_barra(a['custo_usd']/pico)}")
        rotulo = ("TOTAL" if len(atribuidas) == p["atividades"]
                  else f"TOTAL ({len(atribuidas)} de {p['atividades']})")
        print(f"\n  {rotulo:<26} {p['turnos']:>7} {p['agentes']:>8} "
              f"{p['custo_usd']:>10,.2f} {p['humano_h']:>8.2f}h")
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
        sob = p.get("sobreposicoes") or []
        if sob:
            duplo = sum(s["custo_contado_duas_vezes_usd"] for s in sob)
            print(f"\n  [ATENÇÃO] {len(sob)} par(es) dividem branch e janela — o TOTAL acima")
            print(f"            soma até US$ {duplo:,.2f} duas vezes:")
            for s in sob:
                print(f"              {' + '.join(s['atividades'])}   ({s['branch']})")
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
        print(_rodape(json.loads((destino / "projeto.json").read_text(encoding="utf-8"))))
        return 0

    h = a["humano"]
    linhas = [
        ("turnos de assistente", f"{a['turnos']:,}"),
        ("agentes", f"{a['agentes']}"),
        ("custo em tabela de API", f"US$ {a['custo_usd']:,.2f}"),
        ("prazo, do primeiro registro à entrega", f"{a['prazo_h']:.1f} h"),
        ("hora humana (leitura + reentrada)", f"{h['total_h']:.2f} h"),
        ("cauda, trabalho depois da entrega", f"{a.get('cauda_h', 0):.1f} h"),
        ("interações humanas", f"{h['interacoes']}"),
        ("perguntas de portão respondidas", f"{h['perguntas_portao']}"),
    ]
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
    for k, v in linhas:
        print(f"  {k:<42} {v:>14}")

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

    print(_rodape(json.loads((destino / "projeto.json").read_text(encoding="utf-8"))))
    return 0


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
    print()
    print(f"  {'prazo somado':<38} {somado:>10.1f} h   o que custaria em série")
    print(f"  {'prazo de parede':<38} {parede:>10.1f} h   o que custou de fato")
    if parede > 0 and somado > 0:
        print(f"  {'GANHO DE PARALELISMO':<38} {somado / parede:>10.2f}x")
    else:
        print(f"  {'GANHO DE PARALELISMO':<38} {'indisponível':>12}   sem janela nos registros")
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
    P.gerar(saida, projeto, atividades)
    print(f"  painel gravado em {saida}")
    print(f"  {len(atividades)} atividade(s), coletadas em {projeto.get('gerado_em')}")
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
    raise SystemExit(main())
