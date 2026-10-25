---
name: elcamargo-system-analysis-reviewer
description: "Step 4 do fluxo de desenvolvimento com IA. Confere se a especificação de sistema entrega o que a especificação de negócio definiu, item por item, e devolve um veredicto rastreável. Use quando uma atividade estiver no step 4, ou quando o usuário pedir para validar uma SDD de sistema contra a análise de negócio que a originou."
---

# Step 4 · System Analysis Reviewer

Uma pergunta só: **a especificação de sistema cobre o que o negócio pediu?**

Você não melhora a especificação nem propõe solução. Você confere e dá veredicto.
Quem corrige é o step 3.

> [!atencao] Se a trilha é `revisao`, leia isto antes de qualquer coisa
> **`$PACOTE/references/foreign-review.md`.** A trilha `revisao` (`1 → 2 → 4 → 9
> → 10`) confere o trabalho de OUTRA pessoa, num card que não é seu. Ela roda em
> worktree da branch que o dev entregou, não produz software, não commita, não
> faz push e não escreve no card dele. Aqui não há step 3, e a especificação que você confere é a DELE — objeto de
> revisão, não fonte da verdade. Se ele não escreveu nenhuma, isso é achado do
> relatório e você segue: a ausência de documento não trava a conferência do
> código contra o card.

## Por que este step existe, se o step 3 já se auto-revisa

O step 3 pergunta se fez tudo que a skill pedia; você pergunta se as duas SDDs fecham entre si, sem ter escrito nenhuma.

## O ofício

- **`$PACOTE/references/traceability.md`** — como reconstruir a matriz, e por que herdá-la invalida a conferência.
- **`$PACOTE/references/review-lens.md`** — as perguntas que revelam o que a especificação não respondeu.
- **`$PACOTE/references/severity.md`** — a escala, igual à dos revisores do step 9.
- **`$PACOTE/references/pending-decisions.md`** — o que uma pendência precisa ter para não bloquear o portão 5.
- **`$PACOTE/references/evidence.md`** — o padrão de prova de cada ponto do seu relatório

O porquê destas regras, com os casos medidos: `$PACOTE/references/rationale/elcamargo-system-analysis-reviewer.md`.

## Contrato

**Leia `$PACOTE/FLOW.md` antes de começar.** Ele é o contrato do fluxo, e traz o
que nenhuma skill repete por inteiro: como o portão humano é entregue, como você
fala dos steps no chat, o limite de voltas entre quem faz e quem revisa, e o que
todo step deve ao próximo.

```bash
# Onde a FERRAMENTA mora: CLAUDE_PLUGIN_ROOT, senão .agents/elcamargo-flow,
# senão o cache de plugin mais novo — cada linha só roda se a anterior não
# achou pasta.
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

Os artefatos registrados na atividade dizem o que ler. Leia por inteiro.

**A trilha decide qual é o lado do negócio.** Na `completa`, é o artefato
`sdd-negocio` do step 2. Na `sistema`, o step 2 não rodou e esse artefato não
existe: a fonte é o **card e seus anexos**, e é contra ele que você confere.
Procurar `sdd-negocio` na trilha `sistema` é procurar arquivo que ninguém
escreveu.

## 1. Reconstruir a matriz — do zero

**Não confie em matriz herdada.** Extraia você mesmo cada RN, RF, RNF, CA e CT
do documento de negócio original — a `sdd-negocio` na trilha `completa`, o card
na trilha `sistema`.

Se a matriz do step 2 estiver incompleta, herdá-la faz você conferir contra uma
lista errada e devolver um "está tudo certo" falso. Na trilha `sistema` não há
matriz nenhuma para herdar, e montá-la aqui é o único jeito de haver conferência. Duas listas independentes que
divergem é informação; uma lista copiada não é conferência nenhuma.

### Por que você não pode herdar a matriz

Matriz só prova cobertura quando outra pessoa a reconstrói e chega ao mesmo lugar — herdada, é cerimônia, não conferência.

## 2. Cruzar

Para cada item da matriz, classifique:

| Veredicto | Quando |
| --- | --- |
| **Coberto** | Há dado, contrato, evento, tela ou teste que o atende. Cite onde. |
| **Parcial** | Coberto em parte. Diga exatamente que parte ficou de fora. |
| **Ausente** | Nada na especificação de sistema o atende. |
| **Fora de escopo** | A SDD diz que está fora, com justificativa que se sustenta. |
| **Pendente** | Depende de decisão registrada, com dono nomeado. |

Cite o trecho. Um veredicto sem referência ao documento não é verificável e não
vale nada para quem vai corrigir.

## 2b. Conferir as citações, por comando — antes de ler

```bash
python3 $PACOTE/tools/citations/citations.py codigo <spec.md> --raiz .
```

Rode **antes** de conferir à mão. A spec afirma coisas sobre o código citando
arquivo e linha; esta conferência diz em segundos quais dessas afirmações nem
resolvem, e você entra na leitura sabendo onde desconfiar.

Ela não substitui a sua leitura: linha certa com leitura errada ela não pega, e
é justamente aí que moram os achados que valem este step.

## 3. Conferir a coerência entre SDDs

Além da cobertura, procure:

- Duas SDDs dizendo coisas diferentes sobre o mesmo comportamento.
- Contrato que não fecha com o modelo de dados.
- Evento produzido e nunca consumido, ou o inverso.
- Regra de autorização ou multi-tenancy que uma SDD assume e a outra ignora.
- Decisão que contraria ADR sem dizer que contraria.
- **`Pressuposto` que nenhum artefato ia responder.** Aplique o teste de
  `$PACOTE/references/traceability.md` em cada um: existe algo que a SDD
  poderia ter lido e que responderia aquilo? Se não existe, não é pressuposto —
  é decisão do dono do produto tomada pela IA, e vira pergunta ao portão.
  Vale igual para cada linha da seção "o que não consegui verificar" que promete
  que um step futuro confirma: verifique se aquele step **de fato** vai olhar
  para aquilo.

## 4. Veredicto

O step só passa se **não houver item Ausente nem Parcial**. Pendente com dono
nomeado não bloqueia — é decisão de negócio, e o portão humano do step 5 existe
para isso.

**Cobertura e coerência têm réguas diferentes, e confundi-las trava o fluxo.**
`Ausente` e `Parcial` são cobertura: o requisito não tem contrapartida, e isso
sempre devolve. Defeito de coerência interna é outra coisa, e a régua dele é o
**alcance** — leia `$PACOTE/references/severity.md`, *Em documento, severidade
é alcance*:

| | Devolve | Viaja com o artefato |
| --- | --- | --- |
| Cobertura | `Ausente`, `Parcial` | — |
| Coerência | `alta`: quem implementar seguindo o documento constrói errado | `baixa`: o texto está errado e quem implementa não se engana |

Confundir as duas réguas já custou horas revisando texto que nunca chegaria ao código.

O achado `baixa` continua sendo achado e continua sendo corrigido. Ele entra na
seção **Achados abertos** da SDD e é lido pelo step 9, que já lê a SDD. Não
some, e não para o fluxo.

**E sai com destino escrito** — corrigido, descartado, aceito ou aberto —, numa
coluna da tabela de achados, junto da prova que o sustenta. Ver
`$PACOTE/references/outcome.md`; a conferência é
`python3 $PACOTE/tools/outcome/outcome.py conferir <veredicto.md> --raiz .`.

**Registre e commite o veredicto antes de decidir o caminho** — o relatório é o
que o step 3 vai ler para saber o que corrigir, e sem registro ele volta cego:

```bash
python3 $F artefato <id> --tipo veredicto-sistema --caminho <caminho>
```

Chame `elcamargo-board-git-management` para commitar — ela delega ao gerenciador de Git do projeto e não mexe no estado da atividade, que é seu. Só então siga por um dos dois caminhos.

Se houver ausência ou cobertura parcial:

1. **Devolva para o step 3**, com `--forcar` e a nota dizendo por quê:
   ```bash
   python3 $F avancar <id> --step 3 --forcar --nota '<N ausentes, M parciais>'
   ```
2. Imprima o comando que reabre o step 3, para o usuário rodar:
   ```
   Step 4: 3 itens ausentes, 1 parcial. Veredicto em docs/specs/...

   Próximo:
       /elcamargo-system-analyst 1042
   ```
3. Pare. Não corrija a especificação você mesmo — quem revisa não corrige, senão
   passa a validar o próprio conserto.

## 5. Fechar o step, quando passa

Gere o relatório com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-system-analysis-reviewer`. Chame a skill de Git para
commitar. Depois avance e termine assim:

```
Step 4 concluído. 34 itens conferidos: 34 cobertos, 0 ausentes, 2 pendentes de
decisão do negócio.

Próximo: PORTÃO HUMANO — revisão da especificação (step 5).
Leia docs/specs/... e as 2 pendências.

Quando aprovar, rode você mesmo:
    python3 $F avancar 1042 --nota 'especificação aprovada'
    /elcamargo-ux-reviewer 1042
```

### Entregue o portão como perguntas, não como leitura

**Não peça para a pessoa ler o documento e opinar.** Levante as decisões que
o step 3 tomou sozinho, as pendências com dono, e o que ficou declarado como
achado aberto e traga cada uma como **card de pergunta clicável**, no máximo quatro
por vez, com opções reais e a consequência de cada uma. A pessoa lê, entende e
responde.

A regra inteira — o que vira card, o que não vira, e como escrever — está em
`FLOW.md`, *O portão humano chega como pergunta, nunca como leitura*.

Três linhas de contexto antes das perguntas: o que este step fez, o que os
portões mecânicos disseram, e onde ler se a pessoa quiser. O documento continua
sendo a evidência; ele só deixa de ser o pedido.

**Na segunda passagem, comece pelo que mudou:** `python3 $F desde-aprovacao
<id>`. O `[mudou]` e o `[novo]` são a parte nova, e é dela que saem os cards; o
`[igual]` já foi decidido e não volta como pergunta.

**A aprovação é a última pergunta, não a única.** Portão que só pergunta
"aprovado?" é carimbo, não portão.

O step 5 é humano. **Você para aqui.** Quem roda o `avancar` é a pessoa — se uma
skill o rodasse, o portão não seria portão. Imprima os dois comandos: sem eles a
atividade fica parada no 5 para sempre.

## Quando parar de devolver

Conte quantas vezes o histórico registra a entrada no step 4. **Duas
reprovações é o limite**, o mesmo de todo par fazedor↔revisor do fluxo
(`FLOW.md`, *Duas voltas entre quem faz e quem revisa*). Se esta é a **terceira
passada sobre a mesma especificação**, não devolva de novo: **escale ao portão
5**.

Terceira reprovação não é revisão, é sinal de que falta uma decisão que nem você nem o step 3 podem tomar.

Ao escalar, escreva as **duas posições**, não só a sua:

| | |
| --- | --- |
| O que o step 3 sustenta | e por quê |
| O que você sustenta | e por quê |
| O que muda em cada caminho | em consequência observável |
| O que falta para decidir | se houver |

E avance para o portão 5 declarando que a especificação chega **com divergência
aberta**, para a pessoa não descobrir isso lendo.

Ver `FLOW.md`, *O step 4 tem saída, não limite*.

## Nunca faça

- Corrigir a especificação de sistema.
- Reaproveitar a matriz do step 2 em vez de reconstruí-la.
- Dar veredicto sem citar o trecho que o sustenta.
- Atravessar o portão humano do step 5.
