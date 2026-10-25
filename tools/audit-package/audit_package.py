#!/usr/bin/env python3
"""Audita o instrumento, não o produto: as skills e os agentes deste pacote.

Todo o resto do fluxo depende destes arquivos, e nada os verificava. Deriva de
nome, descrição que não dispara, agente sem lista de ferramentas e skill que
incha em silêncio só apareciam quando falhavam numa atividade real.

A ideia veio de ler o `ruvnet/ruflo`, que tem ~20 scripts auditando o próprio
setup de agentes. Duas coisas foram roubadas de lá e uma foi corrigida:

- `audit-skill-frontmatter.mjs` confere frontmatter, nome contra diretório e
  lista de ferramentas explícita — "no implicit 'all tools'";
- o limiar de tamanho por arquivo de skill;
- **e eles escreveram o limiar sem nunca verificá-lo**, com 145 skills. Aqui ele
  é verificado, que é a diferença entre regra e intenção.

    audit_package.py            audita e sai 1 se houver violação
    audit_package.py --tamanho  só o relatório de tamanho, sem veredicto
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PACOTE = Path(__file__).resolve().parents[2]

# Acima disto, o arquivo provavelmente carrega referência que pertence a
# `references/`. Não é limite de qualidade: é limite de CONTEXTO — o corpo
# inteiro entra na janela do step toda vez que ele roda.
TETO_SKILL = 12 * 1024
TETO_AGENTE = 8 * 1024

RE_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)

# Skill que dispara subagente e depende do retorno dele não pode rodar DENTRO
# de um subagente: o turno de um subagente acaba quando ele para de chamar
# ferramenta, e esperar não existe ali. O guarda de identidade é o que impede a
# próxima skill de nascer sem o aviso — a prosa numa skill não protege a outra.
GUARDA_ORQUESTRACAO = "references/orchestration.md"


class Achado:
    def __init__(self, grave: bool, onde: str, o_que: str, porque: str) -> None:
        self.grave, self.onde, self.o_que, self.porque = grave, onde, o_que, porque


def frontmatter(texto: str) -> dict[str, str] | None:
    m = RE_FRONTMATTER.match(texto)
    if not m:
        return None
    campos: dict[str, str] = {}
    chave = None
    for linha in m.group(1).splitlines():
        casou = re.match(r"^([a-zA-Z_-]+):\s*(.*)$", linha)
        if casou:
            chave = casou.group(1)
            campos[chave] = casou.group(2).strip().strip('"').strip("'")
        elif chave and linha.startswith(" "):
            campos[chave] += " " + linha.strip()
    return campos


def auditar(raiz: Path) -> tuple[list[Achado], list[tuple[int, str]]]:
    achados: list[Achado] = []
    tamanhos: list[tuple[int, str]] = []
    # Quem dispara subagente se descobre pelo NOME do agente citado no corpo,
    # não por palavra-chave: "espere" e "aguarde" acharam duas das quatro
    # skills afetadas, porque as outras duas dizem a mesma coisa com outras
    # palavras ("você não terminou enquanto o subagente não voltar").
    agentes = {a.stem for a in (raiz / "agents").glob("*.md")}

    for arquivo in sorted((raiz / "skills").glob("*/SKILL.md")):
        rotulo = f"skills/{arquivo.parent.name}"
        texto = arquivo.read_text(encoding="utf-8")
        tamanhos.append((len(texto.encode()), rotulo))
        campos = frontmatter(texto)
        if campos is None:
            achados.append(Achado(True, rotulo, "sem frontmatter",
                                  "sem ele a skill não é descoberta"))
            continue
        if not campos.get("name"):
            achados.append(Achado(True, rotulo, "`name` vazio ou ausente", ""))
        elif campos["name"] != arquivo.parent.name:
            achados.append(Achado(
                True, rotulo, f"`name` é `{campos['name']}`, o diretório é `{arquivo.parent.name}`",
                "deriva de nome: quem invoca pelo diretório não acha"))
        if not campos.get("description"):
            achados.append(Achado(
                True, rotulo, "`description` vazia",
                "é ela que decide se a skill dispara; vazia, nunca dispara"))
        elif len(campos["description"]) < 80:
            achados.append(Achado(
                False, rotulo, f"`description` com {len(campos['description'])} caracteres",
                "descrição curta não distingue esta skill das outras na hora de escolher"))
        disparados = sorted(a for a in agentes if a in texto)
        if disparados and GUARDA_ORQUESTRACAO not in texto:
            achados.append(Achado(
                True, rotulo,
                f"dispara subagente ({', '.join(disparados)}) sem o guarda de identidade",
                "rodada dentro de um subagente ela não consegue esperar o "
                "retorno, e gasta o orçamento inteiro descobrindo isso: "
                "193.310 tokens e zero entrega em 18/09/2026"))
        if len(texto.encode()) > TETO_SKILL:
            achados.append(Achado(
                False, rotulo, f"{len(texto.encode()) // 1024} KB, acima de {TETO_SKILL // 1024} KB",
                "o corpo inteiro entra na janela do step toda vez; o que é "
                "referência pertence a `references/`"))

    for arquivo in sorted((raiz / "agents").glob("*.md")):
        rotulo = f"agents/{arquivo.stem}"
        texto = arquivo.read_text(encoding="utf-8")
        tamanhos.append((len(texto.encode()), rotulo))
        campos = frontmatter(texto)
        if campos is None:
            achados.append(Achado(True, rotulo, "sem frontmatter", ""))
            continue
        if campos.get("name") and campos["name"] != arquivo.stem:
            achados.append(Achado(
                True, rotulo, f"`name` é `{campos['name']}`, o arquivo é `{arquivo.stem}`",
                "deriva de nome"))
        if not campos.get("description"):
            achados.append(Achado(True, rotulo, "`description` vazia", ""))
        # Ferramenta implícita é permissão larga que ninguém decidiu dar.
        if "tools" not in campos:
            achados.append(Achado(
                True, rotulo, "sem `tools` declarado",
                "sem a lista, o agente herda TODAS as ferramentas — inclusive "
                "escrita, num revisor que deveria só ler"))
        elif campos["tools"].strip() in {"*", "all"}:
            achados.append(Achado(
                True, rotulo, f"`tools: {campos['tools']}`",
                "curinga é o mesmo que não declarar"))
        if len(texto.encode()) > TETO_AGENTE:
            achados.append(Achado(
                False, rotulo, f"{len(texto.encode()) // 1024} KB, acima de {TETO_AGENTE // 1024} KB", ""))

    return achados, sorted(tamanhos, reverse=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raiz", default=str(PACOTE))
    p.add_argument("--tamanho", action="store_true",
                   help="só o relatório de tamanho")
    args = p.parse_args(argv)
    raiz = Path(args.raiz).expanduser()

    achados, tamanhos = auditar(raiz)

    if args.tamanho:
        print("Tamanho dos arquivos que entram em contexto:\n")
        for n, rotulo in tamanhos:
            marca = "!" if (rotulo.startswith("skills") and n > TETO_SKILL) or \
                           (rotulo.startswith("agents") and n > TETO_AGENTE) else " "
            print(f"  {marca} {n // 1024:>3} KB  {rotulo}")
        total = sum(n for n, _ in tamanhos)
        print(f"\n  {total // 1024} KB no total.")
        return 0

    graves = [a for a in achados if a.grave]
    leves = [a for a in achados if not a.grave]

    print(f"Auditoria do pacote — {raiz}")
    print(f"{len(list((raiz / 'skills').glob('*/SKILL.md')))} skills, "
          f"{len(list((raiz / 'agents').glob('*.md')))} agentes\n")

    for titulo, lista in (("[ALTO]", graves), ("[MEDIO]", leves)):
        if not lista:
            continue
        print(f"{titulo} {len(lista)}")
        for a in lista:
            print(f"    {a.onde}: {a.o_que}")
            if a.porque:
                print(f"        {a.porque}")
        print()

    if not achados:
        print("Nenhuma violação.\n")

    print("O que isto NÃO verifica: se a skill faz o que a descrição promete.")
    print("Frontmatter certo com procedimento errado passa aqui.")
    return 1 if graves else 0


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
