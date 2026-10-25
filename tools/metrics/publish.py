#!/usr/bin/env python3
"""O que a métrica publica DENTRO do repositório, para quem não roda o fluxo.

Três artefatos, do mesmo `projeto.json`:

    docs/metricas.html   a página, um clique, com exportar
    docs/metricas.md     o mesmo em texto, que rende diff legível
    README.md            um bloco entre marcas, com o link

Isto é uma fronteira atravessada de propósito. O `install.sh` põe `.agents/`
em `.git/info/exclude` porque ferramental de IA não é entregável do cliente —
e a consequência é que o painel existe no disco de quem rodou e mais ninguém
o abre. Publicar move um RESUMO para dentro do versionamento, e por isso ele
não é o painel: é menos.

O que fica de fora, e por quê
-----------------------------

**Hora humana por atividade.** No `.agents/` ela é diagnóstico de quem rodou.
Num arquivo versionado, ao lado do nome da branch, ela vira nota de desempenho
individual — com duas pessoas no projeto dá para ler quem gastou mais hora por
card, sem que a métrica tenha sido desenhada para isso. O TOTAL do projeto fica;
a linha por atividade, não.

**O detalhe por agente e por step.** Ele responde "onde foi o custo", que é
pergunta de quem opera. Quem abre o README quer "como vai o projeto".

O que vai junto, sempre
-----------------------

As mesmas três ressalvas do relatório, porque é aqui que elas mais faltam: o
custo é **teto de tabela de API**, não fatura; **PF é declarado**, não medido; e
atividade sem prova de atribuição fica **fora do total, que é de menos e não de
zero**. Um número publicado é lido como verdade por quem não viu a coleta.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# `prazo_esta_aberto` vem do coletor em vez de ser reescrito aqui: a regra
# tem um recuo (registro anterior a 2.5.0 nao tem `prazo_aberto` e responde
# por `concluido_em`), e duas copias dela divergiriam no primeiro ajuste.
# Nao ha ciclo: `metrics` so' importa `publish` dentro do comando, em tempo
# de execucao, quando ja' esta inteiro em `sys.modules`.
from metrics import prazo_esta_aberto
from panel import PALETA

def marcas(nome: str) -> tuple[str, str]:
    """As marcas de um bloco no README, por nome.

    Existe porque o README do projeto pode receber mais de um bloco gerado — as
    métricas aqui, o manual no repositório do pacote — e dois blocos com a mesma
    marca fariam um sobrescrever o outro em silêncio.
    """
    return (f"<!-- elcamargo-ai-flow:{nome}:inicio -->",
            f"<!-- elcamargo-ai-flow:{nome}:fim -->")


INICIO, FIM = marcas("metricas")

# As ressalvas viajam com o número, nos três artefatos. Elas são a razão de o
# resumo publicado ser confiável — não um enfeite no rodapé.
RESSALVAS = [
    ("O custo é teto, não fatura",
     "Ele sai da tabela de preço da API. Quem roda por assinatura não paga "
     "isso — paga a assinatura, que é cobrada por tempo corrido."),
    ("Ponto de função é declarado, não medido",
     "Nenhuma ferramenta conta PF a partir de transcrito ou de diff. O número "
     "vem de quem contou, e a régua APF é multiplicação em cima dele."),
    ("A hora humana é um modelo, não um cronômetro",
     "Ela mede o intervalo entre o fim de uma resposta e a mensagem seguinte, "
     "com teto, mais um custo fixo de reentrada por interação."),
    ("A régua APF e o medido não são a mesma grandeza",
     "APF estima hora de EQUIPE. Hora humana é o mais próximo disso que se "
     "mede aqui; prazo é calendário, e dólar de API é outra moeda que não "
     "converte para hora."),
]


def esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Número em português: milhar com ponto, decimal com vírgula. Não é
# preciosismo — a página é lida por gestão, e `10.386` lido como dez mil e
# `10.3x` lido como dez vírgula três na mesma tela é como se lê errado.
def _dec(v, casas: int = 1) -> str:
    return (f"{float(v):,.{casas}f}"
            .replace(",", "@").replace(".", ",").replace("@", "."))


def _n(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _h(v) -> str:
    return _dec(v, 1) + " h"


def _conta(n: int, singular: str, plural: str = "") -> str:
    """`1 atividade`, `3 atividades`. Sem `atividade(s)` — isto vai a gestão."""
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def _conc(n: int, singular: str, plural: str) -> str:
    """Concordância de verbo e pronome. Companheiro de `_conta`, que só conta.

    Sem ele saía "1 atividade atribuída ficaram fora ... por não terem PF" —
    plural correto no substantivo e errado em todo o resto da frase.
    """
    return singular if n == 1 else plural


def _fator(apf: dict, chave: str, prod: str) -> str:
    v = (apf.get(chave) or {}).get(prod)
    return f"{_dec(v, 1)}x" if v else "—"


def _usd(v) -> str:
    return "US$ " + _dec(v, 2)


# ---------------------------------------------------------------------------
# Alcance e teto. Os dois existem no `projeto.json` desde a 2.32.0 e a 2.34.0,
# e nenhum dos dois chegava aqui — que é o único lugar que a gerência abre.
# Pedido em 12/09/2026 pelo `acme-backoffice`, depois de o README
# deles publicar US$ 90.628 contra um teto físico de US$ 26.604: a rodada
# declarava o estouro na TELA de quem coletou, e o arquivo versionado saía
# calado. Aviso que só aparece para quem rodou o comando não protege quem lê.


def _cobertura(p: dict) -> str:
    """`654 transcritos em 13 pastas de sessão`, ou `""` se a rodada não disse.

    Número sem alcance não é resultado. Duas rodadas do mesmo repositório
    saíam com fator 4 entre elas e nada na página dizia que uma tinha lido um
    terço do corpus da outra.
    """
    c = p.get("cobertura") or {}
    if not c.get("transcritos") and not c.get("pastas"):
        return ""
    return (f"{_n(c.get('transcritos', 0))} transcritos em "
            + _conta(c.get("pastas", 0), "pasta de sessão", "pastas de sessão"))


def _frase_teto(p: dict) -> str:
    """O teto físico do corpus, quando ele foi medido."""
    t = p.get("teto_do_corpus") or {}
    return _usd(t["custo_usd"]) if t.get("custo_usd") else ""




# ---------------------------------------------------------------------------
# O resumo em texto puro. É o que vai para o Teams, para o e-mail e para a
# área de transferência — e é a razão de ele ser CURTO: URL de `mailto:` e
# deep link de Teams têm limite prático de uns 2 mil caracteres, e o que passa
# disso é cortado pelo cliente sem avisar. Página inteira não cabe em link;
# resumo cabe.


def resumo_texto(p: dict) -> str:
    l = [f"Métricas — {p.get('projeto', 'projeto')} (coletado em {p.get('gerado_em', '?')})",
         _conta(p.get("atividades", 0), "atividade") + ", "
         + _conta(p.get("concluidas", 0), "concluída"),
         f"Custo em tabela de API: {_usd(p.get('custo_usd', 0))}  (teto, não fatura)",
         f"Hora humana: {_h(p.get('humano_h') or 0)} em "
         + _conta(p.get("interacoes", 0), "interação", "interações")]
    e = p.get("entrega") or {}
    l.append(f"Entrega: {_n(e.get('arquivos', 0))} arquivos, +{_n(e.get('insercoes', 0))} linhas, "
             f"{_n(e.get('commits', 0))} commits")
    apf = p.get("apf")
    if apf:
        l.append("")
        l.append(f"Régua APF: {apf['pf']} PF ({apf['origem']}) em "
                 + _conta(len(apf["atividades"]), "atividade"))
        for prod, h in apf["horas"].items():
            l.append(f"  produtividade {prod}: {_n(h)} h de equipe estimadas")
        l.append(f"  medido nessas atividades: {_h(apf['prazo_somado_h'])} de relógio, "
                 f"{_h(apf['humano_h'])} humanas, {_usd(apf['custo_usd'])} de API")
        for prod in apf["horas"]:
            fp = (apf.get("fator_prazo") or {}).get(prod)
            fh = (apf.get("fator_humano") or {}).get(prod)
            l.append(f"  a {prod} h/PF: {_dec(fp)}x o relógio, "
                     f"{_dec(fh)}x a hora humana" if fp and fh else
                     f"  a {prod} h/PF: fator indisponível")
    if p.get("nao_atribuidas"):
        l.append("")
        l.append("ATENÇÃO: " + _conta(len(p["nao_atribuidas"]), "atividade")
                 + " fora do total por falta de prova de atribuição — "
                 "o total é DE MENOS, não de zero.")
    cob = _cobertura(p)
    if cob:
        l.append("")
        l.append(f"Alcance da coleta: {cob}."
                 + (f" Teto do corpus lido: {_frase_teto(p)}." if _frase_teto(p) else ""))
    l.append("")
    l.append("Ressalvas: custo é teto de tabela de API, não fatura. PF é declarado, "
             "não medido. APF estima hora de equipe; hora humana é o medido mais próximo.")
    sobre = p.get("sobre_atribuicao")
    if sobre:
        # Na frente de tudo, e não no rodapé: este resumo é colado em conversa,
        # e o que se cola é o começo.
        l.insert(1, "ATENÇÃO — O TOTAL ABAIXO ESTÁ INFLADO: a soma por atividade ("
                 + _usd(sobre["soma_atribuida_usd"]) + ") passa o custo de TUDO que foi "
                 "lido (" + _usd(sobre["teto_do_corpus_usd"]) + ", "
                 + _dec(sobre["vezes"], 2) + "x). Há turno contado mais de uma vez; "
                 "não cite o total.")
    return "\n".join(l)


# ---------------------------------------------------------------------------
# Markdown


def gerar_markdown(p: dict) -> str:
    l = [f"# Métricas — {p.get('projeto', 'projeto')}", "",
         "Geradas pelo Elcamargo AI Flow a partir de "
         + _conta(p.get("atividades", 0), "atividade") + " conduzida"
         + ("" if p.get("atividades", 0) == 1 else "s") + " pelo fluxo, "
         + _conta(p.get("concluidas", 0), "concluída") + ".",
         f"Coletado em **{p.get('gerado_em', '?')}**.", "",
         "A mesma coisa como **página**, com exportar para PDF, Teams e e-mail, "
         "está em\n[`metricas.html`](metricas.html) — o navegador de repositório "
         "mostra HTML como código,\nentão baixe o arquivo e abra, ou sirva a pasta.", ""]
    sobre = p.get("sobre_atribuicao")
    if sobre:
        # Antes do primeiro número, e não depois da tabela. Quem abre este
        # arquivo lê o custo e fecha; ressalva embaixo do total chega tarde.
        l += ["> **O total abaixo está inflado — não o cite.**",
              "> A soma por atividade (" + _usd(sobre["soma_atribuida_usd"])
              + ") passa o custo de **tudo o que foi lido** ("
              + _usd(sobre["teto_do_corpus_usd"]) + "), em "
              + _dec(sobre["vezes"], 2) + "x.\n> O teto do corpus não depende de "
              "atribuição: nenhuma soma por atividade pode passar\n> dele, então há turno "
              "contado mais de uma vez. Os pares que dividem branch e\n> janela estão em "
              "`sobreposicoes`, no `projeto.json`.", ""]
    l += ["## O projeto", "", "| | |", "| --- | --- |",
         f"| atividades | {p.get('atividades', 0)}, "
         + _conta(p.get("concluidas", 0), "concluída") + " |",
         f"| custo em tabela de API | {_usd(p.get('custo_usd', 0))} |",
         f"| hora humana, no total | {_h(p.get('humano_h') or 0)} |",
         f"| interações humanas | {_n(p.get('interacoes', 0))} |",
         f"| turnos de assistente | {_n(p.get('turnos', 0))} |"]
    e = p.get("entrega") or {}
    l.append(f"| entrega | {_n(e.get('arquivos', 0))} arquivos, +{_n(e.get('insercoes', 0))} "
             f"−{_n(e.get('remocoes', 0))}, {_n(e.get('commits', 0))} commits |")
    # O alcance ao lado do total, sempre — inclusive quando está tudo certo.
    # Ele é o que permite comparar duas publicações e saber se a diferença é
    # trabalho novo ou corpus diferente.
    cob = _cobertura(p)
    if cob:
        l.append(f"| alcance da coleta | {cob} |")
    if _frase_teto(p):
        l.append(f"| teto do corpus lido | {_frase_teto(p)} |")
    l.append("")
    l.append("> A hora humana aparece só como **total do projeto**. Por atividade ela "
             "fica no\n> painel local: num arquivo versionado, ao lado do nome da branch, "
             "ela vira\n> nota de desempenho individual — e não foi desenhada para isso.")
    l.append("")

    apf = p.get("apf")
    if apf:
        l += ["## A régua APF, ao lado do medido", "",
              f"**{apf['pf']} pontos de função** ({apf['origem']}), somados nas "
              + _conta(len(apf["atividades"]), "atividade")
              + " que têm PF **e** prova de atribuição.", ""]
        prods = list(apf["horas"])
        l += ["| | " + " | ".join(f"produtividade {x}" for x in prods) + " |",
              "| --- | " + " | ".join("---:" for _ in prods) + " |",
              "| **estimativa APF** | "
              + " | ".join(f"{_n(apf['horas'][x])} h" for x in prods) + " |",
              f"| ÷ prazo de relógio ({_h(apf['prazo_somado_h'])}) | "
              + " | ".join(_fator(apf, "fator_prazo", x) for x in prods) + " |",
              f"| ÷ hora humana ({_h(apf['humano_h'])}) | "
              + " | ".join(_fator(apf, "fator_humano", x) for x in prods) + " |",
              "",
              "**Os dois fatores dizem coisas diferentes, e é por isso que os dois "
              "estão aqui.**\nO de relógio compara com o tempo corrido da atividade; "
              "o de hora humana, só\ncom o tempo em que uma pessoa esteve na frente da "
              "tela. O segundo é sempre\nmaior, e sozinho ele é o tipo de número que se "
              "repete numa reunião e cai na\nprimeira pergunta — porque enquanto a "
              "pessoa não estava lá, a máquina estava,\ne ela custou "
              f"{_usd(apf['custo_usd'])} de tabela de API nestas mesmas atividades.",
              "",
              "Nenhum dos dois é a grandeza da APF, que estima hora de **equipe**. São "
              "razões\nentre uma **estimativa** e uma **medida** — não são produtividade "
              "aferida.", ""]
        if apf.get("fora"):
            n = len(apf["fora"])
            l += ["> **Esta conta não cobre o projeto inteiro.** "
                  + _conta(n, "atividade atribuída", "atividades atribuídas") + " "
                  + _conc(n, "ficou", "ficaram") + " de fora por não "
                  + _conc(n, "ter", "terem") + " PF\n> declarado: `"
                  + "`, `".join(apf["fora"]) + "`. Somar o PF de umas com a hora de "
                  "outras\n> inflaria o fator, e é a direção que este coletor não pode "
                  "errar.", ""]
        if apf.get("em_andamento"):
            l += ["> **" + _conta(len(apf["em_andamento"]), "delas ainda está",
                                "delas ainda estão")
                  + " em andamento** — a hora medida ainda cresce, e\n> o fator acima vai "
                  "cair. Ele é retrato, não resultado.", ""]

    l += ["## As atividades", "",
          "| Atividade | Step | Status | US$ (teto) | Prazo | Entrega |",
          "| --- | --- | --- | ---: | ---: | ---: |"]
    for a in p.get("lista", []):
        ident = f"`{a.get('id', '?')}`"
        titulo = (a.get("titulo") or "").strip()
        rotulo = f"{ident} {titulo}" if titulo else ident
        if a.get("atribuicao") == "sem-prova":
            # Sem número, de propósito. Zero formatado se lê como medição.
            l.append(f"| {rotulo} | — | não atribuída | — | — | — |")
            continue
        ent = a.get("entrega") or {}
        marca = "+" if prazo_esta_aberto(a) else ""
        l.append(f"| {rotulo} | {a.get('step', '—')} · {a.get('trilha', '')} | "
                 f"{a.get('status', '?')} | {_dec(a.get('custo_usd') or 0, 2)} | "
                 f"{_h(a.get('prazo_h') or 0)}{marca} | "
                 f"{_n(ent.get('arquivos', 0))} arq, +{_n(ent.get('insercoes', 0))} |")
    l.append("")
    if any(prazo_esta_aberto(a) for a in p.get("lista", [])
           if a.get("atribuicao") != "sem-prova"):
        l += ["`+` marca prazo **ainda aberto**: ele vai do primeiro registro até agora, "
              "não\naté uma entrega, e vai crescer.", ""]
    if p.get("nao_atribuidas"):
        n = len(p["nao_atribuidas"])
        l += ["> **O total é de menos, não de zero.** " + _conta(n, "atividade") + " "
              + _conc(n, "ficou", "ficaram") + " fora\n> por falta de prova de "
              "atribuição: `" + "`, `".join(p["nao_atribuidas"]) + "`. "
              + _conc(n, "Ela aparece", "Elas aparecem") + " sem\n> número de propósito — "
              "não " + _conc(n, "custou", "custaram") + " zero; não se sabe de quem foi o "
              "que houve\n> " + _conc(n, "nela", "nelas") + ".", ""]
    sob = p.get("sobreposicoes") or []
    if sob:
        soma = sum(float(s.get("custo_contado_duas_vezes_usd") or 0) for s in sob)
        l += ["> **O total soma trabalho duas vezes.** "
              + _conta(len(sob), "par", "pares") + " de atividades dividem branch\n> e janela, e o transcrito não diz de qual delas é cada "
              f"turno — até {_usd(soma)}\n> entram duas vezes.", ""]

    l += ["## O que estes números NÃO provam", ""]
    for titulo, corpo in RESSALVAS:
        l.append(f"**{titulo}.** {corpo}")
        l.append("")
    par = p.get("parametros") or {}
    l += ["---", "",
          f"Hora humana modelada com teto de {par.get('teto_leitura_min', '?')} min por "
          f"interação mais\n{par.get('reentrada_min', '?')} min de reentrada. "
          "Gerado por `metrics.py publicar` — não edite à mão:\na próxima coleta "
          "sobrescreve.", ""]
    return "\n".join(l)


# ---------------------------------------------------------------------------
# HTML

ESTILO = """*{box-sizing:border-box}
body{margin:0;background:var(--papel);color:var(--tinta);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,sans-serif;font-size:15px;
  line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2{font-family:Spectral,Georgia,serif;font-weight:600;margin:0;line-height:1.2;text-wrap:balance}
h1{font-size:clamp(1.6rem,3.6vw,2.3rem);letter-spacing:-.02em}
h2{font-size:1.25rem;letter-spacing:-.01em;margin:34px 0 4px}
p{margin:0}
.mono,code{font-family:"IBM Plex Mono",ui-monospace,monospace}
code{background:var(--superficie-2);border:1px solid var(--linha);border-radius:3px;
  padding:.08em .34em;font-size:.86em}
.rotulo{font-family:"IBM Plex Mono",monospace;font-size:.68rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.13em;color:var(--tinta-fraca)}
.topo{border-bottom:1px solid var(--linha);background:var(--superficie)}
.topo-in{max-width:1060px;margin:0 auto;padding:16px 24px;display:flex;flex-wrap:wrap;
  gap:10px 22px;align-items:baseline}
.marca{font-family:Spectral,serif;font-weight:600;font-size:1rem}
.topo .rotulo:nth-of-type(2){margin-left:auto}
.folha{max-width:1060px;margin:0 auto;padding:26px 24px 80px}
.exportar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:20px 0 4px;
  padding:12px 14px;border:1px solid var(--linha);background:var(--superficie);
  box-shadow:var(--sombra)}
.exportar .rotulo{margin-right:6px}
.exportar button,.exportar a{font:inherit;font-size:.84rem;font-weight:500;cursor:pointer;
  border:1px solid var(--linha-forte);background:var(--superficie-2);color:var(--tinta);
  padding:6px 13px;border-radius:4px;text-decoration:none;display:inline-flex;gap:.4em;
  align-items:center}
.exportar button:hover,.exportar a:hover,.exportar button:focus-visible,
.exportar a:focus-visible{border-color:var(--acento);color:var(--acento);
  background:var(--acento-lavado)}
#aviso-copia{font-size:.8rem;color:var(--ok);margin-left:4px}
.placar{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:1px;
  background:var(--linha);border:1px solid var(--linha);margin:18px 0 8px;box-shadow:var(--sombra)}
.cel{background:var(--superficie);padding:16px 16px 14px}
.cel .n{font-family:"IBM Plex Mono",monospace;font-weight:500;font-size:1.7rem;line-height:1.1;
  letter-spacing:-.03em;font-variant-numeric:tabular-nums;display:block;margin-bottom:4px}
.cel .n .un{font-size:.46em;color:var(--tinta-fraca);margin-left:.2em;letter-spacing:0}
.cel .lg{font-size:.79rem;color:var(--tinta-fraca);line-height:1.4}
.cel.forte .n{color:var(--acento)}
.rolagem{overflow-x:auto;border:1px solid var(--linha);background:var(--superficie);
  box-shadow:var(--sombra);margin:14px 0 10px}
table{border-collapse:collapse;width:100%;font-size:.87rem}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--linha);vertical-align:middle}
thead th{font-family:"IBM Plex Mono",monospace;font-size:.65rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.1em;color:var(--tinta-fraca);
  background:var(--superficie-2);white-space:nowrap;border-bottom:1px solid var(--linha-forte)}
tbody tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right;font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap}
tr.regua td{background:var(--acento-lavado)}
tr.regua td.n{color:var(--acento);font-weight:600}
.sem td{color:var(--tinta-fraca);font-style:italic}
.aviso{border:1px solid var(--parcial);background:var(--parcial-lavado);padding:14px 16px;
  margin:14px 0;font-size:.88rem;color:var(--tinta-media)}
.aviso .rotulo{color:var(--parcial);display:block;margin-bottom:6px}
.aviso.grave{border-color:var(--falhou);background:var(--falhou-lavado)}
.aviso.grave .rotulo{color:var(--falhou)}
.nota{border-left:2px solid var(--linha-forte);padding:2px 0 2px 14px;font-size:.87rem;
  color:var(--tinta-media);max-width:76ch;margin:12px 0}
.ressalvas{display:grid;gap:1px;background:var(--linha);border:1px solid var(--linha);
  margin:16px 0;box-shadow:var(--sombra)}
.ressalvas div{background:var(--superficie);padding:14px 16px;font-size:.88rem;
  color:var(--tinta-media)}
.ressalvas strong{color:var(--tinta);display:block;margin-bottom:3px;font-weight:600}
.rodape{margin-top:44px;padding-top:20px;border-top:1px solid var(--linha);font-size:.82rem;
  color:var(--tinta-fraca);display:flex;flex-direction:column;gap:6px}
@media (max-width:640px){.folha{padding:20px 16px 60px}}

/* IMPRESSAO / PDF. O navegador salva em PDF pelo mesmo caminho da impressao,
   entao o PDF sai daqui. Fundo navy em papel gasta tinta e varios navegadores
   descartam a cor de fundo por padrao -- o que deixaria tinta clara sobre
   branco, ilegivel. Entao no papel a pagina inverte de proposito. */
@media print{
  :root{color-scheme:light}
  body{background:#fff;color:#101820;font-size:11pt}
  .topo{background:#fff;border-bottom:1px solid #9AA8B4}
  .exportar{display:none}
  .cel,.rolagem,.ressalvas div,thead th{background:#fff}
  /* O fundo do `.placar` e' a LINHA entre as celulas -- ele aparece pelo vao
     de 1px e, quando o numero de celulas nao fecha a grade, pela celula vazia
     que sobra. No papel isso vira um retangulo preto. Fundo branco no
     recipiente e contorno em cada celula desenham a mesma grade sem o vao. */
  .placar{background:#fff;border-color:#9AA8B4}
  .cel{outline:1px solid #9AA8B4}
  /* `code` herdava o fundo escuro do tema e ficava tinta escura sobre navy --
     ilegivel, e e' onde estao os nomes de comando. */
  code{background:#F1F5F8;border-color:#9AA8B4;color:#101820}
  .cel .n,.cel.forte .n,tr.regua td.n{color:#101820}
  .cel .lg,.rotulo,.rodape,.nota,.ressalvas div{color:#3C4A57}
  .placar,.rolagem,.ressalvas,.ressalvas div,th,td{border-color:#9AA8B4;box-shadow:none}
  tr.regua td{background:#EAF6FA}
  .aviso{border-color:#8A6D1F;background:#FDF6E3;color:#3C4A57}
  .aviso .rotulo{color:#8A6D1F}
  /* `.aviso.grave` e' mais especifico que `.aviso` e sobrepunha a regra acima:
     no papel ele saia com fundo bordo escuro e tinta cinza escura por cima --
     ilegivel. E o que ele carrega e' justamente a ressalva mais importante da
     pagina, a de que o total e' DE MENOS e nao de zero. */
  .aviso.grave{border-color:#B3261E;background:#FDECEC;color:#3C4A57}
  .aviso.grave .rotulo{color:#B3261E}
  thead th{color:#3C4A57}
  h2,table,.ressalvas{break-inside:avoid}
}
"""


def _placar(itens: list[tuple]) -> str:
    cels = []
    for valor, unidade, legenda, forte in itens:
        un = f'<span class="un">{esc(unidade)}</span>' if unidade else ""
        cels.append(f'<div class="cel{" forte" if forte else ""}">'
                    f'<span class="n">{esc(valor)}{un}</span>'
                    f'<span class="lg">{esc(legenda)}</span></div>')
    return '<div class="placar">' + "".join(cels) + "</div>"


def gerar_html(p: dict) -> str:
    nome = p.get("projeto", "projeto")
    e = p.get("entrega") or {}
    # Sem `<meta charset>` o navegador cai no encoding do sistema e a página
    # abre "MÃ©tricas". Ela vai ser aberta de um repositório, de um anexo e de
    # um servidor que não manda charset no cabeçalho — declarar é obrigatório.
    h = ['<!doctype html>', '<html lang="pt-BR">', "<head>",
         '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f"<title>Métricas do {esc(nome)}</title>",
         '<link rel="preconnect" href="https://fonts.googleapis.com">',
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Spectral:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&'
         'family=IBM+Plex+Mono:wght@400;500;600&display=swap">',
         "<style>", PALETA, ESTILO, "</style>", "</head>", "<body>",
         '<header class="topo"><div class="topo-in">',
         '<span class="marca">Elcamargo AI&nbsp;Flow</span>',
         f'<span class="rotulo">Métricas · {esc(nome)}</span>',
         f'<span class="rotulo">coletado em {esc(p.get("gerado_em", "?"))}</span>',
         "</div></header>", '<div class="folha">',
         f"<h1>{esc(nome)}</h1>",
         f'<p class="nota" style="margin-top:10px">{_conta(p.get("atividades", 0), "atividade")} '
         f'conduzida{"" if p.get("atividades", 0) == 1 else "s"} pelo fluxo, '
         f'{_conta(p.get("concluidas", 0), "concluída")}. Esta página é '
         'gerada pelo <code>metrics.py publicar</code> e vive no repositório — o número '
         'é o da última coleta, não o de agora.</p>',
         # A barra de exportar vem ANTES do placar de propósito: quem abre a
         # página para levar o número a uma reunião não deve ter que procurar.
         '<div class="exportar" role="group" aria-label="Exportar">',
         '<span class="rotulo">Exportar</span>',
         '<button type="button" onclick="window.print()">PDF / imprimir</button>',
         '<button type="button" id="b-teams">Teams</button>',
         '<button type="button" id="b-email">E-mail</button>',
         '<button type="button" id="b-copiar">Copiar resumo</button>',
         '<span id="aviso-copia" role="status"></span>',
         "</div>",
         '<p class="nota" style="margin-top:8px">Teams e e-mail abrem já com o '
         '<strong>resumo</strong> escrito — não com a página inteira: link não '
         'carrega mais que uns dois mil caracteres, e o que passa disso o cliente '
         'corta sem avisar. Para mandar tudo, use o PDF ou o link deste arquivo no '
         'repositório.</p>']

    sobre = p.get("sobre_atribuicao")
    if sobre:
        # Acima do placar. Abaixo dele o leitor já levou o número embora.
        h.append('<div class="aviso grave"><span class="rotulo">O total abaixo está '
                 'inflado — não o cite</span>A soma por atividade ('
                 + esc(_usd(sobre["soma_atribuida_usd"]))
                 + ') passa o custo de <strong>tudo o que foi lido</strong> ('
                 + esc(_usd(sobre["teto_do_corpus_usd"])) + '), em '
                 + esc(_dec(sobre["vezes"], 2)) + 'x. O teto do corpus não depende de '
                 'atribuição: nenhuma soma por atividade pode passar dele, então há turno '
                 'contado mais de uma vez.</div>')

    h.append(_placar([
        (_n(p.get("atividades", 0)), "",
         "atividades · " + _conta(p.get("concluidas", 0), "concluída"), 0),
        (_usd(p.get("custo_usd", 0)), "", "custo em tabela de API — teto, não fatura", 1),
        (_dec(p.get("humano_h") or 0), "h",
         "hora humana no total, em "
         + _conta(p.get("interacoes", 0), "interação", "interações"), 0),
        (_n(e.get("insercoes", 0)), "",
         "linhas entregues em " + _conta(e.get("arquivos", 0), "arquivo"), 1),
        (_n(p.get("turnos", 0)), "", "turnos de assistente", 0),
    ]))
    cob = _cobertura(p)
    if cob:
        h.append('<p class="nota"><strong>Alcance da coleta:</strong> ' + esc(cob)
                 + (f'. Teto do corpus lido: {esc(_frase_teto(p))} — nenhuma soma por '
                    'atividade pode passar dele.' if _frase_teto(p) else '.')
                 + '</p>')
    h.append('<p class="nota">A hora humana aparece só como <strong>total do projeto</strong>. '
             'Por atividade ela fica no painel local: num arquivo versionado, ao lado do nome '
             'da branch, ela vira nota de desempenho individual — e não foi desenhada para '
             'isso.</p>')

    apf = p.get("apf")
    if apf:
        h.append("<h2>A régua APF, ao lado do medido</h2>")
        h.append(f'<p class="nota"><strong>{apf["pf"]} pontos de função</strong> '
                 f'({esc(apf["origem"])}), somados nas {_conta(len(apf["atividades"]), "atividade")} '
                 'que têm PF <strong>e</strong> prova de atribuição. As duas exigências são '
                 'a mesma exigência: estimativa de um conjunto sobre medida de outro sempre '
                 'erra para o lado que agrada.</p>')
        prods = list(apf["horas"])
        cabeca = "".join(f'<th class="n">produtividade {esc(x)}</th>' for x in prods)
        linhas = [f'<div class="rolagem"><table><thead><tr><th></th>{cabeca}</tr></thead>'
                  '<tbody>',
                  '<tr class="regua"><td><strong>estimativa APF</strong></td>'
                  + "".join(f'<td class="n">{_n(apf["horas"][x])} h</td>' for x in prods)
                  + "</tr>",
                  f'<tr><td>÷ prazo de relógio ({_h(apf["prazo_somado_h"])})</td>'
                  + "".join(f'<td class="n">{_fator(apf, "fator_prazo", x)}</td>'
                            for x in prods) + "</tr>",
                  f'<tr><td>÷ hora humana ({_h(apf["humano_h"])})</td>'
                  + "".join(f'<td class="n">{_fator(apf, "fator_humano", x)}</td>'
                            for x in prods) + "</tr>",
                  "</tbody></table></div>"]
        h.append("".join(linhas))
        h.append('<p class="nota"><strong>Os dois fatores dizem coisas diferentes, e é por '
                 'isso que os dois estão aqui.</strong> O de relógio compara com o tempo '
                 'corrido da atividade; o de hora humana, só com o tempo em que uma pessoa '
                 'esteve na frente da tela. O segundo é sempre maior, e sozinho ele é o tipo '
                 'de número que se repete numa reunião e cai na primeira pergunta — porque '
                 'enquanto a pessoa não estava lá, a máquina estava, e ela custou '
                 f'{esc(_usd(apf["custo_usd"]))} de tabela de API nestas mesmas '
                 'atividades.</p>')
        h.append('<p class="nota">Nenhum dos dois é a grandeza da APF, que estima hora de '
                 '<strong>equipe</strong>. São razões entre uma <strong>estimativa</strong> e '
                 'uma <strong>medida</strong> — não são produtividade aferida.</p>')
        if apf.get("fora"):
            n = len(apf["fora"])
            h.append('<div class="aviso"><span class="rotulo">Esta conta não cobre o projeto '
                     'inteiro</span>'
                     + _conta(n, "atividade atribuída", "atividades atribuídas") + " "
                     + _conc(n, "ficou", "ficaram") + ' de fora por não '
                     + _conc(n, "ter", "terem") + ' PF declarado: <code>'
                     + esc(", ".join(apf["fora"])) + '</code>.</div>')
        if apf.get("em_andamento"):
            n = len(apf["em_andamento"])
            h.append('<div class="aviso"><span class="rotulo">Retrato, não resultado</span>'
                     + _conta(n, "atividade") + ' desta conta ainda '
                     + _conc(n, "está", "estão")
                     + ' em andamento: a hora medida continua crescendo, e o fator acima '
                     'vai cair.</div>')
    else:
        h.append("<h2>A régua APF</h2>")
        h.append('<p class="nota">Indisponível: nenhuma atividade atribuída declarou ponto de '
                 'função. A ferramenta <strong>não mede</strong> PF — ela lê o que foi '
                 'declarado no cabeçalho da atividade. Sem número, a régua fica ausente em '
                 'vez de sair errada.</p>')

    if p.get("nao_atribuidas"):
        n = len(p["nao_atribuidas"])
        h.append('<div class="aviso grave"><span class="rotulo">O total acima é de menos, '
                 'não de zero</span>' + _conta(n, "atividade") + " "
                 + _conc(n, "ficou", "ficaram")
                 + ' fora por falta de prova de atribuição: <code>'
                 + esc(", ".join(p["nao_atribuidas"])) + '</code>. '
                 + _conc(n, "Ela aparece", "Elas aparecem")
                 + ' na tabela sem número de propósito — zero formatado se lê como medição, '
                 'e o que houve '
                 + _conc(n, "nela", "nelas") + ' não foi zero: não se sabe de quem foi.</div>')
    sob = p.get("sobreposicoes") or []
    if sob:
        soma = sum(float(s.get("custo_contado_duas_vezes_usd") or 0) for s in sob)
        pares = "".join(f"<li><code>{esc(' + '.join(s.get('atividades', [])))}</code> em "
                        f"<code>{esc(s.get('branch', ''))}</code></li>" for s in sob)
        h.append('<div class="aviso grave"><span class="rotulo">O total acima soma trabalho '
                 'duas vezes</span>' + _conta(len(sob), "par", "pares")
                 + ' de atividades dividem branch e janela, e o transcrito não diz de qual '
                 'delas é cada turno — até '
                 f'{_usd(soma)} entram duas vezes.<ul style="margin:8px 0 0;padding-left:1.1em">'
                 + pares + "</ul></div>")

    h.append("<h2>As atividades</h2>")
    corpo = []
    aberta = False
    for a in p.get("lista", []):
        titulo = (a.get("titulo") or "").strip()
        celula = (f'<strong>{esc(a.get("id", "?"))}</strong>'
                  + (f'<br><span style="color:var(--tinta-fraca);font-size:.9em">'
                     f'{esc(titulo[:70])}</span>' if titulo else ""))
        if a.get("atribuicao") == "sem-prova":
            corpo.append(f'<tr class="sem"><td>{celula}</td><td colspan="5">não atribuída — '
                         f'{esc(a.get("motivo_atribuicao", ""))}</td></tr>')
            continue
        ent = a.get("entrega") or {}
        marca = ""
        if prazo_esta_aberto(a):
            aberta = True
            marca = "+"
        corpo.append(
            f'<tr><td>{celula}</td>'
            f'<td class="mono" style="font-size:.82rem">{esc(a.get("step", "—"))} · '
            f'{esc(a.get("trilha", ""))}</td>'
            f'<td>{esc(a.get("status", "?"))}</td>'
            f'<td class="n">{_dec(a.get("custo_usd") or 0, 2)}</td>'
            f'<td class="n">{_h(a.get("prazo_h") or 0)}{marca}</td>'
            f'<td class="n">{_n(ent.get("arquivos", 0))} arq · '
            f'+{_n(ent.get("insercoes", 0))}</td></tr>')
    h.append('<div class="rolagem"><table><thead><tr><th>Atividade</th><th>Step</th>'
             '<th>Status</th><th class="n">US$ (teto)</th><th class="n">Prazo</th>'
             '<th class="n">Entrega</th></tr></thead><tbody>'
             + ("".join(corpo) or '<tr><td colspan="6">nenhuma atividade coletada</td></tr>')
             + "</tbody></table></div>")
    if aberta:
        h.append('<p class="nota"><code>+</code> marca prazo <strong>ainda aberto</strong>: '
                 'ele vai do primeiro registro até agora, não até uma entrega, e vai '
                 'crescer.</p>')

    h.append("<h2>O que estes números NÃO provam</h2>")
    h.append('<div class="ressalvas">'
             + "".join(f"<div><strong>{esc(t)}</strong>{esc(c)}</div>" for t, c in RESSALVAS)
             + "</div>")

    par = p.get("parametros") or {}
    h.append(f'<div class="rodape"><span>Hora humana modelada com teto de '
             f'{esc(par.get("teto_leitura_min", "?"))} min por interação mais '
             f'{esc(par.get("reentrada_min", "?"))} min de reentrada.</span>'
             '<span>Gerado por <code>metrics.py publicar</code>, do Elcamargo AI Flow. '
             'Não edite à mão: a próxima coleta sobrescreve.</span></div>')
    h.append("</div>")

    # O resumo entra como JSON para não escapar aspas à mão dentro do script.
    h.append("<script>\nconst RESUMO = " + json.dumps(resumo_texto(p), ensure_ascii=False)
             + ";\n" + SCRIPT + "\n</script>")
    h += ["</body>", "</html>"]
    return "\n".join(h) + "\n"


SCRIPT = """function copiar(texto){
  // `navigator.clipboard` exige contexto seguro. `file://` conta na maior
  // parte dos navegadores, mas nao em todos -- e esta pagina EXISTE para ser
  // aberta de um arquivo. Entao o caminho antigo fica como rede de seguranca,
  // em vez de a copia falhar em silencio para quem abriu do jeito previsto.
  if(navigator.clipboard && window.isSecureContext){
    return navigator.clipboard.writeText(texto);
  }
  return new Promise(function(ok, erro){
    try{
      const c = document.createElement("textarea");
      c.value = texto; c.setAttribute("readonly", "");
      c.style.position = "fixed"; c.style.opacity = "0";
      document.body.appendChild(c); c.select();
      const deu = document.execCommand("copy");
      document.body.removeChild(c);
      deu ? ok() : erro(new Error("cópia recusada"));
    }catch(e){ erro(e); }
  });
}
function dizer(texto, cor){
  const el = document.getElementById("aviso-copia");
  el.textContent = texto;
  el.style.color = cor || "var(--ok)";
  setTimeout(function(){ el.textContent = ""; }, 4000);
}
document.getElementById("b-copiar").onclick = function(){
  copiar(RESUMO).then(function(){ dizer("resumo copiado"); },
                      function(){ dizer("não consegui copiar — selecione e copie a página",
                                        "var(--parcial)"); });
};
document.getElementById("b-email").onclick = function(){
  const assunto = document.title;
  location.href = "mailto:?subject=" + encodeURIComponent(assunto) +
                  "&body=" + encodeURIComponent(RESUMO);
  // A copia vai junto: se o cliente de e-mail cortar o corpo, o texto inteiro
  // ja esta na area de transferencia e um Ctrl+V resolve.
  copiar(RESUMO).then(function(){ dizer("resumo também copiado"); }, function(){});
};
document.getElementById("b-teams").onclick = function(){
  // Deep link do Teams: abre a conversa com a mensagem escrita, e quem manda
  // escolhe o destinatario. Nao ha como POSTAR daqui sem credencial, e uma
  // pagina versionada num repositorio nao e' lugar de guardar uma.
  window.open("https://teams.microsoft.com/l/chat/0/0?message=" +
              encodeURIComponent(RESUMO), "_blank", "noopener");
  copiar(RESUMO).then(function(){ dizer("resumo também copiado"); }, function(){});
};"""


# ---------------------------------------------------------------------------
# README


def bloco_readme(p: dict, html_rel: str, md_rel: str) -> str:
    """O bloco entre marcas. Curto de propósito: é o resumo do resumo.

    Ele não repete a tabela — repetir produziria dois lugares para atualizar e
    um deles ficaria velho. Ele dá o número que se olha de relance e o link
    para onde está o resto.

    **O link de um clique é o MARKDOWN, e não a página.** GitHub e Azure Repos
    renderizam `.md` no próprio navegador de repositório; `.html` eles mostram
    como código-fonte. Pôr a página em primeiro lugar prometeria um clique que
    não acontece — a página é para baixar, anexar, imprimir ou servir.
    """
    apf = p.get("apf")
    l = [INICIO, "",
         "## Métricas do fluxo", "",
         f"**[Ver o andamento do projeto]({md_rel})** · "
         f"[página com exportar]({html_rel}) · coletado em {p.get('gerado_em', '?')}", ""]
    sobre = p.get("sobre_atribuicao")
    if sobre:
        l += ["> **O total abaixo está inflado — não o cite.** A soma por atividade ("
              + _usd(sobre["soma_atribuida_usd"]) + ") passa o custo de tudo o que foi "
              "lido (" + _usd(sobre["teto_do_corpus_usd"]) + "), em "
              + _dec(sobre["vezes"], 2) + "x: há turno contado mais de uma vez.", ""]
    l += ["| | |", "| --- | --- |",
         f"| atividades | {p.get('atividades', 0)}, "
         + _conta(p.get("concluidas", 0), "concluída") + " |",
         f"| custo em tabela de API | {_usd(p.get('custo_usd', 0))} |",
         f"| hora humana, no total | {_h(p.get('humano_h') or 0)} |"]
    if apf:
        faixa = sorted(int(v) for v in apf["horas"].values())
        l.append(f"| régua APF ({apf['pf']} PF) | {_n(faixa[0])} a {_n(faixa[-1])} h de "
                 f"equipe estimadas |")
    l.append("")
    l.append("<sub>O primeiro link abre aqui mesmo. A **página** só vira página depois de "
             "baixada ou servida — o navegador de repositório mostra HTML como código.</sub>")
    l.append("")
    cob = _cobertura(p)
    l.append("<sub>Custo é **teto de tabela de API**, não fatura. PF é **declarado**, não "
             "medido. Gerado pelo Elcamargo AI Flow."
             + (f" Coleta: {cob}." if cob else "") + "</sub>")
    if p.get("nao_atribuidas"):
        l.append("")
        l.append("<sub>⚠ " + _conta(len(p["nao_atribuidas"]), "atividade")
                 + " fora do total por falta de prova de atribuição — o total é "
                 "**de menos**, não de zero.</sub>")
    l += ["", FIM]
    return "\n".join(l)


def escrever_readme(readme: Path, bloco: str,
                    inicio: str = INICIO, fim: str = FIM) -> str:
    """Devolve o que aconteceu, em uma palavra: substituiu, acrescentou, criou.

    Substituir entre marcas é o caso normal. Acrescentar acontece uma vez, e é
    a única escrita deste pacote no README de um projeto que não é dele — por
    isso ela é relatada em vez de silenciosa.
    """
    if not readme.exists():
        readme.write_text(f"# {readme.parent.name}\n\n{bloco}\n", encoding="utf-8")
        return "criou"
    texto = readme.read_text(encoding="utf-8")
    if inicio in texto and fim in texto:
        padrao = re.compile(re.escape(inicio) + r".*?" + re.escape(fim), re.S)
        novo = padrao.sub(lambda _: bloco, texto, count=1)
        if novo != texto:
            readme.write_text(novo, encoding="utf-8")
        return "substituiu"
    readme.write_text(texto.rstrip("\n") + "\n\n" + bloco + "\n", encoding="utf-8")
    return "acrescentou"


# ---------------------------------------------------------------------------


def publicar(projeto: dict, raiz: Path, pasta: str = "docs",
             no_readme: bool = True) -> dict:
    destino = (raiz / pasta).resolve()
    destino.mkdir(parents=True, exist_ok=True)
    md = destino / "metricas.md"
    html = destino / "metricas.html"
    md.write_text(gerar_markdown(projeto), encoding="utf-8")
    html.write_text(gerar_html(projeto), encoding="utf-8")
    feito = {"markdown": md, "html": html, "readme": None, "readme_acao": ""}
    if no_readme:
        readme = raiz / "README.md"
        rel = lambda alvo: str(alvo.relative_to(raiz)).replace("\\", "/")  # noqa: E731
        feito["readme_acao"] = escrever_readme(
            readme, bloco_readme(projeto, rel(html), rel(md)))
        feito["readme"] = readme
    return feito
