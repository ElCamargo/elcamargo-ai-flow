---
name: elcamargo-activity-management
description: "Step 1 do fluxo de desenvolvimento com IA. Abre uma atividade: lê o item no rastreador do projeto — GitHub ou Azure DevOps, deduzido do remote — ou a demanda sem card, decide a trilha com o usuário, cria o arquivo de estado e entrega para o próximo step. Também é chamada pelos demais steps para commitar. Use quando o usuário quiser iniciar ou retomar uma atividade, perguntar `qual a próxima atividade?`, `em que passo eu estava?`, ou pedir para começar o fluxo num card. Delega ao gerenciador de Git do projeto tudo que ele já resolve."
---

# Step 1 · Gestor da Atividade

Abre a atividade e coloca o fluxo em movimento. Nada mais.

Esta skill **não implementa Git nem board**. O projeto já tem uma skill para
isso; esta acrescenta apenas o que é do fluxo: a trilha, o arquivo de estado e a
entrega ao próximo step.

## O ofício

- **`$PACOTE/references/check-first.md`** — **as três verificações que vêm antes de abrir a atividade.** Já foi rejeitado? Já está implementado? A alegação se confirma?
- **`$PACOTE/references/rejection-memory.md`** — o que o produto já decidiu não fazer, e como consultar.

## Antes de qualquer coisa

Leia `elcamargo-flow/FLOW.md`. Ele é o contrato — steps, trilhas e as
obrigações de todo step.

Resolva os caminhos assim, nunca por caminho relativo:

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

```bash
python3 $F status <id>
```

## Delegação

Leia `git.skill` do config do projeto:

```bash
python3 $C git.skill
```

**Se houver skill declarada, ela manda.** Invoque-a para ler o board, entender o
card, criar branch, commitar, abrir PR — tudo que ela já faz, do jeito dela,
com os portões dela. Não reimplemente, não contorne, não crie nome de branch por
conta própria.

Se não houver skill declarada, **você é o gerenciador de Git do projeto.** Não é
um toco: é o papel inteiro, e o comportamento padrão abaixo vale.

### Comportamento padrão, sem skill de projeto

**Descobrir a atividade.** Antes de perguntar qualquer coisa, veja onde os cards
deste projeto vivem — o pacote deduz do remote, e `[tracker] backend` no config
sobrepõe quando o board mora num host diferente do código:

```bash
python3 $C --rastreador
```

| Resposta | Como ler o item |
| --- | --- |
| `github` | `gh issue view <id> --comments` |
| `azure` | `az boards work-item show --id <id>` |
| nada, ou a CLI não autentica | Peça ao usuário o texto e os anexos |

`--comments` não é enfeite no GitHub: **o corpo da issue não é a issue.** É nos
comentários que o analista responde dúvida e diz "mudamos de ideia sobre o item
3" — a mesma regra que o §1 já cobra para o Azure, e a listagem de issues
também não os traz.

**Nunca invente o conteúdo de um card que você não leu.** Se o rastreador não
respondeu, diga isso e peça o texto; não deduza do título.

**Branch.** Antes de criar, veja o padrão que o repositório já usa:

```bash
git branch -a --sort=-committerdate | head -20
```

Siga o padrão que estiver ali — é a convenção real, mais confiável que qualquer
default. Sem padrão discernível, use `tipo/id_resumo_curto`, com `tipo` em
`feat`, `fix`, `chore`, `docs`, `refactor`. Confirme o nome com o usuário antes
de criar.

**Base.** Ramifique da branch padrão atualizada, nunca da branch em que você
está por acaso. Confirme qual é a padrão (`git symbolic-ref refs/remotes/origin/HEAD`)
e traga-a antes.

**Commit.** Veja o formato dos últimos commits (`git log --oneline -20`) e siga.
Sem padrão, use `tipo(escopo): assunto no imperativo`, com corpo explicando **por
que**, não o que — o diff já diz o que. Uma mudança coesa por commit.

**Nunca commite sem autorização daquela etapa**, nunca use `--force`, nunca faça
`reset`, `stash` ou `checkout` que descarte alteração que não é sua. Antes de
qualquer coisa, `git status --short`.

**PR.** Só quando o usuário pedir. Título igual ao do commit principal, corpo com
o que muda, como validar e o vínculo com o card. Você **nunca** faz merge nem
aprova: declara que está liberado e para.

## Fluxo

### 1. Descobrir a atividade

Delegue à skill de Git do projeto. O resultado precisa ser: um identificador,
um título, e o entendimento da demanda.

Uma demanda pode chegar **sem card** — pedido direto, ou algo que a análise
descobriu. Use um identificador descritivo (`ajuste-rodape-relatorio`) e siga
normalmente.

**Nunca crie card.** O board é do solicitante; abrir item lá é decisão de gestão.
Se a demanda parecer merecer card, diga isso ao usuário e deixe a decisão com
ele.

Uma atividade pode agrupar **mais de um card** quando os documentos se
complementam. Nesse caso use o card principal como identificador e registre os
demais no título e na nota.

**Leia os comentários do card, não só o corpo.** É onde o analista responde
dúvida, e é onde costuma estar "isso já foi resolvido no card X" ou "mudamos de
ideia sobre o item 3". Uma listagem de cards traz o corpo e **não traz os
comentários** — se você só olhou a listagem, não leu o card.

### 2. Verificar antes de abrir — portão

Siga `$PACOTE/references/check-first.md`, na ordem: rejeitado antes,
implementado, e — só para bug — a alegação se confirma.

O resultado **muda a trilha**, então ele vem antes de escolhê-la:

Comece pelo comando, que custa segundos e responde quase tudo:

```bash
python3 $PACOTE/tools/already-exists/already_exists.py --demanda <texto ou arquivo> --card <id>
```

| Resultado | O que fazer |
| --- | --- |
| Conceito já rejeitado | Mostre a decisão antiga e **pergunte se ainda vale**. Não recuse sozinho. |
| Já implementado | Aponte onde está. A atividade encerra antes de abrir. |
| **Complemento** de algo que já existe | **Declare a base e o delta na nota.** O escopo de todos os steps seguintes é o delta, não o módulo. |
| Bug não reproduz | Não abra trilha `curta`. Volte ao reportador com o que você tentou. |
| Sem detalhe para tentar | Pergunte antes de abrir. É o sinal mais forte de que falta informação. |
| Confirmado | Siga, e registre o caminho de código na nota de abertura. |

A verificação é **rasa**: "isto é real, e mais ou menos onde vive?" — não "qual é
a causa raiz?". Causa raiz é trabalho do step 8, depois de alguém decidir que
vale investir nele.

### 3. Verificar se a atividade já existe

```bash
python3 $F status <id>
```

Se a atividade já existe, **não reabra**. Diga em que step ela está e pergunte
se o usuário quer retomar dali. Retomar é o caso normal — foi para isso que o
estado existe.

### 4. Decidir a trilha — portão

Esta é a decisão que impede o fluxo de virar cerimônia. Apresente as três e
**pergunte**; não escolha sozinho.

**Não decore esta tabela — imprima a de verdade**, para nunca apresentar ao
usuário uma trilha que o script não tem:

```bash
python3 $F fluxo
```

| Trilha | Quando | Portões humanos no caminho |
| --- | --- | --- |
| `completa` | Feature nova, com análise de negócio a revisar | 5 (spec), 7 (telas), 10 (entrega) |
| `sistema` | Card claro, sem análise de negócio a revisar | 5, 7, 10 |
| `curta` | Bug, ajuste, correção pontual | 10 |

Diga quantos portões humanos a trilha tem: é isso que o usuário está aceitando
ao escolher. A `curta` pula os portões 5 e 7 porque não produz especificação nem
tela — não há o que validar neles.

Recomende uma, com o motivo, em uma linha. Espere a resposta.

**Se o desfecho do passo 2 foi complemento**, diga isso ao recomendar — e diga o
delta. A trilha pode continuar sendo a `completa`, mas o que cada step vai
produzir é muito menor, e o usuário precisa saber disso para julgar a
recomendação:

> Recomendo a `completa`: é análise de negócio nova. Mas é **complemento de
> `CAM-002`** — o delta são dois requisitos, então o step 2 revisa esses dois e
> o step 3 atualiza a SDD existente em vez de escrever outra.

### 5. Abrir a atividade

```bash
python3 $F iniciar <id> --titulo "<título>" --trilha <trilha> \
  --nota "<entendimento + resultado da verificação>"
```

### 6. Entregar ao próximo step

```bash
python3 $F avancar <id> --nota "<o que o próximo step recebe>"
```

Depois entregue o próximo step e pare:

```
Atividade 1042 aberta na trilha completa. Card lido, 3 anexos.

Próximo:
    /elcamargo-business-analysis-reviewer 1042
```
**Rode-o você não.** Quem dispara é o usuário, que assim vê a saída desta etapa
antes de gastar a próxima — e consegue apontar onde a cadeia quebrou quando ela
quebra.

**O próximo step roda em contexto novo**, sessão nova ou subagente, nunca esta
mesma janela. É por isso que o handoff é por arquivo: o step seguinte precisa
ler o artefato, não o raciocínio de quem o escreveu. Contexto herdado faz o
modelo responder ao próprio rastro em vez de responder à especificação.


## Quando outro step chama esta skill para commitar

Os demais steps chamam esta skill no fim do trabalho deles. Nesse caso:

1. Delegue o commit à skill de Git do projeto, com os portões dela.
2. Não mexa no estado da atividade — quem avança é o step que chamou.
3. Devolva o resultado e nada mais.

## Nunca faça

- Criar card, tarefa, bug ou qualquer work item no board.
- Mover card, mudar coluna, estado ou responsável.
- Completar, aprovar ou fazer merge de PR.
- Commit, push ou PR sem a autorização daquela etapa.
- Escolher a trilha sem perguntar.
- Abrir atividade de bug sem ter tentado reproduzir.
- Recusar um pedido por conta própria porque ele já foi rejeitado antes — mostre
  a decisão e pergunte.
- Executar o próximo step do fluxo.
- Tocar em alteração local que não é sua.
