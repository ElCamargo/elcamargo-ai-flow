# Fluxo de trabalho com IA

Este documento é o contrato do fluxo. Toda skill do pacote consulta ele para
saber em que step está, o que produzir e a quem entregar.

A definição legível por máquina está em
`tools/flow-state/flow_state.py` (constantes `STEPS` e `TRILHAS`). Se os dois
divergirem, o script vence — e o documento precisa ser corrigido.

## Princípio

**O handoff entre steps é por arquivo, nunca por contexto de conversa.**

Um step lê arquivos, escreve arquivos e termina. O step seguinte não recebe o
raciocínio do anterior; recebe o artefato dele. Isso é o que permite pausar a
atividade por dias, retomá-la em outra sessão, rodar um step em subagente ou em
outra worktree — sem que nada mude.

A consequência prática: **nenhum step depende de estar na mesma sessão que o
anterior.** Uma skill termina anunciando o próximo step; ela não o executa.

## Os steps

| # | Componente | Tipo | Entrega |
| --- | --- | --- | --- |
| 1 | `elcamargo-activity-management` | skill | Card lido, trilha decidida, atividade aberta |
| 2 | `elcamargo-business-analysis-reviewer` | skill | Revisão da análise de negócio + SDD de negócio |
| 3 | `elcamargo-system-analyst` | skill | SDD de sistema |
| 4 | `elcamargo-system-analysis-reviewer` | skill | Veredicto: o sistema cobre o negócio? |
| 5 | **Revisão humana da especificação** | humano | Aprovação da spec antes de gastar esforço em tela |
| 6 | `elcamargo-ux-reviewer` | skill | Decisões de tela documentadas |
| 7 | **Revisão humana das telas** | humano | Aprovação do visual antes de codar |
| 8 | `elcamargo-developer` | skill | Implementação |
| 9 | `elcamargo-development-reviewer` | skill | 5 revisões + correções aplicadas |
| 10 | **Validação humana da entrega** | humano | Aceite final |

Os steps 5, 7 e 10 são **portões**: o fluxo para e espera resposta humana. Uma
skill nunca atravessa um portão por conta própria.

**Quem atravessa o portão é a pessoa**, rodando o `avancar` ela mesma. A skill
que termina num portão imprime o comando exato; a skill do step seguinte, se
encontrar a atividade parada no portão, recusa começar e reimprime o comando.
Sem essa regra o estado congela no portão e nenhuma atividade chega ao fim.

### Os três portões, e o que cada um compra

O mesmo princípio, aplicado em três camadas: **validar antes de gastar o esforço
que vem depois.** Cada portão custa minutos de uma pessoa e evita horas de
trabalho construído sobre uma base errada.

| Portão | Decide | O que evita |
| --- | --- | --- |
| 5 · especificação | A spec descreve o produto certo? | Prototipar e implementar a coisa errada |
| 7 · telas | O visual está certo? | Implementar a coisa certa com a tela errada |
| 10 · entrega | Está aceito? | Entregar sem alguém ter olhado |

O portão 7 pesa mais do que parece quando **não há Figma**: nesse caminho o
`screen-drawer` *inventa* as telas a partir da SDD, e sem este portão a invenção
de uma IA vira código sem que ninguém a tenha confirmado. Com Figma, o portão é
mais leve — mas ainda é onde as divergências que o `figma-reader` levantou são
decididas.

Refazer um protótipo custa uma fração de refazer uma tela implementada, testada
e com baseline visual gravada.

### Decisão encontrada no meio do caminho não espera o portão

Os três portões são os momentos **planejados** de decisão humana. Eles não são os
únicos: um step pode descobrir, no meio do trabalho, algo que só o dono do
produto sabe responder.

**Traga na hora, uma a uma, e siga.** Nunca acumule para o portão seguinte, e
nunca trave o fluxo esperando.

A regra tem três partes, e as três importam:

**Uma a uma.** Cada decisão vira uma pergunta com opções reais e clicáveis. Uma
pergunta com três opções concretas e a consequência de cada uma se responde em
segundos; um parágrafo pedindo "me diga como você quer o menu" se responde em
minutos, ou não se responde.

**Com as opções que existem de fato.** Vá ler o código antes de listar as
alternativas. Numa execução real, a pergunta sobre onde entrava um item de menu
só ficou respondível porque as opções vieram do `app-shell.tsx` — dois grupos,
um item solto — e não de suposição sobre como a barra lateral poderia ser.

**Sem travar.** Enquanto a resposta não vem, faça tudo o que não depende dela. Se
o trabalho inteiro depende, entregue o que existe com a pergunta em destaque —
não devolva silêncio. Uma pergunta feita cedo e respondida em um clique custa
segundos; a mesma pergunta descoberta no step 9 custa a implementação inteira.

O contrário disso é `Pressuposto` indevido, e tem teste próprio em
`references/traceability.md`: **se nenhum artefato ia responder aquilo, é
pergunta, não pressuposto.**

### O portão humano chega como pergunta, nunca como leitura

**Nenhum portão humano se apresenta como "leia o documento e me diga".** Ele
chega ao chat como um punhado de perguntas com opções clicáveis: a pessoa lê,
entende e responde. Vale para os três — 5, 7 e 10.

O documento continua existindo e continua sendo a evidência. O que muda é o que
se pede: **pedir leitura transfere o trabalho de achar a decisão para quem
decide**, e uma especificação de mil e novecentas linhas tem uma dúzia de
decisões enterradas em prosa. Quem produziu o documento sabe quais são; quem vai
decidir não tem como saber sem reler tudo.

**O que vira card, e o que não vira.** O portão pergunta o que a pessoa pode
mudar e o que muda alguma coisa:

| Vira card | Não vira card |
| --- | --- |
| Decisão que o step tomou e que é revertível a baixo custo | O que o step apurou e não tem alternativa |
| Consequência declarada que estreita algo — capacidade, prazo, acesso | Detalhe de implementação que a pessoa não decide |
| Escopo que ficou de fora e podia entrar | Achado já corrigido |
| Achado aberto que sobrou da terceira volta | Cerimônia: "está tudo certo?" |

**Como escrever o card:**

1. **Uma decisão por pergunta.** Duas decisões num card produzem resposta
   ambígua, e a ambiguidade volta como retrabalho.
2. **Opções reais, verificadas.** Vá ler o código antes de listar. Numa execução
   real, a pergunta sobre onde entrava um item de menu só ficou respondível
   porque as três opções vieram do `app-shell.tsx` — dois grupos, um item solto.
3. **A consequência de cada opção**, em resultado observável, não em adjetivo.
4. **Recomende**, e diga por quê em uma linha. Quem decide tem direito à sua
   opinião; ela não é imposição.
5. **No máximo quatro por vez.** Mais que isso vira formulário, e formulário se
   responde no automático.

**A aprovação é a última pergunta, não a única.** Um portão que só pergunta
"aprovado?" não é portão: é carimbo. As decisões vêm primeiro, e a aprovação
depois delas — porque a resposta de uma pode mudar a outra.

**E o que não couber em card vai em uma linha de texto**, antes das perguntas: o
que o step fez, o que os portões mecânicos disseram, e onde ler se a pessoa
quiser. Curto. O card é o pedido; o texto é o contexto.

### O que o pacote garante, e o que depende de a skill ler isto

Uma regra escrita aqui só vale se quem executa a ler. Isso divide o pacote em
duas camadas, e a diferença importa para quem instala em outro projeto:

| | O que é | Vale sempre? |
| --- | --- | --- |
| **Código** | `flow_state.py`, as ferramentas, os testes. O cargo de cada step, a verificação de anexo, os portões mecânicos | **Sim.** Não depende de ninguém ler nada |
| **Doutrina** | Este arquivo e as `references/` | Só se a skill mandar ler |

**Por isso todo step de skill abre mandando ler o `FLOW.md`.** Não é cerimônia:
as regras transversais — como o portão humano é entregue, como se fala dos steps
no chat, o limite de voltas — não cabem repetidas em sete skills sem
divergirem entre si na primeira edição.

O que é **específico de um step** fica na skill dele. O que atravessa o fluxo
fica aqui, e a skill aponta. Quando os dois discordam, é defeito — e o
`test_package.py` existe para achá-lo.

### Chame cada step pelo cargo, e não pelo número

Cada step tem duas identidades, e elas servem a leitores diferentes:

| | O que é | Onde aparece |
| --- | --- | --- |
| **cargo** | Quem faz aquele trabalho, dito como se diria de uma pessoa — *Analista de Sistema*, *Revisor da Especificação* | Tudo que uma pessoa lê |
| **endereço** | O que se invoca — `elcamargo-system-analyst` | O comando, e o arquivo de estado |

**No chat, fale sempre pelo cargo.** *"O step 3 respondeu ao step 4 e pode chamar
o step 5"* é verdadeiro e ilegível: quem lê não sabe quem faz o quê ali, e tem
que ir procurar. *"O Analista de Sistema corrigiu, o Revisor da Especificação
aprovou, e agora é o seu portão"* diz a mesma coisa e não precisa de tradução.

O número fica junto — ele localiza no fluxo e é o que a pessoa usa nos comandos —,
mas **sozinho ele não informa**. `9 · Revisor da Entrega`, não `step 9`.

O padrão, no formato exato que funcionou:

> *"O **Revisor da Entrega** está rodando as seis frentes sobre o commit do
> **Desenvolvedor**. Quando voltar, vai trazer os cards do **Portão humano ·
> Entrega**."*

Três cargos numa frase, e ninguém precisa consultar tabela nenhuma para saber
quem fez o quê, quem está fazendo, e de quem é a vez. Compare com a mesma frase
por números — *"o 9 está rodando sobre o commit do 8 e depois vai para o 10"* —,
que exige que o leitor já saiba o fluxo de cor para entender.

Vale para relatório, para resumo no chat e para o que se escreve no card.

O endereço aparece **só onde é acionável**: no comando do próximo step, e no
`fluxo`, que é a lista de referência. Em relatório, tabela de tempo e histórico,
o endereço é ruído — ninguém lê `elcamargo-system-analysis-reviewer` e pensa
"ah, quem confere a especificação".

**O cargo é derivado do número, sempre.** O histórico da atividade guarda o
rótulo do dia em que a transição aconteceu, e esse rótulo envelhece: renomear um
step deixaria a tabela de tempo listando o mesmo trabalho com dois nomes. Quando
o número resolve, o cargo vem da tabela `STEPS`, não do que ficou gravado.

### A passagem de step também é um clique

O step termina imprimindo o comando do próximo e **não o executa** — quem dispara
é a pessoa, porque o step seguinte precisa rodar em contexto novo, lendo o
artefato e não o raciocínio de quem o escreveu.

Isso continua valendo. O que muda é **como o comando é oferecido**: junto do
comando, ofereça o disparo como **card clicável**, no mesmo formato dos portões.
A pessoa clica em vez de digitar.

| Ofereça assim | Não assim |
| --- | --- |
| Um card com o próximo step, dizendo o que ele vai fazer e o que vai custar | Só a linha `/skill 1042` no fim do texto, para a pessoa copiar |
| A opção de parar, com o que ela ganha ao parar | Card com uma opção só, que é cerimônia |

O card carrega o que o comando não carrega: **o que está sendo autorizado.**
"rodar o step 8" e "implementar quatro fatias, criando duas migrations e a
primeira rota do inventário a declarar `editForm`" são a mesma ação, e só a
segunda deixa a pessoa decidir de verdade.

Duas coisas que **não** mudam: o step seguinte roda em **contexto novo** — sessão
nova ou subagente —, e o estado da atividade só avança quando a pessoa manda.
Clique é forma de autorizar, não atalho para pular o portão.

E o comando continua impresso, para quem preferir digitar ou precisar dele
depois.

### O portão 10 valida em homologação, e é decisão sua

O step 9 prova em ambiente **local**: a frente de execução sobe a aplicação e
percorre o fluxo, com os estados de erro. Isso é do fluxo, e acontece sempre que
a entrega tem tela.

**Homologação é outra coisa.** É ambiente compartilhado, e criar dado lá tem
consequência para outras pessoas. O fluxo não faz isso por conta própria.

O que ele entrega ao portão 10 é o **roteiro**: o que criar, em que ordem, o que
verificar em cada passo, e como desfazer. Quem executa é a pessoa — ou o agente,
**com autorização explícita daquela atividade**, nunca por padrão.

E o que for criado em homologação **se declara**: o que foi, onde ficou, e se
saiu. Dado de teste esquecido em ambiente compartilhado é problema de outra
pessoa, mais tarde, sem contexto.


### O subagente de completude é o componente de maior valor

Os steps 2 e 3 abrem um subagente que confere o **próprio trabalho** antes de
commitar. É fácil tratar isso como formalidade. Não é.

Numa execução real, sobre uma especificação de 27 páginas, o auditor achou mais
de vinte defeitos numa SDD que já parecia boa — inclusive um em que o documento
afirmava algo sobre um protótipo que o protótipo não mostrava, e uma pendência
de severidade alta recomendando com base nessa evidência inexistente.

Ele encontra o que o autor não consegue ver, porque é o autor que tem o ponto
cego. Duas regras que vieram dessa execução:

- **Congele o artefato antes de disparar.** O auditor viu o arquivo mudar
  enquanto auditava. Alvo móvel invalida a auditoria.
- **A auditoria custa cerca de 70% do que custou produzir** — e vale, porque
  descobre que a produção não estava pronta.

### Steps 3 e 4 revisam coisas diferentes

Não são redundantes, e não devem convergir para o mesmo prompt:

- O subagente interno do **step 3** pergunta *"eu fiz tudo que essa skill deveria
  fazer?"* — é auto-completude, e olha para a própria saída.
- O **step 4** pergunta *"a especificação de sistema cobre o que o negócio
  pediu?"* — é rastreabilidade entre dois documentos, e olha para os dois.

O step 2 tem um subagente de auto-completude equivalente ao do step 3.

## As trilhas

A trilha é decidida uma vez, no step 1, com o usuário, e fica gravada na
atividade. Ela existe para o fluxo não virar cerimônia: dez steps para um botão
que não desabilita é como o processo morre.

| Trilha | Quando usar | Steps |
| --- | --- | --- |
| `completa` | Feature nova, com análise de negócio a revisar | 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 |
| `sistema` | Card claro, sem análise de negócio a revisar | 1 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 |
| `curta` | Bug, ajuste, correção pontual | 1 → 8 → 9 → 10 |

A trilha `curta` não passa por especificação nem por tela, e por isso também não
passa pelos portões 5 e 7 — eles existem para validar exatamente o que ela não
produz. Sobra o portão 10, que é o aceite.

Na trilha `curta`, o step 9 roda `code-reviewer`, `quality-reviewer` e
`security-reviewer`. As duas frentes que ficam de fora são as que conferem
contra especificação — e a `curta` não produz nenhuma. O `security-reviewer`
não lê especificação: parte da stack e do diff, e um ajuste de uma linha numa
rota é exatamente onde um vazamento entre clientes entra em produção.

Mudar de trilha no meio exige `--forcar` e uma nota dizendo por quê. Não é
proibido; é registrado.

## Os subagentes

Sete componentes nunca são invocados diretamente — só rodam como subagente,
chamados pelo step que os contém. Por isso são agent definitions em
`.claude/agents/`, e não skills: agent não entra no contexto principal.

| Chamado por | Subagentes |
| --- | --- |
| Step 6 · `ux-reviewer` | `figma-reader` **ou** `screen-drawer` |
| Step 9 · `development-reviewer` | `code-reviewer`, `implemented-sdd-reviewer`, `implemented-business-reviewer`, `security-reviewer`, `quality-reviewer` |

Os cinco do step 9 rodam em paralelo.

### O que o step 6 entrega

Não uma figura: um **protótipo que compila**, com os componentes reais do
projeto. Três arquivos, e só o primeiro migra para produção:

1. **Componente puro** — tudo por propriedade, sem busca, sem rota.
2. **Dados falsos** cobrindo cada estado, com seletor de cenário.
3. **Rota descartável** que renderiza os dois, para ver e fotografar. O step 8
   apaga ao mover.

Renderizado e conferido nas larguras que o projeto declara, e com as
características da tela declaradas — se tem formulário, se pagina, se busca ao
montar — que é o que decide quais invariantes do gate do projeto se aplicam.

A diferença é onde o tempo do desenvolvedor vai: com figura ele traduz, e a
tradução varia; com protótipo ele troca o dado falso pela API.

**Publicar de volta no Figma** é opcional, autorizado a cada vez, e só quando o
seat permite. O artefato que garante a qualidade do desenvolvimento é o
protótipo no repositório — a tela no Figma serve à continuidade do design, que é
outro valor.

### Duas voltas entre quem faz e quem revisa. Em todo par.

O fluxo tem três pares fazedor↔revisor, e todos precisam da mesma conversa:

| Faz | Revisa |
| --- | --- |
| step 2 · business-analysis-reviewer | seu subagente auditor |
| step 3 · system-analyst | seu subagente de completude, e depois o step 4 |
| step 8 · developer | step 9, nas seis frentes |

**Duas voltas em cada par. Na terceira, entrega com o que ficou aberto
declarado.** Não trava, não some, e não vira laço.

O step 9 nasceu com esse limite. Os outros dois não tinham, e numa atividade
real isso custou **sete horas de retrabalho**: cinco rodadas de auditoria dentro
do step 3, e duas reprovações do step 4.

**Por que o limite é necessário, e por que ele não é arbitrário.** A auditoria
converge num documento congelado — a mesma spec deu 12, 6, 5, 1, 0 achados em
cinco rodadas. Mas cada correção **escreve texto novo**, e texto novo tem taxa
de defeito própria: a rodada seguinte, sobre o documento corrigido, achou **dez**
outra vez. Não é regressão — é que a variável não é o número de rodadas, é a
quantidade de texto novo por rodada. Um laço que só para quando está limpo nunca
para.

**O que sai da terceira volta** é um artefato com uma seção **Achados abertos**:
o que ficou, por que ficou, e qual seria a correção. Ela viaja com o documento e
é entrada para quem vem depois — o step 9 já lê a SDD, e um achado declarado é
informação para ele, não dívida escondida.

**O que nunca fica aberto** é achado que alcança código. Ver
`references/severity.md`, *Em documento, severidade é alcance*: `alta` é o que
faz o desenvolvedor construir errado, e isso volta para correção mesmo na
terceira volta — se sobrar `alta` na terceira, o step **escala ao portão humano**
em vez de entregar.

**Corrija em paralelo, por seção.** Foi assim que as sete horas se formaram: um
corretor único, em série, reescrevendo o documento inteiro a cada rodada, com o
defeito de uma correção contaminando a próxima. Quando os achados tocam seções
independentes, um agente por seção — cada um vendo só a sua — limita o texto novo
de cada um e tira a serialização.

### O laço de correção do step 9

1. Dispara os revisores da trilha em paralelo e espera todos.
2. Consolida os retornos.
3. Se não houver erro, segue para o step 10.
4. Se houver, **a correção volta para o `developer`** — quem revisa não corrige,
   senão o revisor passa a validar o próprio conserto.
5. Re-roda **somente as frentes que falharam**, não as cinco.
6. No máximo **2 voltas**. Na terceira, para e chama o humano no chat,
   explicando o que não fecha. Isso existe para um problema externo — internet,
   ambiente fora — não virar laço infinito.

## As duas devoluções

Um step pode receber trabalho de volta por dois motivos, e tratá-los igual
estraga os dois.

**Devolução por defeito.** O step 4 devolve ao 3, o step 9 devolve ao 8. A
entrega está **errada**. O escopo não mudou — mudou que alguém achou um problema
nela.

**Devolução por escopo.** Um portão humano devolve: o 5 ao step 3, o 7 ao step
6, o 10 ao step 8. A entrega **não está errada**. A pessoa quer mais.

| | por defeito | por escopo |
| --- | --- | --- |
| Quem devolve | step 4 ou step 9 | portão 5, 7 ou 10 |
| O que a devolução nomeia | um **defeito** | um **trabalho** |
| A parte já aceita | volta a ser revisada — a correção pode tê-la quebrado | **não se re-litiga** |
| A parte nova | não há | revisão **completa**, não verificação |
| O contador de voltas | avança | **reinicia** |

O contador é a parte concreta. O step 9 descobre em que volta está contando
quantas vezes o histórico registra a entrada nele, e para na terceira — porque
revisor que revisa de novo o mesmo diff **fabrica achado quando os reais
acabam**. Essa regra é certa para devolução por defeito e **errada** para
devolução por escopo: o trabalho novo nunca foi revisado por ninguém, e recusar
revisá-lo por causa de um contador entrega código sem revisão nenhuma.

Quem devolve declara qual das duas é, na nota. Sem isso o step seguinte não tem
como saber, e vai adivinhar.

### O step 4 tem saída, não limite

O step 9 para na terceira volta porque revisor que relê **o mesmo diff** fabrica
achado quando os reais acabam. O step 4 relê um documento **que mudou** a cada
volta, e o mesmo raciocínio não se aplica — na POC, cada volta achou defeito
real, inclusive a segunda, que descobriu que a própria correção tinha quebrado
duas seções.

Então o step 4 não ganha limite. Ganha **saída**.

**Quando o step 4 reprova a mesma especificação pela terceira vez, a terceira
passada não é revisão — é sinal de que falta uma decisão que nenhum dos dois
pode tomar.** Aconteceu com uma pergunta de arquitetura: decidir dentro ou fora
da transação. O step 3 escolheu, o step 4 mostrou que a escolha não tinha
chegado a duas seções, e uma quarta volta só produziria a mesma discussão com
outras palavras.

Nesse ponto o step 4 **escala ao portão 5**, com as duas posições escritas:

- o que o step 3 sustenta, e por quê;
- o que o step 4 sustenta, e por quê;
- o que muda em cada caminho, em consequência observável;
- e a informação que falta para decidir, se houver.

Quem decide é a pessoa. É para isso que o portão 5 existe — e uma divergência
técnica entre dois agentes é exatamente o tipo de coisa que ele deveria receber,
em vez de ficar circulando entre eles até um ceder por cansaço.

**A escalada não é fracasso do laço.** Duas voltas que acharam defeito real
valeram o que custaram; a terceira é que não valeria.

### O crescimento precisa ficar visível

O fluxo não briga com o humano. Se a pessoa quer mais, ela manda, e o fluxo
faz — ela é quem responde pelo produto.

Mas **registre o que foi acrescentado em cada volta**, na nota da atividade. Três
devoluções humanas seguidas na mesma atividade não são sinal de que o fluxo está
funcionando: são sinal de que **a fatia foi mal escolhida**, e a essa altura é
mais barato fechar esta e abrir outra do que continuar empilhando escopo sobre
uma revisão que já aconteceu.

Quem lê a atividade depois precisa conseguir ver o que era o card e o que virou.

## Estado da atividade

Uma atividade = um arquivo em `<.agents>/atividades/<id>.md`.

Um arquivo por atividade, e não uma linha num arquivo compartilhado, porque
worktrees paralelas escreveriam no mesmo lugar. `Atividades_em_andamento_com_IA.md`
existe como **índice gerado**: é derivado dos arquivos e pode ser reconstruído a
qualquer momento.

`<.agents>` é sempre o do repositório principal, inclusive quando a skill roda
dentro de uma worktree.

### Como uma skill acha o pacote

Toda skill começa com este bloco, literalmente. Ele resolve o pacote a partir de
qualquer lugar do projeto, worktree inclusive:

```bash
PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

`--git-common-dir` aponta para o `.git` do repositório principal de qualquer
worktree, e `.agents` fica ao lado dele. Não use caminho relativo: uma worktree
não carrega `.agents`, e de dentro do próprio `.agents` — que é repositório Git
independente — o `git rev-parse` descreveria o repositório errado. Para esse
último caso existe `ELCAMARGO_AGENTS_DIR`.

### Comandos

```bash
F=.agents/elcamargo-flow/tools/flow-state/flow_state.py

python3 $F fluxo                       # steps e trilhas
python3 $F iniciar 1042 --titulo "..." --trilha completa
python3 $F status 1042                # onde está; sem id, lista todas
python3 $F avancar 1042 --nota "..."  # entra no próximo step da trilha
python3 $F artefato 1042 --tipo sdd-sistema --caminho docs/specs/...
python3 $F concluir 1042
python3 $F indice                      # regera o índice
```

O `avancar` recusa, sem `--forcar`:

- **retroceder** — voltar para um step já passado;
- **step fora da trilha** — um step que a trilha escolhida não contém;
- **pular step** — inclusive, e principalmente, pular um portão humano. Ir do
  step 4 direto para o 6 atravessaria a revisão da especificação, e o 6 direto
  para o 8 atravessaria a revisão das telas — que são a razão de os dois
  existirem. O erro diz quais steps seriam pulados e se há portão entre
  eles.

`--forcar` libera os três, e **exige `--nota`**: sair da trilha sem registrar o
motivo torna o histórico inútil justamente onde ele importa. Para mudar a trilha
no meio, `--forcar --trilha <nova> --nota "<por quê>"`.

`concluir` exige estar no último step da trilha, ou `--forcar` com nota.

`--reabrir` **preserva** histórico, artefatos e data de criação. Reabrir uma
atividade não apaga o que já aconteceu nela.

Toda mutação toma um lock exclusivo. Um arquivo por atividade impede dois
processos de dividirem um arquivo; não impede dois processos de lerem o mesmo
estado e escreverem um por cima do outro. `os.replace` é atômico, não é um lock.

### Vocabulário dos artefatos

`--tipo` é texto livre no script, mas o fluxo só reconhece estes. Um step que
registra com outro nome some para quem o procura.

| Tipo | Produzido no | Consumido em |
| --- | --- | --- |
| `sdd-negocio` | 2 | 3, 4, 9 (`implemented-business-reviewer`) |
| `relatorio-negocio` | 2 | — (vai ao analista, fora do fluxo) |
| `sdd-sistema` | 3 | 4, 8, 9 (`implemented-sdd-reviewer`) |
| `veredicto-sistema` | 4 | 3, quando o step 4 devolve |
| `decisoes-ux` | 6 | 7 (portão), 8 |
| `prototipo` | 6 | 7 (portão), 8 |
| `implementacao` | 8 | 9 |
| `revisao-desenvolvimento` | 9, ao fim de **cada volta** | 8, na volta de correção |

`--caminho` é caminho de arquivo, sempre. Prosa nesse campo produz um artefato
que ninguém consegue abrir.

### As métricas se atualizam sozinhas

Toda passagem de step e todo `concluir` recolhem as métricas **daquela**
atividade para `<.agents>/metricas/`. Nada a lembrar, pela mesma razão da
âncora: métrica que só existe quando alguém manda gerar é métrica que não
existe.

```bash
M=$PACOTE/tools/metrics/metrics.py

python3 $M coletar                       # todas; ~3 s por atividade
python3 $M relatar                       # o projeto inteiro
python3 $M relatar --atividade 1042     # desce para os steps dela
python3 $M relatar --atividade 1042 --step 9   # desce para os agentes do step
python3 $M painel                        # HTML com drill-down clicável
python3 $M conjunto <ids>                # as que rodaram em PARALELO, como conjunto
```

Cinco níveis, e cada um soma exatamente o de baixo:

```
projeto  ->  atividade  ->  step  ->  agente  ->  conferência
```

A coleta é **ligada por padrão**. `[metricas] ligado = false` desliga, e o
`doctor.py conferir` mostra em que estado está.

**O gasto pode virar limite.** Com `[metricas] orcamento_usd` declarado, o
`avancar` **para** quando a última coleta da atividade passou do teto, imprime
gasto, teto e excesso, e libera com `--forcar --nota` — o mesmo idioma de sair
da trilha. O `concluir` nunca é barrado: travar o fechamento deixaria a
atividade presa em andamento. Por atividade e em dólar, não por step nem em
token, e a razão dos dois está em `references/metrics.md`.

**Ponto de função é declarado, não medido.** Ele não sai de transcrito nenhum.
São **dois** números declarados: `pf`, do analista, contado da especificação
antes de existir código; e `pf_aferido`, do step 9, contado da entrega, com o
inventário da conta ao lado — `--aferido` é recusado sem `--inventario`. Quando
divergem, o que divergiu foi o escopo, e a ferramenta **não desempata**: mostra
os dois, o sentido da diferença, e h/PF para cada um. Sem nenhum dos dois, a
métrica de PF não aparece — em vez de aparecer errada.

**Atividade que não se consegue atribuir é dita, não zerada.** Sem `branch` nem
`worktree` no cabeçalho, nada liga a atividade a uma sessão: o registro saía
com 0 turnos e US$ 0,00 tendo US$ 36,00 de trabalho no disco. Hoje ela aparece
como *não atribuída*, com a causa nomeada, e o total do projeto a exclui
dizendo quantas ficaram de fora. Ver `references/metrics.md`.

**Prazo e cauda são coisas diferentes.** Prazo é do primeiro registro até a
entrega; cauda é o que veio depois, na mesma worktree. Somar os dois dava 40 h
onde a entrega saiu em 26, e o número não distinguia "demorou a entregar" de
"voltou a mexer".

**Duas atividades na mesma branch dividem o custo, e o painel acusa.** O
transcrito não diz de qual das duas é cada turno, então a ferramenta não
inventa critério: nomeia o par e mostra quanto entra duas vezes.

## O pacote nunca se impõe

Três garantias, e elas valem juntas:

**Você pode trabalhar sem o fluxo.** As skills só rodam quando você as invoca —
não há hook, não há gatilho automático, nenhuma delas se oferece sozinha. Ter o
pacote instalado e tocar uma atividade à mão é um modo de uso legítimo, não uma
violação.

**Você pode desligar o pacote inteiro** com `install.sh --desligar`. Ele
continua no disco e some da vista de todas as sessões.

**Você pode usar só parte dele.** `fluxo.steps` no config declara quais steps
este projeto usa. É política de projeto, não escolha por atividade — um time
onde o UX é de outra pessoa legitimamente não roda o step 6.

Desligar step é permitido, **nunca silencioso**. Desligar portão humano (5, 7,
10) ou verificação (4, 9) imprime aviso alto, e a lista do que ficou de fora vai
para o front matter da atividade, para o histórico e para todo relatório. Uma
entrega que pulou verificação diz isso na própria cara.

O motivo da trava: um fluxo com toda a cerimônia e nenhuma conferência é **pior**
que não usar fluxo nenhum, porque parece rigoroso.

## Capacidades: descubra antes de precisar

O pacote roda em máquinas diferentes, para pessoas com contas e acessos
diferentes. Uma skill que assume capacidade que não tem falha no meio da
atividade; uma que pergunta antes degrada de propósito.

```bash
python3 tools/flow-state/capabilities.py         # tudo
python3 tools/flow-state/capabilities.py figma   # uma só
```

**Nenhum "não" impede o fluxo.** Cada um tem caminho alternativo previsto:

| Capacidade | Sem ela |
| --- | --- |
| Figma acessível | Step 6 vai pelo `screen-drawer` — o outro caminho previsto, não degradação |
| Orçamento de Figma largo | Estratégia de racionamento: uma navegação, uma leitura, e para |
| ReportLab | Relatório em Markdown; o PDF só importa na fronteira com humano |
| Navegador | Protótipo sem screenshot, **dizendo** que a conferência visual não foi feita |
| Gates declarados | O `quality-reviewer` improvisa — e reporta a ausência como achado |
| Skill de Git do projeto | O step 1 assume o papel inteiro |

A regra é sempre a mesma: **degrade e diga o que não foi feito, nunca finja.**

### O orçamento do Figma decide a estratégia

O gargalo do step 6 não é a ferramenta, é a conta. Os limites de leitura do MCP
oficial seguem o **seat**, e o limite vale pelo plano onde o **arquivo** mora:

| Seat | Orçamento |
| --- | --- |
| Dev / Full | 200 a 600 chamadas **por dia** |
| Collab / View | 6 a 20 chamadas **por mês** |

Com seat Collab, uma tela mal conduzida queima a cota do mês. O `figma-reader`
chama `whoami` **antes de qualquer leitura** e escolhe a estratégia a partir da
resposta.

## Antes de abrir a atividade

Três verificações baratas, no step 1, que evitam gastar dez steps no que não
precisava de nenhum: **já foi rejeitado? já está implementado? a alegação se
confirma?**

O resultado muda a trilha, então vem antes de escolhê-la — um bug que não
reproduz não é `curta`, é pergunta ao reportador. Sem isso, a trilha `curta` vai
do step 1 ao 8 e o developer "conserta" o que ninguém confirmou estar quebrado.

A terceira tem um desfecho que se disfarça: **"não havia detalhe para tentar" é
diferente de "tentei e não reproduziu"**, e é o sinal mais forte de que falta
informação. Ver `references/check-first.md`.

## A memória de rejeição

O que o produto decidiu **não** fazer vive em `docs.fora_de_escopo` — um arquivo
por **conceito**, não por card — e é consultado antes de qualquer análise, por
conceito e não por palavra.

Ela fica no repositório do **projeto**, e não no `.agents`. É a única parte deste
pacote que sai do ferramental de propósito: decisão de produto precisa sobreviver
à troca de ferramenta, à saída de quem decidiu, e a alguém remover o `.agents`
inteiro.

Quando um pedido bate num conceito rejeitado, **nenhuma skill recusa sozinha**:
mostra a decisão antiga, com o que a mudaria, e pergunta se ainda vale. Ver
`references/rejection-memory.md`.

## Especificação é documento de vida longa

Uma SDD atravessa três portões humanos entre ser escrita e ser implementada, e
pode esperar semanas enquanto o código se move embaixo dela.

Por isso ela nomeia **tipo, contrato e comportamento**, e nunca caminho de
arquivo nem número de linha. "Altere `orders.service.ts:214`" fica errado no
dia em que alguém insere dez linhas acima — e continua *parecendo* preciso.

A regra é **oposta** para achado de revisão: ali `arquivo:linha` é o que faz o
corretor achar o problema, e o achado é consumido na mesma hora. **Vida curta
pede endereço; vida longa pede nome.**

## Anexar é ação verificada

Todo relatório que vai para o card sobe por
`tools/attach/attach.py`, que **verifica por ida e volta**: envia, baixa o que o
servidor guardou, compara o hash, e só vincula ao card se os bytes baterem.

Onde ele sobe depende do rastreador, e o pacote deduz do remote — `[tracker]
backend` no config sobrepõe. No Azure DevOps o PDF vira anexo do work item. No
GitHub vira **asset de um release de tag fixa**, e a issue recebe o link por
comentário: a Issue não tem API de anexo, e o asset é a única superfície do
GitHub que aceita binário, devolve binário e vale em repositório privado — que é
exatamente o que a verificação acima exige.

Não é zelo excessivo. Aconteceu: um PDF foi anexado com `az rest --body
"@arquivo"`, que trata binário como texto e sobe **base64**. A API devolveu 200,
o anexo apareceu no card, e o arquivo não abria — 14.640 bytes onde havia
10.979, exatamente 4/3, e começando com `JVBERi0x` em vez de `%PDF`. Nada na
resposta dizia isso.

**Um upload que mente é pior que um que falha.** Por isso a verificação não é
opção, não tem flag para desligar, e a falha diz o que aconteceu e que nada foi
anexado.

Para conferir o que está no card:

```bash
python3 tools/attach/attach.py --conferir <card>
```

### Verificar que subiu é do step, não do usuário

A verificação de ida e volta prova que **o byte chegou íntegro**. Ela não prova
que **o anexo aconteceu** — e essa é outra falha, que já custou uma atividade
inteira.

Numa execução real o `attach.py` mandava `Content-Type: application/pdf`, e a
API do Azure só aceita três tipos, nenhum deles o do arquivo. **Todo PDF era
recusado com 400.** O step 2 tinha a obrigação escrita na skill, o comando
estava lá, e o anexo nunca subiu. Descobriu-se uma atividade depois, por acaso,
quando o usuário perguntou se os resumos estavam no card.

Duas obrigações, e as duas são baratas:

1. **Confira depois de anexar.** Rode `--conferir <card>` e confirme que o
   arquivo aparece na lista. Uma linha, e é a diferença entre "eu mandei" e
   "está lá".
2. **Registre o anexo no estado da atividade**, para o `status` mostrar:
   ```bash
   python3 $F artefato <id> --tipo anexo --caminho <nome-do-pdf>
   ```
   Sem isso, o único lugar que sabe se o card recebeu o resumo é o card, e
   ninguém olha o card no meio do fluxo.

**O step não se declara concluído com o anexo em dúvida.** Se o anexo falhar,
diga que falhou e por quê — uma entrega marcada como não anexada é honesta; uma
que diz "anexado" sem ter conferido é a que custou a atividade.

### Quem anexa, e quem não anexa

O card acumula um PDF por step que anexa. Anexar tudo transforma o histórico em
ruído, e aí ninguém abre nenhum.

O critério é **quem lê**: vai ao card o artefato que tem leitor **fora do time
técnico**.

| Step | Anexa | Por quê |
| --- | --- | --- |
| 2 · análise de negócio | **sim** | O analista precisa das correções que voltam para ele |
| 3 · análise de sistema | **sim** | O dono do produto precisa saber o que vai ser construído |
| 6 · telas | **sim** | É o artefato que analista e produto mais reconhecem |
| 9 · revisão da entrega | **sim** | É o que a pessoa lê no portão 10, antes de validar |
| 4 · revisão da spec | não | Veredicto é instrumento do fluxo: serve ao step 3, não a quem lê o card |
| 8 · desenvolvimento | não | Resumo de implementação é técnico, e o diff já o conta melhor |

As decisões dos portões **não** viram anexo: elas moram no repositório, ao lado
da spec que governam, e quem as tomou foi a pessoa que leria o card.

## O manual do ofício

`references/` guarda o que os componentes precisam **saber** — separado do que
eles precisam **fazer**, que é o SKILL.md de cada um.

| Referência | O que ensina | Quem lê |
| --- | --- | --- |
| `review-lens.md` | O banco de perguntas, por tema | 2, 3, 4, `implemented-business-reviewer` |
| `traceability.md` | A matriz que não mente, e os sete estados | 2, 3, 4 |
| `pending-decisions.md` | Como escrever uma pendência decidível | 2, 3, 4, 6 |
| `technical-posture.md` | Como decidir quando o projeto não declara nada | 3, 8, `code-reviewer`, `quality-reviewer`, `security-reviewer` |
| `screen-specification.md` | O que é uma tela especificada | 6, 8, `figma-reader`, `screen-drawer` |
| `writing-requirements.md` | A gramática que torna um requisito testável | 2, 3 |
| `severity.md` | A mesma escala em todos os revisores | 4, 9 e os cinco revisores |
| `check-first.md` | As três verificações que vêm antes de abrir a atividade | 1 |
| `rejection-memory.md` | O que o produto já decidiu não fazer | 1, 2, 3 |
| `build-memory.md` | O que o produto já construiu, e por que a divergência é o achado | 2, 3 |
| `evidence.md` | Afirmar não é provar — vale para quem produz, não só para quem revisa | 2, 3, 6, 8, 9 e todos os revisores |
| `knowledge-graph.md` | Quando um grafo do repositório ajuda, e as três regras que impedem que ele vire evidência falsa | 3, 8 |
| `metrics.md` | O que a métrica mede, os quatro erros de atribuição que a moldaram, e o que ela NÃO prova | 9, e quem cita qualquer número do painel |
| `root-cause-debugging.md` | Causa raiz antes da correção: as quatro fases, a regra das três tentativas, e o que uma correção precisa deixar escrito | 8, 9, `code-reviewer` |

E `references/specialties/`, que é o que faz de cada subagente um
especialista em vez de um leitor de checklist:

| Especialidade | Quem lê |
| --- | --- |
| `code-review.md` | `code-reviewer` |
| `security.md` | `security-reviewer` |
| `test-and-quality.md` | `quality-reviewer` |
| `screen-design.md` | `screen-drawer`, `figma-reader` |
| `implementation-check.md` | `implemented-sdd-reviewer`, `implemented-business-reviewer` |
| `system-usage.md` | `runtime-reviewer` |
| `evidence.md` (compartilhada) | `business-analysis-auditor` |
| `executable-prototype.md` | `screen-drawer`, step 6 |
| `figma-reading.md` | `figma-reader` |
| `implement.md` | step 8 |

Cinco revisores em paralelo só valem mais que um se cada um souber de fato a sua
frente. Sem isso, são cinco leituras genéricas do mesmo diff, e a paralelização
custa cinco vezes para entregar o mesmo.

A separação existe por dois motivos. O primeiro é que vários ofícios se repetem:
"como escrever uma decisão que alguém consegue decidir" serve a cinco
componentes, e duplicá-la em cinco arquivos garante que as cinco cópias divirjam.

O segundo é o que faz o pacote valer fora daqui. **Sem essas referências, um
componente sabe o procedimento e não sabe o ofício** — segue o checklist e
entrega algo que passa nos portões sem ser bom. Num projeto que já tem skill
complementar isso não aparece, porque a skill do projeto cobre o buraco. Num
projeto novo, aparece na primeira atividade.

## O que é da máquina

Três coisas que o fluxo fazia com modelo e passou a fazer com comando. Não é
economia por economia: a máquina conta certo, e não erra sem perceber que errou.

| Ferramenta | O que resolve | Quem usa |
| --- | --- | --- |
| `tools/matrix/matrix.py extrair` | Enumera seções, acha identificadores, conta por seção. Lê `.md`, `.docx` com tabelas, e `.pdf` | 2 |
| `tools/matrix/matrix.py conferir` | Reprova matriz incompleta, item sem estado, item sem destino, seção que anuncia um tipo e entrega zero | 2, 3, 4 |
| `tools/briefing/briefing.py` | Levanta uma vez o que as cinco frentes redescobriam cinco vezes | 9 |
| `tools/outcome/outcome.py` | Conta o que aconteceu com cada achado. Reprova destino ausente, negado, ambíguo ou sem prova | 2, 4, 9 |
| `tools/ratchet/ratchet.py` | Separa o que a entrega quebrou do que já falhava. Só aperta: base consertada encolhe e não volta | 8, 9 |
| `tools/honesty/honesty.py` | `.only` commitado, pulo estático, asserção trivial, teste que simula o que testa, e quantos casos não rodaram | 8, 9 |
| `tools/profiles/profiles.py` | O diff toca autorização? E a passada por perfis prova o que diz, ou só o que não pode? | 9 |
| `tools/doctor/doctor.py` | O config deste projeto bate com este projeto? Roda ao instalar, antes da primeira atividade | instalação |
| `tools/briefing/domain.py` | Mapeia o terreno do domínio: entidades, migrations, rotas, métodos, specs, ADRs, códigos de erro — e a base da branch | 3 |
| `tools/already-exists/already_exists.py` | Isto já existe? E se existe, o que a demanda **acrescenta**? Acha a spec dona e mede o delta | 1 |
| `tools/figma/figma.py` | Lê o Figma por API REST, em camadas — `GET` não consegue escrever | 6 |
| `[ambiente]` do config | Como subir a aplicação: infra, apps, url, espera. A frente de execução usa | 9 |

**A matriz.** Extrair 167 itens à mão custou quinze minutos e uma contagem
errada que ninguém notou — o total dizia 155. O comando faz em segundos e
denuncia sozinho quatro coisas que a leitura não pega: seção do sumário que saiu
vazia (costuma ser imagem), seção que anuncia um tipo e entrega zero,
identificador citado e nunca definido, lacuna de numeração.

O que ele **não** faz é o que vale: decidir o estado de cada item, dizer onde
ele foi parar, achar contradição e cardinalidade. Isso continua sendo leitura.

**O dossiê.** As cinco frentes do step 9 gastaram 310 mil tokens em 36 linhas de
diff, e a maior parte foi redescoberta idêntica. O dossiê levanta os fatos uma
vez — diff (inclusive não commitado), arquivos com os não rastreados marcados,
símbolos de API e quem os referencia, portões, documentos, stack.

**O mapa do terreno.** O step 3 gastou 284 mil tokens e 91 chamadas para
especificar 18 requisitos, e a maior parte foi descobrir onde as coisas moram.
O mapa varre uma vez e devolve por papel: entidades com colunas e decorators,
migrations com só o SQL do domínio, rotas montadas, métodos públicos, specs
anteriores, ADRs, testes, traduções, códigos de erro em uso, e a memória de
rejeição que cita o assunto.

**E declara a base.** Na mesma execução a análise pressupunha um módulo que
existia só numa branch 33 commits à frente e não mesclada — especificar contra
a branch padrão teria quebrado no primeiro import.

**Ele não carrega nenhum achado, de propósito.** As frentes valem porque julgam
de forma independente; um dossiê que apontasse faria as cinco olharem para o
mesmo lugar. Fato entra, julgamento é de cada uma.

**O destino.** Uma revisão real produziu vinte e um achados, e ninguém sabia
quantos tinham virado mudança. A informação existia — espalhada em três tabelas
com três vocabulários, e nenhuma somável com as outras. O comando lê a coluna
**Destino** e conta: corrigidos, descartados, aceitos, abertos.

Ele acusa quatro coisas que a leitura não pega. Achado sem destino. Destino
escrito por negação — *"não fechado"* diz o que não aconteceu e some com o que
aconteceu, e a primeira versão da própria ferramenta leu cinco linhas assim como
fechadas, inflando a taxa para o lado que agrada. `corrigido` sem nada que o
sustente. E bloqueio que ficou aberto, ou que foi aceito sem portão humano.

O número não é meta — perseguir taxa de conversão produz achado fácil inventado
e achado difícil não escrito. Ele existe para a pergunta ser feita, e hoje ela
não é feita nenhuma vez. Ver `references/outcome.md`.

**O doutor.** O `install.sh` copia o `config.example.toml` — que carrega os
valores do projeto onde o pacote nasceu — e avisa para ajustar. Quem não ajusta
leva tudo junto, e nada falha na hora: uma skill de Git declarada e inexistente
faz o step 1 delegar para o nada; um gate apontando para script que não existe
só aparece quando o step 8 tenta rodar.

Ele confere o que está declarado contra o repositório: a skill existe, os
caminhos existem, os gates são scripts que existem, a catraca é coerente com os
gates, o comando de perfil roda, e o backend de anexo tem o que precisa. **Rode
ao instalar num projeto novo, antes da primeira atividade.**

O que ele **não** prova: que os valores estão certos. Ele confere que o que está
declarado existe — não que é o que você queria declarar.

**Os perfis de acesso.** *"Entrar com ator sem a permissão"* é a instrução mais
antiga da frente de execução e a que mais falhou — porque não tinha mecanismo.
Numa atividade real a resposta foi *"não há ator só-leitura no banco, e criar um
exigiria conta e senha"*, e a decisão de merge saiu com a autorização provada na
tela e não no `403`.

O projeto declara em `[perfis]` um comando que recebe o nome do ator e devolve um
token. **Nenhuma senha entra no fluxo.** Quando o diff toca superfície de
autorização, a passada por perfis deixa de ser recomendação e reprova quando
falta.

**E há uma regra que decide se ela vale alguma coisa: todo "não pode" vem com um
"pode", do mesmo ator na mesma sessão.** Um teste negativo passa trivialmente
quando a conta está quebrada — *"não consegui editar"* é verde tanto para a
permissão negada quanto para o login que falhou, a role renomeada, o seed que não
rodou. Sem o par, a matriz de perfis é verde falso com cara de cobertura.

Duas camadas, e elas respondem perguntas diferentes: **esconder um botão não é
recusar uma requisição.** A matriz mora na camada barata — perfis × rotas contra
as guardas de produção, dezenas de células em segundos. O navegador cobre só o
que ela não alcança, em dois perfis e não em sete.

Homologação fica fora por padrão: perfil de escrita cria linha que outras pessoas
veem. Ver `references/access-profiles.md`.

**A honestidade do teste.** Gate verde não é requisito provado. Numa entrega
real onze testes verdes provavam nada — achados por mutação, não por leitura —, e
o portão visual da mesma entrega fechou anunciando `145 passaram, 0 falharam`
com **152 ignorados na mesma linha**. As duas frases eram verdadeiras, e a
decisão foi tomada em cima da primeira.

A varredura acha `.only` commitado — que faz o resto do arquivo não rodar —,
pulo estático, asserção trivialmente verdadeira, caso sem asserção, caso que só
prova a fiação, e o arquivo que simula o próprio módulo que testa. A contagem diz
quantos não rodaram.

**Tudo isso é procedência `estrutural` e não reprova sozinho** — a exceção é
`.only`, que não tem leitura que o salve. O teste de verdade continua sendo a
mutação: quebre a implementação e veja se algum teste reprova.

E há uma lição sobre construir lente estrutural, que custou três rodadas: a
lente acusou 3, depois 35, depois 5 achados contra um repositório real, **e
todos eram legítimos**. Uma regra plausível encontra o padrão certo e a intenção
errada. Calibrar contra código real não é polimento — é a diferença entre uma
ferramenta e um gerador de ruído. Ver `references/test-honesty.md`.

**A catraca.** Um portão vermelho não diz se a entrega quebrou algo ou se já
estava assim, e quem recebe o vermelho tem três saídas ruins: caçar defeito que
não é dele, ignorar o portão, ou marcar "pré-existente" de memória — que foi o
que a POC fez, três vezes.

Ela guarda o conjunto de falhas conhecidas na base e classifica: **novo**
reprova, **conhecido** não, **consertado** faz a base encolher. O terceiro é o
que a faz catraca e não lista — o que foi consertado não volta em silêncio.

**A identidade de uma falha não pode conter o que uma edição legítima muda.** Um
aviso pré-existente foi registrado como `app-shell.tsx:176`; a entrega inseriu
código acima, e hoje o mesmo aviso mora na **185**. Guardar o número da linha
faria a catraca devolver a entrega por um aviso que ninguém tocou. A identidade é
`arquivo :: regra`, e para teste `arquivo > suíte > nome`.

E o gesto que a destrói tem nome: **regravar a base por cima do vermelho de
hoje**, que transforma regressão em passivo conhecido com uma linha de comando.
`gravar` recusa quando já há base; `apertar` só encolhe; admitir falha nova exige
`--admitir "<por quê>"`, e o motivo é impresso em toda conferência seguinte. Ver
`references/ratchet.md`.

**O delta.** A pergunta mais cara do fluxo é *"isto já existe?"*, e a segunda
mais cara é *"então o que esta demanda acrescenta?"*. Respondidas por leitura,
custam o módulo inteiro; respondidas por varredura, custam segundos.

O comando acha a especificação que já é **dona** do comportamento e mede quanto
da demanda ela já cobre. O que sobra é o candidato a delta — e é isso que muda o
fluxo:

**Complemento não reabre o módulo.** O step 2 revisa o delta, o step 3
**atualiza a SDD existente** em vez de escrever outra, o step 4 confere o delta.
Sem essa declaração cada step decide o escopo sozinho, e decide largo — porque
largo parece seguro. Largo aqui é só mais caro, mais lento, e produz
especificação duplicada que alguém vai ter que reconciliar.

### E o que é opcional

Um grafo de conhecimento do repositório responde barato o que o mapa não
alcança: travessia transitiva, caminho entre conceitos, arquivos que tratam do
assunto com outro vocabulário. **Nunca é dependência** — o pacote precisa
funcionar com zero instalação, e é isso que permite zipá-lo e mandá-lo.

Detecte com `python3 tools/flow-state/capabilities.py grafo`, declare em
`[capacidades] grafo`, e leia `references/knowledge-graph.md`. As três
regras, em uma linha cada: **grafo é pista, não evidência**; **aresta inferida
não é aresta observada**; **grafo velho é pior que grafo nenhum.**

## A conferência mecânica deixa rastro, e o `concluir` lê o rastro

Uma obrigação escrita em prosa não acontece. *"Entrar com ator sem a permissão"*
viveu meses na frente de execução e **nunca aconteceu uma vez** — ninguém
registrava, e portanto ninguém sabia.

O arquivo da atividade ganhou uma terceira tabela, **Conferências**, com quatro
veredictos:

| | |
| --- | --- |
| `exigida` | A ferramenta descobriu a obrigação. **Segura o `concluir`** |
| `ok` | A conferência rodou e passou |
| `falhou` | Rodou e reprovou. **Segura o `concluir`** |
| `nao-coberta` | Não deu para cobrir. **Passa, e fica visível** |

**Quem descobre a obrigação é quem a registra.** `profiles.py superficie
--registrar <id>` grava `exigida` sozinho quando o diff toca autorização — um
step que rodou a detecção não consegue mais "esquecer" de exercitar, porque a
exigência já está no arquivo antes de ele decidir qualquer coisa.

E o quarto veredicto é o que impede a regra de virar bloqueio burro: o fluxo
inteiro aceita dimensão não coberta **desde que declarada**. O que ele não aceita
é que ela suma.

## Obrigações de todo step de skill

### Disparar não é terminar

**Quem dispara subagente espera por ele.** Parece óbvio e falhou quatro vezes na
POC, em quatro steps diferentes: o step 2 aguardando a completude, o step 3
aguardando a auditoria, o step 3 de novo numa segunda rodada, e o step 9
aguardando as cinco frentes. Todos retornaram dizendo *"disparei, estou
aguardando"* — e o step ficou pela metade, com trabalho em curso e ninguém para
recolhê-lo.

Numa dessas, a frente de segurança tinha achado uma violação de isolamento, e o
achado ficou órfão.

O trabalho do step é **consolidar**. Disparar é o começo dele.

**Se o subagente não retornar**, procure o retorno onde ele possa ter ficado
antes de concluir que não houve — já aconteceu de o resultado existir e ficar
inacessível por quase duas horas, de um trabalho de quarenta e cinco minutos. Se
realmente não houver:

- **nomeie** o subagente que ficou sem resposta;
- declare a entrega **incompleta naquela dimensão**, no artefato e na nota;
- entregue o que você tem.

### Todo retorno passa por uma conferência de segundos

**Não aja sobre o que um subagente disse sem conferir que ele fez.** E a
conferência tem orçamento: **segundos**, não uma segunda revisão. Se está
custando mais de um minuto, deixou de ser conferência e virou outro trabalho —
essa é uma decisão sua, e consciente.

O que se confere é **o que foi pedido**, e o prompt é o contrato. Três perguntas,
nessa ordem, e pare na primeira que responder:

| Pergunta | Como custa segundos |
| --- | --- |
| **O artefato existe?** | `ls` no caminho que ele disse ter escrito, e o tamanho bate com o que ele descreveu |
| **O comando que ele diz ter rodado passa?** | Rode o mais barato e decisivo. O gate, o teste, o portão mecânico |
| **A afirmação que sustenta tudo é verdade?** | Abra **uma** — a que, se falsa, derruba o resto |

Não é desconfiança: é que a alternativa custa mais. Nesta POC, cada conferência
de retorno pegou coisa — o step 4 apontando um defeito que não existia, o step 8
declarando gate verde que tinha 126 invariantes desligadas, e uma auditoria
mandando remover um limiar cuja remoção reprovava a I2 em duas larguras.

E a conferência mais barata de todas é **contar**: seis frentes foram pedidas,
seis voltaram? Um step que dispara cinco e entrega o relatório de seis não
mente — ele não percebeu.

### Persista enquanto trabalha, não no fim

**O que existe só no contexto de um agente morre com ele.**

O `Revisor da Entrega` rodou as seis frentes, **todas voltaram**, e ele travou na
consolidação. Cinquenta e dois minutos, seis frentes de revisão sobre 6094
linhas, e **zero artefato** — os retornos moravam no contexto dele e foram junto.
A execução seguinte começou do zero.

Todo step longo escreve num arquivo de rascunho **conforme trabalha**:

- assim que cada subagente volta, o retorno **bruto** dele, antes de consolidar;
- durante a consolidação, cada achado conforme é julgado.

Custa segundos de escrita. O que ele compra é que um travamento vire *"continue
de onde parou"* em vez de *"comece de novo"*.

A regra vale para você, que dispara — e para o que você pede a quem dispara por
você.

### Um step que não escreve há muito tempo não está pensando

Um agente parado numa chamada de ferramenta **parece** um agente trabalhando: os
dois não respondem. A diferença é observável, e barata:

```bash
stat -f "modificado=%Sm" <arquivo de saída da tarefa>
```

Se o transcrito não é escrito há dezenas de minutos, ele não está pensando — está
travado. Um agente que trabalha escreve a cada chamada de ferramenta.

**Não fique esperando indefinidamente.** Confira, e se estiver parado: mate,
recolha o que foi persistido, e redispare dizendo de onde continuar. A espera
educada não entrega nada, e o usuário deste fluxo pediu orçamento de tempo para
subagente **duas vezes** antes de isto acontecer — a segunda vez, respondi que
não insistiria no assunto. Ele estava certo.

**Vigie, em vez de esperar.** A ferramenta que mede está pronta:

```bash
python3 $PACOTE/tools/watch/watch.py --dir <tasks da sessão>
python3 $PACOTE/tools/watch/watch.py --agente <id>     # os que você espera
```

Ela separa quem entregou de quem parou no meio, ignora comando em background, e
não lista agente de ontem. E declara o que não sabe: agente morto por interrupção
também para no meio, e de fora isso é igual a travado.

**Comando curto, uma coisa por chamada.** A execução que travou morreu num
`Bash` com vários `grep` concatenados por `;`. Não é prova de causa, e é barato
o bastante para valer como hábito.

Uma entrega marcada como não auditada é honesta. Uma espera indefinida não
entrega nada, e o silêncio de um subagente **nunca** conta como aprovação dele.



Todo step que é skill, sem exceção:

1. Lê o estado da atividade antes de começar e confirma que o step é o dele.
2. Produz seus artefatos em Markdown, no local que o `config.toml` define.
3. Registra cada artefato com `flow_state.py artefato`.
4. Roda seu subagente de completude, quando tiver um, **antes** de commitar.
5. Emite o relatório de fronteira humana com `tools/elcamargo-report` e anexa
   ao card, quando o step previr isso.
6. Chama a skill de Git do projeto para commitar.
7. Roda `flow_state.py avancar` e **entrega** o próximo step — sem executá-lo.

## A entrega entre steps

Um step termina imprimindo o comando seguinte, pronto para rodar:

```
Step 2 concluído. 4 pontos levantados, 2 bloqueiam a especificação.

Próximo:
    /elcamargo-system-analyst 1042
```

Duas regras, e as duas têm o mesmo motivo:

**A skill não executa a próxima.** Ela imprime o comando. Quem dispara é o
usuário — que assim vê a saída de cada etapa antes de gastar a seguinte, e
consegue apontar onde a cadeia quebrou quando quebra.

**O próximo step roda em contexto novo** — sessão nova ou subagente, nunca a
mesma janela. O handoff é por arquivo justamente para isso: o step seguinte
precisa ler a SDD, não o raciocínio de quem a escreveu. Contexto herdado faz o
modelo responder ao rastro anterior em vez de responder à especificação, e é
onde a fidelidade cai.

## Autoria dos documentos

Todo documento que sai para o cliente é assinado por **dois**: a skill que o
gerou e a pessoa que o revisou.

No front matter, a skill declara `gerado_por: <nome-da-skill>`. O `operador` do
config nomeia a pessoa. Uma linha do controle de versões sem nome explícito é
assinada pelos dois, e a página do termo de responsabilidade registra que o
documento teve assistência de IA e foi revisado antes de circular.

Assinar só a ferramenta esconde que alguém respondeu pelo conteúdo. Assinar só a
pessoa esconde como o documento foi produzido. Os dois nomes juntos são a única
versão verdadeira, e é por isso que a saída **precisa** ser revisada antes de
sair: a responsabilidade é compartilhada de fato, não de fachada.

## Skills complementares do projeto

Um step genérico pode ter uma skill do projeto que o **complementa**, declarada
em `[complementos]` no config:

```toml
[complementos]
system_analyst = "acme-system-analyst"
```

O step genérico roda primeiro e chama a complementar para o que só faz sentido
naquele projeto. Complementar, não substituir: uma skill de projeto costuma
carregar aprendizado que não cabe no pacote — casos que já custaram retrabalho
ali, convenções da stack, portões próprios. Descartar isso numa migração é
perder justamente o mais caro.

## Formato dos artefatos

**Markdown é o formato canônico.** Tudo que uma skill produz e outra consome é
MD versionado. PDF e DOCX são exportações, geradas por
`tools/elcamargo-report` **apenas na fronteira com humano**: o relatório que
volta para o analista de negócio, o anexo do card.

O motivo é operacional: o `implemented-sdd-reviewer` precisa *ler* a SDD para
conferir a implementação. PDF não é diffável, não é greppável, e não versiona
com sentido.

## Configuração do projeto

O pacote não sabe nada de nenhum projeto. Tudo que é específico entra por
`<.agents>/config.toml`. Ver `config.example.toml`.
