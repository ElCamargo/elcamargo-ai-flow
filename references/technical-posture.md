# Postura padrão, quando o projeto não declara

O pacote roda em projeto que já tem convenção escrita e em projeto que não tem
nada. **Quando há convenção declarada, ela manda** — leia `docs.convencoes` do
config e siga. Este documento é o que vale no silêncio.

Não é preferência de estilo. É o conjunto de posturas que, erradas, custam caro
e tarde.

## Reversibilidade primeiro

Toda mudança de estrutura tem duas partes: como aplicar e **como voltar**. Se a
volta não foi pensada, a mudança não está especificada.

- Prefira **aditivo** a destrutivo. Adicionar coluna, rota ou evento é
  reversível; remover ou renomear não é.
- Uma remoção acontece em dois passos separados no tempo: parar de usar, e
  depois remover. Nunca no mesmo.
- Migração de dado existente precisa da pergunta que quase ninguém faz:
  **quantos registros existem hoje?** Uma migração que roda em 200 linhas e
  outra que roda em 20 milhões não são a mesma decisão.

## Compatibilidade

Se algo fora do seu controle consome o que você está mudando — outra aplicação,
um cliente, um job —, você tem duas saídas: manter compatível, ou versionar.
Quebrar e avisar depois não é uma delas.

Ao mudar contrato: campo novo é opcional; campo que vira obrigatório precisa de
transição; campo removido some depois que ninguém mais o lê.

## Repetição é retentativa

Qualquer coisa que pode ser reentregue — evento, webhook, job, requisição com
retry — **será** executada mais de uma vez. Especifique o comportamento na
segunda vez, sempre. Se a segunda execução duplica um registro ou soma um valor
duas vezes, o defeito já existe, só não apareceu ainda.

## Autorização é explícita

Nunca deixe "quem pode fazer isso" implícito. Para cada operação: quem pode, onde
a verificação acontece, e o que retorna quando não pode.

A verificação vive no servidor. Interface que esconde botão é conveniência, não
controle — e um identificador de outro escopo passado direto na rota é o teste
que sempre vale fazer.

## Erro é comportamento especificado

O caminho de falha faz parte da especificação, não é detalhe de implementação.
Para cada operação: o que acontece com entrada inválida, com recurso
inexistente, com recurso de outro escopo, com concorrência, e com a dependência
externa fora do ar.

Erro genérico onde a causa era conhecida é perda de informação — e é o que
transforma um incidente de dez minutos em uma tarde.

## Fatia pequena

A unidade de entrega é a **fatia vertical**: uma coisa que funciona de ponta a
ponta e pode ser revisada sozinha. Melhor três fatias que entram do que uma que
fica aberta duas semanas.

Se a especificação não cabe numa revisão que uma pessoa consegue fazer numa
sentada, ela é grande demais — e o defeito vai passar na revisão por cansaço,
não por qualidade.

## O que fica registrado

Ação relevante deixa rastro de **quem fez, quando, e sobre o quê**. E o que
nunca entra em log: credencial, token, dado pessoal, dado financeiro. Dado
pessoal em log é incidente, não descuido.

## Teste que prova

Um teste que passa com a implementação removida não prova nada. Para cada
requisito, o teste precisa **falhar** se o comportamento quebrar.

Cubra o limite, não só o caminho feliz: vazio, nulo, zero, duplicado, sem
permissão, concorrente. É onde o defeito mora.
