# Disparar e esperar: o modo do disparo, não o lugar de quem dispara

Quatro steps deste fluxo disparam subagentes e **dependem do retorno deles** —
os steps 2, 3, 6 e 9. A regra é uma só, e é um parâmetro:

> **Dentro de um subagente, `run_in_background: false` é obrigatório.** Na janela
> principal os dois modos funcionam. Em qualquer um deles, as frentes da mesma
> leva vão numa **única mensagem**.

Em segundo plano a chamada volta na hora com um "lançado com sucesso" que **não
é um resultado**. Quem disparou assim só volta a ter o que consolidar quando a
notificação de conclusão o reinvocar — e **essa notificação não alcança quem está
dentro de um subagente**.

**Na janela principal, escolher o segundo plano é legítimo e às vezes é o certo:**
ele devolve a janela enquanto as frentes rodam, e há trabalho que precisa dela —
atender o interfone, por exemplo. A primeira redação desta regra mandava bloquear
sempre, e teria proibido esse uso sem motivo; quem apontou foi a sessão
`chat-ai-app`, em 18/09/2026, ao declarar que ia disparar em segundo plano
de propósito.

## O que foi medido, em 18/09/2026

Duas medições nesta casa, com subagentes reais:

| experimento | resultado |
| --- | --- |
| Subagente dispara outro com `run_in_background: false` | **recebeu o retorno dentro do próprio turno**, síncrono |
| O mesmo subagente dispara em segundo plano | **nenhuma notificação chegou**; o turno acabou sem o resultado |

**Aninhar subagente funciona.** O que não funciona é esperar notificação de
segundo plano de dentro de um subagente — ela não chega antes de o turno acabar.

Na janela principal os dois modos terminam funcionando, porque ali a notificação
de conclusão chega e reinvoca a sessão. É por isso que o defeito passou
despercebido por tanto tempo: **o mesmo erro de modo é invisível num lugar e
fatal no outro.**

## O caso que custou 193.310 tokens

Na sessão `acme-app-18`, um step 9 rodado dentro de um subagente:

| turno | o que ele fez | acumulado |
| --- | --- | --- |
| 1 | leu a skill, montou o dossiê, marcou os guardas, disparou a leva 1a | 180.935 tokens, 48 chamadas |
| 2 | *"As duas frentes da leva 1a seguem rodando. Vou aguardar o retorno delas"* | 186.864 |
| 3 | *"Seguro aqui até as duas frentes da leva 1a voltarem."* | **193.310, 60 chamadas** |

**Zero achado consolidado, zero relatório, zero artefato** — 18% de todo o token
de subagente da sessão. As mesmas frentes, disparadas da janela principal,
voltaram de primeira, e a de segurança trouxe dois `alta` que nenhuma outra viu.

**E o disparo foi em segundo plano — medido no transcrito**, não inferido. A
sessão `acme-app-5f` extraiu os blocos `tool_use` daquele turno em
18/09/2026: **duas** chamadas de `Agent`, `code-reviewer` e
`implemented-sdd-reviewer`, **as duas com `run_in_background: true`**, e zero
ocorrências de `false` no arquivo inteiro.

**A armadilha de quem for refazer essa conta:** `grep -c '"run_in_background":true'`
no mesmo transcrito devolve **18**. Dezesseis dessas são o **eco do esquema da
ferramenta**, repetido a cada turno — não são chamadas. Só contando os blocos
`tool_use` de verdade aparecem as duas. Contar a ocorrência do texto em vez da
chamada é a mesma classe de erro que esta página inteira documenta.

## A lição retratada, e por que ela fica visível

A primeira versão desta página (2.41.0, empacotada e publicada) dizia outra
coisa: *"o turno de um subagente acaba quando ele para de chamar ferramenta,
logo esperar não existe nesse lugar"*, e o guarda mandava o subagente **parar e
devolver o step**. O teste proposto era de identidade — *"você enxerga a
ferramenta de disparar subagente? Se não, você é um"*.

**As duas coisas estavam erradas, e o teste foi o que as derrubou:**

1. Um subagente `general-purpose` **tem** a ferramenta de disparar subagente. O
   teste de identidade responde *"janela principal"* justamente para o caso que
   custou os 193 mil. Guarda que não dispara no caso que o originou é decoração.
2. Esperar **existe** dentro de um subagente — no modo bloqueante. Proibir o
   lugar teria custado a possibilidade de orquestrar de um subagente, sem
   consertar nada.

Fica escrito porque o erro é de uma classe que este pacote persegue: **a
prescrição foi deduzida da queixa, não medida.** O relato de quem pagou os 193
mil trazia a causa junto — *"ele não tem como bloquear"* — e eu confirmei lendo o
texto da skill, que é onde a causa não mora. Um experimento de dois subagentes e
treze segundos disse o contrário.

## Diagnosticar: o relógio não separa travada de saudável

    python3 $PACOTE/tools/dispatch-guard/dispatch_guard.py

Ele lê os transcritos de subagente em
`~/.claude/projects/<projeto>/<sessao>/subagents/agent-*.jsonl`, extrai só os
blocos `tool_use` de `Agent` e diz o modo do **último** disparo de cada frente.
Extrair não custa contexto: não é preciso abrir o JSONL, que tem centenas de
milhares de bytes.

**Por que o `mtime` não serve**, medido em 18/09/2026 na sessão
`acme-backoffice`:

| frente | parada há | último disparo | o que era |
| --- | --- | --- | --- |
| `a62e67a9` (step 9) | 338 s | `bg=True` | **travada para sempre** |
| `a2f2480a` (step 6) | 324 s | `bg=False` | **saudável**, esperando a frente dela |

Mesmo sintoma, causa oposta. **O arquivo não cresce enquanto o agente pensa**,
então "transcrito parado" não é "frente travada". Quem aplicar a heurística
óbvia — *parado há mais de cinco minutos, matar* — mata frente viva no meio do
trabalho dela.

**O `mtime` não é o diagnóstico. E o modo do disparo sozinho também não.**

Um agente que **terminou** para de crescer igual a um travado, e *dispara e
segue* é um final legítimo. Medido no mesmo dia: das três frentes que dispararam
em segundo plano de dentro de um subagente, **duas entregaram relatório completo**
— um handoff de step 1 e um veredicto de step 4 que devolveu o card, recebido e
acionado — e só uma travou.

**O que separa é a última fala.** Nas 12 frentes daquela sessão, as falas finais
caem em 42, 86, 165 — e depois 3.802, 3.961, 4.142, 4.892, 5.318, 5.350, 5.596,
6.066, 8.295. **Não há nada entre 165 e 3.802.** Entrega tem milhares de
caracteres; espera tem dezenas.

Então o defeito exige **dois** sinais:

| último disparo | última fala | veredicto |
| --- | --- | --- |
| segundo plano | curta | **TRAVADA** |
| segundo plano | longa | entregou **sem o retorno** — risco, não defeito |
| bloqueante | curta | esperando, e matá-la perde o trabalho |
| bloqueante | longa | entregou |

*"Disparou em segundo plano"* é **fator de risco**; *"disparou em segundo plano
e a última fala é uma espera"* é **o defeito**. A distinção é da sessão
`acme-backoffice`, e ela a levantou porque a primeira versão desta
ferramenta teria mandado matar e redisparar um step 4 cujo veredicto ela já
tinha em mãos e já havia acionado.

**Isso não enfraquece a regra do bloqueante.** Bloquear continua sendo o certo,
porque a alternativa depende de o agente ter a sorte de não precisar do retorno
— e num step 9 ele precisa.

E **omitir** o parâmetro conta como segundo plano: o padrão da ferramenta é
assíncrono, então não passá-lo é escolher o modo que quebra.

## Trocar de modo no meio do step não resgata o que já saiu

Medido no mesmo caso. A sessão mandou a frente passar a disparar bloqueando, e
ela aceitou:

> *"Understood — I'll switch to synchronous dispatch. Let me first check the
> state of the quality front already in flight."*
> *"Quality is still running. Let me wait in the foreground for it to actually
> finish."*

E ficou presa do mesmo jeito. **A correção chegou 11 minutos depois dos
disparos**, e o estrago estava na chamada anterior — as três frentes já tinham
saído em segundo plano, e nenhuma delas ia notificá-la.

Duas consequências:

- **chegou tarde não é desobediência.** A instrução pegou nas outras duas
  frentes, que ainda não tinham disparado;
- **frente já disparada em segundo plano não se conserta de dentro.** Ou alguém
  de fora colhe o resultado, ou a frente é morta e redisparada.

## O dossiê é o que torna a troca de orquestrador barata — quando ele existe

Medido pela sessão `chat-ai-app` em 18/09/2026: quando o orquestrador em
subagente foi morto e as frentes foram redisparadas da janela principal, **o
dossiê sobreviveu no scratchpad e a redescoberta custou zero**. As quatro frentes
leram o mesmo dossiê e produziram achados diferentes — a independência não virou
eco.

Sem ele, trocar de orquestrador é recomeçar: os 180 mil tokens do primeiro turno
foram, em boa parte, montá-lo.

**Mas isso depende de QUANDO a frente morreu, e o contra-exemplo é do mesmo
dia.** No backoffice, a frente travada não tinha escrito nada: zero arquivos no
scratchpad depois da hora do disparo, porque ela travou **antes** de rodar o
`briefing.py`. Quem redisparar contando com a economia pode não tê-la.

Antes de redisparar, **confira se o dossiê existe** em vez de supor. O que
sobreviveu naquele caso foi outra coisa, e vale registrar: o `tree_guard
conferir` devolveu *"a árvore está como antes do disparo"*, `rc=0` — nenhum
mutante para trás.

## O 403 do guardrail: frente que não se retoma

Uma frente, ou você, que passa a receber *"403 Requisicao bloqueada pelo
guardrail"* (`authentication_failed`) está com o **contexto contaminado** por um
CPF ou CNPJ por extenso. Não é falha passageira, e é o único caso em que
retomar é pior do que recomeçar: cada tentativa relê o documento.

- **Não retome e não mande `SendMessage`** a quem foi barrado.
- **Colha as devoluções, mascaradas:** `python3 $PACOTE/tools/doc-mask/doc_mask.py
  devolucoes --raiz <worktree>`. Ele marca `BLOQUEADA` a que morreu no 403 e
  grava a última fala de cada uma, inclusive a devolvida por `SubagentHandback`,
  numa pasta.
- **Dispare contexto novo apontando a pasta**, e não redispare quem entregou.
- **Confira o artefato que carregou o documento** (`doc_mask.py conferir`),
  senão a volta seguinte é barrada ao lê-lo.

Medido em 30/09/2026, no step 9 da `acme-backoffice-90`: o CPF entrou
pela SDD de negócio, saiu no relatório da volta 1, e barrou o step-runner da
volta 2 quando ele deu `cat` nesse relatório. Caso, prevenção e o que ainda não
se sabe em `$PACOTE/references/documents-in-context.md`.

## O que o auditor confere, e o que ele não alcança

`tools/audit-package/audit_package.py` exige que toda skill que cita um agente de
`agents/` carregue esta referência. Isso impede a próxima skill de nascer sem a
regra do disparo — que é o defeito de verdade, porque esta página não se lembra
sozinha.

**O que ele não alcança:** se a regra é seguida. O auditor confere presença de
texto, não o parâmetro usado na chamada. Um step 9 que dispare em segundo plano
passa pelo auditor igual.
