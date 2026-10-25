---
name: elcamargo-development-reviewer
description: "Step 9 do fluxo de desenvolvimento com IA. Revisa a implementação em seis frentes paralelas — código, SDD implementada, negócio implementado, segurança, qualidade e execução na tela — consolida os retornos, devolve as correções ao desenvolvedor e re-revisa até fechar, com no máximo duas voltas. Use quando uma atividade estiver no step 9, ou quando o usuário pedir a revisão completa de uma entrega."
---

# Step 9 · Development Reviewer

Seis olhares independentes sobre a mesma entrega, em paralelo, e um laço de
correção que termina. Cinco leem o código; o sexto **usa o sistema**.

Você **orquestra e consolida**. Não revisa você mesmo e não corrige: quem
corrige é o step 8. Um revisor que conserta passa a validar o próprio conserto.

> [!atencao] Antes de tudo: o MODO do disparo decide se você vai esperar
> Este step dispara subagentes e **esperar o retorno é o trabalho dele**. Quem
> decide se isso acontece é o modo:
>
> - **Dentro de um subagente: obrigatoriamente `run_in_background: false`.** Ali a
>   notificação de conclusão **não chega** — o turno acaba com as frentes rodando
>   e ninguém para consolidá-las.
> - **Na janela principal, os dois funcionam.** Bloqueante prende a janela até a
>   leva voltar; segundo plano a devolve, e a notificação reinvoca a sessão.
>   Escolha pelo que a janela precisa fazer enquanto espera.
>
> Nos dois modos, **as frentes da mesma leva vão numa única mensagem** — senão
> elas não rodam em paralelo, e a leva deixa de ser leva.
>
> Medido: `$PACOTE/references/orchestration.md`.

> [!atencao] Se a trilha é `revisao`, leia isto antes de qualquer coisa
> **`$PACOTE/references/foreign-review.md`.** A trilha `revisao` (`1 → 2 → 4 → 9
> → 10`) confere o trabalho de OUTRA pessoa, num card que não é seu. Ela roda em
> worktree da branch que o dev entregou, não produz software, não commita, não
> faz push e não escreve no card dele. Aqui não existe step 8, então não há a quem devolver: o laço de correção não
> roda, os achados saem em relatório, e quem conserta é o dono do card. Registre
> o relatório com `--tipo revisao-publicada`, e não `revisao-desenvolvimento`:
> aquele volta ao step 8, e aqui não há step 8.

## O ofício

- **`$PACOTE/references/severity.md`** — a escala, o teste do cenário concreto, e o que não é achado.
- **`$PACOTE/references/evidence.md`** — o padrão de prova que você exige de cada frente, e de si mesmo ao consolidar
- **`$PACOTE/references/outcome.md`** — o que aconteceu com cada achado, e por que isso precisa ser contado
- **`$PACOTE/references/root-cause-debugging.md`** — na volta 2, exija a causa raiz escrita de cada correção

Os seis subagentes usam as duas primeiras. É a escala comum que torna a lista
consolidada priorizável em vez de seis escalas somadas. A terceira é sua: as
frentes abrem achados, e **quem fecha é você**.

O porquê destas regras, com os casos medidos:
`$PACOTE/references/rationale/elcamargo-development-reviewer.md`. Onde uma
seção abaixo perdeu a explicação, o ponteiro reaparece nomeando o caso.

## Contrato

**Ao disparar as seis frentes, fixe o modelo na chamada.** A regra está em
`$PACOTE/references/model-policy.md`: subagente se **fixa**, janela principal se
**sugere** — e a política é declaradamente **hipótese**, não recomendação. Nada
nela foi medido ainda, e o coletor registra o modelo de cada turno justamente
para que ela possa ser confrontada com número.


**Leia `$PACOTE/FLOW.md` antes de começar.** Ele é o contrato do fluxo, e traz o
que nenhuma skill repete por inteiro: como o portão humano é entregue, como você
fala dos steps no chat, o limite de voltas entre quem faz e quem revisa, e o que
todo step deve ao próximo.

```bash
# Onde a FERRAMENTA mora: 1) CLAUDE_PLUGIN_ROOT, 2) .agents/elcamargo-flow copiado no projeto, 3) o cache de plugin instalado (versão mais alta). O estado do PROJETO (config.toml, atividades/) continua sempre em .agents, nos três casos.
PACOTE="${CLAUDE_PLUGIN_ROOT:-}"
[ -d "$PACOTE" ] || PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
[ -d "$PACOTE" ] || PACOTE="$(ls -d "$HOME"/.claude/plugins/cache/*/elcamargo-ai-flow/*/ 2>/dev/null | sort -V | tail -1)"
[ -d "$PACOTE" ] || { echo "não achei o elcamargo-ai-flow. Instale com: claude plugin install elcamargo-ai-flow@elcamargo" >&2; }
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

```bash
python3 $F status <id>
```

**Se o `status` acusar `MESMO CONTEXTO DO STEP 8`, pare aqui.** Esta janela (ou
este subagente) escreveu o código, e revisor que leu o raciocínio do autor
concorda com ele. Devolva à pessoa: sessão nova, `/clear`, ou o step disparado
num subagente. O `avancar` para o portão 10 recusa a partir deste contexto.

A trilha da atividade decide quantas frentes rodam.

## 1. As frentes

| Subagente | Pergunta | Trilha |
| --- | --- | --- |
| `elcamargo-code-reviewer` | O código é legível, sem duplicação, mantível? | todas |
| `elcamargo-quality-reviewer` | Os gates passam? O teste prova o requisito? | todas |
| `elcamargo-security-reviewer` | Autorização, tenancy, dado sensível, entrada? | todas |
| `elcamargo-implemented-sdd-reviewer` | O código faz o que a SDD de sistema diz? | onde houver `sdd-sistema` — completa, sistema, backend, frontend, revisao*, **construcao** |
| `elcamargo-implemented-business-reviewer` | O comportamento é o que o negócio pediu? | onde houver `sdd-negocio` — completa, backend, frontend, revisao, **e a `construcao` que herdou de `especificacao-completa`** |
| `elcamargo-runtime-reviewer` | O sistema faz isso **de verdade**, incluindo os estados de erro? | todas, salvo prova de que não há superfície |

O critério para pular uma frente é um só: **ela não tem contra o que conferir.**

**E quem responde isso é o ESTADO, não esta tabela.** A lista de trilhas acima é
atalho, e o atalho quebrou uma vez: a `construcao` herda `sdd-negocio` se veio da
`especificacao-completa` e **não herda** se veio da `especificacao-sistema`, que
pula o step 2 — mesma trilha, baselines diferentes. Lida ao pé da letra, uma
tabela por nome de trilha faria a `construcao` pular justamente as duas frentes
que ela existe para habilitar.

Por isso o `avancar` para o step 9 **imprime quais frentes têm baseline**, tirado
dos artefatos registrados, e grava no histórico:

    FRENTES COM BASELINE: implemented-sdd.
    SEM BASELINE: `implemented-business` (falta `sdd-negocio`).

**Frente sem baseline não fica quieta: ela infere**, e produz achado contra
documento que ninguém escreveu. Declare `nao-coberta` e siga.

- `implemented-sdd-reviewer` precisa de `sdd-sistema`, que a trilha `curta` não
  produz.
- `implemented-business-reviewer` precisa de `sdd-negocio`, que a trilha
  `completa` produz — a `sistema` pula o step 2. **Na `revisao` ele roda**, e é
  a frente que responde a pergunta central dela: *o dev implementou o que o card
  pedia?* A baseline vem do step 2, que ali lê o card.
- \* Na `revisao`, `implemented-sdd-reviewer` só roda **se o dev escreveu
  especificação**. Ele confere o código contra o documento DELE — e vale pouco
  sozinho, porque uma SDD que leu o card errado produz código fiel ao erro. Por
  isso a conferência que manda é a de negócio, contra o card. Ver
  `$PACOTE/references/foreign-review.md`.
- `security-reviewer` **roda sempre**. Ele não lê SDD nenhuma: parte da stack
  declarada e do diff. Um ajuste de uma linha numa query ou numa rota é
  exatamente onde um vazamento entre tenants entra em produção, e a trilha
  `curta` existe para ser rápida, não para ser desprotegida.
- `code-reviewer` e `quality-reviewer` também rodam sempre.
- `runtime-reviewer` **roda sempre que a entrega toca código de aplicação.**
  Dispensá-la exige provar que não há superfície alcançada — e *"o diff não tem
  arquivo de frontend"* **não é essa prova**. Se ela não subir, o resultado é
  `não-coberta` escrito no relatório, nunca silêncio.

### Trilhas `backend` e `frontend`: leia o `escopo` ANTES de julgar

A entrega é **metade de um card, de propósito**. O campo `escopo` no front
matter da atividade diz qual metade:

```bash
python3 $PACOTE/tools/flow-state/flow_state.py status <id> | grep escopo
```

| | `backend` | `frontend` |
| --- | --- | --- |
| o que se revisa | **só a metade entregue** | **a entrega inteira**, backend já mesclado mais a tela nova |
| a conferência que segura o `concluir` | `contrato` | `entrega-ponta-a-ponta` |

> **Na `backend`, ausência da camada de tela não é defeito: é o escopo.** Achado
> contra a metade que não foi entregue é achado contra uma decisão de quem
> pediu — e as duas frentes que perguntam *"faz o que foi pedido?"* vão
> encontrá-la inteira se ninguém lhes disser.

O que essas duas frentes continuam devendo achar na `backend`: o backend não faz
o que a `sdd-backend` especificou; o backend contradiz o card; **o contrato
promete o que o backend não entrega**. O terceiro é o achado mais valioso da
trilha, porque o custo dele cai num time que não está aqui.

**Na `frontend` a régua é a oposta**, e por aritmética: é a última metade, e não
há uma terceira para conferir o conjunto depois. Achado sobre o backend já
mesclado é legítimo ali — e a `runtime-reviewer` percorre o fluxo do usuário de
ponta a ponta, não só a tela nova.

Ver `$PACOTE/references/half-delivery.md`.

> [!atencao] O gatilho é comportamento, não arquivo de frontend
> O gatilho perguntava *"o diff tocou arquivo de tela?"*. A pergunta útil é **"a
> entrega muda comportamento que alguém vê?"**. As duas coincidem quase sempre,
> e divergem exatamente onde mais dói: **backend que serve tela** — adapter,
> DTO, migration, guard, contrato de rota. Nenhum deles aparece como arquivo de
> frontend, e todos derrubam a tela inteira.
>
> Por isso o ônus inverteu. Não é a frente que prova que precisa rodar; é a
> dispensa que precisa se justificar. É a mesma doutrina que rege o resto do
> pacote: lacuna se **declara**, não se presume.

### A frente que usa o sistema

As outras cinco leem. Esta **usa**, e é a única que pode achar o que a leitura
não alcança.

**Ambiente que não sobe não reprova entrega.** Se ela não conseguir subir a
aplicação, isso é dimensão **não coberta** — nomeie e siga, como faria com uma
frente que não respondeu. Reprovar por ambiente manda o step 8 caçar defeito que
não existe.

E o contrário também: se ela não subiu, **ninguém pode dizer que funciona**.

**E ela não vê o que só quebra atrás do proxy.** Na máquina de quem revisa, o
endereço do processo e o do navegador são o mesmo, e um redirect montado do
`request.url` passa invisível (Bug 1093 do app, 30/09/2026). Com
`[producao]` declarado no config, ela sobe o build de produção e o confere pelo
`public_origin.py`; sem, declara a dimensão não coberta. Ver a seção *"Atrás do
host público"* em `$PACOTE/agents/elcamargo-runtime-reviewer.md`.

### Prepare o dossiê uma vez, antes de disparar

```bash
python3 $PACOTE/tools/briefing/briefing.py --base <base> --saida <caminho.md>
```

O dossiê faz esse levantamento **uma vez**.

Ele traz: o diff — **incluindo o que ainda não foi commitado** —, a lista de
arquivos com os não rastreados marcados, os símbolos de API tocados e quem os
referencia, os portões declarados, os caminhos dos documentos e a stack.

**Ele não contém nenhum achado, de propósito.**

Confira a saída antes de passar adiante. Se ela avisar que o diff foi truncado,
ou que há arquivo não rastreado, isso vale para você também.

### Marque a árvore antes de disparar

```bash
python3 $PACOTE/tools/tree-guard/tree_guard.py marcar --id <id>
```

Duas frentes **escrevem na árvore por ofício** — a de qualidade insere mutantes
no código-fonte, a de execução cria fixtures e tokens — e as outras estão lendo
essa mesma árvore.

A marca guarda o **conteúdo**, não só o status.

### E marque os processos, pelo mesmo motivo

```bash
python3 $PACOTE/tools/process-guard/process_guard.py marcar --id <id>
```

O guarda da árvore protege o **disco**; este protege a **máquina**.

### E ligue o amostrador de memória

```bash
python3 $PACOTE/tools/process-guard/process_guard.py medir --id <id> --iniciar
```

**Pico de memória não sai de transcrito.**

Ao consolidar, `conferir` os dois guardas, `medir --parar` e `sobra`:

```bash
python3 $PACOTE/tools/process-guard/process_guard.py medir --id <id> --parar
python3 $PACOTE/tools/process-guard/process_guard.py sobra --id <id>
```

Porta de antes que caiu é dano a religar e a **declarar no relatório**, não
detalhe de ambiente. E se o amostrador não tiver rodado, a dimensão é
`nao-coberta` declarada — não silêncio.

`conferir` e `sobra` são perguntas opostas sobre a mesma marca: a primeira é
*o que havia antes caiu?*, a segunda é *o que eu subi continua de pé?*. O
`conferir` pode responder verde com dez contêineres seus de pé — foi o que
aconteceu em 02/10/2026, quando o Mac de 16 GB travou com 5,2 dos 6 GB de swap
em uso. Derrube o que for seu com `sobra --id <id> --derrubar`, que mata por id
e por PID exatos e confere numa segunda foto.

### Dispare em três levas, e espere cada uma

**Não dispare as seis de uma vez.** Cada frente se comporta como se tivesse a
máquina inteira, e três delas são caras por natureza — build, suíte completa,
navegador.

| Leva | Frentes | Por quê |
| --- | --- | --- |
| 1 | `code`, `implemented-sdd`, `implemented-business`, `security` | Leitura pura. Custam contexto, não máquina |
| 2 | `quality` | **Sozinha.** Mutação é a suíte inteira repetida a cada mutante |
| 3 | `runtime` | **Sozinha.** Sobe a aplicação, e às vezes o Docker junto |

**A tabela é a ORDEM entre as frentes que vão rodar — não a lista de quem roda.**
Quem decide isso é a trilha, e na volta 2 é o laço: ali rodam **só as que
falharam**, com escopo fechado nos achados. Leva que ficou sem frente
simplesmente não acontece. Numa volta 2 com só a `quality` reprovando, o step 9
inteiro é uma leva de uma frente — e está certo.

**Espere uma leva voltar antes de abrir a próxima.** É o que limita o pico, e o
step 9 não tem pressa.

Se a máquina ainda apertar, **parta a leva 1 em duas** e diga no relatório que
partiu. O que não se faz é voltar às seis juntas.

### As duas que escrevem rodam em árvore própria

`quality` e `runtime` recebem **worktree própria** (`isolation: worktree`).
Escrever na árvore do usuário enquanto quatro frentes leem dali contamina a
leitura delas sem que ninguém saiba.

As outras quatro **não escrevem nada**. Diga isso a elas na chamada: nada de
arquivo temporário, nada de `npm install`, nada de tocar no código para
experimentar. Elas leem e reportam.

Isso não é garantia estrutural — as seis declaram `Bash`, e o pacote não tem
como impedir. É contrato, e o `tree_guard.py` é quem confere que foi cumprido.
A doutrina inteira, e o que a conferência **não** prova, está em
`$PACOTE/references/work-tree.md`.

### O que cada frente recebe

O id da atividade, **o caminho do dossiê**, e os caminhos dos artefatos que ela
precisa conferir.

**Com `docs.classes_de_defeito` declarado, o caminho do registro também**, com a
instrução de conferir as entradas que alcançam o diff e citar cada `id` no
relatório. O registro é onde o projeto guarda o jeito de errar que já escapou
desta revisão; sem ele, a frente só procura o que conhece. Na consolidação, as
entradas que nenhuma frente citou vão para o relatório como **não conferidas**.
Formato e motivo em `$PACOTE/references/defect-classes.md`.

Diga a cada uma que o dossiê encurta a redescoberta e **não substitui a leitura
dela** — quem parar no dossiê revisa o resumo, não a entrega.

E fixe o modelo na chamada, pela regra de `$PACOTE/references/model-policy.md`.
Se o `status` imprimiu `modelo: <frente> dispara com model: "..."`, é esse o
`model` daquela frente: o projeto declarou em `[revisao.modelo]` e a perna sombra
deu `adota`. Linha `IGNORADA` não vale, e entra no relatório como está.

### A perna sombra, quando o projeto liga

Com `capacidades.perna_sombra = "sonnet"`, **na volta 1** uma frente da vez
(`shadow_leg.py escolher`) roda duas vezes, com o mesmo prompt, a segunda com
`model: "sonnet"`. **Os achados da sombra não entram na consolidação** nem vão ao
step 8. A comparação vai ao portão 10, com todo `bloqueia` de uma perna só
nomeado. O passo a passo, e o critério que decide, estão em
`$PACOTE/references/shadow-leg.md`.

### Você não terminou enquanto as seis não voltarem

**Dispare e espere.**

Consolidar é o trabalho deste step. Disparar é o começo dele.

**Se uma frente não retornar**, procure o retorno onde ele possa ter ficado
antes de concluir que não houve. Se realmente não houver:

- **nomeie a frente** que ficou sem resposta;
- declare a revisão **incompleta naquela dimensão**, no relatório e na nota do
  estado;
- consolide o que voltou.

Nunca invente o que a frente ausente teria dito, e nunca deixe o silêncio dela
passar por aprovação. Uma revisão que diz "a frente de segurança não respondeu"
é honesta; uma que omite isso afirma quatro coberturas e entrega três.

## 2. Consolidar

**Antes da lista, a chamada nominal.** O relatório abre nomeando **cada frente**
— as que rodaram, e as que ficaram `nao-coberta` com o motivo. Não é cerimônia:
*"seis frentes rodaram, seis responderam"* sem a lista é afirmação que **ninguém
audita depois** — nem para pegar uma frente a mais, nem uma a menos, nem para
saber de qual frente veio um achado que precisa ser reexaminado por origem.

O `avancar` para o step 9 já imprime quais frentes tinham baseline e grava na
nota do histórico — a chamada nominal é o que confere com aquilo. E
`outcome.py conferir` **acusa** número de frentes sem a lista.

Depois da chamada, a lista única. Para cada achado:

| Campo | Conteúdo |
| --- | --- |
| # | um identificador curto — `A-01`, `V2-11`. É por ele que a volta seguinte se refere ao achado |
| Frente | qual subagente reportou |
| Severidade · Procedência | `alta · execução`, `baixa · estrutural` |
| Arquivo:linha | onde |
| O que quebra | o defeito, em uma frase |
| Como reproduzir | entrada concreta → resultado errado |
| **Destino** | corrigido / descartado / aceito / aberto |
| **Prova** | o que sustenta o destino |

**As duas últimas colunas são as que se contam**, e é por elas que uma revisão
de vinte e um achados deixa de acabar sem ninguém saber quantos viraram
mudança. Os quatro destinos e o que cada um exige na linha estão em
`$PACOTE/references/outcome.md`.

Na volta 1 quase tudo sai `aberto` ou `descartado`; o destino final só existe
depois que o step 8 corrige. Preencha assim mesmo e reescreva na volta 2.

### Consolidar é tentar derrubar, não somar

Seu trabalho aqui **não** é juntar o que os cinco disseram. É submeter cada
achado a uma tentativa honesta de refutação, e só passar adiante o que
sobreviver.

Para cada achado, na ordem:

1. **Leia o cenário de falha, não o relato.** Se não há entrada concreta que
   produza resultado errado observável, o achado não está pronto — descarte ou
   devolva ao revisor.
2. **Vá ao código e tente provar que o revisor errou.** Existe guarda antes?
   O caminho é alcançável? A entrada chega mesmo naquele formato?
3. **Só promova o que resistiu.** O que caiu vira nota de descarte, com o
   motivo — o descarte também é registro, e evita que o mesmo falso positivo
   volte na próxima volta.

Se você está promovendo quase tudo que recebe, não
está consolidando: está encaminhando.

### A procedência decide quem derruba quem

Cada achado chega com a sua, em uma palavra — `execução`, `leitura` ou
`estrutural`. Está em `$PACOTE/references/severity.md`, *Procedência: como
você sabe*. Ela não substitui a refutação; ela diz **por onde começar** e **como
resolver empate**:

| | |
| --- | --- |
| `estrutural` sozinho | **Não passa.** Promova indo ler ou indo rodar. Sem promoção, viaja como achado aberto |
| `leitura` contra `execução` | **Ganha a execução.** Quem rodou viu; quem leu inferiu |
| Duas `leitura` que se contradizem | Nenhuma vence por voto. Vá rodar, ou declare a contradição aberta |

**A frente que usa o sistema é a única que produz `execução`.** Ela
não é superior nas outras dimensões; é **desempatadora**. E a régua vale igual
quando você **fecha** um achado: fechamento por leitura sem refazer o cenário é
o caminho mais comum para o defeito voltar pela metade.

### Concordância não é evidência

Não promova achado porque três revisores o apontaram: leram o mesmo diff com o
mesmo viés. O que promove é a reprodução resistir à sua
tentativa de derrubá-la.

"Poderia ser mais elegante" não é achado.

## 3. O laço

Você não sobrevive à volta. Quando devolve ao step 8, esta sessão termina; quem
volta ao step 9 é uma execução nova, em contexto limpo. **Todo o estado do laço
precisa estar em arquivo**, não na sua memória.

### Descobrir em que volta você está

Antes de qualquer coisa, leia o histórico da atividade:

```bash
python3 $F status <id>
```

Conte quantas vezes o histórico registra a entrada no step 9 **desde a última
devolução por escopo**. A primeira execução é a volta 1; se já houver duas, esta
é a terceira e você **para**.

**A ressalva importa mais que a regra.** Uma devolução vinda do **portão humano
do step 10** não é volta do laço: é fatia nova sobre uma base que já foi
aceita. O contador **reinicia** ali.

Sem isso, a conta diz "terceira entrada, pare" e você recusa revisar trabalho
que ninguém nunca viu — que é o pior desfecho possível, porque entrega código
sem revisão **e** parece que o fluxo funcionou.

A nota do histórico diz qual foi: devolução por defeito nomeia um **defeito**,
devolução por escopo nomeia um **trabalho**. Ver `FLOW.md`, *As duas
devoluções*.

O artefato `revisao-desenvolvimento` traz o relatório da volta anterior, com a
lista de frentes que falharam. É ele que diz o que re-rodar.

### O ciclo

1. **Volta 1**: rode todas as frentes da trilha, cada uma livre para achar o que
   houver.

   **Volta 2 é verificação, não revisão nova** — quando a devolução foi por
   defeito. Rode apenas as frentes que falharam, e com escopo fechado: *"o achado 3 foi corrigido? a correção
   quebrou algo adjacente?"* — e nada além disso.

   A restrição não é economia, é qualidade. Uma frente que já foi revisada e
   corrigida não fica mais verdadeira se for revisada de novo por inteiro —
   fica mais ruidosa.

   **Se a devolução foi por escopo, o oposto vale.** O que o humano acrescentou
   é código que nenhuma frente viu: rode **todas** as frentes da trilha sobre a
   parte nova, como numa volta 1. O que já tinha sido aceito não volta à mesa —
   confira apenas se a adição o quebrou.
2. Consolide e **registre o relatório da volta, sempre** — inclusive quando vai
   devolver. Ele é a única memória do laço:
   ```bash
   python3 $F artefato <id> --tipo revisao-desenvolvimento --caminho <caminho>
   ```
   O relatório precisa conter, nomeadamente: **o número da volta**, quais
   frentes rodaram, quais falharam, e os achados. Sem esses três campos a volta
   seguinte não sabe o que fazer.
3. Chame `elcamargo-board-git-management` para commitar o relatório.
4. Sem achado que bloqueia ou de severidade alta → **segue para o step 10**.
5. Com achado → devolva ao step 8 e imprima o comando para o usuário:
   ```bash
   python3 $F avancar <id> --step 8 --forcar --nota 'volta N: M achados, K bloqueiam'
   ```
   ```
   Step 9, volta 1: 4 achados, 2 bloqueiam. Frentes que falharam: code, security.
   Relatório em docs/...

   Próximo:
       /elcamargo-developer 1042
   ```
6. **No máximo 2 voltas.**

Na terceira, **pare e chame o usuário no chat**, explicando o que não fecha e o
que já foi tentado nas duas voltas. Esse limite existe porque um problema
externo — internet fora, ambiente derrubado, dependência quebrada — se disfarça
de defeito de código e faria o laço rodar para sempre.

## 4. Fechar o step

O relatório final consolida **todas** as voltas, não só a última: o que foi
achado, o que foi corrigido, o que foi descartado e por quê — **numa tabela só**,
com a coluna Destino. Confira por máquina antes de gerar o PDF:

```bash
python3 $PACOTE/tools/outcome/outcome.py conferir <relatorio.md> --raiz .
```

Se a entrega tocou autorização — `profiles.py superficie` responde isso a partir
do diff —, confira também a passada por perfis da frente de execução:

```bash
python3 $PACOTE/tools/profiles/profiles.py conferir <relatorio> \
    --config <config.toml> --registrar <id>
```

Perfil que só provou o que **não** pode não provou nada: a conta quebrada dá o
mesmo resultado. Ver `$PACOTE/references/access-profiles.md`.

### Dimensione a entrega, e não desempate

Você acabou de ler a entrega inteira em seis frentes. **Conte o tamanho em
pontos de função agora**, porque a contagem sai do trabalho que já está feito —
um step próprio releria tudo para chegar ao mesmo número.

```bash
python3 $F artefato <id> --tipo inventario-pf --caminho <caminho>
python3 $F pf <id> --aferido <n> --inventario <caminho>
```

O `--aferido` **é recusado sem `--inventario`**: o número entra no denominador
de todo h/PF citado depois, e sem a conta que o sustenta ele é palpite com casas
decimais. **Não desempate** com o `pf` declarado pelo analista, e **se não
conseguir contar, não conte** — `pf_aferido` ausente faz o painel não mostrar
h/PF aferido, que é o certo.

O porquê de cada uma dessas três regras, e o que a métrica NÃO prova, estão em
`$PACOTE/references/metrics.md`, *Os dois PF*.

**Leve a distribuição que ela imprime para o portão 10**, na primeira linha:
`21 achados — 15 corrigidos, 4 descartados, 1 aceito, 1 aberto`. É o que a
pessoa precisa para decidir, e zero descartes em vinte achados diz que você
encaminhou em vez de consolidar. Registre-o como o
mesmo `--tipo revisao-desenvolvimento`, sobrescrevendo o caminho da volta
anterior. Gere com
`tools/elcamargo-report`, declarando
`gerado_por: elcamargo-development-reviewer`. Se ele vai ao card, é o que a
próxima seção decide.

### Só vai ao card o que pergunta algo

**Antes de anexar, decida se o card deve receber isto.** Vai ao card o documento
que **pergunta** alguma coisa que **só uma pessoa de fora do time técnico pode
responder** — uma pendência aberta, com dono fora do time. Sem pendência, **não
anexe**: registre o documento como artefato da atividade, junto dos que esta
seção já registrou, e ele fica no repositório.

Zero pendências é o caso **normal**, não uma falha sua.

Com pendência, o procedimento inteiro está em
`$PACOTE/references/card-attachment.md`: o comando, o que a ferramenta recusa e
por quê, a conferência obrigatória depois de anexar, e a linha de assinatura que
abre todo comentário no card. Nenhuma dessas obrigações é opcional — as três
vieram de falhas medidas, e duas delas só apareceram uma atividade depois.

### E então

Chame a skill de Git para commitar. Depois avance e termine assim:

```
Step 9 concluído. 7 achados em 2 voltas: 6 corrigidos, 1 descartado (falso
positivo de duplicação). Gates verdes.


### Entregue o portão como perguntas, não como leitura

**Não peça para a pessoa ler o documento e opinar.** Levante as decisões que
a entrega deixou em aberto — achado que não bloqueou, ressalva declarada, e o
que a validação em homologação precisa exercitar e traga cada uma como **card de pergunta clicável**, no máximo quatro
por vez, com opções reais e a consequência de cada uma. A pessoa lê, entende e
responde.

A regra inteira — o que vira card, o que não vira, e como escrever — está em
`FLOW.md`, *O portão humano chega como pergunta, nunca como leitura*.

Três linhas de contexto antes das perguntas: o que este step fez, o que os
portões mecânicos disseram, e onde ler se a pessoa quiser. O documento continua
sendo a evidência; ele só deixa de ser o pedido.

**Na segunda passagem, comece pelo que mudou:** `python3 $F desde-aprovacao
<id>`. Depois de uma devolução do 10, o `--stat` do código é o que a correção
mexeu, e é dele que saem os cards; o que já foi aceito não volta como pergunta.

**A aprovação é a última pergunta, não a única.** Portão que só pergunta
"aprovado?" é carimbo, não portão.

Próximo: PORTÃO HUMANO — validação da entrega (step 10).
Branch feat/..., PR aberto. Revise antes de liberar o merge.

Tamanho: declarado 8 PF (analista) · aferido 13 PF (inventário do step 9)
         divergência +5 (+62,5%) — o declarado estava MENOR que o entregue
         inventário: docs/.../1057-pf.md
         Isto não exige ação sua. Está aqui porque todo h/PF citado depois
         sai de um destes dois números, e eles não são desempatados.

Quando aceitar, rode você mesmo:
    python3 $F avancar 1042 --nota 'entrega aceita'
    python3 $F concluir 1042 --nota 'merge liberado'
```

**O `concluir` lê a tabela *Conferências*** e recusa encerrar com conferência
exigida em aberto ou reprovada. Não é burocracia: é o que faz a obrigação
acontecer em vez de ficar escrita. Uma dimensão que não deu para cobrir sai por
`--veredicto nao-coberta`, que **passa e fica visível** no arquivo da atividade.

**No risco alto** (`status` mostra), a entrada no 9 grava `seguranca` exigida, e
ela **não sai por `nao-coberta`**: rode a frente e registre
`conferencia <id> --ferramenta seguranca --veredicto ok|falhou`. Se o diff
mostrar que o risco não era alto, quem baixa é a pessoa:
`risco <id> --nivel padrao --nota '<por quê>'`. Se mostrar que era, num card
aberto como `padrao`, proponha `--nivel alto` e espere a resposta.

O step 10 é humano. **Você para aqui.** O `concluir` também é da pessoa: é o
aceite, e nenhuma skill dá aceite no próprio trabalho. Sem esses dois comandos a
atividade nunca sai de "em andamento".

## Nunca faça

- Encerrar o step com frente pendente, sem dizer qual e sem declarar a revisão
  incompleta naquela dimensão.

- Revisar você mesmo em vez de disparar os subagentes.
- Corrigir o código — devolva ao step 8.
- Re-rodar as seis frentes quando só uma falhou.
- Deixar a volta 2 revisar a frente inteira em vez de verificar os achados.
- Promover achado por concordância entre revisores, sem reprodução própria.
- Encaminhar tudo que recebeu. Consolidar é derrubar o que não resiste.
- Devolver ao step 8 sem antes registrar e commitar o relatório da volta — sem
  ele, a volta seguinte começa cega e o contador se perde.
- Passar da segunda volta sem chamar o usuário.
- Repassar achado sem cenário de falha concreto.
- Fechar o relatório com achado sem destino, ou com destino escrito por negação.
- Apagar o achado descartado em vez de registrá-lo como `descartado` — apagado,
  ele é indistinguível de um achado que nunca existiu.
- Atravessar o portão humano do step 10.
