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

Essa última frase é o padrão da ferramenta inteira, e vale para o resto deste
documento.

## O zero silencioso

Uma atividade sem `branch` e sem `worktree` no cabeçalho não tem como ser
ligada a nenhuma sessão. Medido: o registro saía com **0 turnos e US$ 0,00**
com US$ 36,00 de trabalho da mesma pessoa no disco, no mesmo dia. O painel
mostrava como se nada tivesse acontecido — a família de defeito que o
`STATE.md` cataloga: *a ferramenta entrega algo que parece completo e não é.*

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
