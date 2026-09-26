# O que é uma tela especificada

Usado pelo step 6 (que decide), pelo step 8 (que implementa) e pelos dois
subagentes de UX. Uma tela "especificada" que só descreve o caminho feliz manda o
desenvolvedor inventar o resto — e ele inventa diferente do que o negócio queria.

## Os estados, todos

Toda tela tem estes. A especificação diz o que aparece em cada um; "não se
aplica" é resposta válida, ausência não é.

| Estado | A pergunta |
| --- | --- |
| **Inicial** | O que aparece antes de qualquer ação? Há filtro pré-aplicado? |
| **Carregando** | Bloqueia a tela, ou só a região? Há esqueleto? |
| **Vazio** | Nunca teve dado, ou o filtro não achou? São mensagens diferentes. |
| **Com dado** | Ordenação inicial, paginação, quantos por página |
| **Erro** | Do servidor, da rede, de validação. Cada um com sua mensagem. |
| **Sem permissão** | Some, ou aparece desabilitado com explicação? |
| **Parcial** | Carregou parte e falhou o resto — o que o usuário vê? |

O estado **vazio** é o mais esquecido e o que o usuário encontra primeiro, no dia
em que começa a usar.

## Por elemento

Para cada campo: rótulo, tipo, obrigatoriedade, valor padrão, máscara,
limite, e **a mensagem de cada validação**. "Validar o CPF" não é
especificação; o texto que o usuário lê quando erra é.

Para cada ação: o que faz, se pede confirmação, o que aparece durante, o que
aparece depois, e para onde leva. Ação destrutiva sempre confirma, e a
confirmação diz **o que se perde**.

## Permissão muda a tela

Se o produto tem perfis, diga como cada um vê a tela. O padrão a seguir:
elemento que a pessoa não pode usar **não aparece**, em vez de aparecer
desabilitado — desabilitado revela a existência de algo que ela não deveria
saber que existe.

E a regra vale no servidor também: esconder na interface não é controle.

## Acessibilidade, o mínimo

Sem convenção declarada no projeto, o piso é este:

- Todo campo tem rótulo associado, não só *placeholder*.
- Foco visível e navegação por teclado em toda ação.
- Contraste que sobreviva a uma tela ruim em sala clara.
- Cor nunca é o único portador de significado — erro tem ícone ou texto.
- Mensagem de erro fica ao lado do campo, não só num aviso no topo.

## Responsivo

Diga o que acontece quando não cabe. Tabela vira cartão, ou rola? Filtro vira
gaveta, ou empilha? Sem essa decisão, cada tela resolve de um jeito e o produto
fica com três padrões.

## Texto é especificação

Rótulo, mensagem de erro, estado vazio e confirmação são conteúdo, não
decoração. Escreva-os na especificação, na língua do produto. Deixar "mensagem
de erro apropriada" é empurrar para o desenvolvedor uma decisão de produto.

Mensagem de erro diz **o que fazer**, não só o que houve. "CPF inválido" é pior
que "CPF deve ter 11 dígitos".
