# Especialidade: revisão de código

O que um bom revisor de código sabe, e que não está no linter. As convenções do
projeto mandam quando existem; isto é o que vale no silêncio, e o que nenhum
projeto declara porque parece óbvio até alguém errar.

## Nome

O nome é a documentação que não desatualiza. Um nome errado custa mais que um
comentário ausente, porque ele **mente ativamente**.

- Nome diz **o que a coisa é ou faz**, não como foi implementada.
  `listaOrdenada` envelhece quando a ordenação muda; `participantes` não.
- Booleano lê como afirmação: `estaAtivo`, `temSaldo`, `podeEditar`. Nunca
  negado: `naoEstaInativo` obriga o leitor a fazer dupla negação.
- Função que retorna diz o que retorna; função que age diz o que faz. Uma função
  chamada `validarSaldo` que **também debita** é um defeito de nome que vira
  defeito de comportamento.
- Abreviação só quando é o vocabulário do domínio. `cpf` sim, `cmpnhPrtcpnt` não.
- O mesmo conceito tem **um** nome no código inteiro. Três nomes para a mesma
  coisa é o sinal mais confiável de que ninguém entende o domínio.

## Tamanho e forma

Não existe número mágico. Existem sinais:

- **A função não cabe na tela** e você precisa rolar para entender o começo
  enquanto lê o fim. Provável que faça mais de uma coisa.
- **O nome precisa de "e"** — `salvarEEnviarEmail` é duas funções.
- **Aninhamento acima de três níveis.** Quase sempre há uma saída antecipada ou
  uma extração escondida ali.
- **Muitos parâmetros**, principalmente booleanos. `criar(x, true, false, true)`
  é ilegível no ponto de chamada; um objeto nomeado resolve.
- **O arquivo virou depósito.** Quando ninguém acha nada sem busca, o custo já é
  real.

O critério final é sempre o mesmo: **alguém que não escreveu isso conseguiria
dar manutenção daqui a seis meses?**

## Duplicação

A regra prática é **três**. Duas ocorrências parecidas podem ser coincidência;
três é padrão.

E duplicação nem sempre é defeito:

- Duas coisas que **parecem** iguais e mudam por motivos diferentes devem
  continuar separadas. Unificá-las cria acoplamento entre domínios que não têm
  relação, e a próxima mudança em um quebra o outro.
- Abstração prematura custa mais que repetição. Se você não sabe qual é a
  variação, espere a terceira aparecer — ela mostra.

O que **é** defeito e passa despercebido: código novo que duplica um utilitário
que **já existe** no projeto. Antes de apontar duplicação, procure se já há
helper fazendo aquilo — e antes de aceitar código novo, procure também.

## Erro

- **Exceção engolida** — `catch` vazio, ou que só registra e segue. É o defeito
  que transforma incidente de dez minutos em uma tarde.
- **Erro genérico onde a causa era conhecida.** Se o código sabia que era CPF
  inválido, propagar "erro ao processar" apaga informação de propósito.
- **Erro tratado no lugar errado** — capturado fundo demais, onde não há contexto
  para decidir, ou raso demais, onde a operação já foi parcialmente aplicada.
- **Caminho de falha sem teste.** O caminho feliz sempre tem teste; o de erro é
  onde o defeito vive.

## Estado e efeito

- Função que parece pura e **muta o argumento** é armadilha. Se muta, o nome
  precisa dizer.
- Estado compartilhado mutável entre requisições ou entre execuções é defeito,
  não estilo.
- Ordem de efeito importa: validar tudo **antes** de aplicar qualquer coisa,
  para não deixar meia operação aplicada quando o terceiro passo falha.

## Complexidade acidental

- Camada que só repassa. Se um método só chama outro com os mesmos argumentos,
  ele custa leitura e não paga.
- Generalização para um caso que não existe. Ponto de extensão sem segundo
  consumidor é peso morto.
- Configuração para algo que nunca vai variar.
- Comentário explicando código confuso — quase sempre o código é que precisava
  mudar. Comentário bom explica **por que**, não o que.

## Código de teste também é código

Teste ilegível não é revisado, e teste não revisado apodrece:

- Nome do teste diz o cenário e o esperado, não `test1`.
- Um comportamento por teste. Teste que assere sete coisas falha sem dizer qual.
- Preparação repetida em vinte testes pede um construtor de dados.
- Teste que depende de outro teste, ou da ordem de execução, é defeito.

## O que NÃO reportar

Preferência de estilo que o linter cobre ou que o projeto não declarou. "Eu faria
diferente." Sugestão de refatoração ampla numa entrega pequena — ela transforma
uma correção de duas linhas num risco novo.

Cada achado seu custa uma volta ao desenvolvedor. Gaste esse orçamento com
defeito, não com gosto.
