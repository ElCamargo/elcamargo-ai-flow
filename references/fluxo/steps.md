# Fluxo · Os steps

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## Os steps

| # | Componente | Tipo | Entrega |
| --- | --- | --- | --- |
| 1 | `elcamargo-board-git-management` | skill | Card lido, trilha decidida, atividade aberta |
| 2 | `elcamargo-business-analysis-reviewer` | skill | Revisão da análise de negócio + SDD de negócio |
| 3 | `elcamargo-system-analyst` | skill | SDD de sistema |
| 4 | `elcamargo-system-analysis-reviewer` | skill | Só na `revisao` desde a 2.69.0; nas outras trilhas a conferência roda dentro do 3 |
| 5 | **Revisão humana da especificação** | humano | Aprovação da spec antes de gastar esforço em tela |
| 6 | `elcamargo-ux-reviewer` | skill | Decisões de tela documentadas |
| 7 | **Revisão humana das telas** | humano | Aprovação do visual antes de codar |
| 8 | `elcamargo-developer` | skill | Implementação |
| 9 | `elcamargo-development-reviewer` | skill | 5 revisões + correções aplicadas |
| 10 | **Validação humana da entrega** | humano | Aceite final |

Os steps 5, 7 e 10 são **portões**: o fluxo para e espera resposta humana. Uma
skill nunca atravessa um portão por conta própria.

**Quem atravessa o portão é a pessoa**, de um de dois jeitos: rodando o
`avancar` ela mesma, ou clicando a opção de aprovação no último card do portão.
Desde a 2.74.0 a janela que conduz a fase A leva o portão em cards e, **só com
esse clique**, roda o `avancar` com a nota `aprovado no card: ...`. Texto livre
ou silêncio não é aprovação. A skill que termina num portão imprime o comando
exato; a skill do step seguinte, se encontrar a atividade parada no portão,
recusa começar e reimprime o comando.
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

**Na fase B, a regra aperta.** Do step 8 ao portão 10 a pessoa não está na
conversa, e "na dúvida, pergunte" viraria espera. Ali só escalam os sete motivos
de `references/escalation.md` (`produto`, `contradicao`, `impossivel`,
`irreversivel`, `ambiente`, `laco`, `risco`), por `flow_state.py escalar`, que
deixa a atividade `AGUARDANDO VOCÊ` e trava o `avancar` até a resposta. O resto
o step decide e registra na tabela `## Decisões da fase B` da nota de
implementação, com a coluna *Como desfazer*.

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
