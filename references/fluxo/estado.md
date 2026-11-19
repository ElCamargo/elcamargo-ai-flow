# Fluxo · Estado da atividade

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

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
| `veredicto-sistema` | 3 (a conferência por dentro) ou 4 (`revisao`) | 3, na volta; o portão 5 tira dele as perguntas |
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
**sugere** (janela principal, no fecho do step). Desde a 2.71.0 a parte
*Vigente* põe em Sonnet a janela mestra (sugerida), o step 1, o 2 e o 6, onde o
erro tem quem o veja depois, e fixa Opus no 3, no 8, no 9 e em todo agente que
entrega achado. Descer uma frente de achado continua **hipótese**, que só a
perna sombra decide, e o coletor registra o modelo de cada turno
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
