#!/usr/bin/env python3
"""Smoke test for the flow state tool.

Runs against a throwaway `.agents` in a temp directory, so it never touches the
real activity files. Stdlib only, no test runner: this ships in a zip and has to
run wherever the package lands.

    python3 test_smoke.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).parent.resolve()
sys.path.insert(0, str(AQUI))

import sys as _s; _s.path.insert(0, str(Path(__file__).resolve().parents[1] / "metrics"))
import flow_state  # noqa: E402
from flow_state import Atividade, FlowStateError, main  # noqa: E402

falhas: list[str] = []


def checar(condicao: bool, descricao: str, detalhe: str = "") -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)
        if detalhe:
            print("\n".join("        " + l for l in detalhe.splitlines()[-12:]))


def rodar(*argv: str) -> int:
    """Call the CLI. A parse error is a failure, not the end of the suite:
    argparse exits the process, which would otherwise stop the run in silence."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            return main(list(argv))
        except SystemExit as exc:
            return int(exc.code or 0)


def saida(*argv: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        with contextlib.suppress(SystemExit):
            main(list(argv))
    return buf.getvalue()


def codigo_e_saida(*argv: str) -> tuple[int, str]:
    """As duas coisas de UMA execução.

    Chamar `rodar` e depois `saida` executaria o comando duas vezes, e comando
    que muda estado não é idempotente: a segunda passada responderia sobre uma
    atividade diferente da primeira.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            codigo = main(list(argv))
        except SystemExit as exc:
            codigo = int(exc.code or 0)
    return codigo, buf.getvalue()


def erra(descricao: str, *argv: str) -> None:
    checar(rodar(*argv) == 1, descricao)


def main_teste() -> int:
    # `.resolve()` because on macOS /tmp is a symlink to /private/tmp and
    # `resolve_agents_dir` normalises what it returns.
    tmp = Path(tempfile.mkdtemp(prefix="elcamargo-flow-")).resolve()
    agents = tmp / ".agents"
    (agents / "atividades").mkdir(parents=True)
    anterior = os.environ.get("ELCAMARGO_AGENTS_DIR")
    os.environ["ELCAMARGO_AGENTS_DIR"] = str(agents)
    atividades = agents / "atividades"

    # A guarda do step relampago, DESLIGADA para o resto da suite -- e ligada
    # de volta na secao propria dela, mais abaixo.
    #
    # Ela recusa entrar em portao humano quando o step anterior foi aberto ha
    # segundos, e esta suite atravessa dez steps em milissegundos de proposito.
    # Sem desligar, metade dos casos passaria a exercitar `--forcar`, que e' um
    # caminho diferente do que eles existem para provar. O zero e' o mesmo que
    # um projeto que roteiriza o fluxo declara em `[fluxo]`.
    flow_state.SEGUNDOS_DE_STEP_RELAMPAGO = 0

    try:
        print("Resolução")
        checar(flow_state.resolve_agents_dir() == agents,
               "ELCAMARGO_AGENTS_DIR tem precedência")
        vazio = tmp / "vazio"
        vazio.mkdir()
        os.environ["ELCAMARGO_AGENTS_DIR"] = str(vazio / "nao-existe")
        try:
            flow_state.resolve_agents_dir()
            checar(False, "env var apontando para inexistente falha")
        except FlowStateError:
            checar(True, "env var apontando para inexistente falha")
        os.environ["ELCAMARGO_AGENTS_DIR"] = str(agents)
        checar(not flow_state._parece_agents(vazio),
               "diretório sem marca do fluxo não passa por .agents")
        checar(flow_state._parece_agents(agents),
               "diretório com atividades/ passa")

        print("\nIdentificador")
        for ruim in ("a/b", "../fora", "", ".oculto", "a b"):
            erra(f"id {ruim!r} é recusado", "iniciar", ruim, "--titulo", "x")
        checar(not list(agents.glob("fora.md")),
               "nenhum id conseguiu escapar do diretório")

        print("\nCiclo de vida")
        checar(rodar("iniciar", "T-1", "--titulo", "Atividade de teste",
                     "--trilha", "completa") == 0, "iniciar")
        arq = atividades / "T-1.md"
        checar(arq.exists(), "arquivo da atividade criado")
        checar((agents / flow_state.INDEX_NAME).exists(), "índice gerado")
        erra("iniciar duas vezes é recusado", "iniciar", "T-1", "--titulo", "dup")

        print("\nAvanço e portões")
        checar(rodar("avancar", "T-1") == 0, "avancar segue a trilha")
        checar(Atividade.ler(arq).step == 2, "chegou no step 2")
        erra("retrocesso é recusado", "avancar", "T-1", "--step", "1")
        erra("step inexistente é recusado", "avancar", "T-1", "--step", "99")
        erra("--forcar sem --nota é recusado",
             "avancar", "T-1", "--step", "1", "--forcar")
        checar(rodar("avancar", "T-1", "--step", "1", "--forcar",
                     "--nota", "volta de correção") == 0,
               "--forcar com --nota permite o retrocesso")

        print("\nPortão humano")
        # Dois portões humanos no meio da trilha completa: 5 (especificação) e
        # 7 (telas). Nenhum pode ser atravessado sem --forcar.
        rodar("iniciar", "G", "--titulo", "Gate", "--trilha", "completa")
        for destino in ("2", "3", "4"):
            rodar("avancar", "G", "--step", destino, "--nota", "ok")
        checar(Atividade.ler(atividades / "G.md").step == 4, "chegou ao step 4")
        erra("pular o step 5 humano é recusado", "avancar", "G", "--step", "6")
        texto = saida("avancar", "G", "--step", "6")
        checar("portão humano" in texto, "e o erro diz que há portão no caminho")
        erra("pular direto para o 10 é recusado", "avancar", "G", "--step", "10")
        checar(rodar("avancar", "G") == 0, "o próximo da trilha passa")
        checar(Atividade.ler(atividades / "G.md").step == 5,
               "e é exatamente o step 5")
        rodar("avancar", "G", "--nota", "spec aprovada")
        checar(Atividade.ler(atividades / "G.md").step == 6, "chegou ao step 6")
        erra("pular o step 7 humano é recusado", "avancar", "G", "--step", "8")
        texto = saida("avancar", "G", "--step", "8")
        checar("portão humano" in texto,
               "e o erro nomeia o portão das telas")

        print("\nTrilha rapida — o Fluxo Rapido")
        checar(rodar("iniciar", "RAP", "--titulo", "Rapida",
                     "--trilha", "rapida") == 0, "iniciar na trilha rapida")
        _rap = Atividade.ler(agents / "atividades" / "RAP.md")
        checar(_rap.proximo_step() == 3, "a rapida pula o step 2")
        rodar("avancar", "RAP", "--nota", "x")
        _rap = Atividade.ler(agents / "atividades" / "RAP.md")
        checar(_rap.proximo_step() == 6,
               "e pula o 4 e o 5: do analista de sistema direto para a tela")
        rodar("avancar", "RAP", "--nota", "x")
        _rap = Atividade.ler(agents / "atividades" / "RAP.md")
        checar(_rap.proximo_step() == 8, "e o 7: da tela direto para o codigo")

        # O preco da trilha fica ESCRITO, e nao so' impresso: quem le' o
        # portao 10 tem de achar o que nao foi conferido no meio.
        _texto = (agents / "atividades" / "RAP.md").read_text(encoding="utf-8")
        checar("TRILHA `rapida`" in _texto and "FORA DA TRILHA" in _texto,
               "o que a rapida deixou de conferir entra no historico")
        checar(len(flow_state.avisos_da_trilha("rapida")) == 4,
               "e sai como aviso na hora da escolha: 4, 5, 7 e o preco")
        # A `curta` nao produz o que o 5 e o 7 confeririam, entao o aviso
        # GENERICO nao tem o que dizer — e havia o que dizer: o step 9 dela
        # cobre tres das seis dimensoes. Ate' 2.42.0 este teste afirmava
        # `== []`, e a afirmacao prendia a crenca errada no lugar.
        _curta = flow_state.avisos_da_trilha("curta")
        checar(_curta and all("FORA DA TRILHA" not in a for a in _curta),
               "a curta avisa, e NAO por portao ausente: ela nao produz o que "
               "o 5 e o 7 confeririam")
        checar(any("TRÊS DE SEIS" in a for a in _curta),
               "o aviso dela e' sobre a cobertura do step 9, que e' o que ela "
               "de fato perde")
        checar(flow_state.avisos_da_trilha("completa") == [],
               "a completa continua muda: nao deixa nenhuma conferencia de fora")

        print("\nTrilha ultra-rapida — pedida pela gerencia, nao recomendada")
        checar(flow_state.TRILHAS["ultra-rapida"] == [1, 3, 6, 8, 10],
               "a ultra-rapida e' a rapida SEM o step 9")
        checar(rodar("iniciar", "ULT", "--titulo", "Ultra",
                     "--trilha", "ultra-rapida") == 0, "iniciar na ultra-rapida")
        _ult = Atividade.ler(agents / "atividades" / "ULT.md")
        checar(_ult.proximo_step() == 3, "pula o step 2")
        rodar("avancar", "ULT", "--nota", "x")
        rodar("avancar", "ULT", "--nota", "x")
        _ult = Atividade.ler(agents / "atividades" / "ULT.md")
        checar(_ult.proximo_step() == 8, "e o 4, o 5 e o 7")
        rodar("avancar", "ULT", "--nota", "x")
        _ult = Atividade.ler(agents / "atividades" / "ULT.md")
        checar(_ult.proximo_step() == 10,
               "do desenvolvedor DIRETO ao portao humano, sem o step 9")

        _avisos = flow_state.avisos_da_trilha("ultra-rapida")
        checar(any("9 · Revisor da Entrega" in a for a in _avisos),
               "o step 9 ausente e' acusado pelo aviso GENERICO — foi para isso "
               "que o `9: 8` entrou no mapa de conferidores")
        checar(any("NÃO SEGURA NADA" in a for a in _avisos),
               "e o concluir que nao segura nada e' dito a parte: nenhum aviso "
               "generico alcancaria isso")
        checar(len(_avisos) > len(flow_state.avisos_da_trilha("rapida")),
               "ela avisa MAIS que a rapida, porque tira mais")
        _txt = (agents / "atividades" / "ULT.md").read_text(encoding="utf-8")
        checar("TRILHA `ultra-rapida`" in _txt,
               "e o preco entra no historico, para o portao 10 achar")

        print("\nO par especificacao -> construcao")
        # A propriedade que torna o par seguro, e que nao se ve olhando as duas
        # listas separadas: somadas dao a `completa`, e so o step 1 se repete.
        _e = set(flow_state.TRILHAS["especificacao-completa"])
        _c = set(flow_state.TRILHAS["construcao"])
        checar(sorted(_e | _c) == flow_state.TRILHAS["completa"],
               "especificacao-completa U construcao == completa: o corte nao perde step")
        checar(sorted(_e & _c) == [1],
               "e a intersecao e so o step 1, que cada uma precisa para abrir")

        # A porta para quem esta na `sistema`: card claro, sem step 2. Sem ela,
        # quem nao tem analise de negocio a revisar ou era obrigado ao step 2 ou
        # batia no guarda da construcao — que estava certo em recusar.
        _es = set(flow_state.TRILHAS["especificacao-sistema"])
        checar(sorted(_es | _c) == flow_state.TRILHAS["sistema"],
               "especificacao-sistema U construcao == sistema")
        checar(sorted(_es & _c) == [1],
               "e tambem so o step 1 em comum")
        checar(2 not in _es and 2 in _e,
               "a diferenca entre as duas especificacoes e o step 2, e so ele")
        checar(flow_state.SUFIXO_DE_ESCOPO["especificacao-sistema"]
               == flow_state.SUFIXO_DE_ESCOPO["especificacao-completa"],
               "as duas usam o MESMO sufixo de id: do lado do dev nao importa "
               "qual produziu a spec")
        checar(flow_state.id_da_outra_metade("1081-especificacao",
                                             "especificacao-sistema")
               == "1081-construcao",
               "e o par se acha a partir da variante tambem")
        _avs = flow_state.avisos_da_trilha("especificacao-sistema")
        checar(any("SEM O STEP 2" in a for a in _avs),
               "ela avisa que e para card ja claro")
        checar(all(a in _avs for a in
                   flow_state.AVISOS_PROPRIOS_DA_TRILHA["especificacao-completa"]),
               "e HERDA os avisos da especificacao em vez de copia-los")
        checar(not any("portão 5 e para" in a for a in
                       flow_state.avisos_da_trilha("especificacao-completa")),
               "e nenhuma das duas diz que para no portao 5: a tela levou as "
               "duas ate o 7")

        # Sem a especificacao, a construcao RECUSA — em vez de degradar em
        # silencio para uma curta, que e o modo de falha que o par existe para
        # impedir.
        _t = saida("iniciar", "77001-construcao", "--titulo", "Sem spec",
                   "--trilha", "construcao")
        checar("roda DEPOIS" in _t and "77001-especificacao" in _t,
               "a construcao recusa abrir sem a especificacao, e a NOMEIA")
        checar("curta" in _t and "três das seis" in _t,
               "e diz POR QUE recusa: sem spec ela vira uma curta")

        checar(rodar("iniciar", "77001-especificacao", "--titulo", "A spec",
                     "--trilha", "especificacao-completa") == 0, "a especificacao abre")
        _esp = Atividade.ler(agents / "atividades" / "77001-especificacao.md")
        checar(_esp.proximo_step() == 2, "e comeca no step 2")
        rodar("artefato", "77001-especificacao", "--tipo", "sdd-negocio",
              "--caminho", "docs/neg.md")
        rodar("artefato", "77001-especificacao", "--tipo", "sdd-sistema",
              "--caminho", "docs/sis.md")
        rodar("artefato", "77001-especificacao", "--tipo", "decisoes-ux",
              "--caminho", "docs/tela.md")
        for _ in range(6):
            rodar("avancar", "77001-especificacao", "--nota", "x")
        _esp = Atividade.ler(agents / "atividades" / "77001-especificacao.md")
        checar(_esp.step == 7, "e vai ate o portao 7: a tela e do analista")
        rodar("concluir", "77001-especificacao")

        # Aberta a construcao, os artefatos da spec vem junto. E o que separa
        # esta trilha de uma curta: com eles o step 9 roda as seis frentes.
        _t = saida("iniciar", "77001-construcao", "--titulo", "A obra",
                   "--trilha", "construcao")
        checar("herdei" in _t and "sdd-sistema" in _t,
               "a construcao HERDA os artefatos da especificacao, e diz quais")
        _con = Atividade.ler(agents / "atividades" / "77001-construcao.md")
        _tipos = {a[0] for a in _con.artefatos}
        checar({"sdd-negocio", "sdd-sistema", "decisoes-ux"} <= _tipos,
               "negocio, sistema E tela chegaram como artefatos DESTA atividade")
        checar(_con.meta.get("herdou_de") == "77001-especificacao",
               "e o estado diz de quem herdou — sem isso ninguem reconstitui")
        checar(_con.proximo_step() == 8,
               "ela vai direto ao step 8 — MESMA forma da curta, e a diferenca "
               "inteira e o que herdou")

        # O CONTROLE que a sessao do backoffice propos: abrir uma `construcao`
        # herdando de cada uma das duas especificacoes e ver se a lista de
        # frentes muda. Se sair igual nas duas, o numero esta fixo — e uma
        # frente sem baseline nao fica quieta, ela INFERE.
        print("\nA baseline do step 9 sai do ARTEFATO, nao do nome da trilha")
        rodar("iniciar", "77002-especificacao", "--titulo", "So sistema",
              "--trilha", "especificacao-sistema")
        rodar("artefato", "77002-especificacao", "--tipo", "sdd-sistema",
              "--caminho", "docs/sis2.md")
        for _ in range(5):
            rodar("avancar", "77002-especificacao", "--nota", "x")
        rodar("concluir", "77002-especificacao")
        rodar("iniciar", "77002-construcao", "--titulo", "Obra 2",
              "--trilha", "construcao")

        _c1 = Atividade.ler(agents / "atividades" / "77001-construcao.md")
        _c2 = Atividade.ler(agents / "atividades" / "77002-construcao.md")
        _com1, _sem1 = flow_state.frentes_com_baseline(_c1)
        _com2, _sem2 = flow_state.frentes_com_baseline(_c2)
        checar(_sem1 == [],
               "vinda da especificacao-COMPLETA: as duas frentes tem baseline")
        checar(_sem2 == ["implemented-business"],
               "vinda da especificacao-SISTEMA: a de negocio NAO tem, porque o "
               "step 2 nunca rodou")
        checar(_com1 != _com2,
               "a lista MUDA entre as duas — se saisse igual, o numero estaria "
               "fixo e uma frente reviaria contra documento inexistente")
        rodar("avancar", "77002-construcao", "--nota", "vai ao 8")
        _t = saida("avancar", "77002-construcao", "--nota", "vai ao 9")
        checar("SEM BASELINE" in _t and "sdd-negocio" in _t,
               "e o avancar para o step 9 IMPRIME qual frente ficou sem, e o "
               "que falta")
        checar("INFERE" in _t,
               "dizendo por que nao rodar: frente sem baseline nao fica quieta")

        # As duas frentes que ESCREVEM rodam em worktree propria, e worktree
        # nasce do que esta COMMITADO. Entrega viva na arvore chega la como
        # base limpa, e a frente mede o codigo de antes — que numa volta de
        # correcao PARECE confirmacao de conserto.
        print("\nEntrega nao commitada ao entrar no step 9")
        _a3 = Atividade.ler(agents / "atividades" / "77002-construcao.md")
        import subprocess as _sp, tempfile as _tf
        # A atividade nasceu pelo `iniciar`, entao o lugar dela e' PENDENTE —
        # e sem arvore declarada NAO HA O QUE CONTAR. Ate 2.45.5 o contador
        # caia na raiz do projeto e, se ela estivesse limpa, devolvia ZERO:
        # "nao sei" saindo com a cara de "entrega commitada".
        # A ADOCAO do lugar PENDENTE nao se confere aqui: ela dependeria de o
        # cwd DA SUITE estar dentro de um repositorio, e este pacote roda de
        # dentro de um zip extraido, onde nao esta. Ela e' conferida pela linha
        # de comando, contra um repositorio proprio, em "O lugar da atividade".
        # Com o campo em aberto nao ha o que contar. Ate 2.45.5 o contador
        # caia na raiz do projeto e, se ela estivesse limpa, devolvia ZERO:
        # "nao sei" saindo com a cara de "entrega commitada".
        _a3.meta["worktree"] = flow_state.LUGAR_PENDENTE
        _n0, _onde0 = flow_state.entrega_nao_commitada(_a3)
        checar(_n0 is None,
               "sem arvore declarada a contagem devolve None, nao zero")
        checar(_onde0 == flow_state.LUGAR_PENDENTE,
               "e diz por que nao contou, em vez de nomear uma arvore qualquer")
        # Repositorio de verdade, para a contagem ser conferivel em vez de
        # vacuamente verdadeira.
        _r = Path(_tf.mkdtemp(prefix="entrega-"))
        _sp.run(["git", "init", "-q", str(_r)], check=False)
        _a3.meta["worktree"] = str(_r)
        checar(flow_state.entrega_nao_commitada(_a3)[0] == 0,
               "arvore limpa conta ZERO — senao o aviso sairia sempre")
        (_r / "entrega.ts").write_text("x\n", encoding="utf-8")
        (_r / "outra.ts").write_text("y\n", encoding="utf-8")
        _n, _onde = flow_state.entrega_nao_commitada(_a3)
        checar(_n == 2,
               "duas entradas vivas contam DUAS: e o numero que vai no aviso")
        checar(_onde == str(_r),
               "e ele DIZ qual arvore contou — o campo `worktree` ja nasceu "
               "errado tres vezes num dia, quando era herdado do cwd")

        # O controle: campo apontando para arvore ALHEIA e suja. O contador nao
        # tem como saber que e' a errada — mas quem le' tem, se ele disser qual.
        _alheia = Path(_tf.mkdtemp(prefix="alheia-"))
        _sp.run(["git", "init", "-q", str(_alheia)], check=False)
        for _i in range(3):
            (_alheia / f"de-outra-sessao-{_i}.md").write_text("x\n", encoding="utf-8")
        _a3.meta["worktree"] = str(_alheia)
        _n2, _onde2 = flow_state.entrega_nao_commitada(_a3)
        checar(_n2 == 3 and _onde2 == str(_alheia),
               "campo apontando para outra arvore conta a sujeira DELA — e o "
               "aviso nomeia a arvore, que e o que torna o erro visivel")

        # O `iniciar` NAO herda a arvore do cwd. Quem roda o `iniciar` esta,
        # por definicao, num lugar que nao e' o da atividade: e' o step 1 que
        # cria a branch e a worktree, DEPOIS. Ate 2.45.5 o campo nascia do
        # cwd, e em 21/09/2026 tres aberturas seguidas nasceram apontando para
        # a arvore principal de quem abriu o card, corrigidas a mao depois.
        print("\nO lugar nasce PENDENTE, e nao herdado do cwd")
        _cwd_alheio = Path(_tf.mkdtemp(prefix="cwd-de-quem-chama-")).resolve()
        _sp.run(["git", "init", "-q", str(_cwd_alheio)], check=False)
        _sp.run(["git", "-C", str(_cwd_alheio), "commit", "-q", "--allow-empty",
                 "-m", "base"],
                env={**os.environ, "GIT_AUTHOR_NAME": "t",
                     "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                     "GIT_COMMITTER_EMAIL": "t@t"},
                capture_output=True, text=True, encoding="utf-8", errors="replace")
        _volto_para = os.getcwd()
        try:
            os.chdir(_cwd_alheio)
            # O CONTROLE, sem o qual o teste passaria por falta de git em vez
            # de por conserto: daqui o `contexto_git` TEM um lugar a oferecer.
            _oferta = flow_state.contexto_git(agents)
            checar(bool(_oferta.get("worktree")) and bool(_oferta.get("branch")),
                   "controle: daqui havia um lugar para herdar — o teste nao "
                   "passa por falta de git")
            rodar("iniciar", "77009", "--titulo", "Aberta de dentro de uma arvore",
                  "--trilha", "curta")
        finally:
            os.chdir(_volto_para)
        _a9 = Atividade.ler(agents / "atividades" / "77009.md")
        checar(_a9.meta.get("worktree") == flow_state.LUGAR_PENDENTE,
               "worktree sai PENDENTE, e NAO o caminho do cwd")
        checar(str(_cwd_alheio) not in str(_a9.meta.get("worktree", "")),
               "nem como prefixo — era ESTE caminho que o campo herdava")
        checar(_a9.meta.get("branch") == flow_state.LUGAR_PENDENTE,
               "e a branch idem: meia localizacao e' a outra metade errada")
        # Quem JA sabe o lugar continua podendo declarar.
        rodar("iniciar", "77010", "--titulo", "Com lugar declarado",
              "--trilha", "curta", "--branch", "feat/ja-sei",
              "--worktree", str(_cwd_alheio))
        _a10 = Atividade.ler(agents / "atividades" / "77010.md")
        checar(_a10.meta.get("branch") == "feat/ja-sei"
               and _a10.meta.get("worktree") == str(_cwd_alheio),
               "as bandeiras declaram o lugar de quem ja o conhece")

        # O guarda tem de alcancar TODAS as trilhas, nao so o par novo: o caso
        # que disparou no backoffice era uma `sistema` comum — cinco frentes
        # pela tabela, "seis rodaram" no relatorio, zero nomeadas.
        rodar("iniciar", "77003", "--titulo", "Sistema sem negocio",
              "--trilha", "sistema")
        rodar("artefato", "77003", "--tipo", "sdd-sistema",
              "--caminho", "docs/sis3.md")
        for _ in range(6):
            rodar("avancar", "77003", "--nota", "x")
        _t = saida("avancar", "77003", "--nota", "chega no 9")
        checar("SEM BASELINE" in _t and "sdd-negocio" in _t,
               "o aviso de baseline vale para a `sistema` tambem, nao so para "
               "o par novo")
        _a = Atividade.ler(agents / "atividades" / "77003.md")
        checar(any("Baseline do step 9" in (n or "") for _, _, n in _a.history),
               "e fica GRAVADO no historico: quem reconstituir depois acha")

        print("\nTrilha revisao — conferir o trabalho de outra pessoa")
        checar(rodar("iniciar", "REV", "--titulo", "Revisao do card do fulano",
                     "--trilha", "revisao") == 0, "iniciar na trilha revisao")
        _rev = Atividade.ler(agents / "atividades" / "REV.md")
        checar(_rev.trilha == [1, 2, 4, 9, 10], "a trilha e' 1, 2, 4, 9, 10")
        checar(_rev.proximo_step() == 2,
               "o step 2 roda: o card e' a baseline, mesmo se o dev documentou")
        rodar("avancar", "REV", "--nota", "x")
        _rev = Atividade.ler(agents / "atividades" / "REV.md")
        checar(_rev.proximo_step() == 4, "e do 2 vai para o 4, sem passar pelo 3")
        rodar("avancar", "REV", "--nota", "x")
        _rev = Atividade.ler(agents / "atividades" / "REV.md")
        checar(_rev.proximo_step() == 9, "do 4 direto para a revisao da entrega")
        rodar("avancar", "REV", "--nota", "x")
        _rev = Atividade.ler(agents / "atividades" / "REV.md")
        checar(_rev.proximo_step() == 10, "e do 9 para o portao humano")

        # A forma da trilha e' o que a torna segura: sem step 8, o step 9 nao
        # tem a quem devolver correcao. Isto nao e' detalhe -- e' a garantia de
        # que a revisao nao conserta o codigo de outra pessoa.
        checar(8 not in _rev.trilha,
               "NAO tem step 8: o 9 nao tem a quem devolver, entao nao conserta")
        checar(3 not in _rev.trilha,
               "nem step 3: ela confere o que existe, nao especifica de novo")

        _avisos = " ".join(flow_state.avisos_da_trilha("revisao"))
        checar("NÃO CONSERTA NADA" in _avisos,
               "o iniciar avisa que a trilha nao conserta")
        checar("não commita" in _avisos and "card de outra pessoa" in _avisos,
               "e que ela nao commita nem escreve no card alheio")
        checar("worktree" in _avisos,
               "e que roda em worktree, para o trabalho da maquina nao parar")
        _texto = (agents / "atividades" / "REV.md").read_text(encoding="utf-8")
        checar("TRILHA `revisao`" in _texto,
               "e o preco/natureza dela fica ESCRITO no historico")
        # Os avisos proprios nao vazam para quem nao os tem.
        checar(not any("TRILHA DE REVISÃO" in a
                       for a in flow_state.avisos_da_trilha("curta")),
               "os avisos da revisao nao vazam para a curta")

        print("\nA sessao se REGISTRA na atividade, em vez de ser adivinhada")
        # Ate 11/09/2026 a metrica atribuia por duas inferencias -- a branch do
        # repositorio principal e o `cwd`. As duas erraram no mesmo caso
        # medido: uma revisao inteira, 1.708 registros, teve o custo somado a'
        # atividade VIZINHA, porque o checkout principal por acaso estava na
        # branch dela. O zero da revisao a ferramenta declarava; a contaminacao
        # da vizinha ela AFIRMAVA, com `atribuicao: ok`.
        (agents / ".sessao-atual").write_text("sessao-A", encoding="utf-8")
        rodar("iniciar", "SESS", "--titulo", "Rev", "--trilha", "revisao")
        _s = Atividade.ler(agents / "atividades" / "SESS.md")
        checar(_s.meta.get("sessoes") == "sessao-A",
               "o `iniciar` grava quem rodou o comando")

        (agents / ".sessao-atual").write_text("sessao-B", encoding="utf-8")
        rodar("avancar", "SESS", "--nota", "x")
        _s = Atividade.ler(agents / "atividades" / "SESS.md")
        checar(_s.meta.get("sessoes") == "sessao-A sessao-B",
               "e a segunda sessao ACRESCENTA -- atividade atravessa sessoes")

        rodar("avancar", "SESS", "--nota", "y")
        _s = Atividade.ler(agents / "atividades" / "SESS.md")
        checar(_s.meta.get("sessoes") == "sessao-A sessao-B",
               "e a mesma sessao nao duplica")

        # O erro possivel do `.sessao-atual` -- duas sessoes no mesmo projeto ao
        # mesmo tempo -- ACRESCENTA uma entrada, nunca troca a dona. E' por isso
        # que o campo e' lista.
        (agents / ".sessao-atual").write_text("", encoding="utf-8")
        rodar("avancar", "SESS", "--nota", "z")
        _s = Atividade.ler(agents / "atividades" / "SESS.md")
        checar(_s.meta.get("sessoes") == "sessao-A sessao-B",
               "sem sessao no arquivo, nao inventa nem apaga o que havia")
        (agents / ".sessao-atual").unlink(missing_ok=True)

        print("\nSessao declarada: a prova e' o COMANDO, nao o pertencimento")
        # Defeito da 2.29.0, achado ao medir a pergunta do reviewer. Com a
        # sessao inteira virando prova, a janela por ilhas vira uma ilha so' e
        # a atividade engole a sessao inteira -- duas atividades declarando a
        # MESMA sessao, com datas disjuntas, reivindicavam cada uma o total.
        #
        # E o caso e' a MAIORIA: das sessoes que escrevem estado, 41% no
        # backoffice e 80% no app operam mais de uma atividade. Numa janela
        # so', em sequencia -- como trabalha quem tem maquina fraca.
        import metrics as _m  # noqa: PLC0415
        _reg = {"comandos": "python3 flow_state.py avancar ABC-1 --nota x"}
        checar(_m.operou_a_atividade(_reg, "ABC-1"),
               "`avancar` com o id e' prova de que a sessao OPEROU a atividade")
        checar(not _m.operou_a_atividade(_reg, "ABC-2"),
               "e nao vale para o id de outra atividade")
        checar(not _m.operou_a_atividade(
                   {"comandos": "python3 flow_state.py status ABC-1"}, "ABC-1"),
               "`status` NAO e' prova: olhar o board nao e' conduzir")
        checar(not _m.operou_a_atividade({"comandos": ""}, "ABC-1"),
               "e registro sem comando nenhum nao prova nada -- e' o que fazia "
               "a sessao inteira virar uma ilha so'")

        print("\nWorktree detached: `branch: HEAD` nao descreve lugar nenhum")
        # A trilha `revisao` abre worktree no commit do dev -- detached por
        # desenho --, e `rev-parse --abbrev-ref HEAD` devolve a string literal
        # "HEAD". Dois commits diferentes gravariam o mesmo texto. A primeira
        # revisao real, em 11/09/2026, gravou `branch: HEAD` e precisou de
        # `corrigir --forcar` para se recuperar.
        _t = Path(tempfile.mkdtemp(prefix="flow-detached-")).resolve()
        _repo = _t / "repo"; _repo.mkdir()
        def _g(*a, cwd=_repo):
            return subprocess.run(["git", *a], cwd=cwd, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout.strip()
        _g("init", "-q", "-b", "main")
        (_repo / "a.txt").write_text("um\n", encoding="utf-8")
        _g("add", ".")
        _g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "um")
        _sha = _g("rev-parse", "HEAD")
        # Como um `fetch` deixaria: a branch do dev existe so' como ref remota.
        _g("update-ref", "refs/remotes/origin/feat/do_dev", _sha)
        _g("update-ref", "refs/remotes/origin/HEAD", _sha)
        _wt = _t / "revisao"
        _g("worktree", "add", "--detach", str(_wt), _sha)

        checar(_g("rev-parse", "--abbrev-ref", "HEAD", cwd=_wt) == "HEAD",
               "o git cru realmente devolve a string `HEAD` na arvore detached")
        checar(flow_state.nome_do_ponto(_wt) == "origin/feat/do_dev",
               "e o pacote cai para a ref REMOTA que aponta para o commit")
        checar(flow_state.nome_do_ponto(_repo) == "main",
               "a branch local continua ganhando quando existe")

        # `refs/remotes/origin/HEAD` encurta para `origin` -- filtrar pelo nome
        # CURTO deixaria o ponteiro simbolico passar como se fosse um lugar.
        _g("update-ref", "-d", "refs/remotes/origin/feat/do_dev")
        _ponto = flow_state.nome_do_ponto(_wt)
        checar(_ponto != "origin",
               "o ponteiro simbolico `origin/HEAD` NAO vira o nome do lugar")
        _g("update-ref", "-d", "refs/remotes/origin/HEAD")
        checar(flow_state.nome_do_ponto(_wt).startswith("detached:"),
               "sem ref nenhuma, sobra o commit -- feio, mas identifica")
        # E o `corrigir` tem que aceitar a ref remota SEM --forcar: e' o lugar
        # legitimo de uma worktree de revisao, e gastar a saida de emergencia
        # no caso normal da trilha ensina a usar --forcar por habito.
        _g("update-ref", "refs/remotes/origin/feat/do_dev", _sha)
        rodar("iniciar", "DET", "--titulo", "Revisao", "--trilha", "revisao")
        _c, _o = codigo_e_saida("corrigir", "DET",
                                "--branch", "origin/feat/do_dev",
                                "--worktree", str(_wt),
                                "--nota", "worktree da branch do dev")
        checar(_c == 0, "`corrigir` aceita `origin/...` sem --forcar")
        _det = Atividade.ler(agents / "atividades" / "DET.md")
        checar(_det.meta.get("branch") == "origin/feat/do_dev",
               "e grava a ref remota como lugar da atividade")
        _c, _o = codigo_e_saida("corrigir", "DET", "--branch", "nao/existe",
                                "--worktree", str(_wt), "--nota", "x")
        checar(_c != 0, "e continua recusando o que nao existe em lugar nenhum")
        checar("nem como referência remota" in _o,
               "e o erro nomeia os tres lugares onde procurou")

        shutil.rmtree(_t, ignore_errors=True)

        print("\nTrilha revisao: o vermelho e' o PRODUTO, nao divida")
        # Em 11/09/2026 uma revisao fechou com `perfis` em `falhou`: dos doze
        # pares exercitados com ator e sessao reais, dez provaram o que o perfil
        # NAO pode, e os dois que falharam eram o bloqueador e uma alta, ja
        # publicados no PR. Nao havia caminho que tornasse aquilo verde -- a
        # trilha nao conserta, nao commita e nao faz push -- e o `concluir`
        # recusou encerrar. A saida tentadora, re-registrar como `ok`, apagaria
        # do historico o achado que a revisao existiu para produzir.
        rodar("iniciar", "REV2", "--titulo", "Revisao do PR", "--trilha", "revisao")
        for _ in range(4):
            rodar("avancar", "REV2", "--nota", "x")
        rodar("conferencia", "REV2", "--ferramenta", "perfis",
              "--veredicto", "falhou", "--detalhe", "2 perfil(is), 12 linha(s)")

        _c, _o = codigo_e_saida("concluir", "REV2")
        checar(_c != 0, "sem nota, `falhou` na revisao ainda recusa encerrar")
        checar("NAO e' divida" in _o.replace("Ã","").replace("\u00c3","")
               or "NÃO é dívida" in _o,
               "e o erro diz que ali o vermelho e' o produto, nao divida")
        checar("ONDE o achado foi publicado" in _o,
               "e exige que a nota diga onde o achado foi publicado")
        checar("NÃO re-registre" in _o or "NAO re-registre" in _o,
               "e desaconselha a saida tentadora de re-registrar como `ok`")

        checar(rodar("concluir", "REV2", "--nota",
                     "36 achados publicados no PR 2210, 3 threads") == 0,
               "COM nota, encerra sem --forcar: o vermelho nao trava a revisao")
        _texto = (agents / "atividades" / "REV2.md").read_text(encoding="utf-8")
        checar("ACHADOS QUE FECHARAM EM `falhou`" in _texto,
               "e o vermelho entra no HISTORICO, sem depender de alguem escrever")
        checar("perfis" in _texto.split("ACHADOS QUE FECHARAM")[1][:200],
               "nomeando a ferramenta que ficou vermelha")

        print("\nVocabulario de artefato: o chute e' registrado E acusado")
        # No primeiro uso da trilha o entregavel foi registrado como
        # `comentario-pr`, no chute, e o comando aceitou calado. O artefato
        # ficou gravado e invisivel para quem o procurasse pelo nome.
        _c, _o = codigo_e_saida("artefato", "REV2", "--tipo", "comentario-pr",
                                "--caminho", "PR 2210 thread 3301")
        checar(_c == 0, "tipo fora do vocabulario NAO recusa o registro")
        checar("FORA DO VOCABULÁRIO" in _o, "mas acusa, em vez de aceitar calado")
        checar("revisao-publicada" in _o, "e lista os tipos reconhecidos")
        _texto = (agents / "atividades" / "REV2.md").read_text(encoding="utf-8")
        checar("comentario-pr" in _texto,
               "e o artefato fica gravado: perder o registro e' pior que o rotulo errado")

        _c, _o = codigo_e_saida("artefato", "REV2", "--tipo", "revisao-publicada",
                                "--caminho", "PR 2210 thread 3301")
        checar(_c == 0 and "FORA DO VOCABULÁRIO" not in _o,
               "o tipo certo da trilha `revisao` passa sem aviso")

        print("\nTrilha revisao: conferencia da PROPRIA passada tambem segura")
        # A regra da 2.26.0 -- `falhou` nao trava na `revisao` -- vale para o
        # que a revisao ACHA, nao para o que diz se ela e' confiavel. `arvore:
        # falhou` nunca e' achado sobre o outro dev: quer dizer que uma frente
        # escreveu na arvore compartilhada e as outras leram por cima.
        for _f, _esperado in (("perfis", 0), ("execucao", 0),
                              ("arvore", 1), ("memoria", 1)):
            _id = f"HIG-{_f}"
            rodar("iniciar", _id, "--titulo", "Rev", "--trilha", "revisao")
            for _ in range(4):
                rodar("avancar", _id, "--nota", "x")
            rodar("conferencia", _id, "--ferramenta", _f,
                  "--veredicto", "falhou", "--detalhe", "x")
            _c, _o = codigo_e_saida("concluir", _id, "--nota", "publicada no PR")
            if _esperado:
                checar(_c != 0,
                       f"`{_f}: falhou` SEGURA -- e' sobre a propria passada")
            else:
                checar(_c == 0,
                       f"`{_f}: falhou` passa -- e' o produto da revisao")

        print("\nTrilha revisao: `exigida` continua segurando")
        # `exigida` nao diz "achei defeito", diz "ninguem rodou" -- e isso e'
        # lacuna em qualquer regime, inclusive no de quem so' confere.
        rodar("iniciar", "REV3", "--titulo", "Outra", "--trilha", "revisao")
        for _ in range(4):
            rodar("avancar", "REV3", "--nota", "x")
        rodar("conferencia", "REV3", "--ferramenta", "perfis",
              "--veredicto", "exigida", "--detalhe", "o diff toca autorizacao")
        _c, _o = codigo_e_saida("concluir", "REV3", "--nota", "publicado no PR")
        checar(_c != 0, "`exigida` segura o concluir TAMBEM na revisao")
        checar("EXIGIDA" in _o, "e o erro diz qual e' o caso")
        checar("fechou reprovando" not in _o,
               "e NAO diz mais 'ou fechou reprovando' -- na revisao isso e' falso")

        print("\nTrilha completa: `falhou` continua sendo divida")
        rodar("iniciar", "COMP2", "--titulo", "Feature", "--trilha", "completa")
        rodar("conferencia", "COMP2", "--ferramenta", "catraca:lint",
              "--veredicto", "falhou", "--detalhe", "3 novas")
        _c, _o = codigo_e_saida("concluir", "COMP2", "--nota", "publicado no PR")
        checar(_c != 0,
               "nas trilhas que CONSTROEM o vermelho continua travando, mesmo com nota")

        print("\nTrilha curta")
        checar(rodar("iniciar", "T-2", "--titulo", "Bug",
                     "--trilha", "curta") == 0, "iniciar na trilha curta")
        rodar("avancar", "T-2")
        checar(Atividade.ler(atividades / "T-2.md").step == 8,
               "curta pula do 1 direto para o 8")
        erra("step fora da trilha é recusado", "avancar", "T-2", "--step", "3")
        checar(rodar("avancar", "T-2", "--step", "3", "--forcar",
                     "--nota", "mudou de escopo", "--trilha", "completa") == 0,
               "--forcar troca a trilha")
        checar(Atividade.ler(atividades / "T-2.md").meta["trilha"] == "completa",
               "e a troca fica gravada")

        print("\nRound trip do texto")
        casos = {
            "pipe": r"pipe | barra \ e ambos \| juntos",
            "crlf": "primeira parte\r\nsegunda parte importante",
            "cr": "resumo do card\rcontinua aqui",
            "heading": "resumo\r## Artefatos\rlixo",
            "separador": "---",
            "unicode": "linha seguinte fim",
        }
        rodar("iniciar", "RT", "--titulo", "Round trip", "--trilha", "completa")
        rodar("artefato", "RT", "--tipo", "sdd", "--caminho", "docs/x.md")
        for nome, nota in casos.items():
            rodar("avancar", "RT", "--forcar", f"--nota={nota}")
            lida = Atividade.ler(atividades / "RT.md")
            esperado = flow_state.uma_linha(nota)
            checar(lida.history[-1][2] == esperado,
                   f"nota com {nome} volta íntegra")
        lida = Atividade.ler(atividades / "RT.md")
        # A passagem pelo 5 grava `portão gravado`: evento, não transição.
        checar(len([h for h in lida.history if h[1] != "portão gravado"])
               == 1 + len(casos) and len(lida.history) == 2 + len(casos),
               "nenhuma linha do histórico se perdeu")
        checar(lida.artefatos == [("sdd", "docs/x.md")],
               "nota maliciosa não apagou a tabela de artefatos")

        print("\nFront matter")
        rodar("iniciar", "FM", "--titulo", "hotfix\n---\ntrilha: completa",
              "--trilha", "curta")
        lida = Atividade.ler(atividades / "FM.md")
        checar(lida.meta["trilha"] == "curta",
               "título com `---` não derruba a trilha")
        checar(lida.meta["status"] == flow_state.STATUS_ABERTO,
               "nem o status")
        checar("hotfix" in lida.meta["titulo"] and "\n" not in lida.meta["titulo"],
               "título achatado em uma linha")

        print("\nArtefatos")
        rodar("artefato", "T-1", "--tipo", "sdd", "--caminho", "docs/specs/X.md")
        rodar("artefato", "T-1", "--tipo", "sdd", "--caminho", "docs/specs/X.md")
        checar(len(Atividade.ler(arq).artefatos) == 1,
               "artefato repetido não duplica")
        rodar("artefato", "T-1", "--tipo=---", "--caminho=---")
        checar(("---", "---") in Atividade.ler(arq).artefatos,
               "artefato que parece separador sobrevive à releitura")

        print("\nArtefato com CPF por extenso: registra, e avisa")
        # A 1052 gravou o CPF na SDD e no relatório, e o próximo contexto que
        # os leu foi barrado pelo guardrail. Formatado por inteiro já conta,
        # com ou sem dígito válido: o número aqui não fecha o dígito, de
        # propósito, para a suíte não carregar documento de verdade.
        # Montado em partes para o número não existir por extenso NESTE arquivo:
        # a suíte é lida por agente, e o `doc_mask conferir` do pacote a varre.
        _cpf_formatado = ".".join(["123", "456", "789"]) + "-00"
        (tmp / "docs" / "specs").mkdir(parents=True, exist_ok=True)
        (tmp / "docs" / "specs" / "COM-DOC.md").write_text(
            "# spec\n\ncliente de teste: " + _cpf_formatado + "\n", encoding="utf-8")
        _c, _o = codigo_e_saida("artefato", "T-1", "--tipo", "sdd",
                                "--caminho", "docs/specs/COM-DOC.md")
        checar(_c == 0, "o artefato com documento é registrado, não recusado")
        checar("CPF OU CNPJ POR EXTENSO" in _o and "linha 3" in _o,
               "mas o aviso sai, apontando a linha")
        checar("123.456.789" not in _o, "e o aviso nunca repete o número")
        checar(("sdd", "docs/specs/COM-DOC.md") in Atividade.ler(arq).artefatos,
               "e o registro fica gravado")
        (tmp / "docs" / "specs" / "SEM-DOC.md").write_text(
            "# spec\n\ncliente de teste: [CPF] (fixture.json:12)\n", encoding="utf-8")
        _c, _o = codigo_e_saida("artefato", "T-1", "--tipo", "sdd",
                                "--caminho", "docs/specs/SEM-DOC.md")
        checar(_c == 0 and "POR EXTENSO" not in _o, "com o marcador, nenhum aviso")

        print("Tamanho da entrega: o PF declarado e o PF aferido")
        rodar("pf", "T-1", "--declarado", "8")
        checar(Atividade.ler(arq).meta.get("pf") == "8",
               "`pf` declarado entra no front-matter")
        rodar("pf", "T-1", "--aferido", "13", "--inventario", "docs/T-1-pf.md")
        m = Atividade.ler(arq).meta
        checar(m.get("pf_aferido") == "13", "`pf_aferido` entra")
        checar(m.get("pf_inventario") == "docs/T-1-pf.md", "e o inventário junto")
        checar(m.get("pf") == "8", "declarar o aferido NÃO apaga o declarado")
        # A obrigação escrita em prosa não acontece — é a regra que a tabela
        # de conferências existe para provar. Um `pf_aferido` sem inventário é
        # um número no denominador de todo h/PF citado depois, sem a conta que
        # o sustenta: aqui ele é recusado, não avisado.
        erra("aferido sem inventário é RECUSADO", "pf", "T-1", "--aferido", "20")
        checar(Atividade.ler(arq).meta.get("pf_aferido") == "13",
               "e a recusa não mexe no que já estava gravado")
        erra("PF negativo é recusado", "pf", "T-1", "--declarado", "-3")
        erra("PF não inteiro é recusado", "pf", "T-1", "--declarado", "oito")
        erra("`pf` sem nada para declarar é recusado", "pf", "T-1")

        print("Orcamento por atividade: o gasto vira limite, nao so' relatorio")

        def orcar(valor):
            """Declara (ou apaga) o orcamento no config do projeto de mentira."""
            corpo = '[projeto]\nnome = "t"\n\n[metricas]\n'
            if valor is not None:
                corpo += f"orcamento_usd = {valor}\n"
            (agents / "config.toml").write_text(corpo, encoding="utf-8")
            import config as _C
            _C._cache.clear()

        def coletado(ident, custo, atribuicao="ok"):
            d = agents / "metrics"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{ident}.json").write_text(json.dumps({
                "id": ident, "atribuicao": atribuicao, "motivo_atribuicao": "",
                "custo_usd": custo, "turnos": 100,
                "gerado_em": "2026-09-03 09:51:00"}), encoding="utf-8")

        rodar("iniciar", "ORC", "--titulo", "Orcamento", "--trilha", "completa")
        arq_orc = atividades / "ORC.md"

        # Sem config nenhum o `avancar` nao pode nem hesitar: o flow-state roda
        # em projeto que ainda nao declarou nada, e a maioria dos testes daqui
        # nunca escreveu um config.toml.
        coletado("ORC", 999.0)
        checar(rodar("avancar", "ORC", "--nota", "sem config") == 0,
               "sem config.toml, o orcamento nao existe e o avancar passa")

        orcar(None)
        checar(rodar("avancar", "ORC", "--nota", "sem chave") == 0,
               "config sem a chave declarada tambem nao confere nada")

        orcar(1000.0)
        coletado("ORC", 200.0)
        checar(rodar("avancar", "ORC", "--nota", "abaixo do teto") == 0,
               "gasto abaixo do orcamento passa limpo")

        coletado("ORC", 1204.80)
        codigo = rodar("avancar", "ORC", "--nota", "estourado")
        checar(codigo != 0, "gasto acima do orcamento RECUSA o avancar")
        _saida = saida("avancar", "ORC", "--nota", "estourado")
        checar("1,204.80" in _saida or "1204.80" in _saida or "1.204,80" in _saida,
               "e diz quanto gastou")
        checar("1,000.00" in _saida or "1000.00" in _saida or "1.000,00" in _saida,
               "e qual era o teto")
        checar("20.5" in _saida or "20,5" in _saida, "e quanto passou, em percentual")
        checar("2026-09-03 09:51" in _saida,
               "e QUANDO foi a coleta -- o numero e' da ultima, nao de agora")

        # O idioma que o fluxo ja' usa para sair da trilha: nao e' proibido,
        # e' registrado.
        erra("--forcar sem --nota continua recusado", "avancar", "ORC", "--forcar")
        checar(rodar("avancar", "ORC", "--forcar", "--nota", "vale seguir: X") == 0,
               "--forcar com --nota atravessa o orcamento")

        # O zero silencioso, na porta do orcamento: uma atividade sem prova de
        # atribuicao reporta US$ 0,00 e passaria por BAIXO de qualquer teto.
        # Nao conferir e' correto; nao DIZER que nao conferiu nao e'.
        rodar("iniciar", "ORC2", "--titulo", "Sem prova", "--trilha", "completa")
        coletado("ORC2", 0.0, atribuicao="sem-prova")
        _s2 = saida("avancar", "ORC2", "--nota", "sem prova")
        checar(rodar("avancar", "ORC2", "--nota", "de novo") == 0,
               "atividade sem prova de atribuicao nao e' barrada")
        checar("nao conferido" in _s2 or "não conferido" in _s2,
               "mas o avancar DIZ que nao conferiu o orcamento")
        checar("atribui" in _s2, "e diz por que: falta prova de atribuicao")

        # `concluir` nao e' barrado: travar o fechamento deixaria a atividade
        # presa em andamento, que e' pior que estourar o orcamento.
        rodar("iniciar", "ORC3", "--titulo", "Fecha", "--trilha", "curta")
        coletado("ORC3", 99999.0)
        for _ in range(4):
            rodar("avancar", "ORC3", "--forcar", "--nota", "empurrando")
        checar(rodar("concluir", "ORC3", "--nota", "aceita") == 0,
               "o orcamento NAO barra o concluir")
        rodar("artefato", "T-1", "--tipo", "Tipo", "--caminho", "Caminho")
        checar(("Tipo", "Caminho") in Atividade.ler(arq).artefatos,
               "artefato que parece cabeçalho sobrevive à releitura")

        print("\nConclusão")
        erra("concluir antes do fim da trilha é recusado", "concluir", "T-1")
        checar(rodar("concluir", "T-1", "--forcar",
                     "--nota", "cancelada") == 0, "--forcar encerra antes")
        checar(Atividade.ler(arq).meta["status"] == flow_state.STATUS_CONCLUIDO,
               "status vira concluido")
        checar(Atividade.ler(arq).meta.get("concluido_em"),
               "concluido_em é gravado à parte de atualizado_em")
        erra("concluir duas vezes é recusado", "concluir", "T-1")
        erra("atividade concluída não avança", "avancar", "T-1")

        print("\nResistência a arquivo corrompido")
        quebrados = {
            "sem_fm.md": "sem front matter",
            "sem_id.md": "---\ntitulo: x\nstep: 1\ntrilha: curta\n"
                         "status: em_andamento\n---\n",
            "step_texto.md": "---\nid: a\nstep: sete\ntrilha: curta\n"
                             "status: em_andamento\n---\n",
            "step_fora.md": "---\nid: b\nstep: 42\ntrilha: curta\n"
                            "status: em_andamento\n---\n",
            "trilha_ruim.md": "---\nid: c\nstep: 1\ntrilha: turbo\n"
                              "status: em_andamento\n---\n",
        }
        for nome, conteudo in quebrados.items():
            (atividades / nome).write_text(conteudo, encoding="utf-8")
        checar(rodar("listar") == 0,
               "arquivo corrompido não derruba a listagem")
        checar(rodar("indice") == 0, "nem o índice")
        antes = Atividade.ler(atividades / "T-2.md").step
        checar(rodar("avancar", "T-2", "--forcar", "--nota", "segue") == 0,
               "nem impede outra atividade de avançar")
        checar(Atividade.ler(atividades / "T-2.md").step != antes,
               "e o avanço realmente aconteceu")
        avisos = saida("listar")
        checar(all(n.replace(".md", "") in avisos or n in avisos
                   for n in ("sem_fm.md", "step_texto.md")),
               "os arquivos ilegíveis são nomeados no aviso")
        for nome in quebrados:
            (atividades / nome).unlink()

        print("\nConcorrência entre processos")
        # Two worktrees advancing the same activity. Without a lock both read
        # the same state, both write, and the second write erases the first —
        # with both processes reporting success.
        rodar("iniciar", "CC", "--titulo", "Concorrente", "--trilha", "completa")
        env = {**os.environ, "ELCAMARGO_AGENTS_DIR": str(agents)}
        procs = [
            subprocess.Popen(
                [sys.executable, str(AQUI / "flow_state.py"), "avancar", "CC",
                 "--forcar", "--nota", f"processo {i}"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for i in range(6)
        ]
        codigos = [p.wait() for p in procs]
        lida = Atividade.ler(atividades / "CC.md")
        notas = [h[2] for h in lida.history]
        checar(all(c == 0 for c in codigos), "os seis processos terminam bem")
        # Seis transições e um `portão gravado`, o da saída do 5.
        checar(len([h for h in lida.history if h[1] != "portão gravado"]) == 7
               and len(lida.history) == 8,
               f"as seis transições foram registradas (histórico: "
               f"{len(lida.history)})")
        checar(all(f"processo {i}" in notas for i in range(6)),
               "nenhuma escrita foi perdida")

        # Two worktrees opening different activities: both must reach the index.
        procs = [
            subprocess.Popen(
                [sys.executable, str(AQUI / "flow_state.py"), "iniciar",
                 f"P{i}", "--titulo", f"Paralela {i}", "--trilha", "curta"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for i in range(5)
        ]
        [p.wait() for p in procs]
        indice = (agents / flow_state.INDEX_NAME).read_text(encoding="utf-8")
        checar(all(f"P{i}" in indice for i in range(5)),
               "todas as atividades paralelas aparecem no índice")

        # Same id from two processes: exactly one may win.
        procs = [
            subprocess.Popen(
                [sys.executable, str(AQUI / "flow_state.py"), "iniciar", "DUP",
                 "--titulo", f"tentativa {i}", "--trilha", "curta"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for i in range(4)
        ]
        codigos = [p.wait() for p in procs]
        checar(codigos.count(0) == 1,
               f"só um processo abre a mesma atividade (ok: {codigos.count(0)})")

        # A TRAVA NO WINDOWS. Ate' 2.47.0 `trava()` era um `yield` e mais nada
        # quando nao havia `fcntl` -- e o comentario dizia "Documented in
        # README", onde nunca houve linha sobre Windows. A trava nao existia, e
        # o aviso que a declararia tambem nao. Numa instalacao Windows a suite
        # reprovava exatamente aqui: o teste estava certo, faltava o mecanismo.
        #
        # `msvcrt` nao existe nesta maquina, entao o que da' para conferir daqui
        # e' o CAMINHO: que ele e' escolhido, que solta, que o prazo estoura em
        # ERRO, e que plataforma sem primitiva nenhuma DECLARA a lacuna. A
        # syscall em si so' a maquina de la' prova.
        print("\nA trava fora do POSIX: o caminho, conferido com dublê")

        class _MsvcrtFake:
            LK_NBLCK, LK_UNLCK = 1, 0

            def __init__(self, falha_sempre=False):
                self.falha_sempre = falha_sempre
                self.chamadas = []

            def locking(self, fd, modo, nbytes):
                self.chamadas.append(modo)
                if self.falha_sempre and modo == self.LK_NBLCK:
                    raise OSError(36, "Resource deadlock avoided")

        _fcntl_real, _msvcrt_real = flow_state.fcntl, flow_state.msvcrt
        _espera_real = flow_state.SEGUNDOS_ESPERANDO_A_TRAVA
        try:
            _dub = _MsvcrtFake()
            flow_state.fcntl, flow_state.msvcrt = None, _dub
            with flow_state.trava(agents):
                pass
            checar(_dub.chamadas == [_dub.LK_NBLCK, _dub.LK_UNLCK],
                   "sem fcntl, trava e SOLTA pelo msvcrt -- antes nao chamava nada")

            # O prazo estoura em ERRO. Seguir sem a trava e' o que produzia
            # perda de escrita com os dois processos reportando sucesso.
            _teimoso = _MsvcrtFake(falha_sempre=True)
            flow_state.msvcrt = _teimoso
            flow_state.SEGUNDOS_ESPERANDO_A_TRAVA = 0.1
            try:
                with flow_state.trava(agents):
                    checar(False, "trava ocupada NAO deixa entrar no bloco")
            except FlowStateError as exc:
                checar("RECUSO seguir sem a trava" in str(exc),
                       "trava ocupada estoura em erro, e nao passa por cima")
            checar(len(_teimoso.chamadas) > 1,
                   "e tentou mais de uma vez antes de desistir")

            # Plataforma sem primitiva nenhuma: recusar bloquearia o pacote,
            # calar foi o que produziu o defeito. Entao DECLARA.
            flow_state.msvcrt = None
            flow_state._JA_AVISEI_SEM_TRAVA = False
            _err = io.StringIO()
            with contextlib.redirect_stderr(_err):
                with flow_state.trava(agents):
                    pass
            checar("SEM TRAVA" in _err.getvalue(),
                   "sem primitiva nenhuma, a lacuna FALA em vez de passar calada")
            _err2 = io.StringIO()
            with contextlib.redirect_stderr(_err2):
                with flow_state.trava(agents):
                    pass
            checar(_err2.getvalue() == "",
                   "e fala UMA vez por processo -- aviso a cada escrita vira ruido")
        finally:
            flow_state.fcntl, flow_state.msvcrt = _fcntl_real, _msvcrt_real
            flow_state.SEGUNDOS_ESPERANDO_A_TRAVA = _espera_real
            flow_state._JA_AVISEI_SEM_TRAVA = False

        # A SAIDA SOB UMA CODIFICACAO DE REGIAO. No Windows, com a saida em
        # PIPE -- que e' como toda skill e toda suite chamam estas ferramentas
        # --, `print` usa a codificacao da regiao, cp1252. Este pacote imprime
        # `→` as pencas (28 vezes so' em tools/), e cp1252 nao tem o caractere:
        # `UnicodeEncodeError`, saida 1, ferramenta morta.
        #
        # Da' para reproduzir em QUALQUER plataforma com PYTHONIOENCODING, e e'
        # o que este teste faz -- senao seria defeito que so' a maquina de la'
        # consegue ver, e ninguem daqui poderia consertar com confianca.
        print("\nA saida sobrevive a uma codificacao de regiao (o caso Windows)")
        _amb = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        _r = subprocess.run(
            [sys.executable, str(AQUI / "flow_state.py"), "fluxo"],
            env=_amb, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        checar(_r.returncode == 0,
               "`fluxo` nao estoura sob cp1252 em pipe -- era UnicodeEncodeError")
        checar("→" in _r.stdout,
               "e a seta CHEGA inteira, em vez de virar erro ou sujeira")
        # O controle: sem a reconfiguracao, o mesmo ambiente derruba. Sem ele o
        # teste passaria em plataforma que nunca teve o problema.
        _c = subprocess.run(
            [sys.executable, "-c", "print('1 \u2192 2')"],
            env=_amb, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        checar(_c.returncode != 0 and "UnicodeEncodeError" in _c.stderr,
               "controle: sem a reconfiguracao, o MESMO ambiente derruba")

        # O ARTEFATO SO' ACRESCENTAVA, e caminho renomeado virava ponteiro
        # morto. Medido em 24/09/2026 na `1054-backend` do app: a spec
        # foi renomeada no meio da atividade, o caminho novo foi registrado, e
        # o `status` passou a listar TRES `sdd-sistema` -- um apontando para
        # arquivo que nao existia mais. As seis frentes do step 9 ABREM esses
        # caminhos: a que nao achar reporta "a spec nao existe", e o achado
        # parece defeito da entrega quando e' ponteiro velho.
        print("\nArtefato: o ponteiro morto se declara, e renomear tem caminho")
        _raiz = agents.parent
        (_raiz / "docs").mkdir(exist_ok=True)
        (_raiz / "docs" / "viva.md").write_text("x\n", encoding="utf-8")
        rodar("iniciar", "ART", "--titulo", "Artefatos", "--trilha", "curta")
        rodar("artefato", "ART", "--tipo", "sdd-sistema",
              "--caminho", "docs/viva.md")
        rodar("artefato", "ART", "--tipo", "sdd-sistema",
              "--caminho", "docs/renomeada.md")
        _t = saida("status", "ART")
        checar("docs/renomeada.md   (AUSENTE)" in _t,
               "o caminho que nao existe sai marcado AUSENTE na leitura")
        checar("docs/viva.md   (AUSENTE)" not in _t,
               "e o que existe NAO sai marcado -- senao a marca nao diz nada")
        checar("1 caminho(s) marcado(s) AUSENTE" in _t and "--substituir" in _t,
               "e a lista diz quantos e qual o comando de consertar")

        # O aviso no NASCIMENTO. Ele AVISA e nao recusa: recusar perderia o
        # registro de um artefato que existe, que e' a mesma razao pela qual
        # tipo fora do vocabulario passa.
        _t = saida("artefato", "ART", "--tipo", "sdd-sistema",
                   "--caminho", "docs/nasce-morta.md")
        checar("CAMINHO QUE NÃO EXISTE" in _t,
               "registrar caminho inexistente AVISA no momento em que nasce")
        checar("registrado" in _t,
               "e registra assim mesmo -- perder o registro seria pior")

        # OS CONTROLES, que sao o que separa a conferencia de um alarme burro:
        # nem todo artefato e' arquivo. `prototipo` recebe caminho de COMPONENTE
        # do Figma, `anexo` recebe nome de anexo de card, `pr` recebe "PR 42".
        _t = saida("artefato", "ART", "--tipo", "prototipo",
                   "--caminho", "Administrador/Botões/Primário")
        checar("CAMINHO QUE NÃO EXISTE" not in _t,
               "componente de Figma NAO vira alarme: tem barra e nao tem extensao")
        _t = saida("artefato", "ART", "--tipo", "anexo",
                   "--caminho", "relatorio.pdf")
        checar("CAMINHO QUE NÃO EXISTE" not in _t,
               "nome de anexo idem: tem extensao e nao tem barra")
        _t = saida("artefato", "ART", "--tipo", "anexo",
                   "--caminho", "https://exemplo/x.md")
        checar("CAMINHO QUE NÃO EXISTE" not in _t,
               "e URL idem, que e' o terceiro jeito de nao ser arquivo daqui")

        # `--substituir`: a renomeacao troca NO LUGAR, em vez de acrescentar.
        _antes = Atividade.ler(atividades / "ART.md").artefatos
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--substituir", "docs/renomeada.md",
                     "--caminho", "docs/viva.md") == 0,
               "`--substituir` troca o registro do arquivo renomeado")
        _depois = Atividade.ler(atividades / "ART.md").artefatos
        checar(len(_depois) == len(_antes) - 1,
               "e a lista ENCOLHE: o novo ocupa o lugar do antigo, nao soma")
        checar(("sdd-sistema", "docs/renomeada.md") not in _depois,
               "o caminho antigo sai")
        _hist = [h[1] for h in Atividade.ler(atividades / "ART.md").history]
        checar("artefato substituído" in _hist,
               "e a troca deixa rastro no historico, como o `corrigir`")
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--substituir", "docs/nunca-registrada.md",
                     "--caminho", "docs/viva.md") != 0,
               "substituir o que nao esta registrado RECUSA, em vez de somar um")

        # `--retirar`: exige explicacao, e recusa o no-op.
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--caminho", "docs/nasce-morta.md", "--retirar") != 0,
               "retirar SEM nota recusa: registro que some sem explicacao e' "
               "igual a registro que nunca houve")
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--caminho", "docs/nunca-houve.md", "--retirar",
                     "--nota", "x") != 0,
               "retirar o que nao esta registrado RECUSA, em vez de sair com "
               "sucesso sem ter feito nada")
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--caminho", "docs/nasce-morta.md", "--retirar",
                     "--nota", "a spec foi descartada pelo cliente") == 0,
               "com nota, retira")
        _final = Atividade.ler(atividades / "ART.md")
        checar(("sdd-sistema", "docs/nasce-morta.md") not in _final.artefatos,
               "e o registro sai mesmo")
        checar(any(h[1] == "artefato retirado" for h in _final.history),
               "deixando rastro -- a nota fica no historico, nao na conversa")
        checar(rodar("artefato", "ART", "--tipo", "sdd-sistema",
                     "--caminho", "docs/viva.md", "--retirar", "--nota", "x",
                     "--substituir", "docs/outra.md") != 0,
               "--retirar com --substituir recusa: um tira, o outro troca")

        print("\nReabertura")
        rodar("iniciar", "RB", "--titulo", "Reabrir", "--trilha", "curta")
        rodar("avancar", "RB", "--nota", "implementado")
        rodar("artefato", "RB", "--tipo", "pr", "--caminho", "PR 42")
        antes = Atividade.ler(atividades / "RB.md")
        checar(rodar("iniciar", "RB", "--titulo", "Reabrir",
                     "--trilha", "completa", "--reabrir") == 0, "--reabrir")
        depois = Atividade.ler(atividades / "RB.md")
        checar(len(depois.history) > len(antes.history),
               "--reabrir preserva o histórico")
        checar(depois.artefatos == antes.artefatos,
               "--reabrir preserva os artefatos")
        checar(depois.meta["criado_em"] == antes.meta["criado_em"],
               "--reabrir preserva a data de criação")
        checar(depois.meta["trilha"] == "completa", "--reabrir aplica a trilha nova")
        checar(any(h[2].startswith(flow_state.MARCA_DE_REABERTURA)
                   for h in depois.history),
               "e a linha de reabertura leva a marca que o percurso conta")
        checar(flow_state.percurso(depois.history)["reaberturas"] == 1,
               "o percurso conta UMA reabertura -- a da atividade aberta tambem")

        print("\nPercurso: o caminho lido do Historico")
        # Ate' a 2.56.0 ninguem lia o Historico: voltas 9->8, devolucoes de
        # portao e reaberturas estavam escritas e nao eram contadas.
        _r = flow_state.rotulo
        _h = [
            ("2026-10-01 10:00:00", _r(1), "aberta"),
            ("2026-10-01 10:10:00", _r(2), "x"),
            ("2026-10-01 10:20:00", _r(3), "x"),
            ("2026-10-01 10:50:00", _r(4), "x"),
            ("2026-10-01 11:00:00", _r(3), "volta de correcao"),
            ("2026-10-01 11:10:00", _r(4), "x"),
            ("2026-10-01 11:20:00", _r(5), "x"),
            ("2026-10-01 11:30:00", _r(3), "devolvido por escopo: faltou o caso B"),
            ("2026-10-01 11:40:00", _r(4), "x"),
            ("2026-10-01 11:50:00", _r(5), "x"),
            ("2026-10-01 12:00:00", _r(8), "spec aprovada"),
            ("2026-10-01 13:00:00", _r(9), "x"),
            ("2026-10-01 13:30:00", _r(8), "achado bloqueante"),
            ("2026-10-01 13:40:00", _r(9), "x"),
            ("2026-10-01 14:00:00", _r(10), "x"),
            ("2026-10-01 14:30:00", "concluída", "entregue"),
            ("2026-10-02 09:00:00", "artefato retirado", "nao e' marco"),
        ]
        _p = flow_state.percurso(_h)
        checar(_p["voltas"] == {"4→3": 1, "9→8": 1} and _p["voltas_total"] == 2,
               "voltas de correcao sao os retrocessos que saem de step de IA")
        checar(_p["devolucoes"] == [{"de": 5, "para": 3, "motivo": "escopo"}],
               "a devolucao sai do portao, com o motivo lido da nota")
        checar(_p["portoes"]["5"] == {"aprovado": 1, "devolvido": 1}
               and _p["portoes"]["10"] == {"aprovado": 1, "devolvido": 0},
               "o portao 5 aprovou uma e devolveu uma; o 10 aprovou ao concluir")
        checar(_p["reaberturas"] == 0, "sem reabertura, zero")
        checar(_p["por_step"]["8"]["entradas"] == 2
               and _p["por_step"]["8"]["segundos"] == 70 * 60,
               "o tempo do step 8 soma as duas passagens")
        checar(_p["tempo_s"]["humano"] == (10 + 10 + 30) * 60,
               "o tempo humano e' o dos portoes, e o ultimo conta ate' o concluir")
        _txt = io.StringIO()
        with contextlib.redirect_stdout(_txt):
            flow_state.imprimir_percurso(_p)
        checar("portão 5 devolveu ao step 3 (por escopo)" in _txt.getvalue()
               and "9→8 ×1" in _txt.getvalue(),
               "e o `tempo` imprime as duas coisas")
        _sem_nota = flow_state.percurso([
            ("2026-10-01 10:00:00", _r(9), "x"),
            ("2026-10-01 10:30:00", _r(10), "x"),
            ("2026-10-01 11:00:00", _r(8), "faltou teste"),
        ])
        checar(_sem_nota["devolucoes"][0]["motivo"] == "defeito",
               "devolucao sem a palavra escopo conta como defeito")

        print("\nBug que escapou: `iniciar --corrige`")
        _c, _o = codigo_e_saida("iniciar", "BUG1", "--titulo", "Conserto",
                                "--trilha", "curta",
                                "--corrige", "77001-especificacao")
        _bug = Atividade.ler(atividades / "BUG1.md")
        checar(_c == 0 and _bug.meta.get("corrige") == "77001-especificacao",
               "--corrige grava a origem no front matter")
        checar(any(h[2].startswith("Corrige 77001-especificacao")
                   for h in _bug.history),
               "e deixa a linha no historico")
        checar("ORIGEM" not in _o, "origem concluida nao produz aviso")
        _c, _o = codigo_e_saida("iniciar", "BUG2", "--titulo", "x",
                                "--trilha", "curta", "--corrige", "RB")
        checar(_c == 0 and "AINDA ESTÁ ABERTA" in _o,
               "origem ABERTA avisa: o lugar do conserto e' o step 8 dela")
        _c, _o = codigo_e_saida("iniciar", "BUG3", "--titulo", "x",
                                "--trilha", "curta", "--corrige", "NAO-EXISTE")
        checar(_c == 0 and "ORIGEM NÃO ACHADA" in _o,
               "origem inexistente avisa, sem recusar -- pode ser de outro repo")
        erra("--corrige da propria atividade e' recusado",
             "iniciar", "RB", "--titulo", "x", "--trilha", "curta",
             "--reabrir", "--corrige", "RB")
        _orig = (atividades / "77001-especificacao.md").read_text(encoding="utf-8")
        checar("BUG1" not in _orig,
               "e a origem NAO e' escrita: a sessao do conserto nao entra nela")
        checar("corrige:" in saida("status", "BUG1"), "o `status` mostra a origem")

        print("\nÍndice")
        checar(rodar("indice") == 0, "indice regera")
        indice = (agents / flow_state.INDEX_NAME).read_text(encoding="utf-8")
        abertas, _, concluidas = indice.partition("## Concluídas")
        checar("T-2" in abertas, "atividade aberta cai na seção certa")
        checar("T-1" in concluidas, "atividade concluída cai na seção certa")

        print("\nComandos de leitura")
        checar(rodar("caminho") == 0, "caminho")
        checar(rodar("fluxo") == 0, "fluxo")
        checar(rodar("status", "T-2") == 0, "status de uma atividade")

        print("\nDisparo do próximo step")
        # Medido em 25-26/09/2026: 61% do custo com mais de 200 mil de
        # contexto, e os agentes mais caros emendavam steps. A linha sai onde
        # quem orquestra lê o próximo — e só quando o próximo é uma skill.
        _rc, _ini = codigo_e_saida("iniciar", "T-DISP", "--titulo", "disparo",
                                   "--trilha", "completa")
        checar(_rc == 0, "iniciar T-DISP")
        # O step 1 dispara em Sonnet: a saída dele vai a uma pessoa antes de
        # alguém construir em cima. O 2 em diante herda de quem dispara.
        checar('model: "sonnet"' in _ini,
               "iniciar diz que o step 1 dispara em Sonnet")
        _st = saida("status", "T-DISP")
        checar("disparo:" in _st and "elcamargo-step-runner" in _st,
               "status nomeia o step-runner quando o próximo é skill")
        checar("model:" not in _st,
               "o step 2 não recebe modelo: herda de quem dispara")
        _av = saida("avancar", "T-DISP")
        checar("elcamargo-step-runner" in _av,
               "avancar para step de skill também nomeia o step-runner")
        rodar("avancar", "T-DISP")
        rodar("avancar", "T-DISP")
        checar(Atividade.ler(atividades / "T-DISP.md").step == 4,
               "T-DISP chegou no step 4, antes do portão 5")
        _st = saida("status", "T-DISP")
        checar("disparo:" not in _st,
               "com portão humano como próximo, o status NÃO oferece disparo")
        checar(rodar("listar", "--todas") == 0, "listar --todas")
        erra("status de id inexistente falha", "status", "nao-existe")
        erra("avancar em id inexistente falha", "avancar", "nao-existe")
        erra("artefato em id inexistente falha", "artefato", "nao-existe",
             "--tipo", "x", "--caminho", "y")

        print("\nRaiz de trabalho x raiz do projeto")
        # O erro que apareceu duas vezes na POC: usar a raiz do projeto onde o
        # certo é a árvore em que o chamador está. Branch, dependências e
        # arquivos alterados são da worktree do chamador, não da principal.
        checar(flow_state.raiz_do_projeto(agents) == agents.parent,
               "raiz_do_projeto é sempre a principal")
        anterior_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            checar(flow_state.raiz_de_trabalho(agents) == agents.parent,
                   "fora de repositório, raiz_de_trabalho cai na principal")
            os.chdir(agents)
            checar(flow_state.raiz_de_trabalho(agents) == agents.parent,
                   "de dentro do .agents, também cai na principal")
        finally:
            os.chdir(anterior_cwd)

        print("\nSteps configuráveis")
        # Sem config, todos os steps valem — o pacote nunca exige declaração.
        checar(flow_state.steps_assets(agents) == sorted(flow_state.STEPS),
               "sem config, todos os steps estão assets")
        checar(flow_state.steps_desligados(agents) == [],
               "e nenhum aparece como desligado")
        checar(flow_state.avisar_desligados(agents) == [],
               "e não há aviso a dar")

        cfg = agents / "config.toml"
        cfg.write_text("[fluxo]\nsteps = [1, 2, 3, 5, 8, 9, 10]\n",
                       encoding="utf-8")
        import config as _config
        _config._cache.clear()
        checar(flow_state.steps_desligados(agents) == [4, 6, 7],
               "config desliga exatamente os steps declarados fora")
        avisos = " ".join(flow_state.avisar_desligados(agents))
        checar("PORTÃO HUMANO DESLIGADO" in avisos,
               "portão humano desligado gera aviso alto")
        checar("VERIFICAÇÃO DESLIGADA" in avisos,
               "step de verificação desligado gera aviso alto")

        rodar("iniciar", "SD", "--titulo", "Sem UX", "--trilha", "completa")
        lida = Atividade.ler(atividades / "SD.md")
        checar(lida.meta.get("steps_desligados") == "4 6 7",
               "a atividade grava o que ficou de fora")
        checar(lida.trilha == [1, 2, 3, 5, 8, 9, 10],
               "e a trilha efetiva pula os desligados")
        checar(any("desligados" in h[2] for h in lida.history),
               "e o histórico registra na abertura")
        checar(rodar("avancar", "SD", "--nota", "seguindo") == 0,
               "avancar respeita a trilha efetiva")
        checar(Atividade.ler(atividades / "SD.md").step == 2,
               "chegou ao step 2")
        rodar("avancar", "SD", "--nota", "x")
        checar(Atividade.ler(atividades / "SD.md").step == 3, "e ao 3")
        checar(rodar("avancar", "SD", "--nota", "x") == 0,
               "do 3 salta o 4 desligado sem --forcar")
        checar(Atividade.ler(atividades / "SD.md").step == 5,
               "e cai direto no 5")

        cfg.write_text("[fluxo]\nsteps = [2, 3]\n", encoding="utf-8")
        _config._cache.clear()
        try:
            flow_state.steps_assets(agents)
            checar(False, "desligar o step 1 é recusado")
        except FlowStateError:
            checar(True, "desligar o step 1 é recusado")
        cfg.unlink()
        _config._cache.clear()

        print("\nPolítica de ações — poder e querer são eixos diferentes")
        import capabilities as _cap

        # O grafo mora na árvore principal (não é versionado) e o time roda em
        # worktree. Até 2.53.0 a worktree dizia "sem grafo" com ele ao lado.
        _gdir = agents.parent / "graphify-out"
        _gdir.mkdir(exist_ok=True)
        (_gdir / "graph.json").write_text("{}", encoding="utf-8")
        _wt_vazia = Path(tmp) / "wt-sem-grafo"
        _wt_vazia.mkdir(exist_ok=True)
        _orig_rt = _cap.raiz_de_trabalho
        _cap.raiz_de_trabalho = lambda _a: _wt_vazia
        try:
            _g = _cap.capacidade_grafo(agents)
        finally:
            _cap.raiz_de_trabalho = _orig_rt
            (_gdir / "graph.json").unlink()
            _gdir.rmdir()
        checar(_g.get("disponivel") is True,
               "da worktree sem grafo, o grafo da árvore principal é achado")
        checar("árvore principal" in _g.get("detalhe", ""),
               "e o detalhe diz de onde ele veio")
        import config as _config

        # Sem config, valem os padrões do pacote — e o do Figma é NÃO escrever.
        _config._cache.clear()
        checar(_cap.politica("figma_escrita", agents) == "off",
               "figma_escrita nasce off, sem ninguém declarar nada")
        checar(_cap.politica("figma_leitura", agents) == "auto",
               "e ler nasce auto")
        checar(_cap.acoes_desligadas(agents) == ["figma_escrita"],
               "e ela já aparece na lista do que está desligado")
        checar("AÇÃO DESLIGADA NO PROJETO" in " ".join(_cap.avisar_desligadas(agents)),
               "com aviso, para acompanhar a atividade como step desligado acompanha")

        cfg.write_text('[capacidades]\nfigma_escrita = "on"\n', encoding="utf-8")
        _config._cache.clear()
        checar(_cap.politica("figma_escrita", agents) == "on",
               "o projeto liga a escrita e a política acompanha")
        checar(_cap.acoes_desligadas(agents) == [],
               "e ela sai da lista dos desligados")

        # Poder e política cruzados: o MCP funcionando não decide sozinho.
        cfg.write_text('[capacidades]\nfigma_escrita = "off"\n', encoding="utf-8")
        _config._cache.clear()
        e = _cap.efetivo("figma_escrita", True, agents)
        checar(e["permitido"] is False and "config do projeto" in e["porque"],
               "disponível e desligado = NÃO, e o porquê diz que foi política")
        cfg.write_text('[capacidades]\nfigma_leitura = "on"\n', encoding="utf-8")
        _config._cache.clear()
        e = _cap.efetivo("figma_leitura", False, agents)
        checar(e["permitido"] is False and "indisponível" in e["porque"],
               "exigido e indisponível = NÃO, e o porquê diz que foi acesso")
        e = _cap.efetivo("figma_leitura", True, agents)
        checar(e["permitido"] is True, "exigido e disponível = sim")

        # DESCONHECIDO nao e' SIM. `figma_escrita` herdava a deteccao do token
        # da leitura e respondia `[sim]` -- um token prova leitura, e nao diz
        # nada sobre o `use_figma`, que e' o unico caminho de escrita. Uma
        # frente leu "pode escrever" onde nao havia com o que.
        cfg.write_text('[capacidades]\nfigma_escrita = "on"\n', encoding="utf-8")
        _config._cache.clear()
        e = _cap.efetivo("figma_escrita", None, agents)
        checar(e["permitido"] is None,
               "exigido e capacidade DESCONHECIDA = `?`, nunca sim")
        checar("confirme a capacidade na sessão" in e["porque"],
               "e o porquê manda a sessão confirmar, em vez de agir")

        # E a fonte da escrita nao pode ser a da leitura.
        caps = _cap.capacidade_figma_mcp()
        checar(caps["disponivel"] is None,
               "a capacidade de escrita nao se detecta deste processo")
        checar("MCP" in caps["detalhe"] and "token" not in caps["detalhe"],
               "e ela fala de MCP, nao de token")

        # A razão importa: falta de acesso pede fallback, política pede parar.
        cfg.write_text('[capacidades]\nfigma_leitura = "auto"\n', encoding="utf-8")
        _config._cache.clear()
        e = _cap.efetivo("figma_leitura", False, agents)
        checar("degrade e declare" in e["porque"],
               "em auto, indisponível manda degradar declarando — não parar")

        cfg.write_text('[capacidades]\nfigma_escrita = "talvez"\n', encoding="utf-8")
        _config._cache.clear()
        try:
            _cap.politica("figma_escrita", agents)
            checar(False, "valor fora de auto/on/off é recusado")
        except FlowStateError:
            checar(True, "valor fora de auto/on/off é recusado")
        try:
            _cap.politica("figma_escritaX", agents)
            checar(False, "a lista é fechada: ação desconhecida é recusada")
        except FlowStateError:
            checar(True, "a lista é fechada: ação desconhecida é recusada")

        # Toda ação publicada tem leitor. Flag morta parece controle e não é.
        pacote = Path(__file__).resolve().parents[2]
        sem_leitor = []
        for acao in _cap.ACOES:
            lidos = [q for q in (pacote / "skills").glob("*/SKILL.md")
                     if acao in q.read_text(encoding="utf-8")]
            lidos += [q for q in (pacote / "agents").glob("*.md")
                      if acao in q.read_text(encoding="utf-8")]
            if not lidos:
                sem_leitor.append(acao)
        checar(sem_leitor == [],
               "toda ação da lista é consultada por alguma skill ou agente")

        cfg.unlink()
        _config._cache.clear()

        print("\nTravessia completa da trilha")
        # A prova de que o fluxo termina: percorrer os 10 steps do jeito que os
        # documentos mandam, inclusive parando e atravessando os três portões.
        rodar("iniciar", "FIM", "--titulo", "Ponta a ponta", "--trilha", "completa")
        caminho_fim = atividades / "FIM.md"
        for esperado in range(2, 11):
            checar(rodar("avancar", "FIM", "--nota", f"entrou no {esperado}") == 0,
                   f"avança para o step {esperado}")
            checar(Atividade.ler(caminho_fim).step == esperado,
                   f"e o estado registra o step {esperado}")
        checar(Atividade.ler(caminho_fim).proximo_step() is None,
               "o step 10 é o fim da trilha")
        checar(rodar("concluir", "FIM", "--nota", "aceita") == 0,
               "concluir no último step, sem --forcar")

        print("\nLaço de correção do step 9")
        # O step 9 devolve ao 8 e o 8 devolve ao 9. O contador de voltas vive no
        # histórico, porque nenhuma das duas execuções sobrevive à troca.
        rodar("iniciar", "LC", "--titulo", "Laço", "--trilha", "curta")
        caminho_lc = atividades / "LC.md"
        for _ in range(2):
            rodar("avancar", "LC", "--nota", "segue")
        checar(Atividade.ler(caminho_lc).step == 9, "chegou ao step 9")
        for volta in (1, 2):
            checar(rodar("avancar", "LC", "--step", "8", "--forcar",
                         f"--nota=volta {volta}: 2 achados") == 0,
                   f"volta {volta}: step 9 devolve ao 8")
            checar(rodar("avancar", "LC", "--step", "9", "--forcar",
                         f"--nota=volta {volta}: corrigidos") == 0,
                   f"volta {volta}: step 8 devolve ao 9")
        entradas_no_9 = [h for h in Atividade.ler(caminho_lc).history
                         if h[1].startswith("9 ")]
        checar(len(entradas_no_9) == 3,
               f"o histórico conta as 3 entradas no step 9 (contou "
               f"{len(entradas_no_9)})")

        print("\nConcluir")
        rodar("iniciar", "CN", "--titulo", "Concluir", "--trilha", "curta")
        erra("concluir fora do último step é recusado", "concluir", "CN")
        erra("concluir --forcar sem --nota é recusado",
             "concluir", "CN", "--forcar")
        checar(rodar("concluir", "CN", "--forcar", "--nota", "cancelada") == 0,
               "concluir --forcar com --nota passa")

        print("\nAs duas metades: as trilhas `backend` e `frontend`")
        # Pedido da gerencia em 15/09/2026: adiantar o backend, que serve o
        # front web E o mobile, para o time mobile nao esperar. O card fica
        # bloqueado no meio, e a metade da frente roda depois -- sempre.
        checar(flow_state.TRILHAS["backend"] == [1, 2, 3, 4, 5, 8, 9, 10],
               "a `backend` nao tem 6 nem 7: nao ha tela para desenhar nem validar")
        checar(6 in flow_state.TRILHAS["frontend"]
               and 7 in flow_state.TRILHAS["frontend"],
               "e a `frontend` tem os dois")

        erra("a `frontend` recusa abrir antes de a `backend` existir",
             "iniciar", "99-frontend", "--titulo", "tela", "--trilha", "frontend")
        _o = saida("iniciar", "99-frontend", "--titulo", "tela",
                   "--trilha", "frontend")
        checar("roda DEPOIS" in _o and "99-backend" in _o,
               "e o erro nomeia a metade que falta, em vez de dizer so' que nao pode")
        erra("--forcar sem --nota nao abre a excecao",
             "iniciar", "99-frontend", "--titulo", "tela", "--trilha", "frontend",
             "--forcar")

        checar(rodar("iniciar", "99-backend", "--titulo", "API do FAQ",
                     "--trilha", "backend") == 0, "a `backend` abre sozinha")
        _meia = Atividade.ler(atividades / "99-backend.md")
        checar(_meia.meta.get("escopo") == "backend",
               "o escopo e' DERIVADO da trilha, e nao uma bandeira que se esquece")
        checar(_meia.meta.get("outra_metade") == "99-frontend",
               "e a atividade sabe o id da outra metade, pelo sufixo")

        _o = saida("iniciar", "sem-sufixo", "--titulo", "x", "--trilha", "backend")
        checar("ID FORA DA CONVENÇÃO" in _o,
               "id sem sufixo de camada avisa: ninguem acha a outra metade depois")

        # A exigencia nasce ao ENTRAR no step 9 -- quem descobre a obrigacao e'
        # quem a registra. Obrigacao escrita so' na skill e' conselho.
        # Ate o step 9, sem contar saltos: outro bloco desta suite mexe nos
        # steps declarados, e teste que conta hop quebra quando a configuracao
        # ao lado muda -- que e' o defeito que ele deveria pegar, e nao ter.
        while Atividade.ler(atividades / "99-backend.md").step < 9:
            rodar("avancar", "99-backend", "--nota", "x")
        _b = Atividade.ler(atividades / "99-backend.md")
        checar(_b.step == 9, "a `backend` chega ao step 9")
        checar(not any(h[1].startswith(("6 ", "7 ")) for h in _b.history),
               "sem passar por 6 nem 7: nao ha tela para desenhar nem validar")
        _dims = {linha[1] for linha in _b.conferencias}
        checar("contrato" in _dims,
               "entrar no step 9 da `backend` registra `contrato` como exigida")
        rodar("avancar", "99-backend", "--nota", "ao portao")
        _c, _o = codigo_e_saida("concluir", "99-backend", "--nota", "entrega")
        checar(_c != 0 and "contrato" in _o,
               "e o `concluir` segura enquanto o contrato nao for provado")
        rodar("conferencia", "99-backend", "--ferramenta", "contrato",
              "--veredicto", "ok", "--detalhe", "7 rotas exercitadas, 7 respondem")
        _c, _o = codigo_e_saida("concluir", "99-backend", "--nota", "backend entregue")
        checar(_c == 0, "com o contrato provado, ela encerra")
        # O contrato mora em `docs/specs/` DESTE repositorio, e quem constroi a
        # outra metade nao o alcanca: trabalha num card proprio, noutro repo. O
        # card e' o unico caminho que existe -- e a ausencia do artefato e'
        # notavel, porque ele e' o produto de verdade desta trilha.
        checar("[contrato]" in _o and "sdd-frontend" in _o,
               "e sem `sdd-frontend` registrado o encerramento AVISA: "
               "sem contrato no card, a outra metade nao recebe nada")
        checar("artefato 99-backend --tipo sdd-frontend" in _o,
               "com o comando que conserta, em vez de so' reclamar")

        checar(rodar("iniciar", "99-frontend", "--titulo", "tela do FAQ",
                     "--trilha", "frontend") == 0,
               "e agora a `frontend` abre, porque a metade de tras fechou")
        while Atividade.ler(atividades / "99-frontend.md").step < 9:
            rodar("avancar", "99-frontend", "--nota", "x")
        _f = Atividade.ler(atividades / "99-frontend.md")
        checar(_f.step == 9, "a `frontend` chega ao step 9")
        checar(any(h[1].startswith("6 ") for h in _f.history),
               "e ela PASSA pela tela, que e' a metade que ela entrega")
        checar("entrega-ponta-a-ponta" in {l[1] for l in _f.conferencias},
               "e ali a exigencia e' a entrega INTEIRA, nao so' a metade dela")

        print("\nA guarda do step relampago")
        # 15/09/2026: `avancar` rodado duas vezes, uma de cada diretorio, com o
        # aviso de lugar lido como recusa. Step 9 as 14:41:15, step 10 as
        # 14:41:26 -- onze segundos, e a revisao em seis frentes nunca rodou.
        flow_state.SEGUNDOS_DE_STEP_RELAMPAGO = 120
        try:
            rodar("iniciar", "RELAMP", "--titulo", "Guarda", "--trilha", "curta")
            checar(rodar("avancar", "RELAMP", "--nota", "ao 8") == 0,
                   "sair do step 1 passa: o `iniciar` e' a ULTIMA coisa que ele faz")
            checar(rodar("avancar", "RELAMP", "--nota", "ao 9") == 0,
                   "e entre steps de skill ela nao se mete")
            _c, _o = codigo_e_saida("avancar", "RELAMP", "--nota", "ao portao")
            checar(_c != 0 and "10 · Portão humano" in _o,
                   "mas entrar no portao 10 com o step 9 aberto ha segundos e' recusado")
            checar("nunca tendo acontecido" in _o or "declarada revisada" in _o,
                   "e a recusa conta o caso que a produziu, em vez de so' negar")
            checar(rodar("avancar", "RELAMP", "--forcar",
                         "--nota", "o step 9 rodou mesmo: relatorio em docs/r.md") == 0,
                   "`--forcar --nota` encerra a duvida e deixa escrito")
            _h = Atividade.ler(atividades / "RELAMP.md").history
            checar(any("relatorio em docs/r.md" in linha[2] for linha in _h),
                   "e a nota fica no historico, para o portao achar")
        finally:
            flow_state.SEGUNDOS_DE_STEP_RELAMPAGO = 0

        print("\nHigiene")
        checar(not list(atividades.glob("*.tmp*")),
               "nenhum arquivo temporário ficou para trás")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if anterior is None:
            os.environ.pop("ELCAMARGO_AGENTS_DIR", None)
        else:
            os.environ["ELCAMARGO_AGENTS_DIR"] = anterior

    print("\nConferencia mecanica: o registro, e o portao no concluir")

    import subprocess as _sp  # noqa: E402

    _tmp = Path(tempfile.mkdtemp(prefix="conferencia-"))

    _sp.run(["git", "init", "-q"], cwd=_tmp, capture_output=True)

    (_tmp / ".agents" / "elcamargo-flow").mkdir(parents=True)

    _F = str(Path(__file__).resolve().parent / "flow_state.py")

    _P = str(Path(__file__).resolve().parents[1] / "profiles" / "profiles.py")



    def _roda(cmd, entrada=None):

        r = _sp.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", input=entrada, cwd=str(_tmp))

        return r.returncode, r.stdout + r.stderr



    _roda([sys.executable, _F, "iniciar", "99001", "--titulo", "T", "--trilha", "curta"])


    # A ferramenta que DESCOBRE a obrigacao e' a que a registra. Um step que rodou

    # `superficie` nao consegue mais "esquecer" de exercitar os perfis: a exigencia

    # ja' esta' no arquivo da atividade.

    _c, _o = _roda([sys.executable, _P, "superficie", "--base", "-", "--raiz", ".",

                    "--registrar", "99001"],

                   entrada="+++ b/api/x.controller.ts\n+  @RequirePermissions('faq.read')\n")

    checar("registrado em 99001" in _o, "a ferramenta registra sozinha, e diz que registrou")


    for _step in ("8", "10"):

        _roda([sys.executable, _F, "avancar", "99001", "--step", _step, "--forcar", "--nota", "t"])


    _c, _o = _roda([sys.executable, _F, "concluir", "99001"])

    checar(_c != 0 and "perfis" in _o, "concluir recusa com conferencia EXIGIDA em aberto")

    checar("nao-coberta" in _o or "`nao-coberta`" in _o,

           "e diz que declarar nao-coberta e' saida legitima")


    _roda([sys.executable, _F, "conferencia", "99001", "--ferramenta", "perfis",

           "--veredicto", "falhou", "--detalhe", "so negacoes"])

    _c, _o = _roda([sys.executable, _F, "concluir", "99001"])

    checar(_c != 0, "e recusa tambem quando a conferencia REPROVOU")


    _roda([sys.executable, _F, "conferencia", "99001", "--ferramenta", "perfis",

           "--veredicto", "nao-coberta", "--detalhe", "projeto nao declara [perfis]"])

    _c, _o = _roda([sys.executable, _F, "concluir", "99001"])

    checar(_c == 0, "dimensao declarada nao coberta PASSA -- ela nao some, ela aparece")


    _texto = (_tmp / ".agents" / "atividades" / "99001.md").read_text(encoding="utf-8")

    checar("## Conferências" in _texto, "e as tres ficam escritas no arquivo da atividade")

    checar(_texto.count("| perfis |") == 3, "as tres, e nao so' a ultima")


    _c, _o = _roda([sys.executable, _F, "conferencia", "99001", "--ferramenta", "x",

                    "--veredicto", "mais ou menos"])

    checar(_c != 0 and "veredicto desconhecido" in _o,

           "veredicto inventado e' recusado, em vez de virar linha muda")

    shutil.rmtree(_tmp, ignore_errors=True)

    print("\nO lugar da atividade: o `avancar` preserva, e o `corrigir` muda")
    # Em 08/09/2026 um `avancar` rodado da raiz -- que estava na branch de OUTRA
    # atividade -- retargetou branch e worktree em silencio. O step seguinte le'
    # exatamente esses campos para saber onde trabalhar: sem alguem conferir o
    # `status` antes, a implementacao sairia na branch de outra pessoa.
    _t2 = Path(tempfile.mkdtemp(prefix="lugar-")).resolve()
    _sp.run(["git", "init", "-q"], cwd=_t2, capture_output=True)
    _sp.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
             "-q", "--allow-empty", "-m", "base"], cwd=_t2, capture_output=True)
    (_t2 / ".agents" / "elcamargo-flow").mkdir(parents=True)

    def _roda2(cmd):
        r = _sp.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(_t2))
        return r.returncode, r.stdout + r.stderr

    def _campo(nome, ident="A1"):
        texto = (_t2 / ".agents" / "atividades" / f"{ident}.md").read_text(
            encoding="utf-8")
        for linha in texto.splitlines():
            if linha.startswith(f"{nome}: "):
                return linha.split(": ", 1)[1]
        return ""

    _sp.run(["git", "checkout", "-qb", "doc/minha"], cwd=_t2, capture_output=True)
    # O ciclo de vida do campo, pela linha de comando: nasce PENDENTE -- e' o
    # step 1 que cria branch e worktree, DEPOIS do `iniciar` -- e o primeiro
    # `avancar` rodado de dentro da arvore o preenche sozinho.
    _roda2([sys.executable, _F, "iniciar", "A0", "--titulo", "T",
            "--trilha", "curta"])
    checar(_campo("branch", "A0") == flow_state.LUGAR_PENDENTE,
           "o `iniciar` NAO herda a branch do cwd: ele declara a lacuna")
    _c, _o = _roda2([sys.executable, _F, "avancar", "A0", "--nota", "primeira"])
    checar(_campo("branch", "A0") == "doc/minha",
           "e o primeiro `avancar` de dentro da arvore preenche a lacuna")
    checar("O STEP FOI AVANÇADO" not in _o,
           "calado: preencher lacuna declarada nao e' retarget, e' adocao")

    # A1 ja' nasce com o lugar DECLARADO, que e' o caso de quem o conhece --
    # e e' sobre ele que a preservacao abaixo tem o que preservar.
    _roda2([sys.executable, _F, "iniciar", "A1", "--titulo", "T",
            "--trilha", "curta", "--branch", "doc/minha",
            "--worktree", str(_t2)])
    checar(_campo("branch") == "doc/minha",
           "quem ja sabe o lugar declara nas bandeiras do `iniciar`")

    _sp.run(["git", "checkout", "-qb", "doc/outra"], cwd=_t2, capture_output=True)
    _c, _o = _roda2([sys.executable, _F, "avancar", "A1", "--nota", "x"])
    checar(_campo("branch") == "doc/minha",
           "o `avancar` da branch errada NAO sobrescreve o lugar gravado")
    checar("O STEP FOI AVANÇADO" in _o and "doc/outra" in _o,
           "e grita, mostrando os dois lugares -- preservar calado seria o "
           "defeito oposto")
    checar("corrigir A1 --branch doc/outra" in _o,
           "com o comando pronto para quem quis mesmo mudar")

    _c, _o = _roda2([sys.executable, _F, "corrigir", "A1",
                     "--branch", "doc/outra", "--worktree", str(_t2),
                     "--nota", "mudou de branch de verdade"])
    checar(_c == 0 and _campo("branch") == "doc/outra",
           "o `corrigir` muda de proposito")
    _texto2 = (_t2 / ".agents" / "atividades" / "A1.md").read_text(encoding="utf-8")
    checar("lugar corrigido" in _texto2,
           "e deixa rastro no historico -- editar o front matter a' mao nao deixa")

    # No-op COM nota: a frente que corrigiu o front matter a' mao antes de o
    # comando existir ficou sem como deixar rastro. Nota explicita e' pedido de
    # registro; sem nota, gravar a cada conferencia encheria o historico de
    # linha que nao conta nada.
    _c, _o = _roda2([sys.executable, _F, "corrigir", "A1",
                     "--branch", "doc/outra", "--worktree", str(_t2)])
    _antes = (_t2 / ".agents" / "atividades" / "A1.md").read_text(encoding="utf-8")
    checar(_c == 0 and "Nada mudou" in _o and _antes.count("lugar conferido") == 0,
           "no-op sem nota nao grava historico")
    _c, _o = _roda2([sys.executable, _F, "corrigir", "A1",
                     "--branch", "doc/outra", "--worktree", str(_t2),
                     "--nota", "corrigido a mao antes da 2.22.0"])
    _depois = (_t2 / ".agents" / "atividades" / "A1.md").read_text(encoding="utf-8")
    checar(_c == 0 and "lugar conferido" in _depois
           and "corrigido a mao" in _depois,
           "no-op COM nota registra, para quem consertou a' mao ter rastro")

    _c, _o = _roda2([sys.executable, _F, "corrigir", "A1",
                     "--branch", "doc/nao_existe", "--worktree", str(_t2)])
    checar(_c != 0 and "não existe" in _o,
           "branch inexistente e' recusada, em vez de virar lugar impossivel")
    _c, _o = _roda2([sys.executable, _F, "corrigir", "A1",
                     "--branch", "doc/outra", "--worktree", "/nao/existe"])
    checar(_c != 0, "e worktree inexistente tambem")

    _c, _o = _roda2([sys.executable, _F, "avancar", "A1", "--step", "9",
                     "--nota", "x"])
    checar("O STEP FOI AVANÇADO" not in _o,
           "e com o lugar batendo, o `avancar` volta a calar")

    # O ultimo step: a mensagem tem de mostrar as DUAS saidas. A anterior so'
    # mandava `concluir` -- o oposto do que faz quem devolve por escopo --, e
    # `--step`, a unica resposta possivel ali, nao aparecia nela.
    _c, _o = _roda2([sys.executable, _F, "avancar", "A1", "--step", "10",
                     "--forcar", "--nota", "fast-forward do teste ao portao 10"])
    _c, _o = _roda2([sys.executable, _F, "avancar", "A1", "--nota", "x"])
    checar(_c != 0 and "--step" in _o and "escopo" in _o and "concluir" in _o,
           "no ultimo step, o erro mostra as duas saidas -- encerrar e devolver")

    shutil.rmtree(_t2, ignore_errors=True)

    print("\npublicar metricas: as duas recusas FALAM, em vez de escrever")
    # 12/09/2026: o `concluir` de uma revisao do PR 2210, rodado de dentro da
    # worktree, regerou README e metricas com 1/4 dos registros e deixou os
    # tres INDEXADOS -- na branch da autora do PR.
    import io as _io, contextlib as _ctx, subprocess as _sp2
    import flow_state as _FS
    _cap = _io.StringIO()
    with _ctx.redirect_stdout(_cap):
        _FS.publicar_metricas(indexar=True, trilha="revisao")
    _saida = _cap.getvalue()
    checar("nao publiquei" in _saida or "não publiquei" in _saida,
           "na trilha `revisao` o publicar RECUSA")
    checar("dono do card" in _saida,
           "e diz o motivo: ela nao escreve no repositorio de quem e' dono")

    _t3 = tempfile.mkdtemp()
    try:
        _repo = Path(_t3) / "repo"; _repo.mkdir()
        _e = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        _qq = {"capture_output": True, "text": True}
        _sp2.run(["git", "init", "-q", str(_repo)], **_qq)
        _sp2.run(["git", "-C", str(_repo), "commit", "-q", "--allow-empty",
                  "-m", "r"], env=_e, **_qq)
        _wt = Path(_t3) / "fora"
        _r = _sp2.run(["git", "-C", str(_repo), "worktree", "add", "-q",
                       str(_wt), "-b", "outra"], **_qq)
        _antes = os.getcwd()
        try:
            os.chdir(_repo)
            checar(_FS.arvore_alheia() == "",
                   "na arvore principal, nada de alheio")
            if _r.returncode == 0:
                os.chdir(_wt)
                checar(_FS.arvore_alheia() != "",
                       "de dentro da worktree, a arvore e' reconhecida como outra")
                _cap = _io.StringIO()
                with _ctx.redirect_stdout(_cap):
                    _FS.publicar_metricas(indexar=True)
                checar("worktree" in _cap.getvalue(),
                       "e o publicar recusa em QUALQUER trilha, dizendo por que")
        finally:
            os.chdir(_antes)
    finally:
        shutil.rmtree(_t3, ignore_errors=True)

    print("\nPortões do step 8: `gates` grava, e o 8→9 lê a tabela")
    # A frase "não feche o step com gate vermelho" viveu na skill do 8 desde a
    # primeira versão, e nada a conferia. Agora o código de saída vai para a
    # tabela, e o `avancar` lê a tabela -- inclusive com `--forcar`.
    import subprocess as _sp4
    _t4 = Path(tempfile.mkdtemp(prefix="gates-")).resolve()
    try:
        _ag = _t4 / ".agents"
        (_ag / "elcamargo-flow").mkdir(parents=True)
        (_ag / "config.toml").write_text(
            '[projeto]\nnome = "t"\n[gates]\nlint = "true"\n'
            'test = "python3 -c \\"import sys; print(\'w={max_workers}\'); '
            'sys.exit(0 if __import__(\'os\').path.exists(\'ok\') else 1)\\""\n'
            '[recursos]\nmax_workers_teste = 3\n', encoding="utf-8")
        _sp4.run(["git", "init", "-q"], cwd=_t4, capture_output=True)
        _env4 = {**os.environ, "ELCAMARGO_AGENTS_DIR": str(_ag)}
        _F4 = str(Path(__file__).resolve().parent / "flow_state.py")

        def _g(*args):
            r = _sp4.run([sys.executable, _F4, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", cwd=str(_t4), env=_env4,
                         timeout=120)
            return r.returncode, r.stdout + r.stderr

        _g("iniciar", "GT1", "--titulo", "t", "--trilha", "curta")
        _g("avancar", "GT1", "--step", "8", "--forcar", "--nota", "t")
        _c, _o = _g("avancar", "GT1", "--step", "9", "--forcar", "--nota", "pulo")
        checar(_c != 0 and "`lint` não rodou" in _o and "`test` não rodou" in _o,
               "8→9 recusa portão que não rodou, MESMO com --forcar", _o)
        _c, _o = _g("gates", "GT1")
        checar(_c == 1 and "VERMELHO em test" in _o, "gates devolve 1 e nomeia o vermelho", _o)
        checar("w=3" in (_ag / "atividades" / "GT1-gates" / "test.log").read_text(),
               "`{max_workers}` vira [recursos] max_workers_teste")
        _txt = (_ag / "atividades" / "GT1.md").read_text(encoding="utf-8")
        checar("| gate:lint | ok |" in _txt and "| gate:test | falhou |" in _txt,
               "cada portão vira uma linha `gate:<nome>` na tabela")
        _c, _o = _g("avancar", "GT1", "--step", "9", "--forcar", "--nota", "pulo")
        checar(_c != 0 and "`test` falhou" in _o, "8→9 recusa portão vermelho", _o)
        (_t4 / "ok").write_text("")
        _c, _o = _g("gates", "GT1", "--so", "test")
        checar(_c == 0, "--so roda só o pedido", _o)
        _res = json.loads((_ag / "atividades" / "GT1-gates" / "resumo.json").read_text())
        checar(set(_res) == {"lint", "test"}, "e acrescenta ao resumo, sem apagar o lint")
        _c, _o = _g("gates", "GT1", "--conferir")
        checar(_c == 1 and "[velho] lint" in _o and "[vale] test" in _o,
               "--conferir: o portão que rodou antes da árvore mudar fica velho", _o)
        _g("gates", "GT1")
        _c, _o = _g("gates", "GT1", "--conferir")
        checar(_c == 0 and "vale" in _o, "e depois de rodar tudo, o resumo vale", _o)
        (_t4 / "novo.ts").write_text("x")
        _c, _o = _g("gates", "GT1", "--conferir")
        checar(_c == 1 and "NÃO vale" in _o, "e deixa de valer quando a árvore muda", _o)
        _c, _o = _g("gates", "GT1", "--so", "nada")
        checar(_c != 0 and "não declarado" in _o, "portão inventado é recusado")
        _c, _o = _g("avancar", "GT1", "--step", "9", "--nota", "verde")
        checar(_c == 0, "portões verdes: o 8→9 passa", _o)
        _g("avancar", "GT1", "--step", "8", "--forcar", "--nota", "volta do 9")
        _c, _o = _g("avancar", "GT1", "--step", "9", "--forcar", "--nota", "sem rodar")
        checar(_c != 0 and "não rodou desde a entrada" in _o,
               "a volta 9→8 zera: o verde de antes não serve à correção", _o)
        _g("conferencia", "GT1", "--ferramenta", "gate:lint", "--veredicto",
           "nao-coberta", "--detalhe", "sem lint nesta entrega")
        _g("conferencia", "GT1", "--ferramenta", "gate:test", "--veredicto",
           "nao-coberta", "--detalhe", "so docs")
        _c, _o = _g("avancar", "GT1", "--step", "9", "--forcar", "--nota", "docs")
        checar(_c == 0, "`nao-coberta` com motivo deixa passar", _o)
        _g("iniciar", "GT2", "--titulo", "t", "--trilha", "curta")
        _g("avancar", "GT2", "--step", "8", "--forcar", "--nota", "t")
        _g("conferencia", "GT2", "--ferramenta", "gate:lint", "--veredicto", "ok")
        _g("conferencia", "GT2", "--ferramenta", "gate:test", "--veredicto", "ok")
        _g("conferencia", "GT2", "--ferramenta", "casos", "--veredicto", "exigida",
           "--detalhe", "contrato gerado")
        _c, _o = _g("avancar", "GT2", "--step", "9", "--forcar", "--nota", "t")
        checar(_c != 0 and "`casos` exigida" in _o, "contrato de casos sem prova segura o 8→9", _o)
    finally:
        shutil.rmtree(_t4, ignore_errors=True)

    print("\nRisco: o segundo eixo, proposto no step 1 e confirmado por quem abre")
    # A trilha diz QUANTOS steps; o risco diz QUANTA conferência. Alto torna a
    # frente de segurança obrigatória no 9 e o sast sem saída por `nao-coberta`.
    _t5 = Path(tempfile.mkdtemp(prefix="risco-")).resolve()
    try:
        _ag5 = _t5 / ".agents"
        (_ag5 / "elcamargo-flow").mkdir(parents=True)
        _cfg5 = _ag5 / "config.toml"
        _cfg5.write_text('[projeto]\nnome = "t"\n[gates]\nlint = "true"\nsast = "true"\n',
                         encoding="utf-8")
        _sp4.run(["git", "init", "-q"], cwd=_t5, capture_output=True)
        _env5 = {**os.environ, "ELCAMARGO_AGENTS_DIR": str(_ag5)}

        def _r(*args):
            r = _sp4.run([sys.executable, _F4, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", cwd=str(_t5), env=_env5,
                         timeout=120)
            return r.returncode, r.stdout + r.stderr

        def _md(ident):
            return (_ag5 / "atividades" / f"{ident}.md").read_text(encoding="utf-8")

        _c, _o = _r("fluxo")
        checar("autenticacao" in _o and "contrato-publico" in _o,
               "`fluxo` imprime o checklist de superfícies", _o)
        _c, _o = _r("iniciar", "RU1", "--titulo", "t", "--trilha", "ultra-rapida",
                    "--risco", "alto", "--forcar", "--nota", "t")
        checar(_c != 0 and "não tem step 9" in _o,
               "alto em trilha que implementa sem o 9 é recusado, MESMO com --forcar", _o)
        _c, _o = _r("iniciar", "RB1", "--titulo", "t", "--trilha", "curta",
                    "--risco", "baixo", "--superficies", "pagamento")
        checar(_c != 0 and "se contradiz" in _o, "baixo com superfície marcada é recusado", _o)
        _c, _o = _r("iniciar", "RS1", "--titulo", "t", "--trilha", "curta",
                    "--superficies", "pagamento")
        checar(_c != 0, "superfície sem --risco é recusada", _o)
        _c, _o = _r("iniciar", "RS2", "--titulo", "t", "--trilha", "curta",
                    "--risco", "alto", "--superficies", "carteira")
        checar(_c != 0 and "carteira" in _o, "superfície desconhecida é recusada", _o)
        _c, _o = _r("iniciar", "RN1", "--titulo", "t", "--trilha", "curta")
        checar(_c == 0 and "RISCO NÃO DECLARADO" in _o, "sem --risco abre, e avisa", _o)
        _c, _o = _r("iniciar", "RP1", "--titulo", "t", "--trilha", "curta",
                    "--risco", "padrao", "--superficies", "migracao")
        checar(_c == 0 and "RISCO PADRÃO COM SUPERFÍCIE MARCADA" in _o,
               "padrao com superfície abre, e avisa", _o)
        _c, _o = _r("iniciar", "RL1", "--titulo", "t", "--trilha", "completa",
                    "--risco", "baixo")
        checar(_c == 0 and "RISCO BAIXO NA TRILHA" in _o, "baixo na completa abre, e avisa", _o)

        _c, _o = _r("iniciar", "RA1", "--titulo", "t", "--trilha", "curta",
                    "--risco", "alto", "--superficies", "autenticacao,dados-pessoais")
        _t = _md("RA1")
        checar(_c == 0 and "risco: alto" in _t
               and "superficies: autenticacao dados-pessoais" in _t
               and "Risco alto, confirmado por quem abriu" in _t,
               "alto abre, grava risco e superfícies, e o histórico diz quem confirmou", _o)
        _c, _o = _r("status", "RA1")
        checar("risco:" in _o and "alto" in _o, "`status` mostra o risco", _o)
        _c, _o = _r("avancar", "RA1", "--step", "8", "--trilha", "rapida")
        checar(_c != 0 and "--trilha muda RA1" in _o,
               "--trilha sem --forcar é recusado (a ajuda dizia, o código não conferia)", _o)
        _c, _o = _r("avancar", "RA1", "--step", "8", "--forcar", "--trilha",
                    "ultra-rapida", "--nota", "t")
        checar(_c != 0 and "não tem step 9" in _o,
               "trilha mudada para uma sem o 9, com risco alto, é recusada", _o)
        _r("avancar", "RA1", "--step", "8", "--forcar", "--nota", "t")
        _r("conferencia", "RA1", "--ferramenta", "gate:lint", "--veredicto", "ok")
        _r("conferencia", "RA1", "--ferramenta", "gate:sast", "--veredicto",
           "nao-coberta", "--detalhe", "sem regra")
        _c, _o = _r("avancar", "RA1", "--step", "9", "--forcar", "--nota", "t")
        checar(_c != 0 and "risco alto" in _o,
               "no risco alto, sast `nao-coberta` segura o 8→9", _o)
        _r("conferencia", "RA1", "--ferramenta", "gate:sast", "--veredicto", "ok")
        _c, _o = _r("avancar", "RA1", "--step", "9", "--nota", "t")
        checar(_c == 0 and "| seguranca | exigida |" in _md("RA1"),
               "a entrada no 9 grava `seguranca` exigida", _o)
        _r("conferencia", "RA1", "--ferramenta", "seguranca", "--veredicto",
           "nao-coberta", "--detalhe", "pulei")
        _r("avancar", "RA1", "--step", "10", "--forcar", "--nota", "t")
        _c, _o = _r("concluir", "RA1")
        checar(_c != 0 and "não sai por `nao-coberta`" in _o,
               "no risco alto, `seguranca` em `nao-coberta` segura o concluir", _o)
        _r("conferencia", "RA1", "--ferramenta", "seguranca", "--veredicto", "ok")
        _c, _o = _r("concluir", "RA1")
        checar(_c == 0, "com a frente de segurança `ok`, conclui", _o)

        _c, _o = _r("risco", "RN1", "--nivel", "alto")
        checar(_c != 0 and "--nota" in _o, "`risco` sem --nota é recusado", _o)
        _r("avancar", "RN1", "--step", "9", "--forcar", "--nota", "t")
        _c, _o = _r("risco", "RN1", "--nivel", "alto", "--superficies", "pagamento",
                    "--nota", "o diff toca o checkout")
        _t = _md("RN1")
        checar(_c == 0 and "risco: alto" in _t and "| seguranca | exigida |" in _t
               and "Risco: padrao → alto" in _t,
               "subir para alto já no 9 grava a exigência que o `avancar` teria gravado", _o)
        _r("iniciar", "RU2", "--titulo", "t", "--trilha", "ultra-rapida")
        _c, _o = _r("risco", "RU2", "--nivel", "alto", "--nota", "t")
        checar(_c != 0 and "não tem step 9" in _o, "`risco` recusa alto na ultra-rápida", _o)

        _cfg5.write_text('[projeto]\nnome = "t"\n[gates]\nlint = "true"\n', encoding="utf-8")
        _r("iniciar", "RA2", "--titulo", "t", "--trilha", "curta", "--risco", "alto")
        _r("avancar", "RA2", "--step", "8", "--forcar", "--nota", "t")
        _r("conferencia", "RA2", "--ferramenta", "gate:lint", "--veredicto", "ok")
        _c, _o = _r("avancar", "RA2", "--step", "9", "--nota", "t")
        checar(_c == 0 and "RISCO ALTO SEM SAST" in _o,
               "risco alto num projeto sem `[gates] sast` avisa na entrada do 9", _o)
    finally:
        shutil.rmtree(_t5, ignore_errors=True)

    print("\nO que mudou desde o portão: a saída grava, o `desde-aprovacao` compara")
    # A regra "a parte já aceita não se re-litiga" não tinha o que separasse a
    # parte aceita da nova. Agora cada saída de portão grava impressão e cópia.
    _t6 = Path(tempfile.mkdtemp(prefix="portao-")).resolve()
    try:
        _ag6 = _t6 / ".agents"
        (_ag6 / "elcamargo-flow").mkdir(parents=True)
        (_ag6 / "config.toml").write_text('[projeto]\nnome = "t"\n', encoding="utf-8")
        (_t6 / "docs").mkdir()
        (_t6 / "docs" / "sdd.md").write_text("linha 1\nlinha 2\nlinha 3\n", encoding="utf-8")
        (_t6 / "docs" / "velho.md").write_text("v\n", encoding="utf-8")
        _sp4.run(["git", "init", "-q"], cwd=_t6, capture_output=True)
        _sp4.run(["git", "add", "-A"], cwd=_t6, capture_output=True)
        _sp4.run(["git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "i"],
                 cwd=_t6, capture_output=True)
        _env6 = {**os.environ, "ELCAMARGO_AGENTS_DIR": str(_ag6)}

        def _p(*args):
            r = _sp4.run([sys.executable, _F4, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", cwd=str(_t6), env=_env6,
                         timeout=120)
            return r.returncode, r.stdout + r.stderr

        _base6 = _ag6 / "atividades" / "PG1-portoes"
        _p("iniciar", "PG1", "--titulo", "t", "--trilha", "completa", "--risco", "padrao")
        _p("avancar", "PG1", "--step", "5", "--forcar", "--nota", "t")
        _c, _o = _p("desde-aprovacao", "PG1")
        checar(_c == 0 and "nada a comparar" in _o,
               "primeira passagem: nada a comparar, e não é erro", _o)
        _p("artefato", "PG1", "--tipo", "sdd-sistema", "--caminho", "docs/sdd.md")
        _p("artefato", "PG1", "--tipo", "prototipo", "--caminho", "https://figma.com/x")
        _p("artefato", "PG1", "--tipo", "anexo", "--caminho", "docs/velho.md")
        _c, _o = _p("avancar", "PG1", "--step", "3", "--forcar", "--nota", "falta regra")
        _m = {}
        try:
            _m = json.loads((_base6 / "01-p5-devolvido" / "manifesto.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        _a = {a["caminho"]: a for a in _m.get("artefatos", [])}
        checar(_c == 0 and _m.get("desfecho") == "devolvido" and len(_m.get("arvore", "")) == 40
               and len(_m.get("commit", "")) == 40
               and _a.get("docs/sdd.md", {}).get("sha256")
               and (_base6 / "01-p5-devolvido" / (_a.get("docs/sdd.md", {}).get("copia") or "x")).is_file()
               and _a.get("https://figma.com/x", {}).get("motivo") == "não é arquivo",
               "a devolução grava manifesto com commit, árvore, impressão e cópia", _o + str(_m))
        _h = Atividade.ler(_ag6 / "atividades" / "PG1.md").history
        checar(_h[-1][1].startswith("3 ") and _h[-2][1] == "portão gravado"
               and "Portão 5 devolvido" in _h[-2][2],
               "a linha do registro entra ANTES da transição, que segue sendo a última", str(_h[-3:]))

        (_t6 / "docs" / "sdd.md").write_text("linha 1\nlinha 2 mudada\nlinha 3\n", encoding="utf-8")
        (_t6 / "src").mkdir()
        (_t6 / "src" / "b.py").write_text("b = 1\n", encoding="utf-8")
        (_t6 / "docs" / "novo.md").write_text("n\n", encoding="utf-8")
        _p("artefato", "PG1", "--tipo", "anexo", "--caminho", "docs/novo.md")
        _p("artefato", "PG1", "--tipo", "anexo", "--caminho", "docs/velho.md", "--retirar",
           "--nota", "t")
        _p("avancar", "PG1", "--step", "5", "--forcar", "--nota", "t")
        _c, _o = _p("desde-aprovacao", "PG1")
        checar(_c == 0 and "desde o portão 5 devolvido" in _o
               and "[mudou]   sdd-sistema: docs/sdd.md" in _o
               and "+linha 2 mudada" in _o and "-linha 2" in _o
               and "[novo]    anexo: docs/novo.md" in _o
               and "[saiu]    anexo: docs/velho.md" in _o
               and "pode ter mudado sem o endereço mudar" in _o
               and "a árvore mudou" in _o and "src/b.py" in _o,
               "de volta ao 5: o diff da spec, o artefato novo, o que saiu, o link e o código", _o)

        _p("avancar", "PG1", "--step", "6", "--forcar", "--nota", "aprovado")
        _c, _o = _p("desde-aprovacao", "PG1")
        checar(_c == 0 and "desde o portão 5 aprovado" in _o
               and "[igual]   sdd-sistema" in _o and "a árvore é a mesma" in _o,
               "fora de portão: compara com o último de qualquer um", _o)
        _c, _o = _p("desde-aprovacao", "PG1", "--portao", "7")
        checar(_c == 0 and "não saiu do portão 7" in _o, "`--portao` de um que não saiu", _o)
        _pc = flow_state.percurso(Atividade.ler(_ag6 / "atividades" / "PG1.md").history)
        checar(_pc["portoes"]["5"] == {"aprovado": 1, "devolvido": 1}
               and len(_pc["devolucoes"]) == 1 and _pc["voltas_total"] == 0,
               "a linha do registro não vira marco no percurso", str(_pc))
        _c, _o = _p("tempo", "PG1")
        checar("portão gravado" not in _o, "nem no `tempo`", _o)

        _p("avancar", "PG1", "--step", "7", "--forcar", "--nota", "t")
        (_t6 / "docs" / "sdd.md").write_text(
            "".join(f"linha {i}\n" for i in range(400)), encoding="utf-8")
        _c, _o = _p("desde-aprovacao", "PG1")
        checar("desde o portão 5 aprovado" in _o and "`--completo` mostra tudo" in _o,
               "no 7 sem registro dele, compara com o 5; diff longo é cortado", _o)
        _c, _o = _p("desde-aprovacao", "PG1", "--completo")
        checar("`--completo` mostra tudo" not in _o and "+linha 399" in _o,
               "`--completo` mostra o diff inteiro", _o[-300:])

        _p("avancar", "PG1", "--step", "10", "--forcar", "--nota", "t")
        _c, _o = _p("avancar", "PG1", "--step", "9", "--forcar", "--nota", "volta")
        _h = Atividade.ler(_ag6 / "atividades" / "PG1.md").history
        checar(_c == 0 and _h[-1][1].startswith("9 ") and "Baseline do step 9" in _h[-1][2]
               and _h[-2][1] == "portão gravado" and "Portão 10 devolvido" in _h[-2][2],
               "10→9: a baseline do 9 continua na linha da transição", str(_h[-2:]))
        _p("avancar", "PG1", "--step", "10", "--forcar", "--nota", "t")
        _c, _o = _p("concluir", "PG1", "--forcar", "--nota", "aceito")
        _pastas = sorted(d.name for d in _base6.iterdir())
        checar(_c == 0 and _pastas[-1] == "05-p10-aprovado"
               and "03-p7-aprovado" in _pastas and "04-p10-devolvido" in _pastas,
               "o concluir saindo do 10 grava a aprovação", str(_pastas) + _o)
    finally:
        shutil.rmtree(_t6, ignore_errors=True)

    print("\nO contexto do step 9 não é o do step 8, e o modelo da frente só vale com veredito")
    # A regra "o próximo step roda em contexto novo" só valia no modo
    # orquestrador. Contexto é sessão MAIS subagente: o hook grava, o
    # `flow_state` compara.
    _t7 = Path(tempfile.mkdtemp(prefix="contexto-")).resolve()
    try:
        _ag7 = _t7 / ".agents"
        (_ag7 / "elcamargo-flow").mkdir(parents=True)
        _cfg7 = _ag7 / "config.toml"
        _cfg7.write_text('[projeto]\nnome = "t"\n[fluxo]\nsegundos_de_step_relampago = 0\n'
                         '[gates]\nlint = "true"\n', encoding="utf-8")
        _env7 = {**os.environ, "ELCAMARGO_AGENTS_DIR": str(_ag7)}

        def _q(*args):
            r = _sp4.run([sys.executable, _F4, *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", cwd=str(_t7), env=_env7,
                         timeout=120)
            return r.returncode, r.stdout + r.stderr

        def _ctx(sessao, agente="", atras=0):
            (_ag7 / ".contexto-atual").write_text(json.dumps(
                {"sessao": sessao, "agente": agente, "quando": time.time() - atras}),
                encoding="utf-8")

        def _ate_o_9(ident):
            _q("iniciar", ident, "--titulo", "t", "--trilha", "curta")
            _q("avancar", ident, "--step", "8", "--forcar", "--nota", "t")
            _q("conferencia", ident, "--ferramenta", "gate:lint", "--veredicto", "ok")
            return _q("avancar", ident, "--step", "9", "--nota", "t")

        _ctx("s1")
        _c, _o = _ate_o_9("CX1")
        _m = Atividade.ler(_ag7 / "atividades" / "CX1.md").meta
        checar(_c == 0 and _m.get("contexto_do_8") == "s1/janela",
               "o `avancar` 8→9 grava o contexto que fez o 8", _o + str(_m))
        _c, _o = _q("status", "CX1")
        checar(_c == 0 and "MESMO CONTEXTO DO STEP 8" in _o and "na mesma janela" in _o
               and "recusa a partir deste contexto" in _o,
               "o `status` do 9 na mesma janela avisa no começo do step", _o)
        _c, _o = _q("avancar", "CX1", "--nota", "revisado")
        checar(_c != 0 and "MESMO CONTEXTO DO STEP 8" in _o and "--forcar --nota" in _o
               and Atividade.ler(_ag7 / "atividades" / "CX1.md").step == 9,
               "e o `avancar` para o 10 recusa, sem gravar", _o)
        _c, _o = _q("avancar", "CX1", "--step", "8", "--forcar", "--nota", "volta 1: 2 achados")
        checar(_c == 0, "voltar ao 8 para corrigir passa: não aprova nada", _o)
        _ctx("s1", "ag-8b")
        _q("conferencia", "CX1", "--ferramenta", "gate:lint", "--veredicto", "ok")
        _q("avancar", "CX1", "--step", "9", "--forcar", "--nota", "corrigidos 2")
        checar(Atividade.ler(_ag7 / "atividades" / "CX1.md").meta.get("contexto_do_8")
               == "s1/ag-8b", "a volta de correção troca o registro pelo 8 da volta 2")
        _ctx("s1", "ag-9")
        _c, _o = _q("status", "CX1")
        checar("MESMO CONTEXTO" not in _o,
               "mesma sessão, subagente diferente: é o modo orquestrador, e passa", _o)
        _c, _o = _q("avancar", "CX1", "--nota", "revisado")
        checar(_c == 0 and Atividade.ler(_ag7 / "atividades" / "CX1.md").step == 10,
               "e o `avancar` para o 10 também", _o)

        _ctx("s2")
        _ate_o_9("CX2")
        _ctx("s3")
        _c, _o = _q("avancar", "CX2", "--nota", "revisado")
        checar(_c == 0, "sessão nova (ou `/clear`) passa", _o)
        _ctx("s4")
        _ate_o_9("CX3")
        _ctx("s4", atras=flow_state.CONTEXTO_VALE_POR + 5)
        _c, _o = _q("avancar", "CX3", "--nota", "revisado")
        checar(_c == 0, "registro velho é \"não sei\", e não acusa ninguém", _o)
        _ctx("s5")
        _ate_o_9("CX4")
        _c, _o = _q("avancar", "CX4", "--forcar", "--nota", "rodou na mesma janela, sabido")
        checar(_c == 0, "`--forcar --nota` atravessa, e fica escrito", _o)
        (_ag7 / ".contexto-atual").unlink()
        _c, _o = _ate_o_9("CX5")
        checar(_c == 0 and "contexto_do_8" not in Atividade.ler(
                   _ag7 / "atividades" / "CX5.md").meta,
               "sem o hook não grava nada, e a trava cala", _o)

        # 2b: `[revisao.modelo]` só vale com veredito `adota` da perna sombra.
        _ctx("s6")
        _ate_o_9("CX6")
        _ctx("s7")
        _c, _o = _q("status", "CX6")
        checar("modelo:" not in _o, "sem `[revisao.modelo]`, o `status` não fala de modelo", _o)
        _cfg7.write_text(_cfg7.read_text(encoding="utf-8")
                         + '[revisao.modelo]\ncode-reviewer = "sonnet"\nsecurity-reviewer = "haiku"\n'
                           'frente-que-nao-existe = "sonnet"\n', encoding="utf-8")
        _c, _o = _q("status", "CX6")
        checar("`code-reviewer = \"sonnet\"` IGNORADA: nenhum par" in _o
               and "`security-reviewer = \"haiku\"` IGNORADA" in _o
               and "`frente-que-nao-existe` não é frente do step 9" in _o
               and "dispara com" not in _o,
               "sem par da perna sombra, a chave é ignorada e diz por quê", _o)
        _par = {"frente": "code-reviewer", "sombra": "sonnet", "graves_principal": 2,
                "graves_vistos_pela_sombra": 2, "veto_principal": 0}
        (_ag7 / "perna-sombra.jsonl").write_text(
            "".join(json.dumps(_par) + "\n" for _ in range(3)), encoding="utf-8")
        _c, _o = _q("status", "CX6")
        checar("IGNORADA: sem veredito" in _o and "dispara com" not in _o,
               "com menos de cinco pares, ainda ignorada", _o)
        (_ag7 / "perna-sombra.jsonl").write_text(
            "".join(json.dumps(_par) + "\n" for _ in range(6)), encoding="utf-8")
        _c, _o = _q("status", "CX6")
        checar("code-reviewer dispara com `model: \"sonnet\"`" in _o
               and "`security-reviewer = \"haiku\"` IGNORADA" in _o,
               "com veredito `adota`, vale — só na frente e no modelo medidos", _o)
        with open(_ag7 / "perna-sombra.jsonl", "a", encoding="utf-8") as _fh:
            _fh.write(json.dumps({**_par, "veto_principal": 1}) + "\n")
        _c, _o = _q("status", "CX6")
        checar("IGNORADA: REJEITA" in _o and "dispara com" not in _o,
               "um `bloqueia` perdido derruba de novo", _o)
    finally:
        shutil.rmtree(_t7, ignore_errors=True)

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Tudo passou.")
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
    sys.exit(main_teste())
