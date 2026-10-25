#!/usr/bin/env python3
"""Fumaça do guarda de disparo — e o caso que importa é o SÓSIA.

Duas frentes paradas há o mesmo tempo, uma travada e uma saudável: se o teste
não tiver as duas, ele aceita um guarda que só olha o relógio — que é
exatamente a heurística que mata frente viva.
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

sys.path.insert(0, str(Path(__file__).parent))
import dispatch_guard as G  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


def turno_de_disparo(bg, o_que: str) -> str:
    return json.dumps({"timestamp": "2026-09-18T13:55:15.000Z", "message": {"content": [
        {"type": "tool_use", "name": "Agent",
         "input": {"run_in_background": bg, "description": o_que}}]}})


def turno_de_texto(t: str) -> str:
    return json.dumps({"timestamp": "2026-09-18T13:50:00.000Z",
                       "message": {"content": [{"type": "text", "text": t}]}})


def montar(projeto: Path, frentes: dict[str, list[str]], parado_s: int) -> None:
    base = G.raiz_de_transcritos(projeto) / "sessao-de-teste" / "subagents"
    base.mkdir(parents=True, exist_ok=True)
    quando = time.time() - parado_s
    for nome, turnos in frentes.items():
        alvo = base / f"agent-{nome}.jsonl"
        alvo.write_text("\n".join(turnos) + "\n", encoding="utf-8")
        os.utime(alvo, (quando, quando))


def veredictos(projeto: Path) -> dict[str, str]:
    return {f["frente"]: f["veredicto"] for f in G.auditar(projeto, minutos=120)}


def main() -> int:
    casa = Path(tempfile.mkdtemp(prefix="disparo-"))
    projeto = casa / "projeto-de-mentira"
    projeto.mkdir()
    # O guarda lê de ~/.claude/projects; aponto HOME para a casa de teste.
    os.environ["HOME"] = str(casa)

    print("O sósia: mesmo relógio, veredictos opostos")
    montar(projeto, {
        "atravada00": [turno_de_texto("disparei"), turno_de_disparo(True, "Frente code")],
        "asaudavel0": [turno_de_texto("disparei"), turno_de_disparo(False, "Frente code")],
    }, parado_s=338)
    v = veredictos(projeto)
    ok(v.get("atravada0") == "TRAVADA" or v.get("atravada00") == "TRAVADA",
       "último disparo em segundo plano → TRAVADA", str(v))
    ok("esperando" in str(v.get("asaudavel") or v.get("asaudavel0") or ""),
       "último disparo bloqueante → esperando, e NÃO travada", str(v))
    ok(len({k: x for k, x in v.items()}) == 2 and len(set(v.values())) == 2,
       "as duas paradas há 338s recebem veredictos DIFERENTES", str(v))

    print("\nO SEGUNDO sósia: mesmo relógio, ambas em segundo plano, veredictos opostos")
    # Sem este caso a ferramenta reprova quem ENTREGOU: um agente que terminou
    # também para de crescer, e dispara-e-segue é final legítimo.
    montar(projeto, {
        "aentregou0": [turno_de_disparo(True, "Consulta lateral"),
                       turno_de_texto("Step 1 concluído. " + "relatório " * 200)],
        "apresa0000": [turno_de_disparo(True, "Frente quality"),
                       turno_de_texto("Quality is still running. Let me wait for it.")],
    }, parado_s=400)
    v = veredictos(projeto)
    ok(any("entregou" in x for k, x in v.items() if k.startswith("aentregou")),
       "última fala de milhares de caracteres → entregou, NÃO travada", str(v))
    ok(any(x == "TRAVADA" for k, x in v.items() if k.startswith("apresa")),
       "última fala curta de espera, em segundo plano → TRAVADA", str(v))

    montar(projeto, {"amorta00000": [turno_de_disparo(True, "Frente code"),
                                     turno_de_texto("[Request interrupted by user for tool use]")]},
           parado_s=400)
    v = veredictos(projeto)
    ok(any(x == "interrompida" for k, x in v.items() if k.startswith("amorta")),
       "agente morto pelo usuário não é acusado de travado", str(v))

    print("\nA devolução pela ferramenta `SubagentHandback` conta como fala")
    # 11 de 198 subagentes devolveram assim em três dias de setembro de 2026.
    # Lida só como texto, a entrega dela parece espera e vira TRAVADA.
    handback = json.dumps({"timestamp": "2026-09-30T13:50:00.000Z", "message": {"content": [
        {"type": "tool_use", "name": "SubagentHandback",
         "input": {"message": "Frente concluída. " + "achado " * 300}}]}})
    montar(projeto, {"ahandback0": [turno_de_disparo(True, "Consulta"),
                                    turno_de_texto("vou devolver"), handback]},
           parado_s=400)
    v = veredictos(projeto)
    ok(any("entregou" in x for k, x in v.items() if k.startswith("ahandback")),
       "entrega longa por `SubagentHandback` → entregou, NÃO travada", str(v))

    print("\nO que ela DEVE pegar")
    montar(projeto, {"aomitido00": [turno_de_disparo(None, "Frente sem o parâmetro")]},
           parado_s=400)
    v = veredictos(projeto)
    ok(any(x == "TRAVADA" for k, x in v.items() if k.startswith("aomitido")),
       "omitir o parâmetro conta como segundo plano — o padrão é assíncrono", str(v))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = G.main(["--raiz", str(projeto)])
    ok(codigo == 1, "sai 1 quando há frente travada", buf.getvalue())
    ok("NÃO separa travada de saudável" in buf.getvalue(),
       "e a saída diz por que o relógio não serve", buf.getvalue())

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        G.main(["--raiz", str(projeto)])
    ok("CONFIRA O CONTEÚDO, NÃO A PROCEDÊNCIA" in buf.getvalue(),
       "quem entregou sem o retorno leva o aviso, com o que conferir", buf.getvalue())
    ok("sem o retorno de 1 subfrente" in buf.getvalue(),
       "e o aviso diz de QUANTAS subfrentes", buf.getvalue())

    print("\nO que ela NÃO PODE pegar")
    montar(projeto, {"arecente00": [turno_de_disparo(True, "Acabei de disparar")]},
           parado_s=10)
    v = veredictos(projeto)
    ok(any("cedo demais" in x for k, x in v.items() if k.startswith("arecente")),
       "frente recém-disparada não é acusada — não deu tempo de escrever", str(v))

    montar(projeto, {"afolha0000": [turno_de_texto("só li arquivos")]}, parado_s=900)
    v = veredictos(projeto)
    ok(any(x == "sem disparo" for k, x in v.items() if k.startswith("afolha")),
       "frente que nunca disparou subagente não é diagnosticada", str(v))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = G.main(["--raiz", str(casa / "nao-existe")])
    ok(codigo == 0 and "nenhuma frente" in buf.getvalue(),
       "projeto sem transcrito nenhum sai 0 e diz isso", buf.getvalue())

    print("\nO relatório declara a base de tempo")
    montar(projeto, {"abase00000": [turno_de_disparo(False, "Frente")]}, parado_s=400)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        G.main(["--raiz", str(projeto)])
    ok("UTC" in buf.getvalue(),
       "as horas dos disparos saem rotuladas UTC — o transcrito é UTC e o "
       "relógio de quem lê pode não ser", buf.getvalue()[:300])

    print("\nEla lê FORMA, nunca conteúdo")
    segredo = "CONTRATO-SIGILOSO-COM-O-CLIENTE " * 60
    montar(projeto, {"asigilo0000": [turno_de_disparo(False, "Frente"),
                                     turno_de_texto(segredo)]}, parado_s=400)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        G.main(["--raiz", str(projeto)])
    ok("CONTRATO-SIGILOSO" not in buf.getvalue(),
       "o texto da última fala NUNCA sai no relatório — só o tamanho dela",
       buf.getvalue()[:200])
    bruto = json.dumps(G.auditar(projeto, minutos=120), ensure_ascii=False)
    ok("CONTRATO-SIGILOSO" not in bruto,
       "nem no JSON, que é o que alguém automatiza em volta", bruto[:200])

    print("\nEla acha a worktree, onde os times rodam")
    # O nome esperado está escrito à mão, e não saído de `raiz_de_transcritos`:
    # montar pela própria função é o que deixou o defeito passar até a 2.52.0.
    worktree = projeto / ".claude" / "worktrees" / "x"
    worktree.mkdir(parents=True)
    nome = G.raiz_de_transcritos(worktree).name
    ok(nome.endswith("-projeto-de-mentira--claude-worktrees-x"),
       "`.claude/worktrees/x` vira `--claude-worktrees-x`, como o Claude Code grava", nome)
    montar(worktree, {"aworktree0": [turno_de_disparo(True, "Frente"), turno_de_texto("ok")]},
           parado_s=400)
    ok("aworktree" in veredictos(worktree), "e a frente de dentro dela aparece",
       str(veredictos(worktree)))

    print("\n" + ("tudo passou" if not falhas else f"{len(falhas)} FALHA(S)"))
    return 1 if falhas else 0


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
