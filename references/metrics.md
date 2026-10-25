# Métrica do fluxo: o que ela mede, e o que ela não prova

Uma atividade conduzida pelo fluxo deixa rastro em três lugares que ninguém
junta à mão:

| Rastro | Onde | O que sai dele |
| --- | --- | --- |
| o arquivo da atividade | `<.agents>/atividades/<id>.md` | steps, conferências, artefatos, o PF declarado |
| os transcritos de sessão | `~/.claude/projects/<slug>/`, um arquivo por subagente | tokens, turnos, relógio, interações humanas |
| o Git | a branch da atividade contra a base | o tamanho da entrega |

`metrics.py` junta os três e grava o resultado, para que "quanto custou, e
onde" tenha resposta sem arqueologia. Cinco níveis, e cada um soma exatamente
o de baixo:

```
projeto  ->  atividade  ->  step  ->  agente  ->  conferência
```

## O que ela NÃO prova

Esta seção vem antes das outras de propósito. Um painel de métrica é lido como
verdade, e o que ele não sabe tem que chegar junto do que ele sabe.

**O custo é de tabela de API.** Quem roda por assinatura não paga isso: é
**teto**, não fatura. O relatório imprime essa ressalva em todo nível, sempre,
e o painel também. Preço divergente do padrão do pacote não é erro — quem roda
outro modelo tem preço legitimamente outro, e a ferramenta não sabe qual modelo
você roda.

**A hora humana é um modelo, não um cronômetro.** Ela mede o intervalo entre o
fim de uma resposta e a mensagem seguinte da pessoa, com **teto**, mais um
custo de **reentrada** por interação. O teto existe porque latência crua não
distingue "lendo por oito minutos" de "almoçando e respondendo em trinta
segundos". Os dois parâmetros ficam em `[metricas]` e o relatório imprime quais
usou — porque um número cujo parâmetro não aparece não é conferível.

**Ponto de função não é medido: é declarado.** Nem transcrito nem diff contêm
PF. A ferramenta guarda dois números declarados e a divergência entre eles, e
não desempata. Ver *Os dois PF* abaixo.

**Ela não sabe de quem foi o turno.** A atribuição é por prova e por
proximidade, não por certeza. Quando falta prova, ela diz que falta — ver *O
zero silencioso*.

## Os quatro erros de atribuição que moldaram a janela

Nenhum destes é hipótese. Todos foram medidos contra atividades reais, e cada
um está preso por caso no `tools/metrics/test_smoke.py`.

**1. Filtrar por `gitBranch` cortou 23 das 41 interações humanas.** `gitBranch`
é do repositório **principal**, não da worktree. Numa atividade que rodou 27 h
em worktree, a branch dela só apareceu na última tarde, quando o repositório
principal por acaso a checou.

**2. `atualizado_em` como teto fez uma atividade parada engolir 8 mil turnos.**
Qualquer escrita no arquivo move esse campo para agora — inclusive um `avancar`
acidental. A atividade passou a reivindicar tudo que aconteceu desde que
nasceu, e triplicou de custo no painel. **Só `concluido_em` é teto**, porque só
ele significa "acabou".

**3. Raio simétrico em torno de cada prova inflou TODA atividade.** Com 4 h para
os dois lados, uma ilha de prova puxava oito horas de trabalho vizinho que era
de outro assunto: uma atividade foi de 2.321 para 10.357 turnos. O que é
legítimo é o **meio** — entre duas provas próximas estão os turnos do
orquestrador, que roda da raiz e por isso não deixa prova própria: 928 deles
numa atividade medida, mais de um terço. Fora das pontas, só uma margem curta.

**4. Prazo somando a cauda deu 40 h onde a entrega saiu em 26.** O conserto do
que escapou entrou horas depois do merge, na mesma worktree — é custo da
atividade, e é outra coisa. **Prazo** é do primeiro registro até a entrega;
**cauda** é o que veio depois. Quem lê um painel de prazo quer a primeira.

E um quinto, que é de soma e não de janela: **duas atividades na mesma branch
com janelas que se cruzam contam o mesmo trabalho duas vezes.** Medido no
primeiro uso — duas atividades devolveram números idênticos, ao centavo. Não dá
para desempatar: o transcrito não diz de qual das duas é cada turno. Então não
se inventa critério — **acusa, nomeia o par, e deixa a soma visível**.

E um sexto, que não é de número e sim de **rótulo**: **prazo de atividade aberta
era anunciado como "até a entrega".** Medido em 03/09, em três frentes rodando
em paralelo — todas `em_andamento` no step 3, nenhuma entregue. As três telas
imprimiam *"prazo, do primeiro registro à ENTREGA"* e, logo abaixo, *"cauda,
trabalho depois da entrega — 0.0 h"*. Sem `concluido_em`, o prazo vai até o
último registro do transcrito e **ainda cresce**; e a cauda era zero **por
definição**, não por medição. Quem lesse via um prazo fechado e um "não houve
retrabalho", e os dois eram falsos.

O registro passa a gravar `prazo_aberto`. Aberto, o rótulo diz **"até agora"**,
a linha de cauda **sai da tela** — `0.0 h` sob "trabalho depois da entrega" se
lê como medição — e um aviso diz que o número vai crescer. Na lista do projeto a
atividade aberta leva um `+` no prazo, para que um prazo que ainda cresce não
alinhe na mesma coluna de um que acabou. No `conjunto`, o ganho de paralelismo
ganha a ressalva de que é **retrato, não resultado**, enquanto houver frente
aberta.

E um sétimo, que é de **custo** e não de janela: **o número que a apresentação
mostrava era o teto que ninguém paga.** `custo_usd` é tabela de API — quem roda
por assinatura não desembolsa aquilo, e apresentar só ele exagera o custo da
ferramenta na mesma medida em que subestimar hora humana exagera o ganho. Os
dois erros são o mesmo erro, em direções opostas.

`[metricas] assinaturas_usd_mes` é uma **lista de mensalidades**, uma por conta,
e não "preço × número de contas": medido no primeiro caso real, as duas contas
em uso eram de planos diferentes — uma Max 20× e um assento Team —, e um
multiplicador teria cobrado o preço da primeira duas vezes. Sem a chave não há
custo de assinatura em lugar nenhum, pela mesma razão que não há h/PF sem `pf`.

O rateio é pelo **prazo**, sobre 730 h de mês: a assinatura é cobrada por tempo
corrido, não por token consumido. E no `conjunto` ele usa a **parede**, nunca a
soma dos prazos — o tempo corrido não dobra porque se abriu duas janelas, e
somar cobraria a mesma assinatura duas vezes no mesmo mês. É a mesma correção
que a união faz na hora humana, aplicada ao dinheiro.

Ao lado dela entra a **estimativa APF**, `pf × 6` e `pf × 10` horas — a régua de
mercado contra a qual o medido é comparado. Ela também só existe onde há `pf`
declarado: sem ele seria multiplicação de nada.

E um oitavo, que não é defeito e sim **ausência**: o coletor media o que a
entrega **custou** e não media o que a revisão **apanhou**. Contra quem acredita
que pensar menos entrega mais rápido, custo e prazo não respondem — porque o
custo de um erro de análise não aparece na tarefa em que ele foi cometido.
Aparece semanas depois, num card de bug que ninguém liga à especificação que o
causou.

Os achados saem dos relatórios que a atividade registrou como **artefato**, pelo
classificador do `outcome.py` — não por um segundo leitor. Duas leituras da
mesma tabela divergindo seria pior que não ter a métrica. Saem contados por
**severidade**, por **destino**, e com a **segunda volta à parte**.

**A ARMADILHA, e ela é a mesma de sempre.** A versão que a gerência quer ouvir é
`13 defeitos × 8 h = 104 h economizadas`. Esse número **não existe**: ninguém
mediu aquelas 8 h, e parte dos treze seria apanhada por uma pessoa de qualquer
forma. Publicar um multiplicador inventado ao lado de números medidos contamina
os dois — é o mesmo erro que este coletor já recusa em PF, em preço de
assinatura e em atividade que divide branch.

Por isso a ressalva é **impressa antes do número, e não no rodapé**. E a segunda
volta é contada como *"achados da segunda volta"*, nunca como *"introduzidos ao
corrigir"*: a volta 2 traz defeito novo E defeito induzido pela correção, e só
quem escreveu o relatório sabe separar os dois.

Sem artefato de relatório a dimensão fica **ausente**, e não zerada: `0 achados`
se leria como *"revisamos e não achamos nada"*, que é o contrário de *"não há
relatório para ler"*.

E um **nono**, que é o mais caro de todos porque foi publicado: **o coletor
cobrava por um modelo aposentado.** A tabela de preço era `entrada 15,00 ·
cache_escrita 18,75 · cache_leitura 1,50 · saída 75,00` — o preço do **Opus 4.1
e do Opus 4**, retirados. Os transcritos mostram `claude-opus-5`, que custa
**5 e 25**, com cache lido a **0,50** e não 1,50.

Na atividade medida isso é **US$ 3.775,71 publicado contra US$ 1.405,06 reais —
2,69× inflado**, e o número foi para uma apresentação de gestão.

**E havia um teste fixando o valor errado.** Ele afirmava que `1M de entrada +
1M de saída = US$ 90,00` e passava, porque provava que a conta batia com a
tabela — não que a tabela estava certa. Número fixado num teste não vira verdade
por estar fixado.

O preço passa a ser **por modelo**, com a tabela consultada na fonte e a data
registrada. Cada turno é cobrado pela tabela **do modelo que ele de fato
rodou** — somar tudo num balde só cobraria Opus por turno de Haiku, e o erro
cresce justamente quando uma cascata de modelo funciona. Modelo fora da tabela
não vira zero (esconderia gasto) nem vira o mais caro (inventaria gasto): cai
num padrão **declarado**.

**Cache de escrita depende do TTL**, e o transcrito não diz qual foi usado: 5
minutos custa 1,25× a entrada, 1 hora custa 2×. O padrão é o de 1 hora, que é o
do Claude Code, e ele é **impresso** em vez de escolhido em silêncio.

Onde o dinheiro está, na atividade medida: **65% cache lido, 28% cache escrito,
7% saída, 0% entrada nova.** Quem for otimizar custo começa por aí, e não pelo
modelo.

Essa última frase é o padrão da ferramenta inteira, e vale para o resto deste
documento.

## O zero silencioso

Uma atividade sem `branch` e sem `worktree` no cabeçalho não tem como ser
ligada a nenhuma sessão. Medido: o registro saía com **0 turnos e US$ 0,00**
com US$ 36,00 de trabalho da mesma pessoa no disco, no mesmo dia. O painel
mostrava como se nada tivesse acontecido — a família de defeito mais cara
deste pacote: *a ferramenta entrega algo que parece completo e não é.*

Hoje ela **diz que não conseguiu atribuir**, nomeia a causa, e o total do
projeto a **exclui** declarando quantas ficaram de fora. Duas causas, porque o
conserto de cada uma é diferente:

| Causa | Conserto |
| --- | --- |
| sem `branch` nem `worktree` no cabeçalho | declare, e colete de novo |
| declarados, mas nenhuma sessão os tocou | não tem conserto: nada rodou, ou os transcritos foram apagados |

**O detector não pode ser "janela vazia".** Com `concluido_em`, a janela sai
preenchida — `09:05 → 09:05`, medido — porque o `concluir` entra como prova
sintética. O detector ingênuo daria justamente a atividade **concluída** por
boa. Só prova de **sessão** atribui.

E a linha da atividade não atribuída **não traz número nenhum**, de propósito:
`0.00` alinhado numa coluna de custo se lê como medição, e a diferença entre
"custou zero" e "não sei de quem foi" é a única coisa que essa linha existe
para dizer.

O que **não** depende de atribuição continua somando por todas: conferências e
artefatos saem do arquivo da atividade, e a entrega sai do Git. Excluir isso
também jogaria fora dado correto por causa de um cabeçalho incompleto.

## O percurso: voltas, portões e bugs que escaparam

Até a 2.56.0 a coleta lia o arquivo da atividade e **pulava o Histórico**, que
é onde o caminho dela está escrito. As voltas 9→8, as devoluções do portão e as
reaberturas existiam em texto e não eram contadas, e qualquer mudança no fluxo
(trilha por risco, teste antes do código, revisor de outro modelo) ficaria sem
número para se defender.

`flow_state.percurso()` lê os **marcos** do Histórico: linha cujo Step começa
com um número do fluxo, ou `concluída`. O resto (lugar corrigido, artefato
retirado) não é marco e não mexe na conta.

| O quê | Como se conta |
| --- | --- |
| volta de correção | retrocesso que sai de step de **IA** (`9→8`, `4→3`), por par |
| devolução | retrocesso que sai de **portão humano**; motivo `escopo` se a nota tem a palavra, `defeito` no resto |
| aprovação | avanço que sai de portão humano, ou `concluir` estando nele |
| reabertura | linha que começa com `Reaberta:`, ou qualquer marco depois de `concluída` |
| tempo por step | do marco que entra ao marco seguinte; o step ainda aberto não conta |

No projeto, `agregar_percurso` soma tudo e acrescenta o **bug que escapou**:
atividade aberta com `iniciar --corrige <origem>`, contada na origem e por
trilha dela (`concluídas` × `com bug depois`). Origem que não está no projeto
fica em `bugs_com_origem_fora`, nomeada.

**O que isto NÃO prova:**

- **A taxa de bug é um piso.** Bug consertado sem `--corrige` não entra, e
  entrega sem bug pode ser só entrega que ninguém usou ainda.
- **O motivo da devolução é o que a nota diz.** Devolução por escopo escrita
  sem a palavra conta como defeito.
- **Tempo de relógio não é esforço.** Um portão aberto na sexta e aprovado na
  segunda soma o fim de semana; a hora humana medida continua sendo a do
  transcrito.
- **Registro coletado antes da 2.57.0 não tem percurso.** Ele aparece em
  `sem_percurso`, nomeado, em vez de entrar como zero; `coletar` sem
  `--atividade` refaz todos.

## Os dois PF

`pf` é do analista, contado da especificação funcional, antes de existir
código. `pf_aferido` é do step 9, contado da entrega, com o **inventário** do
que foi contado ao lado — cada função, seu tipo e sua complexidade.

```bash
python3 $F pf <id> --declarado 8
python3 $F pf <id> --aferido 13 --inventario docs/.../1057-pf.md
```

`--aferido` **é recusado sem `--inventario`**, e a recusa é mecânica de
propósito: o número entra no denominador de todo h/PF citado depois, e sem a
conta que o sustenta ele é palpite com casas decimais. Obrigação escrita em
prosa não acontece — é a mesma razão da tabela de *Conferências*.

Quando os dois divergem, **o que divergiu foi o escopo**, e nem o transcrito
nem o Git dizem qual estava certo. A ferramenta reporta os dois, o sentido da
diferença e o caminho do inventário; h/PF sai para **os dois**, com sufixo,
porque citar um h/PF sem dizer de qual PF ele saiu é citar o número sozinho.
Ninguém desempata — o portão 10 vê a divergência e decide.

## O conjunto: o que o paralelismo comprou

Uma atividade por vez não responde a pergunta que importa quando três correm
juntas: **quanto o paralelismo comprou.** E a resposta ingênua — somar os
relatórios — sai errada para o lado que agrada.

```bash
metrics.py conjunto <ids ou caminhos de JSON já coletados>
```

Ele recebe os registros, de quantos `.agents/` forem. Isso não é preguiça de
descoberta: um conjunto real atravessa projeto — a mesma demanda rodando no
backoffice e no aplicativo móvel são duas atividades, em dois `.agents/`,
e nenhum `projeto.json` sozinho as contém.

**O que soma:** tokens, custo, turnos, agentes. É consumo, e aconteceu.

**O que NÃO soma, e é o ponto inteiro:**

`prazo` é relógio de parede, e as atividades se sobrepõem. A soma dos prazos é o
que teria custado **em série** — que é o numerador do ganho, não o prazo. Os
dois são impressos, e a razão entre eles é o ganho de paralelismo.

`hora humana` é a pior de somar, porque **a pessoa é uma**. Três atividades
paralelas somadas contam você três vezes no mesmo minuto — e subestimar esforço
humano **infla o ganho da ferramenta**, que é o erro que este coletor declara
não poder cometer. Aqui ela sai da **união dos intervalos**, e a soma aparece ao
lado só para mostrar quanto se evitou de contar duas vezes.

> Se você leu a atividade A de 10:00 às 10:08 e a B de 10:05 às 10:12, o seu
> tempo foi **12 minutos** — não 8 + 7 = 15.

É por isso que o registro de cada atividade guarda os **intervalos já capados**,
e não só o total: do agregado a união não é calculável.

A reentrada continua por interação. Cada mensagem que você digitou é um retorno
de contexto que aconteceu de fato, e trocar de atividade não o torna mais
barato. Ela usa o padrão do pacote, não o config de um projeto — o conjunto
atravessa `.agents/` e não há um config que valha para todos, então o valor
usado é impresso em vez de ficar implícito.

**O que o conjunto NÃO prova:** que o paralelismo foi de graça. A razão mede
relógio, não conflito. Duas atividades que se atrapalham produzem o mesmo ganho
de prazo e um retrabalho que este número não vê.

## O orçamento: quando o gasto vira limite

O custo medido não servia para nada além de relatório. `[metricas]
orcamento_usd` muda isso: declarado, o `avancar` **para** quando a última
coleta da atividade passou do teto, e diz os três números — gasto, teto e
quanto passou. Libera com `--forcar --nota`, que é o mesmo idioma de sair da
trilha: não é proibido, é registrado.

Três recusas no desenho, e cada uma tem número atrás:

**Por atividade, não por step**, embora a frente aberta pedisse por step. O
coletor só atribui step aos **subagentes** — `por_step` é preenchido dentro do
laço de subagente — e os turnos do orquestrador não têm step. No painel medido
eles são **27,7% do gasto**. Um teto por step veria menos do que se gasta, e
número que sai menor do que é é a direção proibida.

**Em dólar, não em token.** São quatro contadores com preços até 50× diferentes
entre si: na mesma atividade, **1,83 bilhão** de cache lido contra **3,97 M** de
saída. Somar os quatro dá um número dominado pelo cache barato, e alguém
queimaria saída à vontade sem mover o total. Dólar é a soma ponderada pelo preço.

**O `concluir` nunca é barrado.** Travar o fechamento deixaria a atividade presa
em andamento, que é pior que estourar o teto — e o `concluir` é o aceite de uma
pessoa, não passagem automática.

E o conferidor **nunca derruba o `avancar` por conta própria**: config ausente,
JSON corrompido ou chave mal declarada resultam em "não confere", nunca em
exceção. O `avancar` é a espinha do fluxo, e um conferidor de orçamento não pode
quebrá-la. Quem reprova declaração malformada é o `doctor.py`.

> **O número é da última coleta, não de agora.** A mensagem imprime quando ele
> foi colhido, justamente para que ninguém confunda os dois. Quem quiser decidir
> com número fresco roda `metrics.py coletar --atividade <id>` antes.

**E o zero silencioso reaparece aqui.** Uma atividade que a coleta não conseguiu
atribuir reporta US$ 0,00 — e passaria por baixo de qualquer teto, para sempre.
Nesse caso o orçamento **não confere, e diz que não conferiu**, com o motivo.
Não conferir é correto; não dizer seria a mesma falsa completude que o estado
`sem-prova` existe para acusar.

## Publicar no repositório: a fronteira que se atravessa de propósito

O `install.sh` põe `.agents/` em `.git/info/exclude`, porque ferramental de IA
não é entregável do cliente. Está certo — e tem uma consequência: **o painel
existe no disco de quem rodou, e mais ninguém o abre.** Quem quer saber como vai
o projeto precisa pedir a alguém que rode um comando.

`metrics.py publicar` move um **resumo** para dentro do versionamento:

| | |
| --- | --- |
| `docs/metricas.html` | a página, um clique, com exportar |
| `docs/metricas.md` | o mesmo em texto, que rende diff legível |
| `README.md` | um bloco entre marcas, com o link |

**Nunca por conta própria.** `[metricas] publicar_no_repo` é `false` por padrão.
Ligada, o `avancar` regenera os três a cada passagem de step e o `concluir`
regenera e dá `git add` — e **nunca commita**, pelo mesmo motivo do `attach.py`:
criar commit no meio de outra coisa mexe no histórico sem ninguém ter pedido.
A única coisa que fura o silêncio do `avancar` é a **primeira** escrita num
README que o pacote não escreveu; isso acontece uma vez, e acontecer calado
seria o pacote se impondo.

### O que fica de fora, e por quê

**Hora humana por atividade.** No `.agents/` ela é diagnóstico de quem rodou.
Versionada, ao lado do nome da branch, ela vira **nota de desempenho
individual** — com duas pessoas no projeto dá para ler quem gastou mais hora por
card, sem que a métrica tenha sido desenhada para isso. O total do projeto fica;
a linha por atividade, não. O detalhe por step e por agente também sai: ele
responde "onde foi o custo", que é pergunta de quem opera.

### A régua APF do projeto, e os dois conjuntos

A régua por atividade já existia. A do projeto tem um erro próprio para evitar:
**somar o PF de TODAS as atividades e confrontar com a hora humana das
ATRIBUÍDAS.** Os dois lados sairiam de conjuntos diferentes, e mais PF estimado
sobre menos hora medida INFLA o ganho da ferramenta — a única direção que este
coletor declara não poder errar.

Então a conta usa só as atividades que têm **as duas coisas**, atribuição e PF,
e nomeia as que ficaram de fora.

**E são dois fatores, nunca um.** A estimativa APF dividida pela hora humana dá
um número grande — na primeira montagem, 106×. Ele é verdadeiro e é metade da
história: enquanto a pessoa não estava na frente da tela, a máquina estava, por
57 h de relógio e por dinheiro. O mesmo caso dividido pelo relógio dá 10×.

Um fator só, publicado sem o outro, é o tipo de número que se repete numa
reunião e cai na primeira pergunta. **A diferença entre os dois é a
informação.**

### Exportar

A página leva três saídas, e cada uma diz o que não faz:

| | O que faz | O limite |
| --- | --- | --- |
| **PDF** | abre a impressão do navegador | — |
| **Teams** | deep link com o resumo escrito; quem manda escolhe o destinatário | não posta sozinho: postar exigiria credencial, e página versionada não é lugar de guardar uma |
| **E-mail** | `mailto:` com assunto e corpo | link não carrega mais que ~2 mil caracteres |

Nos três, o resumo também vai para a área de transferência — se o cliente cortar
o corpo, um `Ctrl+V` resolve. E o resumo é **curto de propósito**: página inteira
não cabe em link.

No papel a página **inverte** as cores. Fundo navy gasta tinta, e vários
navegadores descartam a cor de fundo por padrão — o que deixaria tinta clara
sobre branco, ilegível.

## Ligar, desligar, e conferir

O padrão é **ligado**: a coleta roda a cada `avancar` e no `concluir`, só da
atividade em questão (~3 s), e **nunca reprova** — um `avancar` que falha
porque o coletor tropeçou trocaria o estado do fluxo, que é a fonte de verdade,
por um relatório. Isso é decisão de produto, não regra tirada de erro medido, e
fica dito para ninguém procurar a medição.

`[metricas] ligado = false` faz a coleta sair calada. O estado aparece no
`doctor.py conferir`, junto com o resto do que está declarado.

**A conferência do doutor é assimétrica, e a razão está no coletor**:
*subestimar a hora humana INFLA o ganho da ferramenta — é o erro que não se
pode cometer.* Então:

- **reprova** o que faz o número sair **menor**: teto de leitura zerado, tempo
  de reentrada negativo, preço zerado, valor não numérico (a coleta morre no
  `int()` e o gancho engole o erro em silêncio);
- **informa** o que faz sair **diferente**: preço divergente do padrão do
  pacote, chave de preço com typo — que é ignorada —, reentrada declarada em
  zero, coleta ligada que nunca rodou, e atividades sem prova de atribuição na
  última coleta.

Um `0` declarado vale 0. Era `int(valor or padrao)`, e o `or` engolia o zero: o
config dizia 0, o coletor usava 10 e o rodapé imprimia 10. Config que não faz o
que diz é pior que config ausente, porque quem declarou acredita ter declarado.
