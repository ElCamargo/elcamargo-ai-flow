#!/usr/bin/env python3
"""Isto já existe? E se existe, o que esta demanda ACRESCENTA?

As duas perguntas mais caras do fluxo, respondidas por varredura em vez de
leitura.

Sem isto, cada step relê o repositório inteiro para descobrir que a demanda já
tem dono — e o custo do descobrimento fica proporcional ao MÓDULO, quando
deveria ser proporcional ao DELTA. Uma demanda que acrescenta um campo a um
painel pronto não pode custar o mesmo que especificar o painel.

O que ele faz, tudo mecânico:

    - acha as atividades que já rodaram sobre o mesmo assunto;
    - acha a SDD que já é DONA do comportamento, por sobreposição de conceito;
    - mede o DELTA: quais conceitos da demanda aquela SDD já cobre, e quais não;
    - acha o código que implementa;
    - confronta a memória de rejeição.

O que ele NÃO faz: decidir. Ele entrega sinal; a trilha é escolha de quem lê,
com o usuário.

    python3 already_exists.py --demanda "texto da demanda ou caminho de arquivo"
    python3 already_exists.py --demanda demanda.md --card 1088
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import tomllib
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flow-state"))
from config import pathspec_ignorar as ignorar  # noqa: E402

# Palavras que não carregam conceito. Gramática do português, mais o vocabulário
# genérico de software que aparece em toda especificação e por isso não
# distingue nenhuma.
PARADAS = set("""
a as o os um uma uns umas de do da dos das em no na nos nas por para pelo pela
com sem sob sobre entre ate apos antes que quem qual quais quando onde como
porque pois se nao sim e ou mas nem tambem ja ainda muito mais menos todo toda
todos todas cada outro outra outros outras mesmo mesma seu sua seus suas este
esta estes estas esse essa esses essas aquele aquela isso isto aquilo ser estar
ter haver fazer poder dever ir vir dar ver saber querer deve devem deveria
sera serao foi foram e' sao tem tinha havia pode podem precisa precisam
ao aos as`s la lo na`s num numa pelos pelas dele dela deles delas
sistema usuario usuarios tela telas campo campos dado dados pagina paginas
botao botoes item itens lista listas valor valores nome nomes tipo tipos
funcionalidade requisito requisitos regra regras negocio caso casos teste
testes criterio criterios aceite documento documentacao secao secoes
implementar implementacao desenvolvimento projeto modulo feature
""".split())

MIN_TERMO = 4
MAX_TERMOS = 40
MIN_RADICAL = 4

# Limiares de similaridade de cosseno, em valor ABSOLUTO. Antes o percentual era
# relativo ao primeiro colocado, e por isso um assunto genuinamente novo — Pix,
# conciliação bancária — aparecia com "100% de aderência" contra a spec menos
# distante. Quem lesse concluiria que já existia.
# A medida que decide o veredito é a COBERTURA, não a similaridade — e ela é
# assimétrica de propósito: a pergunta é "quanto da demanda este documento já
# cobre", não "quanto os dois se parecem". Uma spec de 600 linhas que cobre a
# demanda inteira tem cosseno baixo, porque fala de muita coisa além dela; e
# ainda assim é a dona do comportamento.
#
# Ponderada por raridade: cobrir `gateway` e `webhook` vale pouco, porque toda
# spec de integração os cita. Cobrir `conciliacao bancaria` vale muito.
LIMIAR_DONO = 0.70      # acima disto, candidata a dona do comportamento
LIMIAR_PARCIAL = 0.40   # entre os dois, cobre parte

# Quando a demanda é escrita em vocabulário de MECANISMO — "recusa", "exceção",
# "erro", "código", "frontend" — e não de DOMÍNIO, toda spec da área cobre quase
# tudo e nenhuma é dona. Foi o que aconteceu ao rodar o fluxo num bug real: as
# três primeiras vieram em 76/75/71% e a ferramenta anunciou como dona uma spec
# de upload em lote, que não tem nada com o assunto.
#
# O sinal está na forma do resultado: coberturas AGRUPADAS no topo com
# semelhança BAIXA. Se as primeiras empatam e nenhuma se parece com a demanda,
# o que casou foi vocabulário comum, não assunto.
EMPATE_NO_TOPO = 0.15      # diferença entre 1º e 3º abaixo disto = empate
SEMELHANCA_FRACA = 0.15    # nenhuma se parece de verdade com a demanda

# Sufixos do português, do mais longo para o mais curto. O objetivo não é
# linguística correta: é que os DOIS lados — demanda e documento — sofram a
# mesma redução, para "paginada" e "paginação" caírem no mesmo balde.
#
# Sem isto, a ferramenta anunciava como conceito NOVO o que era só outra flexão
# do que já estava especificado: numa demanda sobre painel de pedidos, os três
# "não cobertos" eram `paginada`, `encontra` e `carga` — dois deles variações de
# palavras presentes no documento.
SUFIXOS = (
    "issimo", "issima", "mente", "ancia", "encia", "dade", "agem", "ismo",
    "ista", "ivel", "avel", "ção", "cao", "sao", "ões", "oes", "aes", "aos",
    "ando", "endo", "indo", "adas", "ados", "idas", "idos", "ada", "ado",
    "ida", "ido", "ar", "er", "ir", "am", "em", "ou", "es", "as", "os",
    "a", "o", "e", "s",
)


def radical(palavra: str) -> str:
    """Reduz a palavra ao radical, de forma conservadora.

    Aplica no máximo dois cortes: um derivacional e um de flexão. Cortar mais
    junta conceitos distintos, que é pior que separar flexões da mesma palavra.
    """
    p = palavra
    for _ in range(2):
        for sufixo in SUFIXOS:
            if p.endswith(sufixo) and len(p) - len(sufixo) >= MIN_RADICAL:
                p = p[: -len(sufixo)]
                break
        else:
            break
    return p


class JaExisteError(Exception):
    pass


def sem_acento(t: str) -> str:
    n = unicodedata.normalize("NFD", t)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").lower()


def git(args: list[str], raiz: Path) -> str:
    r = subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def raiz_de_trabalho() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise JaExisteError("não estou dentro de um repositório git")
    return Path(r.stdout.strip())


def pasta_agents(raiz: Path) -> Path:
    """O .agents, mesmo rodando de dentro de uma worktree."""
    for candidato in (raiz / ".agents", raiz.parent / ".agents"):
        if candidato.is_dir():
            return candidato
    comum = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if comum.returncode == 0 and comum.stdout.strip():
        alvo = Path(comum.stdout.strip()).parent / ".agents"
        if alvo.is_dir():
            return alvo
    raise JaExisteError("não achei o .agents")


def carregar_config(agents: Path) -> dict:
    caminho = agents / "config.toml"
    if not caminho.exists():
        return {}
    return tomllib.loads(caminho.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Conceitos
# --------------------------------------------------------------------------
def termos(texto: str) -> Counter:
    """Os conceitos de um texto, sem gramática e sem vocabulário genérico."""
    limpo = sem_acento(texto)
    limpo = re.sub(r"```.*?```", " ", limpo, flags=re.S)   # código não é conceito
    limpo = re.sub(r"https?://\S+", " ", limpo)
    palavras = re.findall(r"[a-z][a-z0-9]{%d,}" % (MIN_TERMO - 1), limpo)
    return Counter(radical(p) for p in palavras if p not in PARADAS)


@dataclass
class Documento:
    caminho: Path
    relativo: str
    termos: Counter
    titulo: str = ""
    pontos: float = 0.0
    cobertura: float = 0.0
    cobertos: list[str] = field(default_factory=list)
    faltando: list[str] = field(default_factory=list)


# "conforme CAM-001 regra 9", "ver UX-003". Quem escreve o card citando a spec
# está dando a resposta de graça, e nenhuma varredura por vocabulário chega
# perto dessa certeza. Sem isto, num card que citava CAM-001 pelo nome a
# ferramenta apontou CAM-009 como dona — uma spec de upload em lote.
#
# O número NÃO tem largura fixa, e a faixa também não serve. O `\d{3}` original
# amarrava esta ferramenta a uma convenção de um projeto: `CAM-1080` — id
# derivado do número do card, que é a saída natural para a colisão de numeração
# sequencial — não casava, porque `\b` exige fronteira depois do terceiro dígito
# e havia um quarto. A varredura devolveria "nenhuma spec citada" com a mesma
# cara de um card que realmente não cita nada.
#
# Achado em 12/09/2026, a partir da colisão que a Leticia levantou: dois ramos
# alocaram CAM-032..037 em paralelo e a renumeração para CAM-039..044 mexeu em
# 106 arquivos. A convenção é do projeto; este acoplamento era do pacote.
#
# A primeira correção pôs `\d{2,6}`, e ela estava errada pelo mesmo motivo, só
# que mais tarde: `acme-app` apontou que um card acima de 999999
# volta a falhar — e falha do mesmo jeito silencioso. Teto escolhido por
# conforto é defeito agendado. Por isso `\d+`: quem aloca o número é o board, e
# o board não pediu permissão para crescer.
#
# O preço de não ter teto é casar coisa que não é spec (`ISO 8601`). Isso é
# inofensivo aqui: `citadas()` só devolve documento que EXISTE com aquele nome,
# então uma citação inventada não vira dona de nada. Errar para o lado de
# procurar demais é o lado certo — o outro lado é silêncio.
RE_CITACAO = re.compile(r"\b([A-Z]{2,4})[\s\-]?(\d+)\b")


def citadas(texto: str, docs: list[Documento]) -> list[Documento]:
    """As especificações que a própria demanda nomeia."""
    alvos = {f"{p}-{n}" for p, n in RE_CITACAO.findall(texto)}
    if not alvos:
        return []
    saida = []
    for d in docs:
        nome = Path(d.relativo).name.upper()
        # Com largura variável o prefixo simples volta a mentir: `CAM-31`
        # casaria `CAM-1080-...`. O separador ancora o fim do número.
        if any(nome.startswith(a + "-") or nome == a + ".MD" for a in alvos):
            saida.append(d)
    return saida


def indexar(pasta: Path, raiz: Path, limite: int = 400) -> list[Documento]:
    docs: list[Documento] = []
    if not pasta.is_dir():
        return docs
    for caminho in sorted(pasta.glob("**/*.md")):
        if len(docs) >= limite:
            break
        try:
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        titulo = ""
        for linha in texto.splitlines()[:40]:
            m = re.match(r"^#\s+(.+)$", linha)
            if m:
                titulo = m.group(1).strip()
                break
        docs.append(Documento(caminho, str(caminho.relative_to(raiz)),
                              termos(texto), titulo))
    return docs


def idf(docs: list[Documento]) -> dict[str, float]:
    """Termo que aparece em toda spec não distingue nenhuma."""
    n = len(docs) or 1
    ocorre = Counter()
    for d in docs:
        ocorre.update(set(d.termos))
    return {t: math.log(n / (1 + c)) + 1.0 for t, c in ocorre.items()}


def pontuar(demanda: Counter, docs: list[Documento], pesos: dict[str, float]) -> None:
    """Similaridade de cosseno entre a demanda e cada documento.

    Cosseno, e não soma, por causa do viés de tamanho: sem normalizar, o
    documento MAIOR vence sempre, porque acumula mais ocorrências de qualquer
    termo. Numa demanda sobre painel de pedidos, a spec de clientes e
    upload em lote — três vezes maior — passou à frente da spec do painel.

    Termo raro pesa mais que termo comum (IDF), e o comprimento do documento
    sai da conta (normalização).
    """
    relevantes = [t for t, _ in demanda.most_common(MAX_TERMOS)]

    vetor_demanda = {t: math.log(1 + demanda[t]) * pesos.get(t, 1.0) for t in relevantes}
    norma_demanda = math.sqrt(sum(v * v for v in vetor_demanda.values())) or 1.0

    for d in docs:
        norma_doc = math.sqrt(sum(
            (math.log(1 + n) * pesos.get(t, 1.0)) ** 2 for t, n in d.termos.items()
        )) or 1.0

        produto = 0.0
        cobertos, faltando = [], []
        for t in relevantes:
            if d.termos.get(t):
                produto += vetor_demanda[t] * math.log(1 + d.termos[t]) * pesos.get(t, 1.0)
                cobertos.append(t)
            else:
                faltando.append(t)

        d.pontos = produto / (norma_demanda * norma_doc)
        # Cobertura: da massa de conceito da demanda, quanto este documento
        # alcança. Ponderada por IDF — termo raro pesa, termo comum não.
        total = sum(pesos.get(t, 1.0) for t in relevantes) or 1.0
        d.cobertura = sum(pesos.get(t, 1.0) for t in cobertos) / total
        d.cobertos = cobertos
        d.faltando = faltando


# --------------------------------------------------------------------------
def atividades_anteriores(agents: Path, demanda: Counter, card: str | None) -> list[tuple]:
    pasta = agents / "atividades"
    if not pasta.is_dir():
        return []
    saida = []
    relevantes = {t for t, _ in demanda.most_common(MAX_TERMOS)}
    for caminho in sorted(pasta.glob("*.md")):
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        cabeca = "\n".join(texto.splitlines()[:30])
        meu = termos(cabeca)
        comuns = relevantes & set(meu)
        mesmo_card = bool(card and card in caminho.stem)
        if not comuns and not mesmo_card:
            continue
        titulo = ""
        step = ""
        for linha in texto.splitlines()[:20]:
            if linha.startswith("titulo:"):
                titulo = linha.split(":", 1)[1].strip()
            if linha.startswith("step:"):
                step = linha.split(":", 1)[1].strip()
        saida.append((caminho.stem, titulo, step, sorted(comuns)[:6], mesmo_card))
    saida.sort(key=lambda x: (not x[4], -len(x[3])))
    return saida


def principal(args) -> int:
    raiz = raiz_de_trabalho()
    agents = pasta_agents(raiz)
    cfg = carregar_config(agents)

    alvo = Path(args.demanda).expanduser()
    bruto = alvo.read_text(encoding="utf-8", errors="replace") if alvo.exists() else args.demanda
    if len(bruto.strip()) < 20:
        raise JaExisteError(
            "a demanda tem menos de 20 caracteres. Passe o texto do card, ou o "
            "caminho de um arquivo com ele — sem conceito não há o que procurar."
        )
    conceitos = termos(bruto)
    if not conceitos:
        raise JaExisteError("não sobrou nenhum conceito na demanda depois de tirar "
                            "gramática e vocabulário genérico")

    docs_cfg = cfg.get("docs", {})
    specs = raiz / docs_cfg.get("specs", "docs/specs")
    docs = indexar(specs, raiz)

    L: list[str] = []
    w = L.append
    w("# Isto já existe?")
    w("")
    w("Varredura mecânica. **Sinal, não decisão** — a trilha é escolha sua, com")
    w("o usuário. E é rasa de propósito: a pergunta é *onde isto vive*, não")
    w("*como funciona*.")
    w("")
    principais = [t for t, _ in conceitos.most_common(12)]
    w(f"Conceitos da demanda: {', '.join(f'`{t}`' for t in principais)}")
    w("")

    # ---- atividades
    anteriores = atividades_anteriores(agents, conceitos, args.card)
    w("## Atividades que já rodaram sobre isto")
    w("")
    if anteriores:
        w("| Atividade | Step | Conceitos em comum | |")
        w("| --- | --- | --- | --- |")
        for ident, titulo, step, comuns, mesmo in anteriores[:10]:
            marca = "**mesmo id**" if mesmo else ""
            w(f"| `{ident}` | {step[:28]} | {', '.join(comuns)} | {marca} |")
        w("")
        w("Atividade com o mesmo id **não se reabre** — retome de onde parou. Com")
        w("id diferente e conceito igual, a pergunta é outra: é a mesma demanda")
        w("voltando com outro número, ou é complemento do que aquela entregou?")
    else:
        w("Nenhuma. Esta demanda é a primeira vez que o fluxo vê estes conceitos.")
    w("")

    # ---- SDD dona
    w("## A SDD que já é dona do comportamento")
    w("")
    nomeadas = citadas(bruto, docs)
    if nomeadas:
        w("### A demanda nomeia estas — leia-as primeiro")
        w("")
        for d in nomeadas:
            w(f"- **`{d.relativo}`**" + (f" — *{d.titulo}*" if d.titulo else ""))
        w("")
        w("Citação explícita vale mais que qualquer sobreposição de vocabulário:")
        w("quem escreveu a demanda já sabia onde o assunto mora. O ranking abaixo")
        w("é varredura cega e **pode discordar disto** — quando discordar, a")
        w("citação ganha.")
        w("")
    if not docs:
        w(f"Não achei especificação em `{specs.relative_to(raiz) if specs.is_relative_to(raiz) else specs}`.")
        w("Ou o projeto não usa SDD, ou o caminho no config está errado.")
    else:
        pesos = idf(docs)
        pontuar(conceitos, docs, pesos)
        # Ordena por cobertura, com a similaridade como desempate: sem o
        # desempate, o documento maior — que menciona tudo de passagem — empata
        # com o dono de verdade.
        ranking = sorted(docs, key=lambda d: (-d.cobertura, -d.pontos))[:5]
        if ranking[0].cobertura <= 0:
            w("Nenhuma especificação tem sobreposição de conceito com a demanda.")
            w("Trate como assunto novo — mas confirme por leitura: a busca é por")
            w("palavra, e o produto pode chamar isto de outro jeito.")
        else:
            # Empate no topo com semelhança fraca: o que casou foi vocabulário.
            candidatas = [d for d in ranking if d.cobertura > 0.02]
            generico = False
            if len(candidatas) >= 3:
                espalhamento = candidatas[0].cobertura - candidatas[2].cobertura
                generico = (espalhamento < EMPATE_NO_TOPO
                            and max(d.pontos for d in candidatas) < SEMELHANCA_FRACA
                            # Cobertura baixa já é "assunto novo", que é uma
                            # resposta melhor que "sem dono identificável".
                            and candidatas[0].cobertura >= LIMIAR_PARCIAL)

            if generico:
                w("> **As primeiras colocadas empatam, e nenhuma se parece com a")
                w("> demanda.** Isso quase sempre significa que a demanda está escrita")
                w("> em vocabulário de MECANISMO — *recusa, exceção, erro, código* — e")
                w("> não de DOMÍNIO. Toda spec da área cobre esse vocabulário, e")
                w("> nenhuma é dona do assunto.")
                w(">")
                w("> **Não leia o primeiro colocado como dono.** Reescreva a busca com")
                w("> o substantivo do domínio, ou vá direto ao código — é o caso")
                w("> típico de **bug**, onde a pergunta certa é *onde isto acontece*,")
                w("> não *quem especificou isto*.")
                w("")

            w("| Especificação | Cobre | Semelha | Leitura |")
            w("| --- | ---: | ---: | --- |")
            for d in ranking:
                if d.cobertura <= 0.02:
                    continue
                if generico:
                    leitura = "vocabulário em comum"
                elif d.cobertura >= LIMIAR_DONO:
                    leitura = "**candidata a dona**"
                elif d.cobertura >= LIMIAR_PARCIAL:
                    leitura = "cobre parte"
                else:
                    leitura = "distante"
                w(f"| `{d.relativo}` | {100 * d.cobertura:>3.0f}% | {d.pontos:.2f} "
                  f"| {leitura} |")
            w("")
            w("**Cobre** é quanto da demanda o documento alcança, com termo raro")
            w("pesando mais — é o que decide. **Semelha** é a similaridade entre os")
            w("dois textos, e serve só para desempatar: uma spec longa que cobre a")
            w("demanda inteira semelha pouco, porque fala de muita coisa além dela.")
            w("")
            w(f"Acima de {100 * LIMIAR_DONO:.0f}% é candidata a dona; abaixo de "
              f"{100 * LIMIAR_PARCIAL:.0f}% é distante. Os números são absolutos,")
            w("não relassets ao primeiro colocado — uma lista inteira abaixo do")
            w("limiar significa **assunto novo**, por mais que alguém apareça no topo.")
            w("")

            dona = ranking[0]
            if generico:
                dona = None
                w("### Sem dono identificável")
                w("")
                w("A varredura não distingue nenhuma spec para esta demanda. Para")
                w("bug, siga pelo código; para funcionalidade, refaça a busca com o")
                w("substantivo do domínio.")
                w("")
            elif dona.cobertura < LIMIAR_PARCIAL:
                w("### Nenhuma spec chega perto")
                w("")
                w(f"O melhor caso é `{dona.relativo}`, cobrindo {100*dona.cobertura:.0f}%")
                w(f"da demanda — abaixo do limiar de {100*LIMIAR_PARCIAL:.0f}%. **Trate")
                w("como assunto novo.**")
                w("")
                w("Confirme por leitura mesmo assim: a busca é por palavra, e o")
                w("produto pode ter isto com vocabulário completamente diferente.")
                w("")
                dona = None
            if dona is None:
                pass
            else:
                w(f"### O delta contra `{dona.relativo}`")
                w("")
                if dona.titulo:
                    w(f"*{dona.titulo}*")
                    w("")
                w(f"**Já cobertos** ({len(dona.cobertos)}): "
                  + ", ".join(f"`{t}`" for t in dona.cobertos[:20]))
                w("")
                    # Ordena por tf*idf: termo citado uma vez de passagem não é
                # conceito novo, é palavra solta. Antes a lista trazia `visa`,
                # `usad`, `cont` — fragmentos de verbo — junto com o que
                # importava, e o ruído escondia o sinal.
                novos = sorted(
                    (t for t in dona.faltando if pesos.get(t, 0) > 1.0),
                    key=lambda t: -(math.log(1 + conceitos[t]) * pesos.get(t, 1.0)),
                )[:12]
                if novos:
                    w(f"**NÃO cobertos** ({len(novos)}): "
                      + ", ".join(f"`{t}`" for t in novos))
                    w("")
                    w("Estes são o candidato a **delta**. Se a leitura confirmar, o")
                    w("trabalho é atualizar a SDD existente com estes pontos — não")
                    w("escrever uma nova. Uma SDD nova para algo que já tem dono")
                    w("espalha a verdade em dois lugares.")
                else:
                    w("**Nenhum conceito da demanda ficou de fora.**")
                    w("")
                    w("Isso é sinal forte de que a demanda **já está especificada**.")
                    w("Antes de abrir a atividade, leia essa SDD e confirme. Se estiver")
                    w("mesmo coberta, o desfecho é apontar onde está e encerrar.")
    w("")

    # ---- histórico
    w("## Isto já foi corrigido?")
    w("")
    achou_history = False
    if args.card:
        saida_log = git(["log", "--all", "--oneline", "--grep", args.card], raiz)
        commits = [l for l in saida_log.splitlines() if l.strip()][:12]
        if commits:
            achou_history = True
            w(f"**O histórico cita `{args.card}`:**")
            w("")
            for c in commits:
                w(f"- `{c}`")
            w("")
            ref = git(["symbolic-ref", "refs/remotes/origin/HEAD"], raiz).strip()
            padrao = ref.rsplit("/", 1)[-1] if ref else "main"
            for c in commits:
                sha = c.split()[0]
                dentro = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", sha, f"origin/{padrao}"],
                    cwd=raiz, capture_output=True)
                marca = "JÁ ESTÁ" if dentro.returncode == 0 else "ainda NÃO está"
                w(f"  - `{sha}` {marca} em `origin/{padrao}`")
            w("")

    # Conceito no assunto do commit: pega o caso em que o card é outro mas o
    # trabalho é o mesmo.
    #
    # Termo que casa com meio histórico não informa nada. Num card de FAQ, os
    # termos mais frequentes eram o nome do produto, `cadastr`, `admin` e
    # `permit`, e
    # os commits devolvidos não tinham nenhuma relação com o assunto — puro
    # ruído com aparência de achado.
    #
    # E busca no ASSUNTO, não na mensagem inteira: `git log --grep` varre também
    # o corpo, então um termo citado de passagem numa explicação de outro commit
    # aparecia como se fosse trabalho sobre o assunto. Uma chamada só, filtrada
    # aqui, é mais barata e diz a verdade sobre o que procurou.
    LIMITE_TERMO_COMUM = 8
    assuntos = [l for l in git(["log", "--all", "--oneline"], raiz).splitlines() if l.strip()]
    for termo in principais[:6]:
        linhas_log = [l for l in assuntos if termo in sem_acento(l)]
        if not linhas_log:
            continue
        if len(linhas_log) > LIMITE_TERMO_COMUM:
            w(f"- `{termo}`: {len(linhas_log)} commits citam este termo. É comum "
              "demais no histórico deste repositório para servir de sinal.")
            w("")
            continue
        achou_history = True
        w(f"**Commits cujo assunto cita `{termo}`:**")
        for l in linhas_log[:4]:
            w(f"- `{l}`")
        w("")

    if not achou_history:
        w("Nada no histórico cita este card nem estes conceitos.")
        w("")
    else:
        w("**Um commit mesclado não prova que o defeito acabou.** Ele prova que")
        w("alguém mexeu ali. Abra o diff, ache o teste que a correção acrescentou,")
        w("e **rode esse teste** — é a única evidência que vale. Se ele passa, o")
        w("desfecho é apontar onde está e **encerrar antes de abrir**.")
    w("")

    # ---- código
    w("## O código")
    w("")
    achou_codigo = False
    for termo in principais[:6]:
        r = subprocess.run(
            # `docs` e `.md` saem por razão PRÓPRIA desta ferramenta: ela
            # procura comportamento em CÓDIGO, e documentação que fala do
            # assunto casaria com tudo.
            ["git", "grep", "-l", "-i", "-F", termo, "--",
             *ignorar([":!docs*", ":!*.md"])],
            cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        arquivos = [l for l in r.stdout.splitlines() if l][:4]
        if arquivos:
            achou_codigo = True
            w(f"- **`{termo}`** — {', '.join(f'`{a}`' for a in arquivos)}"
              + (" …" if len(r.stdout.splitlines()) > 4 else ""))
    if not achou_codigo:
        w("Nenhum conceito da demanda aparece em arquivo de código.")
        w("")
        w("Cuidado: a demanda está em português e o código costuma estar em")
        w("inglês. Ausência aqui **não** prova que não existe — confirme com o")
        w("termo do domínio em inglês, ou com `tools/briefing/domain.py`.")
    w("")

    # ---- rejeição
    fora = docs_cfg.get("fora_de_escopo")
    w("## Memória de rejeição")
    w("")
    if fora and (raiz / fora).is_dir():
        rejeitados = indexar(raiz / fora, raiz)
        if rejeitados:
            pesos_r = idf(rejeitados)
            pontuar(conceitos, rejeitados, pesos_r)
            batem = [d for d in sorted(rejeitados, key=lambda x: -x.pontos)
                     if d.pontos > 0][:3]
            if batem:
                for d in batem:
                    w(f"- `{d.relativo}` — {len(d.cobertos)} conceito(s) em comum: "
                      + ", ".join(f"`{t}`" for t in d.cobertos[:6]))
                w("")
                w("**Não recuse sozinho.** Mostre a decisão antiga — o que foi")
                w("rejeitado, quando, por quem, por quê — e pergunte se ainda vale.")
            else:
                w("Nenhuma decisão antiga bate com estes conceitos.")
        else:
            w(f"`{fora}` está vazio.")
    else:
        w("O projeto não declara `docs.fora_de_escopo`. Sem esse registro, um")
        w("pedido já recusado volta e é re-analisado do zero, toda vez.")
    w("")

    w("## O que fazer com isto")
    w("")
    w("| Sinal | Leitura |")
    w("| --- | --- |")
    w("| Atividade com o mesmo id | retome, não reabra |")
    w("| SDD com aderência alta e **zero** conceitos novos | provavelmente já feito — confirme e encerre |")
    w("| SDD com aderência alta e poucos conceitos novos | **complemento**: atualize aquela SDD, escopo é o delta |")
    w("| SDD com aderência baixa | assunto novo, siga a trilha inteira |")
    w("| Bate na memória de rejeição | pergunte antes de qualquer coisa |")
    w("")
    w("Nada aqui é conclusão. A varredura acha palavra; só a leitura acha")
    w("comportamento — e o produto pode ter isto com outro nome, que nenhuma")
    w("busca por termo encontra.")

    texto = "\n".join(L)
    if args.saida:
        destino = Path(args.saida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        print(f"Escrito em {destino}")
    else:
        print(texto)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="already-exists", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demanda", required=True,
                   help="o texto da demanda, ou o caminho de um arquivo com ele")
    p.add_argument("--card", default=None)
    p.add_argument("--saida", default=None)
    args = p.parse_args(argv)
    try:
        return principal(args)
    except JaExisteError as exc:
        print(f"erro: {exc}", file=sys.stderr)
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
    sys.exit(main())
