#!/usr/bin/env python3
"""Matriz de rastreabilidade: a parte mecânica, feita por máquina.

Enumerar seções, achar identificadores, contar por seção e conferir se nada
sumiu é trabalho de varredura. Um modelo fazendo isso à mão gasta quinze
minutos, erra a contagem e não percebe que errou — foi o que a POC mediu.

O que esta ferramenta faz:

    extrair   varre o documento e devolve o esqueleto da matriz: seções,
              identificadores, contagem por seção e lacunas de série.
    conferir  confere uma matriz já preenchida contra a origem e contra a SDD.
    casos     o contrato de casos de uma atividade: gerar, vermelho, verde.
    conferir-testes
              o step 9: cada caso da SDD tem teste, e o teste passa. Ver
              `casos.py`.

O que ela NÃO faz, de propósito: julgar. Estado, destino e severidade são
decisão de quem lê o requisito. A ferramenta entrega o esqueleto e a prova de
que ele está completo; a carne é do analista.

    python3 matrix.py extrair <documento> [--prefixos RN,RF,RNF,CA,CT] [--formato tabela|matriz|json]
    python3 matrix.py conferir <matrix.md> --origem <documento> [--sdd <sdd.md>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PREFIXOS_PADRAO = ["RN", "RF", "RNF", "CA", "CT", "RNG", "US", "REQ"]

ESTADOS = {
    "confirmado",
    "confirmado com correção",
    "proposto",
    "pressuposto",
    "pendente",
    "conflito",
    "fora de escopo",
}

# Cabeçalhos que anunciam a lista de itens deixados de fora. Um item da matriz
# marcado "Fora de escopo" precisa aparecer aqui, senão sumiu sem justificativa.
MARCAS_FORA_ESCOPO = ("fora de escopo", "nao entra", "excluido", "nao contemplado")


class MatrizError(Exception):
    pass


def sem_acento(texto: str) -> str:
    n = unicodedata.normalize("NFD", texto)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").lower()


# --------------------------------------------------------------------------
# Leitura do documento
# --------------------------------------------------------------------------
def _texto_docx(caminho: Path) -> str:
    """Extrai parágrafos e TABELAS de um .docx com stdlib.

    As tabelas importam: a maior parte das especificações lista requisito em
    tabela, e um extrator que só pega parágrafo devolve um documento vazio com
    cara de documento lido.
    """
    with zipfile.ZipFile(caminho) as z:
        nomes = [n for n in z.namelist() if n == "word/document.xml"]
        if not nomes:
            raise MatrizError(f"{caminho.name} não tem word/document.xml — é mesmo um .docx?")
        xml = z.read("word/document.xml").decode("utf-8", "replace")

    # Quebra em blocos preservando a ordem: parágrafo ou tabela.
    saida: list[str] = []
    # finditer, não findall: com grupo de captura o findall devolveria só "p" ou
    # "tbl" em vez do bloco, e o documento sairia vazio com cara de imagem.
    for m in re.finditer(r"<w:(p|tbl)\b[^>]*>.*?</w:\1>", xml, re.S):
        bloco = m.group(0)
        textos = re.findall(r"<w:t[^>]*>(.*?)</w:t>", bloco, re.S)
        conteudo = "".join(textos)
        conteudo = re.sub(r"<[^>]+>", "", conteudo)
        conteudo = (conteudo.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
        conteudo = conteudo.strip()
        if not conteudo:
            continue
        if bloco.startswith("<w:tbl"):
            # Uma linha por <w:tr>, células separadas por barra, para o
            # classificador enxergar início de célula como início de item.
            linhas = []
            for tr in re.findall(r"<w:tr\b.*?</w:tr>", bloco, re.S):
                celulas = []
                for tc in re.findall(r"<w:tc\b.*?</w:tc>", tr, re.S):
                    t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", tc, re.S))
                    t = re.sub(r"<[^>]+>", "", t).strip()
                    celulas.append(t)
                if any(celulas):
                    linhas.append("| " + " | ".join(celulas) + " |")
            saida.extend(linhas)
        else:
            estilo = re.search(r'<w:pStyle w:val="([^"]+)"', bloco)
            nome = sem_acento(estilo.group(1)) if estilo else ""
            m = re.match(r"(?:heading|titulo)(\d)", nome)
            if m:
                saida.append("#" * min(int(m.group(1)), 6) + " " + conteudo)
            else:
                saida.append(conteudo)
    return "\n".join(saida)


def _texto_pdf(caminho: Path) -> str:
    try:
        import pypdfium2  # type: ignore
    except ImportError:
        raise MatrizError(
            f"{caminho.name} é PDF e pypdfium2 não está disponível.\n"
            "  Instale:  python3 -m venv ~/.cache/elcamargo-flow/venv && "
            "~/.cache/elcamargo-flow/venv/bin/python -m pip install pypdfium2\n"
            "  E rode com ~/.cache/elcamargo-flow/venv/bin/python.\n"
            "  Atenção: PDF cuja seção é imagem sai vazio em silêncio — "
            "confira as seções vazias no relatório."
        )
    doc = pypdfium2.PdfDocument(str(caminho))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def ler_documento(caminho: Path) -> str:
    if not caminho.exists():
        raise MatrizError(f"não achei {caminho}")
    sufixo = caminho.suffix.lower()
    if sufixo == ".docx":
        texto = _texto_docx(caminho)
    elif sufixo == ".pdf":
        texto = _texto_pdf(caminho)
    elif sufixo == ".doc":
        raise MatrizError(
            f"{caminho.name} é .doc (formato antigo, binário). Salve como .docx ou PDF."
        )
    else:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    if not texto.strip():
        raise MatrizError(
            f"{caminho.name} foi lido e veio VAZIO. Isso quase sempre significa "
            "que o conteúdo é imagem. Não trate como documento sem requisitos — "
            "renderize as páginas e leia delas."
        )
    return texto


# --------------------------------------------------------------------------
# Varredura
# --------------------------------------------------------------------------
# Seções que existem para narrar, não para listar requisito. Nenhuma delas
# estar vazia significa coisa alguma.
NOMES_NARRATIVOS = (
    "contexto", "introducao", "objetivo", "escopo", "fora de escopo",
    "glossario", "referencia", "history", "versao", "decisao", "decisoes",
    "consideracoes", "premissa", "sumario", "indice", "resumo", "visao geral",
    "matriz", "rastreabilidade", "aprovacao", "controle",
)


@dataclass
class Secao:
    titulo: str
    linha: int
    nivel: int
    definicoes: int = 0
    mencoes: int = 0
    filhos: int = 0

    @property
    def narrativa(self) -> bool:
        nome = sem_acento(self.titulo)
        nome = re.sub(r"^[\d.\s)\[\]]+", "", nome)
        return any(nome.startswith(n) for n in NOMES_NARRATIVOS)

    @property
    def suspeita(self) -> bool:
        """Vazia de um jeito que merece conferência.

        Seção-pai não conta: os itens estão nas filhas. Seção narrativa não
        conta. Numa SDD em markdown quase toda seção é uma das duas, e avisar
        sobre todas transformava o aviso em ruído — quatro falsos positivos num
        documento de dezoito requisitos, todos corretos.
        """
        return not self.definicoes and not self.filhos and not self.narrativa


@dataclass
class Ocorrencia:
    ident: str
    prefixo: str
    numero: int
    sufixo: str
    linha: int
    tipo: str          # definicao | mencao
    trecho: str
    secao: str = ""


RE_TITULO_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
# "4.1 Regras de Negócio" — numeração de documento gerada por editor.
RE_TITULO_NUM = re.compile(
    r"^\s*(\d+(?:\.\d+){0,3})[.)]?\s+"
    # "3 [RF] REQUISITOS FUNCIONAIS": a etiqueta entre colchetes é comum e
    # fez quatro seções passarem despercebidas na primeira execução real.
    r"((?:\[[^\]]{1,12}\]\s*)?[A-Za-zÀ-ÿ][^|]{2,80})$"
)
# "3 de 6", "Page 2 of 7" — rodapé de página tem a mesma forma de um título
# numerado e apareceu como sete seções falsas na primeira execução real.
RE_RODAPE = re.compile(r"^\s*(?:p[áa]g(?:ina)?\.?\s*)?\d+\s*(?:de|of|/)\s*\d+\s*$",
                       re.IGNORECASE)


def achar_secoes(texto: str) -> list[Secao]:
    secoes: list[Secao] = []
    for n, linha in enumerate(texto.splitlines(), 1):
        if RE_RODAPE.match(linha):
            continue
        m = RE_TITULO_MD.match(linha)
        if m:
            secoes.append(Secao(m.group(2).strip(), n, len(m.group(1))))
            continue
        m = RE_TITULO_NUM.match(linha)
        if m and not linha.strip().endswith((".", ":", ";")):
            secoes.append(Secao(f"{m.group(1)} {m.group(2).strip()}", n,
                                m.group(1).count(".") + 1))
    return secoes


def padrao_ident(prefixos: list[str]) -> re.Pattern:
    alt = "|".join(sorted((re.escape(p) for p in prefixos), key=len, reverse=True))
    return re.compile(rf"\b({alt})[\s\-–—_.]?(\d{{1,4}})([a-zA-Z])?(?![\w-])")


def classificar(linha: str, coluna: int) -> str:
    """Definição ou menção.

    Se tudo que vem antes do identificador na linha é marcação — espaço,
    marcador de lista, barra de tabela, sustenido de título — o identificador
    ABRE o item: é definição. Caso contrário está no meio de uma frase que fala
    sobre ele: é menção.

    Sem essa distinção a contagem infla, porque uma regra citada dez vezes
    viraria onze requisitos.
    """
    antes = linha[:coluna]
    # A crase entrou depois, e o defeito que ela conserta era silencioso: numa
    # tabela de casos de teste com o identificador entre crases na primeira
    # coluna — `| `CT-01` | Título | ... |` —, tudo antes dele era marcação
    # EXCETO a crase, e os 27 itens saíam como "citados e nunca definidos".
    # Sem crase a MESMA tabela já contava como definição, então isto não abre
    # uma classe nova: fecha uma incoerência entre duas formas da mesma coisa.
    if antes.strip(" \t#*-–—|>•·°º.)(0123456789`\"'_") == "":
        return "definicao"
    return "mencao"


def varrer(texto: str, prefixos: list[str]) -> tuple[list[Secao], list[Ocorrencia]]:
    secoes = achar_secoes(texto)
    padrao = padrao_ident(prefixos)
    ocorrencias: list[Ocorrencia] = []
    linhas = texto.splitlines()

    for n, linha in enumerate(linhas, 1):
        for m in padrao.finditer(linha):
            prefixo = m.group(1).upper()
            if prefixo not in {p.upper() for p in prefixos}:
                continue
            tipo = classificar(linha, m.start())
            trecho = linha[m.end():].strip(" \t|:-–—")[:120] or linha.strip()[:120]
            ocorrencias.append(Ocorrencia(
                ident=f"{prefixo}-{int(m.group(2)):02d}" + (m.group(3) or ""),
                prefixo=prefixo, numero=int(m.group(2)), sufixo=m.group(3) or "",
                linha=n, tipo=tipo, trecho=trecho,
            ))

    # Cada ocorrência pertence à última seção aberta antes dela.
    for oc in ocorrencias:
        atual = ""
        for s in secoes:
            if s.linha <= oc.linha:
                atual = s.titulo
            else:
                break
        oc.secao = atual
    for i, s in enumerate(secoes):
        for outra in secoes[i + 1:]:
            if outra.nivel <= s.nivel:
                break
            s.filhos += 1

    indice = {s.titulo: s for s in secoes}
    for oc in ocorrencias:
        s = indice.get(oc.secao)
        if s:
            if oc.tipo == "definicao":
                s.definicoes += 1
            else:
                s.mencoes += 1
    return secoes, ocorrencias


def secoes_que_mentem(secoes: list[Secao], ocorrencias: list[Ocorrencia],
                      prefixos: list[str]) -> list[tuple[Secao, str]]:
    """Seção cujo título anuncia um prefixo e que não contém nenhum item dele.

    É a falha canônica: "64 RN e zero RF, num documento que tem RF". O título
    "3 [RF] REQUISITOS FUNCIONAIS" é a declaração do próprio documento de que
    ali existem RF. Se saíram zero, a extração perdeu a seção — e a matriz vai
    ficar completa na aparência.
    """
    # O alcance de uma seção vai até a próxima do mesmo nível ou acima — e não
    # até a próxima seção qualquer. Antes esta conferência agregava por
    # `o.secao`, que é a seção MAIS INTERNA, e um documento cujos itens são
    # subtítulos (`### RF-01`, a forma normal) punha cada definição na seção do
    # próprio item. A seção de tipo, um nível acima, ficava com zero e a mesma
    # execução imprimia "2 RF" e "zero RF" — achado por
    # `acme-backoffice-0f` em 10/09/2026, com repro de sete linhas.
    fim: dict[int, int] = {}
    for i, s in enumerate(secoes):
        limite = 10 ** 9
        for outra in secoes[i + 1:]:
            if outra.nivel <= s.nivel:
                limite = outra.linha
                break
        fim[id(s)] = limite

    definicoes = [o for o in ocorrencias if o.tipo == "definicao"]
    saida = []
    for s in secoes:
        titulo = s.titulo.upper()
        dentro = {o.prefixo for o in definicoes
                  if s.linha <= o.linha < fim[id(s)]}
        for p in prefixos:
            anunciado = (re.search(rf"\[{re.escape(p)}\]", titulo)
                         or re.search(rf"\b{re.escape(p)}\b", titulo))
            if anunciado and p not in dentro:
                saida.append((s, p))
    return saida


def definicoes_unicas(ocorrencias: list[Ocorrencia]) -> dict[str, Ocorrencia]:
    """Primeira definição de cada identificador, na ordem do documento."""
    saida: dict[str, Ocorrencia] = {}
    for oc in ocorrencias:
        if oc.tipo == "definicao" and oc.ident not in saida:
            saida[oc.ident] = oc
    return saida


def penduradas(ocorrencias: list[Ocorrencia]) -> dict[str, list[int]]:
    """Identificadores citados no texto que nunca são definidos.

    Na primeira execução real isto achou um RN citado no histórico de versões
    — "ajuste de cardinalidade em RN-04" — que o documento nunca define. Ou a
    regra foi removida sem limpar a referência, ou ela existe e a seção não
    entrou no arquivo. Nos dois casos alguém precisa saber.
    """
    definidos = {o.ident for o in ocorrencias if o.tipo == "definicao"}
    saida: dict[str, list[int]] = {}
    for o in ocorrencias:
        if o.tipo == "mencao" and o.ident not in definidos:
            saida.setdefault(o.ident, []).append(o.linha)
    return saida


def lacunas(idents: list[str]) -> dict[str, list[str]]:
    """Buracos de numeração por prefixo: RN-01..RN-36 sem RN-17."""
    por_prefixo: dict[str, list[int]] = {}
    for i in idents:
        p, _, n = i.partition("-")
        por_prefixo.setdefault(p, []).append(int(re.sub(r"\D", "", n) or 0))
    saida = {}
    for p, nums in por_prefixo.items():
        nums = sorted(set(nums))
        if len(nums) < 2:
            continue
        faltando = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if faltando:
            saida[p] = [f"{p}-{n:02d}" for n in faltando]
    return saida


# --------------------------------------------------------------------------
# extrair
# --------------------------------------------------------------------------
def cmd_extrair(args) -> int:
    caminho = Path(args.documento).expanduser()
    prefixos = [p.strip().upper() for p in args.prefixos.split(",") if p.strip()]
    texto = ler_documento(caminho)
    secoes, ocorrencias = varrer(texto, prefixos)
    defs = definicoes_unicas(ocorrencias)

    if args.formato == "json":
        print(json.dumps({
            "documento": str(caminho),
            "secoes": [{"titulo": s.titulo, "linha": s.linha, "nivel": s.nivel,
                        "definicoes": s.definicoes, "mencoes": s.mencoes} for s in secoes],
            "itens": [{"id": o.ident, "secao": o.secao, "linha": o.linha,
                       "trecho": o.trecho} for o in defs.values()],
            "contagem": {p: sum(1 for i in defs if i.startswith(p + "-")) for p in prefixos},
            "lacunas": lacunas(list(defs)),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.formato == "matriz":
        print("| Item | Seção | Origem | Estado | Onde foi parar |")
        print("| --- | --- | --- | --- | --- |")
        for o in defs.values():
            trecho = o.trecho.replace("|", "\\|")[:80]
            print(f"| {o.ident} | {o.secao[:40]} | L{o.linha} — {trecho} |  |  |")
        return 0

    # tabela (humano)
    print(f"Documento  {caminho}")
    print(f"Formato    {caminho.suffix.lower() or 'texto'}    "
          f"{len(texto.splitlines())} linhas")
    print()

    print("Seções e itens definidos")
    print(f"  {'seção':<52} {'linha':>6} {'def':>5} {'menç':>5}")
    vazias = []
    for s in secoes:
        marca = "!!" if s.suspeita else "  "
        print(f"{marca}{s.titulo[:52]:<52} {s.linha:>6} {s.definicoes:>5} {s.mencoes:>5}")
        if s.suspeita:
            vazias.append(s)
    if not secoes:
        print("  (nenhum título reconhecido — o documento pode não ter estrutura, "
              "ou a extração perdeu a formatação)")
    print()

    contagem = {p: sum(1 for i in defs if i.startswith(p + "-")) for p in prefixos}
    resumo = ", ".join(f"{n} {p}" for p, n in contagem.items() if n)
    print(f"Contagem   {resumo or '(nenhum identificador encontrado)'}")
    print(f"Total      {len(defs)} itens definidos, "
          f"{sum(1 for o in ocorrencias if o.tipo == 'mencao')} menções")
    print()

    if vazias:
        print("SEÇÕES SEM NENHUM ITEM — confira uma a uma")
        for s in vazias:
            print(f"  L{s.linha:<6} {s.titulo[:66]}")
        print("  Seção do sumário que sai vazia costuma ser imagem, não seção curta.")
        print("  Vá buscar por outro caminho antes de concluir que não há requisito ali.")
        print()

    penduras = penduradas(ocorrencias)
    if penduras:
        print("CITADOS E NUNCA DEFINIDOS")
        for ident, ls in sorted(penduras.items()):
            print(f"  {ident:<10} citado em " + ", ".join(f"L{l}" for l in ls[:6]))
        print("  Ou a regra sumiu sem limpar a referência, ou ela existe e a seção")
        print("  não entrou no arquivo. Pergunte ao analista; não decida sozinho.")
        print()

    falta = lacunas(list(defs))
    if falta:
        print("LACUNAS DE NUMERAÇÃO")
        for p, ids in falta.items():
            print(f"  {p}: {', '.join(ids)}")
        print("  Pode ser numeração pulada no original, pode ser item que a extração")
        print("  perdeu. Confirme no documento antes de seguir.")
        print()

    mentem = secoes_que_mentem(secoes, ocorrencias, prefixos)
    if mentem:
        print("SEÇÃO QUE ANUNCIA UM TIPO E NÃO ENTREGA NENHUM")
        for s, pref in mentem:
            print(f"  L{s.linha:<6} {s.titulo[:52]:<52} zero {pref}")
        print("  O título é a declaração do documento de que ali existem itens desse")
        print("  tipo. Zero significa extração perdida, não seção vazia.")
        print()

    print("O que a ferramenta NÃO fez, e é seu:")
    print("  - decidir o estado de cada item")
    print("  - dizer onde cada um foi parar na SDD")
    print("  - achar contradição, cardinalidade errada e ambiguidade")
    print()
    print(f"Esqueleto pronto para colar:  {sys.argv[0]} extrair "
          f"{caminho} --formato matriz")
    return 0


# --------------------------------------------------------------------------
# conferir
# --------------------------------------------------------------------------
RE_LINHA_DE_MATRIZ = re.compile(r"^\s*\|\s*\**[A-Z]{2,4}[\s\-–—_.]?\d{1,4}[a-zA-Z]?\**\s*\|")


def partir_sdd(texto: str) -> tuple[str, str]:
    """Separa a SDD em corpo e bloco de fora de escopo.

    O bloco começa num título cujo nome anuncia exclusão e vai até o próximo
    título de nível igual ou superior.

    As linhas da própria matriz de rastreabilidade saem das duas partes. A
    matriz costuma morar dentro da SDD, e sem essa exclusão todo item "aparece
    na SDD" — na linha em que ele diz que aparece. A conferência passaria
    sempre. Num teste com defeito plantado, um requisito que a especificação
    ignorava por completo passou exatamente assim.
    """
    linhas = [l for l in texto.splitlines() if not RE_LINHA_DE_MATRIZ.match(l)]
    dentro_fora = False
    nivel_fora = 0
    corpo: list[str] = []
    fora: list[str] = []
    for linha in linhas:
        m = RE_TITULO_MD.match(linha)
        if m:
            nome = sem_acento(m.group(2))
            nivel = len(m.group(1))
            if any(mk in nome for mk in MARCAS_FORA_ESCOPO):
                dentro_fora, nivel_fora = True, nivel
                fora.append(linha)
                continue
            if dentro_fora and nivel <= nivel_fora:
                dentro_fora = False
        (fora if dentro_fora else corpo).append(linha)
    return "\n".join(corpo), "\n".join(fora)


# O marcador é OBRIGATÓRIO. Com ele opcional, qualquer número virava âncora de
# seção: `CS-01` lia "01", `§8 R-35` lia "8" e "35". Numa spec real isso produziu
# SETENTA E DOIS falsos [ALTO] de "destino inexistente" — e falso positivo em
# massa é pior que verificação ausente, porque ensina a ignorar a ferramenta.
RE_ANCORA = re.compile(r"(?:§|se[cç][aã]o\s+|item\s+)(\d+(?:\.\d+){0,3})",
                       re.IGNORECASE)
# Célula que é só numeração — "3.2" ou "4, 7" — também é destino de seção.
RE_SO_NUMERO = re.compile(r"^[\s,;e]*\d+(?:\.\d+){0,3}(?:[\s,;e]+\d+(?:\.\d+){0,3})*[\s.]*$")


def secoes_numeradas(texto: str) -> set[str]:
    """Os números de seção que existem no documento: {'3', '3.1', '4'}."""
    saida: set[str] = set()
    for linha in texto.splitlines():
        m = RE_TITULO_MD.match(linha)
        titulo = m.group(2) if m else linha
        m2 = re.match(r"^\s*(\d+(?:\.\d+){0,3})[.)\s]", titulo)
        if m2 and (m or RE_TITULO_NUM.match(linha)):
            saida.add(m2.group(1).rstrip("."))
    return saida


def ancoras(destino: str) -> list[str]:
    """Os números de seção citados numa célula de destino.

    Só conta o que está marcado como seção — `§14`, `seção 3.2`, `item 4` — ou
    uma célula que é só numeração. Identificador de item (`CS-01`, `R-35`,
    `RN-04`) não é âncora de seção, e tratá-lo como tal foi o defeito que
    inundou uma revisão real de falso positivo.
    """
    marcadas = [m.group(1).rstrip(".") for m in RE_ANCORA.finditer(destino)]
    if marcadas:
        return marcadas
    if RE_SO_NUMERO.match(destino):
        return [n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+){0,3}", destino)]
    return []


def citado(ident: str, onde: str) -> bool:
    """RN-01 na matriz casa com RN-01, RN01, RN 1 e RN.001 no texto.

    A SDD é escrita por gente: ninguém normaliza o zero à esquerda.
    """
    prefixo, _, resto = ident.partition("-")
    numero = int(re.sub(r"\D", "", resto) or 0)
    alvo = re.escape(prefixo) + r"[\s\-–—_.]?0*" + str(numero) + r"(?!\d)"
    return re.search(alvo, onde, re.IGNORECASE) is not None


@dataclass
class Achado:
    severidade: str    # CRITICO | ALTO | MEDIO
    regra: str
    detalhe: str
    itens: list[str] = field(default_factory=list)


RE_TITULO_MATRIZ = re.compile(
    r"^(#{1,6})\s+.*matriz\s+de\s+rastreabilidade", re.IGNORECASE)


def recortar_matriz(texto: str) -> tuple[str, str]:
    """Recorta a seção da matriz, quando o documento tem uma.

    `ler_matriz` lê toda linha de tabela que comece com um ID. Isso está certo
    quando a matriz é o documento inteiro, e erra quando ela mora dentro da SDD:
    qualquer outra tabela cujas linhas comecem com identificador de duas a
    quatro letras entra junto.

    Numa execução real, uma seção de changelog com as linhas `| **PS-01** |` e
    `| **PS-02** |` — pendências de sistema, não requisitos de origem — virou
    duas linhas de matriz, e o conferidor acusou dois `[ALTO]` de "item da
    matriz sem origem" e dois de "item sem estado válido". Quatro falsos.

    Devolve `(trecho, de_onde)`. Sem título de matriz, devolve o texto inteiro e
    a string vazia — que é o caso da matriz em arquivo próprio.
    """
    linhas = texto.splitlines()
    inicio = nivel = None
    for n, linha in enumerate(linhas):
        m = RE_TITULO_MATRIZ.match(linha)
        if m:
            inicio, nivel = n, len(m.group(1))
            break
    if inicio is None:
        return texto, ""
    fim = len(linhas)
    for n in range(inicio + 1, len(linhas)):
        m = RE_TITULO_MD.match(linhas[n])
        if m and len(m.group(1)) <= nivel:
            fim = n
            break
    return "\n".join(linhas[inicio:fim]), linhas[inicio].strip("# ").strip()


def ler_matriz(caminho: Path) -> dict[str, dict]:
    """Lê a primeira coluna de toda linha de tabela markdown que comece com um ID.

    Quando o documento tem uma seção de matriz de rastreabilidade, lê **só**
    dela — ver `recortar_matriz`.
    """
    texto, _ = recortar_matriz(ler_documento(caminho))
    # `\**` desde o começo, e crase/aspas/sublinhado desde 2.25.2: a linha de
    # matriz aceitava `**RN-01**` e recusava `` `RN-01` ``. Aqui a assimetria
    # doía mais que no `classificar()` — a linha não CASAVA, então a matriz
    # inteira era declarada inexistente ("não achei nenhuma linha de matriz")
    # em vez de sair com uma contagem errada. A sessão que achou tirou as
    # crases do próprio documento para o comando passar.
    marca = r"(?:\*\*|\*|`|\"|_)*"
    padrao = re.compile(rf"^\|\s*{marca}([A-Z]{{2,4}}[\s\-–—_.]?\d{{1,4}}[a-zA-Z]?){marca}\s*\|(.*)$")
    saida: dict[str, dict] = {}
    for n, linha in enumerate(texto.splitlines(), 1):
        m = padrao.match(linha.strip())
        if not m:
            continue
        bruto = m.group(1)
        p = re.match(r"([A-Z]{2,4})", bruto).group(1)
        num = int(re.search(r"\d+", bruto).group())
        suf = re.search(r"\d+([a-zA-Z])", bruto)
        ident = f"{p}-{num:02d}" + (suf.group(1) if suf else "")
        celulas = [c.strip() for c in m.group(2).split("|")]
        estado = ""
        for c in celulas:
            if sem_acento(c.strip("* ")) in {sem_acento(e) for e in ESTADOS}:
                estado = c.strip("* ")
                break
        # O destino é a última célula com conteúdo que não seja o estado.
        destino = ""
        for c in reversed(celulas):
            limpo = c.strip("* ")
            if limpo and sem_acento(limpo) not in {sem_acento(e) for e in ESTADOS}:
                destino = limpo
                break
        saida.setdefault(ident, {"linha": n, "estado": estado, "destino": destino,
                                 "celulas": celulas, "repetido": 0})
        if saida[ident]["linha"] != n:
            saida[ident]["repetido"] += 1
    return saida


def cmd_conferir(args) -> int:
    matriz_caminho = Path(args.matriz).expanduser()
    origem_caminho = Path(args.origem).expanduser()
    prefixos = [p.strip().upper() for p in args.prefixos.split(",") if p.strip()]

    matriz = ler_matriz(matriz_caminho)
    _, secao_matriz = recortar_matriz(ler_documento(matriz_caminho))
    texto_origem = ler_documento(origem_caminho)
    secoes, ocorrencias = varrer(texto_origem, prefixos)
    origem = definicoes_unicas(ocorrencias)

    achados: list[Achado] = []

    if not matriz:
        raise MatrizError(
            f"não achei nenhuma linha de matriz em {matriz_caminho.name}. "
            "A matriz precisa ser uma tabela markdown com o identificador na "
            "primeira coluna."
        )

    faltando = [i for i in origem if i not in matriz]
    if faltando:
        achados.append(Achado("CRITICO", "item da origem fora da matriz",
                              f"{len(faltando)} identificadores estão no documento e "
                              "não aparecem na matriz", sorted(faltando)))

    sobrando = [i for i in matriz if i not in origem]
    if sobrando:
        achados.append(Achado("ALTO", "item da matriz sem origem",
                              f"{len(sobrando)} identificadores estão na matriz e não "
                              "foram achados no documento — confira se o número está "
                              "certo ou se é item que você criou", sorted(sobrando)))

    repetidos = [i for i, d in matriz.items() if d["repetido"]]
    if repetidos:
        achados.append(Achado("MEDIO", "item repetido na matriz",
                              "o mesmo identificador aparece em mais de uma linha",
                              sorted(repetidos)))

    sem_estado = [i for i, d in matriz.items() if not d["estado"]]
    if sem_estado:
        achados.append(Achado("ALTO", "item sem estado válido",
                              "nenhuma célula da linha bate com o vocabulário: "
                              + ", ".join(sorted(ESTADOS)), sorted(sem_estado)))

    vazias = [s for s in secoes if s.suspeita]
    if vazias:
        # MEDIO, não ALTO: seção vazia é sinal fraco. O sinal forte é a seção
        # que ANUNCIA um tipo e entrega zero, e esse tem achado próprio.
        achados.append(Achado("MEDIO", "seção da origem sem nenhum item",
                              "pode ser imagem que a extração perdeu, pode ser seção "
                              "que de fato não lista requisito — confira",
                              [f"L{s.linha} {s.titulo[:60]}" for s in vazias]))

    penduras = penduradas(ocorrencias)
    if penduras:
        achados.append(Achado("ALTO", "identificador citado e nunca definido",
                              "o documento se refere a itens que ele não define",
                              [f"{i} (L{ls[0]})" for i, ls in sorted(penduras.items())]))

    mentem = secoes_que_mentem(secoes, ocorrencias, prefixos)
    if mentem:
        achados.append(Achado("ALTO", "seção anuncia um tipo e não entrega nenhum",
                              "o título declara o tipo; zero itens significa extração "
                              "perdida",
                              [f"L{s.linha} {s.titulo[:50]} — zero {pref}"
                               for s, pref in mentem]))

    falta_num = lacunas(list(origem))
    if falta_num:
        achados.append(Achado("MEDIO", "lacuna de numeração na origem",
                              "confirme se o original pula ou se a extração perdeu",
                              [i for ids in falta_num.values() for i in ids]))

    if args.sdd:
        sdd_caminho = Path(args.sdd).expanduser()
        texto_sdd = ler_documento(sdd_caminho)
        corpo_sdd, bloco_fora = partir_sdd(texto_sdd)
        # As seções existentes vêm do documento INTEIRO, não do corpo. A seção
        # de exclusões costuma se chamar "Escopo e fora de escopo" e é retirada
        # do corpo de propósito — mas ela EXISTE, e item marcado fora de escopo
        # aponta para ela corretamente. Contando só o corpo, os quatro itens que
        # apontavam para a §16 de uma spec real foram acusados de apontar para
        # seção inexistente, que era exatamente onde deviam apontar.
        numeros = secoes_numeradas(texto_sdd)

        # Presente no corpo: especificado. Presente só no bloco de fora de
        # escopo: deixado de fora com justificativa. Em nenhum dos dois: sumiu.
        # Sem separar os dois, um item que só aparece na lista de exclusões
        # passa como se tivesse sido especificado.
        # Não exigimos que a prosa repita o identificador: uma SDD bem escrita
        # descreve o comportamento sem citar "RN-01" a cada parágrafo, e exigir
        # isso acusou 14 de 18 itens corretamente especificados. O que dá para
        # conferir por máquina é outra coisa: a matriz DECLARA um destino, e o
        # destino declarado EXISTE.
        justificados = [i for i in matriz if citado(i, bloco_fora)]

        sem_declaracao = [i for i, d in matriz.items()
                          if not d["destino"] and i not in justificados]
        if sem_declaracao:
            achados.append(Achado(
                "ALTO", "item da matriz sem destino declarado",
                "a linha da matriz não diz onde o item foi parar",
                sorted(sem_declaracao)))

        destino_inexistente = []
        for i, d in matriz.items():
            refs = ancoras(d["destino"])
            if not refs or not numeros:
                continue
            faltando = [r for r in refs if r not in numeros]
            if faltando:
                destino_inexistente.append(f"{i} → aponta {', '.join(faltando)}")
        if destino_inexistente:
            achados.append(Achado(
                "ALTO", "destino declarado que não existe na SDD",
                "a matriz manda para uma seção que o documento não tem",
                sorted(destino_inexistente)))

        marcados_fora = [i for i, d in matriz.items()
                         if sem_acento(d["estado"]) == sem_acento("Fora de escopo")]
        sem_justificativa = [i for i in marcados_fora if i not in justificados]
        if sem_justificativa:
            achados.append(Achado(
                "ALTO", "marcado fora de escopo sem constar da lista",
                "a matriz diz que o item ficou de fora, e a SDD não registra a "
                "justificativa nem o destino", sorted(sem_justificativa)))

    # ----------------------------------------------------------------------
    print(f"Matriz   {matriz_caminho}   {len(matriz)} itens")
    if secao_matriz:
        print(f"         lidos só de \"{secao_matriz}\" — tabela fora dela não conta")
    print(f"Origem   {origem_caminho}   {len(origem)} itens definidos, "
          f"{len(secoes)} seções")
    if args.sdd:
        print(f"SDD      {args.sdd}")
    print()

    if args.sdd and justificados:
        print(f"({len(justificados)} itens fora do corpo da SDD, justificados na "
              f"seção de fora de escopo: {', '.join(sorted(justificados))})")
        print()

    if not achados:
        print("Nenhum defeito mecânico. A matriz cobre a origem, os estados são")
        print("válidos, nenhuma seção saiu vazia e nada sumiu sem destino.")
        print()
        print("Isso NÃO diz que a análise está certa — só que está completa.")
        print("Contradição, cardinalidade e ambiguidade continuam sendo leitura sua.")
        return 0

    ordem = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2}
    for a in sorted(achados, key=lambda x: ordem[x.severidade]):
        print(f"[{a.severidade}] {a.regra}")
        print(f"  {a.detalhe}")
        mostra = a.itens[:20]
        for i in mostra:
            print(f"    {i}")
        if len(a.itens) > len(mostra):
            print(f"    ... e mais {len(a.itens) - len(mostra)}")
        print()

    grave = any(a.severidade in ("CRITICO", "ALTO") for a in achados)
    print("Corrija o que está acima antes de entregar. Um defeito mecânico daqui")
    print("custa uma auditoria inteira quando é o revisor que acha.")
    return 1 if grave else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="matrix", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extrair", help="varre o documento e devolve o esqueleto")
    e.add_argument("documento")
    e.add_argument("--prefixos", default=",".join(PREFIXOS_PADRAO))
    e.add_argument("--formato", default="tabela", choices=["tabela", "matriz", "json"])
    e.set_defaults(func=cmd_extrair)

    c = sub.add_parser("conferir", help="confere a matriz contra a origem e a SDD")
    c.add_argument("matriz")
    c.add_argument("--origem", required=True)
    c.add_argument("--sdd")
    c.add_argument("--prefixos", default=",".join(PREFIXOS_PADRAO))
    c.set_defaults(func=cmd_conferir)

    import casos as K
    K.montar(sub)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except MatrizError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    except K.CasosError as exc:
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
