#!/usr/bin/env python3
"""Os processos que já estavam de pé continuam de pé?

    process_guard.py marcar   --id 1061
    process_guard.py conferir --id 1061

O `tree_guard.py` protege o disco. Esta ferramenta é o irmão que faltava:
protege a **máquina**.

Em 10/09/2026 a frente de execução do step 9 terminou o próprio trabalho e
limpou os processos que havia subido com:

    pkill -f "nest start"

O padrão casou com o backend de **outra atividade** do fluxo, rodando na mesma
máquina, na árvore do usuário. Quatro serviços no chão — portas 3001, 3002,
3003 e 3004 — e a frente não podia religar, porque o prompt a proibia de
executar na árvore do usuário.

**E não foi falha do prompt.** Ele dizia, com todas as letras, que havia outra
atividade em curso e que ela escolhesse portas livres. Ela escolheu (3210, 3211,
3213, 3214), isolou banco e vhost, e ainda assim derrubou os alheios: **limpeza
por padrão de linha de comando não distingue de quem é o processo.** Isolar
porta não protege de `pkill -f`.

Por isso a regra de matar por PID é de código, e não de prosa — ver
`references/specialties/system-usage.md`. E por isso existe esta conferência:
mesmo com a regra escrita, alguém um dia vai chamar `pkill`, e o dano hoje é
silencioso. Ela não impede: **diz que houve.**

## O que ela NÃO prova

**Que os processos de antes seguem sadios.** Ela compara quem escuta em qual
porta. Um serviço que continuou de pé e ficou inutilizável — banco derrubado,
fila apagada — passa limpo por aqui.

**Que o que sumiu foi a frente que matou.** Um serviço pode ter caído sozinho,
ou a pessoa pode tê-lo encerrado de propósito. A ferramenta aponta a diferença;
a causa é leitura de quem consolida.

**Que o que subiu é da frente.** Porta nova entre as duas marcas pode ser da
frente de execução — o caso normal — ou de algo que a pessoa abriu no meio.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))

from flow_state import FlowStateError, resolve_agents_dir  # noqa: E402


def _lsof() -> list[tuple[str, str, str]]:
    """(porta, pid, comando) de tudo que escuta em TCP.

    `lsof` porque é o que existe nos dois sistemas em que o pacote roda. No
    Linux `ss -ltnp` responderia, mas exigiria um segundo parser para um ganho
    de nada: quando `lsof` falta, a resposta certa é declarar a lacuna, não
    adivinhar com outro formato.
    """
    if not shutil.which("lsof"):
        raise FlowStateError(
            "`lsof` não está nesta máquina, e é como o guarda enxerga quem "
            "escuta.\n"
            "  Sem ele não há conferência de processo — e não conferir é\n"
            "  diferente de conferir e não achar nada. Declare a dimensão\n"
            "  como `nao-coberta` em vez de seguir como se tivesse conferido."
        )
    r = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
                       capture_output=True, timeout=60)
    # lsof devolve 1 quando NADA escuta, o que é resposta legítima e não erro.
    saida = r.stdout.decode("utf-8", "replace")
    if r.returncode not in (0, 1):
        raise FlowStateError(
            f"`lsof` falhou: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    fora: list[tuple[str, str, str]] = []
    for linha in saida.splitlines()[1:]:
        campos = linha.split()
        if len(campos) < 9:
            continue
        comando, pid, nome = campos[0], campos[1], campos[-2]
        # "127.0.0.1:3001" e "*:3001" — a porta é o que vem depois do ÚLTIMO
        # ":", porque IPv6 traz dois-pontos no endereço e um split simples
        # devolveria um pedaço do host como porta.
        porta = nome.rpartition(":")[2]
        if porta.isdigit():
            fora.append((porta, pid, comando))
    return fora


def estado() -> dict[str, dict[str, str]]:
    """Por porta, quem a ocupa.

    A chave é a PORTA e não o PID de propósito: um serviço que reinicia troca
    de PID e continua sendo o mesmo serviço para quem o usa. O dano que esta
    ferramenta existe para pegar é "a porta 3001 parou de responder", não "o
    PID 84213 morreu".
    """
    por_porta: dict[str, dict[str, str]] = {}
    for porta, pid, comando in _lsof():
        # Um serviço com vários workers ocupa a mesma porta em mais de um PID.
        # O primeiro basta: a pergunta é se a porta continua servida.
        por_porta.setdefault(porta, {"pid": pid, "comando": comando})
    return por_porta


# --------------------------------------------------------------- contêiner ---
#
# Por que `lsof` não bastava, e o guarda de porta nunca ia pegar isto.
#
# Em 02/10/2026 o Mac de referência travou com 5,2 GB dos 6 GB de swap em uso.
# De pé: **dez contêineres de três stacks** — `rt29986v2r`, `v7-1052` e
# `rt5min` —, há 22 a 25 horas, de atividades cujos steps tinham terminado
# ANTEONTEM. Mais treze processos `node` órfãos, entre eles dois `next dev` que
# ninguém acessava havia um dia.
#
# Nenhum deles aparecia como dano para o `conferir`. Ele pergunta *o que estava
# de pé antes caiu?* — e a resposta era não, nada caiu. O que sobrou de pé ele
# imprime como `[subiu ]` e chama de **esperado, se foram suas**. Era a leitura
# certa para o dano que ele existe para pegar, e cega para este.
#
# E contêiner não é porta. No macOS quem escuta a porta publicada é o
# `com.docker.backend`, um processo só para todos os contêineres: o `lsof` vê
# "docker" e não vê de quem. Contêiner sem porta publicada — a maioria dos
# bancos descartáveis deste fluxo — é **invisível** para ele. A memória, não:
# a VM do Docker reserva 4 GB fixos nesta máquina, com um contêiner ou com dez.


def _conteineres() -> dict[str, dict[str, str]] | None:
    """Os contêineres de pé, por id. `None` quando não dá para saber.

    `None` e `{}` são respostas diferentes, e a diferença é a doutrina do
    pacote inteira: `{}` afirma que não há contêiner nenhum, e quem não tem
    Docker instalado não sabe disso — não sabe. Quem recebe `None` declara a
    dimensão como não coberta; quem recebe `{}` pode afirmar.
    """
    if not shutil.which("docker"):
        return None
    try:
        r = subprocess.run(
            ["docker", "ps", "--no-trunc",
             "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}"],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        # Daemon parado é o caso comum, e não é erro: ninguém está subindo
        # contêiner com o Docker desligado. Mas também não é zero contêiner
        # medido — é zero contêiner MEDÍVEL, que é a mesma lacuna de cima.
        return None
    fora: dict[str, dict[str, str]] = {}
    for linha in r.stdout.decode("utf-8", "replace").splitlines():
        campos = linha.split("\t")
        if len(campos) < 3 or not campos[0].strip():
            continue
        fora[campos[0].strip()] = {"nome": campos[1].strip(),
                                   "imagem": campos[2].strip()}
    return fora


def foto() -> dict:
    """O que esta máquina tem de pé agora: portas e contêineres.

    É o que a marca guarda. A chave do contêiner é o id e não o nome: um
    `docker compose up` refeito devolve o mesmo nome a um contêiner novo, e
    tratá-los como o mesmo esconderia exatamente o caso de recriar sem
    derrubar.
    """
    conteineres = _conteineres()
    return {"portas": estado(),
            "conteineres": conteineres if conteineres is not None else {},
            "docker": "nao-medido" if conteineres is None else "ok"}


def ler_marca(alvo: Path) -> dict:
    """Lê a marca, inclusive as gravadas antes da 2.56.0.

    Até a 2.56.0 o arquivo era o dicionário de portas, sem envelope. Uma
    atividade que marcou na versão anterior e vai conferir nesta tem de
    continuar funcionando — e a parte de contêiner dela fica declarada como
    não medida, que é a verdade: não havia o que medir quando a foto foi tirada.
    """
    d = json.loads(alvo.read_text(encoding="utf-8"))
    if "portas" in d and isinstance(d.get("portas"), dict):
        return d
    return {"portas": d, "conteineres": {}, "docker": "nao-medido"}


def _orfao(pid: str) -> bool:
    """O processo foi adotado pelo init — quem o criou morreu.

    É o sinal mais forte de sobra que existe nesta máquina, e foi o que os
    treze `node` de 02/10/2026 tinham em comum: `ppid 1`, vivos há um dia,
    nenhum deles com dono. Não é prova de abandono (um daemon legítimo também
    tem ppid 1), mas combinado com "apareceu depois da marca" é o caso.
    """
    try:
        r = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    saida = r.stdout.decode("utf-8", "replace").strip()
    return saida == "1"


def marca(agents: Path, ident: str) -> Path:
    return agents / f".processos-{ident}.json"


def cmd_marcar(agents: Path, ident: str) -> int:
    alvo = marca(agents, ident)
    tirada = foto()
    atual, conteineres = tirada["portas"], tirada["conteineres"]
    tirada["em"] = datetime.now().isoformat(timespec="seconds")
    alvo.write_text(json.dumps(tirada, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Processos marcados para a atividade {ident}: "
          f"{len(atual)} porta(s) em escuta.")
    for porta in sorted(atual, key=int):
        print(f"  {porta:>6}  {atual[porta]['comando']}  pid {atual[porta]['pid']}")
    if tirada["docker"] == "ok":
        print(f"  e {len(conteineres)} contêiner(es) de pé:")
        for cid in sorted(conteineres, key=lambda c: conteineres[c]["nome"]):
            print(f"  {'':>6}  {conteineres[cid]['nome']}  "
                  f"({conteineres[cid]['imagem']})")
    else:
        print("  contêineres: NÃO MEDIDOS (sem `docker` nesta máquina, ou com o")
        print("  daemon parado). Não é o mesmo que zero — ver `_conteineres`.")
    print(f"  {alvo}")
    print()
    print("  ESTAS PORTAS NÃO SÃO SUAS. Suba as suas em portas livres, e ao")
    print("  terminar mate SÓ os PIDs que você criou — nunca por padrão de")
    print("  linha de comando. Ao consolidar, rode `conferir`.")
    # O `--iniciar` do amostrador só escreve a dívida se alguém o rodar — e
    # "alguém precisa rodar" era exatamente a obrigação em prosa que a
    # mecanização veio substituir. `marcar` roda ANTES do disparo das frentes,
    # sempre, então é aqui que a dívida nasce mesmo quando ninguém se lembra do
    # amostrador. Quem decidir não medir declara `nao-coberta`, que passa.
    registrar(ident, "exigida",
              "as frentes foram disparadas; o pico de memória ainda não foi "
              "medido (`medir --iniciar` / `--parar`)")
    # A MESMA razão, para a outra dívida. A limpeza do que a atividade sobe era
    # obrigação escrita em prosa — na skill, na `work-tree.md`, e no chat do
    # Ederson em 30/09/2026 — e em 02/10/2026 dez contêineres e treze processos
    # sobreviveram dois dias às atividades que os criaram. Prosa não acontece.
    # Aqui ela vira linha na tabela de Conferências, no instante em que a
    # máquina ainda está limpa e ninguém tem nada a esconder.
    registrar(ident, "exigida",
              "a máquina foi fotografada; o que esta atividade deixar de pé "
              "ainda não foi conferido (`sobra --id <id>`)",
              ferramenta="sobra")
    print()
    print("  E a memória: `medir --id <id> --iniciar` antes de disparar. Sem")
    print("  ela, `memoria` fica como conferência EXIGIDA em aberto e o")
    print("  `concluir` segura — declare `nao-coberta` se a decisão for não medir.")
    print()
    print("  Ao consolidar, `sobra --id <id>` — o que VOCÊ subiu e não derrubou.")
    print("  Também já está EXIGIDA, e também segura o `concluir`.")
    return 0


def cmd_conferir(agents: Path, ident: str) -> int:
    alvo = marca(agents, ident)
    if not alvo.exists():
        raise FlowStateError(
            f"Não há marca de processo para a atividade {ident}.\n"
            f"  A marca se cria ANTES de disparar as frentes:\n"
            f"    process_guard.py marcar --id {ident}\n"
            "  Conferir depois do fato não distingue o que a frente derrubou\n"
            "  do que nunca esteve de pé."
        )
    antes = ler_marca(alvo)["portas"]
    agora = estado()

    caiu = sorted(set(antes) - set(agora), key=int)
    subiu = sorted(set(agora) - set(antes), key=int)
    trocou = sorted((p for p in set(antes) & set(agora)
                     if antes[p]["pid"] != agora[p]["pid"]), key=int)

    if not caiu:
        print(f"Atividade {ident}: nenhuma porta de antes ficou sem serviço.")
        if subiu:
            print(f"  Subiram {len(subiu)}: {', '.join(subiu)} — esperado, se")
            print("  foram suas. Diga no relatório o que você subiu.")
            print("  Se ainda estiverem de pé ao consolidar, são SOBRA: quem")
            print("  responde por elas é `sobra --id " + ident + "`, não esta")
            print("  conferência, que só pergunta se derrubaram os alheios.")
        if trocou:
            print(f"  Trocaram de PID: {', '.join(trocou)} — reinício, não queda.")
        print()
        print("  Isso NÃO prova que os serviços de antes seguem sadios: um que")
        print("  ficou de pé e inutilizável passa limpo por esta conferência.")
        return 0

    print(f"Atividade {ident}: {len(caiu)} PORTA(S) DE ANTES FICARAM SEM SERVIÇO.")
    print()
    for p in caiu:
        print(f"  [CAIU  ] {p:>6}  era {antes[p]['comando']}  pid {antes[p]['pid']}")
    for p in subiu:
        print(f"  [subiu ] {p:>6}  {agora[p]['comando']}")
    for p in trocou:
        print(f"  [trocou] {p:>6}  pid {antes[p]['pid']} -> {agora[p]['pid']}")
    print()
    print("  Isto provavelmente não é seu. Um `pkill -f` com padrão genérico")
    print("  casa com o processo do vizinho, e isolar porta não protege disso.")
    print()
    print("  Antes de consolidar: religue o que derrubou e DECLARE no relatório")
    print("  o que subiu e o que derrubou, com o antes e o depois. Cuidado ao")
    print("  religar — script de `dev` tudo-ou-nada derruba os irmãos que")
    print("  sobreviveram; chame os scripts individuais.")
    return 1


# ---------------------------------------------------------------- memória ---
#
# Por que isto não sai do transcrito, que era a primeira ideia. O `metrics.py`
# lê os transcritos de sessão depois do fato, e transcrito não guarda memória:
# ele tem token, turno e horário. Pico de RSS só existe ENQUANTO o processo
# existe — medir depois é impossível, e estimar seria inventar.
#
# A pergunta que o `DESIGN-maquina-fraca.md` abriu — *quais frentes cabem em
# 8 GB?* — só se responde amostrando durante a execução. Daí este par.

INTERVALO_S = 2.0


def registrar(ident: str, veredicto: str, detalhe: str = "",
              ferramenta: str = "memoria") -> None:
    """Grava o veredicto na atividade, para o `concluir` achar.

    Sem isto, ligar o amostrador é obrigação escrita em prosa: quem esquecer
    não deixa rastro, e o portão 10 recebe uma revisão sem saber que a memória
    nunca foi medida. Com isto, a ausência vira linha na tabela de
    Conferências — que é onde o resto do pacote põe o que não pode sumir.
    """
    if not ident:
        return
    fs = Path(__file__).resolve().parent.parent / "flow-state" / "flow_state.py"
    if not fs.is_file():
        print(f"  [aviso] não achei {fs}; nada foi registrado")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(fs), "conferencia", ident,
             "--ferramenta", ferramenta, "--veredicto", veredicto,
             "--detalhe", detalhe[:200]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [aviso] não consegui registrar: {exc}")
        return
    if r.returncode != 0:
        print(f"  [aviso] registro recusado: {(r.stderr or r.stdout).strip()[:160]}")


def arquivo_de_medida(agents: Path, ident: str) -> Path:
    return agents / f".memoria-{ident}.json"


def arquivo_de_pid(agents: Path, ident: str) -> Path:
    return agents / f".memoria-{ident}.pid"


def _le_saida(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


def _ps_linhas() -> list[tuple[int, int, int, str]]:
    """(pid, ppid, rss_kb, comando). `rss` vem em kilobytes nos dois sistemas."""
    linhas = []
    for linha in _le_saida(["ps", "-axo", "pid=,ppid=,rss=,comm="]).splitlines():
        campos = linha.split(None, 3)
        if len(campos) < 4 or not all(c.isdigit() for c in campos[:3]):
            continue
        linhas.append((int(campos[0]), int(campos[1]), int(campos[2]),
                       campos[3].strip()))
    return linhas


def _quantidade(texto: str, chave: str) -> float | None:
    """Lê `chave = 1234.56M` do `vm.swapusage`, em GB. A unidade varia."""
    m = re.search(chave + r"\s*=\s*([\d.]+)([KMG])", texto)
    if not m:
        return None
    fator = {"K": 1 / 1048576, "M": 1 / 1024, "G": 1.0}[m.group(2)]
    return round(float(m.group(1)) * fator, 2)


def _pressao_do_sistema() -> dict:
    """O que prevê o travamento — e NÃO é a soma de RSS.

    Medido em 11/09/2026, na máquina de referência, com frentes de leitura
    rodando: a soma de RSS CAIU de 11,17 para 10,08 GB, a memória livre SUBIU
    de 0,11 para 2,56 GB, e ao mesmo tempo o swap em uso subiu de 2,73 para
    4,14 GB e o macOS aumentou o arquivo de swap de 4,00 para 5,12 GB. Todo
    indicador de RSS apontou alívio no instante de maior pressão, porque o que
    aconteceu foi despejo: o sistema tirou páginas residentes de quem não
    estava trabalhando — VM do Docker, Chrome, Teams — para caber as frentes.

    Por isso o sinal desta ferramenta é swap e compressor. `inativa` não conta
    como folga: reclamá-la é exatamente a paginação que trava.
    """
    if sys.platform == "darwin":
        saida = _le_saida(["vm_stat"])
        if not saida:
            return {}
        m = re.search(r"page size of (\d+) bytes", saida)
        pagina = int(m.group(1)) if m else 4096

        def paginas(chave: str) -> float:
            for linha in saida.splitlines():
                if linha.startswith(chave):
                    return int(linha.split(":", 1)[1].strip().rstrip(".")) * pagina / 1e9
            return 0.0

        comp = paginas("Pages occupied by compressor")
        d = {"em_uso_gb": round(paginas("Pages active")
                                + paginas("Pages wired down") + comp, 2),
             "compressor_gb": round(comp, 2),
             "livre_gb": round(paginas("Pages free")
                               + paginas("Pages speculative"), 2)}
        sw = _le_saida(["sysctl", "-n", "vm.swapusage"])
        d["swap_usado_gb"] = _quantidade(sw, "used")
        d["swap_total_gb"] = _quantidade(sw, "total")
        return d

    try:
        txt = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return {}

    def gb(chave: str) -> float:
        m = re.search(rf"^{chave}:\s+(\d+) kB", txt, re.M)
        return round(int(m.group(1)) / 1048576, 2) if m else 0.0

    total, disponivel = gb("MemTotal"), gb("MemAvailable")
    swap_total, swap_livre = gb("SwapTotal"), gb("SwapFree")
    # O Linux não tem compressor de memória no sentido do macOS; declarar nulo
    # é diferente de declarar zero.
    return {"em_uso_gb": round(total - disponivel, 2), "compressor_gb": None,
            "livre_gb": disponivel, "swap_usado_gb": round(swap_total - swap_livre, 2),
            "swap_total_gb": swap_total}


def _arvore_de(raiz: int, linhas: list[tuple[int, int, int, str]]) -> dict:
    """Soma e maior processo DESCENDO da raiz — a frente, não a máquina.

    Na primeira medida real (1091, 11/09/2026) o "maior processo" reportado
    foi a VM do Docker: o maior da máquina, que não tinha nada a ver com o
    fluxo. Atribuir exige descer a árvore de quem conduz a atividade.
    """
    filhos: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    nome: dict[int, str] = {}
    for pid, ppid, kb, comando in linhas:
        filhos.setdefault(ppid, []).append(pid)
        rss[pid] = kb
        nome[pid] = comando
    vistos: set[int] = set()
    fila = [raiz]
    while fila:
        atual = fila.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        fila.extend(filhos.get(atual, ()))
    soma = sum(rss.get(pid, 0) for pid in vistos)
    maior = max(((rss.get(pid, 0), nome.get(pid, "?")) for pid in vistos),
                default=(0, ""))
    return {"frente_gb": round(soma / 1048576, 2),
            "maior_gb": round(maior[0] / 1048576, 2),
            "maior_processo": maior[1].rsplit("/", 1)[-1][:40],
            "processos": len(vistos)}


def raiz_da_frente() -> tuple[int, str, bool]:
    """Sobe a árvore até a sessão que conduz a atividade.

    Descoberta no PAI, nunca no amostrador: o amostrador nasce com
    `start_new_session=True` e perde a cadeia — o `ppid` dele vira 1.
    """
    linhas = _ps_linhas()
    pai = {pid: ppid for pid, ppid, _, _ in linhas}
    nome = {pid: comando for pid, _, _, comando in linhas}
    atual, vistos = os.getpid(), set()
    while atual > 1 and atual not in vistos:
        vistos.add(atual)
        if "claude-code" in nome.get(atual, ""):
            return atual, nome[atual].rsplit("/", 1)[-1][:40], True
        atual = pai.get(atual, 0)
    # Lacuna se declara: sem sessão na cadeia, a raiz é o processo atual e a
    # medida da frente cobre só o que ele mesmo disparar.
    meu = os.getpid()
    return meu, nome.get(meu, "?").rsplit("/", 1)[-1][:40], False


def _pressao_agora(raiz: int | None) -> dict | None:
    if not shutil.which("ps"):
        return None
    linhas = _ps_linhas()
    if not linhas:
        return None
    maior = max(linhas, key=lambda l: l[2])
    leitura = {"soma_rss_gb": round(sum(l[2] for l in linhas) / 1048576, 2),
               "maior_maquina_gb": round(maior[2] / 1048576, 2),
               "maior_maquina": maior[3].rsplit("/", 1)[-1][:40]}
    leitura.update(_arvore_de(raiz, linhas) if raiz else
                   {"frente_gb": None, "maior_gb": None,
                    "maior_processo": None, "processos": None})
    leitura.update(_pressao_do_sistema())
    return leitura


# Um buraco entre duas amostras é a máquina não entregando o passo pedido — mas
# ele tem DUAS causas, e elas não se parecem em nada:
#
#   travamento  a máquina está acordada e não consegue nos agendar (paginação)
#   sono        a máquina está suspensa, e ninguém está sofrendo nada
#
# Em 11/09/2026 o medidor externo desta mesma investigação reportou "2.032 s de
# paralisia" que eram tampa fechada. Achado porque o número era absurdo, não
# porque o instrumento soubesse.
#
# A separação é aritmética, sem limiar nem chute: o relógio MONOTÔNICO não anda
# durante o sono, e o de parede anda. Provado na própria corrida — o amostrador
# tinha teto de 150 min de `monotonic` e seguia vivo com 176 min de parede.
#
#   sono   = parede - monotonico
#   travou = monotonico - intervalo pedido
#
VERSAO_AUDITORIA = (
    (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    if (Path(__file__).resolve().parents[2] / "VERSION").is_file() else "?")
LIMIAR_BURACO_S = INTERVALO_S * 1.5
MAX_BURACOS = 300

# O que cresce é pico; o que encolhe é mínimo. `livre_gb` é o único que doi
# quando cai, e por isso é o único do segundo grupo.
PICOS = ("soma_rss_gb", "frente_gb", "em_uso_gb", "swap_usado_gb",
         "swap_total_gb", "compressor_gb")
MINIMOS = ("livre_gb",)


def cmd_amostrador(agents: Path, ident: str, teto_min: float,
                   raiz: int | None = None) -> int:
    """O laço. Roda em processo próprio, disparado pelo `medir --iniciar`."""
    alvo = arquivo_de_medida(agents, ident)
    base = _pressao_agora(raiz)
    estado_ = {"raiz_pid": raiz, "amostras": 0,
               "inicio": datetime.now().isoformat(timespec="seconds"),
               "base": base, "picos": {}, "minimos": {}, "pico_frente": None,
               "buracos": [], "travou_s": 0.0, "dormiu_s": 0.0}
    fim = time.monotonic() + teto_min * 60
    anterior = (time.monotonic(), time.time())
    try:
        return _laco_do_amostrador(alvo, estado_, raiz, fim, anterior)
    except BaseException as e:
        # O amostrador roda em processo proprio, com stdout e stderr em
        # DEVNULL. Sem isto a morte dele e' MUDA: o arquivo fica com a
        # leitura da largada e o `--parar` a imprime como se fosse pico.
        # Foi assim que um TypeError passou por quinze medidas sem ninguem
        # ver -- achado por `acme-backoffice-23` em 14/09/2026.
        estado_["erro"] = f"{type(e).__name__}: {e}"
        estado_["traco"] = traceback.format_exc()[-2000:]
        estado_["fim"] = datetime.now().isoformat(timespec="seconds")
        try:
            alvo.write_text(json.dumps(estado_, indent=2), encoding="utf-8")
        except OSError:
            pass
        raise


def _laco_do_amostrador(alvo: Path, estado_: dict, raiz: int | None,
                        fim: float, anterior: tuple[float, float]) -> int:
    while time.monotonic() < fim:
        agora_ = _pressao_agora(raiz)
        if agora_:
            mono, parede = time.monotonic(), time.time()
            d_mono, d_parede = mono - anterior[0], parede - anterior[1]
            anterior = (mono, parede)
            if d_parede >= LIMIAR_BURACO_S:
                dormiu = max(0.0, d_parede - d_mono)
                travou = max(0.0, d_mono - INTERVALO_S)
                estado_["dormiu_s"] = round(estado_["dormiu_s"] + dormiu, 1)
                estado_["travou_s"] = round(estado_["travou_s"] + travou, 1)
                if len(estado_["buracos"]) < MAX_BURACOS:
                    estado_["buracos"].append(
                        {"em": datetime.now().isoformat(timespec="seconds"),
                         "parede_s": round(d_parede, 1),
                         "travou_s": round(travou, 1),
                         "dormiu_s": round(dormiu, 1)})
            estado_["amostras"] += 1
            for chave in PICOS:
                v = agora_.get(chave)
                if v is not None and v > estado_["picos"].get(chave, -1.0):
                    estado_["picos"][chave] = v
            for chave in MINIMOS:
                v = agora_.get(chave)
                if v is not None and v < estado_["minimos"].get(chave, 1e9):
                    estado_["minimos"][chave] = v
            # NAO chamar isto de `anterior`. Esse nome ja' e' a tupla
            # (monotonico, parede) da deteccao de buraco, la' em cima: ligar
            # os dois no mesmo laco fazia a volta seguinte indexar um float
            # ou um None, e o amostrador morria na SEGUNDA amostra, calado.
            # Entrou na 2.30.1 -- o conserto que ensinou a separar sono de
            # travamento matou toda medida posterior a ele.
            pico_anterior = (estado_["pico_frente"] or {}).get("frente_gb")
            atual = agora_.get("frente_gb")
            if atual is not None and (pico_anterior is None
                                      or atual > pico_anterior):
                estado_["pico_frente"] = agora_
            estado_["fim"] = datetime.now().isoformat(timespec="seconds")
            try:
                alvo.write_text(json.dumps(estado_, indent=2), encoding="utf-8")
            except OSError:
                return 0
        time.sleep(INTERVALO_S)
    return 0


def cmd_medir(agents: Path, ident: str, iniciar: bool, teto_min: float) -> int:
    pid_arq = arquivo_de_pid(agents, ident)
    if iniciar:
        if pid_arq.exists():
            raise FlowStateError(
                f"já há um amostrador para {ident} ({pid_arq.read_text().strip()}).\n"
                f"  Pare o anterior: process_guard.py medir --id {ident} --parar"
            )
        arquivo_de_medida(agents, ident).unlink(missing_ok=True)
        # A raiz se descobre AQUI, no pai. O amostrador nasce com
        # `start_new_session=True` e já não tem cadeia para subir.
        raiz, raiz_nome, raiz_certa = raiz_da_frente()
        filho = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "amostrador",
             "--id", ident, "--teto-min", str(teto_min), "--raiz", str(raiz)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        pid_arq.write_text(str(filho.pid), encoding="utf-8")
        # A dívida se escreve ANTES de existir o que medir, e não depois.
        # Registrar só no `--parar` cobria um caso só: "liguei, não mediu, e eu
        # vim fechar". Deixava de fora justamente o cenário que originou a
        # medida — a máquina trava e leva a sessão junto, o `--parar` nunca
        # roda, e a atividade chega ao portão 10 sem uma palavra sobre memória,
        # agora com a APARÊNCIA de que o assunto foi tratado porque a
        # ferramenta existe. Achado por `acme-backoffice-0f` em
        # 11/09/2026, provado com `kill -9` no próprio amostrador.
        #
        # `exigida` segura o `concluir` em toda trilha, inclusive na `revisao`:
        # amostrador morto é literalmente "ninguém rodou", que é lacuna em
        # qualquer regime.
        registrar(ident, "exigida",
                  f"amostrador de memória ligado (pid {filho.pid}); "
                  "o pico entra quando `medir --parar` rodar")
        print(f"Amostrador de memória ligado para {ident} (pid {filho.pid}).")
        print(f"  Amostra a cada {INTERVALO_S:.0f}s, teto de {teto_min:.0f} min.")
        print(f"  Frente medida: descendentes de {raiz} ({raiz_nome}).")
        if not raiz_certa:
            print("  [aviso] não achei a sessão do fluxo na cadeia de processos;")
            print("          a medida da frente cobre só o que este processo "
                  "disparar.")
        print(f"  Dispare as frentes. Ao consolidar: medir --id {ident} --parar")
        return 0

    if pid_arq.exists():
        try:
            # Só o amostrador, por PID — a regra desta ferramenta vale para ela
            # mesma. `pkill -f process_guard` mataria o de outra atividade.
            os.kill(int(pid_arq.read_text().strip()), signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        pid_arq.unlink(missing_ok=True)

    alvo = arquivo_de_medida(agents, ident)
    if not alvo.exists():
        # A lacuna se REGISTRA, e não só se anuncia. Um erro impresso some
        # quando a janela rola; a linha na tabela de Conferências chega ao
        # portão 10. É a mesma razão pela qual `nao-coberta` existe.
        registrar(ident, "nao-coberta",
                  "amostrador de memória não foi ligado, ou morreu antes da "
                  "primeira amostra")
        raise FlowStateError(
            f"não há medida de memória para {ident}.\n"
            "  Ou o amostrador nunca foi ligado, ou ele morreu antes da\n"
            "  primeira amostra. Isso é dimensão NÃO COBERTA — e ficou\n"
            "  REGISTRADA como tal na atividade, para o portão 10 achar."
        )
    d = json.loads(alvo.read_text(encoding="utf-8"))
    if d.get("invalida"):
        # A marca do `auditar` e' convencao do pacote, e quem lê a medida
        # tem de respeitá-la. Sem isto, marcar o arquivo protegeria só quem
        # abrisse o JSON com os olhos. Apontado por
        # `acme-backoffice-23` em 14/09/2026.
        inv = d["invalida"]
        registrar(ident, "nao-coberta",
                  f"medida marcada como inválida por `{inv.get('por', '?')}`: "
                  f"{inv.get('razao', '?')}")
        raise FlowStateError(
            f"a medida de memória de {ident} está marcada como INVÁLIDA.\n"
            f"  {inv.get('razao', '?')}\n"
            f"  Marcada em {inv.get('em', '?')} por {inv.get('por', '?')}.\n"
            "  Registrado como NÃO COBERTA. Para medir de verdade, rode\n"
            f"  `medir --id {ident} --iniciar` de novo."
        )
    if d.get("erro"):
        # O amostrador gravou a propria morte. Vermelho declarado vale mais
        # que verde por omissao: sem isto, o que sobrou do laco seria lido
        # como medida boa.
        registrar(ident, "falhou",
                  f"o amostrador morreu depois de {d.get('amostras', 0)} "
                  f"amostra(s): {d['erro']}")
        raise FlowStateError(
            f"o amostrador de memória de {ident} MORREU durante a medida.\n"
            f"  {d['erro']}\n"
            f"  Amostras antes de morrer: {d.get('amostras', 0)}.\n"
            "  Registrado como `falhou` na atividade. O traço completo está\n"
            f"  em {alvo.name}, campo `traco`."
        )
    if "picos" not in d:  # medida de antes da 2.30.0
        print(f"Medida de {ident} em esquema antigo, anterior à 2.30.0: só a")
        print("  soma de RSS da MÁQUINA, sem linha de base, sem pressão e sem")
        print("  saber quais processos eram da frente.")
        print(f"  soma de RSS    {d.get('soma_rss_gb', 0):.2f} GB")
        registrar(ident, "ok", f"medida em esquema antigo: pico "
                               f"{d.get('soma_rss_gb', 0):.2f} GB de soma de RSS")
        return 0

    if d.get("amostras", 0) < 2:
        # UMA amostra nao e' pico: e' a leitura da largada. O arquivo com
        # `amostras: 1` e `inicio == fim` foi a assinatura visivel de quinze
        # medidas mortas, e durante tres dias foi lido como "memoria baixa".
        # O numero pior que o atual e' pior que numero ausente.
        registrar(ident, "nao-coberta",
                  f"o amostrador gravou {d.get('amostras', 0)} amostra(s): "
                  "e' a leitura da largada, nao um pico")
        raise FlowStateError(
            f"a medida de memória de {ident} tem {d.get('amostras', 0)} "
            "amostra(s).\n"
            "  Uma amostra é a leitura do instante em que o amostrador subiu,\n"
            "  e não o pico da atividade. Publicá-la seria pior que não ter\n"
            "  número nenhum. Registrado como NÃO COBERTA."
        )

    base, picos = d.get("base") or {}, d.get("picos", {})
    minimos, frente = d.get("minimos", {}), d.get("pico_frente") or {}

    def delta(chave: str) -> float | None:
        a, b = picos.get(chave), base.get(chave)
        return None if a is None or b is None else round(a - b, 2)

    def linha(rotulo: str, chave: str, fonte: dict) -> None:
        v = fonte.get(chave)
        print(f"  {rotulo:<22}" + ("não medido" if v is None else f"{v:.2f} GB"))

    print(f"Memória durante a atividade {ident}:")
    print(f"  {d['amostras']} amostras, de {d.get('inicio','?')} a {d.get('fim','?')}")
    print()
    print("  A FRENTE (descendentes de "
          f"{d.get('raiz_pid','?')}, {frente.get('processos','?')} processos no pico)")
    linha("pico da frente", "frente_gb", picos)
    linha("maior processo dela", "maior_gb", frente)
    print(f"  {'':<22}({frente.get('maior_processo') or 'não medido'})")
    print()
    print("  A PRESSÃO DA MÁQUINA — é ela que trava, não a soma de RSS")
    for rotulo, chave in (("swap em uso", "swap_usado_gb"),
                          ("arquivo de swap", "swap_total_gb"),
                          ("compressor", "compressor_gb"),
                          ("em uso", "em_uso_gb")):
        b, a, dl = base.get(chave), picos.get(chave), delta(chave)
        if a is None:
            print(f"  {rotulo:<22}não medido")
            continue
        print(f"  {rotulo:<22}{b:.2f} -> {a:.2f} GB"
              + (f"   ({dl:+.2f})" if dl is not None else ""))
    livre = minimos.get("livre_gb")
    print(f"  {'livre, no mínimo':<22}"
          + ("não medido" if livre is None else f"{livre:.2f} GB"))
    print()
    travou, dormiu = d.get("travou_s"), d.get("dormiu_s")
    if travou is not None:
        pior = max((b for b in d.get("buracos", [])),
                   key=lambda b: b.get("travou_s", 0), default=None)
        print("  A PARALISIA — a máquina acordada e sem conseguir nos agendar")
        print(f"  {'travada':<22}{travou:.0f} s em {d['amostras']} amostras")
        if pior and pior.get("travou_s"):
            print(f"  {'pior episódio':<22}{pior['travou_s']:.0f} s  (em {pior['em']})")
        if dormiu:
            print(f"  {'(dormindo, à parte)':<22}{dormiu:.0f} s — tampa fechada não é")
            print(f"  {'':<22}travamento, e somar as duas mente")
        print()
    cresceu = delta("swap_total_gb")
    if cresceu:
        print(f"  O sistema AUMENTOU o arquivo de swap em {cresceu:.2f} GB. Ele só")
        print("  faz isso sob pressão: é o sinal mais direto de que não coube.")
    print("  A soma de RSS continua gravada para comparar com as medidas")
    print("  antigas, mas não é limiar: ela aponta ALÍVIO no instante de maior")
    print("  pressão, porque despejo faz RSS cair. Ver `_pressao_do_sistema`.")

    partes = [f"frente pico {picos.get('frente_gb')} GB",
              f"maior {frente.get('maior_gb')} GB "
              f"({frente.get('maior_processo') or '?'})",
              f"swap {base.get('swap_usado_gb')}->{picos.get('swap_usado_gb')} GB",
              f"arquivo de swap {delta('swap_total_gb'):+} GB" if delta("swap_total_gb")
              is not None else "arquivo de swap não medido",
              f"livre min {minimos.get('livre_gb')} GB",
              f"travada {d.get('travou_s', '?')}s"
              + (f" (dormiu {d['dormiu_s']:.0f}s, a' parte)"
                 if d.get("dormiu_s") else ""),
              f"{d['amostras']} amostras"]
    aviso = conferir_contra_a_serie(agents, picos.get("frente_gb"))
    if aviso:
        print()
        print("  !! " + aviso)
        print("  Pico muito fora da série deste projeto. Ou a atividade foi")
        print("  mesmo leve, ou a medida não mediu o que devia. Confira antes")
        print("  de tratar este número como pico -- foi exatamente assim que")
        print("  15 medidas passaram por boas entre 11 e 14/09/2026.")
        partes.append(aviso)
    registrar(ident, "ok", ", ".join(partes))
    return 0


RE_CONFERENCIA = re.compile(
    r"^\| (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \| memoria \| ok \|(.*)\|$")
RE_PICO = re.compile(r"frente pico ([\d.]+) GB")
RE_AMOSTRAS = re.compile(r", (\d+) amostras")
MINIMO_DE_SERIE = 3
FATOR_DISCREPANCIA = 4.0


def serie_de_picos(agents: Path) -> list[float]:
    """Os picos que este projeto já mediu, das medidas com série de verdade.

    A fonte é a tabela de Conferências, e não os `.memoria-*.json`: o arquivo é
    sobrescrito a cada `--iniciar` e só guarda a última medida de cada
    atividade. Quem quiser a série tem de ler onde ela ficou.

    Medida de UMA amostra fica de fora: ela é a leitura da largada, e deixá-la
    entrar contaminaria a régua com exatamente o que a régua existe para pegar.
    """
    picos: list[float] = []
    pasta = agents / "atividades"
    if not pasta.is_dir():
        return picos
    for md in sorted(pasta.glob("*.md")):
        try:
            linhas = md.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for linha in linhas:
            m = RE_CONFERENCIA.match(linha.strip())
            if not m:
                continue
            corpo = m.group(2)
            p, n = RE_PICO.search(corpo), RE_AMOSTRAS.search(corpo)
            if p and n and int(n.group(1)) >= 2:
                picos.append(float(p.group(1)))
    return picos


def conferir_contra_a_serie(agents: Path, pico: float | None) -> str:
    """Compara o pico novo com o que este projeto já mediu antes.

    **Esta é a defesa que faltava**, e ela é de outra natureza que as três da
    2.35.0/2.36.0. Aquelas pegam medida quebrada pela FORMA -- uma amostra,
    exceção gravada, marca de auditoria. Esta pega pela GRANDEZA.

    O episódio de 11 a 14/09/2026 passou três dias porque 0,44 GB parecia
    plausível lido sozinho. Não era: o mesmo repositório vinha medindo 4,5 a
    5,6 GB, e num caso as duas leituras estão no MESMO arquivo, a oito linhas
    de distância. **Valor sem série não é interrogável** -- e a pessoa que
    lê uma medida de cada vez nunca tem a série na cabeça.

    Avisa, e não trava: pico legitimamente baixo existe (atividade documental
    não sobe frente nenhuma). Mas o aviso vai junto no registro da
    conferência, e não só na tela -- tela rola, tabela chega ao portão 10.
    """
    if pico is None:
        return ""
    serie = serie_de_picos(agents)
    if len(serie) < MINIMO_DE_SERIE:
        return ""
    mediana = sorted(serie)[len(serie) // 2]
    if mediana <= 0:
        return ""
    if pico * FATOR_DISCREPANCIA < mediana:
        return (f"DISCREPANTE: {pico:.2f} GB contra mediana {mediana:.2f} GB "
                f"de {len(serie)} medidas deste projeto ({mediana / pico:.1f}x "
                "menor)")
    if pico > mediana * FATOR_DISCREPANCIA:
        return (f"DISCREPANTE: {pico:.2f} GB contra mediana {mediana:.2f} GB "
                f"de {len(serie)} medidas deste projeto ({pico / mediana:.1f}x "
                "maior)")
    return ""


def cmd_auditar(agents: Path) -> int:
    """Marca no PRÓPRIO arquivo as medidas que não são medida.

    A recusa que o `--parar` passou a fazer na 2.35.0 protege o futuro e não
    toca no passado: os arquivos gravados pelo amostrador morto continuam em
    disco, com um número que parece pico. Quem os ler daqui a um mês não vai
    lembrar desta conversa.

    Esta varredura não apaga e não corrige — ela **declara dentro do dado**.
    O número fica onde está, com um carimbo ao lado dizendo por que não vale.

    O que ela deliberadamente NÃO faz: mexer na conferência da atividade.
    Reabrir atividade encerrada é decisão de pessoa, e apareceria como se a
    ferramenta tivesse remedido o que ninguém remediu. Ela lista as afetadas e
    para aí.
    """
    achados: list[tuple[str, str, float | None]] = []
    ja_marcadas = 0
    for arq in sorted(agents.glob(".memoria-*.json")):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ident = arq.name[len(".memoria-"):-len(".json")]
        pico = (d.get("picos") or {}).get("frente_gb")
        if d.get("erro"):
            razao = f"o amostrador morreu: {d['erro']}"
        elif d.get("amostras", 0) < 2:
            razao = (f"{d.get('amostras', 0)} amostra(s): é a leitura do "
                     "instante da largada, não um pico")
        else:
            continue
        if d.get("invalida"):
            ja_marcadas += 1
            continue
        d["invalida"] = {
            "em": datetime.now().isoformat(timespec="seconds"),
            "por": f"medir --auditar ({VERSAO_AUDITORIA})",
            "razao": razao,
            "leia": "o número em `picos` e `pico_frente` NÃO é um pico medido",
        }
        try:
            arq.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except OSError:
            continue
        achados.append((ident, razao, pico))

    # O ARQUIVO SUBESTIMA, e por construção: ele é sobrescrito a cada
    # `medir --iniciar`, então só a ÚLTIMA medida de cada atividade sobrevive
    # em disco. As anteriores ficam gravadas na tabela de Conferências da
    # atividade — e é lá que o estrago aparece inteiro. Apontado por
    # `acme-backoffice-42` em 14/09/2026: 10 arquivos no disco
    # contra 18 conferências, no mesmo repositório.
    #
    # A assinatura é o texto exato `, 1 amostras |`. Procurar por
    # `1 amostras` solto casa dentro de `1621 amostras`, e eu mesmo errei
    # assim antes de conferir.
    conferencias: list[tuple[str, str]] = []
    pasta = agents / "atividades"
    if pasta.is_dir():
        for md in sorted(pasta.glob("*.md")):
            try:
                for linha in md.read_text(encoding="utf-8").splitlines():
                    if ", 1 amostras |" in linha and "| memoria |" in linha:
                        conferencias.append((md.stem, linha.strip()))
            except OSError:
                continue

    if not achados and not ja_marcadas and not conferencias:
        print("Nenhuma medida inválida em " + str(agents) + ".")
        return 0
    if achados:
        print(f"{len(achados)} medida(s) marcada(s) como INVÁLIDA no próprio "
              "arquivo:")
        for ident, razao, pico in achados:
            alvo = "?" if pico is None else f"{pico:.2f} GB"
            print(f"  {alvo:>8}  {ident}")
            print(f"  {'':>8}  {razao}")
    if ja_marcadas:
        print(f"{ja_marcadas} já estavam marcadas.")
    if conferencias:
        atividades = sorted({i for i, _ in conferencias})
        print()
        print(f"{len(conferencias)} conferência(s) de memória gravada(s) com UMA")
        print(f"amostra, em {len(atividades)} atividade(s) — estas NÃO foram tocadas:")
        for ident in atividades:
            quantas = sum(1 for i, _ in conferencias if i == ident)
            print(f"  {quantas}x  {ident}")
        print()
        print("  Elas dizem `ok` sobre um pico que não foi medido, e dizem também")
        print("  `travada 0.0s` e swap sem variação — com uma amostra só, essas")
        print("  duas saem limpas POR CONSTRUÇÃO. São duas afirmações falsas por")
        print("  linha, não uma.")
    print()
    print("O número continua gravado, agora com o carimbo ao lado. NADA foi")
    print("apagado, e NENHUMA conferência de atividade foi alterada: reabrir")
    print("atividade encerrada é decisão de pessoa, e a ferramenta fazê-lo")
    print("apareceria como remedida sem ninguém ter remedido.")
    return 0


# ------------------------------------------------------------------ sobra ---
#
# A outra metade da pergunta. O `conferir` pergunta *o que havia antes caiu?*
# e protege o vizinho. Esta pergunta é *o que eu subi continua de pé?* e
# protege a máquina — que é a que trava.
#
# As duas usam a MESMA marca e o mesmo diff, em direções opostas. Por isso
# `sobra` não tem foto própria: separar as fotos criaria duas verdades sobre o
# mesmo instante, e a primeira vez que alguém rodasse só uma delas a outra
# estaria mentindo.
#
# ## O que esta conferência NÃO prova
#
# **Que a sobra é da atividade.** O critério é tempo, não dono: apareceu depois
# da marca e continua de pé. Um contêiner que a pessoa subiu para outra coisa
# no meio do step entra na lista igual. É por isso que ela LISTA e pede
# declaração, em vez de derrubar sozinha.
#
# **Que o que ela não lista está limpo.** Contêiner parado mas não removido
# segue ocupando disco e não aparece aqui — `docker ps` só vê o que está de pé.
# Processo que a atividade subiu ANTES da marca também não: para a marca ele é
# paisagem. E sem `docker` na máquina, a metade de contêiner inteira é lacuna
# declarada, não zero.


def _sobra_de(agents: Path, ident: str) -> dict:
    """O diff de sobra de uma atividade, sem imprimir nada.

    Separado do comando porque a varredura chama isto para cada marca, e
    porque o teste consegue olhar o resultado sem parsear texto de tela.
    """
    alvo = marca(agents, ident)
    antes = ler_marca(alvo)
    agora = foto()

    portas = []
    for porta in sorted(set(agora["portas"]) - set(antes["portas"]), key=int):
        dono = agora["portas"][porta]
        portas.append({"porta": porta, "pid": dono["pid"],
                       "comando": dono["comando"], "orfao": _orfao(dono["pid"])})

    conteineres = []
    for cid in sorted(set(agora["conteineres"]) - set(antes["conteineres"]),
                      key=lambda c: agora["conteineres"][c]["nome"]):
        conteineres.append(dict(agora["conteineres"][cid], id=cid))

    # Docker não medido na marca OU agora é lacuna dos dois lados: um diff
    # contra `{}` acusaria como sobra todo contêiner que já existia antes.
    docker = ("ok" if antes["docker"] == "ok" and agora["docker"] == "ok"
              else "nao-medido")
    if docker != "ok":
        conteineres = []

    return {"id": ident, "marcada_em": antes.get("em", "?"),
            "portas": portas, "conteineres": conteineres, "docker": docker}


def _imprime_sobra(d: dict) -> None:
    for c in d["conteineres"]:
        print(f"  [CONTÊINER] {c['nome']}  ({c['imagem']})  id {c['id'][:12]}")
    for p in d["portas"]:
        marca_ = "ÓRFÃO    " if p["orfao"] else "PROCESSO "
        print(f"  [{marca_}] {p['porta']:>6}  {p['comando']}  pid {p['pid']}"
              + ("   (ppid 1: quem o criou morreu)" if p["orfao"] else ""))


def _derruba(d: dict) -> int:
    """Derruba EXATAMENTE o que está na lista, por id e por PID.

    Nunca por padrão de linha de comando. É a mesma lei que o cabeçalho deste
    arquivo conta: em 10/09/2026 um `pkill -f "nest start"` derrubou quatro
    serviços de outra atividade, e isolar porta não protegeu de nada. Lista
    fechada, feita de um diff que a pessoa acabou de ler na tela.
    """
    caiu = 0
    for c in d["conteineres"]:
        try:
            r = subprocess.run(["docker", "stop", c["id"]],
                               capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"  [erro ] {c['nome']}: {exc}")
            continue
        if r.returncode == 0:
            # `stop`, e não `rm`: volume e dados ficam, e um `docker start`
            # devolve tudo. Apagar é decisão de pessoa, e esta ferramenta
            # nasceu de uma máquina travando, não de disco cheio.
            print(f"  [parado] {c['nome']}")
            caiu += 1
        else:
            print(f"  [erro  ] {c['nome']}: "
                  f"{r.stderr.decode('utf-8', 'replace').strip()[:120]}")
    for p in d["portas"]:
        try:
            os.kill(int(p["pid"]), signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError) as exc:
            print(f"  [erro  ] pid {p['pid']}: {type(exc).__name__}")
            continue
        print(f"  [morto ] {p['comando']} pid {p['pid']} (porta {p['porta']})")
        caiu += 1
    return caiu


def cmd_sobra(agents: Path, ident: str, derrubar: bool) -> int:
    alvo = marca(agents, ident)
    if not alvo.exists():
        # A mesma recusa do `conferir`, pela mesma razão: sem a marca, tudo que
        # está de pé parece sobra, e nada do que está de pé é atribuível.
        registrar(ident, "nao-coberta",
                  "não havia marca de processo; sem o antes, o que está de pé "
                  "não é atribuível a esta atividade",
                  ferramenta="sobra")
        raise FlowStateError(
            f"Não há marca de processo para a atividade {ident}.\n"
            f"  A marca se cria ANTES de disparar as frentes:\n"
            f"    process_guard.py marcar --id {ident}\n"
            "  Registrado como NÃO COBERTA: sem o antes, não há como separar\n"
            "  o que esta atividade subiu do que já estava na máquina."
        )
    d = _sobra_de(agents, ident)
    nada = not d["portas"] and not d["conteineres"]

    if nada:
        print(f"Atividade {ident}: nada de pé que não estivesse antes da marca.")
        if d["docker"] != "ok":
            print("  Mas os CONTÊINERES não foram medidos — sem `docker` na")
            print("  máquina, ou com o daemon parado em uma das duas fotos.")
            print("  Isso é metade da conferência em branco, e vai registrada")
            print("  como NÃO COBERTA, não como limpa.")
            registrar(ident, "nao-coberta",
                      "nenhuma porta sobrou, mas os contêineres não foram "
                      "medidos (docker ausente ou parado)", ferramenta="sobra")
            return 0
        print("  Portas e contêineres conferidos contra a marca de "
              f"{d['marcada_em']}.")
        print()
        print("  Isto NÃO prova que a máquina está limpa: contêiner PARADO e")
        print("  não removido não aparece no `docker ps`, e o que a atividade")
        print("  subiu ANTES da marca é paisagem para este diff.")
        registrar(ident, "ok",
                  f"nada sobrou de pé; marca de {d['marcada_em']}",
                  ferramenta="sobra")
        return 0

    quantos = len(d["portas"]) + len(d["conteineres"])
    print(f"Atividade {ident}: {quantos} COISA(S) DE PÉ QUE NÃO ESTAVAM NA MARCA.")
    print()
    _imprime_sobra(d)
    print()

    if not derrubar:
        print("  Cada uma é uma de duas coisas: sobra sua, e então derrube; ou")
        print("  de outra pessoa, e então NÃO toque e declare no relatório.")
        print("  O critério aqui é TEMPO, não dono — apareceu depois da marca.")
        print()
        print(f"  Derrube as suas:  process_guard.py sobra --id {ident} --derrubar")
        print("  (`docker stop`, sem apagar volume; e `SIGTERM` por PID exato)")
        print()
        print("  Em 02/10/2026 dez contêineres e treze processos sobreviveram")
        print("  DOIS DIAS às atividades que os criaram, e o Mac de 16 GB")
        print("  travou com 5,2 dos 6 GB de swap em uso. As worktrees tinham")
        print("  sido removidas; os contêineres, não.")
        detalhe = (f"{quantos} de pé ao conferir: "
                   + ", ".join([c["nome"] for c in d["conteineres"]]
                               + [f"porta {p['porta']} ({p['comando']})"
                                  for p in d["portas"]]))
        registrar(ident, "falhou", detalhe, ferramenta="sobra")
        return 1

    print("  Derrubando SÓ o que está nesta lista, por id e por PID:")
    caiu = _derruba(d)
    print()
    restou = _sobra_de(agents, ident)
    sobrou = len(restou["portas"]) + len(restou["conteineres"])
    if sobrou:
        # Reconferir depois de derrubar não é zelo: `SIGTERM` é pedido, e
        # processo que o ignora continua de pé enquanto a ferramenta imprime
        # "morto". Afirmar não é provar — quem prova é a segunda foto.
        print(f"  {sobrou} ainda de pé depois da derrubada:")
        _imprime_sobra(restou)
        print()
        print("  SIGTERM é pedido, não ordem. Estes ou ignoraram, ou não são")
        print("  seus para matar. Resolva à mão e declare.")
        registrar(ident, "falhou",
                  f"derrubei {caiu}, e {sobrou} seguiram de pé depois do "
                  "SIGTERM", ferramenta="sobra")
        return 1
    print(f"  {caiu} derrubada(s), e a segunda foto confirma que nenhuma "
          "ficou de pé.")
    registrar(ident, "ok",
              f"{caiu} sobra(s) derrubada(s) e conferida(s) na segunda foto",
              ferramenta="sobra")
    return 0


def cmd_varrer(agents: Path, quieto: bool = False) -> int:
    """Todas as marcas deste projeto, inclusive as de atividade encerrada.

    **É esta a varredura que teria pego o caso.** O `sobra --id` roda ao
    consolidar, e as três atividades de 02/10/2026 nunca consolidaram: as
    sessões morreram antes. Conferência que depende da atividade estar viva
    não cobre o modo de falha mais comum deste fluxo, que é a janela ser
    fechada no meio.

    Não registra conferência e não derruba: ela varre atividades ENCERRADAS, e
    reabrir conferência de atividade encerrada é decisão de pessoa — a mesma
    regra que o `auditar` segue logo abaixo.
    """
    marcas = sorted(agents.glob(".processos-*.json"))
    if not marcas:
        if not quieto:
            print(f"Nenhuma marca de processo em {agents}.")
        return 0
    total = 0
    for arq in marcas:
        ident = arq.name[len(".processos-"):-len(".json")]
        try:
            d = _sobra_de(agents, ident)
        except (OSError, json.JSONDecodeError):
            print(f"  [ilegível] {arq.name}")
            continue
        quantos = len(d["portas"]) + len(d["conteineres"])
        if not quantos:
            continue
        total += quantos
        if total == quantos and quieto:
            print("[elcamargo] Sobrou de pé na máquina, de atividade "
                  "anterior:")
        print(f"{ident}  (marcada em {d['marcada_em']}) — {quantos} de pé:")
        _imprime_sobra(d)
        print()
    if not total:
        if not quieto:
            print(f"{len(marcas)} marca(s) varrida(s): nada de pé que não "
                  "estivesse em nenhuma delas.")
        return 0
    print(f"{total} coisa(s) de pé somando {len(marcas)} marca(s).")
    print()
    print("  Uma atividade pode estar viva e no meio do trabalho — confira")
    print("  antes de derrubar, com `sobra --id <id>`, que é quem derruba.")
    print("  Esta varredura não registra conferência: ela alcança atividade")
    print("  JÁ ENCERRADA, e reabrir o veredicto dela é decisão de pessoa.")
    # No gancho, achar sobra NÃO é erro da sessão que está abrindo: é recado
    # sobre a sessão anterior, que já morreu. Responder 1 ali faria o Claude
    # Code pintar de vermelho a abertura de toda janela nesta máquina, e a
    # resposta humana a vermelho constante é desligar o gancho.
    return 0 if quieto else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="process_guard.py",
        description="Guarda os processos da máquina enquanto as frentes rodam.")
    p.add_argument("acao",
                   choices=("marcar", "conferir", "sobra", "varrer", "medir",
                            "amostrador", "auditar"))
    p.add_argument("--id", default=None,
                   help="id da atividade (todas as ações menos `auditar` e "
                        "`varrer`)")
    p.add_argument("--quieto", action="store_true",
                   help="varrer: cala quando não há sobra e sempre responde 0 "
                        "(é como o gancho de abertura de sessão a chama)")
    p.add_argument("--derrubar", action="store_true",
                   help="sobra: derruba o que a lista mostrou, por id e por "
                        "PID exatos")
    p.add_argument("--iniciar", action="store_true",
                   help="medir: liga o amostrador de memória")
    p.add_argument("--parar", action="store_true",
                   help="medir: desliga e imprime o pico")
    p.add_argument("--teto-min", type=float, default=240.0,
                   help="medir: teto de duração do amostrador, em minutos")
    # `str` de propósito, e não `int`: com `type=int`, um `auditar --raiz .`
    # morria em `invalid int value: '.'`, que não diz nada a quem digitou
    # esperando uma pasta. Quem valida é a ação, que sabe o que a flag
    # significa para ela. Apontado por `acme-app-0c`.
    p.add_argument("--raiz", default=None,
                   help="amostrador: pid da sessão cuja árvore é a frente")
    args = p.parse_args(argv)
    try:
        agents = resolve_agents_dir()
        raiz = None
        if args.raiz is not None:
            if args.acao != "amostrador":
                raise FlowStateError(
                    f"`--raiz` só vale para `amostrador`, e `{args.acao}` não a "
                    "usa.\n"
                    "  Ela é o PID da sessão cuja árvore de processos é a "
                    "frente,\n"
                    "  e não uma pasta. A raiz do projeto sai do Git, ou de "
                    "ELCAMARGO_AGENTS_DIR."
                )
            try:
                raiz = int(args.raiz)
            except ValueError:
                raise FlowStateError(
                    f"`--raiz` é o PID da sessão, um número inteiro — "
                    f"recebi `{args.raiz}`."
                ) from None
        if args.acao == "auditar":
            return cmd_auditar(agents)
        if args.acao == "varrer":
            return cmd_varrer(agents, args.quieto)
        if args.derrubar and args.acao != "sobra":
            raise FlowStateError(
                f"`--derrubar` só vale para `sobra`, e `{args.acao}` não a usa.\n"
                "  Derrubar é a única ação deste guarda que MEXE na máquina, e\n"
                "  ela só existe depois de uma lista que a pessoa leu na tela."
            )
        if not args.id:
            raise FlowStateError(f"`{args.acao}` exige --id.")
        if args.acao == "marcar":
            return cmd_marcar(agents, args.id)
        if args.acao == "conferir":
            return cmd_conferir(agents, args.id)
        if args.acao == "sobra":
            return cmd_sobra(agents, args.id, args.derrubar)
        if args.acao == "amostrador":
            return cmd_amostrador(agents, args.id, args.teto_min, raiz)
        if args.iniciar == args.parar:
            raise FlowStateError(
                "`medir` exige --iniciar OU --parar, e não os dois nem nenhum. "
                "Ligar e parar na mesma chamada mediria zero."
            )
        return cmd_medir(agents, args.id, args.iniciar, args.teto_min)
    except FlowStateError as exc:
        if args.quieto:
            # O gancho roda em TODA abertura de sessão, inclusive fora de um
            # projeto do fluxo, onde não há `.agents` nenhum. Reclamar ali é
            # ruído em cima de quem não pediu nada — e ruído constante é como
            # se desliga um gancho.
            return 0
        print(f"erro: {exc}", file=sys.stderr)
        return 1


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
