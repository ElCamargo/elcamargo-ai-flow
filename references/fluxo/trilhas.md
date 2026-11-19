# Fluxo · As trilhas

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## As trilhas

A trilha é decidida uma vez, no step 1, com o usuário, e fica gravada na
atividade. Ela existe para o fluxo não virar cerimônia: dez steps para um botão
que não desabilita é como o processo morre.

| Trilha | Quando usar | Steps |
| --- | --- | --- |
| `completa` | Feature nova, com análise de negócio a revisar | 1 → 2 → 3 → 5 → 6 → 7 → 8 → 9 → 10 |
| `sistema` | Card claro, sem análise de negócio a revisar | 1 → 3 → 5 → 6 → 7 → 8 → 9 → 10 |
| `curta` | Bug, ajuste, correção pontual | 1 → 8 → 9 → 10 |
| `rapida` | O Fluxo Rápido: pressa declarada, com o preço escrito | 1 → 3 → 6 → 8 → 9 → 10 |
| `ultra-rapida` | **Pedida pela gerência, não recomendada por este pacote.** Sem revisão da entrega | 1 → 3 → 6 → 8 → 10 |
| `especificacao-completa` | O analista especifica tudo e para; o card fica aguardando dev | 1 → 2 → 3 → 5 → 6 → 7 |
| `construcao` | O dev implementa a especificação que o analista deixou | 1 → 8 → 9 → 10 |
| `revisao` | Revisar o trabalho de outra pessoa, num card que não é seu | 1 → 2 → 4 → 9 → 10 |
| `backend` | A metade de trás de um card, entregue antes da tela | 1 → 2 → 3 → 5 → 8 → 9 → 10 |
| `frontend` | A metade da frente, depois que a de trás fechou | 1 → 2 → 3 → 5 → 6 → 7 → 8 → 9 → 10 |

A trilha `curta` não passa por especificação nem por tela, e por isso também não
passa pelos portões 5 e 7 — eles existem para validar exatamente o que ela não
produz. Sobra o portão 10, que é o aceite.

Na trilha `curta`, o step 9 roda `code-reviewer`, `quality-reviewer` e
`security-reviewer`. As duas frentes que ficam de fora são as que conferem
contra especificação — e a `curta` não produz nenhuma.

**Isso é dito no `iniciar` desde 2.42.0, e não era.** O aviso genérico se deriva
de *"a trilha produz o que o conferidor ausente olharia"*, e a `curta` não
produz nada — então ela saía muda. Só que havia o que dizer, e não é sobre
portão: **o step 9 dela cobre três das seis dimensões, e as duas que faltam são
as únicas que respondem *"é isto que foi pedido?"*.** A `curta` não tem baseline
de documento; a linha de comparação é o código de antes mais o card. Medido nas
quatro `curta` que chegaram ao portão 10 até 15/09/2026: o achado que mudou
decisão veio de execução ou de qualidade, **nunca** de leitura contra
especificação. Por isso dispensar a frente de execução aqui não é perder uma
dimensão — é ficar sem nenhuma. O `security-reviewer`
não lê especificação: parte da stack e do diff, e um ajuste de uma linha numa
rota é exatamente onde um vazamento entre clientes entra em produção.

### A trilha `revisao` — conferir o trabalho de outra pessoa

As outras quatro **produzem** software. Esta não: ela confere o que já foi
entregue, num card que não é seu, contra o que o card pediu.

O cenário: você precisa revisar a entrega de outro dev e **não sabe** se ele
revisou negócio, se especificou, se leu o Figma, se implementou tudo, nem se a
qualidade é a que vocês querem. Refazer o trabalho para descobrir custaria mais
que ele ter feito de novo.

**O card é a âncora, porque é a única peça do conjunto que não saiu das mãos
dele.** Se o dev escreveu SDDs, elas entram como *objeto de revisão*, nunca como
fonte da verdade: uma especificação que leu o card errado produz código fiel ao
erro, e conferir código contra ela só prova coerência interna. É o mesmo buraco
que faz o step 9 ter duas frentes separadas em vez de uma.

Por isso o step 2 roda sempre aqui, mesmo com documentação do outro lado: ele lê
o card e produz a **baseline** — a lista do que dá para cobrar. O step 4
confronta com ela o que o dev escreveu, se escreveu; quando não há documento, a
ausência é achado do relatório e a trilha segue.

**Três coisas que a forma da trilha garante, sem depender de ninguém lembrar:**

| Ela não | Por quê |
| --- | --- |
| **conserta** | não tem step 8, então o step 9 não tem a quem devolver — os achados saem em relatório, e quem conserta é o dono do card |
| **escreve no card dele** | publicar crítica no card de outra pessoa é decisão dela; o step 1 lê o board e não anexa nada |
| **para o seu trabalho** | roda em **worktree da branch que o dev entregou**, nunca na árvore em que você está implementando |

A worktree não é conforto, é necessidade: duas frentes do step 9 escrevem em
disco — a de qualidade insere mutantes no código-fonte, a de execução cria
fixtures. A branch é dele, a worktree é sua, e nela não se commita nem se faz
push.

Doutrina inteira em `references/foreign-review.md`, lida pelos steps 1, 2, 4 e 9
quando a trilha é `revisao`.

### A trilha `rapida` — o Fluxo Rápido

Ela mantém **quem produz** — especificação de sistema, tela e código — mais o
revisor da entrega, e corta os dois portões que ficam entre eles, o 5 e o 7. Até
a 2.68.0 cortava também o step 4; desde que a conferência da SDD roda dentro do
step 3, ela vem junto com quem produz. Do analista de sistema a tela vai direto para o
desenvolvedor; do desenvolvedor, com o step 9 no meio, direto para o portão 10.

**A diferença para a `curta` não é de tamanho, é de natureza.** A `curta` não
passa pelos portões 5 e 7 porque não produz nada que eles validem — a omissão é
gratuita. A `rapida` **produz** a especificação e a tela, e decide não
conferi-las. Isso não é o mesmo, e o fluxo não finge que é: o `iniciar` avisa o
que ficou de fora e **grava no histórico da atividade**, para quem estiver no
portão 10 achar. Quem valida no fim precisa saber o que não foi validado no
meio.

O que ela mantém, e o motivo de manter: o step 9 continua rodando inteiro. O
revisor da entrega é a única conferência que sobrou entre o código e a produção,
e tirá-lo não deixaria o fluxo rápido — deixaria o fluxo sem função.

| O que se ganha | O que se paga |
| --- | --- |
| Quatro steps a menos que a `sistema`, e dois portões humanos a menos de espera | A SDD vai para o código **sem ninguém ter conferido** se ela entrega o que o negócio pediu |
| Nenhuma volta possível nos pares 3↔4 — que na POC custaram ~7h de retrabalho | A tela vai para o código sem aprovação de quem pediu; retrabalho aqui aparece **depois** de estar implementado |

**Quando ela é a escolha certa:** demanda pequena e bem entendida, com prazo
que não cabe outra coisa, e alguém disposto a assumir o retrabalho se a
especificação estiver errada. **Quando não é:** quando o custo de refazer o que
foi construído é maior que o custo dos dois portões — que é quase sempre o caso
quando a demanda toca autorização, dinheiro ou dado de cliente.

### O par `especificacao-*` → `construcao` — quando quem analisa não é quem constrói

Esta ferramenta nasceu do modo de trabalho de quem **faz a análise e
implementa**. Nem todo dev especifica, e nem todo analista constrói. Estas duas
partem o fluxo no **portão 7**: a especificação entrega negócio, sistema e tela
decididos, e o card fica `Aguardando desenvolvimento`.

| | `especificacao-completa` | `construcao` |
| --- | --- | --- |
| steps | 1 → 2 → 3 → 5 → 6 → 7 | 1 → 8 → 9 → 10 |
| produz | as SDDs, as matrizes, as decisões de tela | o software |
| portões humanos | 5 e 7 | 10 |
| implementa | **nada** | tudo |

**Somadas dão exatamente a `completa`, e a interseção é só o step 1** — que cada
uma precisa para abrir a própria atividade. Nada do fluxo se perde no corte e
nada roda duas vezes. Há teste prendendo isso, porque a propriedade é o que
torna o par seguro e ela **não se vê olhando as duas listas separadas**.

Um card vira **duas atividades** — `1081-especificacao` e `1081-construcao` —,
como em `backend`/`frontend`.

#### A `construcao` tem a MESMA FORMA da `curta`, e essa é a armadilha

`1 → 8 → 9 → 10` nos dois casos. **A diferença inteira é o que a `construcao`
herda**, e por isso ela é invisível na lista de steps.

Ao abrir, o step 1 traz os artefatos da `especificacao` — SDDs, matrizes,
decisões de tela — **como artefatos registrados da atividade nova**. O step 8
implementa contra eles e o step 9 os confere como se esta atividade os tivesse
produzido.

O ganho é concreto e mensurável: **a `construcao` roda as seis frentes no step
9; a `curta` roda três.** As duas que faltam na `curta` — SDD implementada e
negócio implementado — são as únicas que respondem *"é isto que foi pedido?"*, e
elas precisam de um documento que só a especificação produz.

**Por isso o guarda RECUSA em vez de avisar.** Aberta sem a metade de
especificação, a `construcao` não fica pior: ela vira uma `curta` sem que nada
na lista de steps mostre isso. O `iniciar` nomeia a atividade que falta, e
`--forcar --nota` abre assim mesmo deixando escrito por quê.

#### Duas regras que a `construcao` carrega

**A especificação envelhece.** Entre o portão 7 e o dev passam dias, e o código
andou. Confira contra o que **existe**, não contra o que a spec supunha — a
mesma regra que a `frontend` carrega sobre o backend.

**Divergência volta ao analista, e não vira decisão do dev.** Achou que a spec
está errada: **relate e devolva**. A `construcao` não tem step 3 para
consertá-la, e corrigir a especificação de quem não aprovou a correção
transforma o contrato em rascunho. A conferência `especificacao-conferida`
segura o `concluir` até isso estar resolvido.

### A trilha `ultra-rapida` — pedida pela gerência, e o pacote não a recomenda

Ela é a `rapida` **sem o step 9**, e essa subtração é de outra ordem. A `rapida`
corta conferências de **documento** e mantém a última conferência do **código**.
A `ultra-rapida` corta também a do código: o desenvolvedor entrega direto ao
portão humano.

Duas seções acima, sobre a `rapida`, este documento já dizia — antes de esta
trilha existir — que tirar o step 9 *"não deixaria o fluxo rápido, deixaria o
fluxo sem função"*. **A frase fica.** A trilha existe porque foi pedida pela
gerência do projeto em 18/09/2026, com o custo de qualidade assumido por quem a
pediu, e não porque o pacote mudou de opinião.

| O que se ganha | O que se paga |
| --- | --- |
| Cinco steps a menos que a `completa`; nenhuma espera de portão até o fim | **Nada confere o código** — nem legibilidade, nem segurança, nem qualidade, nem se a tela funciona |
| A entrega chega ao aceite no menor tempo que este fluxo permite | O portão 10 recebe código que nenhuma máquina e nenhum revisor olhou |

**E há uma consequência que nenhum aviso genérico alcançaria**, por isso ela é
dita à parte: as conferências — árvore, memória, guardas — são registradas como
`exigida` ao **entrar** no step 9. Sem step 9, **nenhuma é pedida**, então
nenhuma aparece como pendência e o `concluir` não segura nada.

> **Ausência de pendência aqui não é sinal de que está tudo certo. É sinal de
> que ninguém perguntou.**

Ela emite **nove avisos** no `iniciar`, mais que qualquer outra trilha, e todos
vão para o histórico da atividade — que é onde quem estiver no portão 10 precisa
achá-los. O fluxo não impede a escolha; ele impede que ela seja silenciosa.

### As trilhas `backend` e `frontend` — um card, duas entregas

As outras cinco entregam um card de uma vez. Estas duas o partem em dois, em
tempos diferentes, e existem por um pedido concreto: **adiantar o backend, que
serve o front web e o mobile, para o time mobile não esperar o front web ficar
pronto.** Entre uma metade e outra o card fica bloqueado, com a etiqueta
`Aguardando frontend` posta pelo próprio `concluir`.

**A regra que resume as duas: cada metade ESPECIFICA as duas camadas e
IMPLEMENTA uma.** A que ela não implementa sai especificada, e essa
especificação é o contrato — na `backend`, é o que o time mobile consome sem
estar neste fluxo.

| | `backend` | `frontend` |
| --- | --- | --- |
| implementa | backend | tela |
| não tem | 6 e 7: não há tela para desenhar nem validar | — |
| o step 9 revisa | só a metade entregue | **a entrega inteira** |
| a conferência que segura o `concluir` | `contrato` | `entrega-ponta-a-ponta` |

**A `frontend` roda sempre depois da `backend`** — o `iniciar` confere e recusa
abrir antes, nomeando a atividade que falta. E ela valida a entrega inteira por
aritmética: é a última metade, e não há uma terceira para conferir o conjunto
depois dela.

**O contrato se prova por execução**, não por leitura: entrar no step 9 registra
a conferência como `exigida`, e a `runtime-reviewer` chama cada rota que o
`sdd-frontend` promete. Contrato errado custa o trabalho de outro time, semanas
depois, e nenhuma frente deste pacote estará lá.

Um card vira **duas atividades** — `1081-backend` e `1081-frontend` —, com
branches e PRs separados. Ver `references/half-delivery.md`.

Mudar de trilha no meio exige `--forcar` e uma nota dizendo por quê. Não é
proibido; é registrado. **Subir da `rapida` para a `sistema` no meio é o
caminho previsto** quando a especificação se mostrar maior do que parecia.

### O risco — o segundo eixo

A trilha diz **quantos** steps a atividade percorre; o risco diz **quanta
conferência** ela recebe no 9. São perguntas diferentes: uma correção de uma
linha na rota de login é `curta` e é `alto`.

O step 1 propõe o risco a partir de um checklist de superfícies — `autenticacao`,
`pagamento`, `dados-pessoais`, `migracao`, `contrato-publico`, que o `fluxo`
imprime com onde olhar — e **a pessoa confirma**, na mesma pergunta da trilha.
O `iniciar` grava `risco` e `superficies` no front matter, e o histórico diz que
foi confirmado.

| Risco | O que muda |
| --- | --- |
| `alto` | A entrada no 9 grava `seguranca` exigida, e ela **não sai por `nao-coberta`** no `concluir`. O portão `sast` também não sai por `nao-coberta` no 8→9. Sem `[gates] sast` declarado, a entrada no 9 avisa. |
| `padrao` | O de sempre. Atividade sem `--risco` conta como `padrao`, e o `iniciar` avisa. |
| `baixo` | Nada é cortado. É declaração, e as métricas separam por ela. |

**Recusas que o `--forcar` não atravessa:** `alto` em trilha que implementa sem
step 9 (`ultra-rapida`), porque o código iria da escrita direto à pessoa; e
`baixo` com superfície marcada, que se contradiz. As duas saídas são mudar a
trilha ou o risco, e as duas ficam escritas. `padrao` com superfície marcada e
`baixo` em trilha longa abrem com aviso.

Mudar o risco depois é `risco <id> --nivel <novo> --nota '<por quê>'`. Subir
para `alto` com o 9 já em curso grava a exigência que a entrada no 9 teria
gravado. O `percurso` das métricas conta a taxa de bug por risco, ao lado da
taxa por trilha.

**A perna sombra não liga no risco alto.** Os achados dela não entram na
consolidação: ela mede o revisor, não protege a atividade. O revisor de outro
modelo, que protegeria, é outra mudança.
