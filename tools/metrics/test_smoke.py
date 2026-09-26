#!/usr/bin/env python3
"""Fumaça de metrics.py — e os quatro erros que ela já cometeu de verdade.

Cada bloco daqui existe por causa de um número errado que apareceu na tela, e
não por causa de um caso imaginado. Os quatro:

  1. filtrar por `gitBranch` cortou 23 das 41 interações humanas;
  2. `atualizado_em` como teto fez uma atividade parada engolir 8 mil turnos;
  3. raio simétrico em torno de cada prova inflou TODA atividade;
  4. prazo somando a cauda deu 40 h onde a entrega saiu em 26.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as M  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
T = T0


def em(minutos: float) -> datetime:
    return T0 + timedelta(minutes=minutos)


# ---------------------------------------------------------------------------
# Um projeto de mentira, com transcritos de mentira. Vale a montagem: os
# defeitos de ATRIBUIÇÃO não aparecem em função pura nenhuma — eles nascem do
# encontro entre o front-matter, o disco de sessões e o Git, e foi por não
# haver este andaime que o zero silencioso passou a 1.1.0 inteira.

TEMPORARIOS: list[Path] = []


class Args:
    def __init__(self, **kw):
        self.__dict__.setdefault("raiz", ".")
        self.__dict__.setdefault("atividade", None)
        self.__dict__.setdefault("silencioso", True)
        self.__dict__.setdefault("step", None)
        self.__dict__.setdefault("saida", None)
        self.__dict__.update(kw)


def utc(quando: datetime) -> str:
    return quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def hora_local(quando: datetime) -> str:
    """Como o `flow_state.py` grava: hora local, sem fuso escrito.

    Derivar do MESMO instante que os transcritos usam é o que mantém o teste
    honesto em qualquer fuso. Escrever `08:00:00` na mão passa em -03:00 e
    reprova em +14:00, e a janela nasceria três horas fora — que é o erro que
    o `janela_da_atividade` existe para não cometer.
    """
    return quando.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def reg_humano(quando, texto, pid=None, branch="", cwd="", sidechain=False):
    r = {"type": "user", "timestamp": utc(quando), "message": {"content": texto}}
    if pid:
        r["promptId"] = pid
    if branch:
        r["gitBranch"] = branch
    if cwd:
        r["cwd"] = cwd
    if sidechain:
        r["isSidechain"] = True
    return r


def reg_assistente(quando, entrada=0, saida=0, cache_r=0, cache_w=0,
                   perguntas=0, sidechain=False):
    conteudo = []
    if perguntas:
        conteudo.append({"type": "tool_use", "name": "AskUserQuestion",
                         "input": {"questions": [{"q": i} for i in range(perguntas)]}})
    r = {"type": "assistant", "timestamp": utc(quando),
         "message": {"usage": {"input_tokens": entrada, "output_tokens": saida,
                               "cache_read_input_tokens": cache_r,
                               "cache_creation_input_tokens": cache_w},
                     "content": conteudo}}
    if sidechain:
        r["isSidechain"] = True
    return r


def jsonl(caminho: Path, registros: list) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(json.dumps(r) for r in registros) + "\n",
                       encoding="utf-8")
    return caminho


def escrever_config(agents: Path, extra: str) -> None:
    (agents / "config.toml").write_text(
        '[projeto]\nnome = "repo-de-teste"\n\n' + extra, encoding="utf-8")
    M.C._cache.clear()   # o config guarda por (caminho, mtime); o teste manda


def cenario() -> tuple[Path, Path]:
    raiz = Path(tempfile.mkdtemp(prefix="metricas-")).resolve()
    TEMPORARIOS.append(raiz)
    agents = raiz / ".agents"
    (agents / "atividades").mkdir(parents=True)
    (raiz / "home").mkdir()
    os.environ["HOME"] = str(raiz / "home")
    # `Path.home()` le HOME no POSIX e USERPROFILE no Windows. Sem os dois,
    # o teste escreve no home de mentira e a metrica le o de verdade: tudo
    # zero, e zero se le como resultado.
    os.environ["USERPROFILE"] = str(raiz / "home")
    os.environ["ELCAMARGO_AGENTS_DIR"] = str(agents)
    escrever_config(agents, "")
    return raiz, agents


def atividade(agents: Path, ident: str, **campos) -> Path:
    corpo = "\n".join(f"{k}: {v}" for k, v in campos.items())
    alvo = agents / "atividades" / f"{ident}.md"
    alvo.write_text(f"---\nid: {ident}\n{corpo}\n---\n\n# {ident}\n",
                    encoding="utf-8")
    return alvo


def sessao(raiz: Path, nome: str, registros: list, sufixo: str = "") -> Path:
    base = Path(os.environ["HOME"]) / ".claude" / "projects"
    return jsonl(base / (M.slug_do_projeto(raiz) + sufixo) / f"{nome}.jsonl", registros)


def coletado(agents: Path, nome: str) -> dict:
    return json.loads((agents / "metrics" / f"{nome}.json").read_text(encoding="utf-8"))


def limpar(caminho: Path) -> None:
    shutil.rmtree(caminho, ignore_errors=True)


def rodar(fn, **kw) -> str:
    """A saída que a pessoa lê. É nela que o zero silencioso aparecia."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(Args(**kw))
    return buf.getvalue()


def linha_de(saida: str, agulha: str) -> str:
    return next((l for l in saida.splitlines() if agulha in l), "")


def main() -> int:
    ambiente = {k: os.environ.get(k)
                for k in ('HOME', 'ELCAMARGO_AGENTS_DIR')}
    print("\nPapel e step do subagente")
    ok(M.papel_do_agente("Você é o **step 3 · Analista de Sistema** do fluxo")
       == (3, "titular"), "titular sai do destaque em negrito")
    # A regressão: o prompt do titular do step 3 contém a palavra `auditoria`
    # na descrição do trabalho dele. Procurar auditor primeiro o classificava
    # errado, e o step 3 aparecia com zero titulares.
    ok(M.papel_do_agente(
        "Você é o **step 3 · Analista de Sistema**. Depois de escrever, "
        "dispare a auditoria de completude") == (3, "titular"),
       "e continua titular mesmo citando auditoria no corpo")
    ok(M.papel_do_agente("Auditor de completude do step 3 do fluxo")
       == (3, "auditor"), "auditor sem destaque vira auditor")
    ok(M.papel_do_agente("Atividade x, step 9 volta 1. Você é a frente de qualidade")
       == (9, "frente"), "frente de revisão vira frente")
    ok(M.papel_do_agente("Conserte os cinco alta")[1] == "dirigido",
       "correção sem step vira dirigida")

    print("\n`atualizado_em` não é teto — foi ele que inflou uma atividade parada")
    campos = {"criado_em": "2026-09-01 09:00:00",
              "atualizado_em": "2026-09-30 09:00:00"}
    _, fim = M.janela_da_atividade(campos)
    ok(fim is None, "sem `concluido_em`, não há teto declarado", str(fim))
    campos["concluido_em"] = "2026-09-02 09:00:00"
    _, fim = M.janela_da_atividade(campos)
    ok(fim is not None and fim.day == 2,
       "com `concluido_em`, o teto é ele — não o `atualizado_em` de 30/09", str(fim))

    print("\nProva de vínculo")
    ok(M.prova_de_vinculo({"gitBranch": "feat/x"}, "feat/x", "", "1"),
       "branch igual é prova")
    ok(M.prova_de_vinculo({"cwd": "/w/tree/sub"}, "feat/x", "/w/tree", "1"),
       "cwd dentro da worktree é prova")
    ok(not M.prova_de_vinculo({"gitBranch": "main", "cwd": "/outro"},
                              "feat/x", "/w/tree", "1"),
       "e main em outro lugar não é")

    print("\nVizinhança: interpola entre provas, quase não extrapola")
    v = M.Vizinhanca([em(0), em(10)], None)
    ok(v.contem(em(5)),
       "o meio de duas provas próximas conta — são os turnos do orquestrador")
    # O erro 3, em uma linha. Com raio simétrico de 4 h, `em(200)` entrava.
    ok(not v.contem(em(200)),
       "mas 3h20 depois da última prova NÃO conta — extrapolar inflou tudo")
    ok(v.contem(em(-20)) and v.contem(em(30)),
       "margem curta nas duas pontas, para a cauda de turnos do passo")
    ok(not v.contem(em(-200)), "e nada muito antes da primeira prova")

    v2 = M.Vizinhanca([em(0), em(10), em(10 + 60 * 9), em(10 + 60 * 9 + 5)], None)
    ok(not v2.contem(em(10 + 60 * 4)),
       "buraco de 9h separa duas ilhas: o meio dele não é da atividade")
    ok(v2.contem(em(10 + 60 * 9 + 2)), "mas o meio da segunda ilha é")

    print("\nA janela respeita o nascimento da atividade")
    v3 = M.Vizinhanca([em(0), em(10)], em(5))
    ok(not v3.contem(em(1)),
       "nada antes do `iniciar` conta — a atividade não existia")

    print("\nCusto e soma")
    uso = {"entrada": 1_000_000, "cache_escrita": 0,
           "cache_leitura": 0, "saida": 1_000_000}
    ok(abs(M.custo(uso, M.PRECOS_PADRAO) - 90.0) < 0.01,
       "1M de entrada + 1M de saída = US$ 90,00", str(M.custo(uso, M.PRECOS_PADRAO)))
    ok(M.somar({"a": 1}, {"a": 2, "b": 3}) == {"a": 3, "b": 3}, "somar une as chaves")

    print("\nTempo humano: teto por interação, mais reentrada")
    respostas = [em(0), em(100)]
    humanas = [(em(3), "ok"), (em(400), "ok")]     # 3 min de leitura; depois 5h
    r = M.tempo_humano(humanas, respostas, teto_min=10, reentrada_min=3)
    ok(r["interacoes"] == 2, "conta as duas interações", str(r))
    # 3 min reais + 10 de teto (a segunda esperou 5 h, que é ausência)
    ok(abs(r["leitura_h"] - 13 / 60) < 0.001,
       "a espera de 5 h entra pelo teto, não crua", str(r))
    ok(abs(r["reentrada_h"] - 6 / 60) < 0.001, "e a reentrada é por interação", str(r))

    print("\nSobreposição: duas atividades na mesma branch dividem o custo")
    a = {"id": "x", "branch": "b", "custo_usd": 100.0,
         "janela": ["2026-09-01T00:00:00+00:00", "2026-09-02T00:00:00+00:00"]}
    b = {"id": "y", "branch": "b", "custo_usd": 80.0,
         "janela": ["2026-09-01T12:00:00+00:00", "2026-09-03T00:00:00+00:00"]}
    c = {"id": "z", "branch": "outra", "custo_usd": 50.0,
         "janela": ["2026-09-01T12:00:00+00:00", "2026-09-03T00:00:00+00:00"]}
    s = M._sobreposicoes([a, b, c])
    ok(len(s) == 1 and s[0]["atividades"] == ["x", "y"],
       "acusa o par que divide branch e janela", str(s))
    ok(s and s[0]["custo_contado_duas_vezes_usd"] == 80.0,
       "e diz quanto entra duas vezes: o menor dos dois", str(s))
    ok(not M._sobreposicoes([a, c]), "branch diferente não é sobreposição")

    print("\nO painel sai self-contained e com os dados dentro")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import panel as P
    with tempfile.TemporaryDirectory() as d:
        alvo = Path(d) / "p.html"
        P.gerar(alvo, {"projeto": "meu-repo", "gerado_em": "hoje",
                       "parametros": {"teto_leitura_min": 10, "reentrada_min": 3},
                       "atividades": 1, "concluidas": 0, "turnos": 5, "agentes": 1,
                       "custo_usd": 1.0, "humano_h": 0.5, "interacoes": 2,
                       "conferencias": {}, "entrega": {"arquivos": 1, "insercoes": 2,
                       "remocoes": 0, "commits": 1}, "lista": []},
                 {"a": {"id": "a"}})
        html = alvo.read_text(encoding="utf-8")
        ok("<title>Métricas do meu-repo</title>" in html, "o título nomeia o projeto")
        ok('const DADOS = {"projeto"' in html, "os dados entram embutidos")
        ok("http://" not in html.replace("http://www.w3.org", ""),
           "e nada é buscado por rede além das fontes do Google")
        ok('data-theme="dark"' in html and "prefers-color-scheme" in html,
           "os dois temas estão definidos")
        ok(html.count("%(") == 0, "e nenhum marcador do modelo sobrou por preencher")

    print("\nZERO SILENCIOSO: a atividade que a coleta não consegue atribuir")
    raiz, agents = cenario()
    # Trabalho de verdade no disco: US$ 36,00 de tokens numa sessão que esta
    # atividade não tem como reivindicar, porque ela não declara `branch` nem
    # `worktree`. Medido antes de escrever a correção: turnos 0, US$ 0,00.
    sessao(raiz, "s1", [
        reg_humano(T, "trabalho de verdade", pid="p1", cwd=str(raiz)),
        reg_assistente(em(5), entrada=900_000, saida=300_000),
    ])
    atividade(agents, "1066", titulo="Sem branch", trilha="completa", step="9",
              status="em_andamento", criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1066")
    ok(r.get("atribuicao") == "sem-prova",
       "sem `branch` nem `worktree`, o registro se declara NÃO ATRIBUÍDO",
       str(r.get("atribuicao")))
    ok("branch" in (r.get("motivo_atribuicao") or ""),
       "e nomeia a causa, em vez de mostrar zero", str(r.get("motivo_atribuicao")))

    # O falso que eu medi ANTES de desenhar isto: com `concluido_em`, a janela
    # sai PREENCHIDA — `09:05 -> 09:05` — porque o `concluir` entra como prova
    # sintética. Um detector de "janela vazia = não atribuída" daria justamente
    # a atividade CONCLUÍDA por boa. O gatilho tem que ser prova de SESSÃO.
    atividade(agents, "1066", titulo="Sem branch", trilha="completa", step="10",
              status="concluido", criado_em=hora_local(em(-240)),
              concluido_em=hora_local(em(-180)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1066")
    ok(r["janela"][0] is not None,
       "o `concluir` preenche a janela sozinho — é o falso do detector ingênuo",
       str(r["janela"]))
    ok(r.get("atribuicao") == "sem-prova",
       "e a atividade segue NÃO ATRIBUÍDA: prova sintética não é prova de sessão",
       str(r.get("atribuicao")))

    print("\nE a causa é distinguida: declarar branch não é o mesmo que tocá-la")
    atividade(agents, "1069", titulo="Branch intocada", trilha="completa", step="8",
              status="em_andamento", branch="feature/nunca-tocada",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1069")
    ok(r.get("atribuicao") == "sem-prova", "branch declarada e intocada também não atribui")
    ok("sessão" in (r.get("motivo_atribuicao") or ""),
       "e o motivo é outro: nenhuma sessão tocou a branch",
       str(r.get("motivo_atribuicao")))

    print("\nO total do projeto EXCLUI as não atribuídas, e diz quantas")
    sessao(raiz, "s2", [
        reg_humano(T, "abre a atividade", pid="q1", branch="feature/1057"),
        reg_assistente(em(5), entrada=1000, saida=500),
        reg_humano(em(20), "segue", pid="q2", branch="feature/1057"),
    ])
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="9",
              status="em_andamento", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    p = coletado(agents, "projeto")
    ok(p.get("atividades_no_total") == 1,
       "o total soma 1 das 3 atividades", str(p.get("atividades_no_total")))
    ok(sorted(p.get("nao_atribuidas") or []) == ["1066", "1069"],
       "e nomeia as duas que ficaram fora", str(p.get("nao_atribuidas")))
    ok(p["custo_usd"] > 0, "o que foi atribuído continua no total", str(p["custo_usd"]))
    ok(p["atividades"] == 3, "e o número de atividades não mente: continua 3")

    print("\n`[metricas] ligado = false`: a coleta não corre")
    escrever_config(agents, "[metricas]\nligado = false\n")
    limpar(agents / "metrics")
    codigo = M.cmd_coletar(Args(raiz=str(raiz)))
    ok(codigo == 0, "desligada, a coleta sai limpa — nunca reprova", str(codigo))
    ok(not list((agents / "metrics").glob("*.json")) if (agents / "metrics").is_dir() else True,
       "e não grava registro nenhum")
    escrever_config(agents, "")
    limpar(agents / "metrics")
    M.cmd_coletar(Args(raiz=str(raiz)))
    ok(bool(list((agents / "metrics").glob("*.json"))),
       "sem a chave declarada, o padrão é LIGADO — é o que a 1.1.0 já fazia")


    print("\nO `relatar` diz `não atribuída` no lugar de mostrar zero")
    saida = rodar(M.cmd_relatar, raiz=str(raiz))
    l99 = linha_de(saida, "1066")
    ok("não atribuída" in l99, "a atividade sem prova aparece rotulada", l99)
    ok("0.00" not in l99,
       "e NÃO traz número nenhum — zero formatado se lê como medição", l99)
    ok("TOTAL (1 de 3)" in saida,
       "o TOTAL declara de quantas ele é", linha_de(saida, "TOTAL"))
    ok("[ATENÇÃO]" in saida and "fora do total" in saida,
       "e uma linha de atenção conta quantas ficaram fora", saida[-400:])

    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1066")
    ok("não consegui atribuir" in saida,
       "no drill-down ela diz isso na primeira pessoa", saida[:300])
    ok("front-matter" in saida, "e repete o motivo, que é onde está o conserto")
    depois = (saida.split("não consegui atribuir") + [""])[1][:400]
    ok("US$" not in depois,
       "sem custo, prazo ou hora humana depois do aviso", saida[:600])

    print("\nE o painel também não mostra zero por ela")
    html = (agents / "metrics" / "painel.html")
    rodar(M.cmd_painel, raiz=str(raiz))
    corpo = html.read_text(encoding="utf-8")
    ok("sem-prova" in corpo or "não atribuída" in corpo,
       "o HTML carrega o estado de atribuição")

    print("\nO `0` declarado vale 0 — o `or` engolia e virava o padrão")
    # Medido: `int(declarado or 10)` faz `0` valer 10. O config dizia 0, o
    # rodapé imprimia "teto de 10 min", e ninguém sabia da discordância.
    escrever_config(agents, "[metricas]\nteto_leitura_min = 0\nreentrada_min = 0\n")
    limpar(agents / "metrics")
    M.cmd_coletar(Args(raiz=str(raiz)))
    par = coletado(agents, "projeto")["parametros"]
    ok(par["teto_leitura_min"] == 0,
       "teto 0 declarado chega como 0 ao coletor", str(par))
    ok(par["reentrada_min"] == 0, "e reentrada 0 também", str(par))
    escrever_config(agents, "")

    print("\nPF: o declarado, o aferido, e a divergência que ninguém desempata")
    limpar(agents / "metrics")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057", pf="8", pf_aferido="13",
              pf_inventario=".agents/metrics/1057-pf.md",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(r.get("pf") == 8 and r.get("pf_aferido") == 13,
       "os dois números entram no registro, lado a lado", str((r.get("pf"), r.get("pf_aferido"))))
    d = r.get("divergencia_pf") or {}
    ok(d.get("absoluta") == 5, "a divergência absoluta é aferido - declarado", str(d))
    ok(abs((d.get("percentual") or 0) - 62.5) < 0.01, "e a percentual sai sobre o declarado", str(d))
    ok(d.get("sentido") == "declarado menor",
       "com o sentido nomeado: o card subestimou o que foi entregue", str(d))
    ok(r.get("h_por_pf_humano") and r.get("h_por_pf_humano_aferido"),
       "e h/PF sai para OS DOIS — nenhum deles é eleito o verdadeiro", str(r.get("h_por_pf_humano_aferido")))
    ok(r.get("pf_inventario") == ".agents/metrics/1057-pf.md",
       "o inventário é apontado: divergência sem a conta é palpite", str(r.get("pf_inventario")))

    # Inflado ao contrário: o card dizia 13, a entrega mediu 8.
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057", pf="13", pf_aferido="8",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    d = coletado(agents, "1057").get("divergencia_pf") or {}
    ok(d.get("sentido") == "declarado maior", "o caso inflado tem sentido próprio", str(d))

    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057", pf="8",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(r.get("pf_aferido") is None and r.get("divergencia_pf") is None,
       "sem aferção não se inventa divergência", str(r.get("divergencia_pf")))
    ok(r.get("h_por_pf_humano"), "e o h/PF declarado continua saindo")

    print("\nE a AUSÊNCIA de PF é dita, em vez de a linha simplesmente faltar")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057", criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("não declarado" in saida,
       "o drill-down diz que o PF não foi declarado", linha_de(saida, "PF"))
    ok("h/PF" in saida, "e a linha de h/PF aparece, indisponível", linha_de(saida, "h/PF"))

    print("\nOs números de ponta a ponta, para o refactor não poder mudá-los")
    # Este bloco é a rede do item 6: ele fixa o resultado ANTES da passada
    # única, para que "mais rápido" não possa virar "mais rápido e diferente".
    raiz2, agents2 = cenario()
    B = "feature/1071"
    sub = sessao(raiz2, "s", [
        reg_humano(T, "abre a atividade", pid="h1", branch=B),
        reg_assistente(em(5), entrada=1000, saida=500, cache_r=4000, cache_w=2000),
        reg_humano(em(20), "segue", pid="h2", branch=B),
        reg_assistente(em(25), entrada=2000, saida=1000, perguntas=2),
        reg_assistente(em(30), entrada=500, saida=100, sidechain=True),
    ])
    jsonl(sub.parent / sub.stem / "subagents" / "agent-abcd1234.jsonl", [
        reg_humano(em(27), "Você é o **step 9** — frente de código"),
        reg_assistente(em(28), entrada=300, saida=200),
    ])
    with sub.open("a", encoding="utf-8") as f:
        f.write("isto nao e json\n")     # linha corrompida não derruba a leitura
    atividade(agents2, "1071", titulo="Referência", trilha="completa", step="9",
              status="em_andamento", branch=B, criado_em=hora_local(em(-60)))
    M.cmd_coletar(Args(raiz=str(raiz2)))
    r = coletado(agents2, "1071")
    ok(r["tokens"] == {"entrada": 3800, "cache_escrita": 2000,
                       "cache_leitura": 4000, "saida": 1800},
       "os quatro contadores de token somam o esperado", str(r["tokens"]))
    ok(r["turnos"] == 4, "quatro turnos: três da sessão e um do subagente", str(r["turnos"]))
    ok(r["agentes"] == 1 and r["sessoes"] == 1, "um agente, uma sessão",
       str((r["agentes"], r["sessoes"])))
    ok(r["humano"]["interacoes"] == 1,
       "uma interação: a primeira mensagem não tem resposta anterior para medir",
       str(r["humano"]))
    ok(r["humano"]["total_h"] == 0.217,
       "hora humana: 15 min cortados no teto de 10, mais 3 de reentrada",
       str(r["humano"]))
    ok(r["humano"]["perguntas_portao"] == 2, "as duas perguntas de portão", str(r["humano"]))
    ok(r["steps"] and r["steps"][0]["step"] == 9 and r["steps"][0]["agentes"] == 1,
       "e o subagente cai no step 9, pelo destaque em negrito", str(r["steps"]))

    print("\nCada transcrito é lido UMA vez por rodada, não uma por atividade")
    # Eram 2N passadas de json.loads sobre o corpus inteiro: uma em `_provas` e
    # uma no laço principal, por atividade. 14 atividades = 28 passadas, os
    # ~45 s medidos. Não é cache: não sobrevive à rodada, e por isso não tem
    # chave de invalidação para servir número velho em silêncio.
    for i in range(3):
        atividade(agents2, f"3040{i}", titulo=f"Extra {i}", trilha="curta", step="8",
                  status="em_andamento", branch=B, criado_em=hora_local(em(-60)))
    saida = rodar(M.cmd_coletar, raiz=str(raiz2), silencioso=False)
    ok("2 transcrito(s)" in saida,
       "os dois arquivos do disco são lidos uma vez, com 4 atividades na rodada",
       saida)

    print("\nUm slug de projeto NAO engole o do vizinho mais longo")
    # Achado por uma pergunta real: o usuario roda a MESMA atividade em
    # `acme-loja-backoffice` e `acme-loja-admin`, e os dois
    # compartilham o prefixo `acme-loja`. `startswith` sem separador faria
    # um repositorio chamado `acme-loja` engolir as sessoes dos dois --
    # em silencio, e para cima.
    raiz3, _ = cenario()
    base3 = Path(os.environ["HOME"]) / ".claude" / "projects"
    curto = M.slug_do_projeto(raiz3)
    for sufixo in ("", "--claude-worktrees-card-1061", "-admin",
                   "-admin--claude-worktrees-x"):
        (base3 / (curto + sufixo)).mkdir(parents=True, exist_ok=True)
    achadas = {p.name for p in M.pastas_de_sessao(raiz3)}
    ok(curto in achadas, "a propria raiz entra", str(sorted(achadas)))
    ok(curto + "--claude-worktrees-card-1061" in achadas,
       "e a worktree dela tambem -- e' o caso normal do fluxo", str(sorted(achadas)))
    ok(curto + "-admin" not in achadas,
       "mas o repositorio VIZINHO, cujo slug so' compartilha o prefixo, NAO",
       str(sorted(achadas)))
    ok(curto + "-admin--claude-worktrees-x" not in achadas,
       "nem a worktree do vizinho", str(sorted(achadas)))


    print("\nE o slug troca `.` tambem, senao a metrica sai zero em silencio")
    # Confirmado contra pasta real: `<raiz>/.claude/worktrees/x` sai com DOIS
    # tracos. So' o `/` trocado geraria `-.claude-`, que nao existe em disco.
    # `endswith` e nao `==`: no Windows o `resolve()` prefixa a unidade, e a
    # afirmacao aqui e' sobre o que acontece com `/` e `.`, nao sobre a raiz.
    ok(M.slug_do_projeto(Path("/a/b/.claude/worktrees/x")).endswith("a-b--claude-worktrees-x"),
       "`/` e `.` viram `-`", M.slug_do_projeto(Path("/a/b/.claude/worktrees/x")))
    ok("." not in M.slug_do_projeto(Path("/dev/my.app")),
       "projeto com ponto no caminho tambem, senao ele nao acha nada",
       M.slug_do_projeto(Path("/dev/my.app")))

    print("\nOs intervalos da hora humana entram no registro")
    # Sem eles a uniao nao e' calculavel: o agregado `total_h` nao diz QUAIS
    # foram os intervalos, e somar agregados de atividades paralelas conta a
    # mesma pessoa duas vezes no mesmo minuto.
    r = coletado(agents2, "1071")
    intervalos = r["humano"].get("intervalos")
    ok(isinstance(intervalos, list) and len(intervalos) == r["humano"]["interacoes"],
       "um intervalo por interacao contada", str(intervalos))
    ok(intervalos and all(len(x) == 2 and x[0] < x[1] for x in intervalos),
       "cada um e' [inicio, fim] com inicio antes do fim", str(intervalos))

    print("\nConjunto: soma o que soma, e NAO soma o que nao soma")
    def reg(ident, custo, prazo, intervalos, janela, turnos=100, total_h=1.0):
        d = agents2 / "metrics"
        (d / f"{ident}.json").write_text(json.dumps({
            "id": ident, "atribuicao": "ok", "custo_usd": custo, "turnos": turnos,
            "agentes": 2, "prazo_h": prazo, "titulo": f"T{ident}",
            "tokens": {"entrada": 10, "cache_escrita": 0, "cache_leitura": 0, "saida": 5},
            "janela": janela,
            "humano": {"interacoes": len(intervalos), "total_h": total_h,
                       "intervalos": intervalos}}), encoding="utf-8")
        return d / f"{ident}.json"

    # Duas atividades em PARALELO, com leitura humana que se sobrepoe:
    # 10:00-10:08 e 10:05-10:12. A uniao e' 12 min, nao 8+7=15.
    # 8 min de leitura + 3 de reentrada = 0,183 h; 7 + 3 = 0,167 h. Soma 0,35.
    # A uniao dos dois intervalos e' 10:00-10:12 = 12 min -> 0,2 + 0,1 = 0,30.
    a = reg("P1", 100.0, 10.0,
            [["2026-09-01T10:00:00+00:00", "2026-09-01T10:08:00+00:00"]],
            ["2026-09-01T09:00:00+00:00", "2026-09-01T19:00:00+00:00"], total_h=0.183)
    b = reg("P2", 50.0, 6.0,
            [["2026-09-01T10:05:00+00:00", "2026-09-01T10:12:00+00:00"]],
            ["2026-09-01T12:00:00+00:00", "2026-09-01T21:00:00+00:00"], total_h=0.167)
    saida = rodar(M.cmd_conjunto, alvos=[str(a), str(b)])
    ok("150.00" in saida, "custo soma", saida[:400])
    ok("200" in saida, "turnos somam", saida[:400])
    ok("16.0" in saida, "prazo SOMADO e' 10 + 6", saida[:400])
    ok("12.0" in saida, "prazo DE PAREDE e' 09:00 -> 21:00", saida[:500])
    ok("1.33" in saida, "e o ganho de paralelismo e' 16 / 12", saida[:500])
    ok("0.30" in saida, "hora humana da UNIAO: 12 min + 6 de reentrada", saida)
    ok("0.35" in saida,
       "e a soma aparece do lado -- 0,35 h contaria voce duas vezes no minuto", saida)

    print("\nSem sobreposicao, uniao == soma (a guarda de falso positivo)")
    # 8 min e 6 min, sem cruzar: uniao = soma = 14 min + 6 de reentrada = 0,33.
    c = reg("P3", 10.0, 1.0,
            [["2026-09-01T15:00:00+00:00", "2026-09-01T15:06:00+00:00"]],
            ["2026-09-01T15:00:00+00:00", "2026-09-01T15:30:00+00:00"], total_h=0.15)
    saida = rodar(M.cmd_conjunto, alvos=[str(a), str(c)])
    ok(saida.count("0.33") >= 2,
       "disjuntos: a UNIAO e' IGUAL a' soma, e as duas linhas mostram 0,33", saida)

    print("\nAtividade sem prova de atribuicao sai do conjunto, e e' nomeada")
    d = agents2 / "metrics"
    (d / "P4.json").write_text(json.dumps({
        "id": "P4", "atribuicao": "sem-prova",
        "motivo_atribuicao": "sem `branch` nem `worktree` no front-matter",
        "custo_usd": 0.0, "turnos": 0, "agentes": 0, "prazo_h": 0.0,
        "tokens": {}, "janela": [None, None],
        "humano": {"interacoes": 0, "total_h": 0.0, "intervalos": []}}), encoding="utf-8")
    saida = rodar(M.cmd_conjunto, alvos=[str(a), str(d / "P4.json")])
    baixo = saida.lower()
    ok("p4" in baixo and "fora do conjunto" in baixo,
       "a nao atribuida e' nomeada e fica fora", saida)
    ok("100.00" in saida, "e o total e' so' da atribuida", saida[:400])

    for k, v in ambiente.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for d in TEMPORARIOS:
        limpar(d)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de metrics.py: tudo verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
