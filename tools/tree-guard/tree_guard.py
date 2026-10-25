#!/usr/bin/env python3
"""A árvore de trabalho está como estava antes de disparar as frentes?

    tree_guard.py marcar   --id 1061
    tree_guard.py conferir --id 1061

O step 9 dispara seis frentes que compartilham a árvore do usuário, e duas delas
**escrevem** por ofício: a de qualidade insere mutantes no código-fonte, a de
execução cria fixtures e tokens para exercitar a aplicação. As duas restauram
depois. O problema é o "depois".

Em 08/09/2026 a máquina paginou até travar no meio de uma execução. A frente de
qualidade tinha três mutantes vivos em `env.ts` — `if (false && ...)` em cima da
validação de boot de um segredo — e restaurou por pouco, antes de morrer. Se
tivesse morrido dois segundos antes, o mutante ficaria, e o commit seguinte o
levaria junto.

E o efeito colateral foi pior que o risco: as outras frentes estavam LENDO
aquela árvore. Uma delas percebeu sozinha que duas leituras do mesmo arquivo
devolviam conteúdos diferentes e passou a revisar contra o commit. Foi o que
salvou a revisão dela, e foi sorte — nenhuma linha do fluxo pedia aquilo.

Esta ferramenta troca a sorte por uma conferência. Ela não impede a escrita:
**diz que houve.** Impedir é papel do isolamento em worktree, que é decisão da
skill; aqui o que se garante é que ninguém consolida uma revisão sobre uma
árvore que mudou embaixo dela sem saber.

O que ela NÃO prova, e são duas coisas:

**Que a árvore limpa foi lida.** Uma frente pode ter lido no instante em que o
mutante existia e devolvido o veredicto depois de a restauração acontecer — a
marca de antes e a de depois batem, e a leitura foi suja. Contra isso só o
isolamento serve.

**Que a marca foi tirada na hora certa.** Se alguma frente já escreveu antes do
`marcar`, o que ela escreveu entra na base como se sempre tivesse estado ali, e o
`conferir` passa limpo. E não há como a ferramenta detectar isso: no step 9 a
árvore chega legitimamente suja da entrega do step 8, então árvore suja no
instante de marcar é o caso **normal**, não o suspeito. A ordem — marcar antes de
disparar qualquer frente — é garantia da skill, não desta ferramenta.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))

from flow_state import (FlowStateError, raiz_de_trabalho,  # noqa: E402
                        resolve_agents_dir)


def _caminhos(raiz: Path) -> list[tuple[str, str]]:
    """(código, caminho) para tudo que o Git vê como diferente do HEAD.

    `--porcelain -z`: formato estável, sem aspas nem escape, e o único que
    enxerga arquivo NOVO. O defeito medido deixou para trás um
    `.qa-step9-token.mjs` e três JWT numa pasta servida — nenhum rastreado, e
    portanto invisível para qualquer conferência que olhasse só o diff.
    """
    r = subprocess.run(["git", "-C", str(raiz), "status", "--porcelain", "-z",
                        "--untracked-files=all"],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        raise FlowStateError(
            f"`git status` falhou em {raiz}: "
            f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    bruto = r.stdout.decode("utf-8", "replace")
    campos = [c for c in bruto.split("\0")]
    saida: list[tuple[str, str]] = []
    i = 0
    while i < len(campos):
        entrada = campos[i]
        i += 1
        if len(entrada) < 4:
            continue
        codigo, caminho = entrada[:2], entrada[3:]
        # Rename/copy gastam DOIS campos: o destino vem no primeiro, a origem
        # no seguinte. Sem consumir o segundo, o parser lê a origem como se
        # fosse outra entrada e inventa uma mudança que não existe.
        if codigo[0] in ("R", "C"):
            i += 1
        saida.append((codigo, caminho))
    return saida


def estado(raiz: Path) -> str:
    """O que o Git vê agora, com o CONTEÚDO de cada arquivo resumido.

    O código do `status` sozinho não bastaria, e é o caso comum do step 9 que o
    prova: a árvore já chega suja da entrega do step 8, então `src/env.ts` já é
    ` M` antes de qualquer frente rodar. Um mutante inserido por cima produz a
    MESMA linha de status — e a conferência passaria dizendo que nada mudou.

    Por isso cada caminho leva um sha256 do que está no disco. Arquivo apagado
    ou ilegível entra como `-`, que também é uma mudança quando antes havia
    conteúdo.
    """
    linhas = []
    for codigo, caminho in sorted(_caminhos(raiz), key=lambda x: x[1]):
        alvo = raiz / caminho
        try:
            resumo = (hashlib.sha256(alvo.read_bytes()).hexdigest()[:16]
                      if alvo.is_file() else "dir")
        except OSError:
            resumo = "-"
        linhas.append(f"{codigo} {resumo} {caminho}")
    return "\n".join(linhas) + ("\n" if linhas else "")


def registrar(ident: str, veredicto: str, detalhe: str = "") -> None:
    """Grava o veredicto na atividade, para o `concluir` achar.

    Até 11/09/2026 esta ferramenta **não registrava nada**. Ela imprimia
    "A ÁRVORE MUDOU durante o disparo" e saía com código 1 — e o `concluir`
    passava, porque nada daquilo chegava à tabela de Conferências.

    A prova é da própria base instalada: em ~250 linhas de conferência gravadas
    nas atividades reais dos dois repositórios, `arvore` aparece **zero vezes**.
    As ferramentas que se registram sozinhas — `catraca`, `perfis` — somam
    centenas. O `FLOW.md` chama isto de *"contrato com conferência"*; o contrato
    existia e a conferência nunca chegou a ninguém.

    É o mesmo defeito do amostrador de memória, achado no mesmo dia: o
    mecanismo existia e registrava no lado errado do laço — aqui, em lado
    nenhum.
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
             "--ferramenta", "arvore", "--veredicto", veredicto,
             "--detalhe", detalhe[:200]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  [aviso] não consegui registrar: {exc}")
        return
    if r.returncode != 0:
        print(f"  [aviso] registro recusado: {(r.stderr or r.stdout).strip()[:160]}")


def marca(agents: Path, ident: str) -> Path:
    return agents / f".arvore-{ident}"


def cmd_marcar(agents: Path, raiz: Path, ident: str) -> int:
    alvo = marca(agents, ident)
    atual = estado(raiz)
    alvo.write_text(atual, encoding="utf-8")
    linhas = [l for l in atual.splitlines() if l.strip()]
    print(f"Árvore marcada para a atividade {ident}: {len(linhas)} entrada(s).")
    print(f"  {alvo}")
    print("  Dispare as frentes. Ao consolidar, rode `conferir`.")
    # A dívida nasce aqui, antes das frentes. Se a máquina travar no meio — o
    # caso de 08/09 — o `conferir` nunca roda, e sem esta linha a atividade
    # chegaria ao portão 10 sem nada dizer que uma árvore compartilhada ficou
    # sem conferência.
    registrar(ident, "exigida",
              f"árvore marcada com {len(linhas)} entrada(s); o veredicto entra "
              "quando `conferir` rodar")
    return 0


def cmd_conferir(agents: Path, raiz: Path, ident: str) -> int:
    alvo = marca(agents, ident)
    if not alvo.exists():
        raise FlowStateError(
            f"Não há marca para a atividade {ident}.\n"
            f"  A marca se cria ANTES de disparar as frentes:\n"
            f"    tree_guard.py marcar --id {ident}\n"
            "  Sem ela não há contra o que comparar, e conferir depois do fato\n"
            "  não distingue o que uma frente escreveu do que já estava lá."
        )
    def por_caminho(texto: str) -> dict[str, str]:
        # "XY hash caminho". O código tem DOIS caracteres e pode começar com
        # espaço (` M`), então ele se lê por posição — `split(" ")` come o
        # espaço da frente e desloca tudo, o que fazia o hash entrar no nome do
        # arquivo e toda mudança virar um par surgiu/sumiu.
        fora = {}
        for l in texto.splitlines():
            if len(l) < 4:
                continue
            codigo, resto = l[:2], l[3:]
            resumo, _, caminho = resto.partition(" ")
            if caminho:
                fora[caminho] = f"{codigo} {resumo}"
        return fora

    antes = por_caminho(alvo.read_text(encoding="utf-8"))
    agora = por_caminho(estado(raiz))

    surgiu = sorted(set(agora) - set(antes))
    sumiu = sorted(set(antes) - set(agora))
    # O caso que mais importa, e o que um `status` sem hash deixaria passar: o
    # arquivo já estava sujo pela entrega do step 8, e uma frente escreveu por
    # cima. Mesma linha de status, conteúdo diferente.
    mudou = sorted(c for c in set(antes) & set(agora) if antes[c] != agora[c])
    if not surgiu and not sumiu and not mudou:
        print(f"Atividade {ident}: a árvore está como antes do disparo.")
        print("  Isso NÃO prova que ninguém leu a árvore no meio de uma escrita")
        print("  que já foi desfeita — só o isolamento em worktree prova isso.")
        registrar(ident, "ok", "a árvore voltou como estava antes do disparo")
        return 0

    print(f"Atividade {ident}: A ÁRVORE MUDOU durante o disparo.")
    print()
    for c in mudou:
        print(f"  [MUDOU ] {c}")
    for c in surgiu:
        print(f"  [surgiu] {c}")
    for c in sumiu:
        print(f"  [sumiu ] {c}")
    print()
    print("  O que é SEU — relatório, spec, correção que você aplicou — é")
    print("  esperado. O que está em código-fonte não é: alguma frente escreveu")
    print("  na árvore do usuário, e as outras leram por cima disso.")
    print()
    print("  Antes de consolidar: restaure o que não é seu, e diga no relatório")
    print("  que a leitura das outras frentes pode ter sido contaminada.")
    registrar(ident, "falhou",
              f"{len(mudou)} mudado(s), {len(surgiu)} surgido(s), "
              f"{len(sumiu)} sumido(s) durante o disparo das frentes")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tree_guard.py",
        description="Guarda a árvore de trabalho enquanto as frentes rodam.")
    p.add_argument("acao", choices=("marcar", "conferir"))
    p.add_argument("--id", required=True, help="id da atividade")
    args = p.parse_args(argv)
    try:
        agents = resolve_agents_dir()
        # A árvore guardada é a que as frentes tocam, e uma atividade pode rodar
        # em worktree. Perguntar pela árvore principal descreveria um lugar que
        # o trabalho nunca tocou — erro que o `flow_state` já cometeu duas vezes
        # e por isso resolve numa função só.
        raiz = raiz_de_trabalho(agents)
        if args.acao == "marcar":
            return cmd_marcar(agents, raiz, args.id)
        return cmd_conferir(agents, raiz, args.id)
    except FlowStateError as exc:
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
