# Ideias para a ferramenta, ainda não construídas

Nada aqui é contrato. São ideias decididas como direção, com o motivo e o jeito
de validar antes de virar padrão.

## Trilha de definição do projeto (`definicao`)

Anotada em 17/11/2026, a pedido do Ederson, ao receber uma demanda para avaliar
alguns pontos no projeto da Acme.

**O problema.** O pacote **lê** decisões de projeto (o step 3 confronta as ADRs
em `docs.adrs` e a memória de rejeição em `docs.fora_de_escopo`), mas nada no
fluxo as **produz**. Toda decisão nasce dentro de um card, fica na SDD daquele
card e não chega às demandas seguintes. Na fase B autônoma, cada decisão que
não está escrita vira uma escalada ao desenvolvedor. Uma decisão registrada uma
vez é uma escalada a menos em todo card depois dela.

**A forma.** Uma trilha própria, sem código, e não um step dentro de todo card:

1. **Briefing**: o que a pessoa trouxe, e o que o repositório já responde.
2. **Perguntas**: a IA levanta as questões em aberto, cada uma com opções reais
   conferidas no código e a consequência de cada.
3. **Conversa**: a pessoa, ou o cliente, fecha as decisões. Como num portão, em
   cards de pergunta.
4. **Registro**: ADR ou documento em `docs/`, com status, dono e o que ficou em
   aberto.
5. **Uso**: o step 3 dos cards seguintes confronta essas decisões, como já faz
   com as ADRs.

**Como validar antes de virar trilha.** Do mesmo jeito que a calibração do
step 9 na 2.70.0: rodar a demanda da Acme como piloto à mão, ver que
perguntas sobreviveram, que documento saiu e se o card seguinte de fato o usou.
Só depois disso escrever a skill e a trilha no `flow_state`.

## Depois da 3.0

A 3.0 fechou na 2.75.0. O que vem agora sai do uso, não de dedução: medir com o
`por_fase` o custo da fase A por card, quantas fases B fecham sem chamar a
pessoa, e se o WIP 3 se sustenta.

