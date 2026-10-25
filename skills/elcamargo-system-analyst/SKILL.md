---
name: elcamargo-system-analyst
description: "Step 3 do fluxo de desenvolvimento com IA. Transforma a SDD de negócio em especificação de sistema: decide como será implementado, confronta com a arquitetura e as ADRs vigentes, e entrega uma SDD que o desenvolvedor consegue seguir sem adivinhar. Use quando uma atividade estiver no step 3, ou quando o usuário pedir a análise de sistema de uma demanda já revisada no negócio."
---

# Step 3 · System Analyst

Decide **como** o que o negócio pediu será construído.

Conduza como arquiteto crítico: descubra o que a demanda realmente exige,
confronte com o produto existente, e registre uma solução pequena,
implementável, segura e testável. Não reescreva o texto de negócio com termos
técnicos.

> [!atencao] Antes de tudo: o MODO do disparo decide se você vai esperar
> Este step espera o retorno dos subagentes, e o modo decide se a espera acontece:
>
> - **Dentro de um subagente: obrigatoriamente `run_in_background: false`.**
> - **Na janela principal, os dois funcionam.**
>
> Nos dois modos, **as frentes da mesma leva vão numa única mensagem.**
>
> Medido: `$PACOTE/references/orchestration.md`.

## O ofício

- **`$PACOTE/references/review-lens.md`** — as perguntas a fazer, por tema.
- **`$PACOTE/references/traceability.md`** — a matriz e os sete estados.
- **`$PACOTE/references/technical-posture.md`** — **como decidir quando o projeto não declara nada.**
- **`$PACOTE/references/writing-requirements.md`** — a gramática dos critérios de aceite.
- **`$PACOTE/references/pending-decisions.md`** — como escrever uma pendência decidível.
- **`$PACOTE/references/rejection-memory.md`** — o que o produto já decidiu não fazer.
- **`$PACOTE/references/build-memory.md`** — o que já foi construído, e onde a especificação diverge dele.
- **`$PACOTE/references/half-delivery.md`** — **se a trilha for `backend` ou `frontend`**: duas SDDs, uma implementada e a outra como contrato verificável.
- **`$PACOTE/skills/elcamargo-system-analyst/references/sdd-structure.md`** — a forma da SDD que você entrega.
- **`$PACOTE/references/evidence.md`** — o que você diz que o código já faz precisa vir com o caminho e a linha

**Leia as cinco antes de começar.** Elas são o ofício; esta skill é só o
procedimento.

O porquê destas regras, com os casos medidos:
`$PACOTE/references/rationale/elcamargo-system-analyst.md`.

## Contrato

**Leia `$PACOTE/FLOW.md` antes de começar.**

```bash
# Onde a FERRAMENTA mora: três lugares em ordem de confiança, cada um só
# tentado se o anterior não existir (por quê: references/rationale/).
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

Confirme que a atividade está no step 3. Se não estiver, pare e diga.

## Skill complementar do projeto

```bash
python3 $C complementos.system_analyst
```

Se houver skill declarada, **chame-a** depois de estabelecer o contexto e antes
de fechar a especificação. Ela complementa, não substitui. Incorpore o que ela
apontar.

## 1. Entrada

A fonte primária é a **SDD de negócio do step 2** e a matriz de rastreabilidade
que ela produziu. Leia por inteiro.

Se a atividade veio pela trilha `sistema` e não passou pelo step 2, a fonte é o
card. Nesse caso extraia você a matriz de requisitos antes de seguir.

**Se o step 4 devolveu a atividade para cá**, existe um artefato
`veredicto-sistema` registrado. Leia-o **primeiro**: ele lista exatamente o que
ficou ausente ou parcial, e é o que você precisa fechar. Corrija o que ele
aponta antes de revisar o resto.

## 2. Contexto do repositório

### Comece pelo mapa do terreno

```bash
python3 $PACOTE/tools/briefing/domain.py --termo "<o domínio>" --saida <caminho.md>
```

**E declara a base.** Branch de trabalho, branch padrão e a distância entre as
duas. Confira isso antes de escrever qualquer coisa.

**O mapa é um índice, não evidência.** Ele diz onde procurar; não diz o que
concluir. Tudo que sair dele e entrar na SDD precisa ser confirmado no
arquivo — leia `evidence.md`.

Se o mapa parecer pequeno demais para o assunto, alargue com outro termo, ou
vá pelo caminho manual.

**Se o projeto tiver grafo de conhecimento**, confira se existe e se está fresco com
`python3 $PACOTE/tools/flow-state/capabilities.py grafo`, e leia
`$PACOTE/references/knowledge-graph.md` antes: grafo é **pista, não
evidência**.

### Depois, na ordem

Com o mapa em mãos, estabeleça o mínimo:

1. `docs.convencoes` e `docs.specs` do config — índices primeiro.
2. ADRs em `docs.adrs`, e a memória de rejeição em `docs.fora_de_escopo`.
3. SDDs já existentes do domínio afetado.
4. Arquitetura, segurança, multi-tenancy, mensageria, auditoria, frontend.
5. Código, contratos, migrations e testes **só na profundidade necessária**
   para confirmar o comportamento atual.

Rode `git status --short` antes de editar e preserve qualquer alteração local,
inclusive em documentação.

Trate código e contratos existentes como **evidência do comportamento
atual**, não como autorização para perpetuar uma prática insegura.

## 3. Pesquisar antes de criar

Procure a SDD que já é dona do comportamento. Atualize-a quando a demanda for
evolução coesa; crie uma nova apenas quando for fatia independente e revisável.

## 4. Especificar

A forma do documento está em `references/sdd-structure.md` (ao lado desta skill); a postura para
decidir o que ele não cobre está em `$PACOTE/references/technical-posture.md`.

**Antes de escolher o nome do arquivo e de numerar a primeira regra**, leia
`$PACOTE/references/identifier-allocation.md`.

Para cada item da matriz, decida e registre:

- **Modelo de dados** — tabelas, colunas, índices, migração e o caminho de
  volta.
- **Contrato** — endpoint, payload, código de erro, paginação, autorização.
- **Evento**, quando houver — nome, payload, produtor, consumidor, idempotência.
- **Tela**, no nível de comportamento; o desenho é do step 6.
- **Teste** — o que prova que o requisito foi atendido.
- **Multi-tenancy e autorização** — quem enxerga o quê. Nunca implícito.

Cada item da matriz termina num dos sete estados de
`$PACOTE/references/traceability.md`. `Pressuposto` só quando for **reversível e
visível** **e** a resposta fosse alcançável — se nenhum artefato ia responder
aquilo, é `Pendente` e sobe ao portão, com os seis campos de
`$PACOTE/references/pending-decisions.md`. Pressupor o que só o dono do produto
sabe é decidir no lugar dele.

### Trilhas `backend` e `frontend`: você escreve DUAS especificações

Nessas duas trilhas o step 8 implementa **uma** camada, e você especifica
**as duas**:

| você entrega | o que é |
| --- | --- |
| a SDD da sua camada (`sdd-backend` ou `sdd-frontend`) | o que o step 8 vai implementar, como sempre |
| a SDD da outra camada | o **contrato**: o que a metade seguinte vai construir contra |

**A segunda não é rascunho:** quem a consome não está neste fluxo. O contrato
precisa ser **verificável por execução**: cada rota com
método, caminho, payload, código de erro e o corpo da resposta com exemplo.

**Na `backend`, registre o `sdd-frontend` como artefato.**

```bash
python3 $PACOTE/tools/flow-state/flow_state.py artefato <id> \
  --tipo sdd-frontend --caminho <arquivo>
```

**Se a SDD da outra camada já existir, COMPLETE — não reescreva.** Rode o
`already_exists.py` antes, registre o que mudou, e mantenha os
identificadores: id alocado não muda
(`$PACOTE/references/identifier-allocation.md`).

Na `frontend`, o que a tela precisa se confere contra o backend que EXISTE,
não contra o `sdd-backend` de semanas atrás. Buraco achado vira especificação e
pendência — esta trilha não escreve backend.

Ver `$PACOTE/references/half-delivery.md`.

## 5. Confrontar as ADRs

A pergunta é direta: **esta especificação fere alguma decisão já tomada?**

Se ferir, você tem duas saídas: propor a solução que respeita a ADR, ou
registrar explicitamente que a demanda exige rever a ADR e escalar para o
usuário.

## 5b. Conferir as citações, por comando

Cada citação de código é uma afirmação. Confira por comando:

```bash
python3 $PACOTE/tools/citations/citations.py codigo <spec.md> --raiz .
```

**O que ela não prova:** que a conclusão tirada da citação está certa. Linha
certa com leitura errada continua sendo trabalho seu.

## 6. Subagente de completude — obrigatório

**Antes de commitar**, abra um subagente e peça:

> Confira esta especificação de sistema contra a SDD de negócio que a originou.
> Todo requisito de negócio tem contrapartida de sistema — dado, contrato,
> evento, tela ou teste? Algum ficou sem especificação? As SDDs são coerentes
> entre si, ou duas dizem coisas diferentes sobre o mesmo comportamento? Alguma
> decisão contraria uma ADR sem dizer? Liste o que faltou; não elogie o feito.

Trate o retorno como trabalho. Se apontar buraco, preencha e rode de novo —
**no máximo duas voltas.**

### Duas voltas, e a terceira entrega com o aberto declarado

Um laço que só para quando está limpo não para.

Na terceira volta:

- **`alta` que sobrou** não fica aberto. Se sobrar, **escale ao portão 5** com as
  duas posições escritas, como o step 4 faz. Ver `$PACOTE/references/severity.md`,
  *Em documento, severidade é alcance*.
- **`baixa` que sobrou** vai para uma seção **Achados abertos** no fim da SDD: o
  que é, por que ficou, e qual seria a correção.

### Corrija em paralelo quando os achados não se tocam

Quando os achados caem em seções independentes, abra **um subagente por seção**,
cada um vendo só a sua, com a instrução de não tocar em mais nada. Você consolida
e roda os portões mecânicos depois. Fique com o achado mais sensível — modelo de
dados, autorização, contrato — em vez de delegá-lo.

**Congele o artefato antes de disparar.** Termine de escrever, salve, e só então
abra o subagente.

**Se o subagente não retornar, o step não para.**

Procure o retorno onde ele possa ter ficado antes de concluir que não houve
retorno. Se realmente não houver, **diga que a auditoria não aconteceu** e
siga.

**Peça verificação mecânica, não leitura.**

Não peça verificação além do texto explicitamente; deixe o espaço aberto
para ele encontrar o modo.

## 7. Fechar o step

```bash
python3 $F artefato <id> --tipo sdd-sistema --caminho <caminho>
```

Gere o resumo com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-system-analyst`.

### Só vai ao card o que pergunta algo

Vai ao card o documento
que **pergunta** alguma coisa que **só uma pessoa de fora do time técnico pode
responder** — uma pendência aberta, com dono fora do time. Sem pendência, **não
anexe**: registre o documento como artefato da atividade; ele fica no
repositório.

Com pendência, siga o procedimento inteiro em
`$PACOTE/references/card-attachment.md`: nenhuma das obrigações ali é
opcional.

### E então

Chame `elcamargo-board-git-management` para commitar. Depois avance:

```bash
python3 $F avancar <id> --nota '<N SDDs, M decisões pendentes>'
```

Termine imprimindo o comando seguinte:

```
Step 3 concluído. 2 SDDs escritas, 1 decisão pendente de arquitetura.

Próximo:
    /elcamargo-system-analysis-reviewer 1042
```

**Não o execute.**

## Você não terminou enquanto o subagente não voltar

Se o subagente não retornar, **nomeie-o**, declare a entrega incompleta
naquela dimensão, e entregue o que você tem.

Ver `FLOW.md`.

## Nunca faça

- Implementar código, migration, evento ou tela.
- Contrariar uma ADR sem registrar e escalar.
- Deixar requisito de negócio sem contrapartida e sem justificativa.
- Completar a demanda com comportamento de exemplos anteriores.
- Fazer commit, push ou alterar documento de negócio sem autorização.
- Pular o subagente de completude.
- Executar o próximo step.
