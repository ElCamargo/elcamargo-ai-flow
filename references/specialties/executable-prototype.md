# Especialidade: o protótipo executável

O que o step 6 entrega ao step 8. **Não é uma figura, é código que compila** —
com os componentes reais do projeto e dados falsos.

A diferença importa: com uma figura, o desenvolvedor traduz e a tradução varia.
Com o protótipo, ele troca o dado falso pela API e move o componente. O tempo
dele vai para ligar dado, não para redesenhar tela.

## O que é entregue

Três coisas, e só a primeira migra para produção:

1. **Um componente puro** — recebe tudo por propriedade, não busca nada, não
   conhece rota. É o artefato que o step 8 move para dentro.
2. **Um arquivo de dados falsos** — cobrindo todos os estados, um por um.
3. **Uma rota descartável** que renderiza o componente com esses dados, para
   ver e fotografar. O step 8 apaga ao mover.

A separação existe porque o componente é o valor e a rota é andaime. Misturar os
dois entrega ao desenvolvedor algo que ele precisa desmontar antes de usar.

## Antes de escrever

Levante, sempre, e **cite o que encontrou** na entrega:

- Onde ficam os componentes do projeto, e quais já resolvem o que a tela pede.
  Tabela, filtro, formulário, diálogo, seleção — quase sempre já existem.
- Os tokens de cor, espaçamento e tipografia, e como se referenciam.
- **Duas ou três telas do mesmo domínio.** Elas mostram o padrão real, mais
  confiável que qualquer documento.
- As convenções de frontend declaradas em `docs.convencoes`.

**Nunca invente propriedade de componente.** Abra o arquivo do componente e leia
a assinatura. Um protótipo que não compila porque `DataGrid` não aceita
`onRowClick` é pior que nenhum: consome revisão e não entrega nada.

## Os estados são a entrega

Um protótipo do caminho feliz não é protótipo, é ilustração. Todos os estados de
`../screen-specification.md` — inicial, carregando, vazio, com dado, erro, sem
permissão, parcial — precisam ser **visíveis e alternáveis** no protótipo.

O jeito mais simples: os dados falsos expõem um seletor de cenário, e a rota
descartável deixa trocar entre eles. Quem revisa no portão 7 clica e vê, em vez
de ler que "o estado vazio mostra uma mensagem".

O estado **vazio** merece atenção especial, e são dois: "ainda não existe nada" e
"o filtro não achou". Telas diferentes, mensagens diferentes.

## A rota descartável tem três armadilhas

Todas apareceram na primeira vez que isto rodou de verdade.

**Fora de qualquer layout autenticado.** Uma rota criada dentro do grupo que
exige sessão renderiza a tela de login, não o protótipo — e a doutrina proíbe
autenticar. O protótipo tem dados falsos e não precisa de sessão: coloque-o num
caminho de topo.

**Ela pode quebrar o portão de rotas do projeto.** Projetos que exigem toda rota
declarada num inventário falham o build quando aparece uma nova. Duas saídas, e
a primeira é a melhor: **crie a rota, renderize, fotografe e apague** — ela é
andaime que existe só durante a conferência, e o componente, que é o artefato,
fica. A outra é declarar no inventário, o que suja arquivo do projeto e exige
limpeza depois.

**A porta pode estar ocupada.** Outra sessão, ou o próprio time, pode ter o
servidor rodando. Escolha uma porta livre em vez de derrubar o que está lá —
você não sabe o que a outra sessão está fazendo.

E um efeito colateral a conhecer: rodar a ferramenta de tipos ou o servidor de
desenvolvimento pode **regenerar arquivo rastreado** do projeto. Confira o
`git status` ao terminar e reverta o que a ferramenta mexeu sem você pedir —
senão o step seguinte recebe diff que você não escreveu.

## Renderize na língua do produto

O protótipo que sai em inglês num produto em português não é conferível: quem
revisa no portão não consegue julgar o texto, que é metade do que ele deveria
julgar.

Escrever o catálogo de mensagens certo não basta — a rota descartável precisa
**forçar o idioma do produto**, porque o padrão do ambiente costuma ser outro.
Confira na imagem, não no arquivo de tradução.

## Renderizar e olhar

Um protótipo não conferido é uma afirmação. Suba, renderize e **olhe** — nas
larguras que o projeto usa; se ele não declarar, use três, do celular ao
desktop.

O que só aparece na imagem: transbordo horizontal, tabela que não cabe, rótulo
cortado, contraste ruim, alvo de toque pequeno, foco invisível.

**Na largura de celular, olhe a tabela com desconfiança.** O padrão comum é
descartar colunas e cortar o texto no meio da palavra — e o resultado passa em
qualquer verificação automática de transbordo, porque tecnicamente cabe. Se a
tabela perdeu colunas, diga **quais** e por quê; se cortou texto, garanta que há
reticências e uma forma de ler o valor inteiro.

Uma verificação barata que vale rodar junto: comparar a largura de rolagem do
documento com a da janela. Zero de diferença é o mínimo, não a prova.

Se o ambiente não permitir renderizar, entregue assim mesmo e **diga que a
conferência visual não foi feita**. Não afirme que a tela está correta sem
tê-la visto.

## Herdar o que o projeto já cobra

Se o projeto tem gate de qualidade com invariantes de tela — coisas como "a rota
carrega limpa", "não há transbordo", "o estado assíncrono não sobrevive à troca
de rota", "erro de API não aparece cru" —, **leia essa lista e resolva por ela**.

É a especificação mais precisa que existe do que uma tela precisa fazer naquele
produto, ela é verificável por comando, e o step 8 vai ser cobrado por ela de
qualquer jeito. Um protótipo que já a respeita economiza uma volta inteira.

Declare, junto do protótipo, quais características a tela tem — se tem
formulário, se pagina, se busca ao montar, se dispara operação assíncrona. É o
que decide quais invariantes se aplicam.

## O que NÃO fazer

- **Não implemente.** Sem chamada de API, sem estado global, sem roteamento
  real. Se você está escrevendo `fetch`, saiu do papel.
- **Não invente contrato de dados.** O formato do dado falso segue a SDD de
  sistema; onde ela não diz, o dado falso é ilustrativo e você **marca isso**.
- **Não introduza componente, cor ou padrão novo** sem perguntar. Componente
  novo é decisão de arquitetura de frontend.
- **Não deixe texto improvisado.** Rótulo, mensagem de erro e estado vazio são
  conteúdo de produto e vão especificados.

## Ao entregar

Diga, separadamente:

1. **O que veio de padrão existente** — componente reusado, tela que serviu de
   referência.
2. **O que foi invenção sua**, e por quê. É o que o portão 7 precisa olhar com
   mais atenção: uma pessoa confirmando um protótipo do Figma decide diferente
   de uma pessoa confirmando o que uma IA deduziu de um texto.
3. **O que ficou pendente** por exigir componente que não existe, ou decisão que
   a SDD não tem.
4. **Se a conferência visual aconteceu**, e em quais larguras.
