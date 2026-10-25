# Entregar um card em duas metades

Lida por: steps 1, 3, 4, 8 e 9, **quando a trilha é `backend` ou `frontend`**.

O cenário que originou este arquivo, em 15/09/2026: *"a gerência me pediu para
adiantar as atividades de backend do app, que servem o front web e o
mobile. Assim o time mobile acelera, e eu sigo no frontend do card depois de
fechar todos os backends. Meus cards ficam parados até fechar o front — no card
vai ter uma tag `Aguardando frontend`, e eles ficam bloqueados com a
justificativa de somente backend implementado."*

    backend    1 → 2 → 3 → 4 → 5 → 8 → 9 → 10        (sem tela)
    frontend   1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

## 1. A regra que resume tudo

**Cada metade ESPECIFICA as duas camadas e IMPLEMENTA uma.**

A camada que ela não implementa não fica em branco: ela sai especificada, e essa
especificação é o **contrato**. Quem construir a outra metade — inclusive quem
não está neste fluxo — constrói contra ele.

| | `backend` | `frontend` |
| --- | --- | --- |
| implementa | backend | tela |
| escreve | `sdd-backend` **e** `sdd-frontend` | os dois, completando o que já existir |
| o contrato é | o `sdd-frontend` | o `sdd-backend` |
| quem consome o contrato | o time mobile e o front web | a próxima atividade de backend, se houver |
| o step 9 revisa | **só a metade entregue** | **a entrega inteira** |

## 2. Por que o contrato é o produto de verdade da `backend`

O backend fecha e é liberado sozinho. A partir dali, **o time mobile constrói
contra o `sdd-frontend`** — e esse time não está neste fluxo, não lê o arquivo
da atividade, e não vai perguntar. Se o contrato estiver errado, o custo cai em
outro time, semanas depois, e nenhuma frente deste pacote estará lá para pegar.

Por isso ele **se prova por execução, e não por leitura**. Entrar no step 9 de
uma atividade `backend` registra a conferência `contrato` como `exigida`, e ela
segura o `concluir`:

> cada rota que o `sdd-frontend` promete existe e responde o que está escrito

A frente que fecha isso é a `runtime-reviewer`. Não é conferência de tipo nem de
schema declarado: é chamar a rota e ler o corpo.

**O argumento que decide, e ele é medido.** Em 09/09/2026 um `array_agg(opcao.label)`
num adapter de backend — zero arquivos de frontend no diff — derrubou o
formulário de primeiro acesso inteiro, `500` em toda chamada. Três frentes de
leitura, em duas voltas, não acharam. Numa entrega que é **só** backend, a
leitura tem ainda menos com o que se desentender: a tela que revelaria o defeito
não existe. Execução não é uma dimensão a mais aqui — é a única testemunha
externa.

## 3. O que o step 9 NÃO deve achar na `backend`

Duas das seis frentes perguntam *"a entrega faz o que foi pedido?"* —
`implemented-sdd-reviewer` e `implemented-business-reviewer`. Numa entrega
deliberadamente pela metade, elas vão encontrar tudo o que falta **de
propósito**.

> **Ausência da camada de tela não é defeito: é o escopo.** Achado contra a
> metade que não foi entregue é achado contra uma decisão de quem pediu.

O campo que responde isso é `escopo`, no front matter da atividade, e ele é
**derivado da trilha** — não é bandeira que alguém lembra de passar. Leia-o
antes de julgar:

```bash
python3 $PACOTE/tools/flow-state/flow_state.py status <id> | grep escopo
```

O que essas duas frentes continuam devendo achar: o backend entregue não faz o
que a `sdd-backend` especificou; o backend entregue contradiz o card; o contrato
promete o que o backend não entrega. As três são achados legítimos, e a terceira
é a mais valiosa da trilha.

## 4. Na `frontend`, a revisão é do TODO

Decidido em 15/09/2026, junto com a regra de que a `frontend` **sempre** roda
depois da `backend`:

> O step 8 implementa só a tela. O step 9 valida a **entrega inteira** — backend
> já mesclado mais a tela nova, no fluxo que o usuário percorre.

A razão é aritmética: esta é a última metade, e não há uma terceira para
conferir o conjunto depois dela. A conferência `entrega-ponta-a-ponta` nasce
`exigida` ao entrar no step 9 e segura o `concluir`.

**O backend pode ter andado.** Entre as duas metades passam dias. O que a tela
precisa se confere contra **o backend que existe**, e não contra o `sdd-backend`
de semanas atrás — que é documento, e documento não recompila.

**Buraco achado vira especificação, não implementação.** Se a tela precisa de
algo que o backend não tem, a `frontend` **completa o `sdd-backend`** e declara
a pendência. Ela não escreve backend: o escopo dela é a tela, e furar isso faria
a metade de trás ser entregue sem nunca ter passado por um step 9 de backend.
Uma atividade `backend` nova é o caminho.

## 5. O par de atividades, e por que ele tem sufixo

Um card, **duas atividades**, branches e PRs separados:

    1081-backend     branch própria, PR próprio, mescla sozinha
    1081-frontend    branch própria, PR próprio, dias depois

O sufixo não é estética: é como uma metade **acha** a outra sem tabela nova e
sem adivinhar por título. O `iniciar` grava `outra_metade` no front matter a
partir dele, a `frontend` confere por ele se a de trás fechou, e o `concluir`
tira dele o número do card para marcar o board. Id fora da convenção avisa, e o
aviso diz o que se perde.

**Por que não uma atividade reaberta:** o `concluir` do backend registraria o
card como concluído, e ele não está. **Por que não a mesma branch:** duas
atividades que dividem branch e janela somam os mesmos turnos nas duas na
métrica — o detector de sobreposição acusa, e os dois números ficam errados.

## 6. O card não pode mentir enquanto isso

Entre uma metade e outra, o card fica com a etiqueta e a justificativa, postas
**pelo fluxo**:

```bash
python3 $PACOTE/tools/board/board.py marcar <card> \
  --tag 'Aguardando frontend' --porque '<o que foi entregue e o que falta>'
```

O `concluir` da `backend` faz isso sozinho, e o da `frontend` remove. Etiqueta
posta à mão é etiqueta que um dia não se põe — e quem lê o board é justamente
quem não está no fluxo para saber disso: o gerente que pediu a antecipação, e o
time que vai construir contra o contrato.

**A etiqueta nunca derruba o encerramento.** Board `nenhum`, `az` ausente,
máquina sem rede: o `concluir` vale, diz que não conseguiu marcar, e imprime a
linha de comando que refaz só a etiqueta.

> **O bloqueio É a etiqueta, e nada além dela.** Decidido pelo Ederson em
> 15/09/2026, quando a pergunta era se "bloqueado" seria um estado do card no
> Azure. Não é: o fluxo põe a etiqueta e escreve a justificativa, e **não muda
> estado, responsável, nem fecha nada**. Está escrito aqui para ninguém reabrir
> a decisão daqui a três meses, não achar motivo, e resolver mexer no estado do
> card de outra pessoa — que é a escrita que este pacote recusa desde que o
> `board.py` existe.

## 6b. O contrato sobe ao card, porque é o único caminho que existe

Quem vai construir contra o contrato **não tem este repositório** — trabalha num
card próprio, no repositório da outra superfície. `docs/specs/` não o alcança.

Por isso o `concluir` da trilha `backend` anexa o `sdd-frontend` ao card, com
`attach.py --contrato`, e o comentário diz na linha que aquilo **não pergunta
nada**: é a especificação da camada que ainda não foi implementada, para quem
vai implementá-la. O anexo é conferido por ida e volta, como todo anexo deste
pacote — os bytes que voltam são os que subiram.

**Só na `backend`.** O contrato da `frontend` é o `sdd-backend`, e quem o
consumiria é a próxima atividade de backend — que vive neste repositório e lê o
arquivo onde ele está.

**Se a atividade não registrou `sdd-frontend`, o `concluir` avisa alto.** Não
barra: barrar deixaria a atividade presa em andamento por causa de um registro.
Mas a ausência é notável, e por isso fala — sem o contrato no card, a outra
metade não recebe nada.

## 7. O que esta trilha NÃO promete

- **Que o contrato está certo.** Ela prova que cada rota prometida responde o
  que está escrito. Não prova que o que está escrito é o que a tela vai
  precisar — isso só a metade da frente descobre, e é por isso que ela completa
  a especificação em vez de segui-la cegamente.
- **Que o card está entregue.** Backend concluído é metade de um card. O `PF`, a
  entrega ao usuário e o aceite são do conjunto, e o portão 10 da `backend`
  valida uma metade sabendo que é uma metade.
- **Que dá para pular a `backend`.** A `frontend` recusa abrir antes dela. Onde
  o backend veio de fora do fluxo, `--forcar --nota` abre e deixa escrito de
  onde ele veio — e o portão 10 acha isso.
