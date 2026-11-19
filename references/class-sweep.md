# O achado é a classe, não a linha

Um defeito sério quase nunca está num lugar só. Ele está num **mecanismo** que a
entrega usou em vários pontos. Quando a revisão reporta uma ocorrência, o step 8
conserta aquela, a próxima volta acha a segunda, e o portão humano devolve de
novo.

Foi o que aconteceu na 1101 (gateway da Globex). O step 9 achou uma
observação de disco rodando em thread virtual (V2-01). O step 8 corrigiu aquela.
O portão 10 devolveu duas vezes com a mesma classe em outros pontos (V3-01 e
V4-01). Cada devolução custou uma volta inteira de desenvolvedor e de revisão.

## A regra, para quem revisa

Para todo achado `bloqueia` ou `alta`, antes de registrar:

1. **Nomeie o mecanismo numa frase genérica**, sem o nome da classe ou do
   arquivo. Escreva *"I/O bloqueante dentro de thread virtual"*, *"valor do
   usuário montado em SQL sem parâmetro"*, e não *"o FooService.bar não faz Z"*.
   O nome genérico é o que permite procurar.
2. **Procure todas as ocorrências que a entrega alcança.** Use o `grep`, a
   leitura de quem chama e os caminhos que passam pelo mesmo ponto. **Cite o
   comando.**
3. **Registre um achado só**, com todos os pontos em *Onde*, e descreva a
   correção pela classe, isto é, o que precisa valer em todos os pontos. Não a
   descreva pela linha.

Se a varredura não coube no seu orçamento, diga quais caminhos ficaram sem
olhar. Meia varredura declarada vale mais que varredura completa presumida.

`baixa` não precisa de varredura, porque não volta ao step 8.

## Na volta de verificação

Quando o step 9 volta depois de uma correção, cada frente que reprovou recebe a
lista de achados corrigidos e o intervalo de commits da correção. Ela faz três
coisas, e nada mais:

1. **Refaz a varredura de cada classe corrigida**, com o mesmo comando, e diz se
   a correção fecha todos os pontos. Ponto que sobrou é o mesmo achado, ainda
   aberto. Não conta como achado novo.
2. **Lê as linhas que a correção mudou**, à procura de `bloqueia` ou `alta`
   introduzido por elas.
3. **Não relê o que não mudou.** Um `baixa` novo vai à lista do portão 10 e não
   volta ao step 8.

## Para quem corrige (step 8)

Um achado com classe se corrige **pela classe**. A correção faz valer a regra que
o achado descreve em todos os pontos listados. Se a correção achar mais um
ponto, ele entra na mesma correção, porque é o mesmo achado. Corrigir só a linha
citada, quando o achado nomeia uma classe, é o que traz a devolução de volta.

A correção que ficou como regra do projeto vai para o registro de classes
(`defect-classes.md`). Essa é a memória entre atividades; esta regra é a
memória dentro de uma.

## Como isto foi calibrado

Em novembro de 2026, o replay às cegas da 1101 repetiu a volta de verificação
com esta regra: o revisor recebeu só o V2-01. Ele reabriu pela classe, listou os
pontos do V3-01 e do V4-01, propôs a mesma correção que o projeto acabou
fazendo duas devoluções depois e confirmou o mecanismo por execução. As duas
devoluções do portão 10 teriam caído numa volta só.

No mesmo exercício, juntar as frentes de código, SDD e negócio num revisor único
foi testado e **reprovado**. Em três entregas, ele não chegou a nenhum dos seis
achados altos de leitura das frentes separadas. A frente de negócio separada,
rodada de novo na 1102, chegou a dois deles. A regra da classe vale **dentro
de cada frente**. Ela não autoriza fundir frentes.
