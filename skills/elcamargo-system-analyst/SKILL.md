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

**Se a atividade voltou do portão 5, ou de um step 4 de antes da 2.69.0**, existe
um artefato `veredicto-sistema` registrado. Leia-o **primeiro**: ele lista
exatamente o que ficou ausente ou parcial, e é o que você precisa fechar.

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

## 6. A conferência da especificação — obrigatória

Até a 2.68.0 isto era o step 4, um step inteiro para refazer a pergunta que o
seu subagente de completude já fazia. Agora é uma conferência só, dentro de
você, em contexto limpo. **Ela continua independente:** quem confere não
escreveu a SDD e reconstrói a matriz do zero. O que se cortou foi o step a mais,
não a conferência.

**Congele o artefato antes de disparar.** Termine de escrever, salve, rode o
`citations.py` da 5b, e só então chame o subagente
`elcamargo-system-analysis-auditor` (`run_in_background: false`, sem `model`:
o cabeçalho dele fixa Opus) passando:

- o id da atividade;
- o caminho de cada SDD de sistema;
- qual é o lado do negócio: a `sdd-negocio`, ou o card e seus anexos quando a
  trilha não tem step 2.

Não mande o seu raciocínio nem a sua matriz: ele tem de chegar ao mesmo lugar
sozinho, senão não confere nada.

**Persista o retorno assim que chegar**, como o veredicto da atividade:

```bash
python3 $F artefato <id> --tipo veredicto-sistema --caminho <caminho-do-veredicto.md>
```

### Duas voltas, e a terceira entrega com o aberto declarado

Se o veredicto é `devolve`, corrija o que ele aponta e chame **de novo**, com o
veredicto anterior e o diff do que você mudou. Na segunda volta, ele confere a
correção e o que ela tocou, não a SDD inteira. **No máximo duas voltas.**

Depois da segunda:

- **`Ausente`, `Parcial` ou coerência `alta` que sobrou** não fica aberto em
  silêncio. Vai ao portão 5 **com as duas posições escritas**: o que você
  sustenta, o que a conferência sustenta, o que muda em cada caminho e o que
  falta para decidir. Divergência que sobrevive a duas voltas é decisão que nem
  você nem o conferente podem tomar.
- **`baixa` que sobrou** vai para uma seção **Achados abertos** no fim da SDD: o
  que é, por que ficou, e qual seria a correção. O step 9 lê a SDD e os acha
  lá. Ver `$PACOTE/references/severity.md`, *Em documento, severidade é
  alcance*.

Cada achado sai com destino escrito (corrigido, descartado, aceito ou aberto),
conferido por
`python3 $PACOTE/tools/outcome/outcome.py conferir <veredicto.md> --raiz .`.

### Corrija em paralelo quando os achados não se tocam

Quando os achados caem em seções independentes, abra **um subagente por seção**,
cada um vendo só a sua, com a instrução de não tocar em mais nada. Você
consolida e roda os portões mecânicos depois. Fique com o achado mais sensível
(modelo de dados, autorização, contrato) em vez de delegá-lo.

**Se o conferente não retornar, o step não para, e também não passa calado.**
Procure o retorno onde ele possa ter ficado. Se não houver, diga no portão que
**a conferência não aconteceu**: a pessoa decide sabendo.

## 7. Fechar o step: você entrega o portão 5

```bash
python3 $F artefato <id> --tipo sdd-sistema --caminho <caminho>
```

Gere o resumo com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-system-analyst`.

### Só vai ao card o que pergunta algo

Vai ao card o documento
que **pergunta** alguma coisa que **só uma pessoa de fora do time técnico pode
responder**: uma pendência aberta, com dono fora do time. Sem pendência, **não
anexe**: registre o documento como artefato da atividade; ele fica no
repositório.

Com pendência, siga o procedimento inteiro em
`$PACOTE/references/card-attachment.md`: nenhuma das obrigações ali é
opcional.

### E então

Chame `elcamargo-board-git-management` para commitar. Depois avance:

```bash
python3 $F avancar <id> --nota '<N SDDs, M itens conferidos, K perguntas ao portão>'
```

Na trilha que não tem portão 5 (`rapida`, `ultra-rapida`), o próximo é o step 6:
imprima o comando dele, **sem executá-lo**, e pare.

### Entregue o portão como perguntas, não como leitura

**Não peça para a pessoa ler o documento e opinar.** As perguntas saem do
veredicto: os pressupostos que viraram decisão, as pendências com dono, a
divergência que sobreviveu às duas voltas e o que ficou em Achados abertos.
Traga cada uma como **card de pergunta clicável**, no máximo quatro por vez, com
opções reais e a consequência de cada uma. Ver `references/fluxo/steps.md`,
*O portão humano chega como pergunta, nunca como leitura*.

Antes das perguntas, três linhas de contexto: o que este step fez, o que a
conferência e os portões mecânicos disseram, e onde ler se a pessoa quiser.

**Na segunda passagem, comece pelo que mudou:** `python3 $F desde-aprovacao
<id>`. Os cards saem do `[mudou]` e do `[novo]`; o `[igual]` já foi decidido.

**A aprovação é a última pergunta, não a única.** Termine assim:

```
Step 3 concluído. 2 SDDs; conferência: 34 itens, 34 cobertos, 2 pendentes.

Próximo: PORTÃO HUMANO · Especificação (step 5).

Quando aprovar, rode você mesmo:
    python3 $F avancar 1042 --nota 'especificação aprovada'
    /elcamargo-ux-reviewer 1042
```

O step 5 é humano. **Você para aqui.** Quem atravessa é a pessoa: rodando o
`avancar`, ou aprovando no card que a janela que conduz lhe traz.

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
- Pular a conferência, ou passar a ela a sua matriz.
- Executar o próximo step.
