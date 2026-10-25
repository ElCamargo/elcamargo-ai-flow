---
name: elcamargo-ai-flow
description: "A porta do fluxo de desenvolvimento com IA. Recebe um ou mais cards do rastreador do projeto — issues do GitHub ou work items do Azure DevOps —, uma demanda em texto livre, ou nada — resolve onde a atividade está e entrega ao step certo, sem sair do fluxo. Use sempre que o usuário disser `/elcamargo-ai-flow`, passar números de card soltos, pedir para começar, retomar ou continuar uma atividade, perguntar `em que passo eu estava?`, ou descrever uma inconsistência que ele quer analisar e corrigir. É a forma normal de entrar; os steps têm skills próprias e não precisam ser chamados pelo nome."
---

# Elcamargo AI Flow — a porta

Você **não faz o trabalho**. Você descobre de que trabalho se trata, abre ou
retoma a atividade, e entrega ao step certo. Fazer é dos steps.

Esta skill existe porque o fluxo não tinha porta: a entrada era uma skill
chamada `elcamargo-board-git-management`, que é o nome do *serviço do step 1* e
não do que a pessoa quer. Quem quer o fluxo chamava um step, e o resto era sorte.

## Contrato

**Leia `$PACOTE/FLOW.md` antes de qualquer coisa.**

```bash
# Onde a FERRAMENTA mora. Três lugares possíveis, em ordem de confiança, e
# cada linha só corre se a anterior não achou uma pasta que existe:
#
#   1. `CLAUDE_PLUGIN_ROOT`  o harness diz. Não confie que ela SEMPRE chega
#      aqui — ela é documentada para hook, e para skill não está confirmado.
#   2. `.agents/elcamargo-flow`  o pacote copiado dentro do projeto.
#   3. o cache de plugin instalado, a versão mais alta.
#
# A terceira existe porque a primeira é incerta: sem ela, um projeto que só tem
# o plugin ficaria sem pacote se a variável não chegasse. Com ela, o pior caso
# é achar pelo caminho mais feio — e não falhar.
#
# O estado do PROJETO — `config.toml` e `atividades/` — continua no `.agents`
# nos três casos. Só a ferramenta se move.
PACOTE="${CLAUDE_PLUGIN_ROOT:-}"
[ -d "$PACOTE" ] || PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
[ -d "$PACOTE" ] || PACOTE="$(ls -d "$HOME"/.claude/plugins/cache/*/elcamargo-ai-flow/*/ 2>/dev/null | sort -V | tail -1)"
[ -d "$PACOTE" ] || { echo "não achei o elcamargo-ai-flow. Instale com: claude plugin install elcamargo-ai-flow@elcamargo" >&2; }
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

## 1. O que veio na sua mão

| O que o usuário passou | O que fazer |
| --- | --- |
| **Um card** — `/elcamargo-ai-flow 1061` | Abrir ou retomar essa atividade |
| **Vários cards** — `1061 1073 1064` | §2. Um deles vira o principal, e o PR fecha os três |
| **Texto livre** — *"analise o botão x da tela y"* | §3. Atividade sem card |
| **Nada** | `python3 $F status` e pergunte qual retomar |

**Antes de abrir qualquer coisa, veja se já existe:**

```bash
python3 $F status <id>
```

Se existir e estiver em andamento, **não abra de novo** — vá para §4.

## 2. Vários cards: um principal, e o PR fecha todos

A atividade tem **um dono**: a branch, o arquivo de estado e o nome saem dele.
Os complementares viajam junto porque a especificação é uma só e o PR fecha os
três.

**Leia os cards antes de perguntar.** Título, tipo, e o tamanho de cada um —
quantidade de requisitos, de anexos, e se algum é pai dos outros na hierarquia.
Perguntar sem essa informação transfere para a pessoa o trabalho que é seu.

Depois traga **um card de pergunta**, com os três nomeados:

> Qual é o principal — o dono da branch e do PR?
>
> - **1061** — *Inconsistência do botão de salvar* · 8 requisitos, 2 anexos
> - **1073** — *Ajuste do rótulo* · 1 requisito
> - **1064** — *Mensagem de erro genérica* · 2 requisitos

**Não decida por heurística.** "O maior" parece regra e não é: o card com mais
requisitos pode ser o acessório de um menor que muda o comportamento central.
Quem sabe é quem abriu os cards.

```bash
python3 $F iniciar 1061 --titulo '<título>' --trilha <trilha> \
    --complementares 1073 1064
```

**Diga em voz alta o que isso implica**, na mesma mensagem: um PR, três Work
items, e — se um dos três reprovar na revisão — **ou os três seguram, ou aquele
sai do PR**, e sair depois custa mais que separar antes.

## 3. Sem card

Gere um identificador local e siga. **Não crie card**: quem usa esta ferramenta
pode não ter permissão para isso, e criar por conta própria enche o board de
coisa que ninguém pediu.

```bash
python3 $F iniciar s-2026-08-31-botao-salvar --titulo '<o que a pessoa descreveu>' \
    --trilha curta
```

O identificador é `s-<data>-<assunto-curto>`. Se depois virar card, `iniciar
<numero> --reabrir` adota o número e preserva o histórico.

**A trilha aqui é quase sempre `curta`** — uma inconsistência vista na tela
raramente precisa de SDD de negócio. Confirme com a pessoa antes, porque a
trilha decide quantos steps rodam.

## 4. Entregar ao step, e não fazer o trabalho

```bash
python3 $F status <id>
```

Ele imprime o step atual e o **próximo, com o nome da skill**. Chame essa skill.

**Um step por contexto.** Se esta janela já rodou um step desta atividade, ou se
a pessoa pediu vários de uma vez (*"roda até o portão 5"*), não emende: dispare
cada step num subagente `elcamargo-ai-flow:elcamargo-step-runner`, **um por
disparo**, bloqueando. **Disparar não é terminar:** só abra o próximo depois de
ler o retorno do anterior, e pare no primeiro retorno que trouxer pendência
para a pessoa ou chegar a um portão. **Nunca um agente conduzindo vários
steps.** Regra do disparo em `$PACOTE/references/orchestration.md`. Quando a
linha `disparo:` do `flow_state` traz um `model`, passe-o na chamada.

**Retorno com 403 do guardrail** é contexto contaminado por CPF ou CNPJ, e não
falha passageira: não retome nem mande `SendMessage`. Rode `doc_mask.py
devolucoes --raiz <worktree>` e dispare contexto novo apontando a pasta que ele
imprimir, sem lê-la aqui. Em `$PACOTE/references/documents-in-context.md`.

É o que mais custa no fluxo, medido em 25 e 26/09/2026: 61% do custo aconteceu
com mais de 200 mil tokens de contexto, e os agentes mais caros eram
`general-purpose` emendando steps (*"Steps 2 a 4"*, até 917 mil). Cada resposta
relê o contexto inteiro.

**Quem orquestra não trabalha.** A janela que dispara não lê código, não abre
navegador e não espia frente com `tail` ou `ls`. Cada chamada dela relê tudo o
que já entrou, e as janelas mais caras (até 945 mil) faziam isso centenas de
vezes. **Atividade nova, janela nova:** uma janela medida passou por doze.

**Você para aqui.** A tentação é começar a analisar — é exatamente ela que
esvazia o fluxo. Uma porta que faz o trabalho do primeiro cômodo vira o
primeiro cômodo, e os outros nove deixam de existir.

Termine sempre assim, com o endereço à vista:

```
Atividade 1061 aberta — trilha completa, step 1 · Gestor da Atividade.
Fecha também: 1073, 1064.

Próximo:
    /elcamargo-board-git-management 1061
Modelo sugerido: Sonnet. O step 1 lê o card e devolve perguntas a você;
se ele ler o card errado, volte para o Opus.
```

## `/elcamargo-ai-flow orquestrar`: a janela que só distribui

Quem marca a janela é o hook, pela mensagem da pessoa, e as regras chegam
impressas por ele. Você não marca nem desmarca nada. A partir daí, o que é
trabalho de step (ler código, navegador, espiar frente, skill de step aqui
dentro) é **recusado** antes de rodar, e a recusa diz o que fazer no lugar.
Depois de cada compactação o hook devolve as regras e o `listar`. Rode
`python3 $F listar` e siga pelas regras. Só a pessoa sai do modo, com
`/elcamargo-ai-flow orquestrar sair`.

## Nunca faça

- Analisar, especificar ou implementar. Você é a porta.
- Abrir atividade sem antes conferir se ela já existe.
- Escolher o card principal sozinho.
- Criar card no board.
- Entregar ao step sem dizer, na mesma mensagem, onde a atividade está.

## Trilha `revisao`: você pode adiantar, mas não substitui o step 1

Ao receber um PR ou branch de outra pessoa é natural você já olhar a branch e
perceber em qual dos três casos ela está. **Adiantar é útil; entregar como
resposta pronta não é.**

Foi o que aconteceu no primeiro uso real da trilha: a porta descobriu, o step 1
recebeu a resposta em vez de procurá-la, e quem entrasse direto pelo step 1 não
descobriria nada. A descoberta é do step 1 e tem comando próprio —
`$PACOTE/tools/prior-work/prior_work.py`.

Se você adiantar, diga que é palpite e mande o step 1 confirmar pelo comando.
