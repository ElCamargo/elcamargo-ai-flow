# Por que — Step 2 · Business Analysis Reviewer

Esta é a explicação da skill `elcamargo-business-analysis-reviewer` (step 2),
não instrução. Cada trecho abaixo é texto movido, verbatim, do `SKILL.md`: a
história, o incidente, o número medido, o exemplo ou a justificativa que
sustentava a regra ao lado, antes de sair de lá.

## Intro

O erro que passa aqui custa dez vezes mais no step 8.

## Antes de tudo: o MODO do disparo

Ali a notificação de conclusão **não chega** — o turno acaba com as frentes
rodando e ninguém para consolidá-las. Foi assim que um step 9 gastou **193.310
tokens em três turnos dizendo que aguardava**, e entregou zero.

Bloqueante prende a janela até a leva voltar; segundo plano a devolve, e a
notificação reinvoca a sessão.

Senão elas não rodam em paralelo, e a leva deixa de ser leva.

## Se a trilha é `revisao`

O card é a única peça do conjunto que não saiu das mãos dele.

## O ofício

Carregar as oito antes de começar enche o contexto de doutrina que só vai
importar daqui a meia hora, e o que entra cedo demais some quando faz falta.

## Contrato

A política é declaradamente **hipótese**, não recomendação. Nada nela foi
medido ainda, e o coletor registra o modelo de cada turno justamente para que
ela possa ser confrontada com número.

## Onde a ferramenta mora (comentário original)

```bash
# Onde a FERRAMENTA mora. Três lugares possíveis, em ordem de confiança, e
# cada linha só corre se a anterior não achou uma pasta que existe:
#
#   1. `CLAUDE_PLUGIN_ROOT`  o harness diz. Não confie que ela SEMPRE chega
#      aqui — ela é documentada para hook, e para skill não está confirmado.
#   2. `.agents/elcamargo-flow`  o pacote copiado dentro do projeto.
#   3. o cache de plugin instalado, a versão mais alta.
#
# A terceira existe porque a primeira é incerta: sem ela, um projeto que só tem
# o plugin ficaria sem pacote se a variável não chegasse. Com ela, o pior caso
# é achar pelo caminho mais feio — e não falhar.
#
# O estado do PROJETO — `config.toml` e `atividades/` — continua no `.agents`
# nos três casos. Só a ferramenta se move.
```

## 1. Ler tudo, por inteiro

Já custou quatro requisitos não atendidos numa SDD marcada como pronta.

## 2. Extrair a matriz de rastreabilidade

Enumerar seções, achar identificadores e contar por seção é trabalho mecânico,
e fazer isso à mão custa quinze minutos e erra a contagem sem perceber que
errou.

Uma matriz com 36 RN e zero RF, num documento que tem RF, está incompleta e se
anuncia.

Essa matriz é o que o step 4 vai usar para conferir se o sistema cobriu o
negócio. Se ela estiver incompleta, a conferência do step 4 é falsa.

## 3. Caçar defeito

Cardinalidade: esta é a que mais escapou até hoje.

Numa execução real uma pendência de severidade alta se apoiou no que o autor
**supôs** que uma tela mostrava — a tela não mostrava aquilo, e ninguém tinha
medido.

## 4. Confrontar a memória de rejeição

"tema noturno" e "modo escuro" são o mesmo pedido com nomes diferentes.

A decisão de seis meses atrás pode não valer mais. O erro é decidir de novo sem
saber que já se decidiu.

## 5. Olhar a arquitetura, sem entrar nela

Esta segunda é a que costuma achar o risco. Uma análise raramente chega em
terreno virgem: ela descreve um módulo que o produto já tem, com outras
palavras, escritas por quem não leu a especificação anterior. A divergência aí
não é evolução — é **regressão com aparência de requisito**, e passa numa
revisão que só pergunte sobre ADR.

## 7. Conferir a si mesmo, por comando

Numa execução real o total declarado dizia 155 e a matriz tinha 159 linhas, e
sete itens sumiram sem justificativa — tudo isso é mecânico, e custou uma
auditoria inteira porque foi o revisor quem achou.

## 8. Auditoria por especialista — obrigatória

É o que permite contar quantos viraram mudança, e o que impede o descartado de
sumir e voltar na volta seguinte.

A auditoria **diverge** num documento que continua sendo corrigido, porque
cada correção escreve texto novo e texto novo tem taxa de defeito própria. Um
laço que só para quando está limpo não para.

Numa execução real o auditor registrou md5 e data, e viu o arquivo **crescer
de 156 para 159 linhas enquanto auditava** — metade dos achados dele podiam já
estar corrigidos, e ele não tinha como saber quais.

Numa execução real ele produziu o relatório inteiro e travou ao entregá-lo — o
resultado existia e ficou inacessível por quase duas horas, de um trabalho de
quarenta e cinco minutos.

Numa execução real descobriu que a frase *"nada foi descartado em silêncio"*
era falsa para sete itens, e que uma recomendação de severidade alta se
apoiava em evidência inexistente.

No mesmo caso, o auditor renderizou uma imagem a 14× e mediu a geometria para
refutar uma afirmação sobre o que o protótipo mostrava — descobrindo que a
recomendação de uma pendência de severidade alta se apoiava em evidência
inexistente.

## 9. Fechar o step

O documento é assinado por você e pela pessoa que o revisa, e sair sem revisão
quebra essa assinatura.

Este é o step em que o card mais recebe anexo, e por isso o critério vale mais
aqui:

As três vieram de falhas medidas, e duas delas só apareceram uma atividade
depois.

Ela delega ao gerenciador de Git do projeto e não mexe no estado da atividade,
que é seu.

## A entrega

Que assim vê a saída desta etapa antes de gastar a próxima — e consegue
apontar onde a cadeia quebrou quando ela quebra.

O step seguinte precisa ler o artefato, não o raciocínio de quem o escreveu.

Contexto herdado faz o modelo responder ao próprio rastro em vez de responder
à especificação.

## O relatório que volta ao analista

É o entregável mais importante deste step.
