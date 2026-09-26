# Especialidade: desenho de tela

`$PACOTE/references/screen-specification.md` diz **o que** precisa estar
especificado. Isto é sobre **como** desenhar bem o que vai ali.

## Antes do primeiro traço

Uma tela bonita que não parece do produto é retrabalho. Levante, sempre:

- Biblioteca de componentes em uso, e quais componentes já existem para
  formulário, tabela, filtro, modal, aviso.
- Tokens de cor, tipografia e espaçamento.
- **Duas ou três telas existentes do mesmo domínio.** Veja como elas resolvem
  estado vazio, erro e confirmação. Esse é o padrão real do produto, mais
  confiável que qualquer documento.

Quando precisar de algo que não existe, **pergunte** em vez de introduzir. Um
componente novo é decisão de arquitetura de frontend, não de protótipo.

## Hierarquia

O olho encontra em ordem: posição, tamanho, peso, cor. Nessa ordem.

- Uma ação primária por tela. Se há duas concorrendo, o usuário não tem ação
  primária — tem duas secundárias.
- A informação que responde "por que estou aqui" fica acima da dobra.
- Agrupe por significado, não por tipo de campo. Formulário organizado por
  "todos os selects juntos" é organizado para quem construiu.

## Formulário

- **Uma coluna.** Múltiplas colunas quebram a ordem de leitura e o preenchimento
  por teclado. Exceção: pares curtos e obviamente relacionados, como cidade e
  estado.
- Rótulo **acima** do campo, sempre visível. `placeholder` como rótulo some
  quando o usuário digita, e some para leitor de tela.
- Marque o **obrigatório**, não o opcional — quando quase tudo é obrigatório,
  inverta e diga na abertura.
- Agrupe em blocos com título quando passar de sete ou oito campos.
- Validação ao **sair do campo**, não a cada tecla. Erro que aparece enquanto se
  digita acusa antes de a pessoa terminar.
- Mensagem de erro **ao lado do campo**, e diz o que fazer: "CPF deve ter 11
  dígitos" e não "CPF inválido".
- Botão de envio desabilitado durante o envio, com indicação — senão o duplo
  clique vira duplo registro.

## Lista e tabela

- Ordenação inicial é decisão de produto: qual a linha que o usuário procura
  primeiro?
- Coluna com número alinha à direita; texto à esquerda; data em formato fixo.
- Ação por linha some quando a permissão não permite — não fica desabilitada.
  Desabilitado revela a existência de algo que a pessoa não deveria saber que
  existe.
- Ação em massa precisa dizer **quantos** itens serão afetados antes de agir.
- Filtro aplicado fica visível, com como limpar. Filtro invisível faz o usuário
  concluir que o dado sumiu.

## Estado vazio

O mais esquecido, e o **primeiro** que o usuário encontra no dia em que começa.

Distinga os dois: "ainda não existe nada" pede explicação e a ação para criar o
primeiro. "O filtro não achou nada" pede o caminho de limpar o filtro. Usar a
mesma tela para os dois confunde quem chegou agora e quem está buscando.

## Carregando

- Bloqueie a região que muda, não a tela inteira.
- Esqueleto quando a estrutura é previsível; indicador quando não é.
- Abaixo de um instante curto, não mostre nada — piscar é pior que esperar.

## Erro e confirmação

Mensagem de erro tem três partes: **o que houve**, **por que**, **o que fazer**.
Sem a terceira, é só um aviso.

Confirmação de ação destrutiva diz **o que se perde**, não "tem certeza?". E o
botão nomeia a ação — "Excluir pedido", não "OK". Botão genérico faz a pessoa
confirmar sem ler.

## Acessibilidade, o piso

- Rótulo associado ao campo, não só visual.
- Foco visível, e ordem de tabulação que segue a leitura.
- Contraste que sobreviva a uma tela ruim em sala clara.
- Cor nunca é o único portador de significado — erro tem ícone ou texto.
- Alvo de toque grande o bastante para o dedo, não só para o cursor.

## Texto é produto

Rótulo, mensagem, estado vazio e confirmação são conteúdo. Escreva-os na
especificação, na língua do produto, com as palavras que o domínio usa. Deixar
"mensagem apropriada" empurra decisão de produto para quem está implementando.

## Diga o que você inventou

Ao entregar, separe o que veio de padrão existente do que **você criou**. O
portão humano do step 7 precisa saber onde olhar com mais atenção — e o que uma
IA inventou a partir de texto é exatamente onde.
