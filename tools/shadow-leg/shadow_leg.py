#!/usr/bin/env python3
"""A perna sombra do step 9: uma frente, dois modelos, a mesma chamada.

O desenho existe desde 04/09/2026 (ver `references/shadow-leg.md`) e
nunca foi ligado: a política de modelo dizia "só desce com a comparação", e a
comparação não tinha quem a fizesse. Medido de 29 a 30/09/2026, as frentes do
step 9 somam mais de 30% do custo dos dois projetos, todas em Opus.

    shadow_leg.py escolher --registro <jsonl> --frentes code,security,quality
    shadow_leg.py comparar --registro <jsonl> --atividade <id> --frente code \\
        --principal code-principal.md --sombra code-sombra.md [--saida cmp.md]
    shadow_leg.py resumo --registro <jsonl>

`escolher` faz o rodízio: das frentes que rodam nesta volta, a que tem menos
pares no registro. `comparar` lê as duas tabelas de achados, casa um achado com
o outro pela âncora `arquivo:linha`, e nomeia em destaque todo `bloqueia` que
só uma perna viu — é o veto do critério. `resumo` aplica o critério
pré-registrado sobre todos os pares de cada frente.

**O que ela não prova.** Casar por âncora é aproximação: dois achados sobre a
mesma linha podem ser defeitos diferentes, e o mesmo defeito pode ser ancorado
em linhas diferentes. Achado sem âncora não casa com nada e vai à lista de
conferir à mão. E o gabarito é o relatório bruto da perna principal, antes da
consolidação: um achado que a consolidação derrubaria ainda conta.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SEVERIDADES = ("bloqueia", "alta", "baixa")
ANCORA = re.compile(r"([A-Za-z0-9_@()\[\]./-]+\.[A-Za-z0-9]{1,6}):(\d+)")
FOLGA = 5          # linhas de distância que ainda contam como o mesmo lugar
N_MINIMO = 5       # pares de uma frente antes de o resumo dizer qualquer coisa
ADOTA, REJEITA = 0.80, 0.60


def achados(texto: str) -> list[dict]:
    """As linhas de tabela que declaram severidade, com as âncoras delas."""
    saida = []
    for linha in texto.splitlines():
        s = linha.strip()
        if not s.startswith("|") or set(s) <= set("|-: "):
            continue
        celulas = [c.strip().strip("*`").lower() for c in s.strip("|").split("|")]
        sev = next((v for c in celulas for v in SEVERIDADES
                    if c == v or c.startswith(v + " ") or c.startswith(v + "·")), None)
        if not sev:
            continue
        ancoras = [(a, int(n)) for a, n in ANCORA.findall(s)]
        saida.append({"severidade": sev, "ancoras": ancoras,
                      "texto": re.sub(r"\s+", " ", s)[:220]})
    return saida


def _mesmo_lugar(a: list, b: list) -> bool:
    for arq_a, l_a in a:
        for arq_b, l_b in b:
            if (arq_a == arq_b or arq_a.endswith("/" + arq_b) or arq_b.endswith("/" + arq_a)) \
                    and abs(l_a - l_b) <= FOLGA:
                return True
    return False


def casar(principal: list[dict], sombra: list[dict]) -> dict:
    usados = set()
    pares, so_principal = [], []
    for p in principal:
        par = None
        if p["ancoras"]:
            for i, s in enumerate(sombra):
                if i not in usados and s["ancoras"] and _mesmo_lugar(p["ancoras"], s["ancoras"]):
                    par = i
                    break
        if par is None:
            so_principal.append(p)
        else:
            usados.add(par)
            pares.append((p, sombra[par]))
    so_sombra = [s for i, s in enumerate(sombra) if i not in usados]
    return {"pares": pares, "so_principal": so_principal, "so_sombra": so_sombra}


def _conta(lista: list[dict]) -> dict:
    return {s: sum(1 for a in lista if a["severidade"] == s) for s in SEVERIDADES}


def cmd_escolher(args) -> int:
    frentes = [f.strip() for f in args.frentes.split(",") if f.strip()]
    if not frentes:
        print("nenhuma frente roda nesta volta: sem perna sombra", file=sys.stderr)
        return 2
    feitos = {f: 0 for f in frentes}
    for r in _ler(args.registro):
        if r.get("frente") in feitos:
            feitos[r["frente"]] += 1
    print(min(frentes, key=lambda f: (feitos[f], frentes.index(f))))
    return 0


def cmd_comparar(args) -> int:
    p = achados(Path(args.principal).read_text(encoding="utf-8", errors="replace"))
    s = achados(Path(args.sombra).read_text(encoding="utf-8", errors="replace"))
    c = casar(p, s)
    graves_p = [a for a in p if a["severidade"] in ("bloqueia", "alta")]
    graves_casados = [a for a, _ in c["pares"] if a["severidade"] in ("bloqueia", "alta")]
    veto_p = [a for a in c["so_principal"] if a["severidade"] == "bloqueia"]
    veto_s = [a for a in c["so_sombra"] if a["severidade"] == "bloqueia"]
    sev_bate = sum(1 for a, b in c["pares"] if a["severidade"] == b["severidade"])
    rebaixados = [a for a, b in c["pares"] if a["severidade"] == "bloqueia" != b["severidade"]]
    m_p, m_s = args.modelo_principal, args.modelo_sombra

    o = [f"# Perna sombra · {args.atividade} · {args.frente}", "",
         f"Principal (`{m_p}`): {len(p)} achados {_conta(p)}. "
         f"Sombra (`{m_s}`): {len(s)} achados {_conta(s)}.", ""]
    if not p and not s:
        o.append("Nenhuma das duas trouxe tabela de achados com severidade. "
                 "Confira os dois relatórios à mão: o par não entra no registro.")
    else:
        o += [f"- **as duas viram:** {len(c['pares'])}, e a severidade bateu em {sev_bate}",
              f"- **`bloqueia`+`alta` da principal que a sombra também viu:** "
              f"{len(graves_casados)} de {len(graves_p)}",
              f"- **`bloqueia` da principal que a sombra viu mais brando:** {len(rebaixados)}",
              f"- **só a principal viu:** {len(c['so_principal'])}",
              f"- **só a sombra viu:** {len(c['so_sombra'])}: conta a favor dela se "
              "se confirmar no código, e só uma pessoa decide isso", ""]
        if veto_p or veto_s:
            o.append("## VETO: `bloqueia` que só uma perna viu")
            o.append("")
            for a in veto_p:
                o.append(f"- só a principal (`{m_p}`): {a['texto']}")
            for a in veto_s:
                o.append(f"- só a sombra (`{m_s}`): {a['texto']}")
            o.append("")
        sem = [a for a in c["so_principal"] + c["so_sombra"] if not a["ancoras"]]
        if sem:
            o.append(f"## Sem âncora `arquivo:linha`: {len(sem)}, conferir à mão")
            o += [f"- {a['texto']}" for a in sem] + [""]
    texto = "\n".join(o)
    if args.saida:
        Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(texto + "\n", encoding="utf-8")
    print(texto)

    if p or s:
        reg = Path(args.registro)
        reg.parent.mkdir(parents=True, exist_ok=True)
        with reg.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "quando": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "atividade": args.atividade, "frente": args.frente,
                "principal": m_p, "sombra": m_s,
                "achados_principal": _conta(p), "achados_sombra": _conta(s),
                "graves_principal": len(graves_p), "graves_vistos_pela_sombra": len(graves_casados),
                "so_sombra": len(c["so_sombra"]), "rebaixados": len(rebaixados),
                "veto_principal": len(veto_p),
                "veto_sombra": len(veto_s)}, ensure_ascii=False) + "\n")
    return 0


def _ler(caminho: str) -> list[dict]:
    p = Path(caminho)
    if not p.exists():
        return []
    saida = []
    for linha in p.read_text(encoding="utf-8").splitlines():
        try:
            saida.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return saida


def vereditos(registros: list[dict]) -> dict[tuple[str, str], dict]:
    """O critério pré-registrado, por `(frente, modelo da sombra)`.

    Separado do `resumo` porque tem um segundo leitor: o `flow_state`, que só
    deixa valer `[revisao.modelo]` numa frente quando este veredito é `adota`.
    Dois lugares com o critério escrito divergiriam em silêncio.
    """
    por: dict[tuple[str, str], list[dict]] = {}
    for r in registros:
        por.setdefault((r["frente"], r.get("sombra", "?")), []).append(r)
    saida = {}
    for chave, rs in sorted(por.items()):
        graves = sum(r["graves_principal"] for r in rs)
        vistos = sum(r["graves_vistos_pela_sombra"] for r in rs)
        veto = sum(r["veto_principal"] for r in rs)
        recall = vistos / graves if graves else None
        if veto:
            veredito, adota = "REJEITA: a sombra perdeu `bloqueia`", False
        elif len(rs) < N_MINIMO or recall is None:
            veredito, adota = f"sem veredito: menos de {N_MINIMO} pares, ou nenhum grave", False
        elif recall >= ADOTA:
            veredito, adota = "adota (falso positivo ainda à mão)", True
        elif recall < REJEITA:
            veredito, adota = "rejeita", False
        else:
            veredito, adota = "inconclusivo: não adota", False
        saida[chave] = {"pares": len(rs), "recall": recall, "veto": veto,
                        "veredito": veredito, "adota": adota}
    return saida


def cmd_resumo(args) -> int:
    registros = _ler(args.registro)
    if not registros:
        print("nenhum par registrado ainda.")
        return 0
    print(f"{'frente':32s} {'sombra':8s} {'pares':>5s} {'recall':>7s} {'veto':>5s}  veredito")
    for (frente, modelo), v in vereditos(registros).items():
        rec = f"{100 * v['recall']:5.0f}%" if v["recall"] is not None else "    —"
        print(f"{frente:32s} {modelo:8s} {v['pares']:5d} {rec:>7s} {v['veto']:5d}  {v['veredito']}")
    print("\nCritério pré-registrado: recall de `bloqueia`+`alta` >= 80% adota, < 60% "
          "rejeita, entre é inconclusivo e não adota. Um único `bloqueia` perdido reprova. "
          "Falso positivo (o que só a sombra viu e não se sustenta) é contado pela pessoa, "
          "no portão 10.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="acao", required=True)
    e = sub.add_parser("escolher", help="a frente da vez, pelo rodízio")
    e.add_argument("--registro", required=True)
    e.add_argument("--frentes", required=True, help="as que rodam nesta volta, separadas por vírgula")
    c = sub.add_parser("comparar", help="casa os achados das duas pernas e registra o par")
    c.add_argument("--registro", required=True)
    c.add_argument("--atividade", required=True)
    c.add_argument("--frente", required=True)
    c.add_argument("--principal", required=True)
    c.add_argument("--sombra", required=True)
    c.add_argument("--modelo-principal", default="herdado")
    c.add_argument("--modelo-sombra", default="sonnet")
    c.add_argument("--saida")
    r = sub.add_parser("resumo", help="o critério sobre todos os pares")
    r.add_argument("--registro", required=True)
    args = p.parse_args(argv)
    return {"escolher": cmd_escolher, "comparar": cmd_comparar, "resumo": cmd_resumo}[args.acao](args)


if __name__ == "__main__":
    # Windows: com a saída em pipe, `print` usa cp1252. Ver `references/windows.md`.
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
