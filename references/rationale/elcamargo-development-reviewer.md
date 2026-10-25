# Rationale — Step 9 · Development Reviewer

Esta é a explicação da skill `elcamargo-development-reviewer` (step 9): histórico, incidentes, números medidos e exemplos que sustentam as regras. Não é instrução — quem decide o que fazer é o `SKILL.md`.

## O ofício

- **`$PACOTE/references/evidence.md`** — o padrão de prova que você exige de cada frente, e de si mesmo ao consolidar
- **`$PACOTE/references/outcome.md`** — o que aconteceu com cada achado, e por que isso precisa ser contado
- **`$PACOTE/references/root-cause-debugging.md`** — na volta 2, exija a causa raiz escrita de cada correção: foi ela que revelou quatro defeitos introduzidos ao corrigir treze

## Antes de tudo: o MODO do disparo decide se você vai esperar

e ninguém para consolidá-las. Foi assim que um step 9 gastou **193.310 tokens
em três turnos dizendo que aguardava**, e entregou zero.

## Trilhas backend e frontend: leia o escopo ANTES de julgar (o erro que produziu esta regra)

> [!erro] Esta regra já custou uma tela em homologação, e o gatilho antigo está aqui de propósito
> Até 2026-09-10 a regra dizia *"roda quando a entrega tem tela — quando o diff
> toca o frontend"*, e fechava com *"numa entrega só de backend não há o que
> abrir"*. A última frase é falsa, e a primeira mede a coisa errada.
>
> O caso: `array_agg(opcao.label)` num adapter de backend, onde a coluna real
> chama-se `value`. Postgres resolve nome de coluna na análise, então a rota
> respondia `500` em **toda** chamada contra tenant real — formulário de
> primeiro acesso morto. **Zero arquivos de frontend no diff.** Três frentes
> lendo código, em duas voltas, não acharam; um testador externo abriu o
> navegador e achou. Na atividade anterior o mesmo critério dispensou a frente
> quatro vezes.

## A frente que usa o sistema

A POC mediu o buraco: das vinte e uma execuções do fluxo, **onze terminaram
confessando *"não verifiquei em navegador"***. E os achados que mudaram uma
decisão vieram todos de quem executou — a sonda que provou a escalação de
escrita, a imagem aberta que mostrou o portão visual aprovando o próprio
defeito, a mutação que revelou onze testes verdes provando nada.

## Prepare o dossiê uma vez, antes de disparar

Na POC as cinco frentes gastaram 310 mil tokens para revisar 36 linhas de diff.
A maior parte não foi revisão: foi cada uma rodar o mesmo `git diff`, abrir os
mesmos arquivos, procurar quem chama o mesmo método e redescobrir como se roda o
lint deste projeto.

## Prepare o dossiê uma vez, antes de disparar (independência das frentes)

**Ele não contém nenhum achado, de propósito.** As frentes valem porque
julgam de forma independente — foi assim que dois vazamentos entre clientes
apareceram numa entrega com onze testes verdes. Um dossiê que dissesse "atenção
ao filtro por cliente" faria as seis olharem para o mesmo lugar, e a
independência viraria eco.

## Marque a árvore antes de disparar

Em 08/09/2026 a máquina travou no meio de uma execução com
três mutantes vivos em cima da validação de boot de um segredo:
`if (false && ...)`. A frente restaurou por pouco. Dois segundos antes e o
mutante ficaria, e o commit seguinte o levaria junto.

## Marque a árvore antes de disparar (conteúdo, não status)

É o que faz diferença no caso
normal: a árvore já chega suja da entrega do step 8, então um mutante por cima
produz a mesma linha de `git status` e passaria despercebido.

## E marque os processos, pelo mesmo motivo

Em
10/09/2026 as três árvores voltaram limpas e conferidas, e os serviços da outra
atividade do usuário estavam no chão: a frente de execução limpou os próprios
processos com `pkill -f "nest start"` e o padrão casou com o backend do vizinho.
Quatro portas — 3001 a 3004.

## E ligue o amostrador de memória

**Pico de memória não sai de transcrito.** O `metrics.py` lê token, turno e
horário depois do fato; RSS só existe enquanto o processo existe. Sem o
amostrador ligado, a pergunta *"esta revisão cabe num notebook de 8 GB?"* não
tem resposta — e não ter medido é diferente de ter medido e estar baixo.

## Dispare em três levas, e espere cada uma

Seis juntas somaram mais de 3 GB numa máquina que já estava em 13,7
de 16 GB, e o travamento matou duas frentes: a revisão fechou com quatro de
seis, e a de execução é a única que produz procedência `execução`.

## Dispare em três levas, e espere cada uma (tempo de parede)

**Espere uma leva voltar antes de abrir a próxima.** É o que limita o pico, e o
step 9 não tem pressa: cada frente leva de 7 a 18 minutos, e o custo é tempo de
parede que ninguém está olhando.

## As duas que escrevem rodam em árvore própria

Escrever na árvore do usuário enquanto quatro frentes leem dali contamina a
leitura delas sem que ninguém saiba — e a única razão de isso ter aparecido é
que a frente de SDD percebeu sozinha que duas leituras do mesmo arquivo
devolviam conteúdos diferentes, e passou a revisar contra o commit. **Foi sorte.**

## Você não terminou enquanto as seis não voltarem

**Dispare e espere.** Numa execução real o orquestrador disparou as frentes e
**retornou dizendo que aguardava os retornos** — o step ficou pela metade, com
cinco revisões em curso e ninguém para consolidá-las. A frente de segurança
tinha achado uma violação de isolamento, e o achado ficou órfão.

## 2. Consolidar

Aconteceu em 20/09/2026: um relatório afirmava seis numa trilha em que a tabela
dava cinco, com **zero nomeadas**. Pelo documento não dá para dizer qual das duas
é verdade, e ele governa a volta seguinte.

## Consolidar é tentar derrubar, não somar

Num estudo de revisão com mandato adversarial, esse passo **derrubou cerca de
79% dos achados candidatos**.

## A procedência decide quem derruba quem

**A frente que usa o sistema é a única que produz `execução`** — três dos nove
defeitos graves de uma revisão real só existiam porque ela subiu a aplicação.

## Concordância não é evidência

leram o mesmo diff com o
mesmo viés, e no mesmo estudo **dez endossaram por unanimidade uma
vulnerabilidade inexistente**.

## Descobrir em que volta você está

Aconteceu na primeira vez que o
portão 10 devolveu.

## O ciclo

Revisão em passada única supera
revisão multi-turno em precisão medida; nas voltas seguintes os revisores
**fabricam achados quando os erros reais acabam**, e a taxa de falso positivo
sobe mais de 60%.
