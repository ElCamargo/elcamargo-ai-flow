#!/usr/bin/env python3
"""Fumaça do detector de caso da trilha `revisao`.

Os três casos são montados em repositório de verdade, com commits de verdade,
porque o diagnóstico sai de `git diff` e de disco — não de um dicionário.

O defeito que originou a ferramenta: no primeiro uso real da trilha quem
descobriu o caso foi a PORTA, não o step 1. Funcionou, e a doutrina diz outra
coisa. "Se alguém entrar direto pelo step 1, ninguém descobre nada."
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FERRAMENTA = AQUI / "prior_work.py"

falhas: list[str] = []


def checar(cond: bool, descricao: str, detalhe: str = "") -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)
        if detalhe:
            print(f"          {detalhe.strip()[:400]}")


def g(raiz: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout.strip()


def repo(tmp: Path, nome: str) -> Path:
    raiz = tmp / nome
    raiz.mkdir()
    g(raiz, "init", "-q", "-b", "main")
    (raiz / ".agents").mkdir()
    (raiz / ".agents" / "config.toml").write_text("[docs]\nspecs = \"docs/specs\"\n",
                                                  encoding="utf-8")
    (raiz / "README.md").write_text("x\n", encoding="utf-8")
    g(raiz, "add", ".")
    g(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    g(raiz, "branch", "base-ref")
    return raiz


def commitar(raiz: Path, *caminhos: str) -> None:
    for c in caminhos:
        alvo = raiz / c
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("conteudo\n", encoding="utf-8")
    g(raiz, "add", "-A")
    g(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "entrega")


def rodar(raiz: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(FERRAMENTA), "--base", "base-ref",
                        *args], cwd=raiz, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t).resolve()

        print("\nCaso 1: o dev usou o fluxo")
        r1 = repo(tmp, "usou")
        commitar(r1, ".agents/atividades/1080.md", "src/a.ts")
        codigo, saida = rodar(r1)
        checar(codigo == 0, "responde 0", saida)
        checar("usou-o-fluxo" in saida, "detecta o arquivo de atividade na árvore", saida)
        checar("1080.md" in saida, "e nomeia qual", saida)
        checar("mais barato" in saida, "e diz que é o caso mais barato", saida)
        checar("estado de atividade antiga" in saida or "atividade antiga" in saida,
               "e avisa que a branch pode carregar estado que ninguém limpou", saida)

        print("\nCaso 2: especificou fora do fluxo")
        r2 = repo(tmp, "fora")
        commitar(r2, "docs/specs/CAM-032.md", "src/b.ts")
        codigo, saida = rodar(r2)
        checar("especificou-fora" in saida, "acha a spec na pasta que o config declara", saida)
        checar("CAM-032.md" in saida, "e nomeia o documento", saida)
        checar("OBJETO DE REVISÃO" in saida,
               "e diz que a SDD dele é objeto de revisão, não fonte da verdade", saida)

        print("\nCaso 3: não documentou nada")
        r3 = repo(tmp, "nada")
        commitar(r3, "src/c.ts", "src/d.ts")
        codigo, saida = rodar(r3)
        checar("nao-documentou" in saida, "sem documento, é o terceiro caso", saida)
        checar("achado, não obstáculo" in saida,
               "e a ausência é achado, não motivo para parar", saida)

        print("\nO README não faz de uma entrega `especificou-fora`")
        # Palpite largo -- todo .md -- classificaria errado toda entrega que
        # mexeu na documentação do projeto.
        r4 = repo(tmp, "readme")
        commitar(r4, "README.md", "src/e.ts")
        codigo, saida = rodar(r4)
        checar("nao-documentou" in saida,
               "mexer no README não conta como ter especificado", saida)

        print("\nSem `docs.specs` declarado, o palpite é estreito E declarado")
        r5 = repo(tmp, "sem-config")
        (r5 / ".agents" / "config.toml").write_text("[docs]\nspecs = \"\"\n",
                                                    encoding="utf-8")
        g(r5, "add", "-A")
        g(r5, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "cfg")
        commitar(r5, "documentacao/sdd-do-modulo.md", "src/f.ts")
        codigo, saida = rodar(r5)
        checar("especificou-fora" in saida,
               "o palpite acha `sdd` no caminho quando não há pasta declarada", saida)
        checar("não declarado" in saida and "palpite" in saida,
               "e o aviso diz que caiu no palpite, em vez de fingir certeza", saida)

        print("\nO JSON serve para o step 1 registrar sem reformatar")
        codigo, saida = rodar(r1, "--json")
        checar('"caso": "usou-o-fluxo"' in saida, "sai como JSON", saida)

        print("\nBase errada não vira veredicto")
        codigo, saida = rodar(r1, "--base", "nao-existe")
        checar(codigo == 1, "recusa quando a base não existe", saida)
        checar("erro:" in saida, "e diz que foi erro, em vez de responder um caso", saida)

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Fumaca do detector de caso: tudo verde.")
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
