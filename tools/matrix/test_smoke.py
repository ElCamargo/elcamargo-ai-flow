#!/usr/bin/env python3
"""Teste de fumaça do extrator de matriz.

Cada caso aqui saiu de um defeito real observado, não de imaginação. Os que
começam com "regressão" quebraram numa execução de verdade.
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import matrix as M  # noqa: E402

falhas = 0
tmp = Path(tempfile.mkdtemp(prefix="matriz-teste-"))


def ok(cond, rotulo, detalhe=""):
    global falhas
    if cond:
        print(f"  [ok] {rotulo}")
    else:
        falhas += 1
        print(f"  [XX] {rotulo}" + (f"\n       {detalhe}" if detalhe else ""))


def escrever(nome: str, conteudo: str) -> Path:
    p = tmp / nome
    p.write_text(conteudo, encoding="utf-8")
    return p


def varrer(texto, prefixos=("RN", "RF", "RNF", "CA", "CT")):
    return M.varrer(texto, list(prefixos))


# --------------------------------------------------------------------------
print("Varredura: definição x menção")
# --------------------------------------------------------------------------
texto = """# 2 Regras
RN-01 - Primeira regra
O sistema faz algo conforme RN-01 e também RN-02.
RN-02 - Segunda regra
"""
secoes, oc = varrer(texto)
defs = M.definicoes_unicas(oc)
ok(sorted(defs) == ["RN-01", "RN-02"], "duas definições, citações não viram itens",
   f"achou {sorted(defs)}")
ok(sum(1 for o in oc if o.tipo == "mencao") == 2, "as duas citações contam como menção")

# --------------------------------------------------------------------------
print("\nVarredura: prefixo mais longo primeiro")
# --------------------------------------------------------------------------
secoes, oc = varrer("RNF-01 - Tempo de resposta\nRN-01 - Regra\n")
defs = M.definicoes_unicas(oc)
ok(sorted(defs) == ["RN-01", "RNF-01"], "RNF não é lido como RN seguido de F",
   f"achou {sorted(defs)}")

# --------------------------------------------------------------------------
print("\nVarredura: formas de identificador")
# --------------------------------------------------------------------------
secoes, oc = varrer("RN-01 a\nRN02 b\nRN 3 c\nRN.004 d\nRN-05a e\n")
defs = M.definicoes_unicas(oc)
ok(sorted(defs) == ["RN-01", "RN-02", "RN-03", "RN-04", "RN-05a"],
   "hífen, colado, espaço, ponto e sufixo de letra normalizam igual",
   f"achou {sorted(defs)}")

secoes, oc = varrer("RN-01 ok\nTURN-01 não\nBRN-02 não\nRN-0123456 não\n")
defs = M.definicoes_unicas(oc)
ok(sorted(defs) == ["RN-01"], "não casa no meio de outra palavra nem número gigante",
   f"achou {sorted(defs)}")

# --------------------------------------------------------------------------
print("\nRegressão: rodapé de página virava seção")
# --------------------------------------------------------------------------
texto = "\n".join(["3 de 6", "Página 2 de 7", "4 of 9", "2 REGRAS DE NEGÓCIO", "RN-01 x"])
secoes, oc = varrer(texto)
titulos = [s.titulo for s in secoes]
ok(titulos == ["2 REGRAS DE NEGÓCIO"], "rodapé não é seção",
   f"achou {titulos}")

# --------------------------------------------------------------------------
print("\nRegressão: título com etiqueta entre colchetes")
# --------------------------------------------------------------------------
texto = "3 [RF] REQUISITOS FUNCIONAIS\nRF-01 - Exibir menu\n"
secoes, oc = varrer(texto)
ok(len(secoes) == 1 and secoes[0].definicoes == 1,
   "'3 [RF] REQUISITOS FUNCIONAIS' é seção e recebe o item",
   f"secoes={[(s.titulo, s.definicoes) for s in secoes]}")

# --------------------------------------------------------------------------
print("\nRegressão: identificador citado e nunca definido")
# --------------------------------------------------------------------------
texto = "# Histórico\nAjuste de cardinalidade em RN-04 após revisão\n# Regras\nRN-01 - a\n"
secoes, oc = varrer(texto)
pend = M.penduradas(oc)
ok(list(pend) == ["RN-04"], "acha a referência pendurada", f"achou {list(pend)}")

# --------------------------------------------------------------------------
print("\nSeção que anuncia um tipo e entrega zero")
# --------------------------------------------------------------------------
texto = "2 [RN] REGRAS\nRN-01 - a\n3 [RF] REQUISITOS FUNCIONAIS\nParágrafo sem item.\n"
secoes, oc = varrer(texto)
mentem = M.secoes_que_mentem(secoes, oc, ["RN", "RF", "RNF", "CA", "CT"])
ok(len(mentem) == 1 and mentem[0][1] == "RF",
   "seção RF sem nenhum RF é denunciada", f"achou {[(s.titulo, p) for s, p in mentem]}")
ok(all(p != "RN" for _, p in mentem), "seção RN com RN não é denunciada")

# --------------------------------------------------------------------------
print("\nRegressão F-01: o item que é SUBTÍTULO conta para a seção de tipo")
# --------------------------------------------------------------------------
# A mesma execução dizia "2 RF" e "zero RF". A conferência agregava por
# `o.secao`, a seção MAIS INTERNA, e com `### RF-01` cada definição ficava na
# seção do próprio item — a de tipo, um nível acima, ficava com zero. Um
# documento cujos itens são subtítulos é a forma NORMAL, não a exceção.
# Repro de sete linhas, de `acme-backoffice-0f`, 10/09/2026.
texto = ("## 3 [RF] Requisitos Funcionais\n\n### RF-01 - um\n\ntexto\n"
         "\n### RF-02 - dois\n\ntexto\n")
secoes, oc = varrer(texto)
mentem = M.secoes_que_mentem(secoes, oc, ["RN", "RF", "RNF", "CA", "CT"])
ok(mentem == [],
   "seção de tipo cujos itens são subtítulos NÃO é denunciada",
   f"achou {[(s.titulo, p) for s, p in mentem]}")
ok(len([o for o in oc if o.tipo == 'definicao']) == 2,
   "e os dois itens continuam contados como definidos")

# E o verdadeiro continua acusando: o alcance de uma seção termina na próxima
# do mesmo nível, então o RN da seção seguinte não absolve a seção de RF.
texto = ("## 3 [RF] Requisitos Funcionais\n\nParágrafo sem item.\n"
         "\n## 4 [RN] Regras\n\n### RN-01 - uma\n\ntexto\n")
secoes, oc = varrer(texto)
mentem = M.secoes_que_mentem(secoes, oc, ["RN", "RF", "RNF", "CA", "CT"])
ok([p for _, p in mentem] == ["RF"],
   "e a seção RF de verdade vazia CONTINUA denunciada, sem herdar o RN vizinho",
   f"achou {[(s.titulo, p) for s, p in mentem]}")

# --------------------------------------------------------------------------
print("\nRegressão F-02: identificador entre crases em linha de tabela")
# --------------------------------------------------------------------------
# 27 casos de teste numa tabela de três colunas saíram como "CITADOS E NUNCA
# DEFINIDOS": tudo antes do identificador era marcação EXCETO a crase. Sem
# crase a mesma tabela já contava — o conserto fecha a incoerência entre duas
# formas da mesma coisa, e não abre uma classe nova.
texto = ("| Item | Título | Descrição |\n| --- | --- | --- |\n"
         "| `CT-01` | um | faz isso |\n| `CT-02` | dois | faz aquilo |\n"
         "\nO caso CT-01 cobre o fluxo.\n")
_, oc = varrer(texto)
definidos = {o.ident for o in oc if o.tipo == "definicao"}
ok(definidos == {"CT-01", "CT-02"},
   "a célula de tabela com crase vira definição", f"achou {sorted(definidos)}")
ok([o.ident for o in oc if o.tipo == "mencao"] == ["CT-01"],
   "e a citação em prosa continua sendo menção, não definição")

# O que NÃO pode mudar: prosa que começa com palavra segue menção.
_, oc = varrer("Segundo a regra RN-07, o saldo trava.\n")
ok([o.tipo for o in oc] == ["mencao"],
   "prefixo no meio de frase continua menção")

# --------------------------------------------------------------------------
print("\nRegressão F-02b: o LEITOR DE MATRIZ também tem que aceitar a crase")
# --------------------------------------------------------------------------
# A 2.25.1 consertou metade: `classificar()` passou a aceitar a crase e
# `ler_matriz` continuou recusando. E aqui a assimetria doía MAIS — a linha não
# casava, então a matriz inteira saía como "não achei nenhuma linha de matriz",
# em vez de uma contagem errada. Quem achou tirou as crases do próprio
# documento de 119 linhas para o comando passar.
doc = escrever("matriz-crase.md",
               "## Matriz\n\n| Item | Destino | Onde |\n| --- | --- | --- |\n"
               "| `RN-01` | implementado | src/a.ts |\n"
               "| **RN-02** | implementado | src/b.ts |\n"
               "| RN-03 | implementado | src/c.ts |\n")
lido = M.ler_matriz(doc)
ok(sorted(lido) == ["RN-01", "RN-02", "RN-03"],
   "as três formas — crase, negrito e nua — entram na matriz",
   f"leu {sorted(lido)}")
ok(lido.get("RN-01", {}).get("destino") == "src/a.ts",
   "e a linha com crase traz o destino, não só o identificador")

# --------------------------------------------------------------------------
print("\nLacunas de numeração")
# --------------------------------------------------------------------------
ok(M.lacunas(["RN-01", "RN-02", "RN-05"]) == {"RN": ["RN-03", "RN-04"]},
   "acha o buraco no meio da série")
ok(M.lacunas(["RN-01"]) == {}, "série de um item não inventa lacuna")
ok(M.lacunas(["RN-03", "RN-04"]) == {}, "série que começa em 3 não reclama de 1 e 2")

# --------------------------------------------------------------------------
print("\nLeitura de .docx, inclusive tabelas")
# --------------------------------------------------------------------------
def docx(paragrafos: list[tuple[str, str]], tabela: list[list[str]] | None = None) -> Path:
    corpo = ""
    for estilo, txt in paragrafos:
        est = f'<w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>' if estilo else ""
        corpo += f"<w:p>{est}<w:r><w:t>{txt}</w:t></w:r></w:p>"
    if tabela:
        linhas = ""
        for linha in tabela:
            celulas = "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>"
                              for c in linha)
            linhas += f"<w:tr>{celulas}</w:tr>"
        corpo += f"<w:tbl>{linhas}</w:tbl>"
    xml = ('<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
           + corpo + "</w:body></w:document>")
    p = tmp / "doc.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    p.write_bytes(buf.getvalue())
    return p


caminho = docx(
    [("Heading1", "2 REGRAS DE NEGOCIO"), ("", "Texto solto")],
    [["RN-01", "Primeira regra"], ["RN-02", "Segunda regra"]],
)
texto = M.ler_documento(caminho)
secoes, oc = varrer(texto)
defs = M.definicoes_unicas(oc)
ok("# 2 REGRAS DE NEGOCIO" in texto, "estilo Heading1 vira título markdown")
ok(sorted(defs) == ["RN-01", "RN-02"],
   "requisito em célula de tabela é definição, não menção", f"achou {sorted(defs)}")
ok(all(o.secao == "2 REGRAS DE NEGOCIO" for o in oc if o.tipo == "definicao"),
   "itens da tabela ficam na seção certa")

# --------------------------------------------------------------------------
print("\nRecusas: o silêncio é o inimigo")
# --------------------------------------------------------------------------
def erro(fn, trecho):
    try:
        fn()
        return False, "não levantou erro"
    except M.MatrizError as e:
        return (trecho.lower() in str(e).lower()), str(e)


vazio = escrever("vazio.md", "   \n\n  \n")
cond, msg = erro(lambda: M.ler_documento(vazio), "imagem")
ok(cond, "documento vazio recusa e explica que costuma ser imagem", msg)

cond, msg = erro(lambda: M.ler_documento(tmp / "nao-existe.md"), "não achei")
ok(cond, "arquivo ausente recusa", msg)

falso = tmp / "falso.docx"
falso.write_bytes(b"nao sou um zip")
try:
    M.ler_documento(falso)
    ok(False, "docx corrompido recusa")
except Exception as e:
    ok(not isinstance(e, SystemExit), "docx corrompido não passa em silêncio", str(e)[:60])

antigo = tmp / "antigo.doc"
antigo.write_bytes(b"\xd0\xcf\x11\xe0")
cond, msg = erro(lambda: M.ler_documento(antigo), ".doc")
ok(cond, ".doc antigo recusa com instrução", msg)

# --------------------------------------------------------------------------
print("\nLeitura da matriz preenchida")
# --------------------------------------------------------------------------
mat = escrever("matrix.md", """
| Item | Origem | Estado | Onde |
| --- | --- | --- | --- |
| RN-01 | L10 | Confirmado | secao 3 |
| **RN-02** | L14 | Confirmado com correção | secao 3 |
| RN03 | L20 | Fora de escopo | adiado |
| RN-04 | L24 |  | secao 4 |
texto solto que não é linha de tabela
""")
lido = M.ler_matriz(mat)
ok(sorted(lido) == ["RN-01", "RN-02", "RN-03", "RN-04"],
   "lê a primeira coluna, com negrito e sem hífen", f"achou {sorted(lido)}")
ok(lido["RN-02"]["estado"] == "Confirmado com correção",
   "estado com acento e espaço é reconhecido", lido["RN-02"]["estado"])
ok(lido["RN-04"]["estado"] == "", "linha sem estado válido fica sem estado")

# --------------------------------------------------------------------------
print("\nConferência ponta a ponta")
# --------------------------------------------------------------------------
origem = escrever("origem.md", """# 2 [RN] REGRAS
RN-01 - primeira
RN-02 - segunda
RN-03 - terceira
# 3 [RF] REQUISITOS FUNCIONAIS
RF-01 - efe um
""")
matriz_ok = escrever("m-ok.md", """
| Item | Estado | Onde foi parar |
| --- | --- | --- |
| RN-01 | Confirmado | §2 |
| RN-02 | Confirmado | §2 |
| RN-03 | Fora de escopo | adiado |
| RF-01 | Confirmado | §2 |
""")
sdd = escrever("sdd.md", """# Especificação
## 2. Comportamento
A regra RN-01 vira o comportamento X. RN.2 vira o comportamento Y.
O requisito RF 1 é atendido pelo endpoint.
## 3. Fora de escopo
RN-03 — adiado para a próxima fatia, decidido com o produto.
""")


class Args:
    def __init__(self, **kw):
        self.prefixos = "RN,RF,RNF,CA,CT"
        self.sdd = None
        self.__dict__.update(kw)


import contextlib  # noqa: E402

def rodar(**kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = M.cmd_conferir(Args(**kw))
    return codigo, buf.getvalue()

codigo, saida = rodar(matriz=str(matriz_ok), origem=str(origem), sdd=str(sdd))
ok(codigo == 0, "matriz completa passa", saida)
ok("[CRITICO]" not in saida,
   "citação como RN.2 e RF 1 na SDD conta como destino", saida)
ok("justificados na seção de fora de escopo" in saida,
   "item fora da SDD mas justificado é reportado sem virar defeito", saida)

matriz_furada = escrever("m-furada.md", """
| Item | Estado | Onde foi parar |
| --- | --- | --- |
| RN-01 | Confirmado | §2 |
| RN-09 | Confirmado | §2 |
| RF-01 |  | §2 |
""")
codigo, saida = rodar(matriz=str(matriz_furada), origem=str(origem), sdd=str(sdd))
ok(codigo == 1, "matriz furada reprova")
ok("RN-02" in saida and "RN-03" in saida, "aponta os itens da origem que faltam")
ok("sem origem" in saida and "RN-09" in saida, "aponta o item inventado")
ok("sem estado" in saida and "RF-01" in saida, "aponta o item sem estado")

vazia = escrever("m-vazia.md", "não tem tabela nenhuma aqui\n")
cond, msg = erro(lambda: M.cmd_conferir(Args(matriz=str(vazia), origem=str(origem))),
                 "nenhuma linha de matriz")
ok(cond, "matriz sem tabela recusa em vez de aprovar vazio", msg)


# --------------------------------------------------------------------------
print("\nRegressão: a matriz não é destino de si mesma")
# --------------------------------------------------------------------------
origem2 = escrever("origem2.md", """# 2 [RN] REGRAS
RN-01 - primeira
RN-02 - segunda
RN-03 - terceira
""")
# A SDD contém a matriz e especifica só RN-01. RN-02 aparece apenas na linha da
# matriz que afirma que ele foi especificado.
sdd2 = escrever("sdd2.md", """# Especificação

| Item | Estado | Onde |
| --- | --- | --- |
| RN-01 | Confirmado | secao 3 |
| RN-02 | Confirmado | secao 4 |
| RN-03 | Confirmado |  |

## 3. Comportamento
O endpoint de listagem devolve os grupos do cliente.
""")
codigo, saida = rodar(matriz=str(sdd2), origem=str(origem2), sdd=str(sdd2))
ok("não existe na SDD" in saida and "RN-02" in saida,
   "destino declarado que não existe é denunciado", saida)
ok("sem destino declarado" in saida and "RN-03" in saida,
   "célula de destino vazia é denunciada", saida)
ok("RN-01" not in saida.split("destino declarado")[-1].split("[")[0],
   "e o item cujo destino existe não é denunciado junto", saida)

# --------------------------------------------------------------------------
print("\nSeção vazia: pai e narrativa não contam")
# --------------------------------------------------------------------------
texto = """# Especificação
## 1. Contexto
Prosa que não lista requisito nenhum.
## 2. Requisitos
### 2.1 [RN] Regras
RN-01 - a
## 3. Fora de escopo
Nada aqui.
## 4. Anexos
"""
secoes, oc = varrer(texto)
suspeitas = [s.titulo for s in secoes if s.suspeita]
ok(suspeitas == ["4. Anexos"],
   "só a seção folha, não narrativa e sem itens, fica suspeita",
   f"achou {suspeitas}")


# --------------------------------------------------------------------------
print("\nRegressão: identificador de item não é âncora de seção")
# --------------------------------------------------------------------------
# Numa spec real, o marcador de seção era OPCIONAL no regex e qualquer número
# virava âncora: `CS-01` lia "01", `§8 R-35` lia "8" e "35". Resultado: setenta
# e dois falsos [ALTO] de "destino inexistente" numa revisão de verdade.
ok(M.ancoras("CS-01") == [], "`CS-01` não é âncora de seção")
ok(M.ancoras("CS-01 e CS-14") == [], "nem uma lista de critérios")
ok(M.ancoras("R-35, R-46") == [], "nem identificadores de regra")
ok(M.ancoras("§12, §14") == ["12", "14"], "mas `§` marca seção", f"{M.ancoras('§12, §14')}")
ok(M.ancoras("secao 3.2") == ["3.2"], "e `secao` também")
ok(M.ancoras("Seção 5") == ["5"], "com acento e maiúscula")
ok(M.ancoras("item 4") == ["4"], "e `item`")
ok(M.ancoras("3.2") == ["3.2"], "célula que é só numeração conta como seção")
ok(M.ancoras("adiado para a próxima fatia") == [], "e prosa não vira âncora")
ok(M.ancoras("§8 R-35") == ["8"], "num destino misto, só o que está marcado",
   f"{M.ancoras('§8 R-35')}")


# --------------------------------------------------------------------------
print("\nRegressão: a seção de exclusões existe, mesmo saindo do corpo")
# --------------------------------------------------------------------------
# Numa spec real a seção 16 se chama "Escopo e fora de escopo": partir_sdd a
# retira do corpo de proposito, e contando as secoes so' do corpo os quatro
# itens que apontavam para ela — os marcados Fora de escopo, apontando para
# onde deviam — foram acusados de apontar para secao inexistente.
origem3 = escrever("origem3.md", """# 2 [RN] REGRAS
RN-01 - primeira
RN-02 - segunda
""")
sdd3 = escrever("sdd3.md", """# Especificação

| Item | Estado | Onde foi parar |
| --- | --- | --- |
| RN-01 | Confirmado | §3 |
| RN-02 | Fora de escopo | §16 |

## 3. Comportamento
O endpoint devolve a listagem.

## 16. Escopo e fora de escopo
RN-02 — adiado para a próxima fatia, decidido com o produto.
""")
codigo, saida9 = rodar(matriz=str(sdd3), origem=str(origem3), sdd=str(sdd3))
ok("não existe na SDD" not in saida9,
   "apontar para a seção de exclusões não é destino inexistente", saida9)
ok("[ALTO]" not in saida9 and "[CRITICO]" not in saida9,
   "e o conjunto passa limpo", saida9)

# --------------------------------------------------------------------------
print("\nTabela fora da seção da matriz não vira linha de matriz")
# --------------------------------------------------------------------------
# Numa spec real, uma seção de changelog com as linhas `| **PS-01** |` e
# `| **PS-02** |` — pendências de sistema, não requisitos de origem — foi lida
# como matriz e produziu quatro [ALTO] falsos.
origem_ps = escrever("origem-ps.md", """
# 1 REGRAS
RN-01 - a primeira
RN-02 - a segunda
""")
sdd_ps = escrever("sdd-ps.md", """
# Especificação

## 2. Corpo

Trata de RN-01 e de RN-02 na §2.

## 21. Matriz de rastreabilidade da origem

| Item | Estado | Onde foi parar |
| --- | --- | --- |
| RN-01 | Confirmado | §2 |
| RN-02 | Confirmado | §2 |

## 23. O que mudou nesta revisão

| # | Resposta | Efeito |
| --- | --- | --- |
| **PS-01** | Contrato anônimo | Pendência fechada |
| **PS-02** | Só Master | Pendência fechada |
""")
codigo, saida = rodar(matriz=str(sdd_ps), origem=str(origem_ps), sdd=str(sdd_ps))
ok(codigo == 0, "changelog com PS-01/PS-02 não reprova a matriz", saida)
ok("120 itens" not in saida and "2 itens" in saida,
   "só as duas linhas da seção da matriz foram lidas", saida)
ok("lidos só de" in saida and "Matriz de rastreabilidade" in saida,
   "e o recorte é declarado, não silencioso", saida)

sem_secao = escrever("m-solta.md", """
| Item | Estado | Onde foi parar |
| --- | --- | --- |
| RN-01 | Confirmado | §2 |
| RN-02 | Confirmado | §2 |
""")
codigo, saida = rodar(matriz=str(sem_secao), origem=str(origem_ps), sdd=str(sdd_ps))
ok(codigo == 0, "matriz em arquivo próprio, sem título de seção, continua lida inteira", saida)
ok("lidos só de" not in saida, "e nesse caso não anuncia recorte nenhum", saida)

# --------------------------------------------------------------------------
print("\nEsqueleto para colar")
# --------------------------------------------------------------------------
doc = escrever("pipe.md", "# Regras\nRN-01 - texto com | barra dentro\n")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    M.cmd_extrair(Args(documento=str(doc), formato="matriz"))
linha = [l for l in buf.getvalue().splitlines() if "RN-01" in l][0]
ok(linha.count("|") - linha.count("\\|") == 6,
   "barra no texto é escapada e não quebra a tabela", linha)

# --------------------------------------------------------------------------
print("\nContrato de casos: quem escreve `passa` é a suíte")
# --------------------------------------------------------------------------
import json as _json  # noqa: E402
import os as _os  # noqa: E402
import subprocess as _sp  # noqa: E402

proj = tmp / "casos-proj"
(proj / ".agents" / "atividades").mkdir(parents=True)
(proj / ".agents" / "elcamargo-flow").mkdir()
(proj / ".agents" / "config.toml").write_text('[projeto]\nnome = "t"\n', encoding="utf-8")
(proj / "docs").mkdir()
sdd_c = proj / "docs" / "sdd.md"
sdd_c.write_text("""# Testes esperados

| Caso | Descrição |
| --- | --- |
| CT-01 | Dado cupom válido, então desconto |
| CT-02 | Dado cupom vencido, então 422 |
""", encoding="utf-8")
(proj / "src").mkdir()
(proj / "src" / "cupom.spec.ts").write_text(
    "it('CT-01 aplica desconto', () => {})\n// CT-02\nit('recusa vencido', () => {})\n",
    encoding="utf-8")
_env = {**_os.environ, "ELCAMARGO_AGENTS_DIR": str(proj / ".agents")}
_FS = str(Path(__file__).resolve().parents[1] / "flow-state" / "flow_state.py")
_MX = str(Path(__file__).resolve().parent / "matrix.py")


def _r(cmd, entrada=None):
    r = _sp.run([sys.executable, *cmd], capture_output=True, text=True, cwd=str(proj),
                env=_env, input=entrada, encoding="utf-8", timeout=120)
    return r.returncode, r.stdout + r.stderr


_r([_FS, "iniciar", "C1", "--titulo", "t", "--trilha", "curta"])
contrato = proj / ".agents" / "atividades" / "C1-casos.json"
c, o = _r([_MX, "casos", "gerar", "--atividade", "C1", "--sdd", str(sdd_c)])
d = _json.loads(contrato.read_text())
ok(c == 0 and [x["id"] for x in d["casos"]] == ["CT-01", "CT-02"],
   "gerar lê um caso por CT da SDD", o)
ok(all(x["passa"] is False for x in d["casos"]), "e todos nascem com passa: false")
ok("|" not in d["casos"][0]["texto"], "o texto guardado é para ler, sem as barras da tabela",
   d["casos"][0]["texto"])
ativ = (proj / ".agents" / "atividades" / "C1.md").read_text()
ok("| casos | exigida |" in ativ, "e grava `casos` exigida na tabela da atividade")
c, o = _r([_MX, "casos", "gerar", "--atividade", "C1", "--sdd", str(sdd_c)])
ok(c != 0 and "--refazer" in o, "não sobrescreve o contrato sem --refazer", o)

vermelho = (" FAIL  src/cupom.spec.ts > CT-01 aplica desconto\n"
            " FAIL  src/cupom.spec.ts > recusa vencido\n")
c, o = _r([_MX, "casos", "vermelho", "--atividade", "C1", "--formato", "vitest", "-"], vermelho)
ok("2 de 2" in o, "fase vermelha: id no nome e id em comentário do arquivo valem", o)
c, o = _r([_MX, "casos", "verde", "--atividade", "C1", "--codigo", "1", "--formato", "vitest", "-"],
          " FAIL  src/cupom.spec.ts > CT-01 aplica desconto\n")
d = _json.loads(contrato.read_text())
ok(c == 1 and d["casos"][0]["passa"] is False,
   "verde com o caso entre as falhas: continua sem prova", o)
c, o = _r([_MX, "casos", "verde", "--atividade", "C1", "--codigo", "1", "-"], "algo quebrou\n")
ok(c == 1 and "0 de 2" in o, "saída vermelha sem falha nomeada não prova caso nenhum", o)
c, o = _r([_MX, "casos", "verde", "--atividade", "C1", "--codigo", "0", "-"], "ok\n")
ok(c == 0 and "2 de 2" in o, "suíte verde prova os casos que têm teste", o)
ativ = (proj / ".agents" / "atividades" / "C1.md").read_text()
ok(ativ.rstrip().splitlines()[-1].startswith("|") and "| casos | ok |" in ativ,
   "e a última conferência `casos` passa a ok")

c, o = _r([_MX, "conferir-testes", "--atividade", "C1", "--raiz", "."])
ok(c == 0 and "[ALTO]" not in o, "conferir-testes: contrato, SDD e testes batem", o)
sdd_c.write_text(sdd_c.read_text().replace("então 422", "então 409")
                 + "| CT-03 | Dado cupom esgotado, então 410 |\n", encoding="utf-8")
c, o = _r([_MX, "conferir-testes", "--atividade", "C1", "--raiz", "."])
ok(c == 1 and "CT-03" in o and "CT-02" in o,
   "SDD mudou depois do contrato: caso novo e caso alterado viram ALTO", o)
c, o = _r([_MX, "casos", "gerar", "--atividade", "C1", "--sdd", str(sdd_c), "--refazer"])
d = {x["id"]: x for x in _json.loads(contrato.read_text())["casos"]}
ok(d["CT-01"]["passa"] is True and d["CT-02"]["passa"] is False and d["CT-03"]["passa"] is False,
   "--refazer guarda só o estado do caso cujo texto não mudou", o)
c, o = _r([_MX, "conferir-testes", "--atividade", "C1", "--raiz", "."])
ok(c == 1 and "CT-03" in o, "caso sem teste que cite o id é ALTO", o)

# --------------------------------------------------------------------------
print()
if falhas:
    print(f"{falhas} FALHA(S)")
    sys.exit(1)
print("tudo passou")
