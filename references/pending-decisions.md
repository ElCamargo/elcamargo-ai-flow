# Como escrever uma decisão que alguém consegue decidir

Toda skill do fluxo chega em pontos que ela **não pode** resolver sozinha:
cardinalidade comercial, prioridade entre requisitos que se excluem, custo que
só o negócio aceita pagar. Registrar isso como "pendente de decisão" e seguir é
metade do trabalho — e a metade fácil.

Uma pendência mal escrita volta como pergunta, atrasa o portão humano, e às
vezes é decidida errado porque quem decidiu não tinha o que precisava.

## O formato

Toda pendência tem **seis campos**. Faltando qualquer um, ela não está pronta.

| Campo | O que é | Erro comum |
| --- | --- | --- |
| **Pergunta** | Uma frase, fechada, respondível | Descrever o problema em vez de perguntar |
| **Por que existe** | O trecho da análise que a origina, citado | Afirmar sem mostrar |
| **Opções** | Duas ou mais, concretas e excludentes | "Definir o comportamento" não é opção |
| **Consequência** | O que muda no produto em cada opção | Falar de esforço técnico em vez de efeito |
| **Recomendação** | Qual você escolheria, e por quê | Não recomendar nada, por medo de influenciar |
| **Dono** | Quem tem autoridade para decidir | "O time" não decide nada |

E um sétimo campo quando for o caso: **bloqueia?** — se a implementação pode
começar sem a resposta, diga; se não pode, diga o que trava.

## Quando o defeito é composto

A regra da frase única não sobrevive a tudo. Há defeito que exige respostas
encadeadas — *"qual é a lista de status, o que muda cada um, e quais transições
existem?"* são três perguntas que ninguém responde isoladamente, porque a
segunda depende da primeira.

Quebrar isso em três pendências produz três decisões que ninguém toma sozinhas, e
o dono responde a primeira sem saber que vai ter que responder as outras duas.

Nesse caso, **uma pendência com sub-perguntas ordenadas**:

> **P-06 · O que define o ciclo de vida do pedido?**
>
> **a.** Qual é a lista fechada de status?
> **b.** O que cada status permite e impede?
> **c.** Quais transições existem, e quem as dispara?
>
> As três se respondem juntas — `b` depende de `a`, `c` depende de `b`.

Os seis campos continuam valendo para a pendência como um todo: as opções e a
recomendação cobrem o conjunto, não cada sub-pergunta.

O limite: **se as sub-perguntas se respondem independentemente, são pendências
separadas.** Encadeamento é o critério, não conveniência.

## Recomende

Não recomendar parece neutralidade e é omissão. Você leu a análise inteira, o
código e as decisões anteriores; quem decide, muitas vezes, não. Uma pendência
sem recomendação transfere para a pessoa o trabalho que era seu.

Recomende e mostre o raciocínio. Quem decide continua livre para discordar — e
agora discorda de algo, em vez de escolher no escuro.

## Exemplos

**Ruim:**

> Pendência: definir a cardinalidade entre forma de pagamento e cliente.

Não é pergunta, não tem opções, não tem consequência, não tem dono. Quem lê isso
responde "definam vocês".

**Bom:**

> **Um cliente pode ter mais de uma forma de pagamento ativa ao mesmo tempo?**
>
> A RN-07 diz "uma forma por cliente". O CT-03 descreve um cliente com cartão
> e boleto salvos simultaneamente. Os dois não podem ser verdade.
>
> - **N para 1** — cada cliente tem uma forma. O CT-03 descreve caso impossível
>   e precisa ser reescrito. O cliente que quiser trocar perde o crédito
>   acumulado na forma anterior, ou exige regra de migração de crédito.
> - **N para N** — cliente acumula formas. A RN-07 precisa ser reescrita, e o
>   extrato passa a somar créditos de origens diferentes, o que muda a tela de
>   crédito e o relatório de pagamentos.
>
> **Recomendação: N para N.** O CT-03 descreve o comportamento que o cliente
> espera, e a restrição da RN-07 aparece uma vez só no documento, o que sugere
> texto herdado e não decisão. O custo é a tela de crédito.
>
> **Dono:** negócio. **Bloqueia:** sim — o modelo de dados muda nas duas opções.

## Onde a pendência aparece

1. Na SDD, na seção de decisões pendentes, com os seis campos.
2. No relatório que vai ao humano, **na conclusão** — quantas bloqueiam.
3. No `--nota` do `avancar`, contada: `"3 pendências, 1 bloqueia"`.

Uma pendência que só existe no meio de um documento de 30 páginas não foi
comunicada. Ela precisa aparecer onde a pessoa decide olhar primeiro.

## Quando a contradição impede especificar

Há um caso em que a pendência não é um item da lista: ela é o motivo de o
documento não estar pronto. Duas fontes determinam comportamentos incompatíveis,
e **nenhuma leitura razoável do material fecha o resultado final**.

Aí a saída não é escolher a mais provável e seguir com a especificação em
`ready-for-review`. É:

- manter a SDD em **`draft`**, e dizer no status por quê;
- registrar a contradição como **bloqueio**, com os seis campos;
- **não inventar o resultado** — nem como pressuposto.

Um pressuposto é reversível e visível. Um resultado inventado para tapar
contradição não é nenhum dos dois: ele some dentro do texto, e o desenvolvedor
o implementa achando que foi decidido.

Uma SDD em `draft` com o bloqueio nomeado atravessa o portão humano como
pergunta. Uma SDD em `ready-for-review` construída por cima da contradição
atravessa como resposta — e ninguém olha duas vezes.

## Quando NÃO abrir pendência

- Quando a resposta está na análise e você não a procurou o bastante.
- Quando é decisão técnica sua: nome de tabela, estrutura de módulo, formato de
  índice. Abrir pendência disso empurra para a pessoa um trabalho que é seu.
- Quando você já decidiu e só quer chancela. Registre como decisão, com a
  justificativa, e siga.

Pendência é para o que **você não tem autoridade** de decidir, não para o que
você não teve vontade de decidir.
