# Rationale — elcamargo-ux-reviewer

Isto é a explicação da skill do step 6 (`skills/elcamargo-ux-reviewer/SKILL.md`),
não instrução. A skill traz o que fazer; este arquivo traz o porquê, com os
casos medidos que produziram cada regra. Títulos de seção espelham os da skill.

## Antes de tudo: o MODO do disparo decide se você vai esperar

Dentro de um subagente, a notificação de conclusão não chega — o turno acaba
com as frentes rodando e ninguém para consolidá-las. Foi assim que um step 9
gastou **193.310 tokens em três turnos dizendo que aguardava**, e entregou
zero.

Na janela principal, bloqueante prende a janela até a leva voltar; segundo
plano a devolve, e a notificação reinvoca a sessão.

Nos dois modos, as frentes da mesma leva vão numa única mensagem — senão elas
não rodam em paralelo, e a leva deixa de ser leva.

## O ofício

- `screen-specification.md` — os sete estados, validações com texto,
  permissão, acessibilidade, responsivo.
- `pending-decisions.md` — como escalar a divergência que muda regra de
  negócio.
- `evidence.md` — afirmar não é provar — meça o que você diz que a tela
  mostra.
- `specialties/figma-writing.md` — a sonda de reconhecimento, o gate de
  aderência, e as seis armadilhas que produzem tela errada sem dar erro.

## Contrato

A política do `model-policy.md` é declaradamente hipótese, não recomendação.
Nada nela foi medido ainda, e o coletor registra o modelo de cada turno
justamente para que ela possa ser confrontada com número.

`$PACOTE/FLOW.md` é o contrato do fluxo, e traz o que nenhuma skill repete por
inteiro: como o portão humano é entregue, como você fala dos steps no chat, o
limite de voltas entre quem faz e quem revisa, e o que todo step deve ao
próximo.

## Onde a ferramenta mora (resolvedor de PACOTE)

Onde a FERRAMENTA mora. Três lugares possíveis, em ordem de confiança, e cada
linha só corre se a anterior não achou uma pasta que existe:

  1. `CLAUDE_PLUGIN_ROOT`  o harness diz. Não confie que ela SEMPRE chega
     aqui — ela é documentada para hook, e para skill não está confirmado.
  2. `.agents/elcamargo-flow`  o pacote copiado dentro do projeto.
  3. o cache de plugin instalado, a versão mais alta.

A terceira existe porque a primeira é incerta: sem ela, um projeto que só tem
o plugin ficaria sem pacote se a variável não chegasse. Com ela, o pior caso é
achar pelo caminho mais feio — e não falhar.

O estado do PROJETO — `config.toml` e `atividades/` — continua no `.agents`
nos três casos. Só a ferramenta se move.

## 2. Disparar o subagente

`off` manda pelo `screen-drawer` mesmo havendo link — e isso não é
degradação: é o outro caminho previsto do step, e um projeto legitimamente não
quer que o fluxo gaste orçamento de leitura do arquivo de design.

Quando a leitura falhar, `GET` não consegue escrever; o editor consegue — num
arquivo da empresa, com gente trabalhando dentro, essa diferença é tudo.

Isto está escrito na skill porque a decisão é sua, nesta janela, antes de o
subagente existir. Em 08/09/2026 uma frente irmã parou o step 6 "por falta de
MCP da Figma", tentou o Chrome, tentou o navegador interno e parou num muro de
login — com o token instalado na mesma máquina e o arquivo legível em um
comando. A regra existia; morava só no agente que ela nunca chegou a disparar.

## 3. Conferir o protótipo antes de aceitar

Confirmar um protótipo do Figma é decisão diferente de confirmar o que uma IA
deduziu de um texto.

## 4. Consolidar as decisões

Uma divergência não resolvida aqui vira retrabalho no step 8 ou, pior, uma
tela implementada contra a regra de negócio.

## 5. Regra do Figma

Um botão em outra cor é decisão de UX. Um campo que o Figma torna opcional e a
RN exige obrigatório não é.

## Publicar no Figma — dois portões, nesta ordem

Faz sentido devolver a tela ao Figma para o design não descolar do produto.

A política do projeto não é negociável dentro da atividade, e insistir contra
ela é a mesma coisa que rodar um step desligado.

Escrever num arquivo de design compartilhado é ação para fora, no arquivo de
outra pessoa — e um arquivo de Figma não tem `git revert`.

Os dois portões existem porque respondem a coisas diferentes: o primeiro é
política, decidida uma vez e para todas as atividades; o segundo é
consentimento, que se pede toda vez.

O pacote não sabe se a máquina consegue escrever porque quem sabe é você,
olhando as suas ferramentas. Pedir consentimento para uma ação que não executa
é teatro, e gasta uma decisão do usuário à toa.

Em 08/09/2026 um projeto com `figma_escrita` em `on` não tinha o MCP: o portão
da política abria e nada executava. A frente conferiu antes de agir; se
tivesse acreditado, teria prometido publicar uma tela.

## Não publicou? Declare nos dois lugares

Mas some do relatório se ninguém disser, e aí a entrega parece completa quando
não é.

A referência `figma-writing.md` explica por que cada passo é obrigatório.

Se o recurso de escrita sumir, perdemos uma conveniência, não uma etapa — o
artefato que garante a qualidade do desenvolvimento é o protótipo no
repositório, não a tela no Figma. E a Figma avisa que passará a ser cobrado
por uso.

## Só vai ao card o que pergunta algo

O procedimento de `card-attachment.md` traz o comando, o que a ferramenta
recusa e por quê, a conferência obrigatória depois de anexar, e a linha de
assinatura que abre todo comentário no card. As três obrigações vieram de
falhas medidas, e duas delas só apareceram uma atividade depois.

## Entregue o portão como perguntas, não como leitura

O documento continua sendo a evidência; ele só deixa de ser o pedido.

## E então (step 7 é humano)

Quem revisa precisa saber se está confirmando um protótipo que o cliente já
viu ou uma tela que a IA inventou a partir do texto da SDD. São decisões de
peso diferente.
