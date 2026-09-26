---
name: elcamargo-ai-flow
description: "A porta do fluxo de desenvolvimento com IA. Recebe um ou mais cards do rastreador do projeto — issues do GitHub ou work items do Azure DevOps —, uma demanda em texto livre, ou nada — resolve onde a atividade está e entrega ao step certo, sem sair do fluxo. Use sempre que o usuário disser `/elcamargo-ai-flow`, passar números de card soltos, pedir para começar, retomar ou continuar uma atividade, perguntar `em que passo eu estava?`, ou descrever uma inconsistência que ele quer analisar e corrigir. É a forma normal de entrar; os steps têm skills próprias e não precisam ser chamados pelo nome."
---

# Elcamargo AI Flow — a porta

Você **não faz o trabalho**. Você descobre de que trabalho se trata, abre ou
retoma a atividade, e entrega ao step certo. Fazer é dos steps.

Esta skill existe porque o fluxo não tinha porta: a entrada era a skill do
step 1, que é o nome de um *serviço* e não do que a pessoa quer. Quem quer o
fluxo chamava um step, e o resto era sorte.

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
python3 $F iniciar 1061 --titulo "<título>" --trilha <trilha> \
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
python3 $F iniciar s-2026-08-31-botao-salvar --titulo "<o que a pessoa descreveu>" \
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

**Você para aqui.** A tentação é começar a analisar — é exatamente ela que
esvazia o fluxo. Uma porta que faz o trabalho do primeiro cômodo vira o
primeiro cômodo, e os outros nove deixam de existir.

Termine sempre assim, com o endereço à vista:

```
Atividade 1061 aberta — trilha completa, step 1 · Gestor da Atividade.
Fecha também: 1073, 1064.

Próximo:
    /elcamargo-activity-management 1061
```

## Nunca faça

- Analisar, especificar ou implementar. Você é a porta.
- Abrir atividade sem antes conferir se ela já existe.
- Escolher o card principal sozinho.
- Criar card no board.
- Entregar ao step sem dizer, na mesma mensagem, onde a atividade está.
