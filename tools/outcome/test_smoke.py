#!/usr/bin/env python3
"""Fumaça de outcome.py — os dois sentidos de cada conferência.

Uma ferramenta que nunca acusa é inútil, e uma que acusa demais é pior: ensina a
ignorá-la, e na vez em que ela estiver certa ninguém olha. Cada verificação tem
aqui um caso que ela DEVE pegar e um que ela NÃO PODE pegar.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outcome as D  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def rodar(texto: str, tmp: Path, raiz: str = ".") -> tuple[int, str]:
    alvo = tmp / "relatorio.md"
    alvo.write_text(texto, encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = D.cmd_conferir(Args(documento=str(alvo), raiz=raiz))
    return codigo, buf.getvalue()


CABECALHO = ("| # | Frente | Severidade | Onde | O que quebra | Destino | Prova |\n"
             "| --- | --- | --- | --- | --- | --- | --- |\n")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="destino-"))

    # ----------------------------------------------------------------
    print("\nA tabela limpa não é acusada de nada")
    limpo = CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | duplicação | corrigido | commit local, lint verde |\n"
        "| A-02 | segurança | bloqueia | b.ts:20 | vazamento | corrigido | teste que reprovava passa |\n"
        "| A-03 | qualidade | alta | c.ts:30 | teste fraco | descartado | o caso é coberto por c2.spec.ts |\n"
        "| A-04 | código | baixa | d.ts:40 | nome ruim | aceito | convenção do módulo, mantida |\n"
        "| A-05 | execução | baixa | e.ts:50 | espaçamento | corrigido | tela conferida em 375 |\n")
    codigo, saida = rodar(limpo, tmp)
    ok(codigo == 0, "relatório completo passa", saida)
    ok("Destino de 5 achados" in saida, "e imprime a distribuição", saida)
    ok("corrigido      3" in saida and "60%" in saida, "com a taxa de conversão", saida)

    # ----------------------------------------------------------------
    print("\nAchado sem destino, e achado com dois")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | x | | |\n"
        "| A-02 | código | baixa | b.ts:20 | y | corrigido em parte, o resto aceito | |\n"
        "| A-03 | código | baixa | c.ts:30 | z | corrigido | commit ok |\n"), tmp)
    ok(codigo == 1, "reprova", saida)
    ok("sem destino declarado" in saida and "A-01" in saida,
       "célula de destino vazia é denunciada", saida)
    ok("dois destinos na mesma célula" in saida and "A-02" in saida,
       "duas palavras na mesma célula é ambiguidade, não soma", saida)
    ok("A-03" not in saida.split("Destino de")[0],
       "e o achado bem preenchido não é denunciado junto", saida)

    # ----------------------------------------------------------------
    print("\n'Corrigi' não fecha nada")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | x | corrigido | |\n"
        "| A-02 | código | baixa | b.ts:20 | y | descartado | |\n"), tmp)
    ok("sem nada que o sustente" in saida and "A-01" in saida and "A-02" in saida,
       "destino sem prova é denunciado, inclusive o descarte", saida)

    print("\nMas a prova pode estar na própria célula do destino")
    codigo, saida = rodar(CABECALHO.replace(" | Prova |", " |").replace(" --- |\n", "\n") + (
        "| A-01 | código | baixa | a.ts:10 | x | corrigido em `dto.ts:44` |\n"), tmp)
    ok("sem nada que o sustente" not in saida,
       "o que sobra na célula depois da palavra conta como prova", saida)

    # ----------------------------------------------------------------
    print("\nBloqueio não viaja aberto, nem é aceito sozinho")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | segurança | bloqueia | a.ts:10 | vazamento | aberto | sem tempo |\n"
        "| A-02 | segurança | bloqueia | b.ts:20 | escalação | aceito | risco assumido |\n"
        "| A-03 | código | baixa | c.ts:30 | z | aberto | fica para depois |\n"
        "\n## Achados abertos\n\nA-01 e A-03 seguem para a próxima fatia.\n"), tmp)
    ok(codigo == 1, "reprova", saida)
    ok("bloqueia, e ficou aberto" in saida and "A-01" in saida,
       "bloqueio aberto é denunciado", saida)
    ok("sem portão que o aceitou" in saida and "A-02" in saida,
       "bloqueio aceito sem portão é denunciado", saida)
    ok("A-03" not in saida.split("Destino de")[0],
       "e um achado baixa aberto e declarado não é denunciado", saida)

    print("\nBloqueio aceito COM portão nomeado passa")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | segurança | bloqueia | a.ts:10 | x | aceito | portão 10: aceite condicionado |\n"), tmp)
    ok("sem portão que o aceitou" not in saida,
       "nomear o portão que aceitou basta", saida)

    # ----------------------------------------------------------------
    print("\nAberto que não está na seção que viaja")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | x | aberto | fica |\n"
        "\n## Achados abertos\n\nNada pendente.\n"), tmp)
    ok("não está na seção que viaja" in saida and "A-01" in saida,
       "a seção existe e não traz o achado", saida)

    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | x | aberto | fica |\n"), tmp)
    ok("não há seção Achados abertos" in saida,
       "e a seção que não existe também é denunciada", saida)

    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:10 | x | corrigido | commit local |\n"), tmp)
    ok("Achados abertos" not in saida.split("Destino de")[0],
       "sem nenhum aberto, a seção não é cobrada", saida)

    # ----------------------------------------------------------------
    print("\nO mesmo achado em duas voltas conta uma vez")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | alta | a.ts:10 | x | aberto | volta 1 |\n"
        "\n### Volta 2\n\n" + CABECALHO +
        "| A-01 | código | alta | a.ts:10 | x | corrigido | volta 2, teste passa |\n"), tmp)
    ok("Destino de 1 achados" in saida, "o total não infla", saida)
    ok("corrigido      1" in saida and "aberto         0" in saida,
       "e vale a última volta, não a primeira", saida)
    ok("mais de uma volta" in saida and "A-01" in saida,
       "e a ferramenta diz que contou assim", saida)

    # ----------------------------------------------------------------
    print("\nO sinal de consolidação que só encaminha")
    codigo, saida = rodar(CABECALHO + "".join(
        f"| A-0{n} | código | baixa | a.ts:{n} | x | corrigido | commit local |\n"
        for n in range(1, 7)), tmp)
    ok("nenhum achado descartado" in saida,
       "seis achados e zero descartes vira aviso", saida)

    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:1 | x | corrigido | commit local |\n"
        "| A-02 | código | baixa | a.ts:2 | x | descartado | não reproduz |\n"), tmp)
    ok("nenhum achado descartado" not in saida,
       "mas duas linhas não são amostra para essa conta", saida)

    codigo, saida = rodar(CABECALHO + "".join(
        f"| A-0{n} | código | baixa | a.ts:{n} | x | descartado | não reproduz |\n"
        for n in range(1, 7)), tmp)
    ok("nenhum achado virou mudança" in saida,
       "revisão que não mudou uma linha também vira aviso", saida)

    # ----------------------------------------------------------------
    print("\nO commit citado como prova")
    repo = tmp / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q"],
                ["git", "config", "user.email", "t@t"],
                ["git", "config", "user.name", "t"],
                ["git", "commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run(cmd, cwd=repo, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    ok(len(sha) == 40, "o repositório de teste tem um commit", sha)

    codigo, saida = rodar(CABECALHO + (
        f"| A-01 | código | baixa | a.ts:1 | x | corrigido | commit {sha[:10]} |\n"), tmp,
        raiz=str(repo))
    ok("commit inexistente" not in saida, "hash que existe passa", saida)

    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:1 | x | corrigido | commit deadbeef1 |\n"), tmp,
        raiz=str(repo))
    ok("commit inexistente" in saida and "deadbeef1" in saida,
       "hash que não resolve é denunciado", saida)
    ok(codigo == 0, "mas como MEDIO — pode ser branch não trazida", saida)

    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | baixa | a.ts:1 | x | corrigido | cor de fundo #a1b2c3d agora |\n"), tmp,
        raiz=str(repo))
    ok("commit inexistente" not in saida,
       "cor hexadecimal não é confundida com hash", saida)

    # ----------------------------------------------------------------
    print("\nRelatório sem coluna de destino nenhuma")
    codigo, saida = rodar(
        "| # | Frente | Severidade | Onde |\n| --- | --- | --- | --- |\n"
        "| A-01 | código | baixa | a.ts:10 |\n", tmp)
    ok(codigo == 1 and "Nenhuma tabela com coluna Destino" in saida,
       "a ausência da coluna é o achado", saida)

    # ----------------------------------------------------------------
    print("\n'não fechado' não é fechado")
    codigo, saida = rodar(CABECALHO + (
        "| A-01 | código | alta | a.ts:1 | x | não fechado | medido de novo |\n"
        "| A-02 | código | alta | a.ts:2 | y | fechado | teste passa |\n"
        "| A-03 | código | alta | a.ts:3 | z | ainda não corrigido | sem tempo |\n"), tmp)
    ok(codigo == 1, "reprova", saida)
    ok("destino escrito por negação" in saida and "A-01" in saida and "A-03" in saida,
       "a negação é denunciada, não classificada", saida)
    ok("corrigido      1" in saida,
       "e não infla a conversão: só o A-02 conta como corrigido", saida)
    ok("A-02" not in saida.split("Destino de")[0],
       "o 'fechado' sem negação passa como corrigido", saida)

    # ----------------------------------------------------------------
    print("\nA coluna com alias só conta linha que parece achado")
    alias = ("| Item | Situação |\n| --- | --- |\n"
             "| **B8** — beco sem saída | fechado |\n"
             "| **Enforcement de escrita sem chave** | Nunca exercido |\n"
             "| **Baseline visual I8** | 126 dos 152 ignorados |\n")
    codigo, saida = rodar(alias, tmp)
    ok("Destino de 1 achados" in saida,
       "a linha com identificador entra e as outras duas não", saida)
    ok("2 linha(s) de tabela" in saida and "ignoradas" in saida,
       "e a ferramenta diz quantas ignorou, em vez de sumir com elas", saida)
    ok("sem destino declarado" not in saida,
       "dimensão não coberta não é achado sem destino", saida)

    print("\nMas a coluna com o nome canônico não perdoa ninguém")
    codigo, saida = rodar(
        "| Item | Destino |\n| --- | --- |\n"
        "| Enforcement de escrita sem chave | Nunca exercido |\n", tmp)
    ok("sem destino declarado" in saida,
       "sob 'Destino', toda linha é achado e precisa de um", saida)

    print("\nE uma tabela que não é de achados é ignorada")
    codigo, saida = rodar(
        "| Volta | Frentes | Duração |\n| --- | --- | --- |\n| 1 | seis | 12min |\n"
        "\n" + CABECALHO +
        "| A-01 | código | baixa | a.ts:10 | x | corrigido | commit local |\n", tmp)
    ok("Destino de 1 achados" in saida,
       "a tabela sem coluna Destino não entra na conta", saida)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de outcome.py: tudo verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
