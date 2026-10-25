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
import publish as P  # noqa: E402

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
                   perguntas=0, sidechain=False, modelo="claude-opus-5"):
    conteudo = []
    if perguntas:
        conteudo.append({"type": "tool_use", "name": "AskUserQuestion",
                         "input": {"questions": [{"q": i} for i in range(perguntas)]}})
    r = {"type": "assistant", "timestamp": utc(quando),
         "message": {"model": modelo,
                     "usage": {"input_tokens": entrada, "output_tokens": saida,
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
    # ERA 90,00 -- $15 + $75, a tabela do Opus 4.1, APOSENTADO. Este teste
    # prendia o preco errado e por isso nao acusou nada quando o modelo mudou:
    # ele provava que a conta batia com a tabela, e nao que a tabela estava
    # certa. Um numero fixado num teste nao vira verdade por estar fixado.
    ok(abs(M.custo(uso, M.PRECOS_PADRAO) - 30.0) < 0.01,
       "1M de entrada + 1M de saida em Opus 5 = US$ 30,00 (5 + 25)",
       str(M.custo(uso, M.PRECOS_PADRAO)))
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

    print("\nSobreposição: o eixo é a JANELA, e nunca foi a branch")
    # O teste antigo exigia a mesma branch, e com isso encodava o defeito: em
    # 12/09/2026 `sobreposicoes` saiu VAZIO enquanto 68% dos registros eram
    # reivindicados por mais de uma atividade e o custo publicado passava o
    # teto do corpus em 3,3x. Quem decide se um registro conta e' a
    # `Vizinhanca`, que olha so' o relogio.
    a = {"id": "x", "branch": "b", "custo_usd": 100.0,
         "janela": ["2026-09-01T00:00:00+00:00", "2026-09-02T00:00:00+00:00"]}
    b = {"id": "y", "branch": "b", "custo_usd": 80.0,
         "janela": ["2026-09-01T12:00:00+00:00", "2026-09-03T00:00:00+00:00"]}
    c = {"id": "z", "branch": "outra", "custo_usd": 50.0,
         "janela": ["2026-09-01T12:00:00+00:00", "2026-09-03T00:00:00+00:00"]}
    d = {"id": "w", "custo_usd": 40.0,      # sem branch: antes nem era olhada
         "janela": ["2026-09-01T18:00:00+00:00", "2026-09-04T00:00:00+00:00"]}
    e = {"id": "v", "branch": "b", "custo_usd": 10.0,
         "janela": ["2026-09-20T00:00:00+00:00", "2026-09-21T00:00:00+00:00"]}
    s = M._sobreposicoes([a, b])
    ok(len(s) == 1 and s[0]["custo_contado_duas_vezes_usd"] == 80.0,
       "acusa o par cujas janelas se cruzam, com o menor dos custos", str(s))
    s = M._sobreposicoes([a, c])
    ok(len(s) == 1, "e acusa TAMBEM quando as branches diferem", str(s))
    ok(s and s[0]["mesma_branch"] is False,
       "dizendo que nao era a mesma branch, em vez de calar", str(s))
    s = M._sobreposicoes([a, d])
    ok(len(s) == 1, "e atividade SEM branch entra na conferencia", str(s))
    ok(not M._sobreposicoes([a, e]),
       "janela que nao cruza nao e' sobreposicao, mesma branch ou nao")

    print("\nInvariante: a soma nao pode passar o teto do corpus lido")
    # A conferencia que faltava. Ela nao corrige -- declara, e alto.
    ok(M.conferir_invariante({"custo_usd": 90628.92},
                             {"custo_usd": 27860.21}) is not None,
       "custo publicado acima do teto e' acusado")
    _e = M.conferir_invariante({"custo_usd": 90628.92}, {"custo_usd": 27860.21})
    ok(_e and _e["vezes"] == 3.25, "e diz quantas vezes passou", str(_e))
    ok(_e and "INFLADO" in _e["o_que_significa"],
       "e diz o que significa, em vez de so' mostrar dois numeros")
    ok(M.conferir_invariante({"custo_usd": 100.0},
                             {"custo_usd": 27860.21}) is None,
       "soma dentro do teto nao acusa nada")
    ok(M.conferir_invariante({"custo_usd": 100.0}, {"custo_usd": 0}) is None,
       "e sem teto medido ela se cala, em vez de acusar por divisao por zero")

    print("\nO painel sai self-contained e com os dados dentro")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import panel as PAINEL
    with tempfile.TemporaryDirectory() as d:
        alvo = Path(d) / "p.html"
        PAINEL.gerar(alvo, {"projeto": "meu-repo", "gerado_em": "hoje",
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
        # A paleta e' FIXA: navy Elcamargo, sem seguir o tema do sistema.
        # Medido: o manual publicado aparecia navy numa maquina e BRANCO em
        # outra, porque `:root` era claro e o escuro so' vinha por
        # `prefers-color-scheme`. Uma pagina de marca nao delega a propria cor
        # ao SO de quem abre.
        css = html.split("<style>")[1].split("</style>")[0]
        ok("@media (prefers-color-scheme" not in css.replace("@media(", "@media (")
           and 'data-theme="dark"' not in css,
           "o CSS nao ramifica por tema do sistema nem por atributo", "")
        ok("#0A1A2B" in html and "#22D3EE" in html,
           "e traz o navy e o ciano da identidade", "")
        ok("color-scheme:dark" in html.replace("color-scheme: dark", "color-scheme:dark"),
           "com `color-scheme:dark`, senao o chrome do navegador sai claro", "")
        ok(html.count("%(") == 0, "e nenhum marcador do modelo sobrou por preencher")
        ok('"10": "Portão · entrega"' in html and '"8": "Desenvolvedor"' in html,
           "os nomes dos steps vêm do STEPS do flow_state, não de cópia à mão")

    print("\nO step 10 não vira step 1")
    # Com `(\d)` o `**step 10**` casava `1`, e o custo do portão 10 caía na
    # conta do Gestor da Atividade sem nada acusar.
    ok(M.papel_do_agente("Você é o **step 10 · Portão humano · Entrega**")[0] == 10,
       "o titular do step 10 é o 10")
    ok(M.papel_do_agente("Auditor de completude do step 10")[0] == 10,
       "e o auditor também")
    ok(M.papel_do_agente("Auditor do step 42")[0] is None,
       "número fora do fluxo não vira step nenhum")

    print("\nPercurso do projeto: voltas, portões e bugs que escaparam")
    _p = lambda **k: {"voltas": {}, "voltas_total": 0, "devolucoes": [],
                      "portoes": {}, "reaberturas": 0, **k}
    _todas = [
        {"id": "A", "status": "concluido", "trilha": "curta", "corrige": None,
         "risco": "alto",
         "percurso": _p(voltas={"9→8": 2}, voltas_total=2,
                        portoes={"10": {"aprovado": 1, "devolvido": 1}},
                        devolucoes=[{"de": 10, "para": 8, "motivo": "escopo"}])},
        {"id": "B", "status": "concluido", "trilha": "completa", "corrige": None,
         "percurso": _p(portoes={"5": {"aprovado": 1, "devolvido": 0},
                                 "10": {"aprovado": 1, "devolvido": 0}},
                        reaberturas=1)},
        {"id": "C", "status": "em_andamento", "trilha": "curta", "corrige": "A",
         "percurso": _p(voltas={"9→8": 1}, voltas_total=1)},
        {"id": "D", "status": "concluido", "trilha": "curta", "corrige": "FORA-1",
         "percurso": _p()},
        {"id": "VELHO", "status": "concluido", "trilha": "curta", "corrige": None},
    ]
    _ag = M.agregar_percurso(_todas)
    ok(_ag["voltas"] == {"9→8": 3} and _ag["atividades_com_volta"] == 2,
       "as voltas somam por par, e contam quantas atividades voltaram")
    ok(_ag["portoes"]["10"]["aprovado"] == 2 and _ag["portoes"]["10"]["devolvido"] == 1
       and _ag["portoes"]["10"]["taxa_de_devolucao"] == 0.333,
       "o portão 10 viu três decisões, uma devolução")
    ok(_ag["devolucoes_por_motivo"] == {"escopo": 1, "defeito": 0},
       "devoluções separadas por motivo")
    ok(_ag["reaberturas"] == 1, "reaberturas somam")
    ok(_ag["bugs_que_escaparam"] == {"A": ["C"]}
       and _ag["bugs_com_origem_fora"] == ["D"],
       "o bug conta na ORIGEM; origem fora do projeto fica à parte")
    ok(_ag["por_trilha"]["curta"]["concluidas"] == 3
       and _ag["por_trilha"]["curta"]["com_bug_depois"] == 1
       and _ag["por_trilha"]["completa"]["com_bug_depois"] == 0,
       "e por trilha da origem: 1 de 3 curtas voltou com bug")
    ok(_ag["por_risco"]["alto"] == {"concluidas": 1, "com_bug_depois": 1,
                                    "bugs": 1, "taxa_com_bug": 1.0}
       and _ag["por_risco"]["nao-declarado"]["concluidas"] == 3,
       "e por risco: sem `--risco` fica `nao-declarado`, não vira `padrao`")
    ok(_ag["sem_percurso"] == ["VELHO"] and _ag["atividades_medidas"] == 4,
       "registro antigo sem percurso é NOMEADO, não contado como zero")
    ok(M.agregar_percurso([])["atividades_medidas"] == 0,
       "projeto vazio não quebra")

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

    # Três números do mesmo arquivo contam conjuntos diferentes, e o nome
    # `atividades_no_total` se lê como "total de atividades". Uma sessão do
    # backoffice leu 46 / 49 / 51 e concluiu, com razão, que não reconcilia.
    _d = p.get("denominadores") or {}
    ok(_d.get("atividades") == 3 and _d.get("com_prova_de_atribuicao") == 1
       and _d.get("sem_prova") == 2,
       "o JSON diz o denominador de cada número, em vez de deixar adivinhar", str(_d))
    ok(_d.get("com_prova_de_atribuicao", 0) + _d.get("sem_prova", -1)
       == _d.get("atividades"),
       "e as duas partes fecham com o todo — a conta é conferível no arquivo")
    ok(_d.get("concluidas_com_prova", 99) <= _d.get("concluidas_de_todas", -1),
       "concluídas COM prova nunca passa de concluídas de todas", str(_d))
    ok("conjuntos diferentes" in (_d.get("leia") or ""),
       "e a legenda avisa que comparar os dois é comparar conjuntos diferentes")

    print("\nA recusa de publicar que era MUDA")
    import io as _io, contextlib as _ctx, time as _time
    _docs = raiz / "docs"
    _docs.mkdir(exist_ok=True)
    _pub = _docs / "metricas.md"
    _alvo = agents / "metrics" / "projeto.json"

    _pub.write_text("velho\n", encoding="utf-8")
    os.utime(_pub, (_alvo.stat().st_mtime - 3600,) * 2)
    _b = _io.StringIO()
    with _ctx.redirect_stdout(_b):
        M._avisar_publicado_velho(raiz, agents)
    ok("NÃO publiquei" in _b.getvalue() and "publicar_no_repo" in _b.getvalue(),
       "publicado mais VELHO que a medida: ela fala, e diz por quê", _b.getvalue())
    ok("metrics.py publicar" in _b.getvalue(),
       "e entrega o comando que alinha os dois", _b.getvalue())

    os.utime(_pub, (_alvo.stat().st_mtime + 60,) * 2)
    _b = _io.StringIO()
    with _ctx.redirect_stdout(_b):
        M._avisar_publicado_velho(raiz, agents)
    ok(_b.getvalue() == "", "publicado mais NOVO: cala — não há o que envelhecer")

    _pub.unlink()
    _b = _io.StringIO()
    with _ctx.redirect_stdout(_b):
        M._avisar_publicado_velho(raiz, agents)
    ok(_b.getvalue() == "",
       "e quem NUNCA publicou não é avisado: a escolha de não publicar é "
       "legítima, e é o padrão")

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

    print("\nPrazo ABERTO: sem `concluido_em`, o prazo e' ate' AGORA, nao a' entrega")
    # Medido em 03/09: as tres frentes do dia estavam TODAS `em_andamento`, no
    # step 3, e o relatorio de cada uma imprimia "prazo, do primeiro registro
    # a' ENTREGA" seguido de "cauda, trabalho depois da entrega  0.0 h".
    # Nenhuma tinha entregue. O prazo ia ate' o ultimo registro do transcrito,
    # e a cauda era zero POR DEFINICAO. Quem lesse a tela leria um prazo
    # fechado e um "nao houve retrabalho" -- os dois falsos, e o segundo pior,
    # porque zero formatado se le' como medicao.
    limpar(agents / "metrics")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="9",
              status="em_andamento", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(r.get("prazo_aberto") is True,
       "o registro marca que o prazo nao fechou numa entrega",
       str(r.get("prazo_aberto")))
    ok(r["prazo_h"] > 0, "e continua medindo: aberto nao e' zero", str(r["prazo_h"]))

    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("à entrega" not in saida,
       "o rotulo NAO promete uma entrega que nao houve", linha_de(saida, "prazo"))
    ok("até agora" in saida,
       "ele diz ate' onde mediu de verdade", linha_de(saida, "prazo"))
    ok("cauda, trabalho depois da entrega" not in saida,
       "e a LINHA de cauda some: sem entrega ela e' zero por definicao",
       linha_de(saida, "cauda"))
    ok("vai crescer" in saida,
       "com o aviso de que o numero ainda se move", saida[-700:])

    print("\nE a lista do projeto marca a aberta, em vez de alinhar tudo igual")
    saida = rodar(M.cmd_relatar, raiz=str(raiz))
    l20 = linha_de(saida, "1057")
    ok("h+" in l20, "a linha da atividade em andamento leva a marca", l20)
    ok("em andamento" in saida, "e a marca tem legenda, senao e' ruido", saida[-400:])

    print("\nQuando a atividade FECHA, o rotulo volta a prometer a entrega")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057",
              criado_em=hora_local(em(-240)), concluido_em=hora_local(em(30)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(r.get("prazo_aberto") is False,
       "fechada, o prazo e' fechado", str(r.get("prazo_aberto")))
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("à entrega" in saida, "e o rotulo de entrega volta", linha_de(saida, "prazo"))
    ok("cauda, trabalho depois da entrega" in saida,
       "a linha de cauda volta a ser mostravel", linha_de(saida, "cauda"))
    ok("vai crescer" not in saida, "sem o aviso de aberto", saida[-500:])
    l20 = linha_de(rodar(M.cmd_relatar, raiz=str(raiz)), "1057")
    ok("h+" not in l20, "e a lista tira a marca dela", l20)

    print("\nRegistro velho, sem a chave: a resposta sai de `concluido_em`")
    # A chave nasceu na 2.5.0. Um registro coletado antes dela nao a tem, e
    # ninguem vai recoletar o historico inteiro para ler um rotulo. O recuo e'
    # `concluido_em`, que esta' no esquema desde o comeco.
    velho = json.loads((agents / "metrics" / "1057.json").read_text(encoding="utf-8"))
    velho.pop("prazo_aberto", None)
    ok(M.prazo_esta_aberto(velho) is False,
       "velho COM `concluido_em` le' fechado", str(velho.get("concluido_em")))
    velho["concluido_em"] = ""
    ok(M.prazo_esta_aberto(velho) is True, "velho SEM ele le' aberto")

    print("\nAssinatura: o que o mes cobra, rateado pelo prazo -- e NAO pelos tokens")
    # Pedido para a apresentacao de resultados: o custo em tabela de API e' teto,
    # e quem roda por assinatura nao paga aquilo. O numero que falta e' o que a
    # assinatura cobrou pelo tempo em que a atividade esteve viva.
    #
    # As assinaturas sao uma LISTA de valores mensais, e nao um preco vezes um
    # numero: medido no caso real, as duas contas do usuario sao de planos
    # DIFERENTES -- uma Max 20x e um assento Team. Multiplicador daria errado.
    limpar(agents / "metrics")
    escrever_config(agents, "[metricas]\nassinaturas_usd_mes = [200.0, 30.0]\n")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057", pf="8",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(abs((r.get("assinatura_usd") or 0)
           - round(230.0 / M.HORAS_POR_MES * r["prazo_h"], 2)) < 0.01,
       "o rateio e' (soma das assinaturas / horas do mes) x prazo",
       str((r.get("assinatura_usd"), r["prazo_h"])))
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("assinatura" in saida.lower(), "e a linha aparece no drill-down",
       linha_de(saida, "assinatura"))
    ok("230" in saida, "com o mensal declarado a' vista, senao o rateio e' magica",
       linha_de(saida, "assinatura"))

    print("\nE sem declaracao ela NAO aparece -- preco nao se adivinha")
    escrever_config(agents, "")
    limpar(agents / "metrics")
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    ok(r.get("assinatura_usd") is None,
       "sem `assinaturas_usd_mes`, o registro nao inventa custo",
       str(r.get("assinatura_usd")))
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("custo de assinatura" not in saida.lower(),
       "e a LINHA do rateio some, em vez de sair zerada",
       linha_de(saida, "custo de assinatura"))

    print("\nFPA: a estimativa sai do PF DECLARADO, nas duas produtividades")
    ok("produtividade 6" in saida and "produtividade 10" in saida,
       "as duas produtividades aparecem", linha_de(saida, "produtividade"))
    ok("48 h" in saida and "80 h" in saida,
       "8 PF x 6 = 48 h e 8 PF x 10 = 80 h", linha_de(saida, "produtividade 6"))

    print("\nSem PF declarado, a estimativa APF nao aparece")
    limpar(agents / "metrics")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("produtividade" not in saida,
       "sem PF nao ha' estimativa: ela seria multiplicacao de nada", saida[:400])

    print("\nMODELO: a tabela de preco e' POR MODELO, e nao uma so' para tudo")
    # Achado ao implementar: a tabela do pacote era `entrada 15.0 / saida 75.0`
    # -- preco do Opus 4.1 e do Opus 4, ambos APOSENTADOS. Os transcritos
    # mostram `claude-opus-5`, que custa 5 e 25, com cache lido a 0,50 e nao
    # 1,50. Todo custo que a ferramenta reportava estava ~3x inflado, e o
    # numero foi para uma apresentacao de gestao.
    ok("claude-opus-5" in M.PRECOS_POR_MODELO, "o Opus 5 tem tabela propria")
    o5 = M.precos_do_modelo("claude-opus-5")
    ok(o5["entrada"] == 5.0 and o5["saida"] == 25.0,
       "com o preco publicado: 5 de entrada, 25 de saida", str(o5))
    ok(o5["cache_leitura"] == 0.50,
       "e cache lido a 0,50 -- 0,1x da entrada, nao 1,50", str(o5["cache_leitura"]))
    ok(M.precos_do_modelo("claude-opus-5", ttl="1h")["cache_escrita"] == 10.0
       and M.precos_do_modelo("claude-opus-5", ttl="5m")["cache_escrita"] == 6.25,
       "e o cache de ESCRITA depende do TTL: 2x em 1h, 1,25x em 5m")
    s5 = M.precos_do_modelo("claude-sonnet-5")
    ok(s5["entrada"] == 2.0 and s5["saida"] == 10.0, "Sonnet 5 a 2 e 10", str(s5))
    h5 = M.precos_do_modelo("claude-haiku-4-5")
    ok(h5["entrada"] == 1.0 and h5["saida"] == 5.0, "Haiku 4.5 a 1 e 5", str(h5))

    print("\nO custo de cada turno usa a tabela DO MODELO daquele turno")
    # Somar tudo numa tabela so' cobra Opus por turno de Haiku. Com cascata de
    # modelo -- que e' justamente o que se quer avaliar -- o erro fica maior
    # quanto mais a cascata funciona.
    uso = {"entrada": 1_000_000, "cache_escrita": 0, "cache_leitura": 0, "saida": 0}
    ok(M.custo_do_modelo(uso, "claude-opus-5") == 5.0,
       "1M de entrada em Opus 5 custa 5", str(M.custo_do_modelo(uso, "claude-opus-5")))
    ok(M.custo_do_modelo(uso, "claude-haiku-4-5") == 1.0,
       "e em Haiku custa 1", str(M.custo_do_modelo(uso, "claude-haiku-4-5")))

    print("\nModelo desconhecido NAO vira zero, e nao vira Opus")
    # Zero esconderia gasto; Opus inventaria gasto. Ele cai no padrao
    # DECLARADO e a atividade registra que houve modelo nao tabelado.
    ok(M.custo_do_modelo(uso, "claude-modelo-que-nao-existe") > 0,
       "modelo fora da tabela ainda custa alguma coisa")
    ok(M.PADRAO_DE_PRECO in M.PRECOS_POR_MODELO,
       "e o padrao e' um modelo declarado, nao um chute", M.PADRAO_DE_PRECO)

    print("\nO registro guarda o gasto POR MODELO")
    limpar(agents / "metrics")
    sessao(raiz, "mods", [
        reg_humano(T, "abre", pid="q1", branch="feature/1057"),
        reg_assistente(em(2), entrada=1000, saida=500, modelo="claude-opus-5"),
        reg_assistente(em(4), entrada=2000, saida=800, modelo="claude-haiku-4-5"),
        reg_humano(em(20), "segue", pid="q2", branch="feature/1057"),
    ])
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="9",
              status="em_andamento", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r = coletado(agents, "1057")
    pm = r.get("por_modelo") or {}
    ok(set(pm) >= {"claude-opus-5", "claude-haiku-4-5"},
       "os dois modelos aparecem separados", str(list(pm)))
    # O cenario acumula sessoes de blocos anteriores, todas no modelo padrao --
    # entao o Opus tem MAIS de um turno aqui. O que este bloco prova e' a
    # SEPARACAO, e o Haiku so' aparece na sessao que este bloco criou.
    ok(pm.get("claude-haiku-4-5", {}).get("turnos") == 1,
       "o turno de Haiku e' contado no balde dele", str(pm.get("claude-haiku-4-5")))
    ok(pm.get("claude-opus-5", {}).get("turnos", 0) >= 1,
       "e os de Opus no dele", str(pm.get("claude-opus-5")))
    ok(pm["claude-haiku-4-5"]["custo_usd"] < pm["claude-opus-5"]["custo_usd"],
       "com o Haiku saindo mais barato, pela tabela dele", str(pm))
    ok(all("custo_usd" in v for v in pm.values()),
       "e o custo de cada um, pela tabela dele", str(pm))

    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1057")
    ok("opus-5" in saida and "haiku" in saida,
       "o relatorio mostra a mistura de modelos", linha_de(saida, "opus"))

    print("\nACHADOS: os furos que a revisao apanhou entram na metrica")
    # A apresentacao defende custo e prazo, e nenhum dos dois responde a quem
    # acha que pensar menos entrega mais rapido: o custo de um erro de analise
    # nao aparece na tarefa em que ele foi cometido. O fluxo apanha esses erros
    # e os corrige -- so' nao contava.
    limpar(agents / "metrics")
    rel = raiz / "docs" / "relatorio.md"
    rel.parent.mkdir(parents=True, exist_ok=True)
    rel.write_text("""# Revisao

| # | Ponto | Severidade | Quem decide | Destino |
| --- | --- | --- | --- | --- |
| A-01 | premissa falsa | alta · leitura | engenharia | corrigido em `x.ts:44` |
| A-02 | sem caminho para renomear | alta · leitura | engenharia | corrigido |
| A-03 | contradicao no mesmo paragrafo | bloqueia · leitura | negocio | corrigido |
| A-04 | duplicacao pequena | baixa · leitura | engenharia | descartado |
| A-05 | falta teste | baixa · leitura | engenharia | aberto |

## Volta 2

| # | O que a volta 2 achou | Severidade | Destino |
| --- | --- | --- | --- |
| B-01 | a correcao do A-01 quebrou outro trecho | alta | corrigido |
| B-02 | texto novo contradiz a CAM-009 | baixa | corrigido |
""", encoding="utf-8")
    atividade(agents, "1057", titulo="Atribuída", trilha="completa", step="10",
              status="concluido", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    (agents / "atividades" / "1057.md").write_text(
        (agents / "atividades" / "1057.md").read_text(encoding="utf-8")
        + "\n## Artefatos\n\n| Tipo | Caminho |\n| --- | --- |\n"
          "| relatorio-negocio | docs/relatorio.md |\n", encoding="utf-8")
    M.cmd_coletar(Args(raiz=str(raiz)))
    a = coletado(agents, "1057").get("achados") or {}
    ok(a.get("total") == 7, "conta os achados das DUAS tabelas", str(a)[:200])
    ok(a.get("severidade", {}).get("alta") == 3, "3 altas", str(a.get("severidade")))
    ok(a.get("severidade", {}).get("bloqueia") == 1, "1 bloqueia", str(a.get("severidade")))
    ok(a.get("severidade", {}).get("baixa") == 3, "3 baixas", str(a.get("severidade")))
    ok(a.get("destino", {}).get("corrigido") == 5, "5 corrigidos", str(a.get("destino")))
    ok(a.get("destino", {}).get("aberto") == 1, "1 aberto", str(a.get("destino")))
    ok(a.get("destino", {}).get("descartado") == 1, "1 descartado", str(a.get("destino")))

    print("\nA VOLTA 2 e' contada a parte, e NAO chamada de 'introduzidos'")
    # A prosa da atividade medida diz "6 delas contradicoes criadas pelas
    # correcoes da 1a" -- ou seja, a volta 2 traz achados novos E achados
    # induzidos, e so' quem escreveu sabe separar. Contar a volta 2 e chama-la
    # de "introduzidos ao corrigir" seria inventar a distincao.
    ok(a.get("volta_2") == 2, "a volta 2 tem contagem propria", str(a.get("volta_2")))
    ok("introduzidos" not in json.dumps(a),
       "e o registro NAO afirma quantos foram induzidos pela correcao", str(a)[:200])

    print("\nSem relatorio, a dimensao fica AUSENTE -- e nao zerada")
    limpar(agents / "metrics")
    atividade(agents, "1069", titulo="Sem relatorio", trilha="completa", step="8",
              status="em_andamento", branch="feature/1057",
              criado_em=hora_local(em(-240)))
    M.cmd_coletar(Args(raiz=str(raiz)))
    r2 = coletado(agents, "1069")
    ok(r2.get("achados") is None,
       "atividade sem relatorio nao ganha `achados: 0` -- zero se leria como "
       "'revisamos e nao achamos nada'", str(r2.get("achados")))

    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="1069")
    ok("achados" not in saida.lower(),
       "e a linha nao aparece na tela", linha_de(saida, "achado"))

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

    # O TETO tem de ler o mesmo corpus que a atividade lê. Ele não lia: varria
    # só `<pasta>/*.jsonl` e deixava `<sessao>/subagents/*.jsonl` de fora —
    # metade do custo medido em dois repositórios reais, 21/09/2026. E o efeito
    # não era um número baixo: era o alarme de sobre-atribuição acusando
    # contagem dupla onde havia assimetria de leitura.
    _p = coletado(agents2, "projeto")
    _teto = _p.get("teto_do_corpus") or {}
    ok(_teto.get("tokens", {}).get("entrada", 0) >= r["tokens"]["entrada"]
       and _teto.get("tokens", {}).get("saida", 0) >= r["tokens"]["saida"],
       "o teto do corpus inclui o subagente — senão não é teto de nada",
       f"teto={_teto.get('tokens')} atividade={r['tokens']}")
    ok(_teto.get("custo_usd", 0) >= _p.get("custo_usd", 0),
       "e nenhuma soma por atividade passa dele, que é a promessa do docblock",
       f"teto={_teto.get('custo_usd')} soma={_p.get('custo_usd')}")
    ok(not _p.get("sobre_atribuicao"),
       "com o teto lendo o corpus inteiro, este caso NÃO acusa sobre-atribuição",
       str(_p.get("sobre_atribuicao")))

    # A SEGUNDA VARREDURA. Trocar a chave de agregação não teria pego a
    # cegueira do coletor: `message.id` e `requestId` concordaram em 0,00%
    # enquanto as duas somavam 48% a menos. Duas medidas que compartilham um
    # estágio não conferem aquele estágio — então esta desce a árvore por
    # `rglob`, que não sabe o que espera achar.
    ok(_teto.get("corpus_nao_lido") is None
       and _teto.get("arquivos_lidos") == _teto.get("arquivos_no_disco"),
       "a varredura de cima e a de baixo enxergam o mesmo número de arquivos",
       f"lidos={_teto.get('arquivos_lidos')} disco={_teto.get('arquivos_no_disco')}")

    # E o detector não é decoração: um transcrito que o coletor NÃO alcança
    # tem de acender a luz. É a forma do defeito que estava lá — `subagents/`
    # fora do glob — plantada de novo em outro lugar da árvore.
    _fundo = sub.parent / sub.stem / "mais" / "fundo" / "perdido.jsonl"
    _fundo.parent.mkdir(parents=True, exist_ok=True)
    _fundo.write_text(json.dumps(reg_assistente(em(40), entrada=10, saida=10)) + "\n",
                      encoding="utf-8")
    _t2 = M.teto_do_corpus(raiz2, M.Corpus(), M.PRECOS_PADRAO)
    ok(_t2.get("corpus_nao_lido") is not None,
       "transcrito fora do alcance do coletor ACENDE a luz — o detector dispara",
       str(_t2.get("corpus_nao_lido")))
    ok((_t2.get("corpus_nao_lido") or {}).get("no_disco", 0)
       > (_t2.get("corpus_nao_lido") or {}).get("lidos", 0),
       "e diz quantos o disco tem contra quantos ele leu")
    ok(_t2.get("raizes_varridas"),
       "e o detector diz SOB QUAL raiz varreu — número sem denominador à vista "
       "convida a mesma leitura que um fator de inflação sem o corpus")
    _fundo.unlink()
    ok((M.teto_do_corpus(raiz2, M.Corpus(), M.PRECOS_PADRAO).get("raizes_varridas") or [])
       == (_t2.get("raizes_varridas") or []),
       "as raízes saem SEMPRE, com a luz acesa ou apagada")
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

    print("\nConjunto: frente ainda aberta faz do ganho um retrato, e ele diz isso")
    # P1 e P2 nao tem `concluido_em`: sao atividades abertas, e o prazo de cada
    # uma ainda cresce. O `2.01x` que saiu das tres frentes de 03/09 era
    # exatamente este caso -- as tres no step 3, nenhuma entregue -- e a tela
    # apresentava o numero como resultado.
    saida = rodar(M.cmd_conjunto, alvos=[str(a), str(b)])
    ok("em andamento" in saida,
       "o conjunto avisa que ha' frente aberta", saida[-600:])
    ok("2 de 2" in saida, "e diz quantas de quantas", saida[-600:])

    fechada = reg("P5", 10.0, 2.0,
                  [["2026-09-01T16:00:00+00:00", "2026-09-01T16:06:00+00:00"]],
                  ["2026-09-01T16:00:00+00:00", "2026-09-01T16:30:00+00:00"],
                  total_h=0.15)
    corpo = json.loads(fechada.read_text(encoding="utf-8"))
    corpo["prazo_aberto"] = False
    fechada.write_text(json.dumps(corpo), encoding="utf-8")
    saida = rodar(M.cmd_conjunto, alvos=[str(fechada)])
    ok("em andamento" not in saida,
       "e cala quando todas fecharam", saida[-600:])

    print("\nConjunto: a assinatura e' rateada pela PAREDE, nao pela soma dos prazos")
    # E' a mesma correcao que a uniao faz na hora humana. Somar o rateio de
    # atividades paralelas cobraria a MESMA assinatura duas vezes no mesmo mes:
    # ela e' cobrada por tempo corrido, e o tempo corrido nao dobra porque voce
    # abriu duas janelas.
    for ident, prazo in (("P1", 10.0), ("P2", 6.0)):
        f = agents2 / "metrics" / f"{ident}.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["assinatura_mensal_usd"] = 230.0
        d["assinatura_usd"] = round(230.0 / M.HORAS_POR_MES * prazo, 2)
        f.write_text(json.dumps(d), encoding="utf-8")
    saida = rodar(M.cmd_conjunto, alvos=[str(a), str(b)])
    parede = round(230.0 / M.HORAS_POR_MES * 12.0, 2)     # 09:00 -> 21:00
    soma = round(230.0 / M.HORAS_POR_MES * 16.0, 2)       # 10 + 6
    ok(f"{parede:.2f}" in saida,
       "o rateio usa as 12 h de parede, nao as 16 h somadas", saida[-700:])
    ok(f"{soma:.2f}" not in saida,
       "e a soma dos rateios NAO aparece como custo", saida[-700:])

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

    # -----------------------------------------------------------------------
    # Publicar: o que sai do `.agents/` e entra no repositorio, e o que NAO sai.

    print("\nTotal que mistura tabelas de preco diferentes ACUSA")
    # Medido no backoffice: `coletar --atividade X` reagrega o projeto a partir
    # dos JSON no disco, inclusive os gravados pela 2.13.0 -- que cobrava pela
    # tabela do Opus 4.1 APOSENTADO. O total dizia US$ 10.544,99 misturando um
    # registro novo com dez velhos, e o custo por turno saia 2,73x o real.
    # `por_modelo` nasceu na 2.14.0: registro sem ele veio da tabela antiga.
    from copy import deepcopy
    novo = {"id": "N", "atribuicao": "ok", "por_modelo": {"claude-opus-5": {}}}
    velho = {"id": "V", "atribuicao": "ok"}
    ok(sorted(a["id"] for a in [novo, velho] if not a.get("por_modelo")) == ["V"],
       "registro sem `por_modelo` e' o que veio de versao anterior")

    print("\nBranch MESCLADA nao entrega zero — ela entrega pelos commits dela")
    # O defeito, medido no `acme-backoffice`: SEIS das onze atividades
    # — todas as concluidas e mescladas — reportavam `0 commits, 0 arquivos, +0`.
    # `main...branch` e' VAZIO por definicao depois que a branch entra na main:
    # ela virou ancestral, e nao ha' tres pontos a comparar. Zero ali se lia
    # como "nao entregou nada", que e' o contrario de "entregou e foi mesclado".
    import subprocess
    repo = Path(tempfile.mkdtemp(prefix="entrega-")).resolve()
    TEMPORARIOS.append(repo)

    def g(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env={**os.environ,
                                              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    g("init", "-q", "-b", "main")
    (repo / "a.txt").write_text("um\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "base")
    g("checkout", "-qb", "feat/x")
    (repo / "b.txt").write_text("\n".join(f"linha {i}" for i in range(10)) + "\n",
                                encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "entrega da atividade")
    g("checkout", "-q", "main")
    g("merge", "-q", "--no-ff", "-m", "merge", "feat/x")

    viva = M.entrega_da_branch(repo, "feat/x", desde="")
    ok(viva.get("metodo") == "indisponivel",
       "mesclada e sem `criado_em`: a entrega fica AUSENTE, com o motivo", str(viva))
    ok("já está em" in viva.get("motivo", ""),
       "e o motivo nomeia a causa em vez de sair zerado", str(viva))

    cheia = M.entrega_da_branch(repo, "feat/x", desde="1970-01-01")
    ok(cheia.get("metodo") == "commits",
       "com a data, ela mede pelos commits da atividade", str(cheia))
    ok(cheia.get("commits") == 2 and cheia.get("insercoes") == 11,
       "e acha os 2 commits e as 11 linhas que a branch escreveu",
       f"{cheia.get('commits')} commits, +{cheia.get('insercoes')}")

    # A guarda do outro lado: com a branch VIVA, o caminho continua o de sempre.
    g("checkout", "-qb", "feat/viva")
    (repo / "c.txt").write_text("so uma\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "viva")
    aberta = M.entrega_da_branch(repo, "feat/viva", desde="1970-01-01")
    ok(aberta.get("metodo") == "diff",
       "branch ainda viva continua medindo pelo diff de tres pontos", str(aberta))
    ok(aberta.get("commits") == 1 and aberta.get("insercoes") == 1,
       "e o diff dela sai certo", str(aberta))

    print("\nA regua APF do projeto so' compara conjuntos IGUAIS")
    # O erro que este bloco prende: somar o PF de TODAS as atividades e
    # confrontar com a hora humana das ATRIBUIDAS. O fator sairia inflado, que
    # e' a unica direcao que este coletor declara nao poder errar.
    apf = M.bloco_apf([
        {"id": "A", "pf": 10, "humano": {"total_h": 2.0}, "prazo_h": 8.0,
         "custo_usd": 50.0},
        {"id": "B", "pf": 30, "humano": {"total_h": 6.0}, "prazo_h": 12.0,
         "custo_usd": 90.0},
        {"id": "C", "humano": {"total_h": 100.0}, "prazo_h": 200.0,
         "custo_usd": 10.0},   # atribuida, mas SEM pf
    ])
    ok(apf["pf"] == 40, "o PF soma so' quem tem PF", str(apf["pf"]))
    ok(apf["humano_h"] == 8.0,
       "e a hora humana vem das MESMAS atividades — as 100 h de C ficam fora",
       str(apf["humano_h"]))
    ok(apf["fora"] == ["C"], "C e' nomeada como fora da conta", str(apf["fora"]))
    ok(apf["horas"]["6"] == 240 and apf["horas"]["10"] == 400,
       "as duas produtividades saem de PF x horas", str(apf["horas"]))
    ok(apf["fator_humano"]["6"] == 30.0 and apf["fator_prazo"]["6"] == 12.0,
       "e ha' DOIS fatores: o de hora humana e o de relogio",
       f"{apf['fator_humano']} / {apf['fator_prazo']}")
    ok(M.bloco_apf([{"id": "X", "humano": {"total_h": 1.0}}]) is None,
       "sem PF nenhum, a regua e' AUSENTE — nao zero")

    print("\nPublicar: o gate e' o config, e o padrao e' NAO escrever")
    raiz, agents = cenario()
    (agents / "metrics").mkdir(parents=True, exist_ok=True)
    projeto = {
        "projeto": "repo-de-teste", "gerado_em": "2026-09-05 10:00:00",
        "parametros": {"teto_leitura_min": 10, "reentrada_min": 3},
        "atividades": 2, "concluidas": 1, "atividades_no_total": 1,
        "nao_atribuidas": ["Z9"], "custo_usd": 300.0, "turnos": 100,
        "agentes": 10, "humano_h": 4.0, "interacoes": 20,
        "entrega": {"arquivos": 5, "insercoes": 500, "remocoes": 20, "commits": 3},
        "conferencias": {}, "sobreposicoes": [],
        "apf": {"pf": 40, "origem": "declarado", "atividades": ["A1"], "fora": [],
                "humano_h": 4.0, "prazo_somado_h": 20.0, "custo_usd": 300.0,
                "em_andamento": [], "horas": {"6": 240, "10": 400},
                "fator_humano": {"6": 60.0, "10": 100.0},
                "fator_prazo": {"6": 12.0, "10": 20.0}},
        "lista": [
            {"id": "A1", "titulo": "Uma atividade", "step": 9, "trilha": "completa",
             "status": "concluido", "custo_usd": 300.0, "prazo_h": 20.0, "pf": 40,
             "concluido_em": "2026-09-04 10:00:00", "prazo_aberto": False,
             "humano": {"total_h": 4.0, "interacoes": 20},
             "entrega": {"arquivos": 5, "insercoes": 500}},
            {"id": "Z9", "titulo": "Sem prova", "step": 2, "trilha": "completa",
             "status": "em-andamento", "atribuicao": "sem-prova",
             "motivo_atribuicao": "sem `branch` no front-matter"},
        ],
    }
    (agents / "metrics" / "projeto.json").write_text(
        json.dumps(projeto, ensure_ascii=False), encoding="utf-8")
    (raiz / "README.md").write_text("# repo\n\nja existia.\n", encoding="utf-8")

    args = Args(raiz=str(raiz), pasta=None, sem_readme=False, indexar=False,
                auto=True, calado=True)
    saida = rodar(M.cmd_publicar, **args.__dict__)
    ok(not (raiz / "docs").exists(),
       "sem `publicar_no_repo`, o `--auto` nao escreve no repositorio de ninguem",
       saida)

    escrever_config(agents, "[metricas]\npublicar_no_repo = true\n")
    saida = rodar(M.cmd_publicar, **args.__dict__)
    md = (raiz / "docs" / "metricas.md").read_text(encoding="utf-8")
    html = (raiz / "docs" / "metricas.html").read_text(encoding="utf-8")
    readme = (raiz / "README.md").read_text(encoding="utf-8")
    ok((raiz / "docs" / "metricas.md").exists() and (raiz / "docs" / "metricas.html").exists(),
       "ligado, ele grava os dois arquivos")
    ok("acrescentou" in saida,
       "e ANUNCIA a primeira escrita no README, mesmo calado", saida)
    ok("ja existia." in readme and M.__name__ and "elcamargo-ai-flow:metricas" in readme,
       "o README de quem estava la' e' preservado, e o bloco entra entre marcas")

    print("\nO publicado NAO leva hora humana por atividade")
    # A regra que este bloco prende: o total do projeto fica, a linha por
    # atividade sai. Versionada ao lado do nome da branch, ela vira nota de
    # desempenho individual — e a metrica nao foi desenhada para isso.
    linha_a1 = linha_de(md, "`A1`")
    ok("4,0 h" in md, "o TOTAL de hora humana esta la'", linha_de(md, "hora humana"))
    ok(linha_a1 and "4,0 h" not in linha_a1,
       "mas a linha da atividade nao tem hora humana", linha_a1)
    ok("humana" not in linha_a1, "nem a palavra", linha_a1)

    print("\nAs ressalvas viajam com o numero, nos tres artefatos")
    for nome, texto in (("markdown", md), ("html", html), ("readme", readme)):
        ok("teto" in texto and "fatura" in texto,
           f"{nome}: o custo e' dito TETO, e nao fatura")
        ok("declarado" in texto, f"{nome}: PF e' dito declarado")
        ok("de menos" in texto,
           f"{nome}: a atividade sem prova deixa o total DE MENOS, nao zero")
    ok("Z9" in md and "não atribuída" in md,
       "e a nao atribuida aparece SEM numero, nomeada", linha_de(md, "Z9"))
    ok("<meta charset=\"utf-8\">" in html,
       "o HTML declara o charset — sem ele a pagina abre 'MÃ©tricas'")
    ok(html.count("<html") == 1 and html.rstrip().endswith("</html>"),
       "e e' um documento inteiro, com cabeca e corpo fechados")

    print("\nRepublicar substitui entre as marcas, e nao empilha")
    saida = rodar(M.cmd_publicar, **args.__dict__)
    readme2 = (raiz / "README.md").read_text(encoding="utf-8")
    ok(readme2.count(P.INICIO) == 1 and readme2.count(P.FIM) == 1,
       "o bloco continua unico depois da segunda publicacao",
       f"{readme2.count(P.INICIO)} marcas de inicio")
    ok(saida.strip() == "",
       "e a republicacao calada nao diz nada", saida)

    print("\nExportar: o resumo cabe num link, e leva a ressalva junto")
    resumo = P.resumo_texto(projeto)
    ok(len(resumo) < 2000,
       f"o resumo tem {len(resumo)} caracteres — cabe em `mailto:` e em deep link")
    ok("teto de tabela de API, não fatura" in resumo and "DE MENOS" in resumo,
       "e nao perde as ressalvas no caminho", resumo[-200:])
    for gancho in ("b-teams", "b-email", "b-copiar", "window.print()", "@media print"):
        ok(gancho in html, f"a pagina tem {gancho}")

    for k, v in ambiente.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for d in TEMPORARIOS:
        limpar(d)

    # ----------------------------------------------------------------------
    print("\nCobertura: a raiz e' o REPOSITORIO, nao o diretorio da chamada")
    # ----------------------------------------------------------------------
    # Medido em 12/09/2026: coletando da raiz, 13 pastas e 52 transcritos; de
    # dentro de uma worktree, 2 e 39. O `.agents` ja' resolvia pelo
    # `--git-common-dir` e por isso a rodada feita na worktree SOBRESCREVIA o
    # `projeto.json` da raiz -- resultado parcial com a cara do completo.
    import subprocess as _sp
    from pathlib import Path as _P
    base = tempfile.mkdtemp()
    try:
        repo = _P(base) / "repo"
        repo.mkdir()
        _q = {"capture_output": True, "text": True}
        _sp.run(["git", "init", "-q", str(repo)], **_q)
        _sp.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                 "-m", "raiz", "--author", "t <t@t>"],
                env={**os.environ, "GIT_AUTHOR_NAME": "t",
                     "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                     "GIT_COMMITTER_EMAIL": "t@t"}, **_q)
        fora = _P(base) / "revisao-fora"
        r = _sp.run(["git", "-C", str(repo), "worktree", "add", "-q",
                     str(fora), "-b", "rev"], **_q)
        if r.returncode != 0:
            ok(False, "consegui criar a worktree do teste", r.stderr[:200])
        else:
            ok(M.raiz_principal(fora) == repo.resolve(),
               "de dentro de worktree FORA da raiz, a raiz resolvida e' o repo",
               f"{M.raiz_principal(fora)} != {repo.resolve()}")
            ok(M.raiz_principal(repo) == repo.resolve(),
               "e da propria raiz continua sendo ela", str(M.raiz_principal(repo)))
            ok(M.slug_do_projeto(M.raiz_principal(fora))
               == M.slug_do_projeto(M.raiz_principal(repo)),
               "entao as duas chamadas procuram a MESMA pasta de sessoes")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    # O `projeto.json` precisa DIZER o que enxergou. Duas rodadas com fator 4
    # de diferenca saiam indistinguiveis, e o unico vestigio era o campo `raiz`
    # -- que guardava o cwd e por isso enganou quem o leu.
    import inspect as _insp
    _fonte = _insp.getsource(M)
    ok('"chamado_de"' in _fonte and '"cobertura"' in _fonte,
       "e o projeto.json grava cobertura e de onde foi chamado")

    # O alcance e o teto EXISTIAM no projeto.json desde a 2.32.0 e a 2.34.0, e
    # nenhum dos dois chegava ao arquivo versionado: a rodada gritava na tela de
    # quem coletou e o README saia calado. Medido pelo `acme-backoffice`
    # em 12/09/2026, com US$ 90.628 publicados contra um teto de US$ 26.604.
    print("\nO que a gerência abre carrega o alcance — e grita quando o total inflou")
    _p = {"projeto": "t", "gerado_em": "2026-09-12 13:00:29",
          "cobertura": {"pastas": 13, "transcritos": 654, "nomes": []},
          "atividades": 23, "concluidas": 11, "custo_usd": 90628.92,
          "humano_h": 409.96, "interacoes": 4504, "turnos": 454776,
          "entrega": {"arquivos": 154, "insercoes": 43182, "remocoes": 78, "commits": 38},
          "lista": [], "nao_atribuidas": [],
          "teto_do_corpus": {"custo_usd": 26604.72, "registros_com_uso": 89361},
          "sobre_atribuicao": {"soma_atribuida_usd": 90628.92,
                               "teto_do_corpus_usd": 26604.72, "vezes": 3.41,
                               "o_que_significa": "..."},
          "parametros": {"teto_leitura_min": 10, "reentrada_min": 2}}
    _md = P.gerar_markdown(_p)
    _html = P.gerar_html(_p)
    _bloco = P.bloco_readme(_p, "docs/metricas.html", "docs/metricas.md")
    _res = P.resumo_texto(_p)
    for _nome, _texto in (("o markdown", _md), ("a página", _html),
                          ("o bloco do README", _bloco), ("o resumo de link", _res)):
        ok("26.604,72" in _texto and "3,41" in _texto,
           f"{_nome} diz que o total passou o teto do corpus, e em quantas vezes")
    ok(_res.splitlines()[1].startswith("ATENÇÃO"),
       "e no resumo o aviso é a SEGUNDA linha — o que se cola é o começo")
    ok(_md.index("inflado") < _md.index("US$ 90.628,92")
       and _bloco.index("inflado") < _bloco.index("US$ 90.628,92"),
       "o aviso vem ANTES do número inflado, não no rodapé")
    ok("654 transcritos em 13 pastas de sessão" in _md
       and "654 transcritos em 13 pastas de sessão" in _bloco
       and "654 transcritos em 13 pastas de sessão" in _html,
       "e os três dizem quantos transcritos e quantas pastas a rodada enxergou")
    _limpo = dict(_p)
    _limpo.pop("sobre_atribuicao")
    ok("inflado" not in P.gerar_markdown(_limpo)
       and "inflado" not in P.bloco_readme(_limpo, "a", "b"),
       "sem estouro da invariante, nenhum dos dois inventa aviso")
    ok("654 transcritos" in P.gerar_markdown(_limpo),
       "mas o alcance continua publicado — ele vale com a conta fechando também")


    print("\nUm turno é uma RESPOSTA de API, não um registro no arquivo")

    def _reg(uuid: str, msgid: str, saida: int, bloco: str = "text") -> str:
        return json.dumps({
            "type": "assistant", "uuid": uuid, "timestamp": "2026-09-19T10:00:00.000Z",
            "message": {"id": msgid, "model": "claude-opus-4-1",
                        "content": [{"type": bloco, "text": "x"}],
                        "usage": {"input_tokens": 2, "output_tokens": saida,
                                  "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0}}})

    def _saida_de(linhas: list[str]) -> float:
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "s.jsonl"
            arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            c = M.Corpus()
            return sum(o["uso"]["saida"] for o in c.registros(arq)
                       if o.get("type") == "assistant")

    # A canária que a sessão do app pediu: cópia tardia com a saída
    # ZERADA não pode apagar o turno. Guardar a última ocorrência trocaria um
    # número inflado por um deflacionado — que é pior, porque não acende luz.
    ok(_saida_de([_reg("u1", "m1", 500), _reg("u1", "m1", 0)]) == 500,
       "cópia com saída zerada não derruba o turno: vence o maior")
    ok(_saida_de([_reg("u1", "m1", 0), _reg("u1", "m1", 500)]) == 500,
       "e vence o maior TAMBÉM quando o zerado vem primeiro")

    # O mecanismo que a deduplicação por `uuid` NÃO alcança, e que era a maior
    # fatia: um registro por bloco de conteúdo, uuid diferente em cada, e o
    # `usage` INTEIRO repetido nos três.
    ok(_saida_de([_reg("u1", "m1", 500, "thinking"),
                  _reg("u2", "m1", 500, "text"),
                  _reg("u3", "m1", 500, "tool_use")]) == 500,
       "três blocos da MESMA resposta contam uma vez, apesar dos três uuids")

    # Instantâneo de streaming: mesma resposta, saída crescendo.
    ok(_saida_de([_reg("u1", "m1", 5), _reg("u1", "m1", 561)]) == 561,
       "instantâneo de streaming conta só o maior, que é o final")

    # E o sósia: respostas DIFERENTES continuam somando. Sem este caso o teste
    # aceitaria uma deduplicação que apaga trabalho de verdade.
    ok(_saida_de([_reg("u1", "m1", 500), _reg("u2", "m2", 300)]) == 800,
       "duas respostas diferentes somam as duas")

    # A soma não pode depender da ordem de leitura: o máximo é o mesmo em
    # qualquer ordem, e é isso que torna o número reproduzível.
    _linhas = [_reg("u1", "m1", 5), _reg("u2", "m1", 561, "tool_use"),
               _reg("u3", "m1", 0), _reg("u4", "m2", 42)]
    ok(_saida_de(_linhas) == _saida_de(list(reversed(_linhas))) == 603,
       "e a soma é a mesma lendo na ordem inversa")

    # O repetido continua no corpus: ele carrega a prova de vínculo.
    with tempfile.TemporaryDirectory() as _d:
        _a = Path(_d) / "s.jsonl"
        _a.write_text(_reg("u1", "m1", 500) + "\n" + _reg("u2", "m1", 500) + "\n",
                      encoding="utf-8")
        _c = M.Corpus()
        _regs = [o for o in _c.registros(_a) if o.get("type") == "assistant"]
        ok(len(_regs) == 2 and sum(1 for o in _regs if o.get("repetido")) == 1,
           "o registro repetido NÃO é descartado — só perde o uso")
        ok(_c.turnos_repetidos == 1, "e o corpus conta quantos foram")

    print("\nPercurso de ponta a ponta: do Histórico ao `relatar`")
    raiz, agents = cenario()
    _hist = ("\n## Histórico\n\n| Quando | Step | Nota |\n|---|---|---|\n"
             "| 2026-10-01 10:00:00 | 8 · Desenvolvedor | x |\n"
             "| 2026-10-01 11:00:00 | 9 · Revisor da Entrega | x |\n"
             "| 2026-10-01 11:30:00 | 8 · Desenvolvedor | achado |\n"
             "| 2026-10-01 12:00:00 | 9 · Revisor da Entrega | x |\n"
             "| 2026-10-01 12:30:00 | 10 · Portão humano · Entrega | x |\n"
             "| 2026-10-01 13:00:00 | concluída | ok |\n")
    _a = atividade(agents, "40001", titulo="Origem", trilha="curta",
                   status="concluido", branch="feat/x")
    _a.write_text(_a.read_text(encoding="utf-8") + _hist, encoding="utf-8")
    atividade(agents, "40002", titulo="Conserto", trilha="curta",
              status="em_andamento", branch="fix/x", corrige="40001")
    M.cmd_coletar(Args(raiz=str(raiz)))
    _proj = json.loads((agents / "metrics" / "projeto.json").read_text(encoding="utf-8"))
    ok(_proj["percurso"]["voltas"] == {"9→8": 1},
       "a coleta lê o Histórico do arquivo da atividade", str(_proj.get("percurso")))
    ok(_proj["percurso"]["bugs_que_escaparam"] == {"40001": ["40002"]},
       "e liga o conserto à entrega de onde o bug saiu")
    ok(coletado(agents, "40002")["corrige"] == "40001",
       "o registro do conserto guarda a origem")
    saida = rodar(M.cmd_relatar, raiz=str(raiz))
    ok("Percurso" in saida and "9→8 ×1" in saida and "1 de 1" in saida,
       "o `relatar` do projeto mostra voltas e bugs por trilha", saida[-900:])
    ok("É um PISO" in saida, "e diz que a taxa de bug é um piso")
    saida = rodar(M.cmd_relatar, raiz=str(raiz), atividade="40001")
    ok("bugs que escaparam desta entrega: 40002" in saida,
       "o drill-down da origem nomeia o conserto", saida[-600:])

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de metrics.py: tudo verde.")
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
    raise SystemExit(main())
