#!/usr/bin/env python3
"""Fumaca do guarda de arvore.

    python3 test_smoke.py

O caso que importa e' o que aconteceu: a arvore ja' chega SUJA da entrega do
step 8, e uma frente escreve por cima. Uma conferencia por codigo de `git
status` passaria dizendo que nada mudou -- a linha ` M src/env.ts` e' a mesma
antes e depois. Por isso cada caminho carrega o hash do conteudo.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).parent.resolve()
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent / "flow-state"))

import tree_guard as T  # noqa: E402

falhas: list[str] = []


def ok(condicao: bool, descricao: str, saida: str = "") -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)
        if saida:
            print("        " + saida.replace("\n", "\n        ")[:600])


def projeto() -> Path:
    raiz = Path(tempfile.mkdtemp(prefix="guarda-")).resolve()
    (raiz / ".agents" / "atividades").mkdir(parents=True)
    # `segundos_de_step_relampago = 0`: esta suite atravessa os steps em
    # milissegundos, e a guarda recusa entrar em portao humano com o step
    # anterior aberto ha segundos. E' o uso legitimo da chave -- quem roteiriza
    # o fluxo declara isso, em vez de o pacote desligar sozinho.
    (raiz / ".agents" / "config.toml").write_text(
        '[projeto]\nnome = "t"\n\n[fluxo]\nsegundos_de_step_relampago = 0\n')
    (raiz / ".gitignore").write_text(".agents/\n")
    (raiz / "src").mkdir()
    (raiz / "src" / "env.ts").write_text("if (cfg.secret) boot()\n")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, capture_output=True)
    return raiz


def rodar(raiz: Path, *args: str) -> tuple[int, str]:
    import contextlib, io  # noqa: E401
    anterior = Path.cwd()
    buf = io.StringIO()
    try:
        os.chdir(raiz)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            codigo = T.main(list(args))
    finally:
        os.chdir(anterior)
    return codigo, buf.getvalue()



def veredicto_da_arvore_chega_ao_portao() -> None:
    """O veredicto desta ferramenta CHEGA ao portao 10?

    Ate 11/09/2026 ela nao registrava nada: imprimia "A ARVORE MUDOU" e saia
    com codigo 1, e o `concluir` passava. A prova veio da base instalada -- em
    ~250 linhas de conferencia gravadas nas atividades reais dos dois
    repositorios, `arvore` aparecia ZERO vezes, enquanto `catraca` e `perfis`,
    que se registram sozinhas, somavam centenas.
    """
    print("\nRegressao: o veredicto da arvore tem que CHEGAR ao portao")
    fs = AQUI.parent / "flow-state" / "flow_state.py"
    guarda = AQUI / "tree_guard.py"

    def cena(mexer: bool, conferir: bool) -> tuple[int, str]:
        tmp = Path(tempfile.mkdtemp()).resolve()
        subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
        (tmp / ".agents" / "atividades").mkdir(parents=True)
        # Ver a nota da outra cena: fluxo roteirizado declara o `0`.
        (tmp / ".agents" / "config.toml").write_text(
            '[projeto]\nnome = "t"\n\n[fluxo]\n'
            'segundos_de_step_relampago = 0\n', encoding="utf-8")
        (tmp / "a.ts").write_text("const x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "b"], cwd=tmp, capture_output=True)

        def roda(exe, *a):
            return subprocess.run([sys.executable, str(exe), *a], cwd=tmp,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
        roda(fs, "iniciar", "T", "--titulo", "Rev", "--trilha", "revisao")
        roda(guarda, "marcar", "--id", "T")
        if mexer:
            (tmp / "a.ts").write_text("const x = 1  // mutante\n", encoding="utf-8")
        if conferir:
            roda(guarda, "conferir", "--id", "T")
        for _ in range(4):
            roda(fs, "avancar", "T", "--nota", "x")
        fim = roda(fs, "concluir", "T", "--nota", "publicada")
        corpo = (tmp / ".agents" / "atividades" / "T.md").read_text(encoding="utf-8")
        return fim.returncode, corpo

    c, corpo = cena(mexer=True, conferir=True)
    ok("| arvore | falhou |" in corpo, "arvore mexida grava `falhou` na atividade")
    ok(c != 0, "e o `concluir` SEGURA -- arvore suja nao e' achado sobre a "
               "entrega, e' contaminacao da propria revisao")

    c, corpo = cena(mexer=False, conferir=True)
    ok("| arvore | ok |" in corpo, "arvore limpa grava `ok`")
    ok(c == 0, "e o `concluir` passa")

    c, corpo = cena(mexer=False, conferir=False)
    ok("| arvore | exigida |" in corpo,
       "quem marcou e nunca conferiu deixa a divida escrita no `marcar`")
    ok(c != 0, "e o `concluir` segura: travamento no meio nao vira silencio")


def main() -> int:
    print("Conferir sem marca nao inventa uma linha de base")
    raiz = projeto()
    c, o = rodar(raiz, "conferir", "--id", "1")
    ok(c == 1 and "ANTES de disparar" in o,
       "recusa, e diz que a marca se cria antes do disparo", o)

    print("\nArvore intacta")
    c, o = rodar(raiz, "marcar", "--id", "1")
    ok(c == 0 and "marcada" in o, "marca", o)
    c, o = rodar(raiz, "conferir", "--id", "1")
    ok(c == 0 and "como antes" in o, "e confere limpa", o)
    ok("NÃO prova" in o, "declarando o que ela nao prova", o)

    print("\nO caso medido: arquivo NOVO que a frente deixou para tras")
    (raiz / "src" / ".qa-token.mjs").write_text("jwt")
    c, o = rodar(raiz, "conferir", "--id", "1")
    ok(c == 1 and "src/.qa-token.mjs" in o,
       "acusa o arquivo nao rastreado -- que nenhum diff mostraria", o)
    (raiz / "src" / ".qa-token.mjs").unlink()

    print("\nO caso REAL: mutante por cima de uma arvore que ja' estava suja")
    # A entrega do step 8 nao esta' commitada: `src/env.ts` ja' e' ` M`.
    (raiz / "src" / "env.ts").write_text("if (cfg.secret && extra) boot()\n")
    c, o = rodar(raiz, "marcar", "--id", "2")
    ok(c == 0, "marca com a arvore ja' suja", o)

    (raiz / "src" / "env.ts").write_text("if (false && cfg.secret && extra) boot()\n")
    c, o = rodar(raiz, "conferir", "--id", "2")
    ok(c == 1 and "MUDOU" in o and "src/env.ts" in o,
       "acusa o mutante mesmo com o codigo de status IGUAL antes e depois", o)
    # Sem o hash, ` M src/env.ts` seria identico nas duas marcas e isto passaria.
    ok(o.count("src/env.ts") == 1,
       "e o caminho aparece UMA vez, como mudanca, nao como par surgiu/sumiu", o)

    print("\nRestaurado volta a passar")
    (raiz / "src" / "env.ts").write_text("if (cfg.secret && extra) boot()\n")
    c, o = rodar(raiz, "conferir", "--id", "2")
    ok(c == 0, "a frente que restaura direito nao e' acusada", o)

    print("\nArquivo apagado durante a janela")
    (raiz / "src" / "env.ts").unlink()
    c, o = rodar(raiz, "conferir", "--id", "2")
    ok(c == 1 and "src/env.ts" in o, "tambem e' mudanca", o)

    import shutil
    shutil.rmtree(raiz, ignore_errors=True)

    veredicto_da_arvore_chega_ao_portao()

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Fumaca do guarda de arvore: tudo verde.")
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

