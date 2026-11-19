# Política de modelo: o que se fixa, o que se sugere, e o que ainda não se sabe

Nem todo step do fluxo pede o mesmo modelo. Um step que decide arquitetura e um
que roda gate e lê log são cargas diferentes, e pagar o mesmo preço por token
nos dois é escolha, não destino.

**Quase tudo aqui é hipótese, não recomendação.** A exceção é *Vigente*, logo
abaixo, e ela também não foi medida: foi adotada pela regra de corte que a seção
declara, e que existe para que só desça o que tem quem veja o erro. Desde a
2.14.0 o coletor registra o modelo de cada turno e cobra pela tabela dele, então
o resto pode ser confrontado com número em vez de defendido com argumento.

Quem escrever aqui uma recomendação antes de medir estará fazendo exatamente o
que o resto deste pacote recusa.

## Vigente (2.71.0)

**Sonnet onde o erro tem quem o veja depois. Opus onde ele escaparia calado.**
Quem vê pode ser uma pessoa, num portão ou numa pergunta, ou um auditor em Opus
de contexto limpo que confere aquela entrega. Quem decide arquitetura, escreve
código ou entrega achado fica em Opus: um `bloqueia` que o modelo mais barato
perdeu não aparece para ninguém.

| Onde | Modelo | Quem vê o erro, se houver | Onde está escrito |
| --- | --- | --- | --- |
| Janela mestra (porta, orquestração) | **Sonnet, sugerido** | todo step pesado fixa o seu modelo no disparo | fecho da porta, e o modo `orquestrar` |
| Step 1 · Gestor da Atividade | Sonnet | a pessoa, que responde a trilha | `STEPS` → linha `disparo:` |
| Step 2 · Revisor de Negócio | Sonnet | o `business-analysis-auditor` em Opus, o step 3 em Opus, a pessoa no portão 5 | `STEPS` → linha `disparo:` |
| Step 3 · Analista de Sistema | **Opus** | — decide arquitetura | `STEPS` → linha `disparo:` |
| Step 4 (só na `revisao`) | **Opus** | — entrega achado | `STEPS` → linha `disparo:` |
| Step 6 · Designer de Telas, `screen-drawer`, `figma-reader` | Sonnet | a pessoa, no portão 7 | `STEPS`, e `model:` no cabeçalho dos dois agentes |
| Step 8 · Desenvolvedor | **Opus** | — escreve o código | `STEPS` → linha `disparo:` |
| Step 9 · Revisor da Entrega | **Opus** | — consolida e decide severidade | `STEPS` → linha `disparo:` |
| Os dois auditores e as seis frentes do step 9 | **Opus** | — entregam achado | `model: opus` no cabeçalho de cada agente |

**Por que o step 9 inteiro fica em Opus, e não só as frentes.** Desde a 2.70.0
quem consolida decide a severidade (`baixa → alta` e o contrário), e um rebaixo
errado manda um defeito sério para a lista do portão 10 em vez da volta ao
step 8. Na fase B, que roda sem a pessoa, isso é quase calado.

**Por que as frentes não desceram, se a meta da 3.0 é Sonnet no resto.** A
calibração da 2.70.0 (em `class-sweep.md`) mediu a variância das frentes de
leitura: as três frentes, no mesmo modelo, rodadas de novo na 1102, chegaram
perto de dois dos quatro altos da primeira rodada, e só como `baixa`; os outros
dois sumiram. Com o recall já
oscilando assim em Opus, trocar o modelo junto tornaria impossível dizer o que
perdeu o achado. Elas descem uma a uma por `[revisao.modelo]`, com a perna
sombra dando `adota`, como manda a seção abaixo.

**O que move.** Medido de 25 a 30/09/2026: a janela principal sai por ~28% do
custo com 9% dos turnos, e é a maior parte que agora desce, por sugestão. O
step 2 e o step 6 juntos são uma fatia pequena. O step 8 (~30%), o step 3
(~24%) e o step 9 continuam onde estavam. A queda grande da 3.0 vem de carregar
menos contexto (núcleo de 9 KB, step 4 dentro do 3, a volta de verificação que
não relê a entrega), não do tier.

**O cabeçalho do agente não trava a perna sombra nem o `[revisao.modelo]`.** O
`model` passado na chamada tem precedência sobre o `model:` do cabeçalho. O
cabeçalho só garante que, sem pedido explícito, a frente não herda o Sonnet de
uma janela mestra em Sonnet.

**Para voltar atrás**: o `"modelo"` do step em `STEPS`, ou o `model:` do
cabeçalho do agente. O `test_package` trava os dois, de propósito: mudar um é
decisão desta página, não ajuste.

### Antes (2.52.0 a 2.70.0)

Só o step 1, o `screen-drawer` e o `figma-reader` desciam para Sonnet. O resto
herdava de quem disparava. Funcionava enquanto a janela principal era Opus; com
a janela mestra em Sonnet, herdar passaria a ser descer sem medir.

### As frentes do step 9 descem por `[revisao.modelo]`, e só com o número

A chave existe desde a 2.61.0 e nasce vazia. Uma linha dela (`code-reviewer =
"sonnet"`) só vale quando o `shadow_leg.py resumo` do projeto dá `adota` para
aquela frente com aquele modelo; antes disso o `status` do step 9 a imprime como
`IGNORADA`, com o motivo. É a regra desta página virada mecanismo: o segundo
modelo entra primeiro como **cobertura** (a perna sombra, cujos achados não
consolidam), e só ganha autoridade com o recall medido contra a perna principal.

## O que se fixa e o que se sugere

A divisão não é preferência — é o que dá para controlar.

| | Quem decide | O que fazer |
| --- | --- | --- |
| **Subagente** | quem dispara | **Fixe** o modelo na chamada |
| **Janela principal** | a pessoa | **Sugira** no fecho do step, e siga |

Medido na atividade de referência: **91% dos turnos são de subagente** e 9% da
janela principal. Em custo a proporção muda — o orquestrador carrega o contexto
inteiro a cada turno, e sai por ~28% do gasto com 9% dos turnos.

Ou seja: **o que se fixa cobre quase todo o volume; o que se sugere cobre um
quarto do dinheiro.** As duas metades importam, por razões diferentes.

## Como sugerir, sem virar ruído

O fecho de um step já anuncia o próximo. A sugestão de modelo entra ali, **uma
linha**, com a razão:

> Próximo: **step 3 · Analista de Sistema**.
> Modelo sugerido: **o mais capaz que você tiver**. É o step que mais consome
> (23,9% do custo medido) e o que decide arquitetura — a carga que mais responde
> a capacidade.

E quando a sugestão for para **baixar** o tier, ela diz o que se arrisca:

> Modelo sugerido: **Sonnet**. Esta frente lê saída de gate e log, e não decide
> arquitetura. Se ela começar a devolver achado sem evidência, suba de volta.

**Nunca troque o modelo da janela em nome de ninguém.** Sugerir é uma linha;
trocar é decisão de quem paga a conta e vive com o resultado.

## A ordem das alavancas, e o modelo não é a primeira

A orientação pública da Anthropic é explícita, e a medição deste pacote
concorda: **meça o modelo mais capaz em `effort` menor antes de montar cascata
de modelo.** Em modelo novo, effort baixo frequentemente iguala ou supera a
geração anterior em effort alto.

E antes das duas: **cache**. Na atividade de referência o custo se reparte em

| | |
| --- | --- |
| cache lido | **65%** |
| cache escrito | 28% |
| saída | 7% |
| entrada nova | 0% |

Quem for reduzir custo começa por **quanto contexto é relido a cada turno**, e
não por qual tier o relê. Trocar de modelo mexe no preço unitário do cache
junto — mas mexe num número que já é 93% cache.

## Uma vantagem de arquitetura que este fluxo tem, e vale saber

A objeção clássica à cascata de modelo é que ela **fragmenta o cache**: caches
são por modelo, e trocar de modelo no meio joga fora o prefixo quente.

**Aqui isso quase não se aplica**, porque o handoff entre steps é por arquivo e
nunca por contexto de conversa: cada step já roda em contexto novo, com cache
próprio. Trocar de modelo *entre* steps não descarta cache nenhum, porque não
havia cache compartilhado para descartar.

Trocar **dentro** de um step, sim, custaria — e é por isso que a política é por
step e por frente, nunca por turno.

## O que ainda não se sabe, e como saber

Nada foi medido. **Desde a 2.55.0 a comparação está ligada no step 9**, com
`capacidades.perna_sombra`: ferramenta, passo a passo e critério em
`shadow-leg.md`, que também carrega o desfecho de uma tentativa que
**falhou por defeito de desenho** — vale ler antes de repetir.

O desenho vigente é o **disparo duplo de subagente**: **um** subagente por
atividade roda **duas vezes, em dois modelos**, na mesma chamada e no mesmo
instante — em rodízio, hoje o auditor, na próxima o `code-reviewer`. Uma
variável, custo de ruído, e o `n` cresce a cada disparo em vez de a cada
atividade.

Só entram os sete subagentes que entregam **tabela de achados**, onde "melhor"
é medida. `screen-drawer` e `figma-reader` entregam protótipo e leitura de
tela: ali "melhor" é julgamento, e eles ficam de fora em vez de entrarem com um
critério inventado para eles.

Três regras que esse desenho carrega, e cada uma vem de um erro cometido:

**Os dois lados rodam o MESMO procedimento.** Mesma skill, mesmos subagentes,
mesmas voltas. Comparar procedimento curto em modelo barato com procedimento
completo em modelo caro mede a economia, não o modelo.

**A janela precisa estar no repositório da atividade.** O transcrito de um
subagente vive sob a pasta da sessão mãe, e a pasta da mãe vem do CWD dela. Uma
orquestração rodada de fora deixa o trabalho invisível para o coletor daquele
repositório — zero com cara de resultado.

**O paralelo para no primeiro portão humano.** Depois dele as pernas deixam de
ser independentes, porque **a pessoa não consegue des-saber**: uma decisão
tomada com a informação de uma perna contamina a outra. No portão as pernas
convergem, a comparação é entregue junto, e a decisão é tomada uma vez.
