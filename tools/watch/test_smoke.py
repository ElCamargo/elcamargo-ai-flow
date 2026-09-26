#!/usr/bin/env python3
"""Fumaça do vigia — nos dois sentidos.

Ferramenta de vigilância que acusa demais é pior que nenhuma: a primeira versão
marcou como TRAVADO trinta e um agentes que haviam entregado dias antes, mais os
comandos em background, que nem agentes são.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch as V  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


def escrever(pasta: Path, nome: str, linhas: list[dict], idade_s: float) -> Path:
    p = pasta / f"{nome}.output"
    p.write_text("\n".join(json.dumps(l) for l in linhas), encoding="utf-8")
    quando = time.time() - idade_s
    os.utime(p, (quando, quando))
    return p


def pedido(texto: str) -> dict:
    return {"agentId": "x", "isSidechain": True, "type": "user",
            "message": {"role": "user", "content": texto}}


def entregou() -> dict:
    return {"agentId": "x", "type": "assistant",
            "message": {"role": "assistant", "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "pronto"}]}}


def no_meio() -> dict:
    return {"agentId": "x", "type": "assistant",
            "message": {"role": "assistant", "stop_reason": None,
                        "content": [{"type": "text", "text": "pensando"}]}}


def rodar(pasta: Path, **kw) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = V.imprimir(V.olhar(pasta, **kw), pasta)
    return codigo, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="vigia-"))

    print("O que ela DEVE pegar")
    escrever(tmp, "travado", [pedido("Frente de segurança"), no_meio()],
             idade_s=40 * 60)
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "TRAVADO" in saida, "agente parado há 40min é acusado", saida)
    ok("Frente de segurança" in saida,
       "e a descrição vem do pedido, para saber qual era", saida)

    print("\nO que ela NÃO PODE pegar")
    escrever(tmp, "entregue", [pedido("Frente de código"), entregou()],
             idade_s=50 * 3600)
    codigo, saida = rodar(tmp)
    ok("Frente de código" not in saida,
       "agente que entregou não é travado, por mais velho que seja", saida)

    escrever(tmp, "trabalhando", [pedido("Frente de qualidade"), no_meio()],
             idade_s=30)
    codigo, saida = rodar(tmp)
    ok("trabalhando" in saida, "agente que escreveu agora está trabalhando", saida)

    (tmp / "bash.output").write_text("saida solta de comando\n", encoding="utf-8")
    os.utime(tmp / "bash.output", (time.time() - 9 * 3600,) * 2)
    codigo, saida = rodar(tmp)
    ok("bash" not in saida,
       "saída de comando em background não é julgada como agente", saida)

    escrever(tmp, "antigo", [pedido("Frente de ontem"), no_meio()],
             idade_s=9 * 3600)
    codigo, saida = rodar(tmp)
    ok("Frente de ontem" not in saida,
       "agente parado há nove horas é história, não problema vivo", saida)
    codigo, saida = rodar(tmp, alvos={"antigo"})
    ok("Frente de ontem" in saida,
       "mas aparece quando alguém pergunta por ele explicitamente", saida)

    print("\nTurno fechado ha pouco nao e' o mesmo que trabalho acabado")
    # Deu falso negativo de verdade: o vigia deu por concluida uma frente que
    # estava editando arquivo naquele instante. `end_turn` diz que o turno
    # fechou, nao que o agente acabou.
    escrever(tmp, "acabou-agora", [pedido("Frente que fechou turno"), entregou()],
             idade_s=20)
    codigo, saida = rodar(tmp)
    ok("Frente que fechou turno" in saida and "trabalhando" in saida,
       "quem fechou turno ha 20s ainda aparece, como trabalhando", saida)

    escrever(tmp, "acabou-mesmo", [pedido("Frente que entregou"), entregou()],
             idade_s=10 * 60)
    codigo, saida = rodar(tmp)
    ok("Frente que entregou" not in saida,
       "e quem fechou turno ha dez minutos sai da lista", saida)

    print("\nA saída declara os próprios limites")
    codigo, saida = rodar(tmp)
    ok("NÃO prova" in saida, "diz que não prova utilidade, só vida", saida)
    ok("NÃO distingue" in saida,
       "e que não distingue travado de morto por interrupção", saida)

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
