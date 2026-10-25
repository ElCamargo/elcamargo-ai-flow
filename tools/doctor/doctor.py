#!/usr/bin/env python3
"""O config deste projeto bate com este projeto?

O `install.sh` confere que o `config.toml` é TOML válido, e só.

Por muito tempo o exemplo carregava os valores do projeto onde o pacote nasceu e
dizia "ajuste antes de usar". Quem não ajustava levava tudo junto. Instalado num
repositório VAZIO, ele saía com seis achados altos e seis médios, e todos eram
valor de outro projeto:

    [git] skill = "acme-azure-git-management"   ← o pacote entrega
                                                     `elcamargo-board-git-management`
    [gates] lint/test/build = "npm run ..."        ← script que não existe ali
    [perfis] comando = "npm run perfil ..."        ← nunca foi escrito nem lá

Hoje o exemplo sai VAZIO, e o `install.sh` deriva a única coisa derivável: o
nome do repositório. Um projeto novo começa limpo, e liga cada seção quando o
que ela declara passa a existir — é o que a lista `A_LIBERAR` acompanha.

Este comando confere as duas coisas, e são diferentes:

  o que está DECLARADO e não existe   → achado, alto ou médio
  o que ainda NÃO está declarado      → lista informativa, não é erro

    doctor.py conferir [--config <arquivo>] [--raiz .] [--so-erros]

Uso obrigatório ao instalar o pacote num projeto novo, e depois de cada seção
que você preencher. Ele não conserta nada.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


class DoutorError(Exception):
    pass


# COMPARAR COM O EXEMPLO NÃO SERVE, e o motivo custou uma rodada: o exemplo
# nasceu do projeto onde o pacote foi escrito, então lá os valores são iguais
# POR SEREM CERTOS. A checagem acusava para sempre o único projeto em que ela
# não deveria acusar nada.
#
# O que separa "copiei e não ajustei" de "é o projeto de origem" é o
# repositório: se `projeto.nome` não bate com o nome do repositório em que o
# comando está rodando, o config é de outro lugar.


def nome_do_repositorio(raiz: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "remote", "get-url", "origin"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return re.sub(r"\.git$", "", r.stdout.strip().rstrip("/").split("/")[-1])
    except (OSError, subprocess.SubprocessError):
        pass
    return raiz.name

# Caminhos declarados que devem existir no repositório. `criado_sob_demanda`
# fica de fora: uma catraca sem arquivo é uma catraca que ainda não gravou base.
CAMINHOS = (
    ("docs.specs", "onde as especificações moram"),
    ("docs.adrs", "onde as decisões de arquitetura moram"),
    ("docs.fora_de_escopo", "onde vai o que foi decidido não fazer"),
    ("docs.classes_de_defeito", "o registro das classes de defeito que já escaparam"),
    ("frontend.componentes", "os componentes reusáveis que o protótipo reusa"),
    ("frontend.tokens", "os tokens de cor, espaçamento e tipografia"),
    ("frontend.gate_de_tela", "as invariantes que toda tela respeita"),
)

# O que o projeto ainda NÃO declarou, e o que cada coisa destrava quando
# declarada. Não é erro: um repositório novo começa com quase tudo vazio, e
# preencher o que ainda não existe é o defeito, não a virtude.
#
# Existe porque a lista do que falta não estava em lugar nenhum: o doutor dizia
# o que está errado, e ninguém dizia o que está apenas desligado. Sem isso a
# escolha era preencher tudo de véspera — que é como o config de um projeto
# chega no outro trazendo valores que não valem ali.
A_LIBERAR = (
    ("git.skill", "o step 1 usa o Git genérico do pacote",
     "houver skill de Git própria em `.agents/skills/`"),
    ("docs.specs", "o step 3 não sabe onde escrever a SDD",
     "a pasta de especificações existir"),
    ("docs.adrs", "nenhum step confronta decisão de arquitetura",
     "houver a primeira ADR"),
    ("docs.fora_de_escopo", "ninguém sabe o que o produto já recusou",
     "houver a primeira decisão de não fazer"),
    ("docs.classes_de_defeito", "a revisão não aprende com o defeito que já escapou",
     "o primeiro defeito escapar da revisão e virar classe"),
    ("producao.subir", "ninguém confere o build de produção atrás do host público",
     "o projeto tiver build de produção que suba localmente"),
    ("gates.lint", "a frente de qualidade improvisa o comando",
     "houver script de lint no package.json"),
    ("gates.test", "a frente de qualidade improvisa o comando",
     "houver script de teste"),
    ("gates.build", "a frente de qualidade improvisa o comando",
     "houver script de build"),
    ("frontend.componentes", "o step 6 desenha sem reusar componente do projeto",
     "houver biblioteca de componentes"),
    ("frontend.tokens", "o protótipo inventa cor e espaçamento",
     "houver tokens de design"),
    ("frontend.gate_de_tela", "nada verifica as invariantes de tela por comando",
     "as invariantes estiverem escritas"),
    ("catraca.arquivo", "portão vermelho não distingue novo de pré-existente",
     "houver o primeiro portão verde para virar linha de base"),
    ("perfis.comando", "a passada por perfis é dimensão NÃO COBERTA declarada",
     "houver autenticação e um script que emita token por perfil"),
    ("complementos", "os steps rodam só com a doutrina genérica",
     "o projeto tiver skill própria que complemente um step"),
    ("stack.linguagens", "o security-reviewer procura o genérico",
     "a stack estiver decidida"),
    ("metricas.ligado", "a coleta de métricas roda a cada `avancar` e no `concluir`",
     "quiser DESLIGAR a coleta, com `ligado = false`"),
    ("metricas.orcamento_usd", "nada limita o gasto de uma atividade — o custo é relatado, nunca decidido",
     "quiser que o `avancar` pare e peça decisão ao passar do teto"),
    ("metricas.publicar_no_repo",
     "as métricas ficam só no `.agents/`, fora do versionamento — ninguém as abre sem rodar o coletor",
     "quiser o resumo em `docs/` e um bloco no README, atualizados a cada step"),
)

def acoes_conhecidas(pacote: Path) -> dict:
    """As ações que o pacote publica, LIDAS DE ONDE ELAS VIVEM.

    Mesma razão de `formatos_de_catraca` ler da catraca: uma tupla copiada aqui
    divergiria no minuto em que uma ação nova entrasse, e o doutor passaria a
    acusar como desconhecida uma chave que existe e funciona.
    """
    try:
        sys.path.insert(0, str(pacote / "tools" / "flow-state"))
        import capabilities  # noqa: PLC0415
        return dict(capabilities.ACOES)
    except Exception:
        return {}


def acoes_de_escolha(pacote: Path) -> dict:
    """As ações cujo valor não é auto/on/off, lidas do mesmo lugar."""
    try:
        sys.path.insert(0, str(pacote / "tools" / "flow-state"))
        import capabilities  # noqa: PLC0415
        return dict(getattr(capabilities, "ACOES_DE_ESCOLHA", {}))
    except Exception:
        return {}


def caminho_do_token_figma(pacote: Path) -> Path | None:
    """Onde o token de leitura do Figma mora, LIDO DE ONDE ELE VIVE.

    Mesma razão de `acoes_conhecidas`: um caminho copiado aqui divergiria na
    primeira vez que ele mudasse, e o doutor passaria a mandar instalar o token
    no lugar errado — que é pior que não checar.
    """
    try:
        sys.path.insert(0, str(pacote / "tools" / "flow-state"))
        import capabilities  # noqa: PLC0415
        return capabilities.CAMINHO_TOKEN_FIGMA
    except Exception:
        return None


def formatos_de_catraca(pacote: Path) -> tuple[str, ...]:
    """Os formatos que a catraca sabe ler, LIDOS DELA.

    Era uma tupla escrita aqui à mão, e ela divergiu em silêncio no minuto em
    que a catraca ganhou o formato `lighthouse`: o doutor passou a reprovar
    como "formato desconhecido" um formato que existia e funcionava. Mesma
    família das duas listas de pastas ignoradas que o `config.py` conta — duas
    listas que deviam ser uma, mantidas por mãos diferentes.

    Fonte única, e uma reserva para o caso de o import falhar: sem ele o
    doutor não pode calar sobre formato nenhum, mas também não pode explodir.
    """
    try:
        sys.path.insert(0, str(pacote / "tools" / "ratchet"))
        from ratchet import FORMATOS
        return tuple(sorted(FORMATOS))
    except Exception:
        return ("eslint", "jest", "lighthouse", "vitest")


def carregar(caminho: Path) -> dict:
    if tomllib is None:
        raise DoutorError("este Python não tem tomllib; use 3.11+")
    if not caminho.is_file():
        raise DoutorError(f"config não encontrado: {caminho}")
    try:
        return tomllib.loads(caminho.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DoutorError(f"config não é TOML válido: {exc}") from exc


def obter(dados: dict, caminho: str):
    atual = dados
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def npm_scripts(raiz: Path) -> dict[str, set[str]]:
    """Scripts declarados na raiz e em cada subprojeto com package.json."""
    achados: dict[str, set[str]] = {}
    for pkg in [raiz / "package.json", *sorted(raiz.glob("*/package.json"))]:
        if not pkg.is_file():
            continue
        try:
            dados = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        prefixo = "" if pkg.parent == raiz else pkg.parent.name
        achados[prefixo] = set((dados.get("scripts") or {}).keys())
    return achados


RE_NPM = re.compile(r"npm\s+(?:--prefix\s+(?P<prefixo>\S+)\s+)?run\s+(?P<script>[\w:-]+)")


def script_existe(comando: str, scripts: dict[str, set[str]]) -> bool | None:
    """True/False quando dá para saber; None quando o comando não é `npm run`."""
    m = RE_NPM.search(comando)
    if not m:
        return None
    prefixo = (m.group("prefixo") or "").strip("./")
    disponiveis = scripts.get(prefixo)
    if disponiveis is None:
        return False
    return m.group("script") in disponiveis


def visivel_para_as_sessoes(raiz: Path, nome: str) -> bool:
    """Alguma sessão descobre esta skill pelo nome?

    A descoberta do Claude Code é por diretório: `.claude/skills/` na raiz vale
    no repositório inteiro, e `<pasta>/.claude/skills/` vale só dentro dela — é
    o que o `install.sh --escopo` usa. As duas contam, senão um projeto que
    ligou só o `mobile/` apareceria como quebrado sem estar.
    """
    candidatos = [raiz / ".claude" / "skills" / nome]
    candidatos += [p / ".claude" / "skills" / nome
                   for p in raiz.iterdir() if p.is_dir() and not p.name.startswith(".")]
    return any(c.exists() for c in candidatos)


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))
from config import copias_do_pacote, versao  # noqa: E402


def cmd_conferir(args) -> int:
    raiz = Path(args.raiz).resolve()
    pacote = Path(__file__).resolve().parents[2]
    # O config é do PROJETO, e sai de `<raiz>/.agents/` — não de `pacote.parent`.
    #
    # `pacote.parent` só é o `.agents` do projeto quando o pacote está copiado
    # lá dentro. Instalado como plugin, ele aponta para a pasta do cache, e o
    # doutor morria dizendo que o config não existe — no exato momento em que
    # o plugin passou a ser a única fonte.
    #
    # Quarto caso da mesma família (os outros: as skills do projeto aqui
    # embaixo, `PACOTE.parent.parent` no teste de pacote, e a resolução do
    # `$PACOTE` nas skills). Todos vinham de presumir onde o pacote mora.
    #
    # Sobreviveu porque o teste de fumaça SEMPRE passava `--config` explícito:
    # este ramo nunca corria. Agora corre — veja `test_smoke.py`.
    config = Path(args.config) if args.config else raiz / ".agents" / "config.toml"
    dados = carregar(config)

    altos: list[str] = []
    medios: list[str] = []

    # -- 0. de onde vem o pacote que está valendo? -------------------------
    #
    # Duas fontes é o normal, não a exceção: o projeto tem a cópia em `.agents`
    # e a pessoa instalou o plugin. Uma delas vence — a cópia, porque é o
    # segundo degrau da resolução e o terceiro só corre se ele falhar — e
    # ninguém enxerga qual.
    #
    # Isso não é defeito por si só: durante o desenvolvimento a cópia adiantada
    # é o que se quer. Vira defeito quando é acaso, e quando as duas divergem
    # sem que ninguém saiba de qual veio o comportamento que está vendo.
    copias = copias_do_pacote(raiz)
    minha = versao(pacote)
    if len(copias) > 1:
        versoes = {v for _, _, v in copias}
        linhas = "\n".join(f"      {o:<20} {v:<10} {c}" for o, c, v in copias)
        if len(versoes) > 1:
            altos.append(
                "o pacote existe em mais de um lugar, com versões DIFERENTES:"
                f"\n{linhas}"
                "\n      A primeira da lista é a que vence. Se a intenção era usar"
                "\n      o plugin, apague a cópia; se era a cópia, `claude plugin"
                "\n      uninstall` evita a dúvida.")
        else:
            medios.append(
                "o pacote existe em mais de um lugar, na mesma versão:"
                f"\n{linhas}"
                "\n      Funciona, e a primeira vence. Fica dito para o dia em que"
                "\n      uma delas mudar e a outra não.")
    # Uma fonte só é o estado CERTO, não um achado. Esta linha nasceu MEDIO
    # quando a cópia em `.agents` era a norma e o plugin a novidade; virou
    # ruído no instante em que o plugin passou a ser a fonte única — acusava
    # todo projeto saudável. Vira nota de cabeçalho: informa de onde veio o
    # que está rodando, sem chamar de defeito o que é o desejado.
    fonte = ""
    if len(copias) == 1:
        origem, caminho, v = copias[0]
        fonte = f"{origem}, versão {v}"
        if origem == "plugin instalado":
            fonte += " — atualiza com `claude plugin update elcamargo-ai-flow@elcamargo`"
    if copias and copias[0][2] == "?":
        medios.append(
            f"o pacote em {copias[0][1]} não declara versão."
            "\n      Falta o arquivo `VERSION` na raiz dele. Sem isso não dá para"
            "\n      comparar com nenhuma outra cópia, e ele é de antes desta regra.")

    # -- 1. o config é deste repositório? ----------------------------------
    declarado = (obter(dados, "projeto.nome") or "").strip()
    real = nome_do_repositorio(raiz)
    if declarado and real and declarado != real:
        medios.append(
            f"`[projeto] nome = \"{declarado}\"` e o repositório é `{real}`."
            "\n      O `install.sh` copia o exemplo do projeto de origem; se o nome"
            "\n      não foi ajustado, provavelmente nada foi.")

    # DOIS lugares, e olhar só um custou uma regressão: o pacote traz as
    # skills DELE, e o projeto pode ter as suas ao lado, em `.agents/skills/`.
    # Uma versão anterior só varria o pacote, declarou inexistente a skill de
    # Git do projeto — que existia, era real e estava em uso — e o config foi
    # "corrigido" para apontar para outra.
    # As do PACOTE saem de onde o pacote está; as do PROJETO saem do `.agents`
    # do projeto que se está conferindo — e NÃO de `pacote.parent`.
    #
    # `pacote.parent` só coincide com o `.agents` do projeto quando o pacote
    # está copiado lá dentro. Com o pacote instalado como plugin, ou apontando
    # o doutor para outro repositório, ele olha para o lugar errado e declara
    # inexistentes skills que existem — foi o que aconteceu na primeira execução
    # depois desta mudança: duas skills reais do projeto viraram `[ALTO]`.
    agents_do_projeto = raiz / ".agents"
    pastas = [pacote / "skills", agents_do_projeto / "skills"]
    aposentadas = agents_do_projeto / "retired"

    def skill_existe(nome: str) -> bool:
        return any((pasta / nome).is_dir() for pasta in pastas)

    def skills_disponiveis() -> list[str]:
        return sorted({p.name for pasta in pastas if pasta.is_dir()
                       for p in pasta.iterdir() if p.is_dir()})

    # -- 2. a skill de Git declarada existe? -------------------------------
    skill = obter(dados, "git.skill") or ""
    if skill and not skill_existe(skill):
        altos.append(
            f"`[git] skill = \"{skill}\"` não existe."
            "\n      Procurei no pacote e em `.agents/skills/`. O step 1"
            "\n      delega para ela e não vai achar nada."
            "\n      Disponíveis: " + ", ".join(skills_disponiveis()))

    # -- 2b. as skills complementares existem, e alguém as lê? --------------
    #
    # `[complementos]` decide se a skill própria de um projeto continua no
    # fluxo ou sai dele — foi a chave que resolveu o par `system_analyst` em
    # dois repositórios, cada um para um lado. Nada a conferia.
    #
    # O caso que motivou: um projeto aposentou a skill própria para `retired/`
    # e a chave continuava declarada. O step chamaria um nome que não existe
    # mais, e nada falharia na hora — a especificação sairia sem o complemento
    # e ninguém saberia dizer que faltou.
    #
    # A checagem "chave que ninguém lê" foi derrubada em geral (ver o comentário
    # no fim do arquivo), e aqui ela FUNCIONA pelo motivo que lá faltava: o
    # consumidor lê por CHAVE, literalmente `config.py complementos.<slot>`
    # dentro de um SKILL.md. Dá para procurar o leitor pelo nome do slot.
    for chave, valor in (obter(dados, "complementos") or {}).items():
        if not isinstance(valor, str) or not valor:
            continue
        if not skill_existe(valor):
            se_aposentada = (aposentadas / valor).is_dir()
            altos.append(
                f"`[complementos] {chave} = \"{valor}\"` "
                + ("aponta para uma skill APOSENTADA em `retired/`."
                   if se_aposentada else "não existe.")
                + "\n      O step que lê esse complemento vai chamar um nome que"
                  "\n      ninguém atende, e a entrega sai sem ele, em silêncio."
                + ("\n      Ou a skill volta para `.agents/skills/`, ou a chave sai"
                   "\n      do config." if se_aposentada else
                   "\n      Disponíveis: " + ", ".join(skills_disponiveis())))
            continue
        leitores = [p.parent.name for p in sorted((pacote / "skills").glob("*/SKILL.md"))
                    if f"complementos.{chave}" in p.read_text(encoding="utf-8")]
        if (pacote / "skills").is_dir() and not leitores:
            medios.append(
                f"`[complementos] {chave}` — nenhuma skill do pacote lê esse slot."
                "\n      A skill existe, mas nada a chama: procurei por"
                f"\n      `complementos.{chave}` nos SKILL.md do pacote. Erro de"
                "\n      digitação no nome do slot faz exatamente isto.")
        elif leitores and not visivel_para_as_sessoes(raiz, valor):
            medios.append(
                f"`[complementos] {chave} = \"{valor}\"` existe, mas nenhuma"
                "\n      sessão a enxerga: não há link para ela em `.claude/skills/`."
                f"\n      Quem a chama é {', '.join(leitores)}, e a chamada é por nome."
                "\n      Ligue com: ln -sfn ../../.agents/skills/"
                + valor + " .claude/skills/" + valor)

    # -- 2c. as ações de `[capacidades]` -----------------------------------
    #
    # A lista é FECHADA, e é isso que torna a conferência possível: chave fora
    # dela é quase sempre erro de digitação, e um `figma_escrit = "on"` que
    # ninguém acusa deixa a escrita desligada enquanto o config diz que ligou.
    #
    # A checagem "alguém lê?" aqui vale pelo mesmo motivo do `[complementos]`:
    # quem consulta lê pelo NOME da ação, dentro de um SKILL.md ou de um agente.
    # Ação sem leitor é flag morta, e flag morta dá impressão de controle que
    # não existe — o pior estado possível para um portão.
    acoes = acoes_conhecidas(pacote)
    escolhas = acoes_de_escolha(pacote)
    for chave, valor in (obter(dados, "capacidades") or {}).items():
        if chave in escolhas:
            if str(valor).strip().lower() not in escolhas[chave]:
                altos.append(
                    f"`[capacidades] {chave} = {valor!r}` não é um valor válido."
                    f"\n      Use um de: {', '.join(escolhas[chave])}.")
            continue
        if acoes and chave not in acoes:
            altos.append(
                f"`[capacidades] {chave}` não é uma ação conhecida."
                "\n      A lista é fechada de propósito. Conhecidas: "
                + ", ".join(sorted({*acoes, *escolhas}))
                + "\n      Chave desconhecida fica no arquivo parecendo política"
                  "\n      e não governa nada.")
            continue
        if str(valor).strip().lower() not in ("auto", "on", "off"):
            altos.append(
                f"`[capacidades] {chave} = {valor!r}` não é um valor válido."
                "\n      Use `auto` (usa se der, e declara quando não der), `on`"
                "\n      (exige) ou `off` (não faz, mesmo podendo).")
            continue
        if not (pacote / "skills").is_dir():
            continue
        leitores = [q.parent.name for q in sorted((pacote / "skills").glob("*/SKILL.md"))
                    if chave in q.read_text(encoding="utf-8")]
        leitores += [q.stem for q in sorted((pacote / "agents").glob("*.md"))
                     if chave in q.read_text(encoding="utf-8")]
        if not leitores:
            medios.append(
                f"`[capacidades] {chave}` — nenhuma skill ou agente do pacote"
                "\n      consulta essa ação. Ela pode ser ligada e desligada no"
                "\n      config sem mudar nada no fluxo, que é o pior estado de"
                "\n      um portão: parece controle e não é.")

    # -- 2d. o token que o caminho do Figma exige --------------------------
    #
    # É o único pré-requisito da leitura do Figma, e não era conferido em lugar
    # nenhum. Em 08/09/2026 uma frente parou o step 6 "por falta de MCP da
    # Figma" — leitura não usa MCP, usa este token — e foi tentar o navegador.
    # Esta checagem é a que teria dito, ANTES da atividade, o que faltava (ou
    # que não faltava nada).
    #
    # Silêncio quando o projeto declarou `figma_leitura = "off"`: ali não ter
    # token é coerente, e acusar seria ruído sobre uma escolha.
    politica_leitura = str(
        (obter(dados, "capacidades") or {}).get("figma_leitura", "auto")
    ).strip().lower()
    token_figma = caminho_do_token_figma(pacote)
    if token_figma is not None and politica_leitura != "off":
        instalar = (
            "\n      Gere em Figma > Settings > Security > Personal access tokens,"
            "\n      com escopo de LEITURA de conteúdo de arquivo, e guarde assim"
            "\n      — o comando não ecoa o valor na tela nem no histórico:"
            f"\n        mkdir -p {token_figma.parent} && printf 'Cole o token: ' \\"
            f"\n          && read -rs T && printf '%s' \"$T\" > {token_figma} \\"
            f"\n          && chmod 600 {token_figma} && unset T")
        if not token_figma.exists():
            queixa = (
                "não há token do Figma nesta máquina."
                "\n      Sem ele o step 6 desenha as telas em vez de ler o "
                "protótipo,"
                "\n      mesmo com link — e ler NÃO usa MCP: é REST, pelo "
                "`tools/figma/figma.py`." + instalar)
            (altos if politica_leitura == "on" else medios).append(queixa)
        elif oct(token_figma.stat().st_mode)[-3:] != "600":
            modo = oct(token_figma.stat().st_mode)[-3:]
            altos.append(
                f"o token do Figma está com permissão {modo}."
                "\n      A ferramenta recusa token legível por outros, então a "
                "leitura"
                f"\n      falha como se não houvesse token.\n      Corrija:  "
                f"chmod 600 {token_figma}")
        elif not token_figma.read_text(encoding="utf-8", errors="replace").strip():
            medios.append(
                f"o token do Figma em {token_figma} está vazio." + instalar)

    # -- 3. caminhos declarados que não existem ----------------------------
    for chave, para_que in CAMINHOS:
        valor = obter(dados, chave)
        if not valor:
            continue
        if not (raiz / valor).exists():
            medios.append(f"`{chave} = \"{valor}\"` não existe — {para_que}")

    # -- 4. os gates rodam? -------------------------------------------------
    scripts = npm_scripts(raiz)
    gates = obter(dados, "gates") or {}
    for nome, comando in gates.items():
        if not isinstance(comando, str) or not comando:
            continue
        existe = script_existe(comando, scripts)
        if existe is False:
            altos.append(
                f"`[gates] {nome} = \"{comando}\"` — não há esse script npm."
                "\n      O step 8 e a frente de qualidade rodam o que está aqui.")
        elif existe is None:
            primeiro = comando.split()[0]
            if not shutil.which(primeiro):
                medios.append(
                    f"`[gates] {nome}` começa com `{primeiro}`, que não está no PATH")

    # -- 5. catraca coerente com os gates -----------------------------------
    formatos = obter(dados, "catraca.formatos") or {}
    conhecidos = formatos_de_catraca(pacote)
    for portao, formato in formatos.items():
        if portao not in gates:
            medios.append(
                f"`[catraca.formatos] {portao}` não tem gate correspondente em `[gates]`")
        if formato not in conhecidos and not (
                obter(dados, "catraca.padroes") or {}).get(portao):
            altos.append(
                f"`[catraca.formatos] {portao} = \"{formato}\"` é formato desconhecido."
                "\n      Conhecidos: " + ", ".join(conhecidos)
                + "; para outro, declare um regex em `[catraca.padroes]`.")

    # -- 6. o comando de perfil roda? ---------------------------------------
    comando_perfil = obter(dados, "perfis.comando") or ""
    if comando_perfil:
        try:
            r = subprocess.run(comando_perfil.split() + ["--listar"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=raiz)
            if r.returncode != 0:
                saida = (r.stderr or r.stdout).strip()
                # `--silent` engole o erro do npm, e "sem saída" não ajuda
                # ninguém a consertar. Diz-se o que fazer para ver.
                detalhe = (saida.splitlines()[-1][:140] if saida else
                           "sem saída — rode o comando sem `--silent` para ver o erro")
                altos.append(
                    f"`[perfis] comando` não roda: {comando_perfil}\n      {detalhe}")
        except (OSError, subprocess.SubprocessError) as exc:
            altos.append(f"`[perfis] comando` não roda: {exc}")
    elif obter(dados, "perfis.atores"):
        altos.append("`[perfis.atores]` declarado sem `[perfis] comando` — "
                     "não há como assumir perfil nenhum")

    # -- 7. anexos ----------------------------------------------------------
    if (obter(dados, "anexos.backend") or "") == "azure":
        for chave in ("anexos.azure.org", "anexos.azure.projeto"):
            if not obter(dados, chave):
                altos.append(f"`backend = \"azure\"` e `{chave}` vazio — "
                             "todo anexo vai falhar")

    # -- 8. métricas --------------------------------------------------------
    #
    # A regra aqui é ASSIMÉTRICA, e ela não é gosto: está escrita no próprio
    # coletor — "subestimar a hora humana INFLA o ganho da ferramenta: é o
    # erro que não se pode cometer". Então o que faz o número sair MENOR do
    # que é reprova; o que faz sair DIFERENTE apenas informa.
    #
    # É por isso que preço divergente da tabela do pacote NÃO reprova: quem
    # roda outro modelo tem preço legitimamente outro, e o doutor não sabe
    # qual modelo você roda. Reprovar seria o falso permanente da mesma
    # família do "projeto de origem" — acusar para sempre quem está certo.
    ligado = obter(dados, "metricas.ligado")
    if ligado is not None and not isinstance(ligado, bool):
        medios.append(f"`[metricas] ligado = {ligado!r}` não é booleano — qualquer "
                      "valor não vazio conta como LIGADO. Use `true` ou `false`.")

    # Teto e reentrada são diferentes, e a diferença decide a severidade: o
    # teto corta uma medida TOMADA (o intervalo entre a resposta e a mensagem
    # seguinte); a reentrada DECLINA de modelar um custo. Declinar do modelo é
    # escolha de contabilidade. Descartar medida não é.
    for chave, minimo, oque in (
            ("teto_leitura_min", 1, "apaga a medida de leitura"),
            ("reentrada_min", 0, "zera o custo de voltar ao contexto")):
        valor = obter(dados, f"metricas.{chave}")
        if valor is None or valor == "":
            continue
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            altos.append(f"`[metricas] {chave} = {valor!r}` não é número — a coleta "
                         "morre no `int()`, e o gancho do `avancar` engole o erro: a "
                         "métrica simplesmente nunca aparece, sem ninguém ser avisado")
        elif valor < minimo:
            altos.append(f"`[metricas] {chave} = {valor}` — {oque}: a hora humana sai "
                         "MENOR do que é, e ganho inflado por esforço subestimado é o "
                         f"erro que a ferramenta declara não poder cometer.\n"
                         f"      Use {minimo} para o mínimo; remova a chave para o padrão.")
        elif chave == "reentrada_min" and valor == 0:
            medios.append("`[metricas] reentrada_min = 0` — você declinou de modelar o "
                          "custo de voltar ao contexto. É escolha legítima de "
                          "contabilidade, e a hora humana passa a ser só leitura. Fica "
                          "dito porque o número fica menor e ninguém lembraria por quê.")

    # Orçamento. A regra da assimetria não alcança este caso: um teto mal
    # declarado não faz número sair menor — ele faz o CONTROLE não existir,
    # enquanto o projeto acredita que existe. É a outra família que o
    # `ESTADO.md` cataloga, a da falsa completude, e ela reprova igual.
    orcamento = obter(dados, "metricas.orcamento_usd")
    if orcamento is not None and orcamento != "":
        if isinstance(orcamento, bool) or not isinstance(orcamento, (int, float)):
            altos.append(
                f"`[metricas] orcamento_usd = {orcamento!r}` não é número — o teto "
                "existe no config e não confere nada. O `avancar` trata valor "
                "inválido como ausência, de propósito (ele é a espinha do fluxo e "
                "não pode quebrar por causa de um relatório), então a única coisa "
                "que denuncia isto é este achado.")
        elif orcamento <= 0:
            medios.append(
                f"`[metricas] orcamento_usd = {orcamento}` está DESLIGADO. Um teto "
                "de zero barraria todo `avancar` para sempre, então zero e negativo "
                "desligam — o que é o oposto do que a declaração parece dizer. "
                "Remova a chave se é isso que você quer; use valor positivo se quer teto.")
        elif ligado is False:
            altos.append(
                f"`[metricas] orcamento_usd = {orcamento}` com `ligado = false` é "
                "controle INERTE: nada coleta, então o teto nunca dispara.\n"
                "      Mesma família do ator de perfil declarado sem comando que o "
                "assuma — controle declarado sem mecanismo que o execute.\n"
                "      Ligue a coleta, ou remova o orçamento.")

    try:
        sys.path.insert(0, str(pacote / "tools" / "metrics"))
        from metrics import PRECOS_PADRAO
    except Exception:
        PRECOS_PADRAO = {}          # sem a tabela, os outros achados seguem
    precos = obter(dados, "metricas.precos") or {}
    if PRECOS_PADRAO and isinstance(precos, dict):
        for chave, valor in sorted(precos.items()):
            if chave not in PRECOS_PADRAO:
                medios.append(
                    f"`[metricas.precos] {chave}` não é uma das quatro chaves que a "
                    f"ferramenta lê ({', '.join(sorted(PRECOS_PADRAO))}) — está sendo "
                    "IGNORADA, e o preço que você quis trocar seguiu no padrão")
            elif isinstance(valor, bool) or not isinstance(valor, (int, float)):
                altos.append(f"`[metricas.precos] {chave} = {valor!r}` não é número — "
                             "o cálculo de custo quebra")
            elif valor <= 0:
                altos.append(f"`[metricas.precos] {chave} = {valor}` — preço zerado ou "
                             "negativo faz o custo sair MENOR do que a tabela cobra "
                             f"(o padrão é {PRECOS_PADRAO[chave]}), e custo subestimado "
                             "infla o ganho. Remova a chave para voltar ao padrão.")
            elif abs(valor - PRECOS_PADRAO[chave]) > 1e-9:
                medios.append(
                    f"`[metricas.precos] {chave}` = {valor}, e a tabela do pacote diz "
                    f"{PRECOS_PADRAO[chave]}. Pode estar certíssimo: o doutor não sabe "
                    "qual modelo você roda, e por isso não reprova. Confira.")

    # Estado da coleta. Só acusa "nunca rodou" quando há atividade para
    # coletar: num projeto recém-instalado não há nada, e acusar ali seria
    # ruído em todo primeiro `doutor` — além de reprovar a saída limpa que
    # um projeto novo tem direito de ver.
    pasta_m = raiz / ".agents" / "metrics"
    coletados = sorted(pasta_m.glob("*.json")) if pasta_m.is_dir() else []
    tem_atividade = any((raiz / ".agents" / "atividades").glob("*.md")) \
        if (raiz / ".agents" / "atividades").is_dir() else False
    if ligado is not False and tem_atividade and not coletados:
        medios.append("a coleta de métricas está ligada, há atividade no fluxo e "
                      "`<.agents>/metricas/` está vazio — nunca rodou.\n"
                      "      Ela roda sozinha no próximo `avancar`. Agora: "
                      "`metrics.py coletar --raiz .`")

    alvo_m = pasta_m / "projeto.json"
    if alvo_m.is_file():
        try:
            ultima = json.loads(alvo_m.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ultima = {}
        sem_prova = ultima.get("nao_atribuidas") or []
        if sem_prova:
            medios.append(
                f"{len(sem_prova)} atividade(s) sem prova de atribuição na última "
                f"coleta: {', '.join(sem_prova)}.\n"
                "      O total do painel está DE MENOS, não em zero. Declare `branch` "
                "(e `worktree`, se houver) no front-matter delas e colete de novo.")

    # ----------------------------------------------------------------------
    print(f"Doutor — {config}")
    print(f"         contra {raiz}")
    if fonte:
        print(f"         pacote: {fonte}")
    print()
    for rotulo, itens in (("ALTO", altos), ("MEDIO", medios)):
        for item in itens:
            print(f"[{rotulo}] {item}")
            print()
    if not altos and not medios:
        print("Nada declarado que não exista. O config bate com o repositório.")
        print()
    else:
        print(f"{len(altos)} alto(s), {len(medios)} médio(s).")
        print()

    if not getattr(args, "so_erros", False):
        falta = [(c, sem, quando) for c, sem, quando in A_LIBERAR
                 if obter(dados, c) in (None, "", [], {})]
        if falta:
            print(f"Ainda não declarado ({len(falta)}) — isto NÃO é erro:")
            print()
            for chave, sem_ela, quando in falta:
                print(f"  {chave}")
                print(f"      hoje: {sem_ela}")
                print(f"      ligue quando: {quando}")
            print()
            print("  Ligue um de cada vez, e rode o doutor depois de cada um.")
            print()
    print("O que isto NÃO prova: que os valores estão CERTOS. Ele confere que o")
    print("que está declarado existe — não que é o que você queria declarar.")
    return 1 if altos else 0


# --------------------------------------------------------------------------
# A verificação que NÃO existe aqui, e por quê
# --------------------------------------------------------------------------
# "Chave declarada que ninguém lê" parecia a checagem óbvia para uma replicação:
# um projeto novo não deveria gastar tempo preenchendo config morto. E há config
# morto de verdade — `frontend.prototipos` e a seção `[relatorios]` não são
# lidos por lugar nenhum do pacote.
#
# Ela foi tentada em duas granularidades e as duas erram:
#
#   POR CHAVE.    45 de 68 apareceram como "nunca citadas", e a maioria era
#                 falso: `[gates]` é lido pela TABELA inteira (`config.py gates`),
#                 nunca por `gates.lint`. O mesmo vale para `[documento]`, que o
#                 gerador de relatório lê de uma vez, e para `[figma]`.
#
#   POR SEÇÃO.    O oposto: `frontend` conta como citada porque ALGUMA chave dela
#                 é lida, e `frontend.prototipos` — que não é lida por ninguém —
#                 desaparece dentro da seção viva.
#
# O que faria funcionar é saber se o consumidor lê a tabela ou a chave, e isso é
# leitura de código, não grep. Fica como trabalho de quem replica: a lista de
# config morto é curta e cabe numa revisão à mão.


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("conferir", help="o config bate com o repositório?")
    c.add_argument("--config", default="", help="caminho do config.toml")
    c.add_argument("--so-erros", action="store_true", dest="so_erros",
                   help="omite a lista do que ainda não está declarado")
    c.add_argument("--raiz", default=".", help="raiz do repositório")
    c.set_defaults(fn=cmd_conferir)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except DoutorError as exc:
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
