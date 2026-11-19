# Fluxo · As duas devoluções

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## As duas devoluções

Um step pode receber trabalho de volta por dois motivos, e tratá-los igual
estraga os dois.

**Devolução por defeito.** O step 4 devolve ao 3, o step 9 devolve ao 8. A
entrega está **errada**. O escopo não mudou — mudou que alguém achou um problema
nela.

**Devolução por escopo.** Um portão humano devolve: o 5 ao step 3, o 7 ao step
6, o 10 ao step 8. A entrega **não está errada**. A pessoa quer mais.

| | por defeito | por escopo |
| --- | --- | --- |
| Quem devolve | step 4 ou step 9 | portão 5, 7 ou 10 |
| O que a devolução nomeia | um **defeito** | um **trabalho** |
| A parte já aceita | volta a ser revisada — a correção pode tê-la quebrado | **não se re-litiga** |
| A parte nova | não há | revisão **completa**, não verificação |
| O contador de voltas | avança | **reinicia** |

O contador é a parte concreta. O step 9 descobre em que volta está contando
quantas vezes o histórico registra a entrada nele, e para na terceira — porque
revisor que revisa de novo o mesmo diff **fabrica achado quando os reais
acabam**. Essa regra é certa para devolução por defeito e **errada** para
devolução por escopo: o trabalho novo nunca foi revisado por ninguém, e recusar
revisá-lo por causa de um contador entrega código sem revisão nenhuma.

Quem devolve declara qual das duas é, na nota. Sem isso o step seguinte não tem
como saber, e vai adivinhar.

**Qual é a parte aceita não se adivinha também.** A saída do portão grava o que
ele viu, e `desde-aprovacao <id>` mostra o diff de cada artefato e o `--stat` do
código contra esse registro. Até a 2.60.0 a regra existia sem nada que separasse
uma parte da outra, e quem voltava ao portão relia o documento inteiro.

### O step 4 tem saída, não limite

> Desde a 2.69.0 a conferência roda dentro do step 3, e a regra vale igual
> para ela: duas voltas, e a divergência que sobrevive vai ao portão 5 com as
> duas posições escritas.

O step 9 para na terceira volta porque revisor que relê **o mesmo diff** fabrica
achado quando os reais acabam. O step 4 relê um documento **que mudou** a cada
volta, e o mesmo raciocínio não se aplica — na POC, cada volta achou defeito
real, inclusive a segunda, que descobriu que a própria correção tinha quebrado
duas seções.

Então o step 4 não ganha limite. Ganha **saída**.

**Quando o step 4 reprova a mesma especificação pela terceira vez, a terceira
passada não é revisão — é sinal de que falta uma decisão que nenhum dos dois
pode tomar.** Aconteceu com uma pergunta de arquitetura: decidir dentro ou fora
da transação. O step 3 escolheu, o step 4 mostrou que a escolha não tinha
chegado a duas seções, e uma quarta volta só produziria a mesma discussão com
outras palavras.

Nesse ponto o step 4 **escala ao portão 5**, com as duas posições escritas:

- o que o step 3 sustenta, e por quê;
- o que o step 4 sustenta, e por quê;
- o que muda em cada caminho, em consequência observável;
- e a informação que falta para decidir, se houver.

Quem decide é a pessoa. É para isso que o portão 5 existe — e uma divergência
técnica entre dois agentes é exatamente o tipo de coisa que ele deveria receber,
em vez de ficar circulando entre eles até um ceder por cansaço.

**A escalada não é fracasso do laço.** Duas voltas que acharam defeito real
valeram o que custaram; a terceira é que não valeria.

### O crescimento precisa ficar visível

O fluxo não briga com o humano. Se a pessoa quer mais, ela manda, e o fluxo
faz — ela é quem responde pelo produto.

Mas **registre o que foi acrescentado em cada volta**, na nota da atividade. Três
devoluções humanas seguidas na mesma atividade não são sinal de que o fluxo está
funcionando: são sinal de que **a fatia foi mal escolhida**, e a essa altura é
mais barato fechar esta e abrir outra do que continuar empilhando escopo sobre
uma revisão que já aconteceu.

Quem lê a atividade depois precisa conseguir ver o que era o card e o que virou.
