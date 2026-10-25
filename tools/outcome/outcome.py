#!/usr/bin/env python3
"""Conta o que aconteceu com cada achado de uma revisão.

Uma revisão real produziu vinte e um achados, e ninguém sabia quantos tinham
virado mudança. Não por descuido: o relatório listava o que foi achado, e o
destino de cada um vivia na cabeça de quem corrigiu. Numa rotina de revisão
automática de porte industrial, 94% das propostas nunca foram tocadas — e só se
descobriu porque alguém contou.

Esta ferramenta conta. Ela lê o relatório de revisão, acha as tabelas que têm
coluna **Destino**, e confere quatro coisas que a leitura não pega:

    - achado sem destino declarado, ou com dois destinos na mesma célula
    - `corrigido` sem prova nenhuma ao lado
    - `bloqueia` que ficou `aberto`, ou que foi `aceito` sem portão humano
    - `aberto` que não aparece na seção "Achados abertos" que viaja adiante

E no fim imprime a distribuição, que é o número que ninguém tinha.

Uso:
    outcome.py conferir relatorio.md [--raiz .]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path


class ConferenciaError(Exception):
    pass


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(texto)).strip().lower()


# Os quatro destinos, por radical. O radical e não a palavra inteira porque a
# célula é escrita por gente: "corrigido", "corrigida", "corrigidos" e
# "corrigido na volta 2" são a mesma coisa.
DESTINOS = {
    "corrigid": "corrigido", "fechad": "corrigido", "resolvid": "corrigido",
    "descartad": "descartado", "falso positivo": "descartado",
    "aceit": "aceito", "assumid": "aceito",
    "abert": "aberto", "pendent": "aberto",
}

# Os sinônimos existem porque os relatórios vieram antes da regra. O relatório
# final de uma revisão real trazia `Situação` e `fechado` — a coluna e o destino
# com outro nome. Recusá-los faria a ferramenta acusar de "não tem coluna" um
# relatório que tinha. Uma célula que casa com dois destinos ao mesmo tempo
# ("fechado por descarte") continua sendo denunciada como ambígua, que é o que
# ela é.

# "não fechado" não é "fechado". O relatório real de uma revisão trazia quatro
# linhas assim, e a primeira versão desta ferramenta contou as quatro como
# corrigidas — inflando a taxa de conversão justamente nos achados que ninguém
# tinha fechado. É o pior defeito possível numa ferramenta de contagem: ela
# mentiu para o lado que agrada.
RE_NEGACAO = r"\b(?:nao|sem|nunca)\b(?:\s+\w+){{0,2}}\s+\w*{radical}\w*"

# A primeira célula de uma linha de achado começa com um identificador curto:
# `A1`, `B12`, `V2-11`, `CS-28`, `A-01`. É o que separa uma tabela de achados de
# uma tabela de dimensões não cobertas, que tem a mesma forma e não é a mesma
# coisa.
# As seis frentes do step 9, pelos nomes curtos que os relatórios usam. O
# `implemented-sdd` antes do `sdd` na ordem de busca não é detalhe: procurar o
# curto primeiro casaria dentro do longo e contaria uma frente por duas.
FRENTES_DO_STEP_9 = ("implemented-sdd", "implemented-business", "runtime",
                     "security", "quality", "code")

# "Seis frentes rodaram, seis responderam" — sem nomear nenhuma. Medido em
# 20/09/2026 num relatório real: a tabela da skill dava CINCO frentes para
# aquela trilha, o relatório afirmava seis, e zero estavam nomeadas. Pelo
# documento não dá para dizer qual das duas é verdade, e ele governa a volta
# seguinte.
#
# **E não é conveniência de leitura: o relatório é o único registro que
# sobrevive.** Tentou-se recuperar a resposta do disco e não deu — a volta 1
# rodou como subagente e disparou as frentes dentro do transcrito DELA, que já
# rotacionou. O dossiê some junto. Então um relatório que afirma um número sem
# a lista não é só difícil de auditar hoje: é **impossível de auditar depois**,
# porque a fonte que o desmentiria deixou de existir.
RE_QUANTAS_FRENTES = re.compile(
    r"\b(uma|duas|tr[êe]s|quatro|cinco|seis|[1-6])\s+frentes?\b", re.I)
NUMERO_POR_EXTENSO = {"uma": 1, "duas": 2, "tres": 3, "três": 3, "quatro": 4,
                      "cinco": 5, "seis": 6}

RE_IDENT = re.compile(r"^[*`_ ]*(?P<id>[A-Z][A-Z0-9]{0,4}-?\d{1,3})\b")

# Severidades, também por radical — a célula costuma trazer severidade e
# procedência juntas: "alta · execução".
SEVERIDADES = {"bloqueia": "bloqueia", "bloqueio": "bloqueia",
               "alta": "alta", "alto": "alta",
               "baixa": "baixa", "baixo": "baixa"}

# Um hash de commit citado como prova. `#` na frente exclui cor hexadecimal e
# número de card, que aparecem nas mesmas células.
RE_HASH = re.compile(r"(?<![#\w])(?P<hash>[0-9a-f]{7,40})(?![\w])")

# Abaixo disto a distribuição não diz nada: três achados com zero descartes é
# uma revisão pequena, não um consolidador que só encaminha.
MINIMO_PARA_TAXA = 5


# --------------------------------------------------------------------------
# tabelas
# --------------------------------------------------------------------------
def celulas(linha: str) -> list[str]:
    """As células de uma linha de tabela markdown, sem as bordas."""
    bruto = linha.strip()
    if bruto.startswith("|"):
        bruto = bruto[1:]
    if bruto.endswith("|"):
        bruto = bruto[:-1]
    return [c.strip() for c in bruto.split("|")]


def eh_separador(linha: str) -> bool:
    return bool(re.match(r"^\s*\|[\s:|-]+\|\s*$", linha)) and "-" in linha


def tabelas(linhas: list[str]):
    """Cada tabela markdown do documento: (linha_do_cabecalho, header, rows).

    `rows` traz (numero_da_linha, celulas).
    """
    i = 0
    while i < len(linhas):
        if (linhas[i].lstrip().startswith("|")
                and i + 1 < len(linhas) and eh_separador(linhas[i + 1])):
            cabecalho = celulas(linhas[i])
            n_cabecalho = i + 1
            i += 2
            corpo = []
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                corpo.append((i + 1, celulas(linhas[i])))
                i += 1
            yield n_cabecalho, cabecalho, corpo
        else:
            i += 1


def indice_da_coluna(cabecalho: list[str], *nomes: str) -> int | None:
    for n, titulo in enumerate(cabecalho):
        t = normalizar(titulo)
        if any(nome in t for nome in nomes):
            return n
    return None


def classificar(celula: str,
                tabela: dict[str, str]) -> tuple[list[str], list[str], str]:
    """Quais chaves aparecem na célula, quais aparecem negadas, e o que sobra.

    O resto importa: numa célula "corrigido em `dto.ts:44`", o que sobra depois
    de tirar a palavra é a prova. Sem isso, um relatório que põe a evidência
    junto do destino seria acusado de não ter evidência nenhuma.
    """
    texto = normalizar(celula)
    achadas, negadas, resto = [], [], texto
    for radical, nome in tabela.items():
        # A PALAVRA INTEIRA, não o radical. Tirar só "corrigid" de "corrigido"
        # deixa um "o" solto, e um "o" solto é texto não vazio — o que fazia
        # um `| corrigido | |` sem prova nenhuma passar como se tivesse prova.
        padrao = re.compile(r"\w*" + re.escape(radical) + r"\w*")
        if not padrao.search(resto):
            continue
        alvo = (negadas if re.search(RE_NEGACAO.format(radical=re.escape(radical)), texto)
                else achadas)
        if nome not in alvo:
            alvo.append(nome)
        resto = padrao.sub(" ", resto)
    achadas = [n for n in achadas if n not in negadas]
    return achadas, negadas, re.sub(r"[\s·,;.\-–—]+", " ", resto).strip()


# --------------------------------------------------------------------------
# seção de achados abertos
# --------------------------------------------------------------------------
def secao_de_abertos(linhas: list[str]) -> tuple[bool, str]:
    """O texto sob o título "Achados abertos", se ele existir.

    Ela é o que viaja: a terceira volta entrega o que não fechou declarado, e
    quem vem depois lê dali. Um `aberto` na tabela que não está nessa seção é
    dívida escondida, não achado declarado.
    """
    inicio = None
    nivel = 0
    for n, linha in enumerate(linhas):
        m = re.match(r"^(#{1,6})\s+(.*)$", linha)
        if not m:
            continue
        titulo = normalizar(m.group(2))
        if inicio is None:
            if "achados abertos" in titulo or "achado aberto" in titulo:
                inicio, nivel = n + 1, len(m.group(1))
        elif len(m.group(1)) <= nivel:
            return True, "\n".join(linhas[inicio:n])
    if inicio is None:
        return False, ""
    return True, "\n".join(linhas[inicio:])


# --------------------------------------------------------------------------
# comando
# --------------------------------------------------------------------------
def commit_existe(raiz: Path, sha: str) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "cat-file", "-e", f"{sha}^{{commit}}"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        # Sem git aqui a verificação não acontece — e não acontecer é diferente
        # de reprovar. Ver o rodapé: o que não foi conferido não vira achado.
        return True


def cmd_conferir(args) -> int:
    documento = Path(args.documento)
    if not documento.is_file():
        raise ConferenciaError(f"documento não encontrado: {documento}")
    raiz = Path(args.raiz).resolve()
    linhas = documento.read_text(encoding="utf-8").splitlines()

    # id -> registro. A última ocorrência vence: o relatório final consolida
    # todas as voltas, e o mesmo achado aparece `aberto` na volta 1 e
    # `corrigido` na volta 2. Contar as duas inflaria o total.
    registros: dict[str, dict] = {}
    repetidos: list[str] = []
    ignoradas = 0

    for _, cabecalho, corpo in tabelas(linhas):
        i_destino = indice_da_coluna(cabecalho, "destino", "situacao", "desfecho")
        if i_destino is None:
            continue
        # A coluna com o nome canônico é contrato: toda linha dela é achado.
        # As aliases — `Situação`, `Desfecho` — são cortesia com relatórios
        # escritos antes da regra, e num deles a mesma forma de tabela servia
        # para listar dimensões não cobertas, que não são achados e não têm
        # destino. Ali a primeira célula precisa parecer um identificador.
        canonica = normalizar(cabecalho[i_destino]) == "destino"
        i_sev = indice_da_coluna(cabecalho, "severidade", "gravidade")
        i_prova = indice_da_coluna(cabecalho, "prova", "evidencia", "por que",
                                   "motivo", "como foi medido", "como sei")

        for n, cel in corpo:
            if len(cel) <= i_destino:
                continue
            bruto_id = cel[0].strip()
            if not bruto_id or set(bruto_id) <= set("-—– *`"):
                continue
            m = RE_IDENT.match(bruto_id)
            if m is None and not canonica:
                ignoradas += 1
                continue
            ident = m.group("id") if m else bruto_id.strip("`* ")[:60]

            destinos, negados, resto = classificar(cel[i_destino], DESTINOS)
            sevs = []
            if i_sev is not None and len(cel) > i_sev:
                sevs, _, _ = classificar(cel[i_sev], SEVERIDADES)
            prova = resto
            if i_prova is not None and len(cel) > i_prova:
                prova = (cel[i_prova].strip() + " " + resto).strip()

            if ident in registros:
                repetidos.append(ident)
            registros[ident] = {"linha": n, "destinos": destinos, "negados": negados,
                                "prova": prova,
                                "severidade": sevs[0] if sevs else "",
                                "bruto": cel[i_destino].strip()}

    if not registros:
        print("Nenhuma tabela com coluna Destino neste documento.")
        if ignoradas:
            print(f"({ignoradas} linha(s) tinham coluna de situação e nenhum")
            print("identificador de achado na primeira célula.)")
        print()
        print("O relatório de revisão precisa de uma: é ela que permite contar")
        print("quantos achados viraram mudança. Ver references/outcome.md.")
        return 1

    sem_destino, ambiguos, sem_prova, negados = [], [], [], []
    bloqueio_aberto, bloqueio_aceito_sem_portao, hash_que_nao_resolve = [], [], []
    contagem = {"corrigido": 0, "descartado": 0, "aceito": 0, "aberto": 0}

    for ident, r in sorted(registros.items()):
        onde = f"{ident} (linha {r['linha']})"
        if not r["destinos"]:
            alvo = negados if r["negados"] else sem_destino
            alvo.append(f"{onde}: {r['bruto'] or '«vazio»'}")
            continue
        if len(r["destinos"]) > 1:
            ambiguos.append(f"{onde}: {', '.join(r['destinos'])}")
            continue
        d = r["destinos"][0]
        contagem[d] += 1

        if d in ("corrigido", "descartado", "aceito") and not r["prova"]:
            sem_prova.append(f"{onde}: {d}, e nada mais na linha")
        if d == "aberto" and r["severidade"] == "bloqueia":
            bloqueio_aberto.append(onde)
        if d == "aceito" and r["severidade"] == "bloqueia":
            if "portao" not in normalizar(r["prova"]):
                bloqueio_aceito_sem_portao.append(onde)
        if d == "corrigido":
            for m in RE_HASH.finditer(r["prova"]):
                if not commit_existe(raiz, m.group("hash")):
                    hash_que_nao_resolve.append(f"{onde}: {m.group('hash')}")

    tem_secao, texto_abertos = secao_de_abertos(linhas)
    abertos_fora = []
    if contagem["aberto"]:
        if not tem_secao:
            abertos_fora = ["«não há seção Achados abertos neste relatório»"]
        else:
            for ident, r in sorted(registros.items()):
                if r["destinos"] == ["aberto"] and ident not in texto_abertos:
                    abertos_fora.append(ident)

    # ----------------------------------------------------------------------
    graves = 0

    def bloco(itens, rotulo, explicacao, nivel="ALTO"):
        nonlocal graves
        if not itens:
            return
        if nivel == "ALTO":
            graves += 1
        print(f"[{nivel}] {rotulo} ({len(itens)})")
        for linha in explicacao:
            print(f"  {linha}")
        for i in itens:
            print(f"    {i}")
        print()

    # A chamada nominal das frentes. Sem ela, "seis rodaram" é afirmação que
    # ninguém audita depois — nem para pegar uma frente a mais, nem uma a
    # menos, nem para saber de qual frente veio um achado a reexaminar.
    texto_todo = "\n".join(linhas)
    nomeadas = {f for f in FRENTES_DO_STEP_9 if f in texto_todo}
    alegadas = set()
    for m in RE_QUANTAS_FRENTES.finditer(texto_todo):
        bruto = m.group(1).lower()
        alegadas.add(NUMERO_POR_EXTENSO.get(bruto, None)
                     or (int(bruto) if bruto.isdigit() else 0))
    alegadas.discard(0)
    frentes_sem_nome = []
    if alegadas and max(alegadas) > len(nomeadas):
        frentes_sem_nome.append(
            f"o relatório afirma {max(alegadas)} frente(s) e nomeia "
            f"{len(nomeadas)}: {', '.join(sorted(nomeadas)) or 'nenhuma'}")

    bloco(frentes_sem_nome, "frente que rodou sem ser nomeada",
          ["um número de frentes sem a lista não é auditável: não dá para pegar",
           "uma a mais, nem uma a menos, nem saber de qual veio um achado que",
           "precisa ser reexaminado por origem. Nomeie cada uma, e diga qual",
           "ficou `nao-coberta` e por quê — o `avancar` para o step 9 imprime",
           "quais tinham baseline, e grava no histórico"])

    bloco(sem_destino, "achado sem destino declarado",
          ["ele foi corrigido, descartado, aceito ou ficou aberto — mas o",
           "relatório não diz qual, e ninguém vai voltar para descobrir"])
    bloco(negados, "destino escrito por negação",
          ["'não fechado' diz o que NÃO aconteceu, e some com o que aconteceu:",
           "voltou aberto? virou decisão? escreva a palavra — `aberto`, `aceito`",
           "— e o porquê ao lado. Uma versão desta ferramenta contou quatro",
           "'não fechado' como corrigidos, e a taxa de conversão subiu sozinha"])
    bloco(ambiguos, "achado com dois destinos na mesma célula",
          ["'corrigido em parte e aceito' são dois achados, não um"])
    bloco(sem_prova, "destino declarado sem nada que o sustente",
          ["'corrigi' não fecha nada; 'descartei' sem motivo volta na próxima",
           "volta como falso positivo novo. Ver references/severity.md,",
           "Vale igual quando o achado FECHA"])
    bloco(bloqueio_aberto, "achado que bloqueia, e ficou aberto",
          ["bloqueio não viaja como achado aberto: ou fecha, ou escala ao",
           "portão humano com nome de quem decide"])
    bloco(bloqueio_aceito_sem_portao, "bloqueio aceito sem portão que o aceitou",
          ["aceitar um bloqueio é decisão de gente. Nomeie o portão e a decisão"])
    bloco(abertos_fora, "achado aberto que não está na seção que viaja",
          ["a tabela diz 'aberto' e a seção Achados abertos não o traz — quem",
           "vem depois não vai lê-lo"])
    bloco(hash_que_nao_resolve, "prova que cita commit inexistente neste repositório",
          ["pode ser hash de outra branch não trazida, ou hash inventado"],
          nivel="MEDIO")

    total = sum(contagem.values())
    print(f"Destino de {total} achados"
          + (f", de {len(registros)} linhas de achado" if len(registros) != total else ""))
    for nome in ("corrigido", "descartado", "aceito", "aberto"):
        n = contagem[nome]
        taxa = f"{100 * n / total:.0f}%" if total else "—"
        print(f"    {nome:<12} {n:>3}   {taxa:>4}")
    if ignoradas:
        print()
        print(f"  {ignoradas} linha(s) de tabela com coluna de situação foram")
        print("  ignoradas: a primeira célula não tem identificador de achado")
    if repetidos:
        print()
        print(f"  {len(set(repetidos))} achado(s) aparecem em mais de uma volta;")
        print("  contei a última ocorrência de cada: " + ", ".join(sorted(set(repetidos))))
    print()

    if total >= MINIMO_PARA_TAXA and contagem["descartado"] == 0:
        print("[MEDIO] nenhum achado descartado")
        print("  consolidar é tentar derrubar, e um mandato adversarial derruba")
        print("  perto de 79% dos candidatos. Zero descartes em "
              f"{total} achados costuma")
        print("  significar que os achados foram encaminhados, não consolidados")
        print()
    if total >= MINIMO_PARA_TAXA and contagem["corrigido"] == 0:
        print("[MEDIO] nenhum achado virou mudança")
        print("  a revisão inteira não alterou uma linha. Ou ela não achou nada")
        print("  que valesse, ou achou e ninguém agiu — e as duas coisas são")
        print("  informação para o portão humano")
        print()

    print("O que isto NÃO prova: que a correção conserta, que o descarte era")
    print("justo, ou que o aceite foi mesmo de uma pessoa. Ele conta destinos e")
    print("cobra que cada um esteja escrito. Julgar continua sendo trabalho seu.")
    return 1 if graves else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("conferir", help="destino de cada achado do relatório")
    c.add_argument("documento")
    c.add_argument("--raiz", default=".", help="raiz do repositório")
    c.set_defaults(fn=cmd_conferir)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ConferenciaError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


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
