# Política de modelo: o que se fixa, o que se sugere, e o que ainda não se sabe

Nem todo step do fluxo pede o mesmo modelo. Um step que decide arquitetura e um
que roda gate e lê log são cargas diferentes, e pagar o mesmo preço por token
nos dois é escolha, não destino.

**Quase tudo aqui é hipótese, não recomendação.** A exceção é *Vigente*, logo
abaixo, e ela também não foi medida: foi adotada pela regra de corte que a seção
declara, e que existe para que só desça o que não tem como falhar calado. Desde a
2.14.0 o coletor registra o modelo de cada turno e cobra pela tabela dele, então
o resto pode ser confrontado com número em vez de defendido com argumento.

Quem escrever aqui uma recomendação antes de medir estará fazendo exatamente o
que o resto deste pacote recusa.

## Vigente (2.52.0)

**Desce para Sonnet só o que uma pessoa lê antes de alguém construir em cima.**
Ali, se o modelo errar, o erro chega à pessoa como pergunta ou como tela, e ela
vê. Quem entrega achado, especificação ou código fica no modelo de quem dispara:
um `bloqueia` que o modelo mais barato perdeu não aparece para ninguém, e o
critério do experimento reprova por um só.

| Onde | Modelo | Por quê | Onde está escrito |
| --- | --- | --- | --- |
| Step 1 · Gestor da Atividade | Sonnet | lê o card, confere se já existe, e devolve a trilha como pergunta | `"modelo"` do step em `STEPS`, no `flow_state`; aparece na linha `disparo:` |
| `screen-drawer`, `figma-reader` (step 6) | Sonnet | o que entregam vai ao portão 7 | `model:` no cabeçalho do agente, e a skill do step 6 |
| Todo o resto | herda de quem dispara | entrega achado, especificação ou código | — |

**Quanto isso move é pouco, e de propósito.** Medido de 25 a 30/09/2026: ~1% do
custo nas duas frentes do step 6. O step 1 não sai separado do serviço de commit
que as outras skills chamam, e os dois juntos ficaram em ~8%. A parte grande,
o step 8 (~30%) e as frentes `runtime`, `quality` e `code` do step 9 (~13,5%), só
desce com a comparação de *O que ainda não se sabe*.

**Para voltar atrás**, se o step 1 ler um card errado ou a tela sair fora da
identidade: tire o `"modelo"` do step 1 em `STEPS`, ou o `model:` do cabeçalho.

**As frentes do step 9 descem por `[revisao.modelo]`, e só com o número.** A
chave existe desde a 2.61.0 e nasce vazia. Uma linha dela (`code-reviewer =
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
