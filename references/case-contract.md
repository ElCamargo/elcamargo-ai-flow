# O contrato de casos

Um arquivo por atividade, `atividades/<id>-casos.json`, com um caso por critério
testável da SDD de sistema. Ele existe porque "cada requisito tem teste que o
prova" era frase de skill, e o step 9 conferia por leitura se a frase tinha sido
cumprida. Agora o step 8 deixa a prova gravada, e o 9 confere a prova.

## Quem escreve o quê

| Campo | Quem escreve | De onde |
| --- | --- | --- |
| `id`, `texto`, `sha`, `fonte` | `matrix.py casos gerar` | a SDD, reextraída |
| `vermelho` | `matrix.py casos vermelho` | a saída da suíte **antes** da implementação |
| `passa`, `teste` | `matrix.py casos verde` (o `flow_state gates` chama, depois do `test`) | a saída da suíte e o código de saída |

**O modelo não escreve nenhum deles.** O hook de PreToolUse recusa Edit e Write
no `-casos.json`, em qualquer janela. Um contrato que o próprio implementador
marca como cumprido é a frase de skill de antes, com outra extensão.

## Os casos

`gerar` lê `CT-NN` da SDD; sem nenhum `CT`, lê `CA-NN`. `--prefixos` muda isso.
O bloco de cada caso vai até o próximo título de mesmo nível (quando o id está
num título) ou até a linha em branco (quando está numa tabela ou lista). A
impressão (`sha`) é desse bloco: se a SDD mudar depois, o `conferir-testes`
acusa, e `gerar --refazer` refaz guardando o estado só do caso cujo texto não
mudou.

Trilha `curta` não tem SDD, e portanto não tem contrato. O card continua sendo a
especificação, e o step 9 confere por leitura.

## Como um teste cita o caso

O id no nome do teste, ou num comentário colado acima dele:

```ts
it('CT-03 recusa cupom vencido', ...)

// CT-04
it('aplica o teto de desconto', ...)
```

O comentário vale até o primeiro não-comentário acima do teste, para não herdar
o id do teste vizinho. Um arquivo que nem sobe (erro de coleta, o caso comum da
fase vermelha, porque o teste importa o que ainda não existe) conta como falha
de todo caso citado nele.

## A fase vermelha

Escreva os testes, rode a suíte **sem** a implementação e passe a saída para
`casos vermelho`. Cada caso sai como:

- `[vermelho]` — falhou, que é o esperado.
- `[sem teste]` — nenhum teste cita o id.
- `[PASSOU]` — passou sem a implementação. Ou o teste não exercita o
  comportamento, ou o comportamento já existia. Diga qual no resumo do step.

Ela substitui a conferência "mental" de apagar a implementação e ver se o teste
continua passando: a falha agora fica registrada, com a linha da suíte.

## Quando um caso passa

`verde` marca `passa: true` quando um teste cita o id e:

- a suíte saiu com 0; ou
- a suíte saiu com outro código, nomeou as falhas, e este caso não está entre
  elas.

Saída vermelha **sem falha nomeada** (o runner caiu, o formato não casou) não
prova caso nenhum. Falha conhecida da catraca deixa o **portão** `ok`, mas não
prova o **caso** que ela atinge: o caso continua sem prova.

## O step 9

```bash
python3 $PACOTE/tools/matrix/matrix.py conferir-testes --atividade <id> --raiz . --registrar
```

`[ALTO]`: caso na SDD que não está no contrato, caso no contrato que saiu da
SDD, texto diferente, nenhum teste citando o id, `passa` falso. `estrutural`: a
SDD mudou depois do contrato, ou caso sem fase vermelha.

## Teste baseado em propriedade

Opcional. Onde o caso é uma regra sobre uma faixa de entradas (arredondamento,
limite, ordenação), um teste com fast-check ou Hypothesis prova mais que três
exemplos. Ele cita o id como qualquer outro.

## O que isto NÃO prova

Que o teste exercita o comportamento que o caso descreve. O contrato prova que
existe um teste com o id do caso, que ele falhou antes e passou depois. Um teste
com o nome certo e a asserção errada atravessa tudo isso, e é por isso que a
frente de qualidade continua lendo os testes e mutando o código.
