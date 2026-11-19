#!/usr/bin/env python3
"""Um comando node pesado por raia na máquina, e só com a memória folgada.

    fila_pesada.py rodar -- '<comando>'    espera a vez, confere o swap, roda
    fila_pesada.py rodar --raia curta -- '<comando>'   força a raia (curta: build, tsc; longa: o resto)
    fila_pesada.py estado                  quem está com a vez, há quanto tempo, quanto falta, e se pode rodar agora (sai 1 se não)
    fila_pesada.py memoria                 quem come a memória (agrupado) e o limite do Docker; só lê
    fila_pesada.py portao                  gancho PreToolUse de Bash

Em 19/10/2026 o Mac de referência (16 GB, 10 núcleos) travou com 14,5 GB de
swap. O retrato tinha nove processos `node` de PIDs consecutivos, de 1,7 a
2,6 GB cada: o jest no padrão de `núcleos - 1` workers. Era a terceira vez. Em
01/10/2026 foram duas suítes jest em paralelo, e em 02/10/2026 sobras de
atividades que já tinham morrido.

A regra de limitar workers e rodar uma suíte por vez já estava escrita em
`references/test-resources.md` desde 01/10/2026. Prosa não acontece: a
suíte de 19/10 rodou sem limite do mesmo jeito. Esta ferramenta é a parte de
código, em três peças:

1. **A fila.** Uma trava de arquivo da máquina inteira (`~/.elcamargo`),
   pedida por `flock`. Vale entre frentes e entre sessões, porque o arquivo é
   um só. O kernel solta a trava quando o processo morre, então não sobra fila
   presa de janela fechada no meio. Desde 2.82.0 são duas raias, uma trava
   cada: a curta (build, `tsc`) e a longa (teste, e2e, runner de QA, e o que a
   fila não reconhece). Um comando de cada, no máximo.
2. **O portão de swap.** Com a vez na mão, antes de rodar, lê o swap em uso.
   Acima de `ELCAMARGO_SWAP_TETO_GB` (padrão 4) recusa, para o pico ficar
   perto dos 5 GB que o Ederson pediu como teto.
3. **O gancho.** Recusa o comando pesado que chega ao Bash fora da fila, e o
   jest, vitest, playwright ou stryker chamados direto sem limite de workers.
   O `flow_state gates` não passa pelo Bash, e por isso chama a fila por
   dentro (`vez`).

## O que ela NÃO prova

**Que todo comando pesado passa por aqui.** O gancho lê o texto do comando
e, desde 2.81.0, o corpo do script de nome neutro (`npm run gate`) no
`package.json` da pasta ou do `--prefix`. Script de workspace apontado por
nome (`--filter`, `--workspace`), os `pre`/`post` do npm, runner que ela não
conhece, ou suíte disparada por um processo que já estava rodando passam sem
ser vistos. Servidor de desenvolvimento (`next dev`, `nest start --watch`)
fica de fora de propósito: ele não termina, e com a vez na mão travaria a
fila até alguém derrubá-lo.

**Que o comando dentro do `npm test` limita os workers.** Atrás do script
pode ser jest, vitest ou outra coisa, e a flag muda de nome. O gancho só
exige o limite quando o runner aparece no comando.

**Que um build e um teste juntos cabem na memória.** As duas raias deixam
os dois rodarem ao mesmo tempo. Quem segura é o portão da memória, na
entrada de cada um, e a vigia, que derruba o que entrar depois de a memória
afundar. Um build pesado de verdade (`next build` de monorepo) pode passar de
"curto" no nome e não no tamanho.

**Que swap baixo é máquina folgada.** O macOS não devolve o swap sozinho
quando a pressão passa: depois de um pico, o número pode ficar alto por horas
com a máquina ociosa. O portão vai recusar nesse caso também, e a decisão de
seguir é da pessoa (`ELCAMARGO_SWAP_FORCAR=1`).

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

TETO_SWAP_PADRAO_GB = 4.0
# Swap acima do teto só recusa se estiver mexendo: acima disto, em MB/s de
# memória indo para o swap, é aperto de agora. Parado, é sobra de pico antigo.
ATIVO_MB_S_PADRAO = 1.0
FOLGA_MIN_PADRAO = 20.0
# A vigia, durante o comando.
VIGIA_S_PADRAO = 10.0
CRESCIMENTO_GB_PADRAO = 1.5
FOLGA_CRITICA_PADRAO = 10.0
ESPERA_PADRAO_S = 300
# O código que o `sysexits.h` reserva para "tente de novo depois". Recusa da
# fila não é falha do comando: ele nem rodou.
SAIDA_RECUSADA = 75
# Quem já está com a vez não pede de novo. Sem isto, um comando da fila que
# chama a fila por dentro esperaria por ele mesmo até a espera estourar.
DONO = "ELCAMARGO_FILA_DONO"

# ------------------------------------------------------------- o que é pesado

# Runner chamado direto. O valor é a flag que limita os workers dele: o gancho
# exige uma delas, porque sem flag o jest abre `núcleos - 1`.
DIRETOS: dict[str, tuple[str, ...]] = {
    "jest": ("--maxWorkers", "--max-workers", "-w", "--runInBand", "-i"),
    "vitest": ("--maxWorkers", "--max-workers", "--no-file-parallelism",
               "--fileParallelism", "--poolOptions"),
    "playwright": ("--workers", "-j"),
    "stryker": ("--concurrency", "-c"),
    "tsc": (),
}
# Runner que só é pesado com este subcomando: `next build`, e não `next dev`.
COM_SUBCOMANDO = {"next": "build", "nest": "build", "vite": "build"}
# `playwright` só pesa no `test`; `playwright install` é download.
SUBCOMANDO_EXIGIDO = {"playwright": "test", "stryker": "run"}
SCRIPT_PESADO = re.compile(
    r"^(test|build|e2e|jest|vitest|playwright|tsc|typecheck|type-check|"
    r"stryker|mutation)([:._-].*)?$")
# Script pesado que é da raia curta: compila e sai. Teste, e2e e mutação são
# da longa. Ver `RAIAS`.
SCRIPT_CURTO = re.compile(r"^(build|tsc|typecheck|type-check)([:._-].*)?$")
GERENCIADORES = {"npm", "pnpm", "yarn", "bun"}
EXECUTORES = {"npx", "bunx", "pnpx"}
# Flag de gerenciador que consome o token seguinte. Sem esta lista,
# `npm --prefix backend test` leria `backend` como o nome do script.
FLAG_COM_VALOR = {"--prefix", "-C", "--dir", "--filter", "-F", "-w",
                  "--workspace", "--cwd", "-p", "--package"}
PREFIXOS = {"env", "time", "nice", "nohup", "command", "exec", "caffeinate"}
CASCAS = {"sh", "bash", "zsh"}
SEPARADORES = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")"}
MARCA_DA_FILA = "fila_pesada.py"


def _tokens(texto: str) -> list[str]:
    # Quebra de linha separa comando como `;`, e o `shlex` com
    # `punctuation_chars` a trata como espaço.
    lex = shlex.shlex(texto.replace("\n", " ; "), posix=True,
                      punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        # Aspa sem par: melhor ler mal do que não ler. Quem decide é o
        # shell, e o comando que ele recusar não roda de qualquer jeito.
        return texto.split()


def _simples(texto: str) -> list[list[str]]:
    """Os comandos simples de uma linha de shell, já em tokens."""
    fora, atual = [], []
    for tok in _tokens(texto):
        if tok in SEPARADORES or (tok and set(tok) <= set("&|;()")):
            if atual:
                fora.append(atual)
            atual = []
        else:
            atual.append(tok)
    if atual:
        fora.append(atual)
    return fora


def _posicionais(resto: list[str], com_valor=frozenset()) -> list[str]:
    fora, pula = [], False
    for tok in resto:
        if pula:
            pula = False
            continue
        if tok == "--":
            break
        if tok.startswith("-"):
            pula = tok in com_valor
            continue
        fora.append(tok)
    return fora


def _programa(toks: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(toks):
        tok = toks[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1
            continue
        if os.path.basename(tok) in PREFIXOS:
            i += 1
            while i < len(toks) and toks[i].startswith("-"):
                i += 1
            continue
        break
    if i >= len(toks):
        return "", []
    return os.path.basename(toks[i]), toks[i + 1:]


# Script que chama script que chama script. Mais fundo que isto é ciclo.
FUNDO_MAXIMO = 4
# Flag de gerenciador que muda a pasta do `package.json`. `--filter` e
# `--workspace` apontam pacote por nome, e daqui não dá para resolver.
FLAG_DE_PASTA = {"--prefix", "-C", "--dir", "--cwd"}


def _pasta_do_gerenciador(resto: list[str], cwd: str | None) -> str | None:
    pasta_ = cwd
    for i, tok in enumerate(resto):
        if tok == "--":
            break
        valor = None
        if tok in FLAG_DE_PASTA and i + 1 < len(resto):
            valor = resto[i + 1]
        elif "=" in tok and tok.split("=", 1)[0] in FLAG_DE_PASTA:
            valor = tok.split("=", 1)[1]
        if valor is not None:
            valor = os.path.expanduser(valor)
            pasta_ = valor if os.path.isabs(valor) or cwd is None else os.path.join(cwd, valor)
    return pasta_


def _corpo_do_script(script: str, pasta_: str | None) -> tuple[str, str] | None:
    """(pasta, corpo) do script no `package.json` da pasta, ou `None`."""
    if not script or pasta_ is None:
        return None
    try:
        dados = json.loads((Path(pasta_) / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    corpo = (dados.get("scripts") or {}).get(script) if isinstance(dados, dict) else None
    return (pasta_, corpo) if isinstance(corpo, str) and corpo.strip() else None


def _classificar(nome: str, resto: list[str], cwd: str | None = None,
                 fundo: int = 0) -> dict | None:
    """O que este comando simples é, se for pesado. `None` se não for.

    `cwd` é a pasta onde o comando roda: é dela (ou do `--prefix`) que sai o
    `package.json` de onde se lê o corpo de um script com nome neutro.
    """
    if nome in EXECUTORES:
        pos = _posicionais(resto, frozenset({"-p", "--package"}))
        if not pos:
            return None
        i = resto.index(pos[0])
        return _classificar(os.path.basename(pos[0]), resto[i + 1:], cwd, fundo)
    if nome == "node":
        pos = _posicionais(resto)
        if not pos:
            return None
        alvo = re.sub(r"\.(c|m)?js$", "", os.path.basename(pos[0]))
        if alvo in DIRETOS or alvo in COM_SUBCOMANDO:
            return _classificar(alvo, resto[resto.index(pos[0]) + 1:], cwd, fundo)
        return None
    if nome in CASCAS and "-c" in resto:
        i = resto.index("-c")
        if i + 1 < len(resto):
            achados = analisar(resto[i + 1], cwd, fundo + 1)
            return achados[0] if achados else None
        return None
    if nome in GERENCIADORES:
        pos = _posicionais(resto, FLAG_COM_VALOR)
        if not pos:
            return None
        sub = pos[0]
        if sub in ("exec", "dlx", "x"):
            if len(pos) < 2:
                return None
            return _classificar(os.path.basename(pos[1]),
                                resto[resto.index(pos[1]) + 1:], cwd, fundo)
        if sub in ("run", "run-script"):
            script = pos[1] if len(pos) > 1 else ""
        elif sub in ("test", "t", "tst"):
            script = "test"
        elif nome == "npm":
            return None
        else:
            # `yarn jest` e `pnpm vitest` rodam o binário quando não há
            # script com esse nome — e aí são o runner direto.
            if sub in DIRETOS or sub in COM_SUBCOMANDO:
                return _classificar(sub, resto[resto.index(sub) + 1:], cwd, fundo)
            script = sub
        rotulo = (f"{nome} {sub if sub != script else ''} {script}"
                  .replace("  ", " ").strip())
        if SCRIPT_PESADO.match(script):
            return {"rotulo": rotulo, "runner": None, "args": resto,
                    "curto": bool(SCRIPT_CURTO.match(script))}
        # Nome neutro (`gate`, `check`, `ci`): o que pesa é o corpo dele.
        # Em 18/11/2026 o `npm --prefix frontend run gate` do backoffice
        # rodava vitest e playwright e passava pela fila sem esperar a vez.
        corpo = _corpo_do_script(script, _pasta_do_gerenciador(resto, cwd))
        if corpo is not None and fundo < FUNDO_MAXIMO:
            dentro = analisar(corpo[1], corpo[0], fundo + 1)
            if dentro:
                # Os workers do script são do `package.json`, não do comando:
                # como `npm test`, o script entra na fila e não é policiado.
                return {"rotulo": f"{rotulo} → {dentro[0]['rotulo']}",
                        "runner": None, "args": resto,
                        "curto": all(d.get("curto") for d in dentro)}
        return None
    if nome in COM_SUBCOMANDO:
        pos = _posicionais(resto)
        if pos and pos[0] == COM_SUBCOMANDO[nome]:
            return {"rotulo": f"{nome} {pos[0]}", "runner": None, "args": resto,
                    "curto": True}
        return None
    if nome in DIRETOS:
        exigido = SUBCOMANDO_EXIGIDO.get(nome)
        if exigido:
            pos = _posicionais(resto)
            if not pos or pos[0] != exigido:
                return None
        if any(t in ("--version", "-v", "--help", "-h") for t in resto):
            return None
        return {"rotulo": nome + (f" {exigido}" if exigido else ""),
                "runner": nome, "args": resto, "curto": nome == "tsc"}
    return None


def _limita(achado: dict) -> bool:
    flags = DIRETOS.get(achado["runner"] or "", ())
    if not flags:
        return True
    return any(t == f or t.startswith(f + "=") or t.startswith(f + ".")
               or (f in ("-w", "-j", "-c") and re.fullmatch(re.escape(f) + r"\d+", t))
               for t in achado["args"] for f in flags)


def analisar(texto: str, cwd: str | None = None, _fundo: int = 0) -> list[dict]:
    """Os comandos pesados de uma linha de shell, cada um marcado se já está
    dentro da fila (`na_fila`) e se limita os workers (`limitado`).

    Com `cwd`, um script de nome neutro é lido no `package.json` daquela
    pasta (ou do `--prefix`), e um `cd pasta &&` muda a pasta dos seguintes.
    Sem `cwd`, só o texto do comando conta, como até a 2.80.0.
    """
    achados = []
    for toks in _simples(texto):
        dentro = _dentro_da_fila(toks)
        if dentro is not None:
            for a in analisar(dentro, cwd, _fundo):
                achados.append(dict(a, na_fila=True))
            continue
        nome, resto = _programa(toks)
        if nome == "cd":
            pos = _posicionais(resto)
            if cwd is not None and pos:
                cwd = os.path.join(cwd, os.path.expanduser(pos[0]))
            continue
        a = _classificar(nome, resto, cwd, _fundo)
        if a:
            a.setdefault("na_fila", False)
            a["limitado"] = _limita(a)
            achados.append(a)
    return achados


def raia_de(achados: list[dict]) -> str:
    """`curta` se tudo que pesa no comando é build ou `tsc`; `longa` no resto.

    Comando que a análise não reconhece (o `runner.py` de QA que alguém passa
    ao `rodar`) é longo: na dúvida, a raia que não deixa nada correr junto
    com teste.
    """
    return "curta" if achados and all(a.get("curto") for a in achados) else "longa"


def _dentro_da_fila(toks: list[str]) -> str | None:
    """O comando que a fila vai rodar, quando este comando simples É a fila."""
    for i, tok in enumerate(toks):
        if os.path.basename(tok) == MARCA_DA_FILA and toks[i + 1:i + 2] == ["rodar"]:
            resto = toks[i + 2:]
            if "--" in resto:
                resto = resto[resto.index("--") + 1:]
            else:
                limpo, pula = [], False
                for t in resto:
                    if pula:
                        pula = False
                    elif t in ("--espera", "--raia"):
                        pula = True
                    elif not t.startswith(("--espera=", "--raia=")):
                        limpo.append(t)
                resto = limpo
            if len(resto) == 1:
                return resto[0]
            return shlex.join(resto)
    return None


# ------------------------------------------------------------ a memória

def _quantidade(texto: str, chave: str) -> float | None:
    """Lê `chave = 1234.56M` do `vm.swapusage`, em GB. A unidade varia."""
    m = re.search(chave + r"\s*=\s*([\d.]+)([KMG])", texto)
    if not m:
        return None
    fator = {"K": 1 / 1048576, "M": 1 / 1024, "G": 1.0}[m.group(2)]
    return round(float(m.group(1)) * fator, 2)


def _saida(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def swap() -> tuple[float | None, float | None]:
    """(em uso, total) em GB. `None` quando não dá para medir.

    A mesma leitura do `process_guard._pressao_do_sistema`, sem importar
    aquele módulo: ele carrega o `flow_state`, e o `flow_state` chama esta
    fila por dentro.
    """
    if sys.platform == "darwin":
        txt = _saida(["sysctl", "-n", "vm.swapusage"])
        return _quantidade(txt, "used"), _quantidade(txt, "total")
    try:
        txt = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None, None

    def gb(chave: str) -> float | None:
        m = re.search(rf"^{chave}:\s+(\d+) kB", txt, re.M)
        return round(int(m.group(1)) / 1048576, 2) if m else None

    total, livre = gb("SwapTotal"), gb("SwapFree")
    if total is None or livre is None:
        return None, None
    return round(total - livre, 2), total


def _gravado_para_o_swap() -> int | None:
    """Bytes que o sistema já mandou para o swap desde o boot. Só cresce.

    É a diferença entre duas leituras que diz se o swap está EM USO. O número
    do `vm.swapusage` diz só quanto ficou lá, e no macOS isso fica por horas
    depois que a pressão passou.
    """
    if sys.platform == "darwin":
        txt = _saida(["vm_stat"])
        pagina = re.search(r"page size of (\d+) bytes", txt)
        saidas = re.search(r"^Swapouts:\s+(\d+)", txt, re.M)
        if not (pagina and saidas):
            return None
        return int(saidas.group(1)) * int(pagina.group(1))
    try:
        txt = Path("/proc/vmstat").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^pswpout (\d+)", txt, re.M)
    return int(m.group(1)) * os.sysconf("SC_PAGE_SIZE") if m else None


def _folga_pct() -> int | None:
    """Quanto da memória está livre, pela conta do próprio sistema."""
    if sys.platform == "darwin":
        # A mesma conta do Monitor de Atividade: livre + o que dá para
        # reaproveitar sem trocar. `free` do `vm_stat` sozinho fica quase em
        # zero numa máquina folgada, porque o macOS usa a sobra como cache.
        m = re.search(r"free percentage:\s*(\d+)%", _saida(["memory_pressure", "-Q"]))
        return int(m.group(1)) if m else None
    try:
        txt = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    total = re.search(r"^MemTotal:\s+(\d+)", txt, re.M)
    livre = re.search(r"^MemAvailable:\s+(\d+)", txt, re.M)
    if not (total and livre) or not int(total.group(1)):
        return None
    return round(100 * int(livre.group(1)) / int(total.group(1)))


def medir(amostra_s: float = 3.0) -> dict:
    """O retrato da memória: o swap parado, o swap mexendo, e a folga.

    `None` em cada campo que não deu para medir. Uma lacuna não vira zero.
    """
    falsa = os.environ.get("ELCAMARGO_FILA_MEDIDA_TESTE")
    if falsa:
        # Só a fumaça usa. Sem isto, testar a recusa exigiria travar a
        # máquina de verdade.
        try:
            return {**{"swap_usado": None, "swap_total": None,
                       "saida_mb_s": None, "folga_pct": None},
                    **json.loads(Path(falsa).read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            pass
    antes = _gravado_para_o_swap()
    inicio = time.monotonic()
    if antes is not None:
        time.sleep(amostra_s)
    depois = _gravado_para_o_swap()
    usado, total = swap()
    taxa = None
    if antes is not None and depois is not None:
        taxa = round((depois - antes) / 1048576 / max(time.monotonic() - inicio, 0.1), 2)
    return {"swap_usado": usado, "swap_total": total, "saida_mb_s": taxa,
            "folga_pct": _folga_pct()}


def _numero(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


def teto_gb() -> float:
    return _numero("ELCAMARGO_SWAP_TETO_GB", TETO_SWAP_PADRAO_GB)


def _ativo_mb_s() -> float:
    return _numero("ELCAMARGO_SWAP_ATIVO_MB_S", ATIVO_MB_S_PADRAO)


def _folga_minima() -> float:
    return _numero("ELCAMARGO_FOLGA_MIN_PCT", FOLGA_MIN_PADRAO)


def descrever_medida(m: dict) -> str:
    partes = []
    if m["swap_usado"] is None:
        partes.append("swap não medido")
    else:
        partes.append(f"swap {m['swap_usado']:.1f} de {m['swap_total'] or 0:.1f} GB")
    if m["saida_mb_s"] is not None:
        partes.append(f"entrando no swap {m['saida_mb_s']:.1f} MB/s")
    if m["folga_pct"] is not None:
        partes.append(f"folga {m['folga_pct']}%")
    return ", ".join(partes)


def avaliar(m: dict) -> tuple[str | None, str]:
    """(motivo da recusa ou `None`, observação). A regra inteira mora aqui.

    Swap alto e PARADO é sobra de um pico que já passou, e não impede nada:
    o que trava a máquina é o sistema mandando memória para o swap AGORA, ou
    a memória sem folga para o comando que vai subir.
    """
    folga, taxa, usado = m["folga_pct"], m["saida_mb_s"], m["swap_usado"]
    if folga is not None and folga < _folga_minima():
        return (f"memória sem folga: {folga}% livre (mínimo "
                f"{_folga_minima():.0f}%)", "")
    if taxa is not None and taxa > _ativo_mb_s():
        return (f"o sistema está mandando memória para o swap agora, "
                f"{taxa:.1f} MB/s (limite {_ativo_mb_s():.1f})", "")
    if usado is not None and usado > teto_gb():
        if taxa is None:
            # Sem a atividade medida, não dá para separar sobra de aperto.
            return (f"swap em {usado:.1f} GB, acima de {teto_gb():.1f}, e não "
                    "consegui medir se ele está mexendo", "")
        return None, (f"swap acima de {teto_gb():.1f} GB, mas parado: é sobra "
                      "de um pico anterior, e não aperto de agora")
    if usado is None and taxa is None and folga is None:
        return None, "memória NÃO medida nesta máquina; o portão não cobriu"
    return None, ""


def regra() -> str:
    """O critério de `avaliar` numa frase, com os números em vigor.

    É o que os steps citam e o que o `estado` imprime: uma regra só, escrita
    aqui, e não um número de swap guardado na memória de cada sessão.
    """
    return (f"recusa com folga abaixo de {_folga_minima():.0f}% ou com memória "
            f"entrando no swap acima de {_ativo_mb_s():.1f} MB/s; swap alto e "
            f"parado (acima de {teto_gb():.1f} GB) não recusa sozinho, só se "
            "não der para medir se ele está mexendo")


def _memoria_mod():
    """O `memoria.py` ao lado deste arquivo, ou `None`."""
    import importlib.util
    arquivo = Path(__file__).with_name("memoria.py")
    spec = importlib.util.spec_from_file_location("elcamargo_memoria", arquivo)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _maiores(n: int = 5) -> list[str]:
    # Agrupado por app, sessão e worktree (2.83.0): `node` solto não diz de
    # quem é. Sem o `memoria.py`, a lista por nome, como antes.
    try:
        mod = _memoria_mod()
        if mod is not None:
            linhas = mod.quem_come(n)
            if linhas:
                return linhas
    except Exception:  # noqa: BLE001
        pass
    linhas = []
    for linha in _saida(["ps", "-axo", "rss=,comm="]).splitlines():
        campos = linha.split(None, 1)
        if len(campos) == 2 and campos[0].isdigit():
            linhas.append((int(campos[0]), campos[1].rsplit("/", 1)[-1][:40]))
    linhas.sort(reverse=True)
    return [f"{kb / 1048576:.1f} GB  {nome}" for kb, nome in linhas[:n]]


# ----------------------------------------------------------------- a fila

class Recusa(Exception):
    """O comando não rodou: a vez não veio, ou a memória estava apertada."""


def pasta() -> Path:
    return Path(os.environ.get("ELCAMARGO_FILA_DIR")
                or Path.home() / ".elcamargo")


def _trancar(fd: int) -> bool:
    """Pede a trava sem esperar. `True` se veio."""
    try:
        import fcntl
    except ImportError:
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


# Duas raias, uma trava cada. Em 18/11/2026 um runner de QA segurou a vez
# 16 min e o build da 1103 esperou 900 s e saiu 75: com uma vez só, o build
# de um minuto espera o teste de vinte. Na raia longa, teste, e2e, mutação e
# o que a fila não reconhece; na curta, build e `tsc`. Um de cada no máximo,
# e os dois passam pelo portão da memória e pela vigia. A longa fica com o
# nome antigo da trava, para a sessão numa versão anterior continuar na
# mesma fila.
RAIAS = {
    "longa": ("fila-pesada.lock", "fila-pesada.json", "teste, e2e, runner de QA"),
    "curta": ("fila-curta.lock", "fila-curta.json", "build, tsc"),
}


def _quem_esta(raia: str = "longa") -> dict:
    try:
        return json.loads((pasta() / RAIAS[raia][1]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# Quantas durações guardar por comando, e quantos comandos. A mediana das
# últimas cinco é a estimativa; o arquivo não cresce sem fim.
HISTORICO_POR_COMANDO = 5
HISTORICO_COMANDOS = 200


def _tempo(segundos: float) -> str:
    return f"{segundos:.0f} s" if segundos < 90 else f"{segundos / 60:.0f} min"


def _historico() -> dict:
    try:
        dados = json.loads((pasta() / "fila-historico.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _guardar_duracao(comando: str, segundos: float) -> None:
    """Quanto o comando ficou com a vez. Só quem tem a vez escreve aqui."""
    hist = _historico()
    chave = comando[:200]
    lista = [x for x in hist.pop(chave, []) if isinstance(x, (int, float))]
    hist[chave] = (lista + [round(segundos, 1)])[-HISTORICO_POR_COMANDO:]
    while len(hist) > HISTORICO_COMANDOS:
        hist.pop(next(iter(hist)))
    try:
        (pasta() / "fila-historico.json").write_text(json.dumps(hist), encoding="utf-8")
    except OSError:
        pass


def _estimativa(comando: str, decorrido: float | None) -> str:
    """Quanto o comando costuma levar e quanto falta, pelas vezes anteriores."""
    duracoes = sorted(x for x in _historico().get(comando[:200], [])
                      if isinstance(x, (int, float)))
    if not duracoes:
        return "sem histórico desse comando, espera sem estimativa"
    mediana = duracoes[len(duracoes) // 2]
    base = f"costuma levar {_tempo(mediana)} ({len(duracoes)} vez(es))"
    if decorrido is None:
        return base
    falta = mediana - decorrido
    if falta <= 0:
        return f"{base}, e já passou disso: a espera não tem estimativa"
    return f"{base}; espera estimada: ~{_tempo(falta)}"


def _descrever(d: dict) -> str:
    if not d:
        return "outro comando pesado (sem registro de quem)"
    desde = d.get("desde", "")
    try:
        decorrido = (datetime.now() - datetime.fromisoformat(desde)).total_seconds()
        ha = f"há {_tempo(decorrido)}"
    except (TypeError, ValueError):
        decorrido = None
        ha = f"desde {desde or '?'}"
    comando = str(d.get("comando", "?"))
    return (f"`{comando}` (pid {d.get('pid', '?')}, {ha}, em {d.get('cwd', '?')}); "
            + _estimativa(comando, decorrido))


def conferir_memoria() -> str:
    """Recusa se a máquina está apertada AGORA. Devolve a linha do que leu.

    Swap mexendo pode ser um pico curto de outro programa: antes de recusar
    por isso, mede de novo duas vezes.
    """
    for tentativa in range(3):
        m = medir()
        motivo, obs = avaliar(m)
        if not motivo or "agora" not in motivo or tentativa == 2:
            break
    leitura = descrever_medida(m) + (f" — {obs}" if obs else "")
    if not motivo:
        return leitura
    if os.environ.get("ELCAMARGO_SWAP_FORCAR") == "1":
        return f"{leitura} — {motivo}; seguindo por ELCAMARGO_SWAP_FORCAR=1"
    linhas = [
        f"[elcamargo] Recusado: {motivo}.",
        f"  Leitura: {leitura}.",
        "  Comando pesado assim é como o Mac de 16 GB travou em 19/10/2026, com",
        "  14,5 GB de swap. Os maiores processos agora:",
        *("    " + x for x in _maiores()),
        "",
        f"  A leitura inteira, com o Docker: python3 {Path(__file__).resolve()} memoria",
        "  Não contorne sozinho. Diga à pessoa o que está ocupando a memória e",
        "  pergunte. Seguir mesmo assim é decisão dela, com ELCAMARGO_SWAP_FORCAR=1.",
    ]
    raise Recusa("\n".join(linhas))


class Vigia:
    """Olha a memória enquanto o comando roda, e o derruba se ela afundar.

    O portão da entrada vê a máquina antes. O jest de 19/10/2026 subiu nove
    workers DEPOIS de começar, e quem afunda a máquina é o comando que a fila
    acabou de deixar entrar. A vigia derruba só o grupo de processos que ela
    própria criou, pelo PID do filho: nunca por nome.

    Derruba quando duas leituras seguidas mostram o swap crescendo mais de
    `ELCAMARGO_SWAP_CRESCIMENTO_GB` desde a entrada E mexendo agora, ou a
    folga abaixo de `ELCAMARGO_FOLGA_CRITICA_PCT`.
    """

    def __init__(self, filho: subprocess.Popen):
        import threading
        self.filho = filho
        self.motivo: str | None = None
        self.pior = ""
        self._parar = threading.Event()
        self._linha = threading.Thread(target=self._olhar, daemon=True)

    def __enter__(self) -> "Vigia":
        self._linha.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._parar.set()
        self._linha.join(timeout=15)

    def _olhar(self) -> None:
        intervalo = _numero("ELCAMARGO_VIGIA_S", VIGIA_S_PADRAO)
        crescimento = _numero("ELCAMARGO_SWAP_CRESCIMENTO_GB", CRESCIMENTO_GB_PADRAO)
        critica = _numero("ELCAMARGO_FOLGA_CRITICA_PCT", FOLGA_CRITICA_PADRAO)
        inicio = medir(amostra_s=0)["swap_usado"]
        ruins = 0
        while not self._parar.wait(intervalo):
            if self.filho.poll() is not None:
                return
            m = medir(amostra_s=min(2.0, intervalo / 2))
            usado, taxa, folga = m["swap_usado"], m["saida_mb_s"], m["folga_pct"]
            motivo = None
            if folga is not None and folga < critica:
                motivo = f"folga caiu a {folga}% (crítico {critica:.0f}%)"
            elif (usado is not None and inicio is not None and taxa is not None
                  and usado - inicio > crescimento and taxa > _ativo_mb_s()):
                motivo = (f"o swap cresceu {usado - inicio:.1f} GB desde a entrada "
                          f"e segue entrando a {taxa:.1f} MB/s")
            ruins = ruins + 1 if motivo else 0
            if motivo:
                self.pior = descrever_medida(m)
            if ruins >= 2:
                self.motivo = motivo
                self._derrubar()
                return

    def _derrubar(self) -> None:
        print(f"[elcamargo] VIGIA: derrubando o comando (pid {self.filho.pid}): "
              f"{self.motivo}. Leitura: {self.pior}.", file=sys.stderr, flush=True)
        for sinal, espera in ((signal.SIGTERM, 10), (getattr(signal, "SIGKILL", None), 5)):
            if sinal is None or self.filho.poll() is not None:
                return
            try:
                if hasattr(os, "killpg"):
                    os.killpg(self.filho.pid, sinal)
                else:
                    self.filho.terminate()
            except (ProcessLookupError, PermissionError):
                return
            try:
                self.filho.wait(timeout=espera)
            except subprocess.TimeoutExpired:
                continue


def motivo_da_vigia(vigia: "Vigia") -> str:
    return "\n".join([
        f"[elcamargo] Interrompido pela vigia: {vigia.motivo}.",
        f"  Leitura: {vigia.pior}.",
        "  O comando NÃO terminou: o resultado dele não vale como vermelho nem",
        "  como verde. Diminua os workers, ou rode uma parte da suíte, e diga à",
        "  pessoa o que a vigia viu.",
    ])


@contextmanager
def vez(comando: str, espera_s: float = ESPERA_PADRAO_S, raia: str = "longa"):
    """Segura a vez da raia enquanto o bloco roda. Levanta `Recusa`.

    Rende a linha de swap lida, para quem chamou registrar o que viu.
    """
    if raia not in RAIAS:
        raia = "longa"
    trava, quem, _ = RAIAS[raia]
    if os.environ.get(DONO):
        yield "dentro da fila (a vez já é de quem chamou)"
        return
    fd = None
    aviso = ""
    try:
        pasta().mkdir(parents=True, exist_ok=True)
        fd = os.open(pasta() / trava, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        # Sandbox que não deixa escrever em `~`. Recusar aqui travaria todo
        # teste da sessão; seguir calado fingiria uma fila que não houve.
        aviso = f"fila NÃO coberta (não abri {pasta()}: {exc.strerror}); "
    try:
        if fd is not None:
            limite = time.monotonic() + espera_s
            avisou = False
            while not _trancar(fd):
                if not avisou:
                    print(f"[elcamargo] Na raia {raia} atrás de "
                          f"{_descrever(_quem_esta(raia))}.",
                          file=sys.stderr, flush=True)
                    avisou = True
                if time.monotonic() >= limite:
                    raise Recusa(
                        f"[elcamargo] A vez não veio em {espera_s:.0f}s na raia {raia}: "
                        f"{_descrever(_quem_esta(raia))} continua rodando.\n"
                        "  Tente de novo quando ele terminar. Não rode por fora da\n"
                        "  fila: dois comandos pesados juntos é o que trava a máquina.")
                time.sleep(2)
            (pasta() / quem).write_text(json.dumps({
                "pid": os.getpid(), "comando": comando[:200], "raia": raia,
                "desde": datetime.now().isoformat(timespec="seconds"),
                "cwd": os.getcwd()}), encoding="utf-8")
        leitura = conferir_memoria()
        os.environ[DONO] = str(os.getpid())
        inicio = time.monotonic()
        try:
            yield aviso + leitura
        finally:
            os.environ.pop(DONO, None)
            if fd is not None:
                _guardar_duracao(comando, time.monotonic() - inicio)
    finally:
        if fd is not None:
            os.close(fd)  # fechar solta a trava


# ---------------------------------------------------------------- comandos

def cmd_rodar(argv: list[str], espera_s: float, raia: str | None = None) -> int:
    if not argv:
        print("erro: `rodar` exige o comando depois de `--`.", file=sys.stderr)
        return 2
    texto = argv[0] if len(argv) == 1 else shlex.join(argv)
    if raia is None:
        try:
            raia = raia_de(analisar(texto, os.getcwd()))
        except Exception:  # noqa: BLE001
            raia = "longa"
    try:
        with vez(texto, espera_s, raia) as leitura:
            print(f"[elcamargo] Com a vez na raia {raia}: {leitura}.",
                  file=sys.stderr, flush=True)
            # Grupo próprio: é o que a vigia derruba inteiro, com os workers
            # do jest juntos, sem tocar em mais nada.
            filho = subprocess.Popen(texto if len(argv) == 1 else argv,
                                     shell=len(argv) == 1, start_new_session=True)

            def repassar(sinal, _quadro):
                try:
                    os.killpg(filho.pid, sinal)
                except (AttributeError, ProcessLookupError, PermissionError):
                    filho.send_signal(sinal)

            for s in (signal.SIGTERM, signal.SIGINT):
                signal.signal(s, repassar)
            with Vigia(filho) as vigia:
                codigo = filho.wait()
    except Recusa as exc:
        print(str(exc), file=sys.stderr)
        return SAIDA_RECUSADA
    if vigia.motivo:
        print(motivo_da_vigia(vigia), file=sys.stderr)
        return SAIDA_RECUSADA
    print(f"[elcamargo] Fim, saída {codigo}; {descrever_medida(medir(1.0))}.",
          file=sys.stderr)
    return codigo


def _livre(raia: str) -> bool | None:
    fd = None
    try:
        pasta().mkdir(parents=True, exist_ok=True)
        fd = os.open(pasta() / RAIAS[raia][0], os.O_RDWR | os.O_CREAT, 0o644)
        return _trancar(fd)
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


def cmd_estado() -> int:
    for raia, (_, _, o_que) in RAIAS.items():
        livre = _livre(raia)
        rotulo = f"fila {raia} ({o_que})"
        if livre is None:
            print(f"{rotulo}: não consegui abrir {pasta()}")
        elif livre:
            print(f"{rotulo}: livre")
        else:
            print(f"{rotulo}: ocupada por {_descrever(_quem_esta(raia))}")
    m = medir()
    motivo, obs = avaliar(m)
    print(f"memória: {descrever_medida(m)}")
    print("portão: " + (f"RECUSARIA — {motivo}" if motivo else
                        "deixaria entrar" + (f" ({obs})" if obs else "")))
    print(f"regra: {regra()}")
    # O código responde "pode rodar?" para quem pergunta por script. Fila
    # ocupada não é "não": o `rodar` espera a vez.
    return 1 if motivo else 0


def cmd_memoria() -> int:
    """Quem come a memória, agrupado, e o limite do Docker. Só lê."""
    print(f"memória: {descrever_medida(medir())}")
    try:
        mod = _memoria_mod()
    except Exception as exc:  # noqa: BLE001
        mod = None
        print(f"(memoria.py não carregou: {exc})")
    if mod is None:
        print("os maiores processos:", *("  " + x for x in _maiores(8)), sep="\n")
        return 0
    print("\n".join(mod.relatorio()))
    return 0


def _ler_evento() -> dict:
    """O JSON do gancho, ou vazio. Nunca trava: ver `anchor.ler_evento`."""
    import select
    try:
        if sys.stdin.isatty() or not select.select([sys.stdin], [], [], 0)[0]:
            return {}
        bruto = sys.stdin.read()
        evento = json.loads(bruto) if bruto else {}
    except (ValueError, OSError, TypeError):
        return {}
    return evento if isinstance(evento, dict) else {}


def cmd_portao() -> int:
    """PreToolUse de Bash. Silêncio e `0` para tudo que não é pesado.

    Recusa com `2` e o motivo no stderr, que é o que o Claude Code devolve ao
    modelo. Não reescreve o comando: reescrever com `allow` pularia a
    permissão da pessoa para o comando inteiro, e não só para a fila.
    """
    if os.environ.get("ELCAMARGO_FILA_PESADA") == "desligada":
        return 0
    evento = _ler_evento()
    if evento.get("tool_name") != "Bash":
        return 0
    texto = str((evento.get("tool_input") or {}).get("command") or "")
    # O `cwd` do evento é a pasta da sessão: dela sai o `package.json`.
    cwd = evento.get("cwd")
    achados = analisar(texto, cwd if isinstance(cwd, str) and cwd else None) if texto else []
    fora = [a for a in achados if not a["na_fila"]]
    sem_limite = [a for a in achados if not a["limitado"]]
    if not fora and not sem_limite:
        return 0
    linhas = []
    if fora:
        linhas += [
            "[elcamargo] Comando pesado fora da fila: "
            + ", ".join(f"`{a['rotulo']}`" for a in fora) + ".",
            "  Na máquina roda um comando pesado por raia (teste numa, build na",
            "  outra), entre frentes e entre sessões, e só com a memória folgada.",
            "  Rode pela fila, com timeout longo no Bash:",
            "",
            f"    python3 {shlex.quote(str(Path(__file__).resolve()))} rodar -- "
            + shlex.quote(texto),
            "",
        ]
    if sem_limite:
        linhas += [
            "  Limite os workers de "
            + ", ".join(f"`{a['rotulo']}`" for a in sem_limite) + ": jest e vitest",
            "  com `--maxWorkers=2`, playwright test com `--workers=2`, stryker com",
            "  `--concurrency=2`. O número vem de `recursos.max_workers_teste`.",
            "",
        ]
    linhas.append("  Em 19/10/2026 nove workers do jest levaram o Mac de 16 GB a 14,5 GB")
    linhas.append("  de swap. Ver references/test-resources.md.")
    print("\n".join(linhas), file=sys.stderr)
    return 2


# ------------------------------------------------------------ a versão

def _versao(nome: str) -> tuple[int, ...] | None:
    return tuple(int(x) for x in nome.split(".")) if re.fullmatch(r"\d+(\.\d+)+", nome) else None


def mais_nova(aqui: Path | None = None) -> Path | None:
    """A cópia deste arquivo na versão instalada mais nova, se não for esta.

    Uma sessão aberta antes de um `plugin update` continua chamando a pasta da
    versão antiga até o `/reload-plugins`, e o cache guarda as versões antigas
    por 14 dias. Sem isto, cada mudança na regra da memória pedia reiniciar
    todas as sessões; com isto, quem chama a pasta velha roda a regra nova.
    Só fora do cache (no clone do pacote) é que não há irmã a procurar.
    """
    aqui = (aqui or Path(__file__)).resolve()
    raiz = aqui.parents[2]
    atual = _versao(raiz.name)
    if atual is None:
        return None
    melhor, caminho = atual, None
    try:
        irmas = list(raiz.parent.iterdir())
    except OSError:
        return None
    for irma in irmas:
        v = _versao(irma.name)
        candidato = irma / aqui.relative_to(raiz)
        if (v and v > melhor and not (irma / ".orphaned_at").exists()
                and candidato.is_file()):
            melhor, caminho = v, candidato
    return caminho


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" in argv:
        i = argv.index("--")
        argv, depois = argv[:i], argv[i + 1:]
    else:
        depois = []
    p = argparse.ArgumentParser(prog="fila_pesada.py", description=__doc__.split("\n")[0])
    p.add_argument("acao", choices=("rodar", "estado", "portao", "memoria"))
    p.add_argument("--espera", type=float, default=ESPERA_PADRAO_S,
                   help="rodar: quantos segundos esperar a vez antes de desistir")
    p.add_argument("--raia", choices=tuple(RAIAS),
                   help="rodar: curta (build, tsc) ou longa (teste, runner de QA). "
                        "Sem ela, a fila decide pelo comando; o que ela não "
                        "reconhece vai para a longa")
    args = p.parse_args(argv)
    if args.acao == "rodar":
        return cmd_rodar(depois, args.espera, args.raia)
    if args.acao == "estado":
        return cmd_estado()
    if args.acao == "memoria":
        return cmd_memoria()
    try:
        return cmd_portao()
    except Exception:  # noqa: BLE001
        # Gancho que quebra atrapalha TODO Bash. Erro aqui sai como silêncio.
        return 0


if __name__ == "__main__":
    if not os.environ.get("ELCAMARGO_FILA_SALTOU"):
        try:
            _nova = mais_nova()
        except Exception:  # noqa: BLE001
            _nova = None
        if _nova:
            os.environ["ELCAMARGO_FILA_SALTOU"] = str(_nova)
            os.execv(sys.executable, [sys.executable, str(_nova), *sys.argv[1:]])
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
