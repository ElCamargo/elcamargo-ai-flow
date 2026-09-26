# Memória de rejeição

O que o produto **decidiu não fazer**, e por quê. Sem isso, um pedido recusado
volta em seis meses, ninguém lembra que foi recusado, e a análise inteira roda de
novo — às vezes chegando à decisão oposta, sem que ninguém perceba que houve uma
primeira.

## Onde fica

`docs.fora_de_escopo` do config — e o padrão é **dentro do repositório do
projeto**, não no `.agents`.

Isso é deliberado e contraria o resto do pacote. Todo o ferramental de IA fica
fora do versionamento do cliente, porque é ferramenta. A memória de rejeição não
é ferramenta: é **decisão de produto**. Ela precisa sobreviver à troca de
ferramenta, à saída de quem a tomou, e a alguém remover o `.agents` inteiro.

## Um arquivo por conceito, não por pedido

`preco-por-usuario.md`, não `card-1042.md`.

O mesmo conceito volta com nomes diferentes, de pessoas diferentes, ao longo de
anos. O arquivo é do conceito; os pedidos que o tocaram são uma lista dentro
dele.

```markdown
# Cobrança por usuário ativo

**Decidido em** 2026-03-14 · **por** produto · **status** rejeitado

## O que foi pedido

Cobrar do cliente por usuário ativo no mês, em vez do valor fixo mensal
por plano.

## Por que não

O contrato vigente com os clientes maiores tem valor fechado por plano, e
mudar a base de cobrança exigiria renegociar todos eles. O ganho estimado não
cobre o risco comercial.

## O que mudaria a decisão

Um contrato novo já assinado nessa base, ou a renegociação da carteira grande
por outro motivo.

## Pedidos que chegaram a este conceito

| Quando | Origem | Como foi pedido |
| --- | --- | --- |
| 2026-03-10 | Card 1010 | "Cobrança variável por usuário" |
| 2026-08-02 | Card 1075 | "Plano por uso" |
```

A seção **"o que mudaria a decisão"** é a mais importante e a mais esquecida. Sem
ela, a memória vira um "não" perpétuo, e o produto para de evoluir por inércia
documentada.

## Como consultar

**Antes de analisar qualquer coisa**, e por **conceito**, não por palavra. Quem
pede usa o vocabulário dele: "tema noturno", "modo escuro" e "fundo preto" são o
mesmo conceito com três nomes.

Leia o diretório inteiro antes de avaliar. São arquivos curtos, e o custo de ler
todos é menor que o de rodar uma análise inteira sobre algo já decidido.

## Quando bate

**Não recuse sozinho.** Mostre a decisão antiga — o que foi rejeitado, quando,
por quem, por quê, e o que a mudaria — e **pergunte se ela ainda vale**.

Duas saídas legítimas:

- **Ainda vale** — a atividade encerra antes de abrir, e o pedido novo entra na
  tabela do arquivo existente.
- **Não vale mais** — o contexto mudou. A atividade segue normalmente, e o
  arquivo é atualizado com a reversão, a data e o motivo. **Nunca apague o
  histórico**: "decidimos não, e depois decidimos sim" é informação; um arquivo
  que só mostra a decisão atual perde o que ensina.

## Quando escrever

Só quando um pedido é **recusado por decisão de produto**.

Não escreva quando:

- **Já está implementado.** É funcionalidade construída, não pedido recusado.
  Registrar ali envenena a busca: da próxima vez, algo que existe aparece como
  rejeitado.
- **Ficou fora do escopo desta fatia**, mas está previsto. Isso é a lista de
  fora de escopo da própria SDD, com destino — outra coisa.
- **Foi adiado sem decisão.** Adiar não é recusar. Se não houve decisão, não há
  o que registrar; há uma pendência.

A distinção entre "recusado" e "adiado" é a que mais se perde, e é a que faz a
memória valer ou virar um cemitério de ideias que ninguém consultou.
