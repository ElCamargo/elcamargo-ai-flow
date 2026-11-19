# Fluxo · Os subagentes

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## Os subagentes

Dez componentes nunca são invocados diretamente — só rodam como subagente,
chamados pelo step que os contém ou pela janela que dispara um step. Por isso
são agent definitions em `.claude/agents/`, e não skills: agent não entra no
contexto principal.

| Chamado por | Subagentes |
| --- | --- |
| A janela que dispara um step | `step-runner` — um step por disparo, retomado por `SendMessage` quando volta com pergunta |
| Step 2 · `business-analysis-reviewer` | `business-analysis-auditor` |
| Step 3 · `system-analyst` | `system-analysis-auditor` |
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
| A mesma janela atravessando atividades | 12 atividades numa janela, 819 mil, 14% do custo de um repositório em dois dias; outra com 11.378 respostas e 9 atividades | `/compact` na troca de atividade, que a âncora oferece; ou atividade nova, janela nova |

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

**Ela é da máquina, e reinstalar o pacote não a leva.** O `install.sh` confere e
avisa em toda instalação; `install.sh --compactar` grava `autoCompactWindow:
200000` no `~/.claude/settings.json`, com backup ao lado. Quem usa o pacote como
plugin, sem `install.sh`, roda `python3 tools/doctor/compactacao.py ligar`. Só
roda quando a pessoa pede: mexer na configuração global de alguém não é papel de
instalador.

**Remedido de 02 a 15/11/2026, já com a compactação em 200 mil:** 36.703
respostas, todos os repositórios desta máquina. Nenhuma janela principal passou
de 177 mil.

| Quem | Parte do custo | Contexto médio |
| --- | --- | --- |
| `step-runner` | 46% | 103 mil |
| Janela principal | 19% | 141 mil |
| Frentes do step 9 (quality, runtime, security, code, sdd, negócio) | 27% | 68 a 99 mil |
| O resto (`general-purpose`, Explore, screen-drawer…) | 8% | |

Escrita de cache foi 33% do custo: todo contexto que nasce paga o seu começo.
**Por isso a janela centralizadora fica, e o que se corta é o que ela carrega de
atividades que já saíram dela.** A âncora mede, pelo transcrito, quanto a janela
relê a cada resposta. Quando a mensagem troca de atividade com 100 mil ou mais,
ela pede ao modelo que ofereça `/compact` à pessoa, em uma linha. Avisa uma vez
por enchente: só volta a avisar depois que o contexto cair abaixo do limiar. Ela
não compacta sozinha, porque nenhum hook consegue: quem roda `/compact` é a
pessoa. O estado de cada atividade está no arquivo dela, e o modo orquestrador
devolve as regras depois da compactação. Código em `tools/anchor/anchor.py`,
`aviso_de_troca`.

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
| step 3 · system-analyst | o `system-analysis-auditor`, que até a 2.68.0 era o step 4 |
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
3. Se não houver `bloqueia` nem `alta`, segue para o step 10. `baixa` viaja na
   lista do portão 10 e não volta ao step 8.
4. Se houver, **a correção volta para o `developer`** — quem revisa não corrige,
   senão o revisor passa a validar o próprio conserto. Cada `bloqueia` e `alta`
   vai com a classe: o mecanismo e todos os pontos onde ele aparece, achados por
   varredura. O `developer` corrige a classe, não a linha.
5. Re-roda **somente as frentes que falharam**, não as seis, e só sobre o que
   mudou: cada uma refaz a varredura da classe que corrigiu e lê as linhas da
   correção. Não relê a entrega.
6. No máximo **2 voltas**. Na terceira, para e chama o humano no chat,
   explicando o que não fecha. Isso existe para um problema externo — internet,
   ambiente fora — não virar laço infinito.

**O achado é a classe, não a linha** (2.70.0). Na 1101, uma classe de defeito
reportada pela linha custou duas devoluções do portão 10; com a varredura, as
três ocorrências teriam saído numa volta. Na mesma calibração, fundir as frentes
de código, SDD e negócio num revisor só foi testado e reprovado: ele não chegou a
nenhum dos seis achados altos de leitura. As frentes continuam separadas. Ver
`$PACOTE/references/class-sweep.md`.
