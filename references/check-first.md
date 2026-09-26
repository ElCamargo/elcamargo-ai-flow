# Verificar antes de especificar

Antes de gastar o fluxo numa demanda, confirme que ela **se sustenta**. Três
verificações baratas, feitas no step 1, que evitam gastar dez steps no que não
precisava de nenhum.

A ordem importa: a mais barata primeiro. E a mais barata de todas é um comando.

## 0. A varredura, antes de qualquer leitura

```bash
python3 $PACOTE/tools/already-exists/already_exists.py --demanda <texto ou arquivo> --card <id>
```

Segundos, e responde as três perguntas de baixo ao mesmo tempo: que atividades
já rodaram sobre estes conceitos, que especificação já é **dona** do
comportamento, quanto dela a demanda já está coberta, onde o código vive, e se
alguma decisão antiga bate.

**Por que isto vem antes.** Sem a varredura, cada step redescobre o mesmo por
leitura — e o custo do descobrimento fica proporcional ao MÓDULO, quando
deveria ser proporcional ao **delta**. Uma demanda que acrescenta um campo a um
painel pronto não pode custar o mesmo que especificar o painel.

**O que a saída é.** Sinal, não decisão. Ela acha palavra; só a leitura acha
comportamento, e o produto pode ter a coisa com outro nome. Use-a para saber
**onde olhar**, e olhe.

## Os quatro desfechos

A varredura mais a sua leitura levam a um destes. Cada um muda o fluxo inteiro,
não só o step 1.

| Desfecho | Sinal | O que muda |
| --- | --- | --- |
| **Assunto novo** | nenhuma spec passa do limiar | trilha inteira, como sempre |
| **Complemento** | uma spec cobre quase tudo, sobram poucos conceitos | **o escopo é o delta** — ver abaixo |
| **Já feito** | uma spec cobre tudo e o código existe | aponte onde está e **encerre antes de abrir** |
| **Já rejeitado** | bate na memória de rejeição | mostre a decisão antiga e pergunte se ainda vale |

## O complemento é o caso que mais se desperdiça

É o mais comum num produto vivo, e o que o fluxo mais facilmente trata como se
fosse novo — refazendo análise, matriz e revisão de um módulo inteiro para
acrescentar dois requisitos.

Quando o desfecho é complemento, **declare a base e o delta na nota de
abertura**, nestas palavras:

> Complemento de `CAM-002`. O delta é: filtro por categoria, e ordenação por
> data de encerramento. O resto do painel já está especificado e implementado.

Isso não é formalidade — é o que faz os steps seguintes custarem o que devem:

- **O step 2** revisa a análise **do delta**, não do módulo. A matriz cobre os
  requisitos novos, e referencia a spec existente para o resto.
- **O step 3** *atualiza a SDD que já é dona*. Não escreve uma nova. Uma SDD
  nova para algo que já tem dono espalha a verdade em dois lugares, e a próxima
  pessoa acha as duas.
- **O step 4** confere o delta contra a matriz do delta.
- **O step 9** revisa o diff, que já é o delta por natureza.

Sem a declaração, cada step decide sozinho o escopo — e decide largo, porque
largo parece mais seguro. Largo aqui não é mais seguro: é mais caro, mais lento,
e produz especificação duplicada que alguém vai ter que reconciliar depois.

## 1. Já foi rejeitado?

Leia a memória de rejeição — ver `rejection-memory.md`. Se o conceito já foi
recusado, **mostre a decisão antiga e pergunte se ela ainda vale**, em vez de
re-analisar do zero.

Um pedido que volta não é necessariamente um erro: o contexto muda, e a decisão
de seis meses atrás pode não valer mais. O erro é decidir de novo sem saber que
já se decidiu uma vez.

## 2. Já está implementado?

A varredura do passo 0 já lhe deu os candidatos. O que falta é **confirmar por
leitura** — ela acha palavra, não comportamento.

Procure por **conceito de domínio**, não pelas palavras do reportador. Quem
reporta descreve o que quer, com o vocabulário dele; o produto pode já ter
aquilo com outro nome.

Se já existe, o desfecho é um apontamento de onde está — e a atividade encerra
antes de abrir. Isso **não** entra na memória de rejeição: é funcionalidade
construída, não pedido recusado, e registrá-la ali envenenaria a busca futura.

## 3. A alegação se confirma?

Só para **bug e correção**. Para pedido de funcionalidade não há o que
reproduzir.

Reproduza pelos passos do reportador. O resultado é um dos três, e os três são
respostas legítimas:

| Resultado | O que fazer |
| --- | --- |
| **Confirmado** | Registre o caminho de código onde acontece. A atividade segue, e a especificação nasce muito mais forte. |
| **Não reproduz** | Não abra trilha `curta`. Volte ao reportador com o que você tentou, exatamente. |
| **Sem detalhe para tentar** | **É o sinal mais forte de que falta informação.** Pergunte antes de abrir a atividade. |

O terceiro caso é o que mais se disfarça. "Não consegui reproduzir" e "não tinha
como tentar" parecem a mesma coisa e não são: o primeiro é um resultado, o
segundo é uma pergunta não feita.

## Por que no step 1

A trilha `curta` vai do step 1 direto ao 8. Sem esta verificação, o fluxo
implementa a correção de um bug que ninguém confirmou existir — e o developer
"conserta" o que não estava quebrado, num código que passa a carregar a mudança
para sempre.

E o resultado **muda a trilha**: um bug que não reproduz não é `curta`, é
pergunta ao reportador. Verificar depois de escolher a trilha é verificar tarde.

## Profundidade

Rasa, de propósito. A pergunta é *"isto é real, e mais ou menos onde vive?"* —
não *"qual é a causa raiz?"*.

Se o bug não reproduz em alguns minutos, o movimento honesto é voltar ao
reportador. Investigação de causa raiz é trabalho do step 8, depois de alguém ter
decidido que vale investir nele.

## O que registrar

O resultado da verificação vai na nota de abertura da atividade, sempre — mesmo
quando é "confirmado, sem observação". Ele é o que justifica a trilha escolhida,
e é a primeira coisa que alguém procura quando a atividade dá errado lá na
frente.
