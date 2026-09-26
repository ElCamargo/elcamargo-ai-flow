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
from pathlib import Path

AQUI = Path(__file__).parent.resolve()
sys.path.insert(0, str(AQUI))

import flow_state  # noqa: E402
from flow_state import Atividade, FlowStateError, main  # noqa: E402

falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


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
        checar(len(lida.history) == 1 + len(casos),
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
        checar(len(lida.history) == 7,
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

        r = _sp.run(cmd, capture_output=True, text=True, input=entrada, cwd=str(_tmp))

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


    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Tudo passou.")
    return 0


if __name__ == "__main__":
    sys.exit(main_teste())
