#!/usr/bin/env python3
"""Track where each activity stands in the Elcamargo AI development flow.

State lives in one file per activity under `<.agents>/atividades/<id>.md`, never
in a shared list, so two worktrees running in parallel never contend for the
same file. `Atividades_em_andamento_com_IA.md` is a generated index: it is
derived from those files and can be rebuilt at any time with `indice`.

Every mutation takes an exclusive lock. One file per activity stops two writers
from sharing a file; it does not stop two writers from reading the same state
and overwriting each other. `os.replace` is atomic, not a lock.

`<.agents>` always resolves to the main repository, even when the caller runs
inside a worktree — see `resolve_agents_dir`.

Stdlib only, by design: this tool ships inside a zip and must run anywhere.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows não tem flock; `msvcrt` abaixo cobre o caso.
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None  # type: ignore[assignment]

# The canonical flow. This constant is the machine-readable source of truth;
# FLOW.md is its prose counterpart and must be kept in step with it.
# `nome` é o ENDEREÇO — o que se invoca, e o que fica gravado no arquivo de
# estado. `cargo` é o que se LÊ: quem faz aquele trabalho, dito como se diria de
# uma pessoa. Os dois existem porque servem a leitores diferentes, e usar o
# endereço como rótulo obriga quem lê a traduzir `elcamargo-system-analysis-reviewer`
# para "quem confere a especificação" toda vez.
#
# O que o código decide POR STEP mora aqui também, e os mapas de mais abaixo se
# derivam disto. Até 2.61.0 eram literais soltos, cada um com o número do step
# repetido à mão: renumerar ou fundir steps exigia lembrar de todos.
#   `confere`      o step cujo trabalho este confere. É o que faz uma trilha
#                  avisar quando tira o conferidor e deixa o produtor.
#   `verificacao`  tirá-lo do fluxo tira justamente o que ele existe para dar.
#                  Pode ser desligado pelo projeto, mas nunca em silêncio.
#   `modelo`       o modelo do disparo do step; sem a chave, herda de quem
#                  dispara. A regra em references/model-policy.md.
# O step de portão continua sendo o de `tipo` "humano".
STEPS: dict[int, dict] = {
    1: {"nome": "elcamargo-board-git-management", "tipo": "skill",
        "cargo": "Gestor da Atividade", "modelo": "sonnet"},
    2: {"nome": "elcamargo-business-analysis-reviewer", "tipo": "skill",
        "cargo": "Revisor de Negócio"},
    3: {"nome": "elcamargo-system-analyst", "tipo": "skill",
        "cargo": "Analista de Sistema"},
    4: {"nome": "elcamargo-system-analysis-reviewer", "tipo": "skill",
        "cargo": "Revisor da Especificação", "confere": 3, "verificacao": True},
    5: {"nome": "Revisão humana da especificação", "tipo": "humano",
        "cargo": "Portão humano · Especificação", "confere": 3},
    6: {"nome": "elcamargo-ux-reviewer", "tipo": "skill",
        "cargo": "Designer de Telas"},
    7: {"nome": "Revisão humana das telas", "tipo": "humano",
        "cargo": "Portão humano · Telas", "confere": 6},
    8: {"nome": "elcamargo-developer", "tipo": "skill",
        "cargo": "Desenvolvedor"},
    9: {"nome": "elcamargo-development-reviewer", "tipo": "skill",
        "cargo": "Revisor da Entrega", "confere": 8, "verificacao": True},
    10: {"nome": "Validação humana da entrega", "tipo": "humano",
         "cargo": "Portão humano · Entrega"},
}

# Which steps each track runs. A track is chosen once, at step 1, and recorded
# in the activity file so later steps cannot silently drift into another track.
TRILHAS: dict[str, list[int]] = {
    "completa": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "sistema": [1, 3, 4, 5, 6, 7, 8, 9, 10],
    # Correção pontual não passa por especificação nem por tela, então também
    # não passa pelos portões que existem para validá-las.
    "curta": [1, 8, 9, 10],
    # O Fluxo Rápido. Mantém quem PRODUZ — especificação de sistema,
    # tela e código — e o revisor da entrega, e corta as três conferências que
    # ficam entre eles: o step 4 (a SDD confere contra o que o negócio pediu) e
    # os portões 5 e 7.
    #
    # A diferença para a `curta` não é de tamanho, é de natureza: a `curta` não
    # passa pelos portões 5 e 7 porque não produz nada que eles validem; a
    # `rapida` **produz** a especificação e a tela, e decide não conferi-las.
    # Por isso ela avisa no `iniciar`, e a `curta` não — ver `avisos_da_trilha`.
    "rapida": [1, 3, 6, 8, 9, 10],
    # Revisar o trabalho de OUTRA pessoa, num card que não é seu. Não produz
    # nada: confere o que já foi entregue contra o que o card pediu.
    #
    # O step 2 lê o card e produz a especificação de negócio, que aqui serve de
    # BASELINE — a lista do que dá para cobrar. O step 4 confere contra ela o
    # que o dev escreveu, se ele escreveu alguma coisa. O step 9 revisa o
    # código. O portão 10 é seu veredicto.
    #
    # A forma da trilha é o que a torna segura: sem o step 8, o step 9 não tem
    # a quem devolver correção — ele relata, e quem conserta é o dono do card.
    # Ver `references/foreign-review.md`.
    # Pedida pela gerência do projeto em 18/09/2026, com o custo de qualidade
    # ASSUMIDO por quem a pediu. Ela mantém só quem PRODUZ — especificação de
    # sistema, tela e código — e vai direto ao portão humano.
    #
    # É a `rapida` sem o step 9, e essa subtração é de outra ordem: a `rapida`
    # corta conferências de DOCUMENTO e mantém a última conferência do CÓDIGO.
    # Esta corta também a do código. O `FLOW.md` já dizia, antes de ela existir,
    # que tirar o step 9 "não deixaria o fluxo rápido — deixaria o fluxo sem
    # função", e a frase continua lá de propósito: a trilha existe porque foi
    # pedida, não porque o pacote a recomenda.
    #
    # Consequência que nenhum aviso genérico alcança: sem entrar no step 9,
    # NENHUMA conferência é registrada como `exigida` — então o `concluir` não
    # segura nada. Árvore, memória e guardas não são conferidos e não aparecem
    # como lacuna, porque nunca foram pedidos.
    "ultra-rapida": [1, 3, 6, 8, 10],
    # O par ANALISTA -> DEV, pedido em 21/09/2026. A ferramenta nasceu do modo
    # de trabalho de quem faz a análise E implementa; nem todo dev especifica, e
    # nem todo analista constrói. Estas duas partem o fluxo no portão 5, que é
    # onde a especificação deixa de ser proposta e vira contrato.
    #
    # **Somadas, dão exatamente a `completa`**, e a interseção é só o step 1 —
    # que cada uma precisa para abrir a própria atividade. Nada do fluxo se
    # perde no corte e nada roda duas vezes; há teste prendendo isso, porque a
    # propriedade é o que torna o par seguro e ela não se vê olhando as duas
    # listas separadas.
    #
    # A TELA É DO ANALISTA, pedido do time em 21/09/2026. A `especificacao` vai
    # até o portão 7 e entrega negócio, sistema E tela decididos; a `construcao`
    # implementa contra os três.
    #
    # Isso dá à `construcao` a MESMA FORMA da `curta` — `1 → 8 → 9 → 10` — e a
    # diferença inteira está no que ela herda. Uma `construcao` que abrisse sem
    # a especificação SERIA uma `curta`, com o step 9 rodando três das seis
    # frentes. É por isso que o guarda dela recusa em vez de avisar: aqui a
    # degradação é invisível na lista de steps.
    "especificacao-completa": [1, 2, 3, 4, 5, 6, 7],
    # A mesma porta para quem está na `sistema`: card claro, sem análise de
    # negócio a revisar. Sem ela, quem não tem step 2 a rodar ou abria a
    # `especificacao` e era obrigado ao 2, ou abria a `construcao` sozinha — e
    # batia no guarda que recusa, com razão. O guarda estava certo; faltava a
    # porta. Achado pela sessão `acme-backoffice` em 21/09/2026, onde
    # as três atividades vivas eram todas `sistema`.
    #
    # `especificacao-sistema` ∪ `construcao` == `sistema`, do mesmo jeito que
    # `especificacao` ∪ `construcao` == `completa`.
    "especificacao-sistema": [1, 3, 4, 5, 6, 7],
    "construcao": [1, 8, 9, 10],
    "revisao": [1, 2, 4, 9, 10],
    # As duas metades de um mesmo card, entregues em tempos diferentes. Pedido
    # da gerência em 15/09/2026: adiantar o backend do app, que serve o
    # front web E o mobile, para o time mobile não esperar o front web ficar
    # pronto. O card fica bloqueado com `Aguardando frontend` no meio.
    #
    # Cada metade ESPECIFICA as duas camadas e IMPLEMENTA uma. A que ela não
    # implementa é o **contrato** — e o contrato é o produto de verdade da
    # `backend`, porque quem o consome (o mobile) não está neste fluxo.
    #
    # `backend` não tem 6 nem 7: não há tela para desenhar nem para validar.
    "backend": [1, 2, 3, 4, 5, 8, 9, 10],
    # `frontend` tem a forma da `completa`, e é uma trilha à parte por três
    # motivos que a forma não mostra: o escopo que o step 8 obedece, a regra de
    # completar a especificação que já existe em vez de reescrevê-la, e a
    # exigência de rodar DEPOIS da `backend` — decidida em 15/09/2026, com a
    # validação da entrega INTEIRA por conta dela.
    "frontend": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
}

# A camada que a trilha implementa. Ausente significa "tudo", que é o
# comportamento de toda atividade anterior a 2.39.0 — e é por isso que o campo
# é derivado da trilha em vez de ser uma bandeira: bandeira se esquece, e uma
# atividade sem escopo declarado teria o step 8 decidindo sozinho.
ESCOPO_DA_TRILHA: dict[str, str] = {"backend": "backend", "frontend": "frontend"}

# A metade oposta, que a trilha ESPECIFICA e não implementa.
OUTRA_CAMADA = {"backend": "frontend", "frontend": "backend",
                "especificacao-completa": "construcao",
                # O valor aqui é usado só para achar o SUFIXO do par, e as duas
                # especificações compartilham `-especificacao`. Qualquer uma das
                # duas serve como chave; nomear a `-completa` é arbitrário e
                # está dito para ninguém ler como "a construcao exige a
                # completa".
                "construcao": "especificacao-completa",
                "especificacao-sistema": "construcao"}

# Qual trilha roda DEPOIS de qual, no mesmo card. Era um `if trilha !=
# "frontend"` dentro do guarda; virou dado quando o segundo par apareceu, e a
# generalização é o que impede o terceiro de virar um terceiro `if`.
PRECISA_DA_ANTERIOR = {"frontend": "backend",
                       "construcao": "especificacao-completa"}

# Quando mais de uma trilha serve de anterior, a mensagem tem de dizer as duas —
# senão ela nomeia uma e quem está na outra conclui que abriu errado.
ANTERIORES_ACEITAS = {"construcao": ("especificacao-completa",
                                     "especificacao-sistema")}

# A `frontend` roda depois da `backend`, sempre. Para achar a outra metade sem
# adivinhação, o id das duas sai do mesmo card com o sufixo da camada.
SUFIXO_DE_ESCOPO = {"backend": "-backend", "frontend": "-frontend",
                    "especificacao-completa": "-especificacao",
                    # Sufixo COMPARTILHADO com a `especificacao`, de propósito:
                    # do lado do dev não importa qual das duas produziu a
                    # spec, importa que `<card>-especificacao` existe. Sufixo
                    # próprio obrigaria o guarda a procurar em dois lugares e
                    # daria dois ids possíveis para a mesma coisa.
                    "especificacao-sistema": "-especificacao",
                    "construcao": "-construcao"}

# A conferência que cada metade tem de fechar, registrada como `exigida` ao
# ENTRAR no step 9 — quem descobre a obrigação é quem a registra, e obrigação
# escrita só na skill é conselho.
#
# Ela é re-exigida a cada entrada no step 9, inclusive nas voltas de correção.
# Um contrato provado na volta 1 e um código mudado na volta 2 fecham com `ok`
# velho, que é a forma exata do defeito que este pacote já consertou duas
# vezes: a decisão mudou e o carimbo ficou.
# De que artefato cada frente do step 9 precisa para ter contra o que conferir.
# A skill decidia isso por NOME DE TRILHA, e o proxy quebrou na `construcao`: a
# mesma trilha tem `sdd-negocio` se herdou da `especificacao-completa` e não tem
# se herdou da `especificacao-sistema`, que pula o step 2.
#
# Pior: a tabela da skill lista trilhas por nome e a `construcao` não estava em
# nenhuma linha — lida ao pé da letra, ela PULA as duas frentes que a trilha
# existe para habilitar. E frente sem baseline não fica quieta: ela infere, e
# produz achado contra um negócio que ninguém escreveu.
#
# Achado pela sessão `acme-backoffice` em 21/09/2026, antes de a
# primeira `construcao` rodar — e as três atividades vivas lá são `sistema`,
# então a primeira de todas seria a que expõe o defeito.
BASELINE_DA_FRENTE = {
    "implemented-sdd": "sdd-sistema",
    "implemented-business": "sdd-negocio",
}


def entrega_nao_commitada(
        atividade: "Atividade") -> tuple[int | None, str]:
    """Quantas entradas a árvore da atividade tem sem commitar.

    **As duas frentes que ESCREVEM — `quality` e `runtime` — rodam em worktree
    própria**, e worktree nasce do que está COMMITADO. Se a entrega ainda vive
    na árvore, elas recebem a base limpa e medem o código de ANTES.

    Medido em 21/09/2026 no `acme-backoffice`: 44 entradas vivas na
    árvore, e as duas worktrees de frente chegaram com zero. As duas
    perceberam, espelharam e provaram por MD5 antes de medir — **mérito delas,
    não do mecanismo**.

    O pior desfecho é o silencioso: uma frente menos cuidadosa mede a base e
    reporta *"não reproduzi"*. Numa volta de correção isso não parece erro —
    **parece confirmação de conserto**, que é o falso negativo mais caro que
    este fluxo pode produzir.

    É comum, e não é descuido de ninguém: o commit é autorizado uma etapa por
    vez, e a entrega passa horas viva na árvore.

    **Devolve o número E a árvore onde ele foi contado**, e isso não é cortesia.
    A árvore sai do campo `worktree`. Até 2.45.5 esse campo nascia do **cwd** de
    quem abriu a atividade, e em 21/09/2026 três aberturas seguidas nasceram
    apontando para a árvore principal: com o campo errado, este contador
    reportava a sujeira de OUTRA sessão — medido, 8 entradas de uma frente
    alheia sobre uma atividade cuja árvore estava limpa. **Quem lesse aquilo
    espelharia trabalho alheio para dentro da worktree da frente.**

    Desde 2.46.0 o campo nasce `PENDENTE`, e então **não há o que contar**:
    devolve `(None, LUGAR_PENDENTE)`. O caminho antigo — cair na raiz do projeto
    quando o campo não aponta para um diretório — mentia duas vezes: contava a
    árvore errada e, quando ela estava limpa, devolvia um ZERO que se lê como
    "entrega commitada". Não saber não é a mesma coisa que estar limpo.
    """
    onde = uma_linha(atividade.meta.get("worktree") or "")
    if not onde or onde == LUGAR_PENDENTE or not Path(onde).is_dir():
        return None, onde or LUGAR_PENDENTE
    raiz = Path(onde)
    saida = _git(["status", "--porcelain"], raiz)
    return len([l for l in saida.splitlines() if l.strip()]), str(raiz)


def frentes_com_baseline(atividade: "Atividade") -> tuple[list[str], list[str]]:
    """Quais frentes do step 9 têm contra o que conferir, e quais não têm.

    Sai dos ARTEFATOS REGISTRADOS, não do nome da trilha. O critério já estava
    escrito na skill — *"o critério para pular uma frente é um só: ela não tem
    contra o que conferir"* —, e era a tabela por trilha que não o cumpria.
    """
    tem = {tipo for tipo, *_ in atividade.artefatos}
    com = [f for f, art in BASELINE_DA_FRENTE.items() if art in tem]
    sem = [f for f, art in BASELINE_DA_FRENTE.items() if art not in tem]
    return sorted(com), sorted(sem)



# O contexto que roda o step 9 não pode ser o que fez o step 8. A regra estava
# escrita desde o começo — "o próximo step roda em contexto novo, nunca a mesma
# janela" — e só o modo orquestrador a fazia valer. Fora dele, nada impedia a
# janela que escreveu o código de revisá-lo e aprová-lo, e revisor que leu o
# raciocínio do autor tende a concordar com ele.
#
# **Contexto é sessão MAIS subagente.** No modo orquestrador o 8 e o 9 rodam na
# MESMA sessão, cada um num `elcamargo-step-runner` — o `session_id` coincide
# e está certo. O que os separa é o `agent_id`, que o harness só põe no evento
# de hook quando a chamada nasce dentro de um subagente.
#
# Quem sabe isso é o hook, não o `flow_state`: não há variável de ambiente com
# a sessão. O `anchor.py --contexto` roda no PreToolUse de todo Bash e grava
# `.agents/.contexto-atual` um instante antes de o comando rodar.
CONTEXTO_VALE_POR = 120  # segundos: depois disso o registro é de outra chamada


def contexto_atual(agents: Path) -> str:
    """`<sessão>/<subagente ou janela>` de quem chamou, ou vazio se não se sabe.

    Vazio é "não sei", e quem lê trata assim: sem o hook (outro harness, pacote
    sem hooks, comando digitado no terminal) a trava não acusa ninguém. Registro
    velho também é vazio — ele descreve a chamada de antes, não esta.
    """
    try:
        dados = json.loads((agents / ".contexto-atual").read_text(encoding="utf-8"))
        if time.time() - float(dados.get("quando", 0)) > CONTEXTO_VALE_POR:
            return ""
        sessao = str(dados.get("sessao") or "").strip()
        agente = str(dados.get("agente") or "").strip()
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if not sessao:
        return ""
    return f"{sessao}/{agente or 'janela'}"


def mesmo_contexto_do_8(atividade: "Atividade", agents: Path,
                        na_saida: bool = True) -> str:
    """A frase que acusa, quando quem está no step 9 é quem fez o step 8.

    No `status` ela é aviso, e chega no começo do step, quando ainda dá para
    parar antes de revisar. No `avancar` para o 10 ela recusa.
    """
    do_8 = str(atividade.meta.get("contexto_do_8") or "")
    agora_ = contexto_atual(agents)
    if not do_8 or not agora_ or do_8 != agora_:
        return ""
    onde = ("na mesma janela" if agora_.endswith("/janela")
            else "no mesmo subagente")
    return (
        f"MESMO CONTEXTO DO STEP 8: o step 9 de {atividade.meta['id']} está "
        f"rodando {onde} que implementou\n  a entrega ({agora_}). Revisor que "
        "leu o raciocínio do autor concorda com ele —\n  é a razão de o step 9 "
        "existir separado. Abra sessão nova (ou `/clear`) ou dispare o\n  step "
        "num subagente, e rode a revisão de lá."
        + ("\n  Se a revisão rodou mesmo assim, e é deliberado: "
           "`--forcar --nota '<por quê>'`." if na_saida else
           "\n  O `avancar` para o portão 10 recusa a partir deste contexto.")
    )


# As seis frentes do step 9, pelo nome do agente sem o prefixo do pacote — o
# mesmo nome que a perna sombra grava no registro.
FRENTES_DO_STEP_9 = ("code-reviewer", "security-reviewer", "quality-reviewer",
                     "runtime-reviewer", "implemented-sdd-reviewer",
                     "implemented-business-reviewer")


def _vereditos_da_sombra(agents: Path) -> dict:
    """O critério da perna sombra sobre o registro deste projeto. Nunca levanta."""
    try:
        import importlib.util  # noqa: PLC0415
        arquivo = (Path(__file__).resolve().parent.parent / "shadow-leg"
                   / "shadow_leg.py")
        spec = importlib.util.spec_from_file_location("shadow_leg", arquivo)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo.vereditos(modulo._ler(str(agents / "perna-sombra.jsonl")))
    except Exception:  # noqa: BLE001
        return {}


def modelo_das_frentes(agents: Path) -> tuple[dict[str, str], list[str]]:
    """`[revisao.modelo]`: o que vale, por frente, e o que foi pedido e não vale.

    **Só vale com veredito `adota` da perna sombra** para aquela frente e aquele
    modelo. A pesquisa e o critério pré-registrado dizem a mesma coisa: revisor
    mais fraco pode piorar a revisão, e um `bloqueia` que o modelo barato
    perdeu não aparece para ninguém. A chave sem o número atrás é exatamente a
    recomendação antes de medir que `references/model-policy.md` recusa — então
    ela fica ignorada, e diz por quê, em vez de valer calada.
    """
    try:
        import config as C  # tardio: config.py importa deste módulo
        pedido = C.obter("revisao.modelo", {}, agents) or {}
    except Exception:  # noqa: BLE001
        return {}, []
    if not isinstance(pedido, dict) or not pedido:
        return {}, []
    vereditos = _vereditos_da_sombra(agents)
    vale, ignoradas = {}, []
    for frente, modelo in sorted(pedido.items()):
        modelo = str(modelo or "").strip()
        if not modelo:
            continue
        if frente not in FRENTES_DO_STEP_9:
            ignoradas.append(f"`{frente}` não é frente do step 9 (as seis: "
                             + ", ".join(FRENTES_DO_STEP_9) + ")")
            continue
        v = vereditos.get((frente, modelo))
        if v and v.get("adota"):
            vale[frente] = modelo
        else:
            ignoradas.append(
                f"`{frente} = \"{modelo}\"` IGNORADA: "
                + (v["veredito"] if v else
                   "nenhum par da perna sombra com esse modelo nesta frente"))
    return vale, ignoradas


EXIGENCIA_DO_STEP_9 = {
    "backend": ("contrato",
                "cada rota que o `sdd-frontend` promete existe e responde o "
                "que está escrito — provado por execução, não por leitura"),
    "frontend": ("entrega-ponta-a-ponta",
                 "a entrega INTEIRA funciona: backend já mesclado mais a tela "
                 "nova, no fluxo que o usuário percorre"),
    # A `construcao` implementa contra uma especificação que OUTRA PESSOA
    # escreveu, dias antes. Divergência entre o que a spec diz e o que o código
    # precisou fazer não pode sair como detalhe de implementação: ela volta ao
    # analista, e é ele quem decide se a spec muda ou se o código está errado.
    # Os mesmos avisos da `especificacao`, mais o que é próprio dela. Montado
    # por referência e não por cópia: dois textos iguais divergem na primeira
    # correção que alguém faz num só.
    "especificacao-sistema": (),
    "construcao": ("especificacao-conferida",
                   "o que foi construído confere com a `sdd-sistema` e as "
                   "decisões de tela herdadas — "
                   "e toda divergência está NOMEADA no relatório, com o que a "
                   "spec dizia e o que ficou"),
}

# Que artefato cada conferência existe para validar. Um step que ficou fora da
# trilha só é perda quando a trilha PRODUZ o que ele conferiria: sem isso, o
# aviso vira ruído que se aprende a ignorar — e aviso ignorado não protege nada.
# Quem confere o que, derivado de `STEPS`. O `9: 8` esteve AUSENTE até 2.42.0,
# e a ausência era um buraco: o 9 já era declarado verificação, mas nenhuma
# trilha sem ele avisava nada — porque o aviso se deriva deste mapa, não
# daquele conjunto. Só apareceu quando alguém pediu uma trilha sem step 9.
# Com os dois atributos lado a lado na mesma linha de `STEPS`, a falta de um
# fica à vista de quem lê o outro.
CONFERE_O_QUE_O_STEP_PRODUZ: dict[int, int] = {
    n: d["confere"] for n, d in STEPS.items() if d.get("confere")}

STEPS_DE_VERIFICACAO = {n for n, d in STEPS.items() if d.get("verificacao")}
STEPS_DE_PORTAO = {n for n, d in STEPS.items() if d["tipo"] == "humano"}

# O SEGUNDO EIXO da escolha, pedido pela avaliação externa de 15/10/2026. A
# trilha diz QUE TIPO de trabalho é; o risco diz quanto custa errar nele. Até
# aqui só a trilha existia, e nada impedia um conserto de login de ir pela
# `ultra-rapida`, que não tem step 9.
#
# O risco é proposto pelo step 1 a partir deste checklist e confirmado pela
# pessoa. Não é derivado da lista: a lista diz onde OLHAR, e quem sabe se a
# mudança mexe de verdade no pagamento é quem leu o card.
RISCOS = ("alto", "padrao", "baixo")
SUPERFICIES_DE_RISCO: dict[str, str] = {
    "autenticacao": "login, sessão, senha, permissão, papel de usuário",
    "pagamento": "cobrança, saldo, preço, crédito, qualquer valor em dinheiro",
    "dados-pessoais": "CPF, e-mail, telefone, endereço — o que a LGPD alcança",
    "migracao": "schema, dado que já existe em produção, script que roda uma vez",
    "contrato-publico": "API, evento ou arquivo que outro time ou app consome",
}
# O que o risco alto torna obrigatório na conferência do step 9.
CONFERENCIA_DO_RISCO_ALTO = (
    "seguranca",
    "risco alto: a frente de segurança roda e registra o veredicto; "
    "`nao-coberta` não encerra a atividade")
# O portão que o risco alto não deixa sair por `nao-coberta`.
GATE_DO_RISCO_ALTO = "sast"


def implementa_sem_revisar(trilha: str) -> bool:
    """A trilha escreve código (step 8) e não o revisa (step 9)."""
    steps = TRILHAS.get(trilha, [])
    return 8 in steps and 9 not in steps


def ler_superficies(texto: str) -> list[str]:
    nomes = [s.strip() for s in (texto or "").replace(" ", ",").split(",")
             if s.strip()]
    estranhas = [s for s in nomes if s not in SUPERFICIES_DE_RISCO]
    if estranhas:
        raise FlowStateError(
            f"Superfície desconhecida: {', '.join(estranhas)}. Use uma de: "
            f"{', '.join(SUPERFICIES_DE_RISCO)}.")
    return list(dict.fromkeys(nomes))


def conferir_risco(risco: str, superficies: list[str], trilha: str) -> list[str]:
    """Recusa a combinação que se contradiz; devolve os avisos da que passa.

    Recusa sem `--forcar` de propósito: a saída de uma combinação recusada é
    mudar o risco ou a trilha, e as duas mudanças ficam escritas. Um
    `--forcar` aqui seria um terceiro jeito, que não diz qual das duas mudou.
    """
    if risco not in RISCOS:
        raise FlowStateError(f"Risco inválido: {risco}. Use um de: {', '.join(RISCOS)}.")
    if risco == "alto" and implementa_sem_revisar(trilha):
        raise FlowStateError(
            f"Risco alto na trilha `{trilha}`, que implementa e não tem step 9: "
            "o código iria da escrita direto à pessoa.\n  Escolha uma trilha "
            "com step 9 (`rapida`, `curta`, `sistema`...), ou, se o risco "
            "não é alto,\n  diga isso com `--risco padrao` e o motivo na nota.")
    if risco == "baixo" and superficies:
        raise FlowStateError(
            f"Risco baixo com superfície marcada ({', '.join(superficies)}) se "
            "contradiz.\n  Se a mudança toca mesmo essa superfície, o risco é "
            "`padrao` ou `alto`; se não toca, tire a superfície.")
    avisos = []
    if risco == "padrao" and superficies:
        avisos.append(
            f"RISCO PADRÃO COM SUPERFÍCIE MARCADA ({', '.join(superficies)}): "
            "decisão de quem abriu, e fica no histórico.\n            O step 9 "
            "não torna a frente de segurança obrigatória; se ela não rodar, "
            "nada segura.")
    if risco == "baixo" and trilha in ("completa", "sistema", "frontend"):
        avisos.append(
            f"RISCO BAIXO NA TRILHA `{trilha}`: nada é cortado, e os portões 5 e "
            "7 vão perguntar\n            sobre especificação e tela. Se é "
            "correção pontual, a `curta` existe para isso.")
    return avisos


STATUS_ABERTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"

# O lugar que a atividade AINDA NÃO TEM.
#
# Até 2.45.5 o `iniciar` gravava branch e worktree do **cwd de quem chamou** —
# e quem chama o `iniciar` está, por definição, num lugar que não é o da
# atividade: é o **step 1** que cria a branch e a worktree, depois. O campo
# nascia descrevendo a árvore principal de quem abriu o card, e em 21/09/2026
# três aberturas seguidas nasceram assim, corrigidas à mão depois.
#
# O estrago não é o campo feio: é que ele carimba de CERTO um lugar errado.
# `entrega_nao_commitada` contava a sujeira da árvore alheia e reportava como
# entrega da atividade; a proposta de fazer o `concluir` desmontar a árvore
# leria este mesmo campo para escolher o que apagar.
#
# Lacuna se declara, não se presume. `PENDENTE` é a declaração — e `conciliar_local`
# a resolve sozinha no primeiro `avancar` rodado de dentro da árvore de verdade.
LUGAR_PENDENTE = "PENDENTE"

INDEX_NAME = "Atividades_em_andamento_com_IA.md"
LOCK_NAME = ".flow-state.lock"

# Every separator `str.splitlines` recognises. Neutralising only "\n" is not
# enough: a note pasted from an Azure card carries CRLF, and everything after
# the first "\r" would be silently dropped on the next write — or, worse, be
# read back as a Markdown heading and truncate the table it landed in.
SEPARADORES = "\n\r\v\f\x1c\x1d\x1e\x85  "
_RE_QUEBRA = re.compile(f"[{re.escape(SEPARADORES)}]+")

# An id becomes a file name. Anything that could climb out of the directory, or
# hide the activity from a non-recursive glob, is refused.
_RE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class FlowStateError(RuntimeError):
    """Represent a condition that must stop the flow instead of being guessed."""


# --------------------------------------------------------------------------
# Location
# --------------------------------------------------------------------------


def _parece_agents(caminho: Path) -> bool:
    """Is this really a flow `.agents`, or just a directory with the name?"""
    return ((caminho / "elcamargo-flow").is_dir()
            or (caminho / "config.toml").is_file()
            or (caminho / "atividades").is_dir())


def resolve_agents_dir() -> Path:
    """Return the `.agents` directory of the main repository.

    Three cases, in this order:

    1. `ELCAMARGO_AGENTS_DIR`, when the caller knows better than we do.
    2. The caller is already inside `.agents`. This is checked *before* asking
       git, because `.agents` is itself an independent repository (it holds the
       backup history), so from inside it `--git-common-dir` describes that
       repository and not the project.
    3. Ask git. A worktree has its own working directory and does not carry
       `.agents`, which is untracked; `--git-common-dir` points at the main
       repository's `.git` from anywhere, so its parent is the one directory
       every worktree agrees on.

    Whatever the route, the result is checked for actually being ours. A
    directory that merely happens to be named `.agents` — an unrelated
    ancestor, a stale env var — is refused rather than silently written into.
    """
    override = os.environ.get("ELCAMARGO_AGENTS_DIR")
    if override:
        agents = Path(override).expanduser().resolve()
        if not agents.is_dir():
            raise FlowStateError(
                f"ELCAMARGO_AGENTS_DIR aponta para {agents}, que não existe."
            )
        return agents  # an explicit override is trusted as given

    cwd = Path.cwd().resolve()
    for candidato in (cwd, *cwd.parents):
        if candidato.name == ".agents" and _parece_agents(candidato):
            return candidato

    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        )
    except FileNotFoundError as exc:
        raise FlowStateError("Não encontrei o comando `git`.") from exc
    except subprocess.CalledProcessError as exc:
        detalhe = (exc.stderr or "").strip().splitlines()
        raise FlowStateError(
            "git não resolveu o repositório"
            + (f": {detalhe[0]}" if detalhe else "")
            + ". Rode a partir do projeto, ou defina ELCAMARGO_AGENTS_DIR."
        ) from exc

    agents = Path(resultado.stdout.strip()).parent / ".agents"
    if not agents.is_dir():
        raise FlowStateError(
            f"Não encontrei {agents}. O pacote precisa de um .agents na raiz "
            "do projeto."
        )
    if not _parece_agents(agents):
        raise FlowStateError(
            f"{agents} existe mas não parece um .agents do fluxo — não tem "
            "elcamargo-flow/, config.toml nem atividades/. Rode o install.sh "
            "ou defina ELCAMARGO_AGENTS_DIR."
        )
    return agents


def steps_assets(agents: Path | None = None) -> list[int]:
    """Os steps que este projeto declarou usar. Sem declaração, todos.

    Um time onde o UX é de outra pessoa legitimamente não roda o step 6. O que
    não é legítimo é desligar verificação em silêncio, e por isso a lista do que
    ficou de fora acompanha a atividade e todo relatório dela.
    """
    try:
        import config as _cfg  # tardio: config.py importa deste módulo
        declarados = _cfg.obter("fluxo.steps", None, agents)
    except Exception:
        declarados = None
    if not declarados:
        return sorted(STEPS)
    try:
        assets = sorted({int(s) for s in declarados} & set(STEPS))
    except (TypeError, ValueError):
        raise FlowStateError(
            "`fluxo.steps` no config precisa ser uma lista de números de step."
        ) from None
    if 1 not in assets:
        raise FlowStateError(
            "`fluxo.steps` não pode desligar o step 1: é ele que abre a "
            "atividade e decide a trilha."
        )
    return assets


def steps_desligados(agents: Path | None = None) -> list[int]:
    return sorted(set(STEPS) - set(steps_assets(agents)))


def avisar_desligados(agents: Path | None = None) -> list[str]:
    """Avisos altos para o que foi desligado e não deveria passar batido."""
    desligados = set(steps_desligados(agents))
    avisos = []
    portoes = sorted(desligados & STEPS_DE_PORTAO)
    if portoes:
        avisos.append(
            "PORTÃO HUMANO DESLIGADO: "
            + "; ".join(rotulo(n) for n in portoes)
            + ". São a parte mais barata e mais valiosa do fluxo — minutos de "
              "uma pessoa contra horas construídas sobre base errada."
        )
    verificacao = sorted(desligados & STEPS_DE_VERIFICACAO)
    if verificacao:
        avisos.append(
            "VERIFICAÇÃO DESLIGADA: "
            + "; ".join(rotulo(n) for n in verificacao)
            + ". Sem ela o fluxo mantém a cerimônia e perde a conferência — o "
              "que é pior que não usar o fluxo, porque parece rigoroso."
        )
    return avisos


# Avisos que não decorrem de conferência ausente, e sim da NATUREZA da trilha.
# `avisos_da_trilha` deriva o resto de `CONFERE_O_QUE_O_STEP_PRODUZ` — o que
# não cabe ali é o que uma trilha faz de diferente, não o que ela deixa de
# fazer.
AVISOS_PROPRIOS_DA_TRILHA: dict[str, tuple[str, ...]] = {
    # A `curta` não produz especificação nem tela, então o aviso genérico não
    # tem o que dizer — e havia algo a dizer. O step 9 dela roda TRÊS das seis
    # frentes, e as duas que faltam são as únicas que respondem "é isto que foi
    # pedido?". Medido pela sessão `acme-app-aa` em 15/09/2026,
    # sobre as quatro `curta` que chegaram ao portão 10: o achado que mudou
    # decisão veio de execução ou de qualidade, nunca de leitura contra
    # especificação.
    "curta": (
        "O STEP 9 RODA TRÊS DE SEIS FRENTES: `code`, `quality` e `security`. As "
        "duas que ficam de fora — SDD implementada e negócio implementado — são "
        "as únicas que respondem *\"é isto que foi pedido?\"*, e elas precisam "
        "de um documento que esta trilha não produz.",
        "ENTÃO A EXECUÇÃO É A ÚNICA TESTEMUNHA EXTERNA. Não há baseline de "
        "documento: a linha de comparação é o código de antes mais o card. "
        "Dispensar a frente de execução aqui não é perder uma dimensão, é ficar "
        "sem nenhuma.",
    ),
    "especificacao-completa": (
        "ESTA TRILHA NÃO CONSTRÓI NADA. Ela vai do card ao PORTÃO 7 e para: "
        "especifica negócio, sistema e tela, e o card fica `Aguardando "
        "desenvolvimento`. Quem constrói abre `<card>-construcao` na trilha "
        "`construcao`, que HERDA estes artefatos.",
        "POR ISSO O QUE VOCÊ REGISTRA COMO ARTEFATO É O PRODUTO. O dev não vai "
        "ter a sua conversa — o handoff é por arquivo. SDD de negócio, SDD de "
        "sistema e matrizes não registradas não chegam do outro lado, e a "
        "trilha de lá degrada para uma `curta` sem perceber.",
        "A TELA É SUA: os steps 6 e 7 estão nesta trilha, e as decisões de tela "
        "são o terceiro artefato que o dev vai herdar. O que você não registrar "
        "ele vai inventar no step 8.",
    ),
    "construcao": (
        "ESTA TRILHA TEM A MESMA FORMA DA `curta` — 1, 8, 9, 10 — e a diferença "
        "inteira é o que ela HERDA: negócio, sistema e tela, de "
        "`<card>-especificacao`. Se a herança não veio, PARE: sem SDD o step 9 "
        "roda três das seis frentes, e nenhuma responde \"é isto que foi "
        "pedido?\". A degradação não aparece na lista de steps.",
        "A ESPECIFICAÇÃO ENVELHECE. Entre o portão 5 e você passam dias, e o "
        "código andou. Confira contra o que EXISTE, não contra o que a spec "
        "supunha — a mesma regra que a `frontend` carrega sobre o backend.",
        "DIVERGÊNCIA VOLTA AO ANALISTA, não vira decisão sua. Achou que a spec "
        "está errada: RELATE e DEVOLVA. Você não tem step 3 para consertá-la, "
        "e corrigir a spec de quem não aprovou a correção transforma o "
        "contrato em rascunho. A conferência `especificacao-conferida` segura "
        "o `concluir` até isso estar resolvido.",
    ),
    "ultra-rapida": (
        "NÃO HÁ REVISÃO DA ENTREGA. Esta trilha não tem step 9: o código vai do "
        "desenvolvedor direto ao portão humano, sem nenhuma das seis frentes. "
        "Nada confere código, segurança, qualidade, nem se a tela funciona.",
        "E O `concluir` NÃO SEGURA NADA. As conferências — árvore, memória, "
        "guardas — são registradas como `exigida` ao ENTRAR no step 9. Sem ele, "
        "nenhuma é pedida, então nenhuma aparece como lacuna. Ausência de "
        "pendência aqui não é sinal de que está tudo certo; é sinal de que "
        "ninguém perguntou.",
        "O PORTÃO 10 É A ÚNICA CONFERÊNCIA QUE SOBROU, e ele é humano. Quem "
        "estiver nele está recebendo código que nenhuma máquina e nenhum "
        "revisor olhou — e precisa saber disso ANTES de aceitar.",
        "O CUSTO DE QUALIDADE É ASSUMIDO POR QUEM PEDIU A TRILHA. Ela foi "
        "pedida pela gerência do projeto em 18/09/2026, com essa troca "
        "explícita. Este pacote NÃO a recomenda, e o `FLOW.md` diz por quê.",
    ),
    "revisao": (
        "TRILHA DE REVISÃO: esta trilha NÃO CONSERTA NADA. Ela não tem step 8, "
        "então o step 9 não tem a quem devolver correção — os achados saem em "
        "relatório, e quem conserta é o dono do card.",
        "O QUE ELA NÃO ESCREVE: não commita, não faz push, e não publica nada "
        "no card de outra pessoa. O relatório é seu, e é você quem decide o "
        "que fazer com ele.",
        "ONDE ELA RODA: em worktree da branch que o dev entregou, para o seu "
        "trabalho na máquina não parar. Sem isso a revisão sequestra a árvore "
        "em que você está implementando.",
    ),
    "backend": (
        "ENTREGA PELA METADE, DE PROPÓSITO: o step 8 implementa SÓ o backend. "
        "O que a tela precisa fica especificado e não implementado — e o card "
        "termina bloqueado, com `Aguardando frontend`.",
        "O PRODUTO DE VERDADE É O CONTRATO: o `sdd-frontend` que esta trilha "
        "escreve é o que o time mobile vai consumir sem estar neste fluxo. "
        "Errar nele custa o trabalho de outro time, semanas depois.",
        "POR ISSO O CONTRATO SE PROVA POR EXECUÇÃO: o step 9 exercita cada rota "
        "que o `sdd-frontend` promete. A conferência `contrato` segura o "
        "`concluir` enquanto isso não acontecer.",
        "O QUE O STEP 9 NÃO DEVE ACHAR: ausência da camada de tela não é "
        "defeito aqui, é o escopo. Achado contra a metade que não foi entregue "
        "é achado contra uma decisão de quem pediu.",
    ),
    "frontend": (
        "RODA DEPOIS DA `backend`, SEMPRE. Decidido em 15/09/2026. O `iniciar` "
        "confere se a metade de trás existe e está concluída, e recusa abrir "
        "antes disso — `--forcar --nota` registra a exceção.",
        "AQUI A REVISÃO É DO TODO: o step 8 implementa só a tela, e o step 9 "
        "valida a ENTREGA INTEIRA — backend já mesclado mais a tela nova —, "
        "porque esta é a última metade e não há terceira para conferir depois.",
        "O BACKEND PODE TER ANDADO: entre as duas metades passam dias. O que a "
        "tela precisa se confere contra o backend QUE EXISTE, e não contra o "
        "`sdd-backend` de semanas atrás. Buraco achado vira especificação, não "
        "implementação — esta trilha também não escreve backend.",
    ),
}


def avisos_da_trilha(trilha: str) -> list[str]:
    """O que ESTA trilha deixa de conferir — dito uma vez, na hora da escolha.

    A trilha é decisão de quem abre a atividade, e continua sendo. O que ela não
    pode ser é **silenciosa**: quem escolhe precisa saber o que está trocando
    por tempo, e o portão 10 precisa achar isso escrito quando receber a
    entrega. É a mesma regra do `avisar_desligados`, aplicada à trilha em vez
    de ao projeto.
    """
    steps = set(TRILHAS[trilha])
    avisos = []
    for conferidor, produtor in sorted(CONFERE_O_QUE_O_STEP_PRODUZ.items()):
        if conferidor in steps or produtor not in steps:
            continue
        tipo = ("PORTÃO HUMANO FORA DA TRILHA"
                if conferidor in STEPS_DE_PORTAO else "VERIFICAÇÃO FORA DA TRILHA")
        avisos.append(
            f"{tipo}: {rotulo(conferidor)} — e a trilha `{trilha}` PRODUZ o que "
            f"ele conferiria ({rotulo(produtor)}). O artefato segue para quem "
            "constrói sem ninguém ter conferido se ele está certo."
        )
    if avisos:
        avisos.append(
            f"A trilha `{trilha}` foi escolhida por tempo, e isto é o preço "
            "dela. Está registrado no histórico da atividade para o portão 10 "
            "achar — quem valida no fim precisa saber o que não foi validado "
            "no meio."
        )
    avisos.extend(AVISOS_PROPRIOS_DA_TRILHA.get(trilha, ()))
    if trilha == "especificacao-sistema":
        # Ela é a `especificacao` sem o step 2, então carrega os avisos dela e
        # acrescenta o que muda. Herdar em vez de copiar: texto duplicado
        # diverge na primeira correção feita num lado só.
        avisos.extend(AVISOS_PROPRIOS_DA_TRILHA["especificacao-completa"])
        avisos.append(
            "SEM O STEP 2: esta é a `especificacao` para card já claro, onde "
            "não há análise de negócio a revisar. Se houver — se o card estiver "
            "ambíguo, se faltar regra, se o fluxo não fechar — a trilha certa é "
            "`especificacao-completa`, e trocar depois custa `--forcar --nota`."
        )
    return avisos


def raiz_do_projeto(agents: Path) -> Path:
    """The MAIN working tree. `.agents` sits at its root.

    Use this only for things that belong to the repository as a whole. For
    anything about the work in progress — branch, installed dependencies, the
    files being changed — use `raiz_de_trabalho`, which follows the caller.
    """
    return agents.parent


def raiz_de_trabalho(agents: Path) -> Path:
    """The working tree the caller is actually in.

    A skill run inside a worktree works on THAT tree: its branch, its
    dependencies, its files. Asking the main tree instead describes a place the
    work never touched — a mistake made twice while building this, in
    `contexto_git` and in the dependency check, which is why it lives in one
    function now.

    The exception is `.agents` itself, an independent repository holding the
    backup history. From inside it, fall back to the main tree.
    """
    cwd = Path.cwd().resolve()
    if agents in (cwd, *cwd.parents):
        return raiz_do_projeto(agents)
    topo = _git(["rev-parse", "--show-toplevel"], cwd)
    return Path(topo) if topo else raiz_do_projeto(agents)


def atividades_dir(agents: Path) -> Path:
    d = agents / "atividades"
    d.mkdir(parents=True, exist_ok=True)
    return d


def validar_id(ident: str) -> str:
    if not _RE_ID.match(ident or ""):
        raise FlowStateError(
            f"Identificador inválido: {ident!r}. Use letras, números, ponto, "
            "hífen ou sublinhado — sem barra, espaço ou `..`, porque o "
            "identificador vira nome de arquivo."
        )
    return ident


def activity_path(agents: Path, ident: str) -> Path:
    return atividades_dir(agents) / f"{validar_id(ident)}.md"


def _git(args: list[str], cwd: Path) -> str:
    """Run git in the project, never in whatever directory the caller is in.

    A skill's natural working directory is inside `.agents`, which is its own
    repository. Asking git there reports the backup repo's branch — which is
    not the branch the activity is being built on.
    """
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def contexto_git(agents: Path) -> dict[str, str]:
    """Branch and worktree the activity is actually being built on.

    Read from the caller's directory, not from the project root: a skill run
    inside a worktree builds on THAT worktree's branch, and recording the main
    one describes a place the work never touched.

    The exception is `.agents` itself, an independent repository holding the
    backup history — from inside it git describes that repo, so fall back to
    the project root.

    Branch and worktree are read and dropped together: half a location
    describes a place that never existed.
    """
    raiz = raiz_de_trabalho(agents)
    branch = nome_do_ponto(raiz)
    worktree = _git(["rev-parse", "--show-toplevel"], raiz)
    return {"branch": branch, "worktree": worktree} if branch and worktree else {}


def nome_do_ponto(raiz: Path) -> str:
    """O nome do lugar onde o trabalho está — que nem sempre é uma branch local.

    `rev-parse --abbrev-ref HEAD` devolve a string literal `HEAD` quando a
    árvore está **detached**, e `branch: HEAD` não descreve lugar nenhum: dois
    commits diferentes gravariam o mesmo texto.

    A trilha `revisao` tornou isso o caso NORMAL, não a exceção: ela abre
    worktree no commit do dev, que é detached por desenho. Em 11/09/2026 a
    primeira revisão real gravou `branch: HEAD` e precisou de `corrigir
    --forcar` para se recuperar.

    Três degraus, do mais informativo ao menos:

    1. a branch local, quando há uma;
    2. a referência **remota** que aponta para este commit — `origin/feat/...`,
       que é exatamente o que a worktree de revisão tem;
    3. o commit curto. Feio, e ainda assim melhor que `HEAD`: ele identifica.
    """
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], raiz)
    if branch and branch != "HEAD":
        return branch

    # O nome COMPLETO vem junto de propósito: `refs/remotes/origin/HEAD`
    # encurta para `origin`, e filtrar pelo nome curto deixaria passar o
    # ponteiro simbólico do remoto como se fosse um lugar — foi o que a
    # primeira versão desta função fez, devolvendo `origin` em vez de
    # `origin/feat/...`.
    remotas = _git(["for-each-ref", "--points-at", "HEAD",
                    "--format=%(refname)\t%(refname:short)",
                    "refs/remotes/"], raiz)
    for linha in remotas.splitlines():
        completo, _, curto = linha.partition("\t")
        if curto.strip() and not completo.strip().endswith("/HEAD"):
            return curto.strip()

    curto = _git(["rev-parse", "--short", "HEAD"], raiz)
    return f"detached:{curto}" if curto else ""


def conciliar_local(atividade: "Atividade", agents: Path) -> tuple[dict, str]:
    """Onde a atividade É construída, contra onde QUEM CHAMOU está.

    O `avancar` gravava `contexto_git()` por cima, incondicionalmente. A
    intenção era boa — uma atividade pode legitimamente mudar de branch no meio
    do fluxo, e o estado precisa acompanhar. O defeito é que o comando **não
    distingue** "a atividade mudou de lugar" de "quem chamou estava em outro
    lugar", e as duas coisas chegam aqui idênticas.

    Aconteceu em 08/09/2026: um `avancar` rodado da raiz do repositório, que
    naquele momento estava na branch de OUTRA atividade, retargetou a atividade
    inteira — branch e worktree — sem imprimir nada. O step seguinte lê esses
    dois campos para saber onde trabalhar: sem alguém conferir o `status` antes,
    a implementação sairia na branch de outra pessoa.

    Preservar calado seria o defeito oposto e igualmente silencioso: atividade
    que mudou de branch de verdade apontaria para sempre para o lugar antigo.
    Então a regra é **preservar e gritar** — o valor gravado fica, e a
    divergência vira aviso com o comando de mudar de propósito.

    Devolve `(campos, aviso)`: os campos a gravar (vazio quando não há o que
    mudar) e o aviso (vazio quando não há divergência).
    """
    local = contexto_git(agents)
    if not local:
        return {}, ""

    gravado = {k: atividade.meta.get(k, "") for k in ("branch", "worktree")}
    # `PENDENTE` e vazio são a mesma coisa para conciliar: NÃO HÁ LUGAR
    # GRAVADO. É aqui que a lacuna que o `iniciar` declara se fecha sozinha —
    # o step 1 cria a árvore, o `avancar` seguinte roda de dentro dela, e o
    # campo passa a descrever onde o trabalho acontece de verdade.
    em_aberto = {k: (not v or v == LUGAR_PENDENTE) for k, v in gravado.items()}
    if all(em_aberto.values()):
        return local, ""

    # Um campo declarado e outro em aberto: só adota o que está em aberto, e
    # SÓ se o declarado bater. Divergindo, quem chamou está em outro lugar —
    # e adotar a árvore de quem chamou é exatamente o defeito que este
    # conciliador existe para impedir.
    if any(em_aberto.values()):
        firmes = [k for k, aberto in em_aberto.items() if not aberto]
        if all(gravado[k] == local[k] for k in firmes):
            return {k: local[k] for k, aberto in em_aberto.items() if aberto}, ""

    if gravado == local:
        return {}, ""

    # "NADA foi alterado" era verdade sobre os CAMPOS e mentira sobre o STEP,
    # que já tinha sido gravado quando esta mensagem aparece. Em 15/09/2026 o
    # `acme-app-aa` leu isto como recusa, foi para a worktree e
    # rodou de novo: as duas rodadas avançaram, o step 9 inteiro não aconteceu,
    # e o estado dizia "portão humano". Onze segundos entre uma linha e outra.
    linhas = [
        "O STEP FOI AVANÇADO — isto é aviso, não recusa.",
        "O que NÃO mudou foi o LUGAR: a atividade é construída em outro.",
        f"    gravado na atividade   branch {gravado['branch'] or '(vazio)'}",
        f"                           worktree {gravado['worktree'] or '(vazio)'}",
        *(["    (PENDENTE é a atividade dizendo que o lugar dela ainda não "
           "existe;",
           "     o campo que já está declarado é que não bate com o seu.)"]
          if LUGAR_PENDENTE in gravado.values() else []),
        f"    de onde você chamou    branch {local['branch']}",
        f"                           worktree {local['worktree']}",
        "",
        "  O step seguinte lê os campos GRAVADOS para saber onde trabalhar.",
        "  NÃO rode o `avancar` de novo de outro diretório: ele avança outra vez,",
        "  e o step que você acabou de deixar não terá acontecido.",
        "  Se você quis mesmo mudar o lugar da atividade, diga por comando:",
        f"    flow_state.py corrigir {atividade.meta.get('id', '<id>')} "
        f"--branch {local['branch']} --worktree {local['worktree']}",
    ]
    return {}, "\n".join(linhas)


# Um step de agente que durou segundos não aconteceu. O limiar é generoso de
# propósito: ele não existe para medir produtividade, e sim para pegar o caso
# em que o comando rodou duas vezes e ninguém trabalhou no meio.
#
# `[fluxo] segundos_de_step_relampago = 0` desliga, e há um uso legítimo: quem
# roteiriza o fluxo de ponta a ponta — a suíte deste pacote é o primeiro
# exemplo — atravessa os steps em milissegundos de propósito. Desligar é
# decisão do projeto, como toda a configuração; o que o pacote não faz é
# desligar sozinho.
SEGUNDOS_DE_STEP_RELAMPAGO = 120


def segundos_de_step_relampago(agents: Path) -> int:
    """O limiar declarado pelo projeto, ou o padrão. Nunca levanta."""
    try:
        import config as C  # tardio: config.py importa deste módulo
        valor = C.obter("fluxo.segundos_de_step_relampago",
                        SEGUNDOS_DE_STEP_RELAMPAGO, agents)
        return max(0, int(valor))
    except Exception:
        return SEGUNDOS_DE_STEP_RELAMPAGO


def guarda_step_relampago(atividade: "Atividade", destino: int,
                          limiar: int = SEGUNDOS_DE_STEP_RELAMPAGO) -> str:
    """Um portão humano está prestes a receber trabalho que não aconteceu?

    Medido em 15/09/2026, na `acme-app-aa`: um `avancar` rodado
    da árvore principal imprimiu o aviso de lugar, foi lido como recusa, e a
    segunda tentativa avançou de novo. **Step 9 às 14:41:15, step 10 às
    14:41:26** — onze segundos, duas linhas no histórico, uma intenção. A
    revisão em seis frentes nunca rodou, e a entrega chegou ao portão humano
    declarada revisada.

    **Só na entrada de portão humano.** O dano do caso acima não foi o step
    rápido: foi o portão 10 receber uma entrega declarada revisada. Guardar
    toda passagem transformaria o comando numa catraca que se aprende a
    `--forcar` por reflexo — e guarda que se atravessa por hábito não guarda.
    Aqui ela aparece três vezes na trilha inteira, nos três portões.

    **Sair de portão humano não conta.** Uma pessoa responde `sim` em vinte
    segundos, e isso é o portão funcionando. Só step de skill entra aqui.

    **O step 1 também não conta**, e a razão não é o relógio: o `iniciar` é a
    ÚLTIMA coisa que o step 1 faz — ele lê o card, decide a trilha e só então
    grava. O carimbo mede o fim do trabalho, não o começo, e avançar logo
    depois é o caminho normal.

    Devolve o motivo quando deve segurar, e `""` quando não há nada a dizer.
    """
    passo = atividade.step
    if STEPS.get(destino, {}).get("tipo") != "humano":
        return ""
    if passo == 1 or STEPS.get(passo, {}).get("tipo") != "skill":
        return ""
    if not atividade.history:
        return ""
    quando, rotulo_ultimo, _ = (list(atividade.history[-1]) + ["", "", ""])[:3]
    # Só vale quando a última linha do histórico É a entrada neste step: se a
    # atividade registrou qualquer outra coisa depois, alguém trabalhou.
    if rotulo_ultimo != rotulo(passo):
        return ""
    try:
        entrou = datetime.strptime(quando, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ""
    if limiar <= 0:
        return ""
    segundos = (datetime.now() - entrou).total_seconds()
    if segundos < 0 or segundos >= limiar:
        return ""
    return (
        f"{rotulo(destino)} está prestes a receber o trabalho de "
        f"{rotulo(passo)},\n"
        f"  que foi aberto há {int(segundos)}s e não registrou nada.\n\n"
        "  Um step de agente não termina nesse tempo. O caso conhecido é o "
        "`avancar` rodado\n"
        "  duas vezes, uma de cada diretório, com o aviso de lugar lido como "
        "recusa — em\n"
        "  15/09/2026 isso levou uma entrega ao portão 10 declarada revisada, "
        "com a revisão\n"
        "  em seis frentes nunca tendo acontecido. O step pulado não deixa "
        "buraco visível:\n"
        "  o estado diz que ele aconteceu.\n\n"
        "  Se ele aconteceu mesmo, `--forcar --nota '<o que foi feito>'` "
        "encerra a dúvida\n  e deixa escrito para quem abrir o portão."
    )


def id_da_outra_metade(ident: str, escopo: str) -> str:
    """O id da metade oposta, quando o id segue a convenção. `""` quando não.

    `1081-backend` e `1081-frontend` são duas atividades do MESMO card, com
    branches e PRs separados — decisão de 15/09/2026. O sufixo é o que permite
    achar uma a partir da outra sem tabela nova e sem adivinhar por título.
    """
    meu = SUFIXO_DE_ESCOPO.get(escopo, "")
    outro = SUFIXO_DE_ESCOPO.get(OUTRA_CAMADA.get(escopo, ""), "")
    if not meu or not outro or not ident.endswith(meu):
        return ""
    return ident[: -len(meu)] + outro


def guarda_da_metade_anterior(agents: Path, ident: str,
                              trilha: str) -> tuple[str, str]:
    """A `frontend` só abre depois de a `backend` do mesmo card ter fechado.

    Regra do Ederson, 15/09/2026, e ela não é preferência de processo: a
    `frontend` é a metade que valida a ENTREGA INTEIRA. Abrir antes de o
    backend existir faz a última conferência do card rodar contra meio produto,
    e não sobra ninguém depois dela.

    Devolve `(erro, aviso)`. O erro recusa; o aviso deixa passar falando.
    """
    anterior_esperada = PRECISA_DA_ANTERIOR.get(trilha)
    if not anterior_esperada:
        return "", ""
    irma = id_da_outra_metade(ident, trilha)
    sufixo = SUFIXO_DE_ESCOPO[trilha]
    sufixo_anterior = SUFIXO_DE_ESCOPO[anterior_esperada]
    if not irma:
        return "", (
            f"ID FORA DA CONVENÇÃO: `{ident}` não termina em `{sufixo}`, "
            "então não dá para\n  achar a metade de "
            f"`{anterior_esperada}` a partir dele — nem daqui, nem por quem "
            "for ler\n  o card depois. O par é "
            f"`<card>{sufixo_anterior}` e `<card>{sufixo}`."
        )
    # O porquê de cada par é diferente, e a mensagem tem de dizer o certo: a
    # `frontend` recusa porque valida a entrega inteira; a `construcao` recusa
    # porque sem a especificação ela vira uma `curta` — três frentes no step 9
    # em vez de seis, e nenhuma respondendo "é isto que foi pedido?".
    PORQUE = {
        "frontend": ("Esta é a metade que valida a entrega inteira: aberta "
                     "antes do backend existir,\n  ela confere meio produto e "
                     "não sobra ninguém para conferir o resto."),
        "construcao": ("Sem a especificação, esta trilha degrada em silêncio "
                       "para uma `curta`: o step 9\n  roda três das seis "
                       "frentes, e as duas que faltam são as únicas que "
                       "respondem\n  \"é isto que foi pedido?\"."),
    }[trilha]
    caminho = activity_path(agents, irma)
    if not caminho.exists():
        aceitas = ANTERIORES_ACEITAS.get(trilha, (anterior_esperada,))
        nomes = " ou ".join(f"`{a}`" for a in aceitas)
        return (
            f"A trilha `{trilha}` roda DEPOIS de {nomes}, e não "
            f"achei {irma}.\n  {PORQUE}\n\n"
            "  Se a especificação deste card foi feita fora do "
            "fluxo, `--forcar --nota '<onde>'`\n"
            "  abre assim mesmo e deixa escrito."
        ), ""
    try:
        anterior = Atividade.ler(caminho)
    except FlowStateError:
        return "", f"{irma} existe e não deu para ler. Confira antes de seguir."
    if anterior.meta.get("status") != STATUS_CONCLUIDO:
        ainda = ("a metade de trás ainda está mudando"
                 if trilha == "frontend"
                 else "a especificação ainda não passou pelo portão 5, e "
                      "construir contra spec\n  não aprovada é construir contra "
                      "proposta")
        return (
            f"{irma} existe e NÃO está concluída — está em "
            f"{anterior.meta.get('step_nome') or anterior.meta.get('step', '?')}.\n"
            f"  {ainda}.\n\n"
            "  `--forcar --nota` abre assim mesmo, e a nota é o que o portão 10 "
            "vai achar."
        ), ""
    return "", ""


def agora() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Mutual exclusion
# --------------------------------------------------------------------------


@contextmanager
def trava(agents: Path):
    """Serialise every mutation across processes.

    One global lock rather than one per activity: the index is rebuilt from all
    activities on every write, so any two mutations conflict through it anyway.
    The operations are short and few, so the contention costs nothing.

    **No Windows isto era um `yield` e mais nada.** O comentário dizia *"no
    flock. Documented in README"* — e o README nunca falou de Windows. Duas
    ausências empilhadas: a trava não existia, e o aviso que a declararia
    também não. Quem instalasse o pacote lá tinha a garantia inteira do
    `trava` — *"nenhuma escrita foi perdida"* — sem nada a sustentando.

    Medido em 22/09/2026, numa instalação Windows: seis processos avançando a
    mesma atividade, e a suíte reprovando exatamente onde a trava deveria
    aparecer. O teste estava certo; a ferramenta é que não tinha o mecanismo.

    `msvcrt.locking` é o equivalente de lá, e a diferença de forma é que ele
    **não espera**: trava ou falha. Por isso o laço, e por isso o prazo — e o
    prazo **estoura em erro**, nunca em seguir sem a trava. Seguir sem ela é o
    que produzia perda de escrita com os dois processos reportando sucesso.
    """
    agents.mkdir(parents=True, exist_ok=True)
    with open(agents / LOCK_NAME, "a+b") as fh:
        _travar(fh)
        try:
            yield
        finally:
            _destravar(fh)


# Quanto tempo esperar pela trava antes de desistir. Generoso: as operações
# que ela protege são curtas, então só chega aqui quem esbarrou em processo
# pendurado — e aí a resposta certa é dizer, não passar por cima.
SEGUNDOS_ESPERANDO_A_TRAVA = 30.0
_JA_AVISEI_SEM_TRAVA = False


def _travar(fh) -> None:
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_EX)
        return
    if msvcrt is not None:
        limite = time.monotonic() + SEGUNDOS_ESPERANDO_A_TRAVA
        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= limite:
                    raise FlowStateError(
                        "não consegui a trava do estado em "
                        f"{SEGUNDOS_ESPERANDO_A_TRAVA:.0f}s.\n"
                        "  Outro processo do fluxo está escrevendo, ou ficou "
                        "pendurado segurando\n"
                        f"  {fh.name}.\n"
                        "  RECUSO seguir sem a trava: duas escritas ao mesmo "
                        "tempo se sobrescrevem,\n"
                        "  e as duas reportam sucesso. Feche o outro processo "
                        "e rode de novo."
                    ) from None
                time.sleep(0.05)
    _avisar_sem_trava()


def _destravar(fh) -> None:
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_UN)
    elif msvcrt is not None:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass  # já solta ao fechar o arquivo; não há o que consertar aqui


def _avisar_sem_trava() -> None:
    """Plataforma sem primitiva de trava: a lacuna FALA, uma vez por processo.

    Recusar bloquearia o pacote inteiro numa plataforma exótica, o que é pior
    que o risco. Calar é o que estava escrito antes, e foi o que produziu o
    defeito. Então declara — que é o único dos três que não mente.
    """
    global _JA_AVISEI_SEM_TRAVA
    if _JA_AVISEI_SEM_TRAVA:
        return
    _JA_AVISEI_SEM_TRAVA = True
    print("  [SEM TRAVA] esta plataforma não tem `fcntl` nem `msvcrt`, e o "
          "estado está\n"
          "  desprotegido: dois processos escrevendo ao mesmo tempo se "
          "sobrescrevem,\n"
          "  e os dois reportam sucesso. Rode um de cada vez.",
          file=sys.stderr)


# --------------------------------------------------------------------------
# Text safety
# --------------------------------------------------------------------------


def uma_linha(texto: str) -> str:
    """Collapse every line separator so a value cannot break its container."""
    return _RE_QUEBRA.sub(" ", texto or "").strip()


def escapar_celula(texto: str) -> str:
    """Keep a pipe in a note from breaking the Markdown table it lands in.

    The inverse is `desescapar_celula`; `dividir_celulas` knows not to split on
    the escaped form. Backslash is escaped first so the round trip is faithful.
    """
    return (uma_linha(texto).replace("\\", "\\\\").replace("|", "\\|"))


def desescapar_celula(texto: str) -> str:
    out, i = [], 0
    while i < len(texto):
        if texto[i] == "\\" and i + 1 < len(texto):
            out.append(texto[i + 1])
            i += 2
        else:
            out.append(texto[i])
            i += 1
    return "".join(out).strip()


def dividir_celulas(linha: str) -> list[str]:
    """Split a Markdown table row on its unescaped pipes."""
    celulas, atual, i = [], [], 0
    interior = linha.strip()
    if interior.startswith("|"):
        interior = interior[1:]
    if interior.endswith("|") and not interior.endswith("\\|"):
        interior = interior[:-1]
    while i < len(interior):
        if interior[i] == "\\" and i + 1 < len(interior):
            atual.append(interior[i:i + 2])
            i += 2
        elif interior[i] == "|":
            celulas.append("".join(atual))
            atual = []
            i += 1
        else:
            atual.append(interior[i])
            i += 1
    celulas.append("".join(atual))
    return [c.strip() for c in celulas]


def escrever_atomico(path: Path, conteudo: str) -> None:
    """Write through a temporary file so a reader never sees a half state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(conteudo)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)  # never leave a stray .tmp behind


# --------------------------------------------------------------------------
# Activity file
# --------------------------------------------------------------------------
#
# Markdown with a flat `chave: valor` front matter. Flat on purpose: it keeps
# the parser short and the file readable by a human who opens it with no
# tooling at all.


class Atividade:
    def __init__(self, meta: dict[str, str],
                 history: list[tuple[str, ...]],
                 artefatos: list[tuple[str, ...]],
                 conferencias: list[tuple[str, ...]] | None = None) -> None:
        self.meta = meta
        self.history = history
        self.artefatos = artefatos
        # A terceira tabela existe porque uma obrigação escrita em prosa não
        # acontece. A instrução "entrar com ator sem a permissão" viveu meses na
        # frente de execução e nunca aconteceu uma vez — ninguém registrava, e
        # portanto ninguém sabia. Aqui a conferência mecânica deixa rastro, e o
        # `concluir` lê o rastro.
        self.conferencias = conferencias or []

    # -- parsing ----------------------------------------------------------

    @classmethod
    def ler(cls, path: Path) -> "Atividade":
        if not path.exists():
            raise FlowStateError(
                f"Atividade não encontrada em {path}. Rode `iniciar` antes."
            )
        texto = path.read_text(encoding="utf-8")
        meta, corpo = cls._split_front_matter(texto, path)
        atividade = cls(
            meta,
            cls._parse_tabela(corpo, "Histórico", ["Quando", "Step", "Nota"]),
            cls._parse_tabela(corpo, "Artefatos", ["Tipo", "Caminho"]),
            cls._parse_tabela(corpo, "Conferências",
                              ["Quando", "Ferramenta", "Veredicto", "Detalhe"]),
        )
        atividade.validar(path)
        return atividade

    def validar(self, path: Path) -> None:
        """Refuse a file whose fields cannot be trusted, with the reason.

        A hand-edited or truncated file must fail here, naming itself, rather
        than surfacing as a KeyError three frames away — and never while a
        listing is walking every other activity.
        """
        for chave in ("id", "step", "trilha", "status"):
            if not self.meta.get(chave):
                raise FlowStateError(f"{path.name}: falta `{chave}` no front matter.")
        if self.meta["trilha"] not in TRILHAS:
            raise FlowStateError(
                f"{path.name}: trilha desconhecida {self.meta['trilha']!r}."
            )
        try:
            step = int(self.meta["step"])
        except ValueError:
            raise FlowStateError(
                f"{path.name}: `step` não é um número ({self.meta['step']!r})."
            ) from None
        if step not in STEPS:
            raise FlowStateError(f"{path.name}: step {step} não existe no fluxo.")

    @staticmethod
    def _split_front_matter(texto: str, path: Path) -> tuple[dict[str, str], str]:
        if not texto.startswith("---\n"):
            raise FlowStateError(f"{path.name}: sem front matter.")
        fim = texto.find("\n---\n", 4)
        if fim == -1:
            raise FlowStateError(f"{path.name}: front matter não fechado.")
        meta: dict[str, str] = {}
        for linha in texto[4:fim].splitlines():
            if not linha.strip() or ":" not in linha:
                continue
            chave, _, valor = linha.partition(":")
            meta[chave.strip()] = valor.strip()
        return meta, texto[fim + 5:]

    @staticmethod
    def _parse_tabela(corpo: str, titulo: str,
                      cabecalho: list[str]) -> list[tuple[str, ...]]:
        """Read back a Markdown table written by `_render_tabela`.

        Splits on unescaped pipes only. A note containing `|` is stored as
        `\\|`; splitting on it naively yields the wrong column count and the
        row would be dropped without a trace.
        """
        linhas = corpo.splitlines()
        try:
            inicio = next(i for i, l in enumerate(linhas)
                          if l.strip().lower() == f"## {titulo}".lower())
        except StopIteration:
            return []
        registros: list[tuple[str, ...]] = []
        for linha in linhas[inicio + 1:]:
            s = linha.strip()
            if s.startswith("## "):
                break
            if not s.startswith("|"):
                continue
            # Structure is decided on the raw text, before unescaping: the
            # escape in `_render_tabela` is exactly what distinguishes a data
            # row reading `---` from the separator, and unescaping first would
            # throw that mark away and drop the row.
            cruas = dividir_celulas(s)
            if len(cruas) != len(cabecalho):
                continue
            if set("".join(cruas)) <= {"-", " ", ":"}:  # separator row
                continue
            if cruas == cabecalho:
                continue
            registros.append(tuple(desescapar_celula(c) for c in cruas))
        return registros

    # -- rendering --------------------------------------------------------

    def escrever(self, path: Path) -> None:
        # A sessão se registra AQUI, e não em cada comando, porque aqui é o
        # único lugar por onde toda escrita de estado passa. Sete chamadas
        # espalhadas seriam sete lugares de esquecer — e a razão de este campo
        # existir é exatamente que inferência falha e registro não.
        self._anotar_sessao(path)
        titulo = uma_linha(self.meta.get("titulo", ""))
        blocos = [
            self._render_front_matter(),
            f"# {self.meta['id']}" + (f" — {titulo}" if titulo else ""),
            "",
            "## Histórico",
            "",
            self._render_tabela(["Quando", "Step", "Nota"], self.history),
            "",
            "## Artefatos",
            "",
            self._render_tabela(["Tipo", "Caminho"], self.artefatos)
            if self.artefatos else "_Nenhum artefato registrado._",
            "",
            "## Conferências",
            "",
            self._render_tabela(["Quando", "Ferramenta", "Veredicto", "Detalhe"],
                                self.conferencias)
            if self.conferencias else "_Nenhuma conferência registrada._",
            "",
        ]
        escrever_atomico(path, "\n".join(blocos))

    def _anotar_sessao(self, path: Path) -> None:
        """Acrescenta a sessão corrente à lista da atividade.

        **Por que isto existe.** Até 11/09/2026 a métrica atribuía trabalho a
        uma atividade por duas provas: a branch do repositório principal e o
        `cwd`. As duas são inferência sobre onde a sessão estava, e as duas
        erraram no mesmo caso medido — uma revisão inteira, 1.708 registros,
        teve o custo somado à atividade **vizinha**, porque o checkout
        principal por acaso estava na branch dela. O zero da revisão a
        ferramenta declarava; a contaminação da vizinha ela **afirmava**, com
        `atribuicao: ok`.

        O id da sessão bate com o nome do arquivo de transcrito, exato. Guardá-
        lo aqui troca heurística por registro: a atividade passa a dizer quem
        trabalhou nela, em vez de a métrica adivinhar.

        É LISTA e só cresce: uma atividade legitimamente atravessa várias
        sessões, e o erro possível do `.sessao-atual` — duas sessões no mesmo
        projeto ao mesmo tempo — acrescenta uma entrada em vez de trocar a
        dona.
        """
        try:
            agents = path.parent.parent
            sessao = (agents / ".sessao-atual").read_text(
                encoding="utf-8").strip()[:64]
        except OSError:
            return
        if not sessao or "/" in sessao or " " in sessao:
            return
        atuais = [s for s in str(self.meta.get("sessoes") or "").split() if s]
        if sessao not in atuais:
            self.meta["sessoes"] = " ".join([*atuais, sessao])

    def _render_front_matter(self) -> str:
        ordem = ["id", "titulo", "complementares", "corrige", "trilha", "risco",
                 "superficies", "step", "step_nome", "status",
                 "steps_desligados", "branch", "worktree", "sessoes",
                 "contexto_do_8",
                 "criado_em", "atualizado_em", "concluido_em"]
        vistas = set()
        linhas = ["---"]
        for chave in [*ordem, *self.meta]:
            if chave in vistas or chave not in self.meta:
                continue
            vistas.add(chave)
            # Values are flattened: a title carrying a newline — or a literal
            # `---` — would otherwise close the front matter early and take
            # trilha, step and status with it.
            linhas.append(f"{chave}: {uma_linha(str(self.meta[chave]))}")
        linhas += ["---", ""]
        return "\n".join(linhas)

    @staticmethod
    def _render_tabela(cabecalho: list[str],
                       linhas: list[tuple[str, ...]]) -> str:
        out = ["| " + " | ".join(cabecalho) + " |",
               "| " + " | ".join("---" for _ in cabecalho) + " |"]
        for linha in linhas:
            celulas = [escapar_celula(c) for c in linha]
            # A data row that renders exactly like the separator row, or like
            # the header, is skipped on re-read and the entry vanishes. Escape
            # one character: the text is identical after unescaping, and the
            # row is no longer mistaken for structure.
            parece_separador = (any(celulas)
                                and set("".join(celulas)) <= {"-", " ", ":"})
            parece_cabecalho = [desescapar_celula(c) for c in celulas] == cabecalho
            if parece_separador or parece_cabecalho:
                primeira = next((i for i, c in enumerate(celulas) if c), None)
                if primeira is not None:
                    celulas[primeira] = "\\" + celulas[primeira]
            out.append("| " + " | ".join(celulas) + " |")
        return "\n".join(out)

    # -- flow -------------------------------------------------------------

    @property
    def trilha(self) -> list[int]:
        """Os steps da trilha, filtrados pelo que o projeto declarou usar.

        A trilha gravada na atividade não muda quando o projeto muda de
        política: o que muda é o caminho efetivo, e o que ficou de fora está
        registrado em `steps_desligados` no front matter.
        """
        declarada = TRILHAS[self.meta["trilha"]]
        desligados = {int(n) for n in
                      (self.meta.get("steps_desligados") or "").replace(",", " ").split()
                      if n.isdigit()}
        efetiva = [s for s in declarada if s not in desligados]
        return efetiva or declarada

    @property
    def step(self) -> int:
        return int(self.meta["step"])

    def proximo_step(self) -> int | None:
        seguintes = [s for s in self.trilha if s > self.step]
        return seguintes[0] if seguintes else None


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_caminho(args: argparse.Namespace) -> int:
    print(resolve_agents_dir())
    return 0


def cmd_fluxo(args: argparse.Namespace) -> int:
    try:
        assets = set(steps_assets())
    except FlowStateError:
        assets = set(STEPS)
    print("Steps do fluxo:\n")
    for numero, dados in STEPS.items():
        if numero not in assets and not getattr(args, "todos", False):
            continue
        marca = "HUMANO" if dados["tipo"] == "humano" else "skill "
        estado = "" if numero in assets else "   [DESLIGADO NO PROJETO]"
        endereco = "" if dados["tipo"] == "humano" else f"  ({dados['nome']})"
        print(f"  {numero:>2}  [{marca}]  {dados['cargo']}{endereco}{estado}")
    print("\nTrilhas:\n")
    for nome, steps in TRILHAS.items():
        efetiva = [s for s in steps if s in assets]
        print(f"  {nome:<9} {' → '.join(str(s) for s in efetiva)}")
    print("\nRisco (`--risco alto|padrao|baixo`), e onde olhar para propor:\n")
    for nome, onde in SUPERFICIES_DE_RISCO.items():
        print(f"  {nome:<16} {onde}")
    print("\n  alto: recusa trilha que implementa sem step 9; a frente de "
          "segurança fica\n        exigida no 9; `sast`, se declarado, não sai "
          "por `nao-coberta`.\n  baixo: não corta nada.")
    for aviso in avisar_desligados():
        print(f"\n  {aviso}")
    return 0


def cmd_iniciar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    ident = validar_id(args.id)
    if args.trilha not in TRILHAS:
        raise FlowStateError(
            f"Trilha inválida: {args.trilha}. Use uma de: {', '.join(TRILHAS)}."
        )
    risco = getattr(args, "risco", "") or ""
    superficies = ler_superficies(getattr(args, "superficies", "") or "")
    if superficies and not risco:
        raise FlowStateError(
            "--superficies sem --risco: a lista diz onde olhar, e o risco é a "
            "conclusão que a pessoa confirmou. Passe os dois.")
    avisos_risco = conferir_risco(risco, superficies, args.trilha) if risco else []

    # O bug que escapou, ligado à entrega de onde escapou. Sem o vínculo, o
    # custo de um erro de análise aparece semanas depois num card que ninguém
    # liga à atividade que o causou — e a métrica conta a atividade de
    # origem como limpa.
    corrige = validar_id(args.corrige) if getattr(args, "corrige", "") else ""
    if corrige == ident:
        raise FlowStateError(
            f"{ident} não pode corrigir a si mesma. Para voltar a mexer na "
            "mesma atividade, use --reabrir.")
    aviso_corrige = ""
    if corrige:
        origem_path = activity_path(agents, corrige)
        if not origem_path.exists():
            aviso_corrige = (
                f"ORIGEM NÃO ACHADA: {corrige} não existe em "
                f"{atividades_dir(agents)}.\n            O vínculo fica "
                "gravado, mas a métrica só o conta se a origem for deste "
                "projeto.")
        else:
            try:
                origem = Atividade.ler(origem_path)
            except FlowStateError:
                origem = None
            if origem and origem.meta.get("status") != STATUS_CONCLUIDO:
                aviso_corrige = (
                    f"A ORIGEM AINDA ESTÁ ABERTA: {corrige} está em "
                    f"{rotulo(origem.step)}.\n            Defeito achado antes "
                    "da entrega é volta de correção dela, não bug que "
                    "escapou.\n            Se for isso, devolva a própria "
                    f"{corrige} ao step 8 em vez de abrir outra.")

    erro_metade, aviso_metade = guarda_da_metade_anterior(
        agents, ident, args.trilha)
    if erro_metade and not getattr(args, "forcar", False):
        raise FlowStateError(erro_metade)
    if erro_metade and not args.nota:
        raise FlowStateError(
            "--forcar exige --nota aqui: abrir a `frontend` sem a metade de "
            "trás é a exceção, e o portão 10 precisa achar escrito por quê."
        )

    with trava(agents):
        path = activity_path(agents, ident)
        anterior = None
        if path.exists():
            if not args.reabrir:
                raise FlowStateError(
                    f"A atividade {ident} já existe em {path}. Use `status` "
                    "para vê-la, ou --reabrir para reabrir o fluxo."
                )
            try:
                anterior = Atividade.ler(path)
            except FlowStateError:
                anterior = None  # unreadable: start clean, say so below

        inicio = TRILHAS[args.trilha][0]
        agora_str = agora()
        meta = {
            "id": ident,
            "titulo": args.titulo,
            "trilha": args.trilha,
            "step": str(inicio),
            "step_nome": STEPS[inicio]["nome"],
            "status": STATUS_ABERTO,
            "steps_desligados": " ".join(str(n) for n in steps_desligados(agents)),
            "criado_em": (anterior.meta.get("criado_em", agora_str)
                          if anterior else agora_str),
            "atualizado_em": agora_str,
            # NÃO herda o lugar do cwd. Quem roda o `iniciar` está num lugar
            # que não é o da atividade — a árvore dela é criada pelo step 1,
            # depois desta linha. Ver `LUGAR_PENDENTE`.
            "branch": LUGAR_PENDENTE,
            "worktree": LUGAR_PENDENTE,
        }
        # Quem JÁ sabe o lugar declara. As duas bandeiras são independentes:
        # `PENDENTE` não é meia-verdade sobre um lugar, é a lacuna dita em voz
        # alta — por isso `--branch` sozinho continua valendo, diferente do
        # `corrigir`, onde os dois campos mudam juntos ou nenhum muda.
        if args.branch:
            meta["branch"] = uma_linha(args.branch)
        if getattr(args, "worktree", ""):
            meta["worktree"] = uma_linha(args.worktree)
        # Reabrir sem `--risco` herda o de antes: o risco é do card, não da
        # abertura.
        if risco:
            meta["risco"] = risco
            if superficies:
                meta["superficies"] = " ".join(superficies)
        elif anterior and anterior.meta.get("risco"):
            meta["risco"] = anterior.meta["risco"]
            conferir_risco(meta["risco"], [], args.trilha)
            if anterior.meta.get("superficies"):
                meta["superficies"] = anterior.meta["superficies"]

        # O escopo é DERIVADO da trilha, e não uma bandeira à parte. Bandeira
        # se esquece, e uma atividade de trilha `backend` sem escopo gravado
        # deixaria o step 8 decidir sozinho o que implementar — que é a decisão
        # que esta trilha existe para tirar dele. Ausente segue significando
        # "tudo", que é toda atividade anterior a 2.39.0.
        escopo = ESCOPO_DA_TRILHA.get(args.trilha, "")
        if escopo:
            meta["escopo"] = escopo
            outra = id_da_outra_metade(ident, escopo)
            if outra:
                meta["outra_metade"] = outra

        # Cards complementares. A atividade continua tendo UM dono — a branch, o
        # arquivo de estado e o nome saem do principal —, e os outros viajam
        # junto porque o PR fecha os três e a especificação é uma só.
        #
        # Guardados no front matter, e não numa tabela, porque são identidade da
        # atividade e não evento dela: quem abre o arquivo precisa ver na
        # primeira tela o que este trabalho fecha.
        if getattr(args, "complementares", None):
            outros = [validar_id(c) for c in args.complementares]
            repetidos = [c for c in outros if c == ident]
            if repetidos:
                raise FlowStateError(
                    f"{ident} é o card principal e não pode ser complementar "
                    "de si mesmo."
                )
            if len(set(outros)) != len(outros):
                raise FlowStateError("Há card complementar repetido na lista.")
            meta["complementares"] = " ".join(outros)

        # Reopening keeps the history. Losing the record of what already
        # happened is the one thing the state file exists to prevent.
        history = list(anterior.history) if anterior else []
        artefatos = list(anterior.artefatos) if anterior else []

        # HERANÇA DOS ARTEFATOS, e é o que separa a `construcao` de uma
        # `curta`. O dev abre uma atividade NOVA, dias depois, noutra sessão:
        # o handoff é por arquivo, e sem trazer os artefatos da especificação
        # para cá o step 8 implementaria sem spec e o step 9 rodaria três das
        # seis frentes — as duas ausentes sendo justamente as que respondem
        # "é isto que foi pedido?".
        #
        # Herdados como artefatos REGISTRADOS desta atividade, o step 6 desenha
        # contra eles e o step 9 os confere como se esta atividade os tivesse
        # produzido. Não é um step novo: o step 1 já é quem abre a atividade e
        # decide de onde ela parte.
        if PRECISA_DA_ANTERIOR.get(args.trilha) and not anterior:
            irma_id = id_da_outra_metade(ident, args.trilha)
            irma_path = activity_path(agents, irma_id) if irma_id else None
            if irma_path and irma_path.exists():
                try:
                    irma = Atividade.ler(irma_path)
                except FlowStateError:
                    irma = None
                if irma:
                    ja = {(tipo, caminho) for tipo, caminho, *_ in artefatos}
                    herdados = [a for a in irma.artefatos
                                if (a[0], a[1]) not in ja]
                    artefatos.extend(herdados)
                    meta["herdou_de"] = irma_id
                    if herdados:
                        print(f"  [fluxo] herdei {len(herdados)} artefato(s) de "
                              f"{irma_id}: "
                              + ", ".join(sorted({a[0] for a in herdados})))
                    else:
                        print(f"  [fluxo] {irma_id} está concluída e NÃO "
                              "registrou artefato nenhum.\n          Esta "
                              "trilha vai rodar sem especificação — confira "
                              "antes de seguir.")
        nota = args.nota or (
            f"Reaberta na trilha {args.trilha}." if anterior
            else f"Atividade aberta na trilha {args.trilha}.")
        # A reabertura se MARCA na própria linha, com ou sem nota de quem
        # reabre: é o que o `percurso` lê para não contar a volta ao step 1
        # como mais uma volta de correção.
        if anterior and not nota.startswith(MARCA_DE_REABERTURA):
            nota = f"{MARCA_DE_REABERTURA}: {nota}"
        history.append((agora_str, rotulo(inicio), nota))

        if risco:
            history.append((
                agora_str, rotulo(inicio),
                f"Risco {risco}, confirmado por quem abriu. Superfícies: "
                + (", ".join(superficies) or "nenhuma") + "."))

        if corrige:
            meta["corrige"] = corrige
            history.append((
                agora_str, rotulo(inicio),
                f"Corrige {corrige}: defeito que escapou da entrega dela."))

        if meta.get("complementares"):
            history.append((
                agora_str, rotulo(inicio),
                f"Card principal {ident}; complementares "
                f"{meta['complementares']}. O PR fecha os "
                f"{1 + len(meta['complementares'].split())}."))

        if desligados := steps_desligados(agents):
            history.append((agora_str, rotulo(inicio),
                              "Steps desligados no projeto: "
                              + " ".join(str(n) for n in desligados)))
        if fora := avisos_da_trilha(args.trilha):
            history.append((agora_str, rotulo(inicio),
                            f"TRILHA `{args.trilha}`: " + " ".join(fora)))
        Atividade(meta, history, artefatos).escrever(path)
        avisos = (regenerar_indice(agents) + avisar_desligados(agents)
              + avisos_da_trilha(args.trilha))
        if escopo and not meta.get("outra_metade"):
            avisos.append(
                f"ID FORA DA CONVENÇÃO: a trilha `{args.trilha}` entrega METADE "
                f"de um card, e o id `{ident}` não termina em "
                f"`{SUFIXO_DE_ESCOPO[escopo]}`.\n"
                "            As duas metades se acham uma à outra pelo sufixo — "
                "`<card>-backend` e\n            `<card>-frontend`. Sem ele, "
                "quem retomar o card daqui a três semanas não\n            "
                "tem como saber que existe outra metade."
            )
        if aviso_metade:
            avisos.append(aviso_metade)
        if aviso_corrige:
            avisos.append(aviso_corrige)
        avisos.extend(avisos_risco)
        if not meta.get("risco"):
            avisos.append(
                "RISCO NÃO DECLARADO: a atividade abre sem `--risco`, e conta "
                "como `padrao`.\n            O step 1 propõe a partir do "
                "checklist do `fluxo` e a pessoa confirma.")
        if erro_metade:
            avisos.append(
                "ABERTA POR EXCEÇÃO, com --forcar: " + erro_metade.splitlines()[0]
                + f"\n            A nota registrada: {uma_linha(args.nota)}"
            )

    print(f"Atividade {ident} {'reaberta' if anterior else 'aberta'} em {path}")
    print(f"  trilha: {args.trilha} "
          f"({' → '.join(str(s) for s in TRILHAS[args.trilha])})")
    if meta.get("risco"):
        print(f"  risco:  {meta['risco']}"
              + (f" ({meta['superficies']})" if meta.get("superficies") else ""))
    print(f"  step:   {rotulo(inicio)}")
    if STEPS[inicio]["tipo"] != "humano":
        print(f"  disparo: {disparo(inicio)}")
    if anterior:
        print(f"  histórico preservado: {len(history) - 1} entrada(s)")
    relatar(avisos)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    if not args.id:
        return cmd_listar(args)
    atividade = Atividade.ler(activity_path(agents, args.id))
    meta = atividade.meta
    print(f"{meta['id']} — {meta.get('titulo', '')}")
    if meta.get("complementares"):
        # Na primeira tela, e não enterrado: quem retoma a atividade precisa
        # saber que o PR fecha mais de um card antes de decidir qualquer coisa.
        print(f"  fecha também: {meta['complementares']}")
    if meta.get("corrige"):
        print(f"  corrige:  {meta['corrige']} — defeito que escapou da entrega dela")
    print(f"  status:   {meta.get('status')}")
    print(f"  trilha:   {meta.get('trilha')}")
    print(f"  risco:    {meta.get('risco') or 'não declarado (conta como padrao)'}"
          + (f" — {meta['superficies']}" if meta.get("superficies") else ""))
    if meta.get("escopo"):
        # Na primeira tela: o step 8 implementa SÓ isto, e quem lê a entrega
        # precisa saber o que está faltando de propósito.
        print(f"  escopo:   {meta['escopo']} — a outra camada é especificada "
              "e NÃO implementada")
    if meta.get("outra_metade"):
        print(f"  a outra metade: {meta['outra_metade']}")
    print(f"  step:     {rotulo(atividade.step)}")
    if atividade.step == 9:
        if mesmo := mesmo_contexto_do_8(atividade, agents, na_saida=False):
            print("\n  " + mesmo + "\n")
        # Na primeira tela do step 9, que é onde a skill dispara as frentes.
        vale, ignoradas = modelo_das_frentes(agents)
        for frente, modelo in vale.items():
            print(f"  modelo:   {frente} dispara com `model: \"{modelo}\"` "
                  "([revisao.modelo], perna sombra: adota)")
        for linha in ignoradas:
            print(f"  modelo:   [revisao.modelo] {linha}")
        if vale or ignoradas:
            print("            as frentes sem linha aqui seguem "
                  "references/model-policy.md")
    proximo = atividade.proximo_step()
    print(f"  próximo:  {rotulo_com_endereco(proximo) if proximo else '— fim da trilha —'}")
    if proximo and STEPS[proximo]["tipo"] != "humano":
        print(f"  disparo:  {disparo(proximo)}")
    for chave, label in (("branch", "branch  "), ("worktree", "worktree")):
        if meta.get(chave):
            print(f"  {label}: {meta[chave]}")
    if atividade.artefatos:
        print("  artefatos:")
        ausentes = 0
        for tipo, caminho in atividade.artefatos:
            # O ponteiro morto se DECLARA na leitura, e não se presume vivo.
            # Medido em 24/09/2026: uma spec renomeada durante a atividade
            # deixou três `sdd-sistema` registrados, um apontando para arquivo
            # que não existia mais — e quem lê a lista não tinha como saber
            # qual. As seis frentes do step 9 abrem estes caminhos.
            morto = artefato_ausente(agents, atividade, caminho)
            ausentes += morto
            print(f"    {tipo}: {caminho}" + ("   (AUSENTE)" if morto else ""))
        if ausentes:
            print()
            print(f"  {ausentes} caminho(s) marcado(s) AUSENTE: parecem arquivo "
                  "e não existem nem na raiz")
            print("  do projeto nem na worktree desta atividade. Se foi "
                  "renomeação, troque o registro:")
            print(f"      flow_state.py artefato {meta['id']} --tipo <tipo> "
                  "--substituir <antigo> --caminho <novo>")
            print("  Se o artefato deixou de existir, retire com --retirar e "
                  "--nota.")
    return 0


def cmd_avancar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()

    with trava(agents):
        # Read inside the lock: two worktrees that both read before either
        # writes would each overwrite the other's transition, and both would
        # report success.
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)

        if atividade.meta.get("status") == STATUS_CONCLUIDO and not args.forcar:
            raise FlowStateError(
                f"A atividade {args.id} está concluída. Use --forcar para "
                "reabrir o fluxo."
            )

        proximo = atividade.proximo_step()
        destino = args.step if args.step is not None else proximo
        if destino is None:
            # Esta mensagem só aparece quando `--step` NÃO veio e não há próximo
            # — ou seja, exatamente quando `--step` é a resposta. A primeira
            # versão dizia só "use `concluir`", que é o **oposto** de quem está
            # devolvendo por escopo: `concluir` é o aceite, e quem devolve está
            # recusando aceitar. Achado pela sessão `acme-app-10`
            # no portão 10, que insistiu; uma sessão menos teimosa teria
            # encerrado a atividade que o humano acabara de decidir não encerrar.
            raise FlowStateError(
                f"A atividade {args.id} já está no último step da trilha "
                f"{atividade.meta['trilha']}.\n"
                "  Para ENCERRAR: `concluir`.\n"
                "  Para DEVOLVER a um step anterior — a devolução por escopo do "
                "portão 10 —: `--step <n> --forcar --nota '<...>'`, e a nota "
                "precisa dizer que é por escopo, senão o step 9 conta como mais "
                "uma volta do laço em vez de reiniciar o contador."
            )
        if destino not in STEPS:
            raise FlowStateError(
                f"Step inexistente: {destino}. Use `fluxo` para ver a lista."
            )

        # A ajuda dizia "exige --forcar" desde que a bandeira nasceu, e o
        # código não conferia: a trilha mudava num `avancar` comum, sem nota,
        # e as checagens de baixo ainda olhavam a trilha ANTIGA.
        trilha_antes = atividade.meta["trilha"]
        trilha_nova = args.trilha if args.trilha and args.trilha != trilha_antes else ""
        if trilha_nova:
            if trilha_nova not in TRILHAS:
                raise FlowStateError(f"Trilha inválida: {trilha_nova}.")
            if not args.forcar:
                raise FlowStateError(
                    f"--trilha muda {args.id} de `{trilha_antes}` para "
                    f"`{trilha_nova}` no meio do fluxo: use --forcar e diga em "
                    "--nota por quê.")
            if atividade.meta.get("risco") == "alto":
                conferir_risco("alto", [], trilha_nova)

        if not args.forcar:
            if destino not in atividade.trilha:
                raise FlowStateError(
                    f"O step {destino} não faz parte da trilha "
                    f"{atividade.meta['trilha']} ({atividade.trilha}). "
                    "Use --forcar se a trilha mudou de propósito."
                )
            if destino <= atividade.step:
                raise FlowStateError(
                    f"A atividade já está no step {atividade.step}; {destino} "
                    "é um retrocesso. Use --forcar se for volta de correção."
                )
            # The gate. Jumping from 4 to 6 would step over the human review at
            # 5, which is the whole point of having it.
            if destino != proximo:
                pulados = [s for s in atividade.trilha
                           if atividade.step < s < destino]
                humanos = [s for s in pulados if STEPS[s]["tipo"] == "humano"]
                raise FlowStateError(
                    f"Ir do step {atividade.step} para o {destino} pula "
                    f"{', '.join(rotulo(s) for s in pulados)}."
                    + (" Há portão humano no caminho." if humanos else "")
                    + f" O próximo da trilha é {rotulo(proximo)}. "
                      "Use --forcar e explique em --nota se for deliberado."
                )
        elif not args.nota:
            raise FlowStateError(
                "--forcar exige --nota: sair da trilha sem registrar o motivo "
                "torna o histórico inútil justamente onde ele importa."
            )

        # ANTES de gravar o step. Recusa que chega depois da escrita é relato,
        # não guarda — foi exatamente assim que o aviso de lugar falhou.
        if not args.forcar:
            relampago = guarda_step_relampago(
                atividade, destino, segundos_de_step_relampago(agents))
            if relampago:
                raise FlowStateError(relampago)
            # Só na saída PARA FRENTE: voltar ao 8 para corrigir não aprova
            # nada, e essa volta já é `--step 8 --forcar`.
            if atividade.step == 9 and destino > 9:
                if mesmo := mesmo_contexto_do_8(atividade, agents):
                    raise FlowStateError(mesmo)

        # Do 8 para o 9 a trava vale MESMO com `--forcar`: a volta de correção
        # entra no 9 exatamente por `--step 9 --forcar`, e é a volta em que o
        # portão mais importa — ela mexeu no código que o step 9 vai reler.
        if atividade.step == 8 and destino == 9:
            faltas = falta_para_sair_do_8(atividade, agents)
            if faltas:
                raise FlowStateError(
                    f"O step 8 de {args.id} não fecha com o que a tabela "
                    "Conferências diz:\n    - " + "\n    - ".join(faltas)
                    + f"\n  Rode `flow_state gates {args.id}` — ele grava o "
                    "código de saída de cada portão.\n  Portão que não se aplica "
                    f"a esta entrega: `conferencia {args.id} --ferramenta "
                    "gate:<nome> --veredicto nao-coberta --detalhe '<por quê>'`."
                )

        # Orçamento: política declarada pelo PROJETO, lida de um JSON já
        # gravado — não coleta nada e não pode demorar. Quem forçou já decidiu,
        # e a nota dele registra o porquê.
        aviso_orcamento = "" if args.forcar else conferir_orcamento(agents, args.id)

        agora_str = agora()
        # A saída do portão, ANTES da linha da transição: quem lê a última
        # linha do Histórico (a guarda do relâmpago, a baseline do 9) continua
        # achando a transição lá.
        if atividade.step in STEPS_DE_PORTAO and destino != atividade.step:
            atividade.history.append((agora_str, "portão gravado", registrar_portao(
                agents, atividade, atividade.step,
                "aprovado" if destino > atividade.step else "devolvido", agora_str)))
        if atividade.step == 8 and destino == 9:
            # Quem roda este `avancar` é o contexto que fez o step 8. A volta
            # de correção troca o registro: o 8 da volta 2 pode ser outro.
            if contexto := contexto_atual(agents):
                atividade.meta["contexto_do_8"] = contexto
            else:
                atividade.meta.pop("contexto_do_8", None)
        atividade.meta["step"] = str(destino)
        atividade.meta["step_nome"] = STEPS[destino]["nome"]
        atividade.meta["atualizado_em"] = agora_str
        campos_local, aviso_local = conciliar_local(atividade, agents)
        atividade.meta.update(campos_local)
        nota = args.nota or ""
        if trilha_nova:
            atividade.meta["trilha"] = trilha_nova
            nota = f"Trilha: {trilha_antes} → {trilha_nova}. {nota}".strip()
        atividade.history.append((agora_str, rotulo(destino), nota))
        exigencias = []
        if e := EXIGENCIA_DO_STEP_9.get(atividade.meta.get("trilha", "")):
            exigencias.append(e)
        if atividade.meta.get("risco") == "alto":
            exigencias.append(CONFERENCIA_DO_RISCO_ALTO)
        aviso_exigencia = ""
        if destino == 9:
            for dimensao, porque in exigencias:
                atividade.conferencias.append(
                    (agora_str, dimensao, "exigida", porque))
                aviso_exigencia += (
                    ("\n\n  " if aviso_exigencia else "")
                    + f"CONFERÊNCIA EXIGIDA NESTE STEP: `{dimensao}` — {porque}.\n"
                    + ("            Ela segura o `concluir` até fechar, e "
                       "`nao-coberta` também segura;\n            baixar o risco "
                       "é `risco <id> --nivel padrao --nota`, e fica escrito."
                       if (dimensao, porque) == CONFERENCIA_DO_RISCO_ALTO else
                       "            Ela segura o `concluir` até fechar. `nao-coberta` "
                       "passa e fica escrita;\n            inventar `ok` apaga do "
                       "histórico a única prova que esta trilha produz.")
                )
            if (atividade.meta.get("risco") == "alto"
                    and GATE_DO_RISCO_ALTO not in dict(gates_declarados(agents))):
                aviso_exigencia += (
                    "\n\n  RISCO ALTO SEM SAST: o projeto não declara "
                    f"`[gates] {GATE_DO_RISCO_ALTO}`, então nenhuma análise "
                    "estática rodou.\n            A frente de segurança é a "
                    "única que olha; diga isso no relatório do step.")
        if destino == 9:
            com, sem = frentes_com_baseline(atividade)
            linhas = [f"FRENTES COM BASELINE: {', '.join(com) or 'nenhuma'}."]
            if sem:
                faltam = ", ".join(
                    f"`{f}` (falta `{BASELINE_DA_FRENTE[f]}`)" for f in sem)
                linhas.append(
                    f"SEM BASELINE: {faltam}.\n            NÃO as rode: frente "
                    "sem contra o que conferir não fica quieta, ela INFERE — e "
                    "produz\n            achado contra documento que ninguém "
                    "escreveu. Declare `nao-coberta`."
                )
            aviso_frentes = "            ".join(linhas)
            # A baseline entra na nota da entrada que JÁ existe, e não numa
            # linha nova: o contador de voltas do step 9 conta ENTRADAS no
            # histórico, e uma linha a mais por entrada dobrava a conta — a
            # terceira volta viraria a sexta, e o step pararia dizendo que
            # esgotou o limite.
            #
            # Defeito meu, pego pelo teste que já existia. É a forma mais
            # comum da classe: o mecanismo escreve no lugar certo e quebra
            # outro leitor do mesmo arquivo.
            marca = ("Baseline do step 9: com "
                     + (", ".join(com) or "nenhuma") + "; sem "
                     + (", ".join(sem) or "nenhuma") + ".")
            quando, onde, nota_atual = atividade.history[-1]
            atividade.history[-1] = (
                quando, onde, (nota_atual + " " if nota_atual else "") + marca)
            pendentes, arvore_contada = entrega_nao_commitada(atividade)
            # A consequência é a mesma nos dois casos — é a PERGUNTA que muda:
            # "sua entrega não chega nas frentes" contra "não sei se chega".
            cauda = (
                "            As frentes "
                "`quality` e `runtime` rodam em WORKTREE PRÓPRIA, e "
                "worktree nasce do\n            que está commitado — elas "
                "vão receber a base, não a sua entrega.\n            "
                "Commite antes, ou espelhe para dentro delas e PROVE por "
                "md5.\n            Sem isso, a frente mede o código de "
                "antes e reporta \"não reproduzi\" —\n            que "
                "numa volta de correção parece confirmação de conserto."
            )
            if pendentes is None:
                # O zero silencioso na porta do step 9. Sem árvore declarada
                # este contador não tem o que contar — e até 2.45.5 ele caía
                # na raiz do projeto, onde uma árvore limpa devolvia ZERO.
                # Zero se lê como "entrega commitada": a resposta certa para
                # a pergunta errada.
                aviso_frentes += (
                    "\n\n            ENTREGA NÃO CONFERIDA: a árvore desta "
                    "atividade não está declarada\n            (worktree: "
                    f"{arvore_contada}), então NÃO contei o que está sem "
                    "commitar.\n            Isto não é \"está limpo\", é "
                    "\"não sei\". Rode o `avancar` de DENTRO da árvore da "
                    "atividade:\n            o campo se preenche sozinho. Ou "
                    "declare com `corrigir --branch ... --worktree ...`.\n"
                    + cauda
                )
            elif pendentes:
                aviso_frentes += (
                    f"\n\n            ENTREGA NÃO COMMITADA: {pendentes} "
                    f"entrada(s) vivas em\n            {arvore_contada}\n"
                    + cauda
                )
        else:
            aviso_frentes = ""
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
        trilha_atual = atividade.meta.get("trilha", "")

    atualizar_metricas(args.id)
    # O `avancar` da `revisao` roda em worktree alheia a cada step, não só no
    # fim — a guarda vale nos dois, senão fecha a porta e deixa a janela.
    publicar_metricas(trilha=trilha_atual)
    print(f"{args.id}: agora em {rotulo(destino)}")
    if aviso_local:
        print()
        print(aviso_local)
        print()
    if aviso_orcamento:
        print(aviso_orcamento)
    if aviso_frentes:
        print()
        print("  " + aviso_frentes)
    if aviso_exigencia:
        print()
        print("  " + aviso_exigencia)
    if STEPS[destino]["tipo"] == "humano":
        print("  Este step é humano. Pare e peça a validação antes de seguir.")
    else:
        print(f"  disparo: {disparo(destino)}")
    relatar(avisos)
    return 0


def atualizar_metricas(ident: str) -> None:
    """Recolhe as métricas desta atividade, em silêncio e sem poder atrapalhar.

    Fica preso à passagem de step e ao `concluir` porque é lá que o número
    muda de verdade — e porque uma métrica que só existe quando alguém lembra
    de gerar é uma métrica que não existe. Mesma razão da âncora.

    Três garantias, todas por causa de erro conhecido:

    Roda SÓ esta atividade. Coletar o projeto inteiro leva ~45 s aqui; por
    atividade, ~3 s. Preso ao `avancar`, o total transformaria cada passagem
    de step numa espera.

    Nunca reprova. Um `avancar` que falha porque o coletor de métrica tropeçou
    trocaria o estado do fluxo — que é a fonte de verdade — por um relatório.

    Não imprime nada em caminho feliz. O `avancar` já diz o que importa.
    """
    import subprocess
    ferramenta = Path(__file__).resolve().parents[1] / "metrics" / "metrics.py"
    if not ferramenta.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(ferramenta), "coletar",
             "--atividade", str(ident), "--silencioso"],
            capture_output=True, timeout=60, check=False)
    except Exception:
        pass


def arvore_alheia() -> str:
    """`""` quando estamos na árvore principal; senão, o caminho onde estamos.

    `--show-toplevel` é a árvore de trabalho ATUAL; `--git-common-dir` aponta
    para o `.git` do repositório principal mesmo de dentro de uma worktree. Se
    as duas discordam, quem chamou está numa worktree — e publicar resumo do
    projeto ali escreve no ramo de outra pessoa.
    """
    import subprocess
    def git(*a: str) -> str:
        try:
            r = subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=15)
        except (OSError, subprocess.SubprocessError):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""

    topo = git("rev-parse", "--show-toplevel")
    comum = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not topo or not comum:
        return ""                      # sem Git, não há o que comparar
    principal = str(Path(comum).parent) if Path(comum).name == ".git" else ""
    if not principal:
        return ""
    return "" if Path(topo).resolve() == Path(principal).resolve() else topo


def publicar_metricas(indexar: bool = False, trilha: str = "") -> None:
    """Regrava o resumo versionado do projeto — `docs/` e o bloco do README.

    Fica ao lado do `atualizar_metricas` e obedece às mesmas três garantias:
    nunca reprova, roda em silêncio no caminho feliz do `avancar`, e não custa
    nada quando não há o que fazer. A quarta é só dela: **só escreve no
    repositório se `[metricas] publicar_no_repo` disser que sim.** O padrão é
    `false`, e o `--auto` é o que faz o comando respeitar isso.

    Regenera a cada passagem de step e **indexa só no `concluir`**. Regenerar
    sempre mantém o arquivo verdadeiro; indexar a cada step encheria a
    atividade de um diff de métrica por passagem. E indexar não é commitar:
    o commit continua sendo de quem trabalha.

    **Duas recusas, e as duas FALAM.** Medidas em 12/09/2026, no `concluir` de
    uma revisão do PR 2210:

    1. **Trilha `revisao`.** Ela não commita, não empurra e não escreve nada do
       dono do card — e este era o único ponto do fluxo que deixava arquivo
       pronto para commit na árvore de outra pessoa. O `concluir` regerou
       README e métricas e **indexou os três** sobre o PR dela.
    2. **Qualquer trilha, fora da árvore principal.** Resumo do projeto
       publicado de dentro de uma worktree escreve no ramo que estiver ali.

    Recusar calado seria o mesmo defeito com outra cara, então as duas
    imprimem o motivo. E a recusa é de PUBLICAR, não de medir: o
    `atualizar_metricas` continua gravando em `.agents/`, que não é versionado.
    """
    import subprocess
    ferramenta = Path(__file__).resolve().parents[1] / "metrics" / "metrics.py"
    if not ferramenta.exists():
        return
    if trilha == "revisao":
        print("  [métricas] não publiquei: a trilha `revisao` não escreve no "
              "repositório de\n             quem é dono do card. A medida está "
              "em .agents/, que não é versionado.")
        return
    fora = arvore_alheia()
    if fora:
        print(f"  [métricas] não publiquei: esta é uma worktree ({fora}), e o "
              "resumo do\n             projeto pertence à árvore principal. "
              "Rode o `publicar` de lá.")
        return
    argv = [sys.executable, str(ferramenta), "publicar", "--auto"]
    argv += ["--indexar"] if indexar else ["--calado"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, check=False)
    except Exception:
        return
    saida = (r.stdout or "").strip()
    if indexar and saida:
        print(saida)


TAG_MEIA_ENTREGA_PADRAO = "Aguardando frontend"

# Impresso onde quem orquestra lê o próximo step. Medido em 25-26/09/2026: 61%
# do custo aconteceu com mais de 200 mil de contexto, e os agentes mais caros
# eram general-purpose emendando steps ("steps 2 a 4", até 917 mil).
DISPARO_DE_STEP = ("contexto novo, UM step por disparo: janela nova, ou subagente "
                   "`elcamargo-ai-flow:elcamargo-step-runner`. Não emende no "
                   "contexto que rodou o step anterior.")

# O modelo do disparo, por step, derivado de `STEPS`. Só tem `modelo` o step
# cuja saída uma PESSOA lê antes de alguém construir em cima dela: se o modelo
# errar, o erro aparece na pergunta e não escapa calado. Os outros herdam de
# quem dispara. A regra, e por que as frentes que entregam achado ficam de
# fora, em references/model-policy.md.
MODELO_DO_DISPARO = {n: d["modelo"] for n, d in STEPS.items() if d.get("modelo")}


def disparo(step: int) -> str:
    modelo = MODELO_DO_DISPARO.get(step)
    if not modelo:
        return DISPARO_DE_STEP
    return f"{DISPARO_DE_STEP} Este step dispara com `model: \"{modelo}\"`."

# O par analista -> dev tem a etiqueta dele. Quem lê o board é quem NÃO está no
# fluxo — o dev que vai pegar o card, o gerente que pergunta por que parou — e
# para essa pessoa "especificado e aguardando" é informação que não existe em
# lugar nenhum além daqui.
TAG_AGUARDANDO_DEV_PADRAO = "Aguardando desenvolvimento"


def marcar_no_board(agents: Path, atividade: "Atividade") -> None:
    """A meia entrega se declara NO CARD, e a declaração se desfaz sozinha.

    `backend` fecha e o card ganha a etiqueta com a justificativa; `frontend`
    fecha e a etiqueta sai. Quem lê o board é justamente quem não está no
    fluxo — o gerente que pediu a antecipação, o time mobile que vai construir
    contra o contrato — e para essa pessoa o card é a única fonte.

    **Nunca derruba o `concluir`.** O board pode ser `nenhum`, o `az` pode não
    estar instalado, a máquina pode estar sem rede. Perder a etiqueta é ruim;
    perder o encerramento de uma atividade por causa dela seria pior, e o
    caminho de volta é uma linha de comando que esta função imprime.

    Mesma garantia do `publicar_metricas`: falha fala, e não levanta.
    """
    # A etiqueta sai do PAR, não do escopo. `escopo` diz que camada o step 8
    # implementa, e a `especificacao` não implementa nenhuma — keyar por ele
    # deixaria o par novo sem etiqueta, que é justamente o estado que o board
    # existe para mostrar a quem não está no fluxo.
    escopo = atividade.meta.get("escopo", "") or atividade.meta.get("trilha", "")
    if escopo not in SUFIXO_DE_ESCOPO:
        return
    ident = atividade.meta.get("id", "")
    card = ident[: -len(SUFIXO_DE_ESCOPO[escopo])] if ident.endswith(
        SUFIXO_DE_ESCOPO[escopo]) else ""
    if not card:
        print(f"  [board] não marquei: o id `{ident}` não diz de que card ele "
              "é a metade.")
        print("          O par é `<card>-backend` e `<card>-frontend`.")
        return
    # Cada par tem a sua etiqueta e a sua chave de config. O padrão vale quando
    # o `config.py` não carrega — perder a etiqueta é ruim, derrubar o
    # `concluir` por causa dela seria pior.
    chave, padrao = (("board.tag_aguardando_dev", TAG_AGUARDANDO_DEV_PADRAO)
                     if escopo.startswith("especificacao") or escopo == "construcao"
                     else ("board.tag_meia_entrega", TAG_MEIA_ENTREGA_PADRAO))
    try:
        import config as C  # tardio: config.py importa deste módulo
        tag = C.obter(chave, padrao, agents)
    except Exception:
        tag = padrao
    tag = uma_linha(str(tag or padrao))
    remover = escopo in ("frontend", "construcao")
    outra = atividade.meta.get("outra_metade", "") or "a outra metade"
    if escopo.startswith("especificacao"):
        porque = (
            f"[fluxo] `{tag}`: a especificação deste card está PRONTA e "
            f"aprovada no portão 5, pela atividade `{ident}`. Nada foi "
            "implementado ainda. Quem for construir abre a atividade "
            f"`{outra}` na trilha `construcao` — ela herda esta "
            "especificação e não recomeça do zero."
        )
    elif escopo == "construcao":
        porque = (
            f"[fluxo] A etiqueta `{tag}` SAI: a construção ({ident}) fechou "
            "sobre a especificação que estava aguardando, e o card está "
            "entregue."
        )
    else:
        porque = (
            f"[fluxo] A etiqueta `{tag}` SAI: a metade de frente ({ident}) "
            f"fechou, e o card está entregue inteiro."
            if remover else
            f"[fluxo] `{tag}`: somente o BACKEND foi implementado, pela "
            f"atividade `{ident}`. A camada de tela está especificada e não "
            f"implementada — ela é a atividade `{outra}`, que ainda não rodou. "
            "O contrato de API deste card já está de pé e pode ser consumido."
        )
    ferramenta = Path(__file__).resolve().parents[1] / "board" / "board.py"
    if not ferramenta.exists():
        return
    import subprocess
    argv = [sys.executable, str(ferramenta), "marcar", card,
            "--tag", tag, "--porque", porque]
    if remover:
        argv.append("--remover")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, check=False)
    except Exception as exc:  # noqa: BLE001 — qualquer falha aqui é recuperável
        r = None
        motivo = str(exc)
    else:
        motivo = (r.stderr or r.stdout or "").strip()
    if r is not None and r.returncode == 0:
        print(f"  [board] card {card}: etiqueta `{tag}` "
              + ("removida." if remover else "posta, com a justificativa."))
        return
    print(f"  [board] NÃO consegui {'tirar' if remover else 'pôr'} a etiqueta "
          f"`{tag}` no card {card}.")
    # A PRIMEIRA linha de um traceback é "Traceback (most recent call last):",
    # que não diz nada a ninguém. O `board.py` fala por `[erro]`; quando não é
    # ele quem fala, a última linha é a que carrega a causa.
    linhas = [ln.strip() for ln in (motivo or "").splitlines() if ln.strip()]
    causa = next((ln for ln in linhas if "[erro]" in ln), linhas[-1] if linhas else "")
    if causa:
        print(f"          {causa}")
    print("          O encerramento valeu assim mesmo. Para refazer só a "
          "etiqueta:")
    print(f"            python3 {ferramenta} marcar {card} --tag '{tag}' "
          f"--porque '...'" + (" --remover" if remover else ""))


def anexar_contrato(agents: Path, atividade: "Atividade") -> None:
    """O contrato sobe AO CARD quando a metade de trás fecha.

    Ele mora em `docs/specs/`, do repositório desta superfície — e quem vai
    construir contra ele **não tem esse repositório**. O card é o único lugar
    que os dois lados abrem, e por isso é o único caminho que existe.

    Só na trilha `backend`, e por assimetria real: o contrato da `frontend` é o
    `sdd-backend`, e quem o consumiria é a próxima atividade de backend — que
    vive no mesmo repositório e lê o arquivo onde ele está.

    **Ausência fala.** Se a atividade não registrou `sdd-frontend`, o contrato
    ou não foi escrito ou não foi registrado, e as duas são notáveis: ele é o
    produto de verdade desta trilha. O aviso sai no encerramento, com o comando
    que conserta — e não barra, porque barrar o `concluir` deixaria a atividade
    presa em andamento por causa de um registro.

    Como o `marcar_no_board`, **nunca derruba o encerramento**: sem rastreador,
    sem `az login` ou sem rede, ela fala e imprime a linha que refaz só o anexo.
    """
    if atividade.meta.get("escopo") != "backend":
        return
    ident = atividade.meta.get("id", "")
    card = (ident[: -len(SUFIXO_DE_ESCOPO["backend"])]
            if ident.endswith(SUFIXO_DE_ESCOPO["backend"]) else "")
    caminhos = [c for tipo, c in atividade.artefatos if tipo == "sdd-frontend"]
    if not caminhos:
        print("  [contrato] esta atividade NÃO registrou `sdd-frontend`, que é "
              "o produto desta trilha.")
        print("             Quem vai construir a outra metade não tem este "
              "repositório: sem o")
        print("             contrato no card, ele não recebe nada. Registre e "
              "anexe à mão:")
        print(f"               flow_state.py artefato {ident} --tipo "
              "sdd-frontend --caminho <arquivo>")
        return
    if not card:
        print(f"  [contrato] não anexei: o id `{ident}` não diz de que card ele "
              "é a metade.")
        return
    caminho = Path(caminhos[-1])
    if not caminho.is_absolute():
        caminho = (raiz_do_projeto(agents) / caminho)
    if not caminho.exists():
        print(f"  [contrato] não anexei: `{caminhos[-1]}` está registrado e não "
              "existe no disco.")
        return
    ferramenta = Path(__file__).resolve().parents[1] / "attach" / "attach.py"
    if not ferramenta.exists():
        return
    import subprocess
    argv = [sys.executable, str(ferramenta), str(caminho), "--card", card,
            "--contrato", "quem vai construir a camada de tela",
            "--comentario", f"Contrato desta entrega ({ident})"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180, check=False)
    except Exception as exc:  # noqa: BLE001
        r, motivo = None, str(exc)
    else:
        motivo = (r.stderr or r.stdout or "").strip()
    if r is not None and r.returncode == 0:
        print(f"  [contrato] {caminho.name} anexado ao card {card}, conferido "
              "por ida e volta.")
        return
    print(f"  [contrato] NÃO consegui anexar {caminho.name} ao card {card}.")
    linhas = [ln.strip() for ln in (motivo or "").splitlines() if ln.strip()]
    causa = next((ln for ln in linhas if "erro" in ln.lower()),
                 linhas[-1] if linhas else "")
    if causa:
        print(f"             {causa}")
    print("             O encerramento valeu. Para refazer só o anexo:")
    print(f"               python3 {ferramenta} {caminho} --card {card} "
          "--contrato 'quem vai construir a camada de tela'")


def conferir_orcamento(agents: Path, ident: str) -> str:
    """O gasto medido passou do orçamento que o projeto declarou?

    Devolve texto de aviso quando há algo a dizer sem barrar, `""` quando não
    há nada, e levanta `FlowStateError` quando estourou.

    Três recusas deliberadas no desenho, e cada uma tem número atrás:

    **Por atividade, não por step** — embora a frente aberta pedisse por step.
    O `metrics.py` só atribui step aos SUBAGENTES: `por_step` é preenchido
    dentro do laço de subagente, e os turnos do orquestrador não têm step. No
    painel medido eles são **27,7% do gasto**. Orçamento por step veria menos
    do que se gasta, e número que sai menor do que é é a direção proibida.

    **Em dólar, não em token.** São quatro contadores com preços até 50x
    diferentes entre si — 1,83 bilhão de cache lido contra 3,97 M de saída,
    medidos na mesma atividade. Somar os quatro dá um número dominado pelo
    cache barato, e alguém queimaria saída à vontade sem mover o total. Dólar
    é a soma ponderada pelo preço, e é por isso que a unidade é ele.

    **Não barra o `concluir`.** Travar o fechamento deixaria a atividade presa
    em andamento, que é pior que estourar o orçamento — e o `concluir` é o
    aceite de uma pessoa, não passagem automática.

    E ela nunca derruba o `avancar` por conta própria: config ausente, JSON
    corrompido ou chave mal declarada resultam em "não confere", nunca em
    exceção. Quem reprova declaração malformada é o `doctor.py`. O `avancar` é
    a espinha do fluxo; um conferidor de orçamento não pode quebrá-la.
    """
    try:
        import config as C
        teto = C.obter("metricas.orcamento_usd", None, agents)
    except Exception:
        return ""                      # projeto sem config: não há orçamento
    if teto is None or teto == "":
        return ""
    try:
        teto = float(teto)
    except (TypeError, ValueError):
        return ("  [orçamento não conferido] `[metricas] orcamento_usd` não é "
                "número. Rode `doctor.py conferir`.")
    if teto <= 0:
        return ""

    alvo = agents / "metrics" / f"{ident}.json"
    if not alvo.is_file():
        return ""                      # nada coletado ainda: normal no começo
    try:
        registro = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    # O zero silencioso, na porta do orçamento. Uma atividade que a coleta não
    # conseguiu atribuir reporta US$ 0,00 — e passaria por BAIXO de qualquer
    # teto, para sempre. Não conferir é correto; não DIZER que não conferiu
    # seria a mesma falsa completude que o `sem-prova` existe para acusar.
    if registro.get("atribuicao") == "sem-prova":
        motivo = registro.get("motivo_atribuicao") or "motivo não registrado"
        return ("  [orçamento não conferido] a última coleta não conseguiu "
                "atribuir trabalho\n"
                "      a esta atividade, então o custo dela sai US$ 0,00 e "
                "passaria por baixo\n"
                f"      de qualquer teto. Motivo: {motivo}")

    gasto = float(registro.get("custo_usd") or 0.0)
    if gasto <= teto:
        return ""

    quando = registro.get("gerado_em") or datetime.fromtimestamp(
        alvo.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    excesso = gasto - teto
    raise FlowStateError(
        f"{ident} passou do orçamento declarado.\n\n"
        f"      gasto na última coleta   US$ {gasto:>12,.2f}\n"
        f"      orçamento declarado      US$ {teto:>12,.2f}\n"
        f"      passou                   US$ {excesso:>12,.2f}  "
        f"(+{excesso * 100 / teto:.1f}%)\n\n"
        f"      Coletado em {quando} — o número é da última coleta, não de\n"
        f"      agora. Rode `metrics.py coletar --atividade {ident}` para\n"
        "      conferir antes de decidir.\n\n"
        "      Para seguir mesmo assim:\n"
        f"          flow_state.py avancar {ident} --forcar --nota \"<por quê>\""
    )


def cmd_risco(args: argparse.Namespace) -> int:
    """Muda o risco depois do `iniciar`, com o motivo no histórico.

    O caso que pede isto: o step 9 lê o diff e vê que a mudança toca a sessão
    do usuário, num card aberto como `padrao`. Ou o contrário, a pessoa marcou
    `alto` por cautela e a SDD mostrou que não era. As duas mudanças são
    decisão, e decisão fica escrita.
    """
    agents = resolve_agents_dir()
    if not args.nota:
        raise FlowStateError("--nota é obrigatória: o histórico precisa dizer "
                             "por que o risco mudou.")
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        antes = atividade.meta.get("risco") or "padrao"
        superficies = (ler_superficies(args.superficies)
                       if args.superficies is not None
                       else (atividade.meta.get("superficies") or "").split())
        avisos = conferir_risco(args.nivel, superficies, atividade.meta["trilha"])
        agora_str = agora()
        atividade.meta["risco"] = args.nivel
        if superficies:
            atividade.meta["superficies"] = " ".join(superficies)
        else:
            atividade.meta.pop("superficies", None)
        atividade.meta["atualizado_em"] = agora_str
        atividade.history.append((
            agora_str, rotulo(atividade.step),
            f"Risco: {antes} → {args.nivel}. Superfícies: "
            + (", ".join(superficies) or "nenhuma") + f". {uma_linha(args.nota)}"))
        # Subir para alto com o step 9 já em curso, ou passado: a exigência que
        # o `avancar` teria gravado na entrada do 9 entra agora.
        if (args.nivel == "alto" and antes != "alto"
                and 9 in atividade.trilha and atividade.step >= 9):
            dimensao, porque = CONFERENCIA_DO_RISCO_ALTO
            atividade.conferencias.append((agora_str, dimensao, "exigida", porque))
            avisos.append(f"CONFERÊNCIA EXIGIDA AGORA: `{dimensao}` — {porque}.")
        atividade.escrever(path)
        avisos = regenerar_indice(agents) + avisos
    print(f"{args.id}: risco {antes} → {args.nivel}")
    relatar(avisos)
    return 0


def cmd_corrigir(args: argparse.Namespace) -> int:
    """Muda o LUGAR da atividade — branch e worktree — de propósito.

    Existe porque a alternativa era editar o front matter do arquivo de estado à
    mão, que foi o que uma frente teve de fazer para se recuperar do `avancar`
    que sobrescrevia. Editar estado à mão funciona quando é quem escreveu a
    ferramenta; quebra quando é outro, e não deixa rastro nenhum.

    Os dois campos andam juntos: metade de um lugar descreve um lugar que nunca
    existiu. E a mudança entra no histórico da atividade, porque trocar onde o
    trabalho acontece é evento, não detalhe.
    """
    agents = resolve_agents_dir()
    branch = uma_linha(args.branch or "")
    worktree = uma_linha(args.worktree or "")
    if not branch or not worktree:
        raise FlowStateError(
            "--branch e --worktree são exigidos juntos. Metade de um lugar "
            "descreve um lugar que nunca existiu, e é justamente o estado que "
            "faz o step seguinte trabalhar no lugar errado."
        )

    caminho_wt = Path(worktree).expanduser()
    if not args.forcar:
        if not caminho_wt.is_dir():
            raise FlowStateError(
                f"{caminho_wt} não existe. Confira com `git worktree list`, ou "
                "use --forcar se a árvore ainda vai ser criada."
            )
        # `refs/heads/` sozinho recusava `origin/feat/...`, que é o lugar
        # legítimo de uma worktree de revisão — a branch é do outro dev e
        # existe só como referência remota aqui. Exigir `--forcar` para isso
        # gastava a saída de emergência no caso NORMAL da trilha `revisao`.
        existe = any(
            _git(["rev-parse", "--verify", f"{prefixo}{branch}"], caminho_wt)
            for prefixo in ("refs/heads/", "refs/remotes/", ""))
        if not existe:
            raise FlowStateError(
                f"`{branch}` não existe em {caminho_wt}, nem como branch local, "
                "nem como referência remota, nem como commit. Confira com "
                "`git branch -a`, ou use --forcar se ela ainda vai ser criada."
            )

    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        antes = {k: atividade.meta.get(k, "(vazio)") for k in ("branch", "worktree")}
        agora_str = agora()
        if antes["branch"] == branch and antes["worktree"] == worktree:
            # Já bate. Sem `--nota` não há o que registrar, e gravar histórico
            # a cada conferência encheria a atividade de linhas que não contam
            # nada. COM `--nota`, o caso é outro: quem escreveu uma nota está
            # pedindo o registro — e o caso real foi este, uma frente que
            # corrigiu o front matter à mão antes de o comando existir e ficou
            # sem como deixar rastro depois.
            if not args.nota:
                print(f"{args.id}: já estava em {branch} · {worktree}. "
                      "Nada mudou.")
                return 0
            atividade.meta["atualizado_em"] = agora_str
            atividade.history.append(
                (agora_str, "lugar conferido",
                 f"{branch} · {worktree} — {uma_linha(args.nota)}"))
            atividade.escrever(path)
            avisos = regenerar_indice(agents)
            print(f"{args.id}: o lugar já estava certo; a nota ficou registrada.")
            relatar(avisos)
            return 0
        atividade.meta["branch"] = branch
        atividade.meta["worktree"] = worktree
        atividade.meta["atualizado_em"] = agora_str
        atividade.history.append(
            (agora_str, "lugar corrigido",
             f"de {antes['branch']} · {antes['worktree']} "
             f"para {branch} · {worktree}"
             + (f" — {uma_linha(args.nota)}" if args.nota else "")))
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    print(f"{args.id}: lugar corrigido")
    print(f"  de   {antes['branch']} · {antes['worktree']}")
    print(f"  para {branch} · {worktree}")
    print("  O step seguinte lê estes campos para saber onde trabalhar.")
    relatar(avisos)
    return 0


# O vocabulário do `--tipo`, espelhando a tabela do `FLOW.md`. A lista existe
# porque **tipo que ninguém reconhece some para quem procura**: um step que
# registra `comentario-pr` no chute grava alguma coisa, e o step seguinte, que
# procura por nome, não acha nada. Foi o que aconteceu no primeiro uso da
# trilha `revisao`, em 11/09/2026 — o comando aceitou o nome inventado sem
# dizer nada.
#
# A lista AVISA e não recusa, de propósito. Recusar perderia o registro de um
# artefato que existe, e um artefato com rótulo errado é melhor que artefato
# nenhum: o rótulo se conserta, a ausência ninguém percebe. É a mesma razão
# pela qual `nao-coberta` passa: o que não pode é sumir.
TIPOS_DE_ARTEFATO = {
    "sdd-negocio", "relatorio-negocio", "sdd-sistema", "veredicto-sistema",
    "decisoes-ux", "prototipo", "implementacao", "revisao-desenvolvimento",
    # A trilha `revisao` não tem step 8, então o relatório dela não volta para
    # ninguém dentro do fluxo: ele vai ao dono do card, com endereço. Mesma
    # forma do `relatorio-negocio`, que vai ao analista.
    "revisao-publicada",
    "anexo", "matriz", "inventario-pf",
    # As duas metades de uma especificação de sistema, para as trilhas
    # `backend` e `frontend`. A da camada que a atividade NÃO implementa é o
    # contrato: ela nasce completa o bastante para outro time construir contra
    # ela, e é conferida por execução antes de a metade fechar.
    "sdd-backend", "sdd-frontend",
    # A comparação da perna sombra do step 9. Vai ao portão 10 junto do
    # relatório, e não ao step 8. Ver `references/shadow-leg.md`.
    "perna-sombra",
}


RE_PARECE_ARQUIVO = re.compile(r"^(?!\w+://).*/[^/]+\.[A-Za-z0-9]{1,5}$")


def parece_caminho_de_arquivo(caminho: str) -> bool:
    """Este artefato é um ARQUIVO do repositório, ou outra coisa?

    A pergunta existe porque nem todo artefato é arquivo, e conferir existência
    de todos barraria o caso normal. Medido no vocabulário: `prototipo` recebe
    caminho de COMPONENTE no Figma — `Administrador/Botões/Primário` —, `anexo`
    recebe nome de anexo de card, e `pr` recebe `PR 42`.

    O critério é conservador de propósito: **barra com `/` e extensão no último
    segmento**, e nada de esquema de URL. `docs/specs/RDM-1054.md` entra;
    `Administrador/Botões/Primário` não entra, porque não tem extensão;
    `https://…/x.md` não entra, porque tem esquema.

    Errar para o lado de NÃO conferir é o lado certo: o aviso que não sai custa
    um ponteiro morto que o `status` ainda denuncia, e o aviso que sai errado
    ensina a ignorar avisos.
    """
    return bool(RE_PARECE_ARQUIVO.match(caminho))


def artefato_ausente(agents: Path, atividade: "Atividade", caminho: str) -> bool:
    """O caminho parece arquivo e não existe em árvore nenhuma que eu conheça.

    Procura na raiz do projeto E na worktree declarada da atividade: o artefato
    pode ter sido escrito na árvore da frente e ainda não ter chegado à
    principal, e acusar isso como ausente seria alarme falso no caso normal.
    """
    if not parece_caminho_de_arquivo(caminho):
        return False
    candidatas = [raiz_do_projeto(agents)]
    onde = uma_linha(atividade.meta.get("worktree") or "")
    if onde and onde != LUGAR_PENDENTE:
        candidatas.append(Path(onde))
    alvo = Path(caminho)
    if alvo.is_absolute():
        return not alvo.exists()
    return not any((raiz / caminho).exists() for raiz in candidatas)


def documentos_no_artefato(agents: Path, atividade: "Atividade", caminho: str) -> list[str]:
    """As linhas `arquivo:linha: CPF por extenso` do artefato, nunca o número.

    Medido em 30/09/2026: o CPF de teste escrito na SDD de negócio e no
    relatório da volta 1 da 1052 foi lido por `sed` e `cat` no step 9, e o
    orquestrador que leu passou a ter TODA chamada barrada pelo guardrail. O
    artefato fica no repositório, e envenena qualquer contexto que o abrir
    depois. Ver `references/documents-in-context.md`.
    """
    if not parece_caminho_de_arquivo(caminho):
        return []
    ferramenta = Path(__file__).resolve().parents[1] / "doc-mask" / "doc_mask.py"
    onde = uma_linha(atividade.meta.get("worktree") or "")
    raizes = [Path(onde)] if onde and onde != LUGAR_PENDENTE else []
    raizes.append(raiz_do_projeto(agents))
    alvo = Path(caminho)
    arquivo = alvo if alvo.is_absolute() else next(
        (r / caminho for r in raizes if (r / caminho).is_file()), None)
    if not ferramenta.exists() or arquivo is None or not arquivo.is_file():
        return []
    try:
        r = subprocess.run([sys.executable, str(ferramenta), "conferir", str(arquivo)],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [l for l in r.stdout.splitlines() if l.endswith("por extenso")] if r.returncode == 1 else []


def cmd_artefato(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        tipo, caminho = uma_linha(args.tipo), uma_linha(args.caminho)
        if not tipo or not caminho:
            raise FlowStateError("--tipo e --caminho não podem ser vazios.")
        antigo = uma_linha(getattr(args, "substituir", "") or "")
        retirar = bool(getattr(args, "retirar", False))
        agora_str = agora()
        avisos: list[str] = []

        if retirar and antigo:
            raise FlowStateError(
                "--retirar e --substituir não andam juntos: um tira, o outro "
                "troca. Escolha o que aconteceu."
            )

        if retirar:
            # Tirar um registro é o oposto do que esta tabela existe para
            # fazer, então custa uma explicação. Ver `cmd_corrigir`: a mesma
            # razão pela qual mudar o LUGAR deixa rastro.
            if not args.nota:
                raise FlowStateError(
                    "--retirar exige --nota. Um artefato que some sem "
                    "explicação é indistinguível de um que nunca foi "
                    "registrado, e é o registro que esta tabela existe para "
                    "guardar."
                )
            alvo = (tipo, caminho)
            if alvo not in atividade.artefatos:
                raise FlowStateError(
                    f"não há artefato `{tipo}` em {caminho} nesta atividade.\n"
                    "  Confira com `status` — retirar o que não está "
                    "registrado sairia com sucesso\n"
                    "  e não teria feito nada, que é a forma de erro mais "
                    "cara aqui."
                )
            atividade.artefatos.remove(alvo)
            atividade.history.append(
                (agora_str, "artefato retirado",
                 f"{tipo}: {caminho}. {args.nota}"))
            print(f"{args.id}: artefato {tipo} retirado — {caminho}")
        elif antigo:
            # Renomeação: o par sai e entra NO LUGAR, preservando a ordem. Sem
            # isto o jeito de renomear era registrar o novo e conviver com o
            # velho — que foi o que produziu três `sdd-sistema` numa atividade,
            # um deles apontando para arquivo que não existe mais.
            indices = [n for n, (t, c) in enumerate(atividade.artefatos)
                       if c == antigo and (t == tipo or not args.tipo)]
            if not indices:
                raise FlowStateError(
                    f"não há artefato registrado em {antigo} nesta atividade.\n"
                    "  `--substituir` recebe o caminho ANTIGO, e `--caminho` o "
                    "novo. Confira com `status`."
                )
            atividade.artefatos[indices[0]] = (tipo, caminho)
            # Substituir PARA um caminho já registrado colapsa, em vez de
            # duplicar. Achado pelo teste: o caso real é justamente esse —
            # alguém registra o caminho novo, vê o velho sobrando no `status`,
            # e usa `--substituir` para limpar. Se isso deixasse dois iguais, o
            # conserto criaria a segunda forma do defeito que veio consertar.
            vistos = set()
            unicos = []
            for par_atual in atividade.artefatos:
                if par_atual in vistos:
                    continue
                vistos.add(par_atual)
                unicos.append(par_atual)
            atividade.artefatos[:] = unicos
            atividade.history.append(
                (agora_str, "artefato substituído",
                 f"{tipo}: {antigo} → {caminho}."
                 + (f" {args.nota}" if args.nota else "")))
            print(f"{args.id}: artefato {tipo} substituído — {antigo} → {caminho}")
        else:
            par = (tipo, caminho)
            if par not in atividade.artefatos:
                atividade.artefatos.append(par)
            print(f"{args.id}: artefato {tipo} registrado — {caminho}")

        # O ponteiro morto se acusa NO NASCIMENTO, e AVISA em vez de recusar.
        # Recusar perderia o registro de um artefato que existe — a mesma razão
        # pela qual tipo fora do vocabulário passa. E a conferência só roda no
        # que PARECE arquivo: `prototipo` recebe caminho de componente do
        # Figma, `anexo` recebe nome de anexo de card.
        if not retirar and artefato_ausente(agents, atividade, caminho):
            avisos.append(
                f"CAMINHO QUE NÃO EXISTE: `{caminho}`.\n"
                "            O artefato FOI registrado — perder o registro "
                "seria pior que o ponteiro errado —,\n"
                "            mas as seis frentes do step 9 ABREM este "
                "caminho, e a que não achar vai\n"
                "            reportar \"a spec não existe\": achado que parece "
                "defeito da entrega e é\n"
                "            ponteiro velho.\n"
                "            Se o arquivo foi RENOMEADO, troque em vez de "
                "acrescentar:\n"
                f"                flow_state.py artefato {args.id} --tipo "
                f"{tipo} --substituir <caminho antigo> --caminho {caminho}"
            )

        # Avisa e não recusa, pela mesma razão do ponteiro morto: uma spec
        # sobre o campo de CNPJ traz exemplo de propósito, e perder o registro
        # seria pior. Quem decide trocar é quem escreveu.
        documentos = [] if retirar else documentos_no_artefato(agents, atividade, caminho)
        if documentos:
            avisos.append(
                f"CPF OU CNPJ POR EXTENSO em `{caminho}`:\n"
                + "".join(f"                linha {l.split(': ', 1)[0].rsplit(':', 1)[-1]}: "
                          f"{l.split(': ', 1)[1]}\n" for l in documentos[:5])
                + "            O artefato FOI registrado. Mas quem abrir este arquivo "
                "depois — as frentes do step 9,\n"
                "            o orquestrador que lê o relatório — pode ter o "
                "contexto inteiro barrado pelo\n"
                "            guardrail, como na 1052. Troque por `[CPF]`/`[CNPJ]` e "
                "cite de onde veio:\n"
                f"                doc_mask.py < {caminho} > {caminho}.novo\n"
                "            Ver `references/documents-in-context.md`."
            )

        atividade.meta["atualizado_em"] = agora_str
        atividade.escrever(path)
        avisos += regenerar_indice(agents)
        if tipo not in TIPOS_DE_ARTEFATO:
            avisos.append(
                f"TIPO FORA DO VOCABULÁRIO: `{tipo}`. O artefato FOI registrado "
                "— perder o registro seria pior que o rótulo errado —, mas quem "
                "procurar por nome não vai achá-lo.\n"
                "            Os reconhecidos: "
                + ", ".join(sorted(TIPOS_DE_ARTEFATO)) + ".\n"
                "            Se o tipo novo é para ficar, ele entra no "
                "`FLOW.md` e em `TIPOS_DE_ARTEFATO` — senão é digitação, e "
                "corrigir agora custa menos que procurar depois."
            )
    relatar(avisos)
    return 0


def cmd_pf(args: argparse.Namespace) -> int:
    """Declara o tamanho da atividade em pontos de função.

    Dois números, e o arquivo da atividade guarda os dois:

    `--declarado` é o do analista, contado da especificação funcional, antes
    de existir código. `--aferido` é o do step 9, contado da entrega, com o
    inventário do que foi contado ao lado.

    **`--aferido` exige `--inventario`, e a exigência é mecânica de
    propósito.** Uma obrigação escrita em prosa não acontece — é a mesma razão
    da tabela de *Conferências*. Este número entra no denominador de todo h/PF
    citado depois; sem a conta que o sustenta ele é palpite com casas decimais,
    e um palpite ali falsifica toda produtividade que se cite do painel.

    A ferramenta continua NÃO medindo ponto de função: ela guarda o que foi
    declarado, por quem, e onde está a conta. Quem divergir dos dois números
    decide por si — o `metrics.py` acusa a divergência e não desempata.
    """
    def inteiro(rotulo: str, bruto: str | None) -> int | None:
        if bruto is None:
            return None
        texto = uma_linha(bruto)
        if not texto.isdigit():
            raise FlowStateError(
                f"{rotulo} precisa ser um inteiro não negativo, e veio `{texto}`.")
        return int(texto)

    declarado = inteiro("--declarado", args.declarado)
    aferido = inteiro("--aferido", args.aferido)
    if declarado is None and aferido is None:
        raise FlowStateError("nada a declarar: passe --declarado, --aferido, ou os dois.")
    inventario = uma_linha(args.inventario or "")
    if aferido is not None and not inventario:
        raise FlowStateError(
            "--aferido exige --inventario: um PF sem a conta que o sustenta é\n"
            "palpite, e ele entra no denominador de todo h/PF citado depois.")

    with trava(agents := resolve_agents_dir()):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        if declarado is not None:
            atividade.meta["pf"] = str(declarado)
        if aferido is not None:
            atividade.meta["pf_aferido"] = str(aferido)
            atividade.meta["pf_inventario"] = inventario
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    partes = [f"declarado {declarado}" if declarado is not None else "",
              f"aferido {aferido}" if aferido is not None else ""]
    print(f"{args.id}: PF — " + ", ".join(p for p in partes if p))
    atualizar_metricas(args.id)
    relatar(avisos)
    return 0


VEREDICTOS = ("exigida", "ok", "falhou", "nao-coberta")


def pendencias(atividade: "Atividade") -> list[tuple[str, str]]:
    """Ferramentas exigidas que não fecharam, e as que fecharam mal.

    A regra é a mesma do fluxo inteiro: uma dimensão pode ficar **não coberta**
    desde que seja **declarada**. O que não pode é sumir. `nao-coberta` passa e
    aparece; `exigida` sem `ok` e `falhou` seguram.
    """
    ultimo: dict[str, tuple[str, str]] = {}
    for linha in atividade.conferencias:
        if len(linha) >= 3:
            ultimo[linha[1]] = (linha[2], linha[3] if len(linha) > 3 else "")
    return [(ferramenta, veredicto, detalhe)
            for ferramenta, (veredicto, detalhe) in sorted(ultimo.items())
            if veredicto in ("exigida", "falhou")]


# Na trilha `revisao` o sinal se inverte, e só nela. As outras CONSTROEM: ali
# `falhou` é dívida de quem encerra, e segurar o `concluir` é a régua certa. A
# `revisao` não constrói — ela não tem step 8, não commita e não faz push —,
# então `falhou` é o PRODUTO dela: o defeito que ela foi achar, já publicado
# onde quem conserta vai ler.
#
# O caso que obrigou esta regra, em 11/09/2026: uma revisão fechou com `perfis`
# em `falhou` — dos doze pares exercitados com ator e sessão reais, dez
# provaram o que o perfil não pode e os dois que falharam eram o bloqueador e
# uma alta, ambos já publicados no PR. Não existia caminho que tornasse aquilo
# verde dali, e o `concluir` recusou encerrar. A saída tentadora era
# re-registrar a conferência como `ok`, que apagaria o achado do histórico.
#
# `exigida` continua segurando em TODA trilha: ela não diz "achei defeito", diz
# "ninguém rodou", e isso é lacuna em qualquer regime.
# Conferências que falam da PRÓPRIA passada, e não da entrega revisada.
#
# A regra da 2.26.0 — `falhou` não trava na `revisao`, porque ali o defeito é o
# produto — vale para o que a revisão ACHA. Não vale para o que diz se a
# revisão é confiável.
#
# `arvore: falhou` nunca é achado sobre o outro dev: quer dizer que uma frente
# escreveu na árvore compartilhada e as outras leram por cima disso. `memoria`
# é do mesmo tipo. Deixá-las passar na `revisao` publicaria um relatório cuja
# própria leitura pode ter sido contaminada, com o carimbo de revisão fechada.
#
# Achado em 11/09/2026 ao consertar o registro do guarda de árvore: a árvore
# mexida registrava `falhou` e o `concluir` passava.
# `sobra` entrou na 2.56.0 pela mesma porta, e o caso dela é ainda mais direto:
# o que a passada deixou de pé não é achado sobre a entrega revisada, é dívida
# da própria passada contra a máquina. Uma revisão que trava o Mac de quem vem
# depois não fica quite por ter publicado bons achados.
CONFERENCIAS_DA_PROPRIA_PASSADA = {"arvore", "memoria", "sobra"}


def segura_o_concluir(veredicto: str, trilha: str,
                      ferramenta: str = "") -> bool:
    if veredicto == "exigida":
        return True
    if ferramenta in CONFERENCIAS_DA_PROPRIA_PASSADA:
        return True
    return trilha != "revisao"


def cmd_conferencia(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    veredicto = uma_linha(args.veredicto)
    if veredicto not in VEREDICTOS:
        raise FlowStateError(
            f"veredicto desconhecido: {veredicto!r}. Use um de: "
            + ", ".join(VEREDICTOS) + ". `nao-coberta` existe para a dimensão "
            "que não deu para cobrir — ela passa, e aparece."
        )
    ferramenta = uma_linha(args.ferramenta)
    if not ferramenta:
        raise FlowStateError("--ferramenta não pode ser vazia.")
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)
        atividade.conferencias.append(
            (agora(), ferramenta, veredicto, uma_linha(args.detalhe or "")))
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    print(f"{args.id}: conferência {ferramenta} → {veredicto}")
    relatar(avisos)
    return 0


# --------------------------------------------------------------------------
# Os portões do step 8, rodados por script
# --------------------------------------------------------------------------
# Até 2.57.0 o step 8 lia `config.py gates` e rodava cada comando À MÃO, e a
# skill dizia "Fechar o step com gate vermelho" em *Nunca faça*. Frase em skill
# é pedido, não trava: o que saía do step era a afirmação do modelo de que os
# portões passaram, e a frente de QA rodava tudo de novo para conferir.
#
# Aqui o script roda o declarado e grava o código de saída na tabela
# Conferências — `gate:<nome>`. O `avancar` do 8 para o 9 lê essa tabela, e não
# a conversa. O que o modelo diz sobre os portões deixa de importar; o que o
# processo devolveu é o que fica.

# A ordem em que rodam, quando declarados. Barato primeiro: um lint vermelho
# em dez segundos poupa os quatro minutos da suíte. Chave declarada fora desta
# lista roda depois, na ordem do arquivo.
ORDEM_DOS_GATES = ("lint", "build", "test", "visual", "qualidade_de_tela",
                   "sast", "deps_audit")
SEGUNDOS_POR_GATE_PADRAO = 1800
BYTES_DE_LOG = 200_000


def gates_declarados(agents: Path) -> list[tuple[str, str]]:
    """`(nome, comando)` de cada portão com comando, na ordem de rodar.

    Vazio é "o projeto não declara" — a mesma leitura do `config.py`. Sem
    config nenhum, também vazio: quem não declara portão não tem o que exigir,
    e o doutor é quem acusa isso.
    """
    try:
        import config as C  # tardio: config.py importa deste módulo
        tabela = C.obter("gates", {}, agents) or {}
    except Exception:
        return []
    if not isinstance(tabela, dict):
        return []
    validos = {n: str(c).strip() for n, c in tabela.items()
               if isinstance(c, str) and str(c).strip()}
    ordem = [n for n in ORDEM_DOS_GATES if n in validos]
    ordem += [n for n in validos if n not in ordem]
    return [(n, validos[n]) for n in ordem]


def entrada_no_step(atividade: "Atividade", step: int) -> str:
    """Quando a atividade entrou pela ÚLTIMA vez no step. `""` se nunca.

    A última, e não a primeira: numa volta 9→8 os portões da volta anterior
    mediram o código de antes da correção, e valer por eles seria aprovar o
    conserto com a prova do defeito.
    """
    quando = ""
    for linha in atividade.history:
        if len(linha) >= 2 and re.match(rf"^\s*{step}\b", str(linha[1])):
            quando = max(quando, str(linha[0]))
    return quando


def casos_path(agents: Path, ident: str) -> Path:
    return atividades_dir(agents) / f"{validar_id(ident)}-casos.json"


def gates_dir(agents: Path, ident: str) -> Path:
    return atividades_dir(agents) / f"{validar_id(ident)}-gates"


def falta_para_sair_do_8(atividade: "Atividade", agents: Path) -> list[str]:
    """O que segura a passagem do step 8 para o 9. Lista vazia = pode passar.

    Lê só a tabela Conferências, e só o que foi gravado DEPOIS da última
    entrada no step 8. Cada portão declarado precisa ter `ok` ou `nao-coberta`
    — esta, para o portão que não se aplica à entrega, com o motivo escrito.

    O contrato de casos entra pela mesma porta: `casos` em `exigida` ou
    `falhou` quer dizer que há critério de aceite sem teste verde que o prove.
    """
    desde = entrada_no_step(atividade, 8)
    ultimo: dict[str, tuple[str, str, str]] = {}
    for linha in atividade.conferencias:
        if len(linha) >= 3 and str(linha[0]) >= desde:
            ultimo[linha[1]] = (linha[0], linha[2],
                                linha[3] if len(linha) > 3 else "")
    faltas = []
    for nome, _ in gates_declarados(agents):
        registro = ultimo.get(f"gate:{nome}")
        if registro is None:
            faltas.append(f"`{nome}` não rodou desde a entrada no step 8")
        elif registro[1] not in ("ok", "nao-coberta"):
            faltas.append(f"`{nome}` {registro[1]}: {registro[2]}")
        elif (registro[1] == "nao-coberta" and nome == GATE_DO_RISCO_ALTO
              and atividade.meta.get("risco") == "alto"):
            faltas.append(
                f"`{nome}` nao-coberta, e a atividade é de risco alto: a análise "
                "estática que o projeto declarou precisa rodar")
    # O contrato não tem prazo: ele nasce no começo do step e vale até alguém
    # provar cada caso. Por isso olha a tabela inteira, não só a fatia.
    casos = None
    for linha in atividade.conferencias:
        if len(linha) >= 3 and linha[1] == "casos":
            casos = (linha[2], linha[3] if len(linha) > 3 else "")
    if casos and casos[0] in ("exigida", "falhou"):
        faltas.append(f"`casos` {casos[0]}: {casos[1]}")
    return faltas


def _raiz_dos_gates(atividade: "Atividade", pedida: str) -> Path:
    if pedida:
        return Path(pedida).expanduser().resolve()
    worktree = atividade.meta.get("worktree", "")
    if worktree and worktree != LUGAR_PENDENTE and Path(worktree).is_dir():
        return Path(worktree)
    return Path.cwd().resolve()


def _rodar_gate(comando: str, raiz: Path, limite: int) -> tuple[int | None, str, float]:
    """Roda o comando como o projeto o declarou. `None` no código = estourou."""
    inicio = time.monotonic()
    try:
        r = subprocess.run(comando, shell=True, cwd=str(raiz),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=limite)
        return r.returncode, r.stdout or "", time.monotonic() - inicio
    except subprocess.TimeoutExpired as exc:
        saida = exc.stdout or ""
        if isinstance(saida, bytes):
            saida = saida.decode("utf-8", "replace")
        return None, saida, time.monotonic() - inicio


def _pela_catraca(agents: Path, ident: str, nome: str, log: Path,
                  raiz: Path) -> int | None:
    """Passa o log pela catraca quando o projeto a declara para este portão.

    Devolve o código da catraca — `0` sem falha nova, `1` com falha nova, `2`
    sem linha de base — ou `None` quando não há catraca para este portão.
    A catraca grava a própria conferência (`catraca:<nome>`) com `--registrar`.
    """
    try:
        import config as C
        base = C.obter("catraca.arquivo", "", agents)
        formato = C.obter(f"catraca.formatos.{nome}", "", agents)
        padrao = C.obter(f"catraca.padroes.{nome}", "", agents)
    except Exception:
        return None
    if not base or not (formato or padrao):
        return None
    catraca = Path(__file__).resolve().parent.parent / "ratchet" / "ratchet.py"
    cmd = [sys.executable, str(catraca), "conferir", "--base",
           str(raiz / base), "--portao", nome, "--raiz", str(raiz),
           "--registrar", ident, str(log)]
    cmd += ["--padrao", padrao] if padrao else ["--formato", formato]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    print("\n".join("    " + l for l in (r.stdout or "").splitlines() if l.strip()))
    return r.returncode


def _casos_verdes(agents: Path, ident: str, log: Path, codigo: int | None,
                  raiz: Path) -> None:
    """Depois do portão `test`, o contrato de casos lê o mesmo log."""
    if not casos_path(agents, ident).is_file():
        return
    try:
        import config as C
        formato = C.obter("catraca.formatos.test", "", agents)
    except Exception:
        formato = ""
    matriz = Path(__file__).resolve().parent.parent / "matrix" / "matrix.py"
    cmd = [sys.executable, str(matriz), "casos", "verde", "--atividade", ident,
           "--raiz", str(raiz), "--saida-do-teste", str(log),
           "--codigo", "-1" if codigo is None else str(codigo)]
    if formato:
        cmd += ["--formato", formato]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env={**os.environ,
                                "ELCAMARGO_AGENTS_DIR": str(agents)})
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"    [aviso] o contrato de casos não leu o log: {exc}")
        return
    print("\n".join("    " + l for l in
                    ((r.stdout or "") + (r.stderr or "")).splitlines()
                    if l.strip()))


def arvore_de(raiz: Path) -> str:
    """Impressão do que está na árvore agora, commitado ou não.

    É a árvore que `git add -A && git commit` gravaria, montada num índice
    temporário para não tocar o da pessoa. O commit depois dos portões não a
    muda, e uma linha editada depois deles muda: é isso que diz se o resultado
    ainda vale. Vazio quando não é repositório git.
    """
    try:
        indice = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-path", "index"],
            cwd=raiz, capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "index"
            if Path(indice).is_file():
                shutil.copyfile(indice, temp)  # aproveita o cache de stat
            env = dict(os.environ, GIT_INDEX_FILE=str(temp))
            # `.agents` fica de fora: os próprios logs dos portões e o backup
            # dele mudariam a impressão sem que uma linha do produto mudasse.
            # Tirar depois, e não excluir no `add`: excluir um caminho que o
            # projeto já ignora faz o `git add` sair com 1.
            subprocess.run(["git", "add", "-A"], cwd=raiz, env=env, check=True,
                           capture_output=True, timeout=300)
            subprocess.run(["git", "rm", "-r", "-q", "--cached", "--ignore-unmatch",
                            "--", ".agents"], cwd=raiz, env=env, check=True,
                           capture_output=True, timeout=60)
            return subprocess.run(["git", "write-tree"], cwd=raiz, env=env,
                                  capture_output=True, text=True, check=True,
                                  timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------------------
# O que mudou desde o último portão
# ---------------------------------------------------------------------------
#
# A regra "a parte já aceita não se re-litiga" existia sem nada que separasse a
# parte aceita da nova: quem voltava ao portão 5 depois de devolver a spec
# relia a spec inteira para achar o que o step 3 mexeu. Agora a saída de cada
# portão humano grava a impressão e uma cópia de cada artefato, e a impressão
# da árvore; `desde-aprovacao` compara com o de agora.

# Cópia acima disto vira só impressão: o que importa num portão é texto.
BYTES_POR_COPIA = 2 * 1024 * 1024
LINHAS_DE_DIFF = 200


def portoes_dir(agents: Path, ident: str) -> Path:
    return atividades_dir(agents) / f"{validar_id(ident)}-portoes"


def _raiz_do_portao(agents: Path, atividade: "Atividade") -> Path:
    """Onde o código da atividade está: a worktree dela, ou o projeto."""
    onde = uma_linha(atividade.meta.get("worktree") or "")
    if onde and onde != LUGAR_PENDENTE and Path(onde).is_dir():
        return Path(onde)
    return raiz_do_projeto(agents)


def arquivo_do_artefato(agents: Path, atividade: "Atividade", caminho: str) -> Path | None:
    """O arquivo do artefato, na worktree da atividade ou na raiz do projeto."""
    if not parece_caminho_de_arquivo(caminho):
        return None
    alvo = Path(caminho)
    if alvo.is_absolute():
        return alvo if alvo.is_file() else None
    raizes = []
    onde = uma_linha(atividade.meta.get("worktree") or "")
    if onde and onde != LUGAR_PENDENTE:
        raizes.append(Path(onde))
    raizes.append(raiz_do_projeto(agents))
    return next((r / caminho for r in raizes if (r / caminho).is_file()), None)


def _sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def registrar_portao(agents: Path, atividade: "Atividade", step: int,
                     desfecho: str, quando: str) -> str:
    """Grava o que o portão viu, e devolve a linha para o Histórico.

    Roda na SAÍDA do portão, aprovando ou devolvendo, porque é aí que a pessoa
    decidiu sobre um conteúdo. Nunca segura a transição: o que não deu para
    gravar fica dito no manifesto, e o `desde-aprovacao` diz que não sabe.
    """
    base = portoes_dir(agents, atividade.meta["id"])
    numero = 1 + sum(1 for d in base.glob("[0-9]*") if d.is_dir()) if base.is_dir() else 1
    pasta = base / f"{numero:02d}-p{step}-{desfecho}"
    (pasta / "arquivos").mkdir(parents=True, exist_ok=True)
    raiz = _raiz_do_portao(agents, atividade)
    artefatos = []
    for i, (tipo, caminho) in enumerate(
            ((a[0], a[1]) for a in atividade.artefatos if len(a) >= 2), 1):
        item = {"tipo": tipo, "caminho": caminho, "sha256": None, "copia": None}
        arquivo = arquivo_do_artefato(agents, atividade, caminho)
        if arquivo is None:
            item["motivo"] = ("ausente" if parece_caminho_de_arquivo(caminho)
                              else "não é arquivo")
        else:
            try:
                item["sha256"] = _sha256(arquivo)
                if arquivo.stat().st_size <= BYTES_POR_COPIA:
                    copia = f"arquivos/{i:02d}-{arquivo.name}"
                    shutil.copyfile(arquivo, pasta / copia)
                    item["copia"] = copia
                else:
                    item["motivo"] = "grande demais para cópia"
            except OSError as exc:
                item["motivo"] = f"ilegível: {exc}"
        artefatos.append(item)
    manifesto = {
        "numero": numero, "quando": quando, "step": step, "desfecho": desfecho,
        "raiz": str(raiz), "commit": _git(["rev-parse", "HEAD"], raiz),
        "arvore": arvore_de(raiz), "artefatos": artefatos,
    }
    (pasta / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    impressos = sum(1 for a in artefatos if a["sha256"])
    return (f"Portão {step} {'aprovado' if desfecho == 'aprovado' else 'devolvido'}: "
            f"{impressos} de {len(artefatos)} artefato(s) com impressão"
            + (f", árvore {manifesto['arvore'][:12]}" if manifesto["arvore"] else
               ", árvore sem impressão (não é git)")
            + f". Ver `desde-aprovacao {atividade.meta['id']}`.")


def ultimo_portao(agents: Path, ident: str, step: int | None) -> tuple[Path, dict] | None:
    base = portoes_dir(agents, ident)
    if not base.is_dir():
        return None
    for pasta in sorted((d for d in base.glob("[0-9]*") if d.is_dir()), reverse=True):
        try:
            manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if step is None or manifesto.get("step") == step:
            return pasta, manifesto
    return None


def _texto(arquivo: Path) -> list[str] | None:
    try:
        return arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return None


def cmd_desde_aprovacao(args: argparse.Namespace) -> int:
    """O que mudou nos artefatos e na árvore desde a saída do último portão.

    Sem `--portao`: o último registro do portão em que a atividade está; se ela
    nunca saiu dele, o último de qualquer portão. É o caso do portão 7 na
    primeira passagem: a comparação é com a spec que o 5 aprovou.
    """
    agents = resolve_agents_dir()
    atividade = Atividade.ler(activity_path(agents, args.id))
    ident = atividade.meta["id"]
    achado = None
    if args.portao is not None:
        achado = ultimo_portao(agents, ident, args.portao)
    else:
        if atividade.step in STEPS_DE_PORTAO:
            achado = ultimo_portao(agents, ident, atividade.step)
        achado = achado or ultimo_portao(agents, ident, None)
    if achado is None:
        alvo = f"do portão {args.portao}" if args.portao is not None else "de portão nenhum"
        print(f"{ident}: a atividade ainda não saiu {alvo}; nada a comparar. "
              "É a primeira passagem: o portão olha tudo.")
        return 0
    pasta, m = achado
    desfecho = "aprovado" if m.get("desfecho") == "aprovado" else "devolvido"
    print(f"{ident}: desde o portão {m.get('step')} {desfecho} em {m.get('quando')} "
          f"(registro {pasta.name})\n")

    antes = {(a["tipo"], a["caminho"]): a for a in m.get("artefatos", [])}
    agora_ = [(str(a[0]), str(a[1])) for a in atividade.artefatos if len(a) >= 2]
    contagem = {"igual": 0, "mudou": 0, "novo": 0, "saiu": 0, "sem-prova": 0}
    for tipo, caminho in agora_:
        velho = antes.get((tipo, caminho))
        arquivo = arquivo_do_artefato(agents, atividade, caminho)
        if velho is None:
            contagem["novo"] += 1
            print(f"  [novo]    {tipo}: {caminho}")
            continue
        if not parece_caminho_de_arquivo(caminho):
            contagem["sem-prova"] += 1
            print(f"  [?]       {tipo}: {caminho} — não é arquivo: o conteúdo "
                  "pode ter mudado sem o endereço mudar")
            continue
        if arquivo is None:
            contagem["sem-prova"] += 1
            print(f"  [?]       {tipo}: {caminho} — "
                  + ("sumiu da árvore" if velho.get("sha256") else
                     "não existe, nem no portão nem agora"))
            continue
        if not velho.get("sha256") and velho.get("motivo") != "ausente":
            contagem["sem-prova"] += 1
            print(f"  [?]       {tipo}: {caminho} — sem impressão no registro "
                  f"({velho.get('motivo', '')})")
            continue
        if velho.get("sha256") and _sha256(arquivo) == velho["sha256"]:
            contagem["igual"] += 1
            print(f"  [igual]   {tipo}: {caminho}")
            continue
        contagem["mudou"] += 1
        print(f"  [mudou]   {tipo}: {caminho}")
        # Ausente no portão e presente agora: tudo nele é novo.
        linhas_antes = ([] if velho.get("motivo") == "ausente" else
                        _texto(pasta / velho["copia"]) if velho.get("copia") else None)
        linhas_agora = _texto(arquivo)
        if linhas_antes is None or linhas_agora is None:
            print("            (sem cópia de texto para comparar: só a impressão mudou)")
            continue
        diff = list(difflib.unified_diff(linhas_antes, linhas_agora,
                                         f"portão {m.get('step')}", "agora", n=2))
        mostrar = diff if args.completo else diff[:LINHAS_DE_DIFF]
        for linha in mostrar:
            print("            " + linha.rstrip("\n"))
        if len(diff) > len(mostrar):
            print(f"            … mais {len(diff) - len(mostrar)} linha(s); "
                  "`--completo` mostra tudo.")
    for (tipo, caminho), velho in antes.items():
        if (tipo, caminho) not in agora_:
            contagem["saiu"] += 1
            print(f"  [saiu]    {tipo}: {caminho}")

    raiz = Path(m.get("raiz") or _raiz_do_portao(agents, atividade))
    arvore_antes = m.get("arvore") or ""
    print()
    if not arvore_antes or not raiz.is_dir():
        print("  Código: sem impressão da árvore no registro; não sei o que mudou.")
    else:
        arvore_agora = arvore_de(raiz)
        if arvore_agora == arvore_antes:
            print("  Código: a árvore é a mesma do portão.")
        else:
            base_diff = arvore_antes
            if subprocess.run(["git", "cat-file", "-e", arvore_antes], cwd=raiz,
                              capture_output=True).returncode != 0:
                base_diff = m.get("commit") or ""
            stat = _git(["diff", "--stat", base_diff, arvore_agora], raiz) if base_diff else ""
            print("  Código: a árvore mudou desde o portão"
                  + ("" if base_diff == arvore_antes else
                     " (a impressão foi recolhida pelo git; comparando com o commit de então)")
                  + ".")
            for linha in (stat or "(sem diff legível)").splitlines():
                print("    " + linha)
            if base_diff:
                print(f"    Diff inteiro: git -C {raiz} diff {base_diff[:12]} {arvore_agora[:12]}")
    print(f"\n  {contagem['mudou']} mudou, {contagem['novo']} novo, {contagem['saiu']} saiu, "
          f"{contagem['igual']} igual" + (f", {contagem['sem-prova']} sem prova"
                                          if contagem["sem-prova"] else "") + ".")
    return 0


def conferir_resumo(agents: Path, atividade: "Atividade", raiz: Path) -> int:
    """Diz, sem rodar nada, se o `resumo.json` ainda vale para esta árvore."""
    ident = atividade.meta["id"]
    alvo = gates_dir(agents, ident) / "resumo.json"
    try:
        resumo = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"{ident}: sem resumo dos portões em {alvo}. Rode-os.")
        return 1
    agora_arvore = arvore_de(raiz)
    velhos, faltando = [], []
    for nome, _ in gates_declarados(agents):
        item = resumo.get(nome)
        if item is None:
            faltando.append(nome)
        elif not agora_arvore or item.get("arvore") != agora_arvore:
            velhos.append(nome)
    for nome, item in resumo.items():
        marca = ("velho" if nome in velhos else "vale")
        print(f"  [{marca}] {nome}: {item.get('veredicto')} — saída "
              f"{item.get('codigo')} em {item.get('quando')} — log {item.get('log')}")
    for nome in faltando:
        print(f"  [falta] {nome}: declarado e nunca rodado")
    if velhos or faltando:
        print(f"{ident}: o resumo NÃO vale para a árvore de agora"
              + ("" if agora_arvore else " (não é repositório git)")
              + f": {', '.join(velhos + faltando)}. Rode esses de novo.")
        return 1
    print(f"{ident}: o resumo vale para a árvore de agora ({agora_arvore[:12]}).")
    return 0


def cmd_gates(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    path = activity_path(agents, args.id)
    atividade = Atividade.ler(path)
    if args.conferir:
        return conferir_resumo(agents, atividade,
                               _raiz_dos_gates(atividade, args.raiz))
    declarados = gates_declarados(agents)
    if args.so:
        pedidos = [n.strip() for n in args.so.split(",") if n.strip()]
        desconhecidos = [n for n in pedidos if n not in dict(declarados)]
        if desconhecidos:
            raise FlowStateError(
                f"portão não declarado em [gates]: {', '.join(desconhecidos)}. "
                f"Declarados: {', '.join(n for n, _ in declarados) or 'nenhum'}.")
        declarados = [(n, c) for n, c in declarados if n in pedidos]
    if not declarados:
        print(f"{args.id}: o projeto não declara portão em [gates] — nada a rodar.")
        print("  Isso é um achado por si só: o step 9 vai dizer que não há portão.")
        return 0

    raiz = _raiz_dos_gates(atividade, args.raiz)
    try:
        import config as C
        workers = str(C.obter("recursos.max_workers_teste", 2, agents))
        limite = int(C.obter("recursos.segundos_por_gate",
                             SEGUNDOS_POR_GATE_PADRAO, agents))
    except Exception:
        workers, limite = "2", SEGUNDOS_POR_GATE_PADRAO
    pasta = gates_dir(agents, args.id)
    pasta.mkdir(parents=True, exist_ok=True)
    print(f"{args.id}: {len(declarados)} portão(ões) em {raiz}, um por vez")

    resultados: list[tuple[str, str, str]] = []
    # `--so test` acrescenta ao resumo; não apaga o lint que rodou antes.
    try:
        resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        resumo = {}
    arvore = arvore_de(raiz)
    for nome, comando in declarados:
        # `{max_workers}` no comando declarado é onde o limite entra. O script
        # não injeta flag em comando alheio: `--maxWorkers` no jest é
        # `--max-workers` noutro runner, e chutar errado quebra o portão.
        comando = comando.replace("{max_workers}", workers)
        print(f"\n  [{nome}] {comando}")
        codigo, saida, segundos = _rodar_gate(comando, raiz, limite)
        log = pasta / f"{nome}.log"
        log.write_text(saida[-BYTES_DE_LOG:], encoding="utf-8")
        # Só no vermelho: verde não tem o que separar, e a catraca sem base
        # gravaria `exigida` num portão que passou.
        catraca = (_pela_catraca(agents, args.id, nome, log, raiz)
                   if codigo not in (0, None) else None)
        if codigo is None:
            veredicto = "falhou"
            detalhe = f"estourou {limite}s sem terminar"
        elif codigo == 0:
            veredicto, detalhe = "ok", f"saída 0 em {segundos:.0f}s"
        elif catraca == 0:
            # Vermelho que a catraca reconhece inteiro como da base: não é
            # desta entrega, e reprovar por ele mandaria caçar defeito alheio.
            veredicto = "ok"
            detalhe = (f"saída {codigo} em {segundos:.0f}s, só falha "
                       "conhecida da catraca")
        else:
            veredicto = "falhou"
            detalhe = f"saída {codigo} em {segundos:.0f}s" + (
                ", falha nova na catraca" if catraca == 1 else "")
        try:
            curto = log.relative_to(agents)
        except ValueError:
            curto = log
        detalhe += f" — log {curto}"
        if nome == "test":
            _casos_verdes(agents, args.id, log, codigo, raiz)
        print(f"  [{nome}] {veredicto}: {detalhe}")
        if veredicto == "falhou":
            cauda = [l for l in saida.splitlines() if l.strip()][-15:]
            print("\n".join("      " + l for l in cauda))
        resultados.append((f"gate:{nome}", veredicto, detalhe))
        resumo[nome] = {"comando": comando, "codigo": codigo,
                        "segundos": round(segundos, 1), "veredicto": veredicto,
                        "catraca": catraca, "quando": agora(),
                        "raiz": str(raiz), "log": str(log), "arvore": arvore}

    (pasta / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    with trava(agents):
        atividade = Atividade.ler(path)
        for ferramenta, veredicto, detalhe in resultados:
            atividade.conferencias.append(
                (agora(), ferramenta, veredicto, uma_linha(detalhe)))
        atividade.meta["atualizado_em"] = agora()
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    relatar(avisos)

    vermelhos = [f.split(":", 1)[1] for f, v, _ in resultados if v == "falhou"]
    print()
    print(f"{args.id}: " + (f"VERMELHO em {', '.join(vermelhos)}" if vermelhos
                             else "portões verdes") + f". Resumo em {pasta / 'resumo.json'}")
    faltas = falta_para_sair_do_8(atividade, agents)
    if faltas and atividade.step == 8:
        print("  Ainda segura a passagem para o step 9:")
        for f in faltas:
            print(f"    - {f}")
    print()
    print("O que isto NÃO prova: que os testes provam o requisito. Prova que o")
    print("comando declarado devolveu esse código nesta árvore, agora.")
    return 1 if vermelhos else 0


def cmd_concluir(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        path = activity_path(agents, args.id)
        atividade = Atividade.ler(path)

        if atividade.meta.get("status") == STATUS_CONCLUIDO:
            raise FlowStateError(f"A atividade {args.id} já está concluída.")
        ultimo = atividade.trilha[-1]
        if atividade.step != ultimo:
            if not args.forcar:
                raise FlowStateError(
                    f"A atividade está em {rotulo(atividade.step)}; o último "
                    f"step da trilha é {rotulo(ultimo)}. Use --forcar se ela "
                    "foi encerrada antes do fim, e explique em --nota."
                )
            if not args.nota:
                raise FlowStateError(
                    "--forcar exige --nota: encerrar antes do fim da trilha sem "
                    "dizer por quê apaga a única explicação que restaria."
                )

        trilha = atividade.meta.get("trilha", "")
        abertas = pendencias(atividade)
        travam = [(f, v, d) for f, v, d in abertas
                  if segura_o_concluir(v, trilha, f)]
        achados = [(f, v, d) for f, v, d in abertas
                   if not segura_o_concluir(v, trilha, f)]
        # No risco alto, a frente de segurança é a que não pode sair por
        # `nao-coberta`: foi para isso que a pessoa marcou o risco.
        if atividade.meta.get("risco") == "alto":
            dimensao = CONFERENCIA_DO_RISCO_ALTO[0]
            ultima = [linha for linha in atividade.conferencias
                      if len(linha) >= 3 and linha[1] == dimensao]
            if ultima and ultima[-1][2] == "nao-coberta":
                travam.append((dimensao, "nao-coberta",
                               "risco alto, e a frente de segurança não "
                               "cobriu: rode-a, ou baixe o risco com `risco "
                               f"{args.id} --nivel padrao --nota '<por quê>'`"))

        if travam and not args.forcar:
            linhas = "\n".join(
                f"    {ferramenta}: {detalhe or 'sem detalhe'}"
                for ferramenta, _, detalhe in travam)
            # A frase envelheceu na 2.26.0 e foi corrigida na 2.26.2: ela
            # dizia "EXIGIDA e não fechou, OU FECHOU REPROVANDO" em toda
            # trilha, e desde a 2.26.0 reprovar não segura mais nada na
            # `revisao`. Quem lesse ali iria procurar um vermelho que não está
            # travando nada.
            causa = ("Uma delas foi EXIGIDA e não fechou."
                     if trilha == "revisao" else
                     "Uma delas foi EXIGIDA e não fechou, ou fechou reprovando.")
            so_do_risco = all(v == "nao-coberta" for _, v, _ in travam)
            raise FlowStateError(
                "Conferência mecânica pendente:\n" + linhas + "\n\n"
                + ("  No risco alto a frente de segurança não sai por "
                   "`nao-coberta`. "
                   if so_do_risco else
                   "  " + causa + " "
                   "Rode a ferramenta e registre o resultado, ou declare a "
                   "dimensão como `nao-coberta` — que passa e fica escrita. ")
                + "`--forcar` com `--nota` também encerra, e deixa dito por quê."
            )

        # O vermelho da `revisao` não trava, mas também não passa calado: sem a
        # nota, o que a revisão ACHOU sairia do fluxo sem endereço, e a próxima
        # pessoa a abrir a atividade veria `falhou` sem saber onde foi parar.
        if achados and not args.nota:
            linhas = "\n".join(
                f"    {ferramenta}: {detalhe or 'sem detalhe'}"
                for ferramenta, _, detalhe in achados)
            raise FlowStateError(
                "Esta revisão fecha com conferência em `falhou`:\n" + linhas
                + "\n\n"
                "  Na trilha `revisao` isso NÃO é dívida: é o produto. Ela não "
                "conserta, não commita e não faz push — não existe caminho que "
                "torne isso verde daqui.\n"
                "  Por isso `--nota` é obrigatória, e ela precisa dizer ONDE o "
                "achado foi publicado: número do PR, da thread, do card.\n\n"
                "  NÃO re-registre a conferência como `ok` para o comando "
                "passar. Isso apagaria do histórico o achado que a revisão "
                "existiu para produzir."
            )

        agora_str = agora()
        if atividade.step in STEPS_DE_PORTAO:
            atividade.history.append((agora_str, "portão gravado", registrar_portao(
                agents, atividade, atividade.step, "aprovado", agora_str)))
        atividade.meta["status"] = STATUS_CONCLUIDO
        atividade.meta["atualizado_em"] = agora_str
        atividade.meta["concluido_em"] = agora_str
        nota = args.nota or "Fluxo encerrado."
        if achados:
            # O vermelho entra no HISTÓRICO, e não só na nota de quem encerra:
            # a nota depende de alguém escrever, a linha abaixo não.
            nota += ("  ACHADOS QUE FECHARAM EM `falhou` — o produto desta "
                     "revisão: "
                     + "; ".join(f"{f} ({d})" if d else f
                                 for f, _, d in achados) + ".")
        atividade.history.append((agora_str, "concluída", nota))
        atividade.escrever(path)
        avisos = regenerar_indice(agents)
    atualizar_metricas(args.id)
    print(f"{args.id}: concluída.")
    marcar_no_board(agents, atividade)
    anexar_contrato(agents, atividade)
    publicar_metricas(indexar=True, trilha=trilha)
    relatar(avisos)
    return 0


def cmd_listar(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    atividades, avisos = carregar_todas(agents)
    if not atividades:
        print("Nenhuma atividade registrada.")
        relatar(avisos)
        return 0
    abertas = [a for a in atividades if a.meta["status"] != STATUS_CONCLUIDO]
    concluidas = [a for a in atividades if a.meta["status"] == STATUS_CONCLUIDO]
    if abertas:
        print("Em andamento:\n")
        for a in abertas:
            print(f"  {a.meta['id']:<12} {rotulo(a.step):<48} "
                  f"{a.meta.get('titulo', '')}")
    if concluidas and getattr(args, "todas", False):
        print("\nConcluídas:\n")
        for a in concluidas:
            print(f"  {a.meta['id']:<12} {a.meta.get('titulo', '')}")
    elif concluidas:
        print(f"\n({len(concluidas)} concluída(s); use --todas para listar.)")
    relatar(avisos)
    return 0


# --------------------------------------------------------------------------
# O percurso: voltas, portões e tempo, lidos do Histórico
# --------------------------------------------------------------------------

# A nota da devolução humana diz se ela é por escopo — o `FLOW.md` exige isso,
# porque é o que reinicia o contador de voltas. A métrica lê a mesma palavra
# que a skill lê, e não uma bandeira nova: duas fontes para o mesmo fato
# divergem, e a nota já é obrigatória.
DEVOLUCAO_POR_ESCOPO = re.compile(r"\bescopo\b", re.I)

# A linha que o `iniciar --reabrir` grava começa assim, sempre. Sem a marca,
# uma reabertura com nota própria se leria como volta ao step 1.
MARCA_DE_REABERTURA = "Reaberta"


def _instante(texto: str) -> datetime | None:
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def percurso(history: list[tuple[str, ...]]) -> dict:
    """O caminho que a atividade fez, contado a partir do Histórico.

    **Por que isto existe.** Até a 2.56.0 as voltas só existiam como texto: o
    step 9 descobria em que volta estava contando linhas, e nenhum código
    somava. A métrica sabia quanto custou e não sabia **por onde** o custo
    passou — quantas vezes o 9 devolveu ao 8, quantas vezes o portão 5
    devolveu a spec, quanto tempo cada step ficou aberto.

    Só as linhas de TRANSIÇÃO contam: as de step (`3 · Analista…`) e a de
    `concluída`. `lugar corrigido` e `artefato retirado` são eventos, não
    passos, e contá-los como marco partiria o tempo de um step em dois.

    Três leituras, e a fronteira entre elas é o que dá valor ao número:

    - **volta** é retrocesso a partir de step de IA (9→8, 4→3) — devolução por
      defeito, o laço fazedor↔revisor;
    - **devolução** é retrocesso a partir de portão humano (5→3, 10→8), com o
      motivo lido da nota: `escopo` quando ela diz, `defeito` quando não;
    - **reabertura** é o que vem depois de `concluída`, ou a linha marcada
      pelo `iniciar --reabrir`. Não é volta: a entrega já tinha sido aceita.

    O que NÃO prova: tempo é DECORRIDO entre transições, não trabalho — um
    step aberto enquanto a sessão fazia outra coisa aparece longo sem ter
    sido. E o motivo da devolução é o que a nota declarou; nota sem a palavra
    `escopo` conta como defeito, mesmo que a pessoa quisesse mais.
    """
    marcos: list[tuple[datetime | None, int | None, str]] = []
    for linha in history:
        quando, onde, nota = (list(linha) + ["", "", ""])[:3]
        numero = onde.split(" ")[0]
        if numero.isdigit() and int(numero) in STEPS:
            marcos.append((_instante(quando), int(numero), nota))
        elif onde == "concluída":
            marcos.append((_instante(quando), None, nota))

    voltas: dict[str, int] = {}
    devolucoes: list[dict] = []
    portoes: dict[str, dict[str, int]] = {}
    por_step: dict[str, dict[str, float]] = {}
    reaberturas = 0
    tempo = {"ia": 0.0, "humano": 0.0}

    def portao(step: int) -> dict[str, int]:
        return portoes.setdefault(str(step), {"aprovado": 0, "devolvido": 0})

    anterior: int | None = None
    encerrada = False
    for i, (instante, step, nota) in enumerate(marcos):
        # O tempo do marco ANTERIOR fecha aqui. Medido sobre o marco que
        # começa, e não sobre o que termina, para o último step aberto ficar
        # de fora: ele ainda não acabou, e "até agora" não é duração.
        if i and marcos[i - 1][1] is not None:
            inicio, step_anterior = marcos[i - 1][0], marcos[i - 1][1]
            if inicio and instante and instante >= inicio:
                segundos = (instante - inicio).total_seconds()
                tipo = "humano" if STEPS[step_anterior]["tipo"] == "humano" else "ia"
                tempo[tipo] += segundos
                alvo = por_step.setdefault(str(step_anterior),
                                           {"entradas": 0, "segundos": 0.0})
                alvo["segundos"] += segundos

        if step is None:
            if anterior is not None and STEPS[anterior]["tipo"] == "humano":
                portao(anterior)["aprovado"] += 1
            encerrada = True
            anterior = None
            continue
        reaberta = encerrada or nota.startswith(MARCA_DE_REABERTURA)
        encerrada = False
        if anterior is None or reaberta:
            reaberturas += int(reaberta)
            por_step.setdefault(str(step), {"entradas": 0, "segundos": 0.0})
            por_step[str(step)]["entradas"] += 1
            anterior = step
            continue
        if step == anterior:
            # Linha extra no mesmo step (cards complementares, aviso da trilha,
            # a baseline do 9): não é entrada nova.
            continue
        por_step.setdefault(str(step), {"entradas": 0, "segundos": 0.0})
        por_step[str(step)]["entradas"] += 1
        humano = STEPS[anterior]["tipo"] == "humano"
        if step > anterior:
            if humano:
                portao(anterior)["aprovado"] += 1
        elif humano:
            portao(anterior)["devolvido"] += 1
            devolucoes.append({
                "de": anterior, "para": step,
                "motivo": "escopo" if DEVOLUCAO_POR_ESCOPO.search(nota) else "defeito",
            })
        else:
            par = f"{anterior}→{step}"
            voltas[par] = voltas.get(par, 0) + 1
        anterior = step

    for dados in por_step.values():
        dados["segundos"] = round(dados["segundos"], 1)
    return {
        "voltas": voltas,
        "voltas_total": sum(voltas.values()),
        "devolucoes": devolucoes,
        "portoes": portoes,
        "reaberturas": reaberturas,
        "tempo_s": {k: round(v, 1) for k, v in tempo.items()},
        "por_step": dict(sorted(por_step.items(), key=lambda kv: int(kv[0]))),
    }


def cmd_tempo(args: argparse.Namespace) -> int:
    """Onde o tempo foi, step a step.

    O fluxo tem dez etapas e três portões humanos. Se ele vira gargalo, é aqui
    que se vê — e a resposta útil separa o que a IA gastou do que ficou
    esperando uma pessoa, porque são problemas diferentes com soluções
    diferentes.
    """
    agents = resolve_agents_dir()
    atividade = Atividade.ler(activity_path(agents, args.id))
    marcos = []
    for quando, rotulo_step, nota in atividade.history:
        # Evento não é marco: `portão gravado` sai no mesmo segundo da
        # transição e viraria uma linha de zero segundos sem tipo.
        if not (rotulo_step.split(" ")[0].isdigit() or rotulo_step == "concluída"):
            continue
        try:
            t = datetime.strptime(quando, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                t = datetime.strptime(quando, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
        marcos.append((t, rotulo_step, nota))

    if len(marcos) < 2:
        print(f"{args.id}: histórico curto demais para medir "
              f"({len(marcos)} marco(s)).")
        return 0

    print(f"{atividade.meta['id']} — {atividade.meta.get('titulo', '')}")
    print(f"trilha {atividade.meta.get('trilha')}\n")
    print(f"  {'step':<46} {'duração':>10}  {'tipo':<7}")
    print(f"  {'-' * 46} {'-' * 10}  {'-' * 7}")

    total_ia = total_humano = 0.0
    for (inicio, rotulo_step, _), (fim, _, _) in zip(marcos, marcos[1:]):
        segundos = (fim - inicio).total_seconds()
        numero = rotulo_step.split(" ")[0]
        tipo = "?"
        # O histórico guarda o rótulo do dia em que a transição aconteceu. Ele
        # envelhece: um step renomeado deixa linhas antigas com o nome velho, e
        # a tabela passa a listar o mesmo trabalho com dois nomes. Quando o
        # número resolve, o cargo vem de STEPS.
        legivel = rotulo_step
        if numero.isdigit() and int(numero) in STEPS:
            tipo = STEPS[int(numero)]["tipo"]
            legivel = rotulo(int(numero))
        if tipo == "humano":
            total_humano += segundos
        else:
            total_ia += segundos
        print(f"  {legivel[:46]:<46} {_dur(segundos):>10}  {tipo:<7}")

    total = total_ia + total_humano
    print(f"\n  {'IA':<46} {_dur(total_ia):>10}  "
          f"{total_ia / total * 100:.0f}%" if total else "")
    print(f"  {'espera humana':<46} {_dur(total_humano):>10}  "
          f"{total_humano / total * 100:.0f}%" if total else "")
    print(f"  {'total':<46} {_dur(total):>10}")
    print("\n  Espera humana longa não é lentidão do fluxo — é o portão "
          "fazendo o trabalho dele.")
    print("  Tempo de IA longo é o que vale investigar.")
    print("\n  Atenção: isto mede tempo DECORRIDO entre as transições, não "
          "tempo de trabalho.")
    print("  Um step que ficou aberto enquanto a sessão fazia outra coisa "
          "aparece longo\n  sem ter sido. Para o portão humano a medida é "
          "exata — esperar É o trabalho dele.")
    imprimir_percurso(percurso(atividade.history))
    return 0


def imprimir_percurso(p: dict) -> None:
    """As voltas e os portões, na mesma tela do tempo — é a mesma pergunta:
    por onde o trabalho passou, e quantas vezes."""
    print("\n  Percurso")
    voltas = ", ".join(f"{par} ×{n}" for par, n in p["voltas"].items())
    print(f"    voltas de correção: {voltas or 'nenhuma'}")
    for d in p["devolucoes"]:
        print(f"    portão {d['de']} devolveu ao step {d['para']} "
              f"(por {d['motivo']})")
    for step, v in p["portoes"].items():
        print(f"    portão {step}: {v['aprovado']} aprovação(ões), "
              f"{v['devolvido']} devolução(ões)")
    if p["reaberturas"]:
        print(f"    reaberta {p['reaberturas']} vez(es)")


def _dur(segundos: float) -> str:
    if segundos < 90:
        return f"{segundos:.0f}s"
    if segundos < 5400:
        return f"{segundos / 60:.1f}min"
    return f"{segundos / 3600:.1f}h"


def cmd_indice(args: argparse.Namespace) -> int:
    agents = resolve_agents_dir()
    with trava(agents):
        avisos = regenerar_indice(agents)
    print(f"Índice regerado em {agents / INDEX_NAME}")
    relatar(avisos)
    return 0


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------


def carregar_todas(agents: Path) -> tuple[list[Atividade], list[str]]:
    """Read every activity, reporting — never raising on — the broken ones.

    One hand-edited file must not take down a listing that spans the others,
    and must not stop an unrelated activity from advancing.
    """
    atividades, avisos = [], []
    for path in sorted(atividades_dir(agents).glob("*.md")):
        try:
            atividades.append(Atividade.ler(path))
        except FlowStateError as exc:
            avisos.append(str(exc))
        except Exception as exc:  # malformed beyond what validation predicts
            avisos.append(f"{path.name}: ilegível ({exc.__class__.__name__}).")
    return atividades, avisos


def relatar(avisos: list[str]) -> None:
    for aviso in avisos:
        print(f"  aviso: {aviso}", file=sys.stderr)


def regenerar_indice(agents: Path) -> list[str]:
    """Rebuild the human-facing index from the activity files.

    Derived, never authoritative: deleting it loses nothing. Call inside the
    lock — it reads every activity and writes one file.
    """
    atividades, avisos = carregar_todas(agents)
    abertas = [a for a in atividades if a.meta["status"] != STATUS_CONCLUIDO]
    concluidas = [a for a in atividades if a.meta["status"] == STATUS_CONCLUIDO]

    linhas = [
        "# Atividades em andamento com IA",
        "",
        "Arquivo **gerado** por `elcamargo-flow/tools/flow-state/flow_state.py`.",
        "Não edite à mão: a fonte de verdade é `atividades/<id>.md`.",
        "Para reconstruir: `flow_state.py indice`.",
        "",
        f"Atualizado em {agora()}.",
        "",
        "## Em andamento",
        "",
    ]
    if abertas:
        linhas += ["| Atividade | Step | Trilha | Branch | Título |",
                   "| --- | --- | --- | --- | --- |"]
        for a in abertas:
            linhas.append("| {} | {} | {} | {} | {} |".format(*(
                escapar_celula(v) for v in (
                    a.meta["id"], rotulo(a.step), a.meta["trilha"],
                    a.meta.get("branch", ""), a.meta.get("titulo", "")))))
    else:
        linhas.append("_Nenhuma._")

    linhas += ["", "## Concluídas", ""]
    if concluidas:
        linhas += ["| Atividade | Título | Encerrada em |", "| --- | --- | --- |"]
        for a in concluidas:
            linhas.append("| {} | {} | {} |".format(*(
                escapar_celula(v) for v in (
                    a.meta["id"], a.meta.get("titulo", ""),
                    a.meta.get("concluido_em",
                               a.meta.get("atualizado_em", ""))))))
    else:
        linhas.append("_Nenhuma._")

    if avisos:
        linhas += ["", "## Arquivos ilegíveis", ""]
        linhas += [f"- {a}" for a in avisos]
    linhas.append("")

    escrever_atomico(agents / INDEX_NAME, "\n".join(linhas))
    return avisos


def rotulo(step: int | None) -> str:
    """`3 · Analista de Sistema` — o cargo, que é o que se lê."""
    return "—" if step is None else f"{step} · {STEPS[step]['cargo']}"


def rotulo_com_endereco(step: int) -> str:
    """`3 · Analista de Sistema  (elcamargo-system-analyst)`.

    Para onde o endereço é acionável: quem lê precisa saber o que rodar, e o
    cargo sozinho não diz. Nos steps humanos não há endereço a mostrar.
    """
    dados = STEPS[step]
    if dados["tipo"] == "humano":
        return f"{step} · {dados['cargo']}"
    return f"{step} · {dados['cargo']}  ({dados['nome']})"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flow_state.py",
        description="Estado das atividades no fluxo de desenvolvimento com IA.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("caminho", help="imprime o .agents resolvido")
    s.set_defaults(func=cmd_caminho)

    s = sub.add_parser("fluxo", help="lista os steps e as trilhas")
    s.add_argument("--todos", action="store_true",
                   help="mostra também os steps desligados no projeto")
    s.set_defaults(func=cmd_fluxo)

    s = sub.add_parser("iniciar", help="abre uma atividade")
    s.add_argument("id", help="número do card, ou um identificador sem card")
    s.add_argument("--titulo", required=True)
    s.add_argument("--trilha", default="completa", choices=sorted(TRILHAS))
    s.add_argument("--risco", default="", choices=["", *RISCOS],
                   help="proposto pelo step 1 a partir do checklist do `fluxo`, "
                        "confirmado pela pessoa")
    s.add_argument("--superficies", default="",
                   help="as do checklist que a mudança toca, separadas por "
                        "vírgula: " + ", ".join(SUPERFICIES_DE_RISCO))
    s.add_argument("--branch", default="",
                   help="quando o lugar JÁ é conhecido; sem ela grava PENDENTE, "
                        "que o primeiro `avancar` de dentro da árvore resolve")
    s.add_argument("--worktree", default="",
                   help="idem, para a árvore")
    s.add_argument("--nota", default="")
    s.add_argument("--complementares", nargs="*", default=[], metavar="ID",
                   help="cards que este trabalho fecha junto com o principal")
    s.add_argument("--forcar", action="store_true",
                   help="abre mesmo quando a metade anterior não fechou; "
                        "exige --nota")
    s.add_argument("--corrige", default="", metavar="ID",
                   help="esta atividade corrige um defeito que escapou da "
                        "entrega de ID; a métrica conta o bug na origem")
    s.add_argument("--reabrir", action="store_true",
                   help="reabre uma atividade existente, preservando o histórico")
    s.set_defaults(func=cmd_iniciar)

    s = sub.add_parser("status", help="mostra uma atividade, ou todas se sem id")
    s.add_argument("id", nargs="?")
    s.add_argument("--todas", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("avancar", help="registra a entrada num step")
    s.add_argument("id")
    s.add_argument("--step", type=int, default=None,
                   help="destino; sem isso vai para o próximo da trilha")
    s.add_argument("--nota", default="")
    s.add_argument("--trilha", default="", choices=["", *sorted(TRILHAS)],
                   help="muda a trilha; exige --forcar")
    s.add_argument("--forcar", action="store_true",
                   help="permite retroceder, pular step ou sair da trilha; "
                        "exige --nota")
    s.set_defaults(func=cmd_avancar)

    s = sub.add_parser("risco", help="muda o risco da atividade; exige --nota")
    s.add_argument("id")
    s.add_argument("--nivel", required=True, choices=RISCOS)
    s.add_argument("--superficies", default=None,
                   help="a lista nova, separada por vírgula; vazia tira todas; "
                        "sem a bandeira, mantém a de antes")
    s.add_argument("--nota", default="")
    s.set_defaults(func=cmd_risco)

    s = sub.add_parser("corrigir",
                       help="muda a branch e o worktree da atividade")
    s.add_argument("id")
    s.add_argument("--branch", required=True)
    s.add_argument("--worktree", required=True)
    s.add_argument("--nota", default="", help="por que o lugar mudou")
    s.add_argument("--forcar", action="store_true",
                   help="aceita branch ou árvore que ainda não existem")
    s.set_defaults(func=cmd_corrigir)

    s = sub.add_parser("artefato", help="registra um artefato produzido")
    s.add_argument("id")
    s.add_argument("--tipo", required=True)
    s.add_argument("--caminho", required=True,
                   help="o caminho; com --substituir, o caminho NOVO")
    s.add_argument("--substituir", default="", metavar="CAMINHO_ANTIGO",
                   help="o arquivo foi renomeado: troca o registro no lugar, "
                        "em vez de acrescentar um segundo")
    s.add_argument("--retirar", action="store_true",
                   help="tira o registro; exige --nota")
    s.add_argument("--nota", default="",
                   help="por quê — obrigatória em --retirar")
    s.set_defaults(func=cmd_artefato)

    s = sub.add_parser("pf", help="declara o tamanho em pontos de função")
    s.add_argument("id")
    s.add_argument("--declarado", default=None,
                   help="o do analista, contado da especificação funcional")
    s.add_argument("--aferido", default=None,
                   help="o do step 9, contado da entrega; exige --inventario")
    s.add_argument("--inventario", default=None,
                   help="caminho do inventário que sustenta o --aferido")
    s.set_defaults(func=cmd_pf)

    s = sub.add_parser("conferencia",
                       help="registra o resultado de uma conferência mecânica")
    s.add_argument("id")
    s.add_argument("--ferramenta", required=True,
                   help="catraca, perfis, destino, honestidade, citacoes…")
    s.add_argument("--veredicto", required=True,
                   help=" | ".join(VEREDICTOS))
    s.add_argument("--detalhe", default="", help="uma linha dizendo o que saiu")
    s.set_defaults(func=cmd_conferencia)

    s = sub.add_parser("gates",
                       help="roda os portões de [gates] e grava cada código de saída")
    s.add_argument("id")
    s.add_argument("--so", default="", help="só estes portões, separados por vírgula")
    s.add_argument("--conferir", action="store_true",
                   help="não roda: diz se o resumo gravado vale para a árvore de agora")
    s.add_argument("--raiz", default="",
                   help="onde rodar; sem isso, a worktree da atividade")
    s.set_defaults(func=cmd_gates)

    s = sub.add_parser("desde-aprovacao",
                       help="o que mudou nos artefatos e no código desde a saída do último portão")
    s.add_argument("id")
    s.add_argument("--portao", type=int, choices=sorted(STEPS_DE_PORTAO),
                   help="comparar com o último registro deste portão")
    s.add_argument("--completo", action="store_true",
                   help=f"diff inteiro, sem o corte de {LINHAS_DE_DIFF} linhas")
    s.set_defaults(func=cmd_desde_aprovacao)

    s = sub.add_parser("concluir", help="encerra a atividade")
    s.add_argument("id")
    s.add_argument("--nota", default="")
    s.add_argument("--forcar", action="store_true",
                   help="encerra antes do último step da trilha")
    s.set_defaults(func=cmd_concluir)

    s = sub.add_parser("listar", help="lista as atividades")
    s.add_argument("--todas", action="store_true")
    s.set_defaults(func=cmd_listar)

    s = sub.add_parser("tempo", help="onde o tempo foi, step a step")
    s.add_argument("id")
    s.set_defaults(func=cmd_tempo)

    s = sub.add_parser("indice", help="regera Atividades_em_andamento_com_IA.md")
    s.set_defaults(func=cmd_indice)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FlowStateError as exc:
        print(f"erro: {exc}", file=sys.stderr)
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
    sys.exit(main())
