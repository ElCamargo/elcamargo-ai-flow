#!/usr/bin/env python3
"""Escreve o `config.toml` do projeto sem destruir o que ele explica.

O `config.example.toml` tem 353 linhas, e a maior parte é **comentário que diz
o que a chave faz e quando vale a pena ligá-la**. Um escritor que releia o TOML
para um dicionário e regrave o arquivo joga tudo isso fora — e o próximo humano
encontra 48 chaves sem explicação nenhuma.

Por isso aqui não há serialização de arquivo inteiro. Há **cirurgia de linha**:
acha a chave dentro da seção certa e troca só aquela linha. O resto do arquivo
não é tocado, e o teste prende isso — ele conta as linhas que mudaram.

Stdlib apenas. `tomllib` (Python 3.11+) lê; escrever TOML não existe na stdlib,
e trazer `tomlkit` quebraria a regra do pacote de não ter dependência externa.
O subconjunto de valores que este config usa é pequeno o bastante para caber em
`como_toml()`.

    configure.py iniciar                      cria o config a partir do exemplo
    configure.py detectar                     o que o repositorio responde sozinho
    configure.py estado                       o que falta, e o que trava por faltar
    configure.py definir <chave> <valor>      escreve UMA chave
"""
from __future__ import annotations

import argparse
import difflib
from datetime import date
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

PACOTE = Path(__file__).resolve().parents[2]
EXEMPLO = PACOTE / "config.example.toml"


class ConfigError(Exception):
    """Erro que a pessoa consegue consertar, e cuja mensagem diz como."""


class Args:
    """Mesmo andaime que as outras ferramentas usam para chamar sem argparse."""

    def __init__(self, **kw):
        self.__dict__.setdefault("raiz", ".")
        self.__dict__.setdefault("chave", None)
        self.__dict__.setdefault("valor", None)
        self.__dict__.update(kw)


# ---------------------------------------------------------------- serialização

def como_toml(valor: Any) -> str:
    """O subconjunto de TOML que este config usa, e nada além dele.

    Booleano vem ANTES de inteiro de propósito: em Python `True` é instância de
    `int`, e testar `int` primeiro escreveria `1` onde o TOML precisa de `true`.
    """
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, str):
        escapado = valor.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escapado}"'
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, (list, tuple)):
        return "[" + ", ".join(como_toml(v) for v in valor) + "]"
    raise ConfigError(f"não sei escrever {type(valor).__name__} em TOML: {valor!r}")


def do_texto(bruto: str) -> Any:
    """O que veio da linha de comando, no TIPO que o TOML precisa.

    Tudo que chega pelo shell é `str`. Sem esta conversão, `definir
    metricas.publicar_no_repo false` escrevia `publicar_no_repo = "false"` — uma
    **string**, que em Python é verdadeira. O interruptor de desligar ligava.

    Medido ao ligar a publicação no `acme-backoffice`: a chave saiu
    como `"true"` e funcionou por acidente, porque string não vazia é verdadeira.
    `"false"` teria funcionado do mesmo jeito, e ninguém descobriria por
    tentativa — descobriria por um `docs/` que continua sendo regravado depois
    de alguém jurar ter desligado.

    Número idem: `orcamento_usd = "1500"` não compara com float em lugar nenhum.

    O que NÃO é convertido continua string, que é o tipo certo para caminho,
    comando e nome de skill.
    """
    # Chamada de dentro do pacote já passa o tipo pronto; só o que vem do shell
    # chega como texto. O teste da 2.9.0 chama com `50.0` e pegou isto.
    if not isinstance(bruto, str):
        return bruto
    t = bruto.strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    for tipo in (int, float):
        try:
            return tipo(t)
        except ValueError:
            pass
    return bruto


# ------------------------------------------------------------------- o esquema

# O `(?:\[)?...(?:\])?` interno cobre `[[array.de.tabelas]]`. Sem ele o header
# não casava, `secao` seguia sendo a de cima, e as chaves do bloco entravam na
# seção ERRADA — o exemplo de `[[perfis.padroes]]` apareceu como três chaves
# órfãs de `[perfis]` em 22/09/2026. Vale para comentado e não comentado.
RE_SECAO = re.compile(r"^\s*(?:#\s*)?\[\[?([A-Za-z0-9_.]+)\]\]?\s*$")
RE_CHAVE = re.compile(r"^(\s*)(#\s*)?([A-Za-z0-9_]+)\s*=\s*(.*)$")

# Seções cujos nomes de chave são escolhidos pelo PROJETO, não pelo esquema.
# `[catraca.formatos]` recebe um nome por formato de saída que o projeto usa;
# `[perfis]` recebe um por perfil de acesso. Não dá para enumerá-las num
# roteiro, e fingir que dá faria o /config perguntar por chaves inventadas.
SECOES_ABERTAS = ("catraca.formatos", "catraca.padroes", "perfis.atores",
                  "perfis.padroes")


def _e_mesmo_uma_chave(nome: str, resto: str) -> bool:
    """`# Vazio = o step 1 usa o comportamento genérico` NÃO é chave comentada.

    Medido no primeiro uso: o índice pegou essa linha de prosa do `[git]` e
    passou a oferecer `git.Vazio` como chave declarável. O critério que separa
    prosa de chave não é heurística de maiúscula — é se o TOML aceita.
    """
    try:
        tomllib.loads(f"{nome} = {resto}")
        return True
    except (tomllib.TOMLDecodeError, ValueError):
        return False


def indexar(linhas: list[str]) -> dict[str, dict]:
    """Mapeia `secao.chave` -> onde ela está e em que estado.

    Guarda também as chaves COMENTADAS. Elas não são lixo: `orcamento_usd` e
    `assinaturas_usd_mes` vivem comentadas com a explicação em cima, e declarar
    uma delas é descomentar a linha — não inserir outra embaixo, o que deixaria
    a explicação órfã e a chave sem contexto.
    """
    indice: dict[str, dict] = {}
    secao = ""
    for n, linha in enumerate(linhas):
        m = RE_SECAO.match(linha)
        if m:
            secao = m.group(1)
            continue
        m = RE_CHAVE.match(linha)
        if not m or not secao:
            continue
        recuo, comentada, chave, resto = m.groups()
        if comentada and not _e_mesmo_uma_chave(chave, resto):
            continue
        if any(secao == a or secao.startswith(a) for a in SECOES_ABERTAS):
            continue
        caminho = f"{secao}.{chave}"
        # Só a PRIMEIRA ocorrência conta. Um comentário de exemplo mais abaixo
        # (`# lint = "eslint"` dentro da explicação da catraca) não pode
        # sequestrar a chave real que está acima dele.
        if caminho in indice:
            continue
        indice[caminho] = {
            "linha": n,
            "comentada": bool(comentada),
            "recuo": recuo,
            # Valor que abre `"""` e não fecha na mesma linha é multilinha: a
            # cirurgia de uma linha só o partiria ao meio.
            "multilinha": resto.startswith('"""') and not resto.rstrip().endswith('"""'),
        }
    return indice


def _linhas_do_exemplo() -> list[str]:
    return EXEMPLO.read_text(encoding="utf-8").splitlines()


def _comentario_acima(linhas: list[str], n: int) -> list[str]:
    """As linhas de comentário coladas acima de `n`, na ordem original.

    Para quando encontra linha em branco ou qualquer coisa que não seja
    comentário: o bloco de uma chave é o que está grudado nela, e não a
    explicação da chave anterior.
    """
    i = n - 1
    while i >= 0 and linhas[i].lstrip().startswith("#"):
        i -= 1
    return linhas[i + 1:n]


def bloco_do_exemplo(chave: str) -> tuple[str, list[str]]:
    """A chave, o valor padrão dela, e a explicação que vem junto.

    O comentário não é enfeite. Metade do `config.example.toml` é explicação, e
    é por isso que o `iniciar` copia byte a byte em vez de gerar o arquivo do
    esquema. Inserir a chave sozinha deixaria no config do projeto uma linha sem
    contexto — pior que a ausência, porque parece decidida por alguém.
    """
    linhas = _linhas_do_exemplo()
    n = indexar(linhas)[chave]["linha"]
    secao = chave.rsplit(".", 1)[0]
    # A linha vem SEM o `#` de comentário: quem está declarando quer o valor
    # ativo, e a chave comentada no exemplo é a forma de dizer "não declarado".
    m = RE_CHAVE.match(linhas[n])
    recuo, _, nome, resto = m.groups()
    return secao, _comentario_acima(linhas, n) + [f"{recuo}{nome} = {resto}"]


def padrao_do_esquema(chave: str):
    """O valor que a chave tem no `config.example.toml`, já convertido."""
    linhas = _linhas_do_exemplo()
    n = indexar(linhas)[chave]["linha"]
    m = RE_CHAVE.match(linhas[n])
    try:
        return tomllib.loads(f"{m.group(3)} = {m.group(4)}")[m.group(3)]
    except (tomllib.TOMLDecodeError, ValueError):
        return None


MARCA_DIVERGE = "# Declarado como "


def anotar_divergencia(linhas: list[str], onde: int, chave: str, valor,
                      pode_criar: bool = True) -> list[str]:
    """Diz no arquivo que o valor escrito não é o padrão do pacote.

    Sem isto o `definir` produzia contradição: o comentário que vem do esquema
    fala do PADRÃO, o valor escrito é o que alguém pediu, e quando os dois
    diferem o arquivo passa a se contradizer três linhas depois. Foi achado no
    config de outro projeto, com `# NASCE off` em cima de `figma_escrita = "on"`.

    Inserir a linha nua deixava o valor sem contexto; trazer o comentário do
    esquema deixou o valor com contexto que MENTE — que é pior, porque parece
    informação. A saída não é escolher entre os dois: é declarar a diferença.

    Só vale para o bloco que NÓS inserimos. Numa chave que já estava no arquivo o
    comentário acima é do projeto, e a cirurgia promete mexer numa linha só — três
    asseveracões guardam isso, e elas estão certas.
    """
    padrao = padrao_do_esquema(chave)
    anterior = linhas[onde - 1] if onde > 0 else ""
    ja_tem = anterior.lstrip().startswith(MARCA_DIVERGE)
    if padrao is None or valor == padrao:
        # Voltou ao padrão: a nota vira ruído e sai.
        if ja_tem:
            del linhas[onde - 1]
        return linhas
    if not ja_tem and not pode_criar:
        # Arquivo curado por gente: não entra linha sem pedir. Mas quem rodou
        # precisa saber que o comentário logo acima fala do padrão, e o valor
        # que acabou de ser escrito não é ele — senão a contradição fica no
        # arquivo e ninguém foi avisado.
        if anterior.lstrip().startswith("#"):
            print(f"  aviso: o comentário acima de `{chave.rsplit('.', 1)[1]}` "
                  f"explica o padrão do pacote, que é {como_toml(padrao)}.")
            print(f"  O valor escrito é {como_toml(valor)}. Vale uma linha "
                  f"dizendo por quê — não entra sozinha em arquivo seu.")
        return linhas
    nota = (f"{MARCA_DIVERGE}{como_toml(valor)} em {date.today():%d/%m/%Y} — "
            f"o padrão do pacote é {como_toml(padrao)}.\n")
    if ja_tem:
        linhas[onde - 1] = nota
    else:
        linhas.insert(onde, nota)
    return linhas


def cabecalho_da_secao(secao: str) -> list[str]:
    """O `[secao]` e o bloco de comentário que o apresenta.

    Tolera UMA linha em branco entre o bloco e o cabeçalho, porque é a convenção
    do arquivo: a explicação da seção vem numa moldura de `# ---`, um branco, e
    então o `[secao]`. Sem essa tolerância a seção entrava nua no config do
    projeto — e é justamente a explicação dela que diz por que ela existe.
    """
    linhas = _linhas_do_exemplo()
    for n, linha in enumerate(linhas):
        m = RE_SECAO.match(linha)
        if not (m and m.group(1) == secao and not linha.lstrip().startswith("#")):
            continue
        acima = _comentario_acima(linhas, n)
        if not acima and n > 0 and not linhas[n - 1].strip():
            acima = _comentario_acima(linhas, n - 1)
            if acima:
                acima = acima + [""]
        return acima + [linha]
    return [f"[{secao}]"]


def chaves_do_exemplo() -> list[str]:
    return sorted(indexar(EXEMPLO.read_text(encoding="utf-8").splitlines()))


# ------------------------------------------------------------------- o roteiro
# A ordem é a ordem em que as coisas TRAVAM, e não a ordem do arquivo. Quem
# parar no meio da entrevista sai com um projeto que roda até onde respondeu.

# `essenciais` são as chaves de que a `trava` fala. As outras do bloco são
# opcionais: ausentes, o fluxo roda — só não roda AQUELA parte.
#
# Medido rodando a entrevista: o bloco de gates avisava "sem comando de lint,
# teste e build o step 9 não tem o que rodar" com os três JÁ declarados, porque
# faltavam `visual` e `qualidade_de_tela`. É a mesma classe do rótulo do prazo
# que dizia "até a entrega" sem entrega: a mensagem promete o que o dado não
# diz, e quem lê corre atrás do alarme errado.
ROTEIRO = [
    {
        "bloco": "projeto", "ordem": 1, "essenciais": ["projeto.nome"],
        "titulo": "O projeto",
        "trava": "sem `nome`, todo relatório e todo painel saem sem identidade",
        "chaves": ["projeto.nome", "projeto.descricao", "projeto.idioma_docs"],
    },
    {
        "bloco": "fluxo", "ordem": 2, "essenciais": ["fluxo.steps"],
        "titulo": "Quais steps valem aqui",
        "trava": "sem `steps`, o fluxo assume os dez e cobra portões que este projeto talvez não queira",
        "chaves": ["fluxo.steps", "fluxo.segundos_de_step_relampago"],
    },
    {
        "bloco": "git", "ordem": 3, "essenciais": ["board.tipo", "anexos.backend"],
        "titulo": "Board e Git",
        "trava": "sem `board.tipo`, o step 1 não sabe de onde ler o card, e passa a pedir o texto colado",
        "chaves": ["board.tipo", "board.org", "board.projeto", "board.repo",
                   "board.tag_meia_entrega",
                   "git.skill", "anexos.backend", "anexos.azure.org",
                   "anexos.azure.projeto", "anexos.github.pasta"],
    },
    {
        "bloco": "docs", "ordem": 4, "essenciais": ["docs.specs"],
        "titulo": "Onde ficam os documentos",
        "trava": "sem isto, os steps 2, 3 e 4 escrevem SDD sem achar convenção nem ADR, e repetem decisão já tomada",
        "chaves": ["docs.specs", "docs.convencoes", "docs.adrs", "docs.fora_de_escopo",
                   "docs.classes_de_defeito"],
    },
    {
        "bloco": "stack", "ordem": 5, "essenciais": ["stack.linguagens"],
        "titulo": "A stack",
        "trava": "sem isto, os steps 8 e 9 revisam sem saber a linguagem nem os temas de segurança que valem",
        "chaves": ["stack.linguagens", "stack.runtime", "stack.frameworks", "stack.temas",
                   "leitura.ignorar"],
    },
    {
        "bloco": "gates", "ordem": 6, "essenciais": ["gates.lint", "gates.test", "gates.build"],
        "titulo": "Os portões mecânicos",
        "trava": "sem comando de lint, teste e build, o step 9 não tem o que rodar e a entrega passa sem conferência",
        "chaves": ["gates.lint", "gates.test", "gates.build", "gates.visual",
                   "gates.qualidade_de_tela", "gates.sast", "gates.deps_audit",
                   "catraca.arquivo"],
    },
    {
        "bloco": "frontend", "ordem": 7, "essenciais": ["frontend.componentes"],
        "titulo": "Telas, componentes e tokens",
        "trava": "sem isto, o step 6 desenha sem os componentes que o projeto já tem, e inventa o que já existe",
        "chaves": ["frontend.prototipos", "frontend.componentes", "frontend.tokens",
                   "frontend.gate_de_tela", "frontend.larguras"],
    },
    {
        "bloco": "perfis", "ordem": 8, "essenciais": [],
        "titulo": "Perfis de acesso",
        "trava": "sem isto, a frente de segurança do step 9 não consegue exercitar permissão, e declara a dimensão não coberta",
        "chaves": ["perfis.comando", "perfis.injecao", "perfis.ambiente"],
    },
    {
        "bloco": "producao", "ordem": 8, "essenciais": [],
        "titulo": "O build de produção atrás do host público",
        "trava": "nada trava — mas sem isto a frente de execução do step 9 só vê o sistema como quem desenvolve, e declara a dimensão não coberta",
        "chaves": ["producao.subir", "producao.escuta", "producao.origem_publica",
                   "producao.rotas"],
    },
    {
        "bloco": "metricas", "ordem": 9, "essenciais": [],
        "titulo": "Medição e custo",
        "trava": "nada trava — mas sem `assinaturas_usd_mes` o custo sai só em tabela de API, que é o teto que ninguém paga",
        "chaves": ["metricas.ligado", "metricas.teto_leitura_min", "metricas.reentrada_min",
                   "metricas.orcamento_usd", "metricas.assinaturas_usd_mes",
                   "metricas.publicar_no_repo", "metricas.publicar_em",
                   "metricas.precos.entrada", "metricas.precos.cache_escrita",
                   "metricas.precos.cache_leitura", "metricas.precos.saida"],
    },
    {
        "bloco": "relatorios", "ordem": 10, "essenciais": [],
        "titulo": "PDF e identidade do documento",
        "trava": "nada trava — o gerador de PDF usa o padrão Elcamargo até isto ser declarado",
        "chaves": ["relatorios.saida", "relatorios.rodape",
                   "documento.operador", "documento.cliente", "documento.produto",
                   "documento.classificacao", "documento.classificacao_texto",
                   "documento.fornecedor.nome", "documento.fornecedor.razao_social",
                   "documento.fornecedor.cnpj", "documento.fornecedor.endereco",
                   "documento.integrantes.cliente", "documento.integrantes.fornecedor"],
    },
    {
        "bloco": "capacidades", "ordem": 11, "essenciais": [],
        "titulo": "O que este projeto deixa o fluxo fazer",
        # Não trava, e mesmo assim é o bloco que mais muda o comportamento: aqui
        # é POLÍTICA, e ela é outro eixo do que a máquina consegue. O Figma é o
        # caso — o MCP pode estar autenticado e o projeto continuar não querendo
        # que ninguém escreva no arquivo que o UX mantém.
        #
        # Dá para rodar a qualquer momento, e não só na instalação: um projeto
        # que libera a escrita no Figma no meio do caminho muda uma chave aqui.
        "trava": "nada trava — cada ação desligada não corre, e a lista do que ficou de fora acompanha a atividade e todo relatório dela",
        "chaves": ["capacidades.grafo", "capacidades.figma_leitura",
                   "capacidades.figma_escrita", "capacidades.navegador",
                   "capacidades.perna_sombra", "complementos.system_analyst"],
    },
    {
        "bloco": "recursos", "ordem": 11, "essenciais": [],
        "titulo": "Quanto da máquina uma suíte de teste ocupa",
        "trava": "nada trava — sem a chave, a suíte roda com 2 workers",
        "chaves": ["recursos.max_workers_teste", "recursos.segundos_por_gate"],
    },
]


def chaves_do_roteiro() -> list[str]:
    return sorted({c for b in ROTEIRO for c in b["chaves"]})


# -------------------------------------------------------------------- leitura

def caminho_config(raiz: Path) -> Path:
    return Path(raiz) / ".agents" / "config.toml"


def ler(raiz: Path) -> dict:
    alvo = caminho_config(raiz)
    if not alvo.exists():
        raise ConfigError(f"não existe `{alvo}`. Rode: configure.py iniciar")
    return tomllib.loads(alvo.read_text(encoding="utf-8"))


def valor_em(dados: dict, caminho: str) -> Any:
    atual: Any = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


# ------------------------------------------------------------------ detecção
# Perguntar o que dá para descobrir é o que faz configuração virar formulário.

RE_AZURE = re.compile(r"dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/\s]+)")
RE_GITHUB = re.compile(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$")

# `dev` sobe servidor; `start` também. Nenhum dos dois é conferência, e tratar
# um servidor como gate faz o step 9 travar esperando um processo que não sai.
SCRIPTS_DE_GATE = {"lint": "lint", "test": "test", "build": "build"}


def _git(raiz: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _json_ou_vazio(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# Um nível abaixo da raiz, e só nas pastas onde subprojeto de fato mora. Varrer
# o repositório inteiro entraria em `node_modules` e traria a dependência da
# dependência como se fosse stack do projeto.
PASTAS_DE_SUBPROJETO = ("frontend", "backend", "web", "api", "app", "server", "client")


def _manifestos_node(raiz: Path) -> list[Path]:
    achados = [raiz / "package.json"]
    for pasta in PASTAS_DE_SUBPROJETO:
        achados.append(raiz / pasta / "package.json")
    for guarda_chuva in ("apps", "packages"):
        base = raiz / guarda_chuva
        if base.is_dir():
            achados += sorted(base.glob("*/package.json"))[:8]
    return [c for c in achados if c.exists()]


def detectar(raiz: Path) -> dict:
    raiz = Path(raiz)
    achado: dict[str, Any] = {
        "board": {"tipo": None},
        "gates": {},
        "stack": {"linguagens": [], "frameworks": [], "runtime": ""},
        "frontend": {},
        "git": {},
    }

    # O HOST decide o board, nunca o nome do repositório. Medido como armadilha
    # óbvia: um repo chamado `github-clone` hospedado no Azure continua sendo
    # Azure, e casar por nome erraria em silêncio.
    remote = _git(raiz, "remote", "get-url", "origin")
    if remote:
        m = RE_AZURE.search(remote)
        if m:
            achado["board"] = {"tipo": "azure", "org": m.group(1),
                               "projeto": m.group(2), "repo": m.group(3)}
        else:
            m = RE_GITHUB.search(remote)
            if m:
                achado["board"] = {"tipo": "github", "org": m.group(1),
                                   "repo": m.group(2)}

    # OS GATES saem da RAIZ, a STACK sai de onde as dependências estiverem.
    # Medido no acme-backoffice: o `package.json` da raiz tem
    # `scripts` e ZERO dependência — ele orquestra os subprojetos. Procurar a
    # stack só na raiz devolvia linguagem e framework vazios num repositório
    # TypeScript inteiro, e o /config passaria a perguntar o que estava ali do
    # lado. O comando de gate, ao contrário, é o da raiz: é de lá que se roda.
    raiz_pkg = _json_ou_vazio(raiz / "package.json")
    scripts = raiz_pkg.get("scripts") or {}
    for gate, nome in SCRIPTS_DE_GATE.items():
        if nome in scripts:
            achado["gates"][gate] = f"npm run {nome}"

    deps: dict = {}
    for manifesto in _manifestos_node(raiz):
        dados = _json_ou_vazio(manifesto)
        deps.update(dados.get("dependencies") or {})
        deps.update(dados.get("devDependencies") or {})
    if raiz_pkg or deps:
        achado["stack"]["runtime"] = "node"
    if deps:
        achado["stack"]["frameworks"] = sorted(deps)[:12]
        achado["stack"]["linguagens"] = (
            ["typescript"] if "typescript" in deps else ["javascript"])

    for manifesto, lingua in (("pyproject.toml", "python"), ("go.mod", "go"),
                              ("Cargo.toml", "rust"), ("pom.xml", "java")):
        if (raiz / manifesto).exists() and lingua not in achado["stack"]["linguagens"]:
            achado["stack"]["linguagens"].append(lingua)

    skills = raiz / ".agents" / "skills"
    if skills.is_dir():
        achado["git"]["skills_disponiveis"] = sorted(
            p.name for p in skills.iterdir() if p.is_dir())

    for chave, candidatos in (("componentes", ("src/components", "components",
                                               "app/components",
                                               "frontend/components",
                                               "frontend/src/components",
                                               "apps/web/components")),
                              ("tokens", ("src/styles", "styles", "tokens",
                                          "frontend/styles",
                                          "frontend/src/styles"))):
        for c in candidatos:
            if (raiz / c).is_dir():
                achado["frontend"][chave] = c
                break
    return achado


# --------------------------------------------------------------------- estado

def tem_padrao_no_exemplo() -> set[str]:
    """Chaves cujo exemplo já traz um valor — ou seja, que têm padrão.

    `metricas.ligado = true` e `teto_leitura_min = 10` funcionam sem serem
    declaradas. `projeto.nome = ""` não. Tratar as duas como "falta" é a mesma
    mentira de rótulo do prazo que dizia "até a entrega" numa atividade que não
    entregou: a palavra promete o que o dado não diz, e quem lê vai declarar
    nove chaves para calar um aviso que não era sobre elas.
    """
    linhas = EXEMPLO.read_text(encoding="utf-8").splitlines()
    com_padrao = set()
    for chave, onde in indexar(linhas).items():
        if onde["comentada"]:
            continue                      # comentada = não vale como padrão
        m = RE_CHAVE.match(linhas[onde["linha"]])
        bruto = (m.group(4) if m else "").split("#")[0].strip()
        if bruto not in ('""', "[]", "''", ""):
            com_padrao.add(chave)
    return com_padrao


def estado(raiz: Path) -> dict:
    # Repositório sem config é ESTADO, não erro. A skill descobre o modo dela
    # daqui, e mandar o modo "repositório novo" pelo stderr como `[erro]` fazia
    # o começo normal da entrevista parecer uma falha.
    if not caminho_config(Path(raiz)).exists():
        return {"raiz": str(raiz), "configurado": False, "blocos": [],
                "prontos": [], "proximo": "configure.py iniciar --raiz ."}

    dados = ler(raiz)
    padroes = tem_padrao_no_exemplo()
    blocos = []
    for b in ROTEIRO:
        faltando, declaradas, no_padrao, opcional = [], [], [], []
        for chave in b["chaves"]:
            v = valor_em(dados, chave)
            # `0`, `false` e `[]` SÃO declarações. Só `None` e `""` são ausência
            # — a mesma armadilha do `or` que o coletor já documentou.
            if v not in (None, ""):
                declaradas.append(chave)
            elif chave in padroes:
                no_padrao.append(chave)
            elif chave in b["essenciais"]:
                faltando.append(chave)
            else:
                opcional.append(chave)
        blocos.append({**{k: b[k] for k in ("bloco", "ordem", "titulo", "trava")},
                       "declaradas": declaradas, "no_padrao": no_padrao,
                       "faltando": faltando, "opcional": opcional,
                       "mostra_trava": bool(faltando)})
    return {"raiz": str(raiz), "configurado": True, "blocos": blocos,
            "prontos": [b["bloco"] for b in blocos if not b["faltando"]],
            "proximo": None}


# -------------------------------------------------------------------- comandos

def cmd_iniciar(args) -> int:
    alvo = caminho_config(Path(args.raiz))
    if alvo.exists():
        raise ConfigError(f"`{alvo}` já existe. Use `definir` para ajustar chave a chave.")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    # Cópia LITERAL, byte a byte. Gerar o arquivo a partir do esquema perderia
    # os comentários, que são a metade útil dele.
    shutil.copyfile(EXEMPLO, alvo)
    print(f"  config criado em {alvo}")
    print(f"  {len(chaves_do_exemplo())} chaves, com a explicação de cada uma preservada")
    return 0


def cmd_definir(args) -> int:
    alvo = caminho_config(Path(args.raiz))
    if not alvo.exists():
        raise ConfigError(f"não existe `{alvo}`. Rode: configure.py iniciar")
    linhas = alvo.read_text(encoding="utf-8").splitlines(keepends=True)
    indice = indexar([l.rstrip("\n") for l in linhas])

    chave = args.chave
    # O ESQUEMA é o exemplo do pacote; o config do projeto é só onde a chave é
    # escrita. Confundir os dois é o que fazia uma chave nova ser recusada com a
    # mensagem "não existe no esquema" quando ela existia — o projeto é que era
    # anterior a ela.
    esquema = indexar(_linhas_do_exemplo())
    if chave not in esquema:
        parecidas = difflib.get_close_matches(chave, sorted(esquema), n=2, cutoff=0.5)
        dica = f" Você quis dizer `{'` ou `'.join(parecidas)}`?" if parecidas else ""
        raise ConfigError(
            f"`{chave}` não existe no esquema do config.{dica}\n"
            f"  O esquema é o `config.example.toml` do pacote — chave que não está "
            f"lá não é lida por ninguém, e declará-la faria você acreditar ter "
            f"configurado algo que não existe.")

    if chave not in indice:
        # O projeto é anterior à chave: ela entrou numa versão do pacote mais
        # nova que o `config.toml` daqui. Sem isto, "configurável a qualquer
        # momento" valia só para chave que o projeto já tinha — e toda chave
        # nova exigia edição à mão, que é o que esta ferramenta existe para
        # evitar.
        secao, bloco = bloco_do_exemplo(chave)
        secoes = [n for n, l in enumerate(linhas)
                  if (m := RE_SECAO.match(l.rstrip("\n")))
                  and m.group(1) == secao and not l.lstrip().startswith("#")]
        if secoes:
            # A seção existe: a chave entra no fim dela, antes da próxima.
            inicio = secoes[0]
            fim = len(linhas)
            for n in range(inicio + 1, len(linhas)):
                if RE_SECAO.match(linhas[n].rstrip("\n")) and not linhas[n].lstrip().startswith("#"):
                    fim = n
                    break
            while fim > inicio + 1 and not linhas[fim - 1].strip():
                fim -= 1
            novas = ["\n"] + [l + "\n" for l in bloco]
            onde_entrou = f"no fim de `[{secao}]`"
        else:
            # A seção também não existe: entra inteira, com o cabeçalho dela.
            fim = len(linhas)
            while fim > 0 and not linhas[fim - 1].strip():
                fim -= 1
            novas = ["\n"] + [l + "\n" for l in cabecalho_da_secao(secao) + bloco]
            onde_entrou = f"com a seção `[{secao}]`, que também faltava"
        linhas[fim:fim] = novas
        alvo.write_text("".join(linhas), encoding="utf-8")
        print(f"  `{chave}` não existia neste config — entrou {onde_entrou},")
        print("  com a explicação que vem do esquema.")
        linhas = alvo.read_text(encoding="utf-8").splitlines(keepends=True)
        indice = indexar([l.rstrip("\n") for l in linhas])
        inserimos = True
    else:
        inserimos = False

    onde = indice[chave]
    if onde["multilinha"]:
        raise ConfigError(
            f"`{chave}` tem valor de várias linhas, e a escrita aqui é de uma "
            f"linha só.\n  Edite à mão em `{alvo}`, linha {onde['linha'] + 1}.")

    valor = do_texto(args.valor)
    nome = chave.rsplit(".", 1)[1]
    fim = "\n" if linhas[onde["linha"]].endswith("\n") else ""
    linhas[onde["linha"]] = f"{onde['recuo']}{nome} = {como_toml(valor)}{fim}"
    # Criar a nota, só onde o bloco veio do esquema: em chave que já estava no
    # arquivo o comentário acima é do projeto, e a cirurgia promete mexer numa
    # linha só. MANTER a nota, sempre — ela tem marca própria, é nossa, e uma
    # nota velha contradiz na direção oposta: `Declarado como "on"` em cima de
    # um `= "off"` que alguém acabou de escrever.
    linhas = anotar_divergencia(linhas, onde["linha"], chave, valor,
                                pode_criar=inserimos)
    alvo.write_text("".join(linhas), encoding="utf-8")

    # Relê para provar que o TOML continua válido. Escrever e não conferir é
    # como o coletor deixaria um número sair errado com cara de certo.
    try:
        tomllib.loads(alvo.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"a escrita quebrou o TOML: {exc}") from exc
    estado_txt = "descomentada e definida" if onde["comentada"] else "definida"
    print(f"  {chave} {estado_txt} = {como_toml(valor)}")
    return 0


def cmd_detectar(args) -> int:
    print(json.dumps(detectar(Path(args.raiz)), ensure_ascii=False, indent=2))
    return 0


def cmd_estado(args) -> int:
    e = estado(Path(args.raiz))
    print(f"\nConfiguração — {e['raiz']}\n")
    if not e["configurado"]:
        print("  Ainda não configurado — não há `.agents/config.toml`.")
        print(f"  Próximo: {e['proximo']}\n")
        return 0
    for b in e["blocos"]:
        marca = "ok   " if not b["faltando"] else "falta"
        print(f"  [{marca}] {b['ordem']}. {b['titulo']}")
        if b["faltando"]:
            print(f"          por declarar: "
                  f"{', '.join(c.rsplit('.', 1)[1] for c in b['faltando'][:6])}")
            print(f"          {b['trava']}")
        if b["opcional"]:
            print(f"          opcional, não trava: "
                  f"{', '.join(c.rsplit('.', 1)[1] for c in b['opcional'][:6])}")
        if b["no_padrao"]:
            print(f"          no padrão do pacote (não precisa declarar): "
                  f"{', '.join(c.rsplit('.', 1)[1] for c in b['no_padrao'][:6])}")
    print()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Configuração do projeto, sem perder o que ela explica.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nome, fn in (("iniciar", cmd_iniciar), ("detectar", cmd_detectar),
                     ("estado", cmd_estado)):
        s = sub.add_parser(nome)
        s.add_argument("--raiz", default=".")
        s.set_defaults(fn=fn)
    s = sub.add_parser("definir")
    s.add_argument("chave")
    s.add_argument("valor")
    s.add_argument("--raiz", default=".")
    s.add_argument("--json", action="store_true",
                   help="interpreta o valor como JSON (para lista, número e booleano)")
    s.set_defaults(fn=cmd_definir)

    args = p.parse_args(argv)
    if getattr(args, "json", False):
        args.valor = json.loads(args.valor)
    try:
        return args.fn(args)
    except ConfigError as exc:
        print(f"\n  [erro] {exc}\n", file=sys.stderr)
        return 1


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
    raise SystemExit(main())
