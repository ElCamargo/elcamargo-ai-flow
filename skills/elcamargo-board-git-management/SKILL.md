---
name: elcamargo-board-git-management
description: "Step 1 do fluxo de desenvolvimento com IA. Abre uma atividade: lê o card ou a demanda sem card, decide a trilha com o usuário, cria o arquivo de estado e entrega para o próximo step. Também é chamada pelos demais steps para commitar. Use quando o usuário quiser iniciar ou retomar uma atividade, perguntar `qual a próxima atividade?`, `em que passo eu estava?`, ou pedir para começar o fluxo num card. Lê o card em Azure Boards, GitHub, ou nenhum dos dois. Delega ao gerenciador de Git do projeto tudo que ele já resolve."
---

# Step 1 · Board e Git

Abre a atividade e coloca o fluxo em movimento. Nada mais.

Esta skill **não implementa Git nem board**. Ela acrescenta o que é do fluxo: a
trilha, o arquivo de estado e a entrega ao próximo step.

> [!atencao] Se a trilha é `revisao`, leia isto antes de qualquer coisa
> **`$PACOTE/references/foreign-review.md`.** Ela roda em worktree da branch do
> dev: não produz software, não commita, não faz push, não escreve no card
> dele. Ver a seção 4.

Quem lê o board é, nesta ordem: a **skill de Git do projeto**, se `[git] skill`
estiver declarada — ela manda, e faz do jeito dela; senão, o **leitor do
pacote**, que fala Azure Boards e GitHub e devolve a mesma forma dos dois:

```bash
python3 $PACOTE/tools/board/board.py ler <id>
python3 $PACOTE/tools/board/board.py comentarios <id>
python3 $PACOTE/tools/board/board.py listar
```

Com `[board] tipo = "nenhum"`, ou sem a chave, ele pede o texto do card — e o
fluxo **não trava** por isso. Ausência declarada é aceita; inventar o conteúdo
de um card que não se consegue ler, não.

`criar` não existe em board nenhum — ver abaixo.

## O ofício

- **`$PACOTE/references/check-first.md`** — as três verificações antes de abrir a atividade (seção 2).
- **`$PACOTE/references/rejection-memory.md`** — o que o produto já decidiu não fazer, e como consultar.
- **`$PACOTE/references/rationale/elcamargo-board-git-management.md`** — o porquê destas regras, com os casos medidos.

## Antes de qualquer coisa

Leia `elcamargo-flow/FLOW.md`. Ele é o contrato — steps, trilhas e as
obrigações de todo step.

Resolva os caminhos assim, nunca por caminho relativo:

```bash
# Onde a FERRAMENTA mora: CLAUDE_PLUGIN_ROOT, senão .agents/elcamargo-flow, senão o cache do plugin instalado (versão mais alta).
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
card, criar branch, commitar, abrir PR — tudo que ela já faz, com os portões
dela. Não reimplemente, não contorne, não crie nome de branch por conta própria.

Se não houver skill declarada, **você é o gerenciador de Git do projeto** — o
comportamento padrão abaixo vale.

### Comportamento padrão, sem skill de projeto

**Descobrir a atividade.** Pergunte ao usuário o identificador e o que a demanda
é. Se o projeto tem rastreador (GitHub, GitLab, Jira, Azure) e há CLI
autenticada, leia o item de lá — `gh issue view`, `glab issue view`. Sem CLI,
peça ao usuário o texto e os anexos. **Nunca invente o conteúdo de um card que
você não leu.**

**Branch.** Antes de criar, veja o padrão que o repositório já usa:

```bash
git branch -a --sort=-committerdate | head -20
```

Siga o padrão que estiver ali. Sem padrão discernível, use
`tipo/id_resumo_curto`, com `tipo` em `feat`, `fix`, `chore`, `docs`,
`refactor`. Confirme o nome com o usuário antes de criar.

**Base.** Ramifique da branch padrão atualizada, nunca da branch em que você
está por acaso. Confirme qual é a padrão (`git symbolic-ref refs/remotes/origin/HEAD`)
e traga-a antes.

**Commit.** Veja o formato dos últimos commits (`git log --oneline -20`) e siga.
Sem padrão, use `tipo(escopo): assunto no imperativo`, com corpo explicando **por
que**, não o que. Uma mudança coesa por commit.

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

**Nunca crie card.** O board é do solicitante. Se a demanda parecer merecer
card, diga isso ao usuário e deixe a decisão com ele.

Uma atividade pode agrupar **mais de um card** quando os documentos se
complementam. Nesse caso use o card principal como identificador e registre os
demais no título e na nota.

**Leia os comentários do card, não só o corpo.** É onde o analista responde
dúvida e registra mudança de decisão. Uma listagem de cards traz o corpo e
**não traz os comentários** — se você só olhou a listagem, não leu o card.

### 2. Verificar antes de abrir — portão

Siga `$PACOTE/references/check-first.md`, na ordem: rejeitado antes,
implementado, e — só para bug — a alegação se confirma.

O resultado **muda a trilha**, então ele vem antes de escolhê-la. Comece pelo
comando:

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

A verificação é **rasa** — só confirma que é real. Causa raiz é trabalho do
step 8.

### 3. Verificar se a atividade já existe

```bash
python3 $F status <id>
```

Se a atividade já existe, **não reabra**. Diga em que step ela está e pergunte
se o usuário quer retomar dali.

### 4. Decidir a trilha — portão

Apresente as três e **pergunte**; não escolha sozinho.

**Não decore esta tabela — imprima a de verdade:**

```bash
python3 $F fluxo
```

| Trilha | Quando | Portões humanos no caminho |
| --- | --- | --- |
| `completa` | Feature nova, com análise de negócio a revisar | 5 (spec), 7 (telas), 10 (entrega) |
| `sistema` | Card claro, sem análise de negócio a revisar | 5, 7, 10 |
| `curta` | Bug, ajuste, correção pontual | 10 |
| `rapida` | Fluxo Rápido: prazo aperta e a pressa é decisão tomada | 10 |
| `revisao` | Revisar a entrega de outra pessoa, num card que não é seu | 10 |
| `backend` | Metade de trás de um card, entregue antes da tela | 5 (spec), 10 |
| `frontend` | A metade da frente, depois que a de trás fechou | 5, 7 (telas), 10 |

Diga quantos portões humanos a trilha tem. A `curta` pula os portões 5 e 7.

**A `rapida` é o caso oposto:** produz a especificação e a tela, mas decide não
conferi-las. Se o usuário a escolher, **não discuta de novo** — diga uma vez,
na escolha, e siga.

**A `backend` e a `frontend` entregam UM card em DUAS atividades**, e abrir
qualquer uma delas exige três coisas:

1. **O id leva o sufixo da camada** — `1081-backend` e `1081-frontend`. Id
   sem sufixo abre com aviso.
2. **Branch e PR próprios de cada metade.**
3. **A `frontend` só abre depois de a `backend` do mesmo card ter concluído** —
   o `iniciar` confere e recusa, nomeando a atividade que falta. Se o backend
   veio de fora do fluxo, `--forcar --nota '<de onde>'` abre e deixa escrito.

Diga ao usuário, na escolha, o que ele está aceitando: **o card fica entregue
pela metade e bloqueado com `Aguardando frontend`** até a segunda atividade
fechar. Ver `$PACOTE/references/half-delivery.md`.

**A `revisao` não é trilha de construção, e abrir uma exige três coisas
diferentes:** worktree a partir da branch que o dev entregou (nunca branch
nova, nunca a árvore em que o usuário está trabalhando), descobrir em qual dos
três casos você está, e gravar isso no histórico. Nada é anexado ao card dele.
Ver `$PACOTE/references/foreign-review.md`.

**A descoberta do caso é um comando, e ele roda aqui.** De dentro da worktree,
depois de criá-la:

```bash
python3 $PACOTE/tools/prior-work/prior_work.py --base origin/<base-do-pr>
```

Ele responde `usou-o-fluxo`, `especificou-fora` ou `nao-documentou`, diz o que
isso muda nos steps seguintes, e nomeia o que achou. **Registre a saída no
histórico.**

> [!erro] Não deduza o caso, e não aceite deduzido
> Rode o comando mesmo quando alguém já tiver dito o caso. Ele custa segundos e
> é a diferença entre a doutrina e uma coincidência.

Recomende uma, com o motivo, em uma linha. Espere a resposta.

**Se o desfecho do passo 2 foi complemento**, diga isso ao recomendar e diga o
delta — o usuário precisa saber que cada step vai produzir muito menos.

**Na mesma pergunta, o risco** (`alto`, `padrao`, `baixo`): proponha pelo
checklist do `fluxo`, nomeando a superfície tocada, e **a pessoa confirma**.
Ver `FLOW.md`, *O risco*.

### 5. Abrir a atividade

```bash
python3 $F iniciar <id> --titulo '<título>' --trilha <trilha> \
  --risco <nivel> --superficies '<lista>' \
  --nota '<entendimento + resultado da verificação>'
```

**O lugar da atividade nasce `PENDENTE`** — branch e worktree. Não é
esquecimento: quem roda o `iniciar` pode não estar na árvore da atividade.

**O `avancar` do passo seguinte preenche sozinho**, se você o rodar de dentro da
árvore onde o trabalho vai acontecer. Rodando de outro lugar, declare:

```bash
python3 $F iniciar <id> --titulo '...' --trilha <trilha> \
  --branch <branch> --worktree <caminho>
```

### 6. Entregar ao próximo step

```bash
python3 $F avancar <id> --nota '<o que o próximo step recebe>'
```

Depois entregue o próximo step e pare:

```
Atividade 1042 aberta na trilha completa. Card lido, 3 anexos.

Próximo:
    /elcamargo-business-analysis-reviewer 1042
```
**Rode-o você não.** Quem dispara é o usuário.

**O próximo step roda em contexto novo**, sessão nova ou subagente, nunca esta
mesma janela — o handoff é por arquivo, para o step seguinte ler o artefato,
não o raciocínio de quem escreveu.


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
- Escolher a trilha ou o risco sem perguntar.
- Abrir atividade de bug sem ter tentado reproduzir.
- Recusar um pedido por conta própria porque ele já foi rejeitado antes — mostre
  a decisão e pergunte.
- Executar o próximo step do fluxo.
- Tocar em alteração local que não é sua.
