# Por que — Step 1 · Board e Git

Esta é a explicação da skill `elcamargo-board-git-management` (step 1 do
fluxo elcamargo-ai-flow). Não é instrução — o step não lê este arquivo para
saber o que fazer. É o porquê que saiu do corpo da skill para não entrar no
contexto de toda invocação; a SKILL.md continua completa quanto ao que fazer.

## História

*(sem passagem separável desta categoria; ver Incidente e O erro que produziu
isto, abaixo — ambas nasceram de um uso real da trilha `revisao`.)*

## Incidente

**Seção 5, "Abrir a atividade" — o lugar nascer `PENDENTE`.** Texto original:

> Não é esquecimento: quem roda o `iniciar` pode não estar na árvore da
> atividade, e até 2.45.5 o campo herdava o diretório de quem chamou. Em
> 21/09/2026 três aberturas seguidas nasceram apontando para a árvore
> principal.

## Número medido

*(o número medido do incidente acima — versão `2.45.5` e a data `21/09/2026`,
com "três aberturas seguidas" — está reproduzido no bloco de Incidente, para
não fragmentar a mesma passagem em duas seções.)*

## Exemplo longo

**Seção 4, "Decidir a trilha" — recomendação quando o passo 2 achou
complemento.** Texto original:

> **Se o desfecho do passo 2 foi complemento**, diga isso ao recomendar — e diga o
> delta. A trilha pode continuar sendo a `completa`, mas o que cada step vai
> produzir é muito menor, e o usuário precisa saber disso para julgar a
> recomendação:
>
> > Recomendo a `completa`: é análise de negócio nova. Mas é **complemento de
> > `CAM-002`** — o delta são dois requisitos, então o step 2 revisa esses dois e
> > o step 3 atualiza a SDD existente em vez de escrever outra.

## Justificativa de mais de uma frase

**Seção 4 — por que a trilha `rapida` merece dizer o preço em voz alta.**
Texto original:

> **A `rapida` é o caso oposto, e recomendá-la exige dizer isso em voz alta:** ela
> produz a especificação e a tela e decide não conferi-las, então o que ela troca
> por tempo é conferência, não cerimônia. Se o usuário a escolher, **não discuta
> de novo** — a decisão é dele, o `iniciar` já grava o preço no histórico, e
> repetir o argumento a cada step é o que faz uma ferramenta ser desligada. Diga
> uma vez, na escolha, e siga.

**Seção 4 — mecanismo por trás do sufixo de camada e da branch separada em
`backend`/`frontend`.** Texto original dos itens 1 e 2:

> 1. **O id leva o sufixo da camada** — `1081-backend` e `1081-frontend`. É como
>    uma metade acha a outra: o `iniciar` grava `outra_metade` a partir dele, e o
>    `concluir` tira dele o número do card para marcar o board. Id sem sufixo abre
>    com aviso, e o que se perde está escrito nele.
> 2. **Branch e PR próprios de cada metade.** A de trás mescla sozinha, dias antes
>    da outra. Dividir branch faz as duas somarem os mesmos turnos na métrica, e
>    os dois números saem errados.

**Seção 4 — o que o `concluir` faz sozinho no card, na entrega pela metade.**
Texto original:

> Diga ao usuário, na escolha, o que ele está aceitando: **o card fica entregue
> pela metade e bloqueado com `Aguardando frontend`** até a segunda atividade
> fechar, e o `concluir` põe a etiqueta e a justificativa no card sozinho. Ver
> `$PACOTE/references/half-delivery.md`.

**Seção 4 — por que registrar a saída do detector de caso.** Texto original:

> Ele responde `usou-o-fluxo`, `especificou-fora` ou `nao-documentou`, diz o que
> isso muda nos steps seguintes, e nomeia o que achou. **Registre a saída no
> histórico** — quem retomar a revisão depois precisa achar isso escrito.

**Seção 5 — por que o campo de lugar em aberto muda o aviso do step 9.** Texto
original:

> Quem lê esse campo depois é o step 9, para contar o que ficou sem commitar antes
> das frentes rodarem. Com ele em aberto, o aviso diz **"não conferi"** — e é
> melhor assim do que contar a árvore errada.

**Seção 6 — por que quem dispara o próximo step é o usuário, não esta janela.**
Texto original:

> **Rode-o você não.** Quem dispara é o usuário, que assim vê a saída desta etapa
> antes de gastar a próxima — e consegue apontar onde a cadeia quebrou quando ela
> quebra.

**Seção 6 — por que o próximo step precisa de contexto novo.** Texto original:

> **O próximo step roda em contexto novo**, sessão nova ou subagente, nunca esta
> mesma janela. É por isso que o handoff é por arquivo: o step seguinte precisa
> ler o artefato, não o raciocínio de quem o escreveu. Contexto herdado faz o
> modelo responder ao próprio rastro em vez de responder à especificação.

**Seção 2 — por que a verificação de "já existe" é rasa.** Texto original:

> A verificação é **rasa**: "isto é real, e mais ou menos onde vive?" — não "qual é
> a causa raiz?". Causa raiz é trabalho do step 8, depois de alguém decidir que
> vale investir nele.

## O erro que produziu isto

**Seção 4, admonição `[!erro]` sobre a trilha `revisao` — não deduzir o
caso.** Texto original:

> No primeiro uso real da trilha quem descobriu o caso foi a **porta**: ela leu
> a branch e entregou ao step 1 com a resposta pronta. Funcionou, e a sessão que
> conduziu escreveu a frase certa — *"se alguém entrar direto pelo step 1,
> ninguém descobre nada."*

A doutrina põe a descoberta do caso no step 1; nesse uso real, quem descobriu
foi a porta (`elcamargo-ai-flow`), que já tinha a branch e entregou a
resposta pronta. Funcionou, mas por coincidência — daí a regra de rodar o
comando mesmo quando alguém já disse o caso, testada em
`tools/flow-state/test_package.py`.

## Outras reduções de texto (mesmo sentido, menos palavras)

Estas passagens não são história, incidente, número medido, exemplo longo,
justificativa de mais de uma frase, nem "o erro que produziu isto" — são
regra ou instrução que só tiveram a formulação encurtada para caber no teto de
12 KiB. O sentido não mudou; quem quiser a redação original a encontra aqui.

- Admonição de abertura (trilha `revisao`), forma original:

  > [!atencao] Se a trilha é `revisao`, leia isto antes de qualquer coisa
  > **`$PACOTE/references/foreign-review.md`.** A trilha `revisao` (`1 → 2 → 4 → 9
  > → 10`) confere o trabalho de OUTRA pessoa, num card que não é seu. Ela roda em
  > worktree da branch que o dev entregou, não produz software, não commita, não
  > faz push e não escreve no card dele. Aqui você NÃO cria branch: cria worktree a partir da branch dele, descobre em
  > qual dos três casos está (usou o fluxo, especificou fora dele, ou não
  > documentou nada) e grava isso no histórico.

- Comentário original do resolvedor de `$PACOTE` (o código que segue é
  idêntico ao da skill; só o comentário foi comprimido a uma linha):

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

- Bullet do `check-first.md`, forma original: "**as três verificações que vêm
  antes de abrir a atividade.** Já foi rejeitado? Já está implementado? A
  alegação se confirma?"

- Leitura dos comentários do card, forma original: "É onde o analista responde
  dúvida, e é onde costuma estar 'isso já foi resolvido no card X' ou 'mudamos
  de ideia sobre o item 3'."

- Portão da seção 4, forma original: "Esta é a decisão que impede o fluxo de
  virar cerimônia. Apresente as três e **pergunte**; não escolha sozinho."

- Tabela de trilhas, forma original do aviso: "**Não decore esta tabela —
  imprima a de verdade**, para nunca apresentar ao usuário uma trilha que o
  script não tem:"

- Portões por trilha, forma original: "Diga quantos portões humanos a trilha
  tem: é isso que o usuário está aceitando ao escolher. A `curta` pula os
  portões 5 e 7 porque não produz especificação nem tela — não há o que
  validar neles."

- Retomar atividade existente, forma original: "Se a atividade já existe,
  **não reabra**. Diga em que step ela está e pergunte se o usuário quer
  retomar dali. Retomar é o caso normal — foi para isso que o estado existe."

- `criar` no board, forma original: "`criar` não existe em board nenhum, e não
  é esquecimento — ver abaixo."

- Comando de já-existe, forma original: "O resultado **muda a trilha**, então
  ele vem antes de escolhê-la: Comece pelo comando, que custa segundos e
  responde quase tudo:"

- Delegação à skill de Git do projeto, forma original: "**Se houver skill
  declarada, ela manda.** Invoque-a para ler o board, entender o card, criar
  branch, commitar, abrir PR — tudo que ela já faz, do jeito dela, com os
  portões dela."

- Sem skill de projeto, forma original: "Se não houver skill declarada,
  **você é o gerenciador de Git do projeto.** Não é um toco: é o papel
  inteiro, e o comportamento padrão abaixo vale."

- Branch sem padrão discernível, forma original: "Siga o padrão que estiver
  ali — é a convenção real, mais confiável que qualquer default."

- Corpo do commit, forma original: "com corpo explicando **por que**, não o
  que — o diff já diz o que."

- Nunca crie card, forma original: "**Nunca crie card.** O board é do
  solicitante; abrir item lá é decisão de gestão."

- Preenchimento do `avancar`, forma original: "se você o rodar de dentro da
  árvore onde o trabalho vai acontecer — que é o normal, porque a branch você
  acabou de criar."
