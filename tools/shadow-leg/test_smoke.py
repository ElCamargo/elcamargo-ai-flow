#!/usr/bin/env python3
"""Smoke da perna sombra: rodízio, casamento por âncora, veto e critério."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FERRAMENTA = AQUI / "shadow_leg.py"
sys.path.insert(0, str(AQUI))
import shadow_leg as S  # noqa: E402

falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)


def rodar(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(FERRAMENTA), *args],
                       capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout + r.stderr


PRINCIPAL = """
| Achado | Arquivo:linha | Severidade |
| --- | --- | --- |
| rota sem guard de tenant | `src/api/pedido.controller.ts:42` | bloqueia |
| DTO aceita campo extra | src/api/dto/pedido.dto.ts:17 | alta · leitura |
| nome de variável | src/api/util.ts:3 | baixa |
| teste sem asserção | sem lugar fixo | alta |
"""
SOMBRA = """
| Achado | Arquivo:linha | Severidade |
| --- | --- | --- |
| falta guard | api/pedido.controller.ts:45 | alta |
| índice ausente na migration | db/migrations/0042.sql:9 | bloqueia |
"""


def main() -> int:
    print("Ler a tabela de achados")
    a = S.achados(PRINCIPAL)
    checar(len(a) == 4, "quatro linhas com severidade, cabeçalho e separador de fora")
    checar(a[1]["severidade"] == "alta", "`alta · leitura` conta como alta")
    checar(a[0]["ancoras"] == [("src/api/pedido.controller.ts", 42)], "âncora sai da crase")
    checar(a[3]["ancoras"] == [], "achado sem lugar fica sem âncora")

    print("\nCasar por lugar")
    c = S.casar(a, S.achados(SOMBRA))
    checar(len(c["pares"]) == 1, "o mesmo arquivo, sufixo de caminho e 3 linhas de distância casam")
    checar(c["pares"][0][1]["severidade"] == "alta", "e a severidade diferente fica registrada no par")
    checar(len(c["so_principal"]) == 3 and len(c["so_sombra"]) == 1, "o resto fica de cada lado")

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        reg = t / "perna-sombra.jsonl"
        (t / "p.md").write_text(PRINCIPAL, encoding="utf-8")
        (t / "s.md").write_text(SOMBRA, encoding="utf-8")

        print("\nRodízio")
        rc, out = rodar("escolher", "--registro", str(reg), "--frentes", "code,security")
        checar(rc == 0 and out.strip() == "code", "registro vazio: a primeira da lista")

        print("\nComparar")
        rc, out = rodar("comparar", "--registro", str(reg), "--atividade", "1052",
                        "--frente", "code", "--principal", str(t / "p.md"),
                        "--sombra", str(t / "s.md"), "--saida", str(t / "cmp.md"))
        checar(rc == 0, "sai 0: é medida, não portão")
        checar("VETO" in out and "só a principal" in out and "só a sombra" in out,
               "`bloqueia` de uma perna só vai ao veto, dos dois lados")
        checar("1 de 3" in out, "um dos três graves da principal a sombra também viu")
        checar("Sem âncora" in out, "o achado sem lugar vai para conferir à mão")
        checar((t / "cmp.md").exists(), "a comparação fica gravada")
        r = [json.loads(l) for l in reg.read_text().splitlines()]
        checar(len(r) == 1 and r[0]["veto_principal"] == 0 and r[0]["veto_sombra"] == 1,
               "o par entra no registro; o `bloqueia` que a sombra viu como `alta` não é veto")
        checar(r[0]["rebaixados"] == 1 and "mais brando:** 1" in out, "mas conta como rebaixado")

        rc, out = rodar("escolher", "--registro", str(reg), "--frentes", "code,security")
        checar(out.strip() == "security", "com um par de `code`, a vez é da `security`")

        (t / "vazio.md").write_text("não rodou", encoding="utf-8")
        rodar("comparar", "--registro", str(reg), "--atividade", "x", "--frente", "security",
              "--principal", str(t / "vazio.md"), "--sombra", str(t / "vazio.md"))
        checar(len(reg.read_text().splitlines()) == 1, "par sem tabela nenhuma não entra no registro")

        print("\nCritério")
        reg1 = t / "r1.jsonl"
        reg1.write_text(json.dumps({"frente": "code", "sombra": "sonnet", "graves_principal": 3,
                                    "graves_vistos_pela_sombra": 3, "veto_principal": 1}) + "\n")
        rc, out = rodar("resumo", "--registro", str(reg1))
        checar("REJEITA" in out, "um `bloqueia` perdido pela sombra reprova, com n = 1")
        linhas = [json.dumps({"frente": "security", "sombra": "sonnet", "graves_principal": 2,
                              "graves_vistos_pela_sombra": 2, "veto_principal": 0})] * 4
        reg2 = t / "r2.jsonl"
        reg2.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        rc, out = rodar("resumo", "--registro", str(reg2))
        checar("sem veredito" in out, "quatro pares perfeitos ainda não decidem")
        reg2.write_text("\n".join(linhas * 2) + "\n", encoding="utf-8")
        rc, out = rodar("resumo", "--registro", str(reg2))
        checar("adota" in out, "com oito e recall de 100%, adota")

    print()
    if falhas:
        print(f"{len(falhas)} falha(s).")
        return 1
    print("perna sombra: tudo certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
