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
atividade por dias, retomá-la em outra sessão ou em outra worktree — sem que
nada mude.

**Rodar um step em subagente continua valendo — com três regras.**

- **Um step por subagente**, do tipo `elcamargo-step-runner`, e nunca um agente
  conduzindo vários. É a regra que mais pesa no custo; os números estão em
  *O que custa é o contexto acumulado*, mais abaixo.
- **Quem dispara frente dispara bloqueando.** Os quatro steps que disparam
  subagentes (2, 3, 6 e 9) usam `run_in_background: false`. Em segundo plano a
  notificação de conclusão não alcança quem está dentro de um subagente, e o
  turno acaba com as frentes rodando e ninguém para consolidá-las. Medido em
  `references/orchestration.md`.
- **Documento não viaja.** CPF ou CNPJ por extenso num contexto faz toda chamada
  seguinte voltar com o 403 do guardrail, e retomar não resolve: colhe-se com
  `doc_mask.py devolucoes` e dispara-se contexto novo. Em
  `references/documents-in-context.md`.

A consequência prática: **nenhum step depende de estar na mesma sessão que o
anterior.** Uma skill termina anunciando o próximo step; ela não o executa.

## Os steps

| # | Componente | Tipo | Entrega |
| --- | --- | --- | --- |
| 1 | `elcamargo-board-git-management` | skill | Card lido, trilha decidida, atividade aberta |
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

**Na segunda passagem, o contexto começa pelo que mudou.** Cada saída de portão,
aprovando ou devolvendo, grava a impressão e uma cópia de cada artefato e a
impressão da árvore (`atividades/<id>-portoes/`). Antes das perguntas, rode
`flow_state.py desde-aprovacao <id>`: ele compara com o último registro do
portão em que a atividade está — ou, se ela nunca saiu dele, com o último de
qualquer portão; o 7 da primeira passagem compara com a spec que o 5 aprovou. O
que saiu `[mudou]` ou `[novo]` é a parte nova, e é dela que saem os cards; o que
saiu `[igual]` já foi decidido. Link de Figma sai `[?]`: o endereço não muda
quando o desenho muda, e isso a pessoa precisa ouvir.

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
a entrega toca código de aplicação — inclusive quando o diff é só de backend,
porque backend que serve tela derruba tela.

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
| `rapida` | O Fluxo Rápido: pressa declarada, com o preço escrito | 1 → 3 → 6 → 8 → 9 → 10 |
| `ultra-rapida` | **Pedida pela gerência, não recomendada por este pacote.** Sem revisão da entrega | 1 → 3 → 6 → 8 → 10 |
| `especificacao-completa` | O analista especifica tudo e para; o card fica aguardando dev | 1 → 2 → 3 → 4 → 5 → 6 → 7 |
| `construcao` | O dev implementa a especificação que o analista deixou | 1 → 8 → 9 → 10 |
| `revisao` | Revisar o trabalho de outra pessoa, num card que não é seu | 1 → 2 → 4 → 9 → 10 |
| `backend` | A metade de trás de um card, entregue antes da tela | 1 → 2 → 3 → 4 → 5 → 8 → 9 → 10 |
| `frontend` | A metade da frente, depois que a de trás fechou | 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 |

A trilha `curta` não passa por especificação nem por tela, e por isso também não
passa pelos portões 5 e 7 — eles existem para validar exatamente o que ela não
produz. Sobra o portão 10, que é o aceite.

Na trilha `curta`, o step 9 roda `code-reviewer`, `quality-reviewer` e
`security-reviewer`. As duas frentes que ficam de fora são as que conferem
contra especificação — e a `curta` não produz nenhuma.

**Isso é dito no `iniciar` desde 2.42.0, e não era.** O aviso genérico se deriva
de *"a trilha produz o que o conferidor ausente olharia"*, e a `curta` não
produz nada — então ela saía muda. Só que havia o que dizer, e não é sobre
portão: **o step 9 dela cobre três das seis dimensões, e as duas que faltam são
as únicas que respondem *"é isto que foi pedido?"*.** A `curta` não tem baseline
de documento; a linha de comparação é o código de antes mais o card. Medido nas
quatro `curta` que chegaram ao portão 10 até 15/09/2026: o achado que mudou
decisão veio de execução ou de qualidade, **nunca** de leitura contra
especificação. Por isso dispensar a frente de execução aqui não é perder uma
dimensão — é ficar sem nenhuma. O `security-reviewer`
não lê especificação: parte da stack e do diff, e um ajuste de uma linha numa
rota é exatamente onde um vazamento entre clientes entra em produção.

### A trilha `revisao` — conferir o trabalho de outra pessoa

As outras quatro **produzem** software. Esta não: ela confere o que já foi
entregue, num card que não é seu, contra o que o card pediu.

O cenário: você precisa revisar a entrega de outro dev e **não sabe** se ele
revisou negócio, se especificou, se leu o Figma, se implementou tudo, nem se a
qualidade é a que vocês querem. Refazer o trabalho para descobrir custaria mais
que ele ter feito de novo.

**O card é a âncora, porque é a única peça do conjunto que não saiu das mãos
dele.** Se o dev escreveu SDDs, elas entram como *objeto de revisão*, nunca como
fonte da verdade: uma especificação que leu o card errado produz código fiel ao
erro, e conferir código contra ela só prova coerência interna. É o mesmo buraco
que faz o step 9 ter duas frentes separadas em vez de uma.

Por isso o step 2 roda sempre aqui, mesmo com documentação do outro lado: ele lê
o card e produz a **baseline** — a lista do que dá para cobrar. O step 4
confronta com ela o que o dev escreveu, se escreveu; quando não há documento, a
ausência é achado do relatório e a trilha segue.

**Três coisas que a forma da trilha garante, sem depender de ninguém lembrar:**

| Ela não | Por quê |
| --- | --- |
| **conserta** | não tem step 8, então o step 9 não tem a quem devolver — os achados saem em relatório, e quem conserta é o dono do card |
| **escreve no card dele** | publicar crítica no card de outra pessoa é decisão dela; o step 1 lê o board e não anexa nada |
| **para o seu trabalho** | roda em **worktree da branch que o dev entregou**, nunca na árvore em que você está implementando |

A worktree não é conforto, é necessidade: duas frentes do step 9 escrevem em
disco — a de qualidade insere mutantes no código-fonte, a de execução cria
fixtures. A branch é dele, a worktree é sua, e nela não se commita nem se faz
push.

Doutrina inteira em `references/foreign-review.md`, lida pelos steps 1, 2, 4 e 9
quando a trilha é `revisao`.

### A trilha `rapida` — o Fluxo Rápido

Ela mantém **quem produz** — especificação de sistema, tela e código — mais o
revisor da entrega, e corta as três conferências que ficam entre eles: o step 4
e os portões 5 e 7. Do analista de sistema a tela vai direto para o
desenvolvedor; do desenvolvedor, com o step 9 no meio, direto para o portão 10.

**A diferença para a `curta` não é de tamanho, é de natureza.** A `curta` não
passa pelos portões 5 e 7 porque não produz nada que eles validem — a omissão é
gratuita. A `rapida` **produz** a especificação e a tela, e decide não
conferi-las. Isso não é o mesmo, e o fluxo não finge que é: o `iniciar` avisa o
que ficou de fora e **grava no histórico da atividade**, para quem estiver no
portão 10 achar. Quem valida no fim precisa saber o que não foi validado no
meio.

O que ela mantém, e o motivo de manter: o step 9 continua rodando inteiro. O
revisor da entrega é a única conferência que sobrou entre o código e a produção,
e tirá-lo não deixaria o fluxo rápido — deixaria o fluxo sem função.

| O que se ganha | O que se paga |
| --- | --- |
| Quatro steps a menos que a `sistema`, e dois portões humanos a menos de espera | A SDD vai para o código **sem ninguém ter conferido** se ela entrega o que o negócio pediu |
| Nenhuma volta possível nos pares 3↔4 — que na POC custaram ~7h de retrabalho | A tela vai para o código sem aprovação de quem pediu; retrabalho aqui aparece **depois** de estar implementado |

**Quando ela é a escolha certa:** demanda pequena e bem entendida, com prazo
que não cabe outra coisa, e alguém disposto a assumir o retrabalho se a
especificação estiver errada. **Quando não é:** quando o custo de refazer o que
foi construído é maior que o custo dos dois portões — que é quase sempre o caso
quando a demanda toca autorização, dinheiro ou dado de cliente.

### O par `especificacao-*` → `construcao` — quando quem analisa não é quem constrói

Esta ferramenta nasceu do modo de trabalho de quem **faz a análise e
implementa**. Nem todo dev especifica, e nem todo analista constrói. Estas duas
partem o fluxo no **portão 7**: a especificação entrega negócio, sistema e tela
decididos, e o card fica `Aguardando desenvolvimento`.

| | `especificacao-completa` | `construcao` |
| --- | --- | --- |
| steps | 1 → 2 → 3 → 4 → 5 → 6 → 7 | 1 → 8 → 9 → 10 |
| produz | as SDDs, as matrizes, as decisões de tela | o software |
| portões humanos | 5 e 7 | 10 |
| implementa | **nada** | tudo |

**Somadas dão exatamente a `completa`, e a interseção é só o step 1** — que cada
uma precisa para abrir a própria atividade. Nada do fluxo se perde no corte e
nada roda duas vezes. Há teste prendendo isso, porque a propriedade é o que
torna o par seguro e ela **não se vê olhando as duas listas separadas**.

Um card vira **duas atividades** — `1081-especificacao` e `1081-construcao` —,
como em `backend`/`frontend`.

#### A `construcao` tem a MESMA FORMA da `curta`, e essa é a armadilha

`1 → 8 → 9 → 10` nos dois casos. **A diferença inteira é o que a `construcao`
herda**, e por isso ela é invisível na lista de steps.

Ao abrir, o step 1 traz os artefatos da `especificacao` — SDDs, matrizes,
decisões de tela — **como artefatos registrados da atividade nova**. O step 8
implementa contra eles e o step 9 os confere como se esta atividade os tivesse
produzido.

O ganho é concreto e mensurável: **a `construcao` roda as seis frentes no step
9; a `curta` roda três.** As duas que faltam na `curta` — SDD implementada e
negócio implementado — são as únicas que respondem *"é isto que foi pedido?"*, e
elas precisam de um documento que só a especificação produz.

**Por isso o guarda RECUSA em vez de avisar.** Aberta sem a metade de
especificação, a `construcao` não fica pior: ela vira uma `curta` sem que nada
na lista de steps mostre isso. O `iniciar` nomeia a atividade que falta, e
`--forcar --nota` abre assim mesmo deixando escrito por quê.

#### Duas regras que a `construcao` carrega

**A especificação envelhece.** Entre o portão 7 e o dev passam dias, e o código
andou. Confira contra o que **existe**, não contra o que a spec supunha — a
mesma regra que a `frontend` carrega sobre o backend.

**Divergência volta ao analista, e não vira decisão do dev.** Achou que a spec
está errada: **relate e devolva**. A `construcao` não tem step 3 para
consertá-la, e corrigir a especificação de quem não aprovou a correção
transforma o contrato em rascunho. A conferência `especificacao-conferida`
segura o `concluir` até isso estar resolvido.

### A trilha `ultra-rapida` — pedida pela gerência, e o pacote não a recomenda

Ela é a `rapida` **sem o step 9**, e essa subtração é de outra ordem. A `rapida`
corta conferências de **documento** e mantém a última conferência do **código**.
A `ultra-rapida` corta também a do código: o desenvolvedor entrega direto ao
portão humano.

Duas seções acima, sobre a `rapida`, este documento já dizia — antes de esta
trilha existir — que tirar o step 9 *"não deixaria o fluxo rápido, deixaria o
fluxo sem função"*. **A frase fica.** A trilha existe porque foi pedida pela
gerência do projeto em 18/09/2026, com o custo de qualidade assumido por quem a
pediu, e não porque o pacote mudou de opinião.

| O que se ganha | O que se paga |
| --- | --- |
| Cinco steps a menos que a `completa`; nenhuma espera de portão até o fim | **Nada confere o código** — nem legibilidade, nem segurança, nem qualidade, nem se a tela funciona |
| A entrega chega ao aceite no menor tempo que este fluxo permite | O portão 10 recebe código que nenhuma máquina e nenhum revisor olhou |

**E há uma consequência que nenhum aviso genérico alcançaria**, por isso ela é
dita à parte: as conferências — árvore, memória, guardas — são registradas como
`exigida` ao **entrar** no step 9. Sem step 9, **nenhuma é pedida**, então
nenhuma aparece como pendência e o `concluir` não segura nada.

> **Ausência de pendência aqui não é sinal de que está tudo certo. É sinal de
> que ninguém perguntou.**

Ela emite **nove avisos** no `iniciar`, mais que qualquer outra trilha, e todos
vão para o histórico da atividade — que é onde quem estiver no portão 10 precisa
achá-los. O fluxo não impede a escolha; ele impede que ela seja silenciosa.

### As trilhas `backend` e `frontend` — um card, duas entregas

As outras cinco entregam um card de uma vez. Estas duas o partem em dois, em
tempos diferentes, e existem por um pedido concreto: **adiantar o backend, que
serve o front web e o mobile, para o time mobile não esperar o front web ficar
pronto.** Entre uma metade e outra o card fica bloqueado, com a etiqueta
`Aguardando frontend` posta pelo próprio `concluir`.

**A regra que resume as duas: cada metade ESPECIFICA as duas camadas e
IMPLEMENTA uma.** A que ela não implementa sai especificada, e essa
especificação é o contrato — na `backend`, é o que o time mobile consome sem
estar neste fluxo.

| | `backend` | `frontend` |
| --- | --- | --- |
| implementa | backend | tela |
| não tem | 6 e 7: não há tela para desenhar nem validar | — |
| o step 9 revisa | só a metade entregue | **a entrega inteira** |
| a conferência que segura o `concluir` | `contrato` | `entrega-ponta-a-ponta` |

**A `frontend` roda sempre depois da `backend`** — o `iniciar` confere e recusa
abrir antes, nomeando a atividade que falta. E ela valida a entrega inteira por
aritmética: é a última metade, e não há uma terceira para conferir o conjunto
depois dela.

**O contrato se prova por execução**, não por leitura: entrar no step 9 registra
a conferência como `exigida`, e a `runtime-reviewer` chama cada rota que o
`sdd-frontend` promete. Contrato errado custa o trabalho de outro time, semanas
depois, e nenhuma frente deste pacote estará lá.

Um card vira **duas atividades** — `1081-backend` e `1081-frontend` —, com
branches e PRs separados. Ver `references/half-delivery.md`.

Mudar de trilha no meio exige `--forcar` e uma nota dizendo por quê. Não é
proibido; é registrado. **Subir da `rapida` para a `sistema` no meio é o
caminho previsto** quando a especificação se mostrar maior do que parecia.

### O risco — o segundo eixo

A trilha diz **quantos** steps a atividade percorre; o risco diz **quanta
conferência** ela recebe no 9. São perguntas diferentes: uma correção de uma
linha na rota de login é `curta` e é `alto`.

O step 1 propõe o risco a partir de um checklist de superfícies — `autenticacao`,
`pagamento`, `dados-pessoais`, `migracao`, `contrato-publico`, que o `fluxo`
imprime com onde olhar — e **a pessoa confirma**, na mesma pergunta da trilha.
O `iniciar` grava `risco` e `superficies` no front matter, e o histórico diz que
foi confirmado.

| Risco | O que muda |
| --- | --- |
| `alto` | A entrada no 9 grava `seguranca` exigida, e ela **não sai por `nao-coberta`** no `concluir`. O portão `sast` também não sai por `nao-coberta` no 8→9. Sem `[gates] sast` declarado, a entrada no 9 avisa. |
| `padrao` | O de sempre. Atividade sem `--risco` conta como `padrao`, e o `iniciar` avisa. |
| `baixo` | Nada é cortado. É declaração, e as métricas separam por ela. |

**Recusas que o `--forcar` não atravessa:** `alto` em trilha que implementa sem
step 9 (`ultra-rapida`), porque o código iria da escrita direto à pessoa; e
`baixo` com superfície marcada, que se contradiz. As duas saídas são mudar a
trilha ou o risco, e as duas ficam escritas. `padrao` com superfície marcada e
`baixo` em trilha longa abrem com aviso.

Mudar o risco depois é `risco <id> --nivel <novo> --nota '<por quê>'`. Subir
para `alto` com o 9 já em curso grava a exigência que a entrada no 9 teria
gravado. O `percurso` das métricas conta a taxa de bug por risco, ao lado da
taxa por trilha.

**A perna sombra não liga no risco alto.** Os achados dela não entram na
consolidação: ela mede o revisor, não protege a atividade. O revisor de outro
modelo, que protegeria, é outra mudança.

## Os subagentes

Dez componentes nunca são invocados diretamente — só rodam como subagente,
chamados pelo step que os contém ou pela janela que dispara um step. Por isso
são agent definitions em `.claude/agents/`, e não skills: agent não entra no
contexto principal.

| Chamado por | Subagentes |
| --- | --- |
| A janela que dispara um step | `step-runner` — um step por disparo |
| Step 2 · `business-analysis-reviewer` | `business-analysis-auditor` |
| Step 6 · `ux-reviewer` | `figma-reader` **ou** `screen-drawer` |
| Step 9 · `development-reviewer` | `code-reviewer`, `implemented-sdd-reviewer`, `implemented-business-reviewer`, `security-reviewer`, `quality-reviewer`, `runtime-reviewer` |

### O que custa é o contexto acumulado

Medido em 25 e 26/09/2026, os dois dias de pico: todos os repositórios, janela
principal e subagente, deduplicado por `message.id`. O peso de cada token vem da
tabela de API e serve só como proporção.

| Contexto na resposta | Parte do custo |
| --- | --- |
| até 100 mil | 12% |
| 100 a 200 mil | 27% |
| 200 a 400 mil | 29% |
| **acima de 400 mil** | **32%** |

**Cada resposta relê o contexto inteiro.** Cache lido foi 64,5% do custo: 6,47
bilhões de tokens lidos contra 28 milhões de saída. O que faz o contexto crescer
foram três padrões:

| Padrão | Maior caso medido | O que fazer |
| --- | --- | --- |
| Um agente conduzindo vários steps | *"Card 1055 até o portão 5"*, 917 mil | um `step-runner` por step |
| A janela que orquestra também trabalha: lê código, abre navegador, espia frente com `tail`/`ls` | 843 mil, com 332 leituras e 293 espiadas | leitura e tela no subagente; espera por disparo bloqueante ou notificação |
| A mesma janela atravessando atividades | 12 atividades numa janela, 819 mil, 14% do custo de um repositório em dois dias; outra com 11.378 respostas e 9 atividades | atividade nova, janela nova |

**O ponto de partida pesa menos, mas pesa.** Um `general-purpose` nasce com ~49
mil tokens na app desktop, porque recebe o esquema de todas as ferramentas da
máquina. Um agente do pacote com ferramentas declaradas nasce com 9–12 mil. O
`step-runner` nasce com 15.880 na app desktop, contra 40–51 mil dos
`general-purpose` disparados na mesma sessão; na CLI, 11.892 contra 24.739.

**E o texto da skill é o menor dos três.** Ele acrescenta 7–16 mil ao contexto de
um step. Uma medição anterior o pôs em 51–61% do custo, e caiu: faltava
deduplicar, e quem mediu retirou.

**A janela que orquestra pode ser travada.** `/elcamargo-ai-flow orquestrar`
marca a janela, e um hook do pacote recusa nela, antes de rodar, o que é
trabalho de step: ler código, navegador, espiar frente, skill de step,
`general-purpose`. A recusa diz o que fazer no lugar. Subagente trabalha livre,
porque só a chamada da janela é barrada. Depois de cada compactação, as regras e
o `listar` voltam sozinhos. Só a pessoa sai, com `orquestrar sair`. Código em
`tools/orchestrator-guard/`.

**O que só a pessoa configura.** O Claude Code compacta sozinho perto do limite,
e nestes modelos o limite é 1 milhão. A configuração `autoCompactWindow` (ou a
variável `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, que tem precedência) compacta antes:
`200k`, por exemplo. `CLAUDE_CODE_DISABLE_1M_CONTEXT` **sozinha não basta** em
modelo que já nasce com 1 milhão, e o próprio Claude Code avisa que a sessão
continua crescendo. Conferido no binário da versão 2.1.281. O handoff por
arquivo é o que torna a compactação segura aqui: o que o step seguinte precisa
está no artefato, não na conversa.

**O que isto NÃO prova:** que um step por contexto rende o mesmo trabalho; e
nada da régua da cota da assinatura, que não é pública. A PoC que mede isso está
com as sessões dos projetos.

### Quem dispara subagente dispara bloqueando

Os quatro steps que aparecem nesta página como chamadores — 2, 3, 6 e 9 —
disparam com **`run_in_background: false`**, todas as frentes da mesma leva numa
única mensagem. Em segundo plano a chamada volta com um "lançado com sucesso"
que não é resultado, e quem disparou fica sem o que consolidar: um step 9 assim
gastou **193.310 tokens em três turnos dizendo que aguardava**, e entregou zero.

Na janela principal os dois modos terminam funcionando, porque a notificação de
conclusão reinvoca a sessão. **É o que torna o erro invisível até alguém
orquestrar de dentro de um subagente.**

Cada uma das quatro skills abre com essa regra, e
`tools/audit-package/audit_package.py` **reprova** a skill que dispara subagente
sem carregar `references/orchestration.md` — é o que impede a próxima de nascer
sem ela.

### As seis do step 9 rodam em levas, e não todas de uma vez

Cada frente se comporta como se tivesse a máquina inteira, e três são caras por
natureza — build, suíte completa, navegador. Seis juntas somaram mais de 3 GB
numa máquina já em 13,7 de 16 GB: ela paginou até travar, e o travamento matou
duas frentes. A revisão fechou com quatro de seis, e a que morreu era a única
que produz procedência `execução`.

São três levas — as quatro de leitura pura juntas, a de qualidade sozinha, a de
execução sozinha —, e **espera-se cada leva antes de abrir a próxima**. As levas
são a **ordem** entre as frentes que vão rodar, não a lista de quem roda: quem
decide isso é a trilha, e na volta 2 é o laço, que roda só as que falharam.

### Duas delas escrevem, e por isso rodam em árvore própria

`quality-reviewer` insere mutantes no código-fonte; `runtime-reviewer` cria
fixtures e tokens. As duas restauram depois — o problema é o "depois". Numa
execução real a máquina travou com três mutantes vivos em cima da validação de
boot de um segredo, e a restauração ganhou por segundos.

Pior que o risco foi o efeito colateral: as outras frentes estavam **lendo**
aquela árvore. Uma percebeu sozinha que duas leituras do mesmo arquivo davam
conteúdos diferentes e passou a revisar contra o commit — foi o que salvou a
revisão dela, e **foi sorte**.

Então: as duas que escrevem vão para worktree própria, as outras quatro não
escrevem nada, e `tools/tree-guard/tree_guard.py` confere que foi cumprido —
marcando antes do disparo e comparando depois, **por conteúdo**, porque a árvore
já chega suja da entrega do step 8 e um mutante por cima produz a mesma linha de
`git status`.

O `tools/process-guard/process_guard.py` faz o mesmo pelos **processos**, e é o
irmão que faltava: em 10/09/2026 as três árvores voltaram limpas e conferidas, e
quatro serviços de outra atividade do usuário estavam no chão — a frente de
execução limpou os próprios com `pkill -f`, e o padrão casou com o backend do
vizinho. **Isolar árvore protege o disco; não protege a máquina.**

E ele tem duas perguntas, não uma. `conferir` pergunta *o que havia antes
caiu?*; `sobra` pergunta *o que eu subi continua de pé?*. A segunda entrou na
2.56.0, depois de 02/10/2026: dez contêineres e treze processos sobreviveram
dois dias às atividades que os criaram, e o Mac de 16 GB travou com 5,2 dos 6
GB de swap em uso — com o `conferir` respondendo verde o tempo todo, porque
nada tinha caído. Ver `references/work-tree.md`.

Isso não é garantia estrutural: as seis declaram `Bash`, e o pacote não tem como
impedir. É contrato com conferência.

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
5. Re-roda **somente as frentes que falharam**, não as seis.
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

**Qual é a parte aceita não se adivinha também.** A saída do portão grava o que
ele viu, e `desde-aprovacao <id>` mostra o diff de cada artefato e o `--stat` do
código contra esse registro. Até a 2.60.0 a regra existia sem nada que separasse
uma parte da outra, e quem voltava ao portão relia o documento inteiro.

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

### O lugar da atividade se preserva, e só muda por comando

`branch` e `worktree` no cabeçalho dizem **onde a atividade é construída**, e o
step seguinte lê exatamente esses dois campos para saber onde trabalhar.

O `avancar` já os regravava do diretório de quem chamou, toda passagem de step.
A intenção era acompanhar uma atividade que muda de branch no meio do fluxo; o
efeito é que o comando **não distinguia** isso de "quem chamou estava em outro
lugar". Em 08/09/2026 um `avancar` rodado da raiz do repositório — que estava na
branch de outra atividade — retargetou branch e worktree sem imprimir nada.

Agora: **o valor gravado vence, e a divergência vira aviso.** O `avancar` mostra
os dois lugares lado a lado e o comando para mudar de propósito. Preservar em
silêncio seria o defeito oposto — atividade que mudou de branch de verdade
apontando para sempre para o lugar antigo —, e as duas falham do mesmo jeito.

Mudar é ação declarada, com rastro no histórico da atividade:

```bash
python3 $F corrigir <id> --branch <branch> --worktree <caminho> --nota 'por quê'
```

Ele recusa branch ou árvore que não existem — `--forcar` aceita, para o caso de
ainda irem ser criadas. E os dois campos andam juntos: **metade de um lugar
descreve um lugar que nunca existiu.**

### O `iniciar` NÃO deriva o lugar do diretório

Até 2.45.5 ele derivava, com o mesmo argumento: *ali é a primeira gravação, e
não há o que preservar*. O argumento é verdadeiro e a conclusão era errada —
quem roda o `iniciar` está, **por definição**, num lugar que não é o da
atividade: é o **step 1** que cria a branch e a worktree, depois. O campo
nascia descrevendo a árvore principal de quem abriu o card.

Em 21/09/2026 três aberturas seguidas nasceram assim, corrigidas à mão depois. O
estrago não é o campo feio: é que ele **carimba de certo um lugar errado**. O
contador de entrega não commitada do step 9 contava a sujeira da árvore alheia e
a reportava como entrega da atividade — medido, 8 entradas de outra sessão sobre
uma atividade cuja árvore estava limpa.

Desde 2.46.0 os dois campos nascem `PENDENTE`, e **o primeiro `avancar` rodado
de dentro da árvore de verdade os preenche sozinho, sem avisar** — preencher
lacuna declarada não é retarget. A partir daí vale a preservação descrita acima.

Quem já conhece o lugar declara na abertura, e as bandeiras são independentes:

```bash
python3 $F iniciar <id> --titulo '...' --trilha curta \
    --branch feat/x --worktree /caminho/da/arvore
```

`PENDENTE` não é meia-verdade sobre um lugar — é **a lacuna dita em voz alta**.
Por isso, diferente do `corrigir`, aqui uma bandeira sozinha vale.

**E o que não se sabe não se conta.** Com o campo em aberto, o aviso de entrega
não commitada do step 9 diz *"não conferi"* em vez de contar a raiz do projeto:
uma árvore principal limpa devolvia **zero**, e zero se lê como *entrega
commitada*. Não saber não é a mesma coisa que estar limpo.

### Texto livre vai entre aspas SIMPLES

Toda flag que recebe prosa — `--nota`, `--comentario`, `--titulo`, `--motivo`,
`--detalhe`, `--admitir` — vai entre **aspas simples**, e os exemplos deste
pacote são escritos assim.

O motivo é uma armadilha silenciosa, e ela mordeu em 09/09/2026: entre aspas
**duplas**, o shell trata crase como **substituição de comando**. Uma nota
escrita na voz deste pacote — *"o `avancar` foi forçado porque…"* — chega ao
comando **sem a palavra**, o shell imprime `command not found` no meio da saída,
e a ferramenta reporta sucesso, porque recebeu exatamente o que lhe foi passado.
O erro aconteceu antes dela.

Nenhuma verificação alcança isso: do lado de dentro não há nada errado a
conferir. E a nota do `avancar` entra **permanente** no histórico da atividade.

**Se o texto precisar de apóstrofo**, não escape dentro da aspa simples — troque
a palavra, ou passe o texto por variável:

```bash
NOTA='três achados, um bloqueia'
python3 $F avancar 1042 --nota "$NOTA"
```

Aspas duplas em torno de `$NOTA` são seguras: a substituição de comando já não
acontece sobre o **valor** de uma variável.

### Comandos

```bash
F=.agents/elcamargo-flow/tools/flow-state/flow_state.py

python3 $F fluxo                       # steps e trilhas
python3 $F iniciar 1042 --titulo '...' --trilha completa --risco padrao
python3 $F status 1042                # onde está; sem id, lista todas
python3 $F avancar 1042 --nota '...'  # entra no próximo step da trilha
python3 $F artefato 1042 --tipo sdd-sistema --caminho docs/specs/...
python3 $F corrigir 1042 --branch feat/x --worktree /caminho/da/arvore
python3 $F gates 1042                 # roda os portões e grava cada código de saída
python3 $F risco 1042 --nivel alto --nota '...'  # muda o risco, com o motivo
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
no meio, `--forcar --trilha <nova> --nota '<por quê>'`. Até a 2.59.0 a ajuda
dizia isso e o código não conferia: a trilha mudava num `avancar` comum, sem
nota. Agora `--trilha` sem `--forcar` é recusado, e a nota registra
`Trilha: <antes> → <nova>`.

`concluir` exige estar no último step da trilha, ou `--forcar` com nota.

`--reabrir` **preserva** histórico, artefatos e data de criação. Reabrir uma
atividade não apaga o que já aconteceu nela. A linha que a reabertura escreve
começa com `Reaberta:`, e é por essa marca que o percurso a conta.

**Bug que escapou de uma entrega** abre atividade NOVA com
`iniciar <id> --corrige <origem>`. A origem fica no front matter (`corrige:`) e
no histórico, e as métricas contam o bug **na origem**, por trilha dela — é o
único jeito de responder se a trilha curta cobra o preço depois. O comando
avisa, sem recusar, quando a origem não existe neste projeto ou ainda está
aberta (aí o lugar do conserto é o step 8 dela, não uma atividade nova), e
recusa `--corrige` da própria atividade. Ele **não escreve** na origem: a
sessão do conserto entraria nas sessões dela e contaminaria a atribuição de
custo.

Toda mutação toma um lock exclusivo. Um arquivo por atividade impede dois
processos de dividirem um arquivo; não impede dois processos de lerem o mesmo
estado e escreverem um por cima do outro. `os.replace` é atômico, não é um lock.

### Vocabulário dos artefatos

O fluxo só reconhece estes, e o comando **avisa** quando recebe outro — ele
registra assim mesmo, porque perder o registro é pior que o rótulo errado, mas
**tipo que ninguém reconhece some para quem procura**. A lista mora em
`TIPOS_DE_ARTEFATO`, no `flow_state.py`: tipo novo entra nos dois lugares ou não
entra em nenhum.

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
| `revisao-publicada` | 9 ou 10, **só na trilha `revisao`** | — (vai ao dono do card, fora do fluxo) |
| `sdd-backend` | 3, nas trilhas `backend` e `frontend` | 4, 8 e 9 da `backend`; na `frontend` é o que se confere contra o backend que EXISTE |
| `sdd-frontend` | 3, nas trilhas `backend` e `frontend` | 4, 8 e 9 da `frontend`; na `backend` é o **contrato**, exercitado rota a rota pela `runtime-reviewer` |

`--caminho` é caminho de arquivo, sempre. Prosa nesse campo produz um artefato
que ninguém consegue abrir.

### As métricas se atualizam sozinhas

Toda passagem de step e todo `concluir` recolhem as métricas **daquela**
atividade para `<.agents>/metrics/`. Nada a lembrar, pela mesma razão da
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
python3 $M publicar                      # o RESUMO dentro do repositório
```

**O percurso sai do Histórico.** Voltas de correção (9→8, 4→3), devoluções
de portão com o motivo (`escopo` quando a nota diz, `defeito` no resto),
aprovações por portão, reaberturas e tempo de relógio por step. O `relatar`
mostra o do projeto e o da atividade, e `flow_state.py tempo <id>` imprime o
de uma só. Como as conferências, ele não depende de atribuição: sai do arquivo
da atividade. O detalhe e o que ele não prova estão em
`references/metrics.md`.

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

**O andamento do projeto pode ficar no repositório, a um clique.** O
`install.sh` põe `.agents/` em `.git/info/exclude` — ferramental de IA não é
entregável do cliente —, e a consequência é que o painel só existe no disco de
quem rodou. Com `[metricas] publicar_no_repo = true`, o `avancar` regenera
`docs/metricas.html`, `docs/metricas.md` e um bloco no README a cada passagem
de step, e o `concluir` os **indexa** — nunca commita, mesmo idioma do
`attach.py`.

O publicado é **menos** que o painel, de propósito: **hora humana por atividade
não sai.** Versionada ao lado do nome da branch, ela vira nota de desempenho
individual, e a métrica não foi desenhada para isso — o total do projeto fica.
A página traz a régua APF ao lado do medido, com **dois** fatores (relógio e
hora humana) porque um só, publicado sem o outro, é número que cai na primeira
pergunta. E leva exportar para PDF, Teams e e-mail.

**Qual modelo em qual step** é decisão de custo, e ela tem regra própria em
`references/model-policy.md`: o que se **fixa** (subagente, na chamada) e o que se
**sugere** (janela principal, no fecho do step). Desde a 2.52.0 ela tem uma parte
*Vigente*: o step 1 e as duas frentes do step 6 rodam em Sonnet, porque o que
entregam vai a uma pessoa antes de alguém construir em cima. O resto continua
**hipótese**, sem medição, e o coletor registra o modelo de cada turno
justamente para que ela possa ser confrontada com número em vez de defendida com
argumento. E a ordem das alavancas não começa no modelo: **cache primeiro**, que é
93% do gasto medido, depois `effort`, e só então trocar de tier.

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

### Ler o Figma é REST, e não MCP

A leitura do step 6 é a **API REST**, pelo `tools/figma/figma.py`, com um token
pessoal fora de todo repositório. Sem MCP, sem app desktop, sem navegador
logado. O MCP é o caminho da **escrita**, que é ação separada e nasce
desligada.

A razão não é conveniência: **`GET` não consegue escrever.** Num arquivo da
empresa, com gente trabalhando dentro, essa garantia vale mais que qualquer
comodidade — e é por isso que **o plano B nunca é o navegador**. Quando a
leitura falha, o step para, diz o que falhou, e pede export ao usuário.

Se há token é pergunta de máquina, e o pacote responde:

```bash
python3 tools/flow-state/capabilities.py figma_leitura
```

Ele cruza o que o projeto **quer** com o que a máquina **consegue**, e imprime
os comandos de leitura — ou o comando exato de instalar o que falta. Isso existe
porque a resposta anterior era `?`, escrita em nomes de tool do MCP, e uma
frente irmã leu nela que sem MCP não havia leitura. Havia.

A disciplina que continua valendo é a do **custo de contexto**: comece raso
(`paginas`), escolha o nó, e só então desça (`resumo`). Descer direto na árvore
inteira gasta numa chamada o que a atividade toda deveria gastar. Os orçamentos
por seat da tabela do MCP valem para o MCP — na REST o que limita é o que a
conta do token alcança, mais o `429` que a API devolve quando se insiste.

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

Todo relatório que vai para o card sobe por `tools/attach/attach.py`, nunca pela
API do rastreador direto. A ferramenta **verifica por ida e volta**: envia,
baixa o que o servidor guardou, compara o hash, e só vincula ao card se os bytes
baterem.

**Um upload que mente é pior que um que falha** — já aconteceu aqui, com a API
devolvendo 200 sobre um PDF que não abria. Por isso a verificação não é opção e
não tem flag para desligar.

Para conferir o que está no card:

```bash
python3 tools/attach/attach.py --conferir <card>
```

### Verificar que subiu é do step, não do usuário

A verificação de ida e volta prova que **o byte chegou íntegro**. Ela não prova
que **o anexo aconteceu** — e essa é outra falha, que já custou uma atividade
inteira: a ferramenta recusava todo PDF com 400, a obrigação estava escrita na
skill, e ninguém percebeu até alguém perguntar se os resumos estavam no card.

Daí duas obrigações depois de anexar, e as duas são baratas: rodar `--conferir`,
e registrar o anexo no estado da atividade com `artefato --tipo anexo`. **O step
não se declara concluído com o anexo em dúvida** — uma entrega marcada como não
anexada é honesta; uma que diz "anexado" sem ter conferido é a que custou a
atividade.

Os três defeitos por inteiro, com os números que os provaram, estão em
`references/card-attachment.md` — junto do procedimento que eles moldaram.

### O card recebe pergunta, não relatório

O critério antigo era **quem lê**: ia ao card o artefato com leitor fora do time
técnico. Ele parecia certo e produziu o defeito oposto ao que evitava — quatro
steps produzem documento com leitor de negócio, então quatro anexavam, e o card
virou uma pilha de PDF em que o que precisava de resposta se perdia no meio do
que era só registro. **Um card com seis anexos não tem nenhum.**

O critério agora é **o que exige resposta**:

> Vai ao card o documento que **pergunta** alguma coisa que **só uma pessoa de
> fora do time técnico pode responder**. Todo o resto fica no repositório.

Não é uma regra sobre importância. O resumo do step 9 é o documento mais denso
do fluxo e continua não indo ao card quando não pergunta nada: ele é versionado,
diffável e greppável no repositório, e o card não é nenhuma das três coisas.

**Quem decide é a pendência.** Uma pendência aberta, com os seis campos de
`references/pending-decisions.md` e dono fora do time técnico, é exatamente "algo
que só o analista pode responder" — e é o que abre o portão: sem `--pendencia`,
o `attach.py` **recusa**.

O procedimento inteiro — o comando, o que a ferramenta recusa e por quê, e a
conferência obrigatória depois de anexar — está em
`references/card-attachment.md`, num lugar só. Ele já esteve copiado em quatro
skills, que é onde a divergência entra sem ninguém ver.

| Step | Quando vai ao card |
| --- | --- |
| 2 · análise de negócio | Quando a revisão abriu pendência para o analista |
| 3 · análise de sistema | Quando a SDD tem decisão que só o negócio fecha |
| 6 · telas | Quando uma divergência de tela ficou sem dono técnico |
| 9 · revisão da entrega | Quando um achado ficou aberto e depende de decisão de fora |
| 4 · revisão da spec | Nunca: veredicto é instrumento do fluxo, serve ao step 3 |
| 8 · desenvolvimento | Nunca: resumo de implementação é técnico, e o diff o conta melhor |
| `concluir` da trilha `backend` | **Sempre**: o `sdd-frontend` sobe como contrato — ver abaixo |

**A segunda razão, e ela não é pergunta.** De 15/09/2026: sobe ao card também o
documento de que alguém precisa **e cujo repositório essa pessoa não alcança**.
É o `sdd-frontend` que a trilha `backend` escreve — o contrato que outro time
vai construir contra, num card próprio, sem acesso a este repositório. Sem o
anexo ele não recebe nada, e o critério de cima o deixaria de fora com razão:
contrato não pergunta, informa.

`attach.py --contrato "<quem>"` declara isso, **exige nomear o público** e faz o
comentário do card dizer, na linha, que não há o que responder. As duas razões
não se combinam: documento que pergunta *e* informa sobe como pergunta. O
`concluir` da `backend` anexa sozinho, e avisa alto quando a atividade não
registrou nenhum `sdd-frontend` — ele é o produto de verdade daquela trilha.

Zero pendências é o caso **normal**, não a exceção — e nele o step registra o
artefato e segue:

```bash
python3 $F artefato <id> --tipo <tipo> --caminho <caminho>
```

### Arquivo renomeado no meio da atividade

O `artefato` só acrescentava, e isso produzia **ponteiro morto**. Medido em
24/09/2026: uma spec renomeada durante a atividade fez o `status` listar **três**
`sdd-sistema`, um deles apontando para arquivo que não existia mais. As seis
frentes do step 9 **abrem** esses caminhos — a que não achar reporta *"a spec não
existe"*, e o achado parece defeito da entrega quando é ponteiro velho.

Renomeação **troca**, não acrescenta:

```bash
python3 $F artefato <id> --tipo <tipo> \
    --substituir <caminho antigo> --caminho <caminho novo>
```

Artefato que deixou de existir **sai com explicação**:

```bash
python3 $F artefato <id> --tipo <tipo> --caminho <caminho> \
    --retirar --nota 'por quê'
```

`--nota` é obrigatória ali porque um registro que some sem explicação é
indistinguível de um que nunca houve — a mesma razão do rastro no `corrigir`.

**E o `status` marca `(AUSENTE)`** o caminho que parece arquivo e não existe nem
na raiz do projeto nem na worktree da atividade. Registrar um assim **avisa na
hora e registra assim mesmo**: recusar perderia o registro de um artefato que
existe, que é a mesma razão pela qual tipo fora do vocabulário passa.

A conferência só roda no que **parece arquivo** — barra e extensão no último
segmento, sem esquema de URL. `prototipo` recebe caminho de componente do Figma,
`anexo` recebe nome de anexo de card, e nenhum dos dois vira alarme.

As decisões dos portões continuam sem virar anexo: elas moram no repositório, ao
lado da spec que governam, e quem as tomou foi a pessoa que leria o card.

**O portão humano não depende do anexo.** Os steps 6 e 9 entregam o portão como
perguntas — cartões clicáveis, no máximo quatro — e não pedindo que alguém leia
um PDF. Um anexo a mais nunca foi o que fez o portão andar.

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
| `severity.md` | A mesma escala em todos os revisores | 4, 9 e os seis revisores |
| `check-first.md` | As três verificações que vêm antes de abrir a atividade | 1 |
| `rejection-memory.md` | O que o produto já decidiu não fazer | 1, 2, 3 |
| `build-memory.md` | O que o produto já construiu, e por que a divergência é o achado | 2, 3 |
| `evidence.md` | Afirmar não é provar — vale para quem produz, não só para quem revisa | 2, 3, 6, 8, 9 e todos os revisores |
| `knowledge-graph.md` | Quando um grafo do repositório ajuda, e as três regras que impedem que ele vire evidência falsa | 3, 8 |
| `capacidades.md` | Poder e política são eixos diferentes: o que a máquina consegue e o que o projeto quer, e por que escrever no Figma nasce desligado | 6, e quem for ligar ou desligar uma ação |
| `card-attachment.md` | O que vai ao card e o que fica no repositório, e as três falhas que moldaram o `attach.py` | 2, 3, 6, 9 |
| `work-tree.md` | A árvore do step 9 é compartilhada: quem pode escrever nela, quem não pode, e o que a conferência não prova | 9, `quality-reviewer`, `runtime-reviewer` |
| `metrics.md` | O que a métrica mede, os quatro erros de atribuição que a moldaram, e o que ela NÃO prova | 9, e quem cita qualquer número do painel |
| `root-cause-debugging.md` | Causa raiz antes da correção: as quatro fases, a regra das três tentativas, e o que uma correção precisa deixar escrito | 8, 9, `code-reviewer` |
| `half-delivery.md` | Um card em duas metades: cada uma especifica as duas camadas e implementa uma, e o contrato se prova por execução | 1, 3, 4, 8, 9, quando a trilha é `backend` ou `frontend` |
| `documents-in-context.md` | CPF e CNPJ nunca por extenso num contexto, e por que o 403 do guardrail não se retoma | os dez agentes, e quem dispara step ou frente |
| `shadow-leg.md` | A perna sombra: uma frente do step 9 em dois modelos, com o mesmo prompt, e o critério que decide se ela desce de modelo | step 9, com `capacidades.perna_sombra` |
| `defect-classes.md` | O registro das classes de defeito que escaparam da revisão: o formato, quem confere e quem acrescenta | steps 8 e 9, e as seis frentes do 9 |

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
| `figma-writing.md` | `ux-reviewer`, `screen-drawer` |
| `implement.md` | step 8 |

Seis revisores só valem mais que um se cada um souber de fato a sua frente. Sem
isso, são seis leituras genéricas do mesmo diff, e a paralelização custa seis
vezes para entregar o mesmo.

A separação existe por dois motivos. O primeiro é que vários ofícios se repetem:
"como escrever uma decisão que alguém consegue decidir" serve a cinco
componentes, e duplicá-la em cinco arquivos garante que as cinco cópias divirjam.

O segundo é o que faz o pacote valer fora daqui. **Sem essas referências, um
componente sabe o procedimento e não sabe o ofício** — segue o checklist e
entrega algo que passa nos portões sem ser bom. Num projeto que já tem skill
complementar isso não aparece, porque a skill do projeto cobre o buraco. Num
projeto novo, aparece na primeira atividade.

## O que é da máquina

O que o fluxo fazia com modelo e passou a fazer com comando. Não é
economia por economia: a máquina conta certo, e não erra sem perceber que errou.

| Ferramenta | O que resolve | Quem usa |
| --- | --- | --- |
| `tools/matrix/matrix.py extrair` | Enumera seções, acha identificadores, conta por seção. Lê `.md`, `.docx` com tabelas, e `.pdf` | 2 |
| `tools/matrix/matrix.py conferir` | Reprova matriz incompleta, item sem estado, item sem destino, seção que anuncia um tipo e entrega zero | 2, 3, 4 |
| `tools/briefing/briefing.py` | Levanta uma vez o que as seis frentes redescobriam seis vezes | 9 |
| `tools/tree-guard/tree_guard.py` | Marca a árvore antes do disparo das frentes e confere depois, por conteúdo | 9 |
| `tools/prior-work/prior_work.py` | Em qual dos três casos da trilha `revisao` a entrega está: o dev usou o fluxo, especificou fora dele, ou não documentou nada | 1, na trilha `revisao` |
| `tools/process-guard/process_guard.py` | Marca quem já escutava e quais contêineres estavam de pé antes do disparo, e depois confere as duas direções — o que caiu (`conferir`) e o que a atividade deixou de pé (`sobra`) —, amostrando o pico de memória durante as levas | 9, `runtime-reviewer`, gancho de abertura de sessão |
| `tools/outcome/outcome.py` | Conta o que aconteceu com cada achado. Reprova destino ausente, negado, ambíguo ou sem prova | 2, 4, 9 |
| `tools/ratchet/ratchet.py` | Separa o que a entrega quebrou do que já falhava. Só aperta: base consertada encolhe e não volta | 8, 9 |
| `flow_state.py gates` | Roda os portões de `[gates]`, um por vez, e grava o código de saída de cada um como `gate:<nome>`. O `avancar` 8→9 lê essa tabela | 8, 9 |
| `tools/anchor/anchor.py --contexto` | Gancho de `PreToolUse` de Bash: grava sessão + subagente de quem vai rodar o comando. O `avancar` 8→9 guarda o do 8, e o 9→10 recusa o mesmo | 8, 9 |
| `flow_state.py status` no step 9 | Avisa quando o contexto é o que fez o 8, e diz o `model` de cada frente com `[revisao.modelo]` — só vale com veredito `adota` da perna sombra | 9 |
| `flow_state.py desde-aprovacao` | O que mudou nos artefatos e no código desde a saída do último portão, que o `avancar` e o `concluir` gravam sozinhos | 4, 6, 9 — antes das perguntas do portão |
| `tools/matrix/matrix.py casos` | O contrato de casos: um por `CT` da SDD, a fase vermelha antes da implementação, o `passa` escrito pela saída da suíte. `conferir-testes` cruza tudo com a SDD | 8, 9 |
| `tools/gate-guard/gate_guard.py` | Gancho de fim de turno: lembra, uma vez, a janela do step 8 que encerra com portão sem `ok` | 8 |
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
de forma independente; um dossiê que apontasse faria as seis olharem para o
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
`--admitir '<por quê>'`, e o motivo é impresso em toda conferência seguinte. Ver
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

### O step 8 não passa para o 9 com portão vermelho

A mesma tabela fecha o step 8. `flow_state gates <id>` roda o que `[gates]`
declara e grava `gate:<nome>`; o `avancar` do 8 para o 9 **recusa, mesmo com
`--forcar`**, enquanto algum portão declarado não tiver `ok` ou `nao-coberta`
gravado **depois da última entrada no 8**, ou enquanto a última conferência
`casos` estiver `exigida` ou `falhou`. A fatia por data é o que faz a volta de
correção do 9 rodar os portões de novo: o verde de antes da correção não serve.

Vermelho que a catraca reconhece inteiro como da base vira `ok` com o motivo no
detalhe. Portão que não se aplica se declara `nao-coberta` com o porquê. O
`resumo.json` em `atividades/<id>-gates/` guarda a impressão da árvore; o
`gates <id> --conferir` diz ao step 9 se o resultado ainda vale, e a frente de
qualidade lê em vez de rodar de novo. Ver `references/case-contract.md` para o
contrato de casos.

Dois ganchos lembram o que o comando já trava: o de fim de turno avisa, uma vez
por conjunto de faltas, a janela do 8 que encerra com portão sem `ok`; o de
PreToolUse recusa editar o `-casos.json` à mão.

**O que isto NÃO prova:** que os testes provam o requisito. Prova que o comando
declarado devolveu aquele código naquela árvore.

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

**Entre o 8 e o 9 a regra é trava, não só prosa.** É o par em que ela mais pesa:
a janela que escreveu o código e o revisa tende a concordar com o próprio
raciocínio. Contexto é **sessão mais subagente** — no modo orquestrador o 8 e o
9 rodam na mesma sessão, em subagentes distintos, e está certo. Um hook de
`PreToolUse` grava quem vai rodar cada Bash; o `avancar` do 8 para o 9 guarda
quem fez o 8; o `status` do step 9 avisa quando é o mesmo contexto, e o
`avancar` para o 10 **recusa**. Voltar ao 8 para corrigir passa, porque não
aprova nada. Atravessar é `--forcar --nota`, e fica escrito. Sem o hook —
outro harness, ou comando digitado no terminal — a trava não sabe, e cala em
vez de acusar.

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
