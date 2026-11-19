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

    testar_fila()
    testar_memoria()

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Fumaca do guarda de processo: tudo verde.")
    return 0


FILA = AQUI / "fila_pesada.py"


def testar_memoria() -> None:
    """Quem come a memória, agrupado, e o limite do Docker (2.83.0).

    Em 18/11/2026 a recusa da fila mostrava `node`, `claude` e
    `com.apple.Virtualization.VirtualMachine` soltos, sem dizer de quem eram.
    """
    sys.path.insert(0, str(AQUI))
    import memoria as M

    print("\nmemória: agrupar por app, sessão e worktree")
    casa = "/Users/x"
    vm = ("/System/Library/Frameworks/Virtualization.framework/Versions/A/XPCServices/"
          "com.apple.Virtualization.VirtualMachine.xpc/Contents/MacOS/"
          "com.apple.Virtualization.VirtualMachine")
    cc = "/Users/x/Library/Application Support/Claude/claude-code/2.1/abc/claude.app/Contents/MacOS/claude"
    procs = [
        {"pid": 1, "kb": 1800 * 1024, "caminho": vm},
        {"pid": 2, "kb": 300 * 1024, "caminho": "/Applications/Docker.app/Contents/MacOS/com.docker.backend"},
        {"pid": 3, "kb": 700 * 1024, "caminho": "/Applications/Claude.app/Contents/Frameworks/Claude Helper (Renderer).app/Contents/MacOS/Claude Helper (Renderer)"},
        {"pid": 4, "kb": 280 * 1024, "caminho": cc},
        {"pid": 5, "kb": 260 * 1024, "caminho": cc},
        {"pid": 6, "kb": 900 * 1024, "caminho": "node"},
        {"pid": 7, "kb": 800 * 1024, "caminho": "/usr/local/bin/node"},
    ]
    pastas = {4: "/Users/x/dev/ai-flow", 5: "/Users/x/dev/back/.claude/worktrees/1103-z/frontend",
              6: "/Users/x/dev/back/.claude/worktrees/1103-z/backend",
              7: "/Users/x/dev/back/.claude/worktrees/1103-z"}
    grupos = {g: (kb, n) for kb, g, n in M.agrupar(procs, pastas, casa)}
    checar(grupos.get("Docker (VM e app)") == (2100 * 1024, 2),
           "a VM do Docker e o app do Docker viram uma linha", str(grupos))
    checar("Claude" in grupos and "Claude Code em ~/dev/ai-flow" in grupos
           and "Claude Code em ~/dev/back/.claude/worktrees/1103-z" in grupos,
           "o app do Claude e cada sessão do Claude Code, pela pasta", str(grupos))
    checar(grupos.get("node em ~/dev/back/.claude/worktrees/1103-z") == (1700 * 1024, 2),
           "node solto agrupado pelo worktree, cortado no nome dele", str(grupos))
    checar(M.agrupar(procs, pastas, casa)[0][1] == "Docker (VM e app)",
           "do maior para o menor")
    checar(M.grupo_de("/usr/bin/python3", None, casa) == "python3",
           "sem pasta lida, só o nome")

    print("\nmemória: o Docker")
    checar(M.mb_de("856.7MiB / 3.826GiB") == 856.7 and M.mb_de("1.5GiB / 4GiB") == 1536
           and M.mb_de("512KiB / 4GiB") == 0.5 and M.mb_de("--") is None,
           "lê o uso do `docker stats` em MB, em qualquer unidade")
    lista = [
        {"nome": "r-pg-1", "projeto": "acme", "pasta": "/nao/existe/mais", "imagem": "pg", "mb": 240.0},
        {"nome": "r-mq-1", "projeto": "acme", "pasta": "/nao/existe/mais", "imagem": "mq", "mb": 60.0},
        {"nome": "zen", "projeto": "", "pasta": "", "imagem": "jdk", "mb": 900.0},
        {"nome": "sem-stats", "projeto": "a", "pasta": "", "imagem": "x", "mb": None},
    ]
    proj = M.por_projeto(lista)
    checar([g["projeto"] for g in proj] == ["zen (jdk, sem compose)", "acme", "a"]
           and proj[1]["mb"] == 300.0 and proj[1]["quantos"] == 2,
           "contêineres somados por projeto do compose; solto pelo nome e imagem",
           str(proj))
    checar(M.sugerir_limite(1620) == 3072 and M.sugerir_limite(100) == 2048
           and M.sugerir_limite(3000) == 5120,
           "limite sugerido: uso × 1,5 + 512 MB, em degraus de 512, mínimo 2 GB")
    checar("baixar para 3.0 GB" in M.recomendacao(1620, 4096)
           and "Quem muda é a pessoa" in M.recomendacao(1620, 4096),
           "limite folgado: sugere baixar, e diz que quem muda é a pessoa")
    checar("apertada" in M.recomendacao(3000, 4096),
           "limite curto: diz que está apertada")
    checar("não foi lido" in M.recomendacao(1620, None), "sem o arquivo do Docker: diz")
    cfg = Path(tempfile.mkdtemp(prefix="docker-cfg-")) / "settings-store.json"
    cfg.write_text(json.dumps({"MemoryMiB": 4096, "Cpus": 4}), encoding="utf-8")
    checar(M.limite_do_docker(cfg) == 4096 and M.limite_do_docker(cfg.with_name("x")) is None,
           "lê o MemoryMiB do settings-store.json do Docker Desktop")

    print("\nmemória: a linha de comando")
    env = {**os.environ, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    r = subprocess.run([sys.executable, str(FILA), "memoria"], capture_output=True,
                       text=True, env=env, timeout=60)
    checar(r.returncode == 0 and "quem come a memória" in r.stdout
           and "docker: não respondeu" in r.stdout,
           "`fila_pesada.py memoria` sem Docker no PATH: lê a máquina e diz", r.stdout + r.stderr)


def testar_fila() -> None:
    """A fila da máquina, o portão da memória (2.64.0) e a vigia (2.65.0).

    Em 19/10/2026 nove workers do jest levaram o Mac de 16 GB a 14,5 GB de
    swap. A regra de uma suíte por vez já estava escrita, e não aconteceu.
    """
    sys.path.insert(0, str(AQUI))
    import fila_pesada as F

    print("\nfila: o que é comando pesado")
    casos = {
        "npx jest": ["jest"],
        "npm test": ["npm test"],
        "npm --prefix backend test": ["npm test"],
        "npm run test:unit -- --maxWorkers=2": ["npm run test:unit"],
        "pnpm build": ["pnpm build"],
        "cd web && npx vitest run --maxWorkers=2": ["vitest"],
        "FOO=1 npx playwright test --workers=2": ["playwright test"],
        "bash -c 'npx jest -w 2'": ["jest"],
        "node node_modules/.bin/jest": ["jest"],
        "next build": ["next build"],
        "tsc --noEmit": ["tsc"],
        # Não pesados: servidor que não termina, download, texto citado.
        "next dev": [],
        "npx playwright install chromium": [],
        'git commit -m "roda o jest e o npm test"': [],
        "npm install": [],
        "jest --version": [],
        "ls; echo test": [],
    }
    for cmd, esperado in casos.items():
        achado = [a["rotulo"] for a in F.analisar(cmd)]
        checar(achado == esperado, f"`{cmd}` → {esperado or 'não pesado'}",
               str(achado))
    checar(not F.analisar("npx jest")[0]["limitado"]
           and F.analisar("npx jest --maxWorkers=2")[0]["limitado"]
           and F.analisar("npx vitest run --no-file-parallelism")[0]["limitado"]
           and not F.analisar("npx playwright test")[0]["limitado"]
           and F.analisar("npx playwright test -j 2")[0]["limitado"],
           "limite de workers lido por runner (jest, vitest, playwright)")

    print("\nfila: script de nome neutro, lido no package.json (2.81.0)")
    # Em 18/11/2026 o `npm --prefix frontend run gate` do backoffice rodava
    # vitest e playwright, e a fila lia só o nome `gate`.
    proj = Path(tempfile.mkdtemp(prefix="fila-pkg-"))
    (proj / "frontend").mkdir()
    (proj / "frontend" / "package.json").write_text(json.dumps({"scripts": {
        "gate": "npm run check && vitest run --maxWorkers=2",
        "check": "eslint .",
        "ciclo": "npm run ciclo",
        "fundo": "npm run gate",
        "lint": "eslint .",
    }}), encoding="utf-8")
    (proj / "package.json").write_text(json.dumps({"scripts": {
        "ci": "npm --prefix frontend run gate"}}), encoding="utf-8")
    raiz_pkg = str(proj)
    casos_pkg = {
        "npm --prefix frontend run gate": ["npm run gate → vitest"],
        "npm --prefix=frontend run gate": ["npm run gate → vitest"],
        "cd frontend && npm run gate": ["npm run gate → vitest"],
        "pnpm -C frontend gate": ["pnpm gate → vitest"],
        "npm run ci": ["npm run ci → npm run gate → vitest"],
        "npm --prefix frontend run fundo": ["npm run fundo → npm run gate → vitest"],
        # O que segue leve: script leve, script que não existe, ciclo.
        "npm --prefix frontend run lint": [],
        "npm --prefix frontend run nao-existe": [],
        "npm --prefix frontend run ciclo": [],
        "npm --prefix pasta-que-nao-ha run gate": [],
    }
    for cmd, esperado in casos_pkg.items():
        achado = [a["rotulo"] for a in F.analisar(cmd, raiz_pkg)]
        checar(achado == esperado, f"`{cmd}` → {esperado or 'não pesado'}",
               str(achado))
    print("\nfila: raia curta e raia longa (2.82.0)")
    raias = {
        "npm run build": "curta",
        "pnpm build:prod": "curta",
        "tsc --noEmit": "curta",
        "next build": "curta",
        "npx jest --maxWorkers=2": "longa",
        "npm run build && npm test": "longa",
        "npm --prefix frontend run gate": "longa",
        "python3 qa36161/runner.py": "longa",
    }
    for cmd, esperado in raias.items():
        achado = F.raia_de(F.analisar(cmd, raiz_pkg))
        checar(achado == esperado, f"`{cmd}` → raia {esperado}", achado)
    checar(F.analisar("npm --prefix frontend run gate") == [],
           "sem `cwd`, só o texto do comando conta (como até a 2.80.0)")
    checar(all(a["limitado"] for a in F.analisar("npm --prefix frontend run gate", raiz_pkg)),
           "script do package.json entra na fila sem ser policiado nos workers")

    pasta = Path(tempfile.mkdtemp(prefix="fila-"))
    # A memória é a de mentira, relida a cada leitura: o teste não depende de
    # como está a máquina que o roda, e não espera a amostra de 3 s.
    medida = pasta / "medida.json"

    def memoria(**campos) -> None:
        calma = {"swap_usado": 0.5, "swap_total": 5.0, "saida_mb_s": 0.0,
                 "folga_pct": 60}
        medida.write_text(json.dumps({**calma, **campos}), encoding="utf-8")

    memoria()
    base = {**os.environ, "ELCAMARGO_FILA_DIR": str(pasta),
            "ELCAMARGO_FILA_MEDIDA_TESTE": str(medida),
            "ELCAMARGO_VIGIA_S": "0.3"}
    for k in ("ELCAMARGO_FILA_DONO", "ELCAMARGO_SWAP_FORCAR",
              "ELCAMARGO_FILA_PESADA", "ELCAMARGO_SWAP_TETO_GB",
              "ELCAMARGO_FILA_SALTOU", "ELCAMARGO_VIGIA"):
        base.pop(k, None)

    def gancho(comando: str, **env) -> subprocess.CompletedProcess:
        evento = {"tool_name": "Bash", "tool_input": {"command": comando}}
        return subprocess.run([sys.executable, str(FILA), "portao"],
                              input=json.dumps(evento), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              env={**base, **env}, timeout=30)

    def fila(*args, **env) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(FILA), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env={**base, **env}, timeout=60)

    print("\nfila: o gancho do Bash")
    r = gancho("npx jest --maxWorkers=2")
    checar(r.returncode == 2 and "fora da fila" in r.stderr
           and "fila_pesada.py rodar --" in r.stderr,
           "recusa o pesado fora da fila, com 2, e diz como rodar", r.stderr)
    r = gancho(f"python3 {FILA} rodar -- 'npx jest --maxWorkers=2'")
    checar(r.returncode == 0 and not r.stderr, "aceita o mesmo comando dentro da fila",
           r.stderr)
    r = gancho(f"python3 {FILA} rodar -- 'npx jest'")
    checar(r.returncode == 2 and "fora da fila" not in r.stderr
           and "--maxWorkers=2" in r.stderr,
           "dentro da fila, mas sem limite de workers: recusa pelo limite", r.stderr)
    r = gancho("npx playwright test")
    checar(r.returncode == 2 and "--workers=2" in r.stderr,
           "playwright sem `--workers` recebe a flag dele", r.stderr)
    evento_pkg = {"tool_name": "Bash", "cwd": raiz_pkg,
                  "tool_input": {"command": "npm --prefix frontend run gate"}}
    r = subprocess.run([sys.executable, str(FILA), "portao"],
                       input=json.dumps(evento_pkg), capture_output=True,
                       text=True, env=base, timeout=30)
    checar(r.returncode == 2 and "npm run gate → vitest" in r.stderr,
           "o gancho lê o package.json da pasta do evento", r.stderr)
    r = gancho('git commit -m "jest"')
    checar(r.returncode == 0 and not r.stderr, "silêncio no que não é pesado")
    r = gancho("npx jest", ELCAMARGO_FILA_PESADA="desligada")
    checar(r.returncode == 0, "ELCAMARGO_FILA_PESADA=desligada desliga")
    r = subprocess.run([sys.executable, str(FILA), "portao"], input="{torto",
                       capture_output=True, text=True, env=base, timeout=30)
    checar(r.returncode == 0, "evento torto não quebra o gancho", r.stderr)

    print("\nfila: um por vez")
    pid_a = pasta / "a.pid"
    primeiro = subprocess.Popen(
        [sys.executable, str(FILA), "rodar", "--",
         f"echo $$ > {pid_a}; sleep 4"],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if pid_a.exists():
            break
        time.sleep(0.1)
    r = fila("rodar", "--espera", "1", "--", "true")
    checar(r.returncode == F.SAIDA_RECUSADA and "A vez não veio" in r.stderr,
           "o segundo desiste com 75 quando a vez não vem", r.stderr)
    r = fila("estado")
    checar("ocupada" in r.stdout and "sleep 4" in r.stdout and "há " in r.stdout,
           "`estado` diz quem está com a vez, e há quanto tempo", r.stdout)
    checar("sem histórico desse comando" in r.stdout,
           "primeira vez do comando: `estado` diz que não há estimativa", r.stdout)
    checar(r.returncode == 0 and "regra: recusa com folga abaixo de 20%" in r.stdout
           and "não recusa sozinho" in r.stdout,
           "`estado` imprime a regra única, e fila ocupada não é `não pode`", r.stdout)
    memoria(swap_usado=5.8, swap_total=6.0, saida_mb_s=0.0, folga_pct=54)
    r = fila("estado")
    checar(r.returncode == 0 and "deixaria entrar" in r.stdout and "parado" in r.stdout,
           "swap 5,8 de 6 GB parado com 54% livre (o caso do backoffice): pode", r.stdout)
    memoria(saida_mb_s=4.0)
    r = fila("estado")
    checar(r.returncode == 1 and "RECUSARIA" in r.stdout,
           "memória entrando no swap: `estado` sai 1", r.stdout)
    memoria()
    r = fila("rodar", "--", "true", ELCAMARGO_FILA_DONO="1")
    checar(r.returncode == 0, "quem já tem a vez não espera por si mesmo", r.stderr)
    t0 = time.monotonic()
    r = fila("rodar", "--espera", "30", "--", "true")
    checar(r.returncode == 0 and "Na raia longa atrás de" in r.stderr
           and time.monotonic() - t0 >= 1,
           "e com espera maior, entra quando o primeiro sai", r.stderr)
    checar(primeiro.wait(timeout=30) == 0, "o primeiro terminou inteiro")

    print("\nfila: quanto falta (2.81.0)")
    # Em 18/11/2026 um runner de QA segurou a vez 16 min e o build atrás
    # dele esperou 900 s sem saber se valia esperar.
    hist = json.loads((pasta / "fila-historico.json").read_text(encoding="utf-8"))
    chave = f"echo $$ > {pid_a}; sleep 4"
    checar(chave in hist and 3.5 <= hist[chave][-1] <= 15,
           "quem solta a vez grava quanto a segurou", str(hist.get(chave)))
    pid_a.unlink()
    segundo = subprocess.Popen(
        [sys.executable, str(FILA), "rodar", "--", chave],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if pid_a.exists():
            break
        time.sleep(0.1)
    r = fila("estado")
    checar("costuma levar 4 s (1 vez(es))" in r.stdout and "espera estimada: ~" in r.stdout,
           "a segunda vez: `estado` estima a espera pelo histórico", r.stdout)
    r = fila("rodar", "--espera", "1", "--", "true")
    checar(r.returncode == F.SAIDA_RECUSADA and "costuma levar" in r.stderr,
           "quem desiste também vê a estimativa", r.stderr)
    checar(segundo.wait(timeout=30) == 0, "o segundo terminou inteiro")
    antes = os.environ.get("ELCAMARGO_FILA_DIR")
    os.environ["ELCAMARGO_FILA_DIR"] = str(pasta)
    passou = F._estimativa(chave, 3600)
    if antes is None:
        os.environ.pop("ELCAMARGO_FILA_DIR")
    else:
        os.environ["ELCAMARGO_FILA_DIR"] = antes
    checar("e já passou disso" in passou and "espera estimada" not in passou,
           "passou da mediana: diz que não há estimativa, em vez de prometer")

    print("\nfila: as duas raias rodando (2.82.0)")
    # Em 18/11/2026 o build da 1103 esperou 900 s atrás de um runner de QA.
    # O `sleep` abaixo, que a fila não reconhece, vai para a raia longa.
    pid_l = pasta / "l.pid"
    longo = subprocess.Popen(
        [sys.executable, str(FILA), "rodar", "--", f"echo $$ > {pid_l}; sleep 6"],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if pid_l.exists():
            break
        time.sleep(0.1)
    r = fila("rodar", "--raia", "curta", "--espera", "1", "--", "true")
    checar(r.returncode == 0 and "raia curta" in r.stderr,
           "com a longa ocupada, o build entra na raia curta sem esperar", r.stderr)
    bin_falso = pasta / "bin"
    bin_falso.mkdir()
    (bin_falso / "tsc").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_falso / "tsc").chmod(0o755)
    r = fila("rodar", "--espera", "1", "--", "tsc --noEmit",
             PATH=f"{bin_falso}{os.pathsep}{base.get('PATH', '')}")
    checar(r.returncode == 0 and "raia curta" in r.stderr,
           "sem `--raia`, a fila põe o `tsc` na curta sozinha", r.stderr)
    r = fila("estado")
    checar("fila longa (teste, e2e, runner de QA): ocupada" in r.stdout
           and "fila curta (build, tsc): livre" in r.stdout,
           "`estado` mostra as duas raias", r.stdout)
    pid_c = pasta / "c.pid"
    curto = subprocess.Popen(
        [sys.executable, str(FILA), "rodar", "--raia", "curta", "--",
         f"echo $$ > {pid_c}; sleep 3"],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if pid_c.exists():
            break
        time.sleep(0.1)
    r = fila("rodar", "--raia", "curta", "--espera", "1", "--", "true")
    checar(r.returncode == F.SAIDA_RECUSADA and "raia curta" in r.stderr,
           "dois builds juntos não: a raia curta também é um por vez", r.stderr)
    r = gancho(f"python3 {FILA} rodar --raia curta -- 'npx jest --maxWorkers=2'")
    checar(r.returncode == 0, "o gancho lê `rodar --raia curta -- ...` como dentro da fila",
           r.stderr)
    checar(curto.wait(timeout=30) == 0, "o build da raia curta terminou inteiro")
    checar(longo.wait(timeout=30) == 0, "o runner da raia longa terminou inteiro")
    r = fila("rodar", "--", "exit 3")
    checar(r.returncode == 3, "devolve o código do comando", str(r.returncode))

    print("\nfila: o portão da memória")
    rodou = pasta / "rodou"

    def tentar(**env) -> subprocess.CompletedProcess:
        rodou.unlink(missing_ok=True)
        return fila("rodar", "--", f"touch {rodou}", **env)

    memoria(swap_usado=3.7, saida_mb_s=40.0, folga_pct=43)
    r = tentar()
    checar(r.returncode == F.SAIDA_RECUSADA and "swap agora" in r.stderr
           and "40.0 MB/s" in r.stderr and not rodou.exists(),
           "swap MEXENDO recusa com 75 e não roda", r.stderr)
    r = tentar(ELCAMARGO_SWAP_FORCAR="1")
    checar(r.returncode == 0 and rodou.exists() and "FORCAR" in r.stderr,
           "ELCAMARGO_SWAP_FORCAR=1 segue, e diz que forçou", r.stderr)
    memoria(folga_pct=12)
    r = tentar()
    checar(r.returncode == F.SAIDA_RECUSADA and "sem folga: 12%" in r.stderr,
           "memória sem folga recusa, mesmo com o swap baixo", r.stderr)
    # O caso de 19/10/2026 depois de fechar tudo: 3,7 GB de swap que o macOS
    # não devolve, e nada entrando nele.
    memoria(swap_usado=14.5, saida_mb_s=0.0, folga_pct=43)
    r = tentar()
    checar(r.returncode == 0 and rodou.exists() and "parado" in r.stderr,
           "swap acima do teto mas PARADO segue, e avisa que é sobra", r.stderr)
    memoria(swap_usado=14.5, saida_mb_s=None, folga_pct=43)
    r = tentar()
    checar(r.returncode == F.SAIDA_RECUSADA and "não consegui medir" in r.stderr,
           "swap alto sem a atividade medida recusa: não dá para separar",
           r.stderr)
    memoria(swap_usado=None, swap_total=None, saida_mb_s=None, folga_pct=None)
    r = tentar()
    checar(r.returncode == 0 and "NÃO medida" in r.stderr,
           "nada medido: segue, e diz que o portão não cobriu", r.stderr)
    checar(F.avaliar({"swap_usado": 3.7, "swap_total": 5.0, "saida_mb_s": 0.4,
                      "folga_pct": 43}) == (None, ""),
           "a máquina de hoje (3,7 GB, 0,4 MB/s, 43%) entra sem aviso")

    print("\nfila: a vigia durante o comando")
    memoria()
    neto = pasta / "neto.pid"
    neto.unlink(missing_ok=True)
    t0 = time.monotonic()
    filho = subprocess.Popen(
        [sys.executable, str(FILA), "rodar", "--",
         f"sleep 60 & echo $! > {neto}; wait"],
        env=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if neto.exists() and neto.read_text().strip():
            break
        time.sleep(0.1)
    memoria(folga_pct=5)
    _, erro = filho.communicate(timeout=60)
    pid_neto = int(neto.read_text().strip())
    time.sleep(0.3)
    try:
        os.kill(pid_neto, 0)
        vivo = True
    except ProcessLookupError:
        vivo = False
    except PermissionError:
        vivo = True
    checar(filho.returncode == F.SAIDA_RECUSADA
           and "Interrompido pela vigia" in erro and "folga caiu a 5%" in erro
           and time.monotonic() - t0 < 30,
           "folga afundando no meio: a vigia derruba e devolve 75", erro)
    checar(not vivo, "e derruba o grupo inteiro, com o neto que o shell subiu",
           str(pid_neto))
    memoria(swap_usado=0.5, saida_mb_s=30.0)
    r = fila("rodar", "--", "sleep 1.5", ELCAMARGO_SWAP_FORCAR="1")
    checar(r.returncode == 0 and "Interrompido" not in r.stderr,
           "swap mexendo mas sem crescer: a vigia deixa terminar", r.stderr)

    print("\nfila: a versão mais nova responde por quem não recarregou")
    cache = Path(tempfile.mkdtemp(prefix="fila-cache-")) / "elcamargo-ai-flow"
    for versao in ("2.9.0", "2.10.0", "2.11.0"):
        destino = cache / versao / "tools" / "process-guard"
        destino.mkdir(parents=True)
        (destino / "fila_pesada.py").write_text(FILA.read_text(encoding="utf-8"),
                                               encoding="utf-8")
    (cache / "2.10.0" / "tools" / "process-guard" / "fila_pesada.py").write_text(
        "import sys\nprint('a-2.10.0', *sys.argv[1:])\n", encoding="utf-8")
    (cache / "2.11.0" / ".orphaned_at").write_text("1", encoding="utf-8")
    velha = cache / "2.9.0" / "tools" / "process-guard" / "fila_pesada.py"
    r = subprocess.run([sys.executable, str(velha), "estado"], capture_output=True,
                       text=True, env=base, timeout=30)
    checar(r.stdout.strip() == "a-2.10.0 estado",
           "a 2.9.0 salta para a 2.10.0, e não para a 2.11.0 órfã", r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(velha), "estado"], capture_output=True,
                       text=True, env={**base, "ELCAMARGO_FILA_SALTOU": "1"},
                       timeout=30)
    checar("fila longa" in r.stdout, "já saltou uma vez: não salta de novo", r.stdout)
    checar(F.mais_nova() is None, "fora do cache (no clone) não há salto")

    print("\nfila: o `gates` do step 8 passa por ela")
    raiz = Path(tempfile.mkdtemp(prefix="fila-gates-")).resolve()
    ag = raiz / ".agents"
    (ag / "elcamargo-flow").mkdir(parents=True)
    (raiz / "bin").mkdir()
    jest = raiz / "bin" / "jest"
    jest.write_text("#!/bin/sh\n[ -n \"$DORME\" ] && sleep \"$DORME\"\n"
                    "echo jest-rodou \"$@\"\n", encoding="utf-8")
    jest.chmod(0o755)
    (ag / "config.toml").write_text(
        '[projeto]\nnome = "t"\n[gates]\nlint = "true"\n'
        'test = "./bin/jest --maxWorkers={max_workers}"\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=raiz, capture_output=True)
    env_g = {**base, "ELCAMARGO_AGENTS_DIR": str(ag)}

    def g(*args, **env):
        return subprocess.run([sys.executable, str(FLOW), *args], cwd=raiz,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env={**env_g, **env}, timeout=120)

    def linha_do_test() -> str:
        corpo = (ag / "atividades" / "FG1.md").read_text(encoding="utf-8")
        return next((x for x in reversed(corpo.splitlines())
                     if "| gate:test |" in x), "")

    g("iniciar", "FG1", "--titulo", "t", "--trilha", "curta")
    memoria(swap_usado=3.7, saida_mb_s=40.0)
    r = g("gates", "FG1")
    corpo = (ag / "atividades" / "FG1.md").read_text(encoding="utf-8")
    checar(r.returncode == 1 and "| gate:lint | ok |" in corpo
           and "| gate:test | falhou | não rodou: Recusado: o sistema" in corpo,
           "swap mexendo: o portão pesado fica `falhou`/não rodou, o lint roda",
           r.stdout[-600:] + corpo[-400:])
    memoria()
    r = g("gates", "FG1", "--so", "test")
    log = (ag / "atividades" / "FG1-gates" / "test.log").read_text()
    checar(r.returncode == 0 and "com a vez da máquina" in r.stdout
           and "jest-rodou --maxWorkers=2" in log,
           "com a vez e a memória folgada, roda o pesado", r.stdout[-600:])
    memoria(folga_pct=5)
    t0 = time.monotonic()
    r = g("gates", "FG1", "--so", "test", ELCAMARGO_SWAP_FORCAR="1", DORME="30")
    checar(r.returncode == 1 and "falhou | interrompido pela vigia: folga caiu"
           in linha_do_test() and time.monotonic() - t0 < 25,
           "afundando no meio do portão: `falhou`/interrompido, e não espera "
           "o comando", linha_do_test() + r.stdout[-400:])


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
