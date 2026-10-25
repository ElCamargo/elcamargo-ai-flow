#!/usr/bin/env python3
"""Tira CPF e CNPJ do caminho antes que eles entrem num contexto.

Medido em 30/09/2026, na sessão `acme-backoffice-90`: a frente de
negócio implementado escreveu por extenso, no relatório, o CPF de teste das
specs, que tem dígitos verificadores válidos. Quando as devoluções chegaram ao
orquestrador, TODA chamada dele passou a voltar com *"403 Requisicao bloqueada
pelo guardrail"*, e retomar pelo `SendMessage` não resolveu. Só saiu com um
orquestrador novo, sobre as devoluções mascaradas.

    comando 2>&1 | doc_mask.py            filtra: troca o documento por [CPF]/[CNPJ]
    doc_mask.py conferir <arquivo>...     sai 1 se algum arquivo tem documento
    doc_mask.py devolucoes                depois do 403: colhe, mascaradas, as
                                          últimas falas dos subagentes do projeto

**O que conta como documento.** Formatado por inteiro (`NNN.NNN.NNN-NN`,
`NN.NNN.NNN/NNNN-NN`) é sempre documento, com ou sem dígito válido: ninguém
formata assim outra coisa. Sem a formatação, só quando o dígito verificador
fecha — é o que o guardrail reconhece, e é o que impede de mascarar timestamp,
id e telefone, que também têm onze ou catorze dígitos. O CNPJ alfanumérico
(julho de 2026) entra pelo mesmo cálculo, com cada caractere valendo o código
ASCII menos 48.

**O que ela não alcança:** o que já entrou num contexto. A ferramenta de
leitura de arquivo não passa por filtro; quem precisa de uma fixture com
documento lê pelo `grep -n ... | doc_mask.py`, e não pela leitura inteira.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

LIMITE = r"(?<![0-9A-Za-z])"
FIM = r"(?![0-9A-Za-z])"
# CNPJ antes de CPF: os dois começam iguais e o mais longo tem de ganhar.
CANDIDATO = re.compile(
    LIMITE + r"(?:"
    r"(?P<cnpj>[0-9A-Z]{2}(?P<p1>\.?)[0-9A-Z]{3}(?P=p1)[0-9A-Z]{3}(?P<b>/?)[0-9A-Z]{4}(?P<t1>-?)\d{2})"
    r"|(?P<cpf>\d{3}(?P<p2>\.?)\d{3}(?P=p2)\d{3}(?P<t2>-?)\d{2})"
    r")" + FIM)

GUARDRAIL = "bloqueada pelo guardrail"
HANDBACK = "SubagentHandback"
MARCA_DE_INTERRUPCAO = "[Request interrupted"


def _valores(texto: str) -> list[int]:
    return [ord(c) - 48 for c in texto]


def cpf_valido(texto: str) -> bool:
    n = re.sub(r"\D", "", texto)
    if len(n) != 11 or len(set(n)) == 1:
        return False
    v = _valores(n)
    for k in (9, 10):
        soma = sum(v[i] * (k + 1 - i) for i in range(k))
        if soma * 10 % 11 % 10 != v[k]:
            return False
    return True


def cnpj_valido(texto: str) -> bool:
    n = re.sub(r"[./-]", "", texto)
    if len(n) != 14 or len(set(n)) == 1 or not n[-2:].isdigit():
        return False
    v = _valores(n)
    for k in (12, 13):
        pesos = [*range(k - 7, 1, -1), *range(9, 1, -1)]
        resto = sum(v[i] * pesos[i] for i in range(k)) % 11
        if (0 if resto < 2 else 11 - resto) != v[k]:
            return False
    return True


def _tipo(m: re.Match) -> str | None:
    """`CPF`, `CNPJ` ou None quando o candidato não é documento."""
    if m.group("cnpj"):
        formatado = bool(m.group("p1") and m.group("b") and m.group("t1"))
        return "CNPJ" if formatado or cnpj_valido(m.group("cnpj")) else None
    formatado = bool(m.group("p2") and m.group("t2"))
    return "CPF" if formatado or cpf_valido(m.group("cpf")) else None


def mascarar(texto: str) -> str:
    def trocar(m: re.Match) -> str:
        tipo = _tipo(m)
        return f"[{tipo}]" if tipo else m.group(0)
    return CANDIDATO.sub(trocar, texto)


def achados(texto: str) -> list[tuple[int, str]]:
    """(linha, tipo) de cada documento. Nunca o número."""
    saida = []
    for i, linha in enumerate(texto.splitlines(), 1):
        for m in CANDIDATO.finditer(linha):
            tipo = _tipo(m)
            if tipo:
                saida.append((i, tipo))
    return saida


def cmd_filtrar(_args) -> int:
    for linha in sys.stdin:
        sys.stdout.write(mascarar(linha))
    return 0


def cmd_conferir(args) -> int:
    total = 0
    for nome in args.arquivos:
        try:
            texto = Path(nome).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"{nome}: não li ({e.strerror})", file=sys.stderr)
            return 2
        for linha, tipo in achados(texto):
            print(f"{nome}:{linha}: {tipo} por extenso")
            total += 1
    if total:
        print(f"\n{total} documento(s) por extenso. Troque por [CPF]/[CNPJ] e cite o "
              "arquivo:linha de onde veio; `doc_mask.py < arq > arq.novo` faz a troca.")
        return 1
    print("nenhum CPF ou CNPJ por extenso.")
    return 0


def raiz_de_transcritos(projeto: Path) -> Path:
    """`~/.claude/projects/<caminho>`, com todo caractere que não é letra nem
    dígito trocado por `-`. Uma worktree em `.claude/worktrees/x` vira
    `--claude-worktrees-x`: trocar só a `/` não acha a pasta."""
    marca = re.sub(r"[^A-Za-z0-9]", "-", str(projeto.resolve()))
    return Path.home() / ".claude" / "projects" / marca


def ultima_fala(transcrito: Path) -> str:
    fala = ""
    with transcrito.open(errors="ignore") as f:
        for linha in f:
            try:
                d = json.loads(linha)
            except (ValueError, TypeError):
                continue
            msg = d.get("message") or {}
            if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
                continue
            for b in msg["content"]:
                if not isinstance(b, dict):
                    continue
                # A devolução chega de dois jeitos: a última fala em texto, ou
                # a chamada `SubagentHandback`, que é por onde a frente da 1052
                # devolveu o CPF. Ler só o texto perdia justamente essa.
                if b.get("type") == "text":
                    texto = (b.get("text") or "").strip()
                elif b.get("type") == "tool_use" and b.get("name") == HANDBACK:
                    texto = str((b.get("input") or {}).get("message") or "").strip()
                else:
                    continue
                if texto:
                    fala = texto
    return fala


def situacao(fala: str) -> str:
    if GUARDRAIL in fala:
        return "BLOQUEADA (403 do guardrail)"
    if fala.startswith(MARCA_DE_INTERRUPCAO):
        return "interrompida"
    if not fala:
        return "sem fala"
    return "entregou" if len(fala) >= 1000 else "fala curta"


def cmd_devolucoes(args) -> int:
    base = raiz_de_transcritos(Path(args.raiz).expanduser())
    agora = time.time()
    transcritos = sorted(
        (t for t in base.glob("*/subagents/*.jsonl")
         if agora - t.stat().st_mtime <= args.minutos * 60
         and (not args.sessao or t.parent.parent.name.startswith(args.sessao))),
        key=lambda t: t.stat().st_mtime)
    if not transcritos:
        print(f"nenhum subagente nos últimos {args.minutos} min em {base}")
        return 1
    saida = Path(args.saida) if args.saida else Path(tempfile.mkdtemp(prefix="devolucoes-"))
    saida.mkdir(parents=True, exist_ok=True)
    print(f"{len(transcritos)} subagente(s), do mais antigo ao mais novo. "
          f"Últimas falas, mascaradas, em:\n  {saida}\n")
    for t in transcritos:
        try:
            meta = json.loads(t.with_suffix(".meta.json").read_text())
        except (OSError, ValueError):
            meta = {}
        fala = ultima_fala(t)
        ident = t.stem.replace("agent-", "")[:9]
        tipo = (meta.get("agentType") or "?").split(":")[-1].replace("elcamargo-", "")
        rotulo = mascarar(meta.get("description") or "")
        (saida / f"{ident}.md").write_text(mascarar(
            f"<!-- {tipo} · {rotulo} · sessão {t.parent.parent.name[:8]} -->\n\n{fala}\n"),
            encoding="utf-8")
        hora = time.strftime("%H:%M", time.localtime(t.stat().st_mtime))
        print(f"  {ident}  {hora}  {tipo:26} {situacao(fala):28} {rotulo[:40]}")
    print("\nQuem retoma lê os arquivos que ENTREGARAM e não redispara essas frentes. "
          "A BLOQUEADA\nnão se retoma nem recebe SendMessage: o contexto dela é que está contaminado.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="acao")
    c = sub.add_parser("conferir", help="sai 1 se algum arquivo tem CPF ou CNPJ por extenso")
    c.add_argument("arquivos", nargs="+")
    d = sub.add_parser("devolucoes", help="depois do 403: as últimas falas dos subagentes, mascaradas")
    d.add_argument("--raiz", default=".", help="o projeto ou a worktree (padrão: o diretório atual)")
    d.add_argument("--minutos", type=int, default=240)
    d.add_argument("--sessao", help="só a sessão cujo id começa assim")
    d.add_argument("--saida", help="pasta dos arquivos (padrão: uma pasta temporária nova)")
    args = p.parse_args(argv)
    acoes = {"conferir": cmd_conferir, "devolucoes": cmd_devolucoes}
    return acoes.get(args.acao, cmd_filtrar)(args)


if __name__ == "__main__":
    # Windows: com a saída em pipe, `print` usa cp1252 e estoura em `·`.
    # Ver `references/windows.md`.
    for _fluxo in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
