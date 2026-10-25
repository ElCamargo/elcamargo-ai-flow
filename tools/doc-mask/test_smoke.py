#!/usr/bin/env python3
"""Fumaça do doc_mask: o filtro, a conferência e a colheita depois do 403."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import doc_mask as D  # noqa: E402

FERRAMENTA = AQUI / "doc_mask.py"
falhas: list[str] = []

# Documentos de exemplo, gerados só para o teste; nenhum é de pessoa.
CPF = "529.982" ".247-25"
CPF_CRU = "52998" "224725"
CNPJ = "11.222.33" "3/0001-81"
CNPJ_CRU = "1122233" "3000181"
CNPJ_ALFA = "12.ABC.34" "5/01DE-35"  # o exemplo da Receita para o alfanumérico


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)


def rodar(*args: str, entrada: str = "", env: dict | None = None) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(FERRAMENTA), *args], input=entrada,
                       capture_output=True, text=True, timeout=30, env=env)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    print("O dígito verificador")
    checar(D.cpf_valido(CPF) and D.cpf_valido(CPF_CRU), "CPF válido, com e sem formatação")
    checar(not D.cpf_valido("52998224724"), "CPF com o último dígito errado")
    checar(not D.cpf_valido("11111111111"), "CPF de dígito repetido não é CPF")
    checar(D.cnpj_valido(CNPJ) and D.cnpj_valido(CNPJ_CRU), "CNPJ válido, com e sem formatação")
    checar(D.cnpj_valido(CNPJ_ALFA), "CNPJ alfanumérico, pelo exemplo da Receita")
    checar(not D.cnpj_valido("11222333000182"), "CNPJ com o último dígito errado")

    print("\nO filtro troca o documento e deixa o resto")
    texto = (f"expect(cpf).toBe('{CPF_CRU}')  formatado {CPF}  cnpj {CNPJ_CRU}  alfa {CNPJ_ALFA}\n"
             "formatado sem dígito válido 123.456" ".789-00\n"
             "timestamp 1727712000123  telefone 11987654321  id 1234567890123456  hash ab12cd34ef56\n")
    rc, saida = rodar(entrada=texto)
    checar(rc == 0, "sai 0")
    for doc in (CPF, CPF_CRU, CNPJ_CRU, CNPJ_ALFA, "123.456" ".789-00"):
        checar(doc not in saida, f"{doc} some da saída")
    checar(saida.count("[CPF]") == 3 and saida.count("[CNPJ]") == 2, "cada um vira o seu marcador")
    for fica in ("1727712000123", "11987654321", "1234567890123456", "ab12cd34ef56"):
        checar(fica in saida, f"{fica} fica: não é documento")

    print("\nA conferência acusa sem repetir o número")
    pasta = Path(tempfile.mkdtemp(prefix="docmask-"))
    sujo, limpo = pasta / "relatorio.md", pasta / "limpo.md"
    sujo.write_text(f"# Relatório\n\nA spec usa o CPF {CPF} em dez arquivos.\n", encoding="utf-8")
    limpo.write_text("# Relatório\n\nA spec usa o [CPF] de `a.spec.ts:12`.\n", encoding="utf-8")
    rc, saida = rodar("conferir", str(sujo))
    checar(rc == 1 and "relatorio.md:3: CPF" in saida, "sai 1 e aponta arquivo e linha")
    checar(CPF not in saida and CPF_CRU not in saida, "a acusação não traz o número")
    rc, saida = rodar("conferir", str(limpo))
    checar(rc == 0, "relatório com marcador passa")

    print("\nDepois do 403: colher as devoluções, mascaradas, numa worktree")
    casa = Path(tempfile.mkdtemp(prefix="casa-"))
    worktree = pasta / "repo" / ".claude" / "worktrees" / "x"
    worktree.mkdir(parents=True)
    env = dict(os.environ, HOME=str(casa))
    base = casa / ".claude" / "projects" / D.raiz_de_transcritos(worktree).name / "sessao-1" / "subagents"
    checar("--claude-worktrees-x" in str(base), "a pasta da worktree leva `--claude`, como o Claude Code grava")
    base.mkdir(parents=True)

    def transcrito(nome: str, tipo: str, fala: str) -> None:
        linhas = [{"message": {"role": "user", "content": [{"type": "text", "text": f"prompt com {CPF}"}]}},
                  {"message": {"role": "assistant", "content": [{"type": "text", "text": fala}]}}]
        (base / f"agent-{nome}.jsonl").write_text("\n".join(json.dumps(l) for l in linhas), encoding="utf-8")
        (base / f"agent-{nome}.meta.json").write_text(json.dumps(
            {"agentType": f"elcamargo-ai-flow:{tipo}", "description": "1052 step 9 volta 2"}))

    transcrito("aaa111", "elcamargo-implemented-business-reviewer",
               f"Achado alta: o CPF {CPF} da fixture passa sem validação. " + "x" * 1200)
    transcrito("bbb222", "elcamargo-step-runner",
               "API Error: 403 Requisicao bloqueada pelo guardrail (authentication_failed)")
    saida_dir = pasta / "colhidas"
    rc, saida = rodar("devolucoes", "--raiz", str(worktree), "--saida", str(saida_dir), env=env)
    checar(rc == 0, "sai 0")
    checar("BLOQUEADA" in saida and "step-runner" in saida, "o orquestrador do 403 sai como BLOQUEADA")
    checar("entregou" in saida and "implemented-business" in saida, "a frente que entregou sai como entregou")
    colhida = (saida_dir / "aaa111.md").read_text(encoding="utf-8")
    checar("[CPF]" in colhida and CPF not in colhida, "a devolução colhida vem mascarada")
    checar("prompt com" not in colhida, "colhe a última fala do agente, não o prompt")
    checar("SendMessage" in saida, "diz que a bloqueada não se retoma")

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("tudo passou")
    return 0


if __name__ == "__main__":
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
