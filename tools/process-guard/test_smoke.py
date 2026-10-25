#!/usr/bin/env python3
"""Fumaça do guarda de processo.

O defeito que a originou: a frente de execução limpou os próprios processos com
`pkill -f "nest start"`, o padrão casou com o backend de OUTRA atividade na
mesma máquina, e quatro serviços caíram. A frente havia escolhido portas livres
e isolado banco e vhost -- isolar porta não protege de `pkill -f`.

Este teste sobe um ouvinte de verdade, marca, mata, e exige que o `conferir`
acuse. Guarda de dano que não acusa dano é pior que nenhum: parece controle.
"""
from __future__ import annotations

import json
import os
import socket
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
GUARDA = AQUI / "process_guard.py"
FLOW = AQUI.parent / "flow-state" / "flow_state.py"

falhas: list[str] = []


def checar(condicao: bool, descricao: str, detalhe: str = "") -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)
        if detalhe:
            print(f"          {detalhe.strip()[:400]}")


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rodar(raiz: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARDA), *args],
                          cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
        (raiz / ".agents" / "atividades").mkdir(parents=True)
        # Esta suite roteiriza o fluxo inteiro em subprocesso, em
        # milissegundos: a guarda do step relampago recusaria a entrada no
        # portao 10. Declarar `0` e' o caminho previsto para quem roteiriza.
        (raiz / ".agents" / "config.toml").write_text(
            '[projeto]\nnome = "t"\n\n[fluxo]\n'
            'segundos_de_step_relampago = 0\n', encoding="utf-8")

        porta = porta_livre()
        # Um ouvinte de verdade: o guarda lê `lsof`, então processo fingido
        # não provaria nada.
        ouvinte = subprocess.Popen(
            [sys.executable, "-c",
             f"import socket,time\n"
             f"s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
             f"s.bind(('127.0.0.1',{porta})); s.listen(1); time.sleep(120)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                time.sleep(0.1)
                if rodar(raiz, "marcar", "--id", "T").stdout.count(str(porta)):
                    break

            print("\nmarcar")
            r = rodar(raiz, "marcar", "--id", "T")
            if "lsof" in r.stderr and "não está nesta máquina" in r.stderr:
                print("  lsof ausente: o guarda declara a lacuna em vez de adivinhar.")
                return 0
            checar(r.returncode == 0, "marcar responde 0")
            checar(str(porta) in r.stdout, "e enxerga o ouvinte que acabou de subir")
            checar("NÃO SÃO SUAS" in r.stdout,
                   "e avisa que as portas de antes não são de quem dispara")
            checar((raiz / ".agents" / f".processos-T.json").exists(),
                   "a marca fica em disco, ao lado da atividade")

            print("\nconferir, com tudo de pé")
            r = rodar(raiz, "conferir", "--id", "T")
            checar(r.returncode == 0, "responde 0 quando nada caiu")
            checar("NÃO prova" in r.stdout,
                   "e declara o que a conferência não prova")

            print("\nconferir, depois de a porta cair — o defeito de 10/09")
            ouvinte.kill()
            ouvinte.wait(timeout=10)
            time.sleep(0.5)
            r = rodar(raiz, "conferir", "--id", "T")
            checar(r.returncode == 1, "ACUSA: responde 1 quando uma porta de antes caiu")
            checar("CAIU" in r.stdout and str(porta) in r.stdout,
                   "e nomeia a porta que ficou sem serviço")
            checar("pkill" in r.stdout,
                   "e diz a causa provável, que é o padrão genérico")
            checar("individuais" in r.stdout,
                   "e avisa da armadilha de religar com script tudo-ou-nada")
        finally:
            if ouvinte.poll() is None:
                ouvinte.kill()

        print("\nmedir: o pico so' existe enquanto o processo existe")
        # Pico de RSS nao sai de transcrito -- transcrito tem token, turno e
        # horario. Medir depois e' impossivel, e estimar seria inventar. Por
        # isso o amostrador roda DURANTE, e por isso ausencia de medida e'
        # lacuna declarada, nao zero.
        r = rodar(raiz, "medir", "--id", "M", "--iniciar", "--teto-min", "1")
        codigo, saida = r.returncode, r.stdout + r.stderr
        checar(codigo == 0, "liga o amostrador", saida)
        checar("pid" in saida, "e diz o pid dele", saida)
        time.sleep(5)
        r = rodar(raiz, "medir", "--id", "M", "--parar")
        codigo, saida = r.returncode, r.stdout + r.stderr
        checar(codigo == 0, "para e responde 0", saida)
        checar("A FRENTE" in saida, "e separa a frente da maquina", saida)
        checar("amostras" in saida and "0 amostras" not in saida,
               "com amostras de verdade, colhidas no intervalo", saida)
        # O defeito da 2.29.x: o instrumento media a MAQUINA e chamava de
        # frente. Na primeira medida real o "maior processo" foi a VM do
        # Docker.
        checar("descendentes de" in saida,
               "e diz de QUEM sao os processos que ela somou", saida)
        checar("swap em uso" in saida and "compressor" in saida,
               "e mostra a pressao, que e' o que trava", saida)
        checar("nao e' limiar" in saida or "não é limiar" in saida,
               "e declara que soma de RSS nao serve de limiar", saida)
        # O medidor externo desta investigacao reportou 2.032s de "paralisia"
        # que eram tampa fechada. Sono e travamento nao se somam.
        checar("PARALISIA" in saida and "travada" in saida,
               "separa paralisia de sono, em vez de somar os dois", saida)
        import json as _j
        med = _j.loads((raiz / ".agents" / ".memoria-M.json").read_text())
        checar("travou_s" in med and "dormiu_s" in med,
               "e grava as duas parcelas separadas", str(med)[:200])
        checar(med["dormiu_s"] == 0,
               "maquina acordada durante o teste: dormiu 0s", str(med)[:200])
        # A prosa nao chega ao portao 10; a linha de Conferencias chega.
        corpo_m = (raiz / ".agents" / "atividades" / "M.md")
        if corpo_m.is_file():
            checar("swap" in corpo_m.read_text(encoding="utf-8"),
                   "e o swap entra na tabela de Conferencias, nao so' na tela",
                   corpo_m.read_text(encoding="utf-8")[:300])

        print("\nmedir: a frente e' a ARVORE de quem conduz, nao a maquina")
        sys.path.insert(0, str(AQUI))
        import process_guard as pg  # noqa: E402
        # pai 10 -> filhos 11 e 12; 99 e' de outra janela e nao pode entrar.
        linhas = [(10, 1, 1048576, "/x/claude"), (11, 10, 2097152, "/x/next-server"),
                  (12, 10, 1048576, "/x/node"), (99, 1, 8388608, "/x/OutraJanela")]
        a = pg._arvore_de(10, linhas)
        checar(a["frente_gb"] == 4.0,
               "soma so' a arvore da raiz (4 GB), ignorando os 8 GB alheios",
               str(a))
        checar(a["maior_processo"] == "next-server",
               "e o maior processo e' o maior DELA, nao o da maquina", str(a))
        checar(a["processos"] == 3, "e conta quantos processos eram", str(a))

        pressao = pg._pressao_do_sistema()
        checar("swap_usado_gb" in pressao and "em_uso_gb" in pressao,
               "a leitura de pressao traz swap e uso reais", str(pressao))
        agora = pg._pressao_agora(os.getpid())
        checar(agora is not None and agora.get("frente_gb") is not None,
               "e a leitura completa atribui uma frente", str(agora))

        print("\nmedir: medida velha nao quebra quem for ler")
        import json as _json
        velha = raiz / ".agents" / ".memoria-V.json"
        velha.write_text(_json.dumps({"soma_rss_gb": 9.9, "maior_gb": 1.1,
                                      "maior_processo": "x", "amostras": 7}),
                         encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "V", "--parar")
        checar(r.returncode == 0, "le o esquema antigo sem quebrar",
               r.stdout + r.stderr)
        checar("esquema antigo" in (r.stdout + r.stderr),
               "e diz que e' antigo, em vez de fingir que mediu a frente",
               r.stdout + r.stderr)

        print("\nmedir: a lacuna se REGISTRA, nao so' se anuncia")
        # Ligar o amostrador escrito numa skill e' obrigacao em prosa: quem
        # esquecer nao deixa rastro, e o portao 10 recebe a revisao sem saber
        # que a memoria nunca foi medida. Registrado, some do impresso e fica
        # na tabela de Conferencias.
        ativ = raiz / ".agents" / "atividades" / "R1.md"
        subprocess.run([sys.executable, str(FLOW), "iniciar", "R1",
                        "--titulo", "Rev", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rodar(raiz, "medir", "--id", "R1", "--parar")
        corpo = ativ.read_text(encoding="utf-8")
        checar("| memoria | nao-coberta |" in corpo,
               "parar sem medida grava `memoria: nao-coberta` na atividade",
               corpo[-400:])

        subprocess.run([sys.executable, str(FLOW), "iniciar", "R2",
                        "--titulo", "Rev2", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rodar(raiz, "medir", "--id", "R2", "--iniciar", "--teto-min", "1")
        time.sleep(5)
        rodar(raiz, "medir", "--id", "R2", "--parar")
        corpo = (raiz / ".agents" / "atividades" / "R2.md").read_text(encoding="utf-8")
        checar("| memoria | ok |" in corpo and "GB" in corpo,
               "e o ciclo completo grava `ok` com o pico medido",
               corpo[-400:])

        print("\nmedir: amostrador MORTO nao pode virar silencio")
        # O buraco que a 2.27.1 deixou: `registrar` morava so' no `--parar`, e
        # cobria um caso so' -- "liguei, nao mediu, e vim fechar". Deixava de
        # fora o cenario que ORIGINOU a medida: a maquina trava, leva a sessao
        # junto, `--parar` nunca roda, e a atividade chega ao portao 10 sem uma
        # palavra sobre memoria -- agora com a APARENCIA de tratado, porque a
        # ferramenta existe. Achado por acme-backoffice-0f com
        # `kill -9` no proprio amostrador.
        subprocess.run([sys.executable, str(FLOW), "iniciar", "R3",
                        "--titulo", "Rev3", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        r = rodar(raiz, "medir", "--id", "R3", "--iniciar", "--teto-min", "5")
        saida = r.stdout + r.stderr
        corpo = (raiz / ".agents" / "atividades" / "R3.md").read_text(encoding="utf-8")
        checar("| memoria | exigida |" in corpo,
               "o `--iniciar` grava a divida ANTES de existir o que medir",
               corpo[-300:])
        pid = int(saida.split("pid ")[1].split(")")[0])
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        for _ in range(4):
            subprocess.run([sys.executable, str(FLOW), "avancar", "R3",
                            "--nota", "x"], cwd=raiz, capture_output=True)
        r = subprocess.run([sys.executable, str(FLOW), "concluir", "R3",
                            "--nota", "publicada no PR"],
                           cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        checar(r.returncode != 0,
               "e com o amostrador morto o `concluir` SEGURA, em vez de passar",
               r.stdout + r.stderr)

        print("\nmarcar: ninguem ligou o amostrador tambem nao pode passar")
        # `--iniciar` so' escreve a divida se alguem o rodar -- e "alguem
        # precisa rodar" era a obrigacao em prosa que a mecanizacao veio
        # substituir. `marcar` roda antes do disparo, sempre.
        subprocess.run([sys.executable, str(FLOW), "iniciar", "R4",
                        "--titulo", "Rev4", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rodar(raiz, "marcar", "--id", "R4")
        corpo = (raiz / ".agents" / "atividades" / "R4.md").read_text(encoding="utf-8")
        checar("| memoria | exigida |" in corpo,
               "`marcar` deixa a divida escrita mesmo sem ninguem lembrar do amostrador",
               corpo[-300:])
        for _ in range(4):
            subprocess.run([sys.executable, str(FLOW), "avancar", "R4",
                            "--nota", "x"], cwd=raiz, capture_output=True)
        r = subprocess.run([sys.executable, str(FLOW), "concluir", "R4",
                            "--nota", "publicada no PR"],
                           cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        checar(r.returncode != 0, "e o `concluir` segura", r.stdout + r.stderr)

        # E a saida continua existindo: quem DECIDE nao medir declara.
        #
        # SAO DUAS declaracoes desde a 2.56.0, e nao uma. O `marcar` passou a
        # abrir tambem a divida de `sobra`, e quem decide nao conferir o que
        # deixou de pe tem de dizer isso com todas as letras -- declarar a
        # memoria nao cobre a maquina. Esta linha so' existe porque a suite
        # ficou vermelha ao ligar o mecanismo: a divida nova nao pode ser
        # fechada de carona na antiga.
        for _ferramenta, _detalhe in (("memoria", "maquina sem ps"),
                                      ("sobra", "maquina sem docker nem lsof")):
            subprocess.run([sys.executable, str(FLOW), "conferencia", "R4",
                            "--ferramenta", _ferramenta,
                            "--veredicto", "nao-coberta",
                            "--detalhe", _detalhe],
                           cwd=raiz, capture_output=True)
        r = subprocess.run([sys.executable, str(FLOW), "concluir", "R4",
                            "--nota", "publicada no PR"],
                           cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
        checar(r.returncode == 0,
               "`nao-coberta` declarada passa: decidir nao medir continua permitido",
               r.stdout + r.stderr)

        print("\nmedir: nao ter medido e' diferente de ter medido zero")
        r = rodar(raiz, "medir", "--id", "NUNCA-LIGADO", "--parar")
        codigo, saida = r.returncode, r.stdout + r.stderr
        checar(codigo == 1, "parar sem medida recusa", saida)
        checar("NÃO COBERTA" in saida,
               "e manda declarar a dimensao, em vez de seguir como se coubesse",
               saida)

        r = rodar(raiz, "medir", "--id", "M", "--iniciar", "--parar")
        codigo, saida = r.returncode, r.stdout + r.stderr
        checar(codigo == 1, "--iniciar e --parar juntos e' recusado", saida)
        checar("mediria zero" in saida, "porque mediria zero", saida)

        print("\namostrador sobrevive a' SEGUNDA amostra")
        # O defeito que originou este teste: `anterior` era ligada duas vezes
        # no mesmo laco -- tupla para a deteccao de buraco, float para o pico
        # -- e a segunda volta indexava o float. O amostrador morria calado na
        # amostra 2, o arquivo ficava com a leitura da largada, e o `--parar`
        # imprimia aquilo como pico. Quinze medidas passaram assim.
        #
        # A suite anterior nao pegava porque provava que o amostrador LIGA.
        # Ele ligava. Morria depois.
        r = rodar(raiz, "amostrador", "--id", "AM", "--teto-min", "0.12",
                  "--raiz", str(os.getpid()))
        medida = raiz / ".agents" / ".memoria-AM.json"
        checar(r.returncode == 0, "o amostrador termina sem excecao",
               r.stdout + r.stderr)
        checar(medida.exists(), "e deixa arquivo de medida")
        if medida.exists():
            d = json.loads(medida.read_text(encoding="utf-8"))
            checar(d.get("erro") is None,
                   "sem erro gravado no proprio arquivo", str(d.get("traco")))
            checar(d.get("amostras", 0) >= 2,
                   "com DUAS amostras ou mais -- uma so' e' a largada, nao pico",
                   f"amostras={d.get('amostras')}")

        print("\n`--parar` recusa chamar UMA amostra de pico")
        (raiz / ".agents" / ".memoria-SO1.json").write_text(json.dumps({
            "raiz_pid": os.getpid(), "amostras": 1, "inicio": "2026-09-14T00:00:00",
            "fim": "2026-09-14T00:00:00", "base": {}, "picos": {"frente_gb": 0.44},
            "minimos": {}, "pico_frente": {"frente_gb": 0.44}, "buracos": [],
            "travou_s": 0.0, "dormiu_s": 0.0}), encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "SO1", "--parar")
        saida = r.stdout + r.stderr
        checar(r.returncode == 1, "recusa a medida de uma amostra so'", saida)
        checar("não o pico da atividade" in saida,
               "e diz que aquilo e' a largada, nao o pico", saida)
        checar("0.44" not in saida,
               "sem imprimir o numero falso como se fosse medida", saida)

        print("\n`--parar` acusa amostrador que morreu")
        (raiz / ".agents" / ".memoria-MORTO.json").write_text(json.dumps({
            "raiz_pid": os.getpid(), "amostras": 7, "inicio": "2026-09-14T00:00:00",
            "fim": "2026-09-14T00:00:14", "base": {}, "picos": {"frente_gb": 1.0},
            "minimos": {}, "pico_frente": {"frente_gb": 1.0}, "buracos": [],
            "travou_s": 0.0, "dormiu_s": 0.0,
            "erro": "TypeError: 'NoneType' object is not subscriptable",
            "traco": "..."}), encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "MORTO", "--parar")
        saida = r.stdout + r.stderr
        checar(r.returncode == 1, "recusa medida cujo amostrador morreu", saida)
        checar("MORREU" in saida, "e nomeia a morte em vez de publicar o pico",
               saida)

        print("\n`auditar` marca no proprio arquivo o que nao e' medida")
        # A recusa do `--parar` protege o futuro; o passado fica em disco.
        # Sugerido por `acme-backoffice-23` em 14/09/2026.
        for nome, corpo in (
            ("VELHA1", {"amostras": 1, "picos": {"frente_gb": 0.44}}),
            ("VELHA2", {"amostras": 9, "picos": {"frente_gb": 1.2},
                        "erro": "TypeError: x"}),
            ("SADIA", {"amostras": 300, "picos": {"frente_gb": 4.9}}),
        ):
            (raiz / ".agents" / f".memoria-{nome}.json").write_text(
                json.dumps(corpo), encoding="utf-8")
        (raiz / ".agents" / "atividades" / "ATV.md").write_text(
            "| 2026-09-12 10:00:00 | memoria | ok | frente pico 0.44 GB, "
            "travada 0.0s, 1 amostras |\n"
            "| 2026-09-11 17:38:45 | memoria | ok | frente pico 4.52 GB, "
            "1621 amostras |\n", encoding="utf-8")
        r = rodar(raiz, "auditar")
        saida = r.stdout + r.stderr
        checar(r.returncode == 0, "auditar roda sem --id", saida)
        d1 = json.loads((raiz / ".agents" / ".memoria-VELHA1.json").read_text())
        d2 = json.loads((raiz / ".agents" / ".memoria-VELHA2.json").read_text())
        d3 = json.loads((raiz / ".agents" / ".memoria-SADIA.json").read_text())
        checar(bool(d1.get("invalida")), "marca a de uma amostra")
        checar(bool(d2.get("invalida")), "marca a que gravou erro")
        checar(d3.get("invalida") is None, "e NAO marca a sadia")
        checar(d1.get("picos", {}).get("frente_gb") == 0.44,
               "sem apagar o numero -- declara ao lado, nao corrige")
        checar("ATV" in saida, "lista a atividade com conferencia de 1 amostra",
               saida)
        checar("1621" not in saida,
               "e nao confunde `1621 amostras` com `1 amostras`", saida)
        r2 = rodar(raiz, "auditar")
        saida2 = r2.stdout + r2.stderr
        checar("já estavam marcadas" in saida2
               and "marcada(s) como INVÁLIDA" not in saida2,
               "rodar de novo nao remarca o que ja' estava marcado", saida2)

        print("\n`--parar` respeita a marca do `auditar`")
        (raiz / ".agents" / ".memoria-MARCADA.json").write_text(json.dumps({
            "amostras": 400, "picos": {"frente_gb": 3.3}, "base": {},
            "minimos": {}, "pico_frente": {"frente_gb": 3.3},
            "invalida": {"em": "2026-09-14T09:00:00", "por": "medir --auditar",
                         "razao": "amostrador morreu"}}), encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "MARCADA", "--parar")
        saida = r.stdout + r.stderr
        checar(r.returncode == 1, "recusa medida marcada como invalida", saida)
        checar("3.3" not in saida and "3,3" not in saida,
               "sem imprimir o numero que a marca desautoriza", saida)

        print("\n`--parar` grita quando o pico foge da SERIE do projeto")
        # A defesa que faltava: as tres camadas anteriores pegam medida
        # quebrada pela FORMA; esta pega pela GRANDEZA. O episodio de 11 a
        # 14/09/2026 durou tres dias porque 0,44 GB parecia plausivel lido
        # sozinho -- o mesmo repo vinha medindo 4,5 a 5,6 GB. Apontado por
        # `acme-backoffice-23`, que mediu a razao: 11x.
        (raiz / ".agents" / "atividades" / "SERIE.md").write_text("\n".join(
            f"| 2026-09-1{i} 10:00:00 | memoria | ok | frente pico 5.0 GB, "
            f"1000 amostras |" for i in range(1, 5)) + "\n", encoding="utf-8")
        (raiz / ".agents" / "atividades" / "BAIXA.md").write_text("x\n",
                                                                 encoding="utf-8")
        (raiz / ".agents" / ".memoria-BAIXA.json").write_text(json.dumps({
            "amostras": 900, "inicio": "a", "fim": "b", "base": {},
            "picos": {"frente_gb": 0.44}, "minimos": {},
            "pico_frente": {"frente_gb": 0.44}, "buracos": [],
            "travou_s": 0.0, "dormiu_s": 0.0}), encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "BAIXA", "--parar")
        saida = r.stdout + r.stderr
        checar("DISCREPANTE" in saida,
               "acusa pico uma ordem de grandeza abaixo da serie", saida)
        checar("11.4x menor" in saida or "11.4x" in saida,
               "e diz de quanto e' a discrepancia", saida)

        (raiz / ".agents" / "atividades" / "NORMAL.md").write_text("x\n",
                                                                  encoding="utf-8")
        (raiz / ".agents" / ".memoria-NORMAL.json").write_text(json.dumps({
            "amostras": 900, "inicio": "a", "fim": "b", "base": {},
            "picos": {"frente_gb": 4.2}, "minimos": {},
            "pico_frente": {"frente_gb": 4.2}, "buracos": [],
            "travou_s": 0.0, "dormiu_s": 0.0}), encoding="utf-8")
        r = rodar(raiz, "medir", "--id", "NORMAL", "--parar")
        checar("DISCREPANTE" not in (r.stdout + r.stderr),
               "e fica calado quando o pico esta' dentro da serie",
               r.stdout + r.stderr)

        print("\nconferir sem marca")
        r = rodar(raiz, "conferir", "--id", "NAO-EXISTE")
        checar(r.returncode == 1, "recusa conferir o que nunca foi marcado")
        checar("ANTES de disparar" in r.stderr,
               "e explica que a marca se cria antes, não depois")

        print("\nsobra: o que a atividade deixou de pé — 02/10/2026")
        # O caso: dez contêineres e treze processos sobreviveram DOIS DIAS às
        # atividades que os criaram, e o Mac de 16 GB travou com 5,2 dos 6 GB
        # de swap em uso. Nada disso era dano para o `conferir`: ele pergunta
        # se o que havia ANTES caiu, e nada havia caído. O que sobrou de pé ele
        # imprimia como `[subiu ]`, "esperado, se foram suas".
        subprocess.run([sys.executable, str(FLOW), "iniciar", "S1",
                        "--titulo", "Sobra", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        r = rodar(raiz, "marcar", "--id", "S1")
        checar(r.returncode == 0, "marcar, com a máquina limpa", r.stderr)
        corpo = (raiz / ".agents" / "atividades" / "S1.md").read_text(encoding="utf-8")
        checar("| sobra | exigida |" in corpo,
               "e a dívida de limpeza nasce AQUI, antes de haver o que limpar",
               corpo[-400:])

        # A REVERSÃO. Sem este passo, o verde do caso seguinte não prova nada:
        # um `sobra` que respondesse 1 sempre passaria no teste do defeito e
        # reprovaria toda atividade limpa.
        r = rodar(raiz, "sobra", "--id", "S1")
        checar(r.returncode == 0, "e ANTES de subir nada, `sobra` responde 0",
               r.stdout + r.stderr)
        checar("NÃO prova" in r.stdout,
               "declarando o que a conferência limpa não prova", r.stdout)

        porta_s = porta_livre()
        sobrou = subprocess.Popen(
            [sys.executable, "-c",
             f"import socket,time\n"
             f"s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
             f"s.bind(('127.0.0.1',{porta_s})); s.listen(1); time.sleep(120)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                time.sleep(0.1)
                if str(porta_s) in rodar(raiz, "sobra", "--id", "S1").stdout:
                    break
            r = rodar(raiz, "sobra", "--id", "S1")
            checar(r.returncode == 1,
                   "ACUSA: 1 quando a atividade deixou um ouvinte de pé",
                   r.stdout + r.stderr)
            checar(str(porta_s) in r.stdout,
                   "e nomeia a porta que sobrou", r.stdout)
            corpo = (raiz / ".agents" / "atividades" / "S1.md").read_text(encoding="utf-8")
            checar("| sobra | falhou |" in corpo,
                   "e a sobra vai para a tabela de Conferências, não só à tela",
                   corpo[-400:])

            print("\nsobra: a varredura alcança quem nunca consolidou")
            # É esta que teria pego o caso. O `sobra --id` roda ao consolidar,
            # e as três atividades de 02/10/2026 nunca consolidaram: as sessões
            # morreram antes. Conferência que depende da atividade estar viva
            # não cobre o modo de falha mais comum deste fluxo.
            r = rodar(raiz, "varrer")
            checar(r.returncode == 1, "varrer acusa sem precisar de --id",
                   r.stdout + r.stderr)
            checar("S1" in r.stdout and str(porta_s) in r.stdout,
                   "e diz de qual atividade é a sobra", r.stdout)
            checar("não registra conferência" in r.stdout,
                   "e declara que não reabre veredicto de atividade encerrada",
                   r.stdout)

            print("\nsobra --derrubar: por PID exato, e com segunda foto")
            r = rodar(raiz, "sobra", "--id", "S1", "--derrubar")
            checar(r.returncode == 0, "derruba e responde 0",
                   r.stdout + r.stderr)
            checar("segunda foto" in r.stdout,
                   "e PROVA com uma segunda foto, porque SIGTERM é pedido",
                   r.stdout)
            checar(sobrou.poll() is not None or sobrou.wait(timeout=10) is not None,
                   "e o ouvinte morreu de verdade")
            corpo = (raiz / ".agents" / "atividades" / "S1.md").read_text(encoding="utf-8")
            checar(corpo.rstrip().endswith("|")
                   and "| sobra | ok |" in corpo,
                   "e o veredicto vira `ok` depois da limpeza conferida",
                   corpo[-400:])
        finally:
            if sobrou.poll() is None:
                sobrou.kill()

        print("\nsobra: o `concluir` segura enquanto a sobra estiver de pé")
        # Mesma lei da memória: prosa não acontece, linha na tabela acontece.
        # E `sobra` é conferência da PRÓPRIA passada — vale inclusive na
        # trilha `revisao`, onde `falhou` normalmente é o produto. Uma revisão
        # que trava o Mac de quem vem depois não fica quite por ter publicado
        # bons achados.
        subprocess.run([sys.executable, str(FLOW), "iniciar", "S2",
                        "--titulo", "Sobra2", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        rodar(raiz, "marcar", "--id", "S2")
        for _ in range(4):
            subprocess.run([sys.executable, str(FLOW), "avancar", "S2",
                            "--nota", "x"], cwd=raiz, capture_output=True)
        r = subprocess.run([sys.executable, str(FLOW), "concluir", "S2",
                            "--nota", "publicada no PR"],
                           cwd=raiz, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        checar(r.returncode != 0 and "sobra" in (r.stdout + r.stderr),
               "sem rodar `sobra`, o `concluir` RECUSA na trilha revisao",
               (r.stdout + r.stderr)[-400:])

        print("\nsobra: sem marca, é lacuna declarada e não limpeza")
        r = rodar(raiz, "sobra", "--id", "NUNCA-MARCADA")
        checar(r.returncode == 1, "recusa conferir sobra sem o antes",
               r.stdout + r.stderr)
        checar("não é atribuível" in r.stderr or "NÃO COBERTA" in r.stderr,
               "e explica que sem o antes nada é atribuível", r.stderr)

        print("\nsobra: marca velha (anterior à 2.56.0) continua legível")
        # Uma atividade que marcou na versão anterior e vai conferir nesta tem
        # de funcionar. A parte de contêiner dela fica NÃO MEDIDA, que é a
        # verdade: não havia o que medir quando a foto foi tirada.
        velha_marca = raiz / ".agents" / ".processos-ANTIGA.json"
        velha_marca.write_text(
            json.dumps({"8080": {"pid": "1", "comando": "x"}}), encoding="utf-8")
        import process_guard as pg2  # noqa: E402
        lida = pg2.ler_marca(velha_marca)
        checar(lida["portas"] == {"8080": {"pid": "1", "comando": "x"}},
               "lê o esquema antigo como portas", str(lida)[:200])
        checar(lida["docker"] == "nao-medido",
               "e declara contêiner como NÃO MEDIDO, não como zero",
               str(lida)[:200])

        print("\nsobra: contêiner não medido não vira máquina limpa")
        # `None` e `{}` são respostas diferentes: `{}` afirma que não há
        # contêiner nenhum, e quem não tem Docker não sabe disso.
        subprocess.run([sys.executable, str(FLOW), "iniciar", "S3",
                        "--titulo", "Sobra3", "--trilha", "revisao"],
                       cwd=raiz, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        rodar(raiz, "marcar", "--id", "S3")
        m3 = raiz / ".agents" / ".processos-S3.json"
        d3 = json.loads(m3.read_text(encoding="utf-8"))
        d3["docker"] = "nao-medido"
        m3.write_text(json.dumps(d3), encoding="utf-8")
        r = rodar(raiz, "sobra", "--id", "S3")
        checar(r.returncode == 0, "sem porta sobrando, responde 0",
               r.stdout + r.stderr)
        corpo = (raiz / ".agents" / "atividades" / "S3.md").read_text(encoding="utf-8")
        checar("| sobra | nao-coberta |" in corpo,
               "mas registra NAO-COBERTA, e não `ok`, com contêiner não medido",
               corpo[-400:])

        print("\nsobra: --derrubar não existe para as outras ações")
        r = rodar(raiz, "conferir", "--id", "S1", "--derrubar")
        checar(r.returncode == 1 and "só vale para `sobra`" in r.stderr,
               "recusa `--derrubar` fora de `sobra`", r.stderr)

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Fumaca do guarda de processo: tudo verde.")
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
    sys.exit(main())
