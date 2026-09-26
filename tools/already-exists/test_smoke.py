#!/usr/bin/env python3
"""Teste de fumaça do 'já existe'. Cada caso saiu de um defeito real."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import already_exists as J  # noqa: E402

falhas = 0


def ok(cond, rotulo, detalhe=""):
    global falhas
    if cond:
        print(f"  [ok] {rotulo}")
    else:
        falhas += 1
        print(f"  [XX] {rotulo}" + (f"\n       {detalhe}" if detalhe else ""))


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


# --------------------------------------------------------------------------
print("Regressão: flexão não é conceito novo")
# --------------------------------------------------------------------------
for a, b in [("paginada", "paginacao"), ("encontra", "encontrar"),
             ("filtro", "filtros"), ("ordenacao", "ordenar"),
             ("pedido", "pedidos"), ("listagem", "listar")]:
    ok(J.radical(a) == J.radical(b), f"`{a}` e `{b}` caem no mesmo radical",
       f"{J.radical(a)} != {J.radical(b)}")

ok(J.radical("pedido") != J.radical("pedra"),
   "mas conceitos distintos continuam distintos",
   f"{J.radical('pedido')} vs {J.radical('pedra')}")
ok(len(J.radical("moeda")) >= J.MIN_RADICAL, "o radical não some por completo")

# --------------------------------------------------------------------------
print("\nGramática e vocabulário genérico saem")
# --------------------------------------------------------------------------
t = J.termos("O sistema deve permitir que o usuario visualize a tela de pedidos")
ok(not any(x.startswith("sistem") for x in t), "`sistema` não vira conceito")
ok(not any(x.startswith("usuari") for x in t), "`usuario` não vira conceito")
ok(any(x.startswith("pedid") for x in t), "mas `pedidos` vira", f"{list(t)}")
ok(J.termos("de a o os para com") == Counter(), "texto só de gramática sai vazio")
ok(J.termos("```python\nimport pedido\n```") == Counter(),
   "bloco de código não vira conceito")

# --------------------------------------------------------------------------
print("\nCobertura é assimétrica e ponderada")
# --------------------------------------------------------------------------
def doc(nome, texto):
    d = J.Documento(Path(nome), nome, J.termos(texto), nome)
    return d

demanda = J.termos("conciliacao bancaria com retentativa de liquidacao")
docs = [
    doc("cobre-tudo.md", "conciliacao bancaria retentativa liquidacao " * 3),
    doc("gigante-generico.md", ("integracao gateway webhook servico rotina " * 200)
        + " conciliacao"),
]
pesos = J.idf(docs)
J.pontuar(demanda, docs, pesos)
por_nome = {d.relativo: d for d in docs}
ok(por_nome["cobre-tudo.md"].cobertura > por_nome["gigante-generico.md"].cobertura,
   "documento curto que cobre tudo vence documento gigante que cita de passagem",
   f"{por_nome['cobre-tudo.md'].cobertura:.2f} vs "
   f"{por_nome['gigante-generico.md'].cobertura:.2f}")
ok(por_nome["cobre-tudo.md"].cobertura >= 0.99, "cobrir tudo dá cobertura cheia",
   f"{por_nome['cobre-tudo.md'].cobertura:.2f}")

# --------------------------------------------------------------------------
print("\nRegressão: o percentual é absoluto, não relativo ao topo")
# --------------------------------------------------------------------------
docs2 = [doc("longe-a.md", "assunto totalmente diferente rotina noturna"),
         doc("longe-b.md", "outro assunto diferente ainda relatorio mensal")]
pesos2 = J.idf(docs2)
J.pontuar(J.termos("conciliacao bancaria pix liquidacao"), docs2, pesos2)
melhor = max(d.cobertura for d in docs2)
ok(melhor < J.LIMIAR_PARCIAL,
   "sem nenhuma spec do assunto, o melhor caso fica abaixo do limiar",
   f"melhor cobertura {melhor:.2f}")

# --------------------------------------------------------------------------
print("\nPonta a ponta, num repositório de mentira")
# --------------------------------------------------------------------------
raiz = Path(tempfile.mkdtemp(prefix="ja-existe-teste-"))
(raiz / "docs" / "specs").mkdir(parents=True)
(raiz / ".agents" / "atividades").mkdir(parents=True)
(raiz / "docs" / "fora-de-escopo").mkdir(parents=True)
(raiz / ".agents" / "config.toml").write_text(
    '[docs]\nspecs = "docs/specs"\nfora_de_escopo = "docs/fora-de-escopo"\n',
    encoding="utf-8")
(raiz / "docs" / "specs" / "PAI-001-panel.md").write_text(
    "# PAI-001 Painel de grupos\n\nO painel lista grupos com moeda e valor do "
    "ponto. Permite filtrar por cliente e ordenar por data.\n" * 4, encoding="utf-8")
(raiz / "docs" / "specs" / "OUT-001-outro.md").write_text(
    "# OUT-001 Rotina noturna\n\nExpurgo de arquivos temporarios agendado.\n" * 4,
    encoding="utf-8")
# Três specs que compartilham vocabulário de MECANISMO e nada de domínio.
# Sem elas o empate no topo não tem como aparecer — a detecção precisa de três.
# Cada uma é MAJORITARIAMENTE domínio próprio, com só uma linha de mecanismo —
# que é a proporção real de uma spec. Se forem só mecanismo, a semelhança sobe e
# a condição que estamos testando não aparece.
for nome, dominio in (
    ("MEC-001-pedidos.md", "pedido entrega transportadora frete rastreio romaneio"),
    ("MEC-002-estoque.md", "estoque armazem inventario lote validade endereco"),
    ("MEC-003-fiscal.md", "nota fiscal tributo aliquota escrituracao apuracao"),
):
    corpo = f"# {nome}\n\n" + (f"{dominio} " * 12 + "\n") * 30
    corpo += ("A recusa por permissao lanca excecao com codigo de erro e objeto "
              "com message, e o frontend distingue o caso.\n")
    (raiz / "docs" / "specs" / nome).write_text(corpo, encoding="utf-8")

(raiz / "docs" / "fora-de-escopo" / "tema-escuro.md").write_text(
    "# Tema escuro\n\nRecusado em 2026-01-10: modo escuro nao entra nesta fase.\n",
    encoding="utf-8")
(raiz / ".agents" / "atividades" / "1001.md").write_text(
    "---\ntitulo: Painel de grupos de pedido\nstep: 3\n---\n", encoding="utf-8")
sh("git", "init", "-q", "-b", "main", cwd=raiz)
sh("git", "config", "user.email", "t@t", cwd=raiz)
sh("git", "config", "user.name", "t", cwd=raiz)
sh("git", "add", "-A", cwd=raiz)
sh("git", "commit", "-qm", "base", cwd=raiz)


def rodar(demanda, card=None):
    class Args:
        pass
    Args.demanda, Args.card, Args.saida = demanda, card, None
    anterior = Path.cwd()
    os.chdir(raiz)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            J.principal(Args())
        return buf.getvalue()
    finally:
        os.chdir(anterior)


saida = rodar("O painel de grupos deve listar grupos com moeda e valor do ponto, "
              "filtrando por cliente e ordenando por data de termino.")
ok("PAI-001-panel.md" in saida, "acha a spec dona")
ok("candidata a dona" in saida, "e a classifica como dona", saida[:400])
ok(saida.index("PAI-001") < saida.index("OUT-001") if "OUT-001" in saida else True,
   "a spec dona vem antes da irrelevante")
ok("1001" in saida, "acha a atividade anterior sobre o mesmo assunto")

saida2 = rodar("Expurgo de arquivos temporarios com agendamento noturno")
ok("tema-escuro" not in saida2 or "Nenhuma decisão antiga" in saida2,
   "memória de rejeição só aparece quando bate de verdade")

saida3 = rodar("Emissao de nota fiscal eletronica com assinatura digital "
               "e transmissao para a SEFAZ estadual")
ok("assunto novo" in saida3.lower(), "assunto sem dono é declarado novo", saida3[-600:])


# --------------------------------------------------------------------------
print("\nRegressão: vocabulário de mecanismo não tem dono")
# --------------------------------------------------------------------------
# Rodando o fluxo num BUG real, a demanda veio em vocabulário de mecanismo —
# recusa, excecao, erro, codigo — e a ferramenta anunciou como dona uma spec de
# upload em lote, que nao tem nada com o assunto. O sinal estava na forma: topo
# empatado com semelhanca baixa.
saida4 = rodar("A recusa por falta de permissao chega ao frontend sem codigo de "
               "erro. A excecao e lancada com uma string solta em vez de um "
               "objeto com code e message, e a tela nao consegue distinguir.")
ok("vocabulário em comum" in saida4 or "Sem dono" in saida4,
   "topo empatado com semelhança baixa não vira dono", saida4[:500])
linhas_tabela = [l for l in saida4.splitlines() if l.startswith("| `docs/")]
ok(not any("candidata a dona" in l for l in linhas_tabela),
   "e nenhuma spec é anunciada como dona", "\n".join(linhas_tabela))
ok("bug" in saida4.lower(), "a saída sugere o caminho certo para bug", saida4[:500])


# --------------------------------------------------------------------------
print("\nRegressão: a demanda que nomeia a spec")
# --------------------------------------------------------------------------
# Num card que citava CAM-001 pelo nome, a varredura apontou como dona uma spec
# de upload em lote. Citação explícita é o sinal mais forte que existe, e era
# ignorado.
(raiz / "docs" / "specs" / "CAM-001-fundacao.md").write_text(
    "# CAM-001 Fundacao do dominio\n\nRegra 9: o allowlist restringe o acesso "
    "os pedidos listados.\n" * 3, encoding="utf-8")
sh("git", "add", "-A", cwd=raiz)
sh("git", "commit", "-qm", "cam", cwd=raiz)

saida5 = rodar("O resumo ignora o allowlist. A regra ja esta escrita em CAM-001, "
               "regra 9, e a listagem de pedidos ja aplica esse filtro.")
ok("nomeia estas" in saida5, "a seção de citação aparece", saida5[:400])
ok("CAM-001-fundacao.md" in saida5.split("| Especificação")[0],
   "e a spec citada aparece ANTES do ranking cego", saida5[:600])
ok("citação ganha" in " ".join(saida5.split()),
   "com a instrução de que citação vence varredura", saida5[:600])

saida6 = rodar("O painel de grupos lista grupos com moeda e valor do ponto, "
               "filtrando por cliente.")
ok("nomeia estas" not in saida6,
   "e a seção não aparece quando a demanda não cita ninguém")


# --------------------------------------------------------------------------
print("\nRegressão: o card já corrigido")
# --------------------------------------------------------------------------
# Rodando o fluxo num card REAL que ja estava fechado e mesclado, a varredura
# acertou o dominio e nao disse a unica coisa que importava: que ja tinha sido
# corrigido. A resposta estava no history do git, e a ferramenta nao olhava.
(raiz / "corrigido.txt").write_text("ajuste\n", encoding="utf-8")
sh("git", "add", "-A", cwd=raiz)
sh("git", "commit", "-qm", "fix(99123) Desabilita o botao durante a requisicao", cwd=raiz)

saida7 = rodar("O botao de confirmacao permanece habilitado enquanto o sistema "
               "processa a requisicao, e clicar duas vezes gera erro.", card="99123")
ok("já foi corrigido" in saida7.lower(), "a seção de histórico aparece", saida7[:300])
ok("99123" in saida7 and "Desabilita o botao" in saida7,
   "e acha o commit que cita o card", saida7[:600])
ok("prova que alguém mexeu ali" in saida7 or "não prova que o defeito acabou" in saida7,
   "com o aviso de que commit mesclado não é prova de defeito resolvido")

saida8 = rodar("Emissao de nota fiscal eletronica com assinatura digital e "
               "transmissao para a SEFAZ estadual", card="99999")
ok("Nada no histórico cita" in saida8,
   "e não inventa histórico quando não há", saida8[-400:])

# --------------------------------------------------------------------------
print("\nRecusas")
# --------------------------------------------------------------------------
def erro(fn, trecho):
    try:
        fn()
        return False, "não levantou"
    except J.JaExisteError as e:
        return trecho.lower() in str(e).lower(), str(e)

cond, msg = erro(lambda: rodar("curto"), "menos de 20 caracteres")
ok(cond, "demanda curta demais recusa em vez de procurar no vazio", msg)
cond, msg = erro(lambda: rodar("de a o para com os as e ou mas nem que se"),
                 "nenhum conceito")
ok(cond, "demanda só de gramática recusa", msg)

# --------------------------------------------------------------------------
print("\nA saída é sinal, não decisão")
# --------------------------------------------------------------------------
ok("Sinal, não decisão" in saida, "declara isso ao leitor")
ok("nenhuma busca por termo encontra" in saida or "outro nome" in saida,
   "e avisa que o produto pode chamar o assunto de outro jeito")
ok("não se reabre" in saida, "diz o que fazer com atividade de mesmo id")

print()
if falhas:
    print(f"{falhas} FALHA(S)")
    sys.exit(1)
print("tudo passou")
