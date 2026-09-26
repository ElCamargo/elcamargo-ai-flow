#!/usr/bin/env python3
"""Fumaça de citations.py — os dois sentidos, porque só um não prova nada.

Uma ferramenta de conferência que nunca acusa é inútil, e uma que acusa demais é
pior: ensina a ignorá-la, e na vez em que ela estiver certa ninguém olha. Cada
verificação aqui tem um caso que ela DEVE pegar e um que ela NÃO PODE pegar.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citations as C  # noqa: E402

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


def rodar(fn, **kw) -> tuple[int, str]:
    C._INDICE.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = fn(Args(**kw))
    return codigo, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="citacoes-"))
    subprocess.run(["git", "init", "-q", str(tmp)], check=True)

    (tmp / "src").mkdir()
    alvo = tmp / "src" / "componente.ts"
    alvo.write_text(
        "// linha 1\n"
        "const LARGURA = 176;\n"
        "// linha 3\n"
        "const painel = 'min-w-44';\n"
        "// linha 5\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp), "add", "-A"], check=True,
                   capture_output=True)

    print("Citação de código")
    doc = tmp / "spec.md"
    doc.write_text(
        "Ver `src/componente.ts:2`, que declara \"const LARGURA = 176\".\n"
        "E `componente.ts:4` traz \"const painel\".\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 0, "citação certa, com trecho que confere, passa", saida)
    ok("2 de código, 2 com arquivo e linha válidos" in saida,
       "e o nome solto resolve pelo índice do git", saida)

    print("\nO que ela DEVE pegar")
    doc.write_text("Ver `src/inexistente.ts:2`.\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 1 and "arquivo não existe" in saida,
       "arquivo que não existe é acusado", saida)

    doc.write_text("Ver `src/componente.ts:99`.\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 1 and "5 linhas" in saida,
       "linha além do fim do arquivo é acusada, com o tamanho real", saida)

    doc.write_text(
        "Ver `src/componente.ts:2`, que declara \"const ALTURA = 200\".\n",
        encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 1 and "não está na linha citada" in saida,
       "trecho que não aparece na linha citada é acusado", saida)

    print("\nO que ela NÃO PODE pegar")
    # Aspas de ênfase do autor, longe da citação. Numa spec real isto produziu
    # falso positivo: a frase entre aspas era do autor, não do arquivo.
    doc.write_text(
        "Ver `src/componente.ts:2`. O painel cresce com o conteúdo e nunca "
        "encolhe abaixo do mínimo declarado pelo design system, e por isso "
        "este é o precedente de \"não fixar largura\" que faltava.\n",
        encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 0, "aspa de ênfase do autor, longe da citação, não vira achado",
       saida)

    # Aspa que pertence a OUTRA citação na mesma linha.
    doc.write_text(
        "O teste `src/componente.ts:2` declara duas coisas, e o mapa de traços "
        "de `src/componente.ts:4` diz \"const painel\".\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 0, "aspa que pertence à citação seguinte não é cobrada da primeira",
       saida)

    # Citação de seção de documento, que não é arquivo:linha.
    doc.write_text("Ver `IAM-008:42` e `CAM-001:168`.\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                          estrito=False)
    ok(codigo == 0 and "0 de código" in saida,
       "citação de seção de spec não é lida como arquivo", saida)

    print("\nA verificação de número foi derrubada, e o registro fica")
    fonte = (Path(__file__).resolve().parent / "citations.py").read_text(encoding="utf-8")
    ok(not hasattr(C, "cmd_numeros"),
       "o comando `numeros` não existe — duas tentativas, as duas inundaram")
    ok("29 conflitos, todos legítimos" in fonte and "34 achados em 38" in fonte,
       "e o arquivo registra os dois caminhos que não funcionam, com os números")

    print("\nA saída declara o próprio limite")
    doc.write_text("Ver `src/componente.ts:2`.\n", encoding="utf-8")
    _, saida = rodar(C.cmd_codigo, documento=str(doc), raiz=str(tmp),
                     estrito=False)
    ok("NÃO prova" in saida,
       "a conferência de citação diz o que ela não prova", saida)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S)")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("tudo passou")
    return 0


if __name__ == "__main__":
    sys.exit(main())
