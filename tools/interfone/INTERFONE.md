# interfone

O canal entre sessoes de IA. Substitui o `canal.mjs`, que continua funcionando
enquanto as outras frentes nao migram.

    node interfone.mjs                     # a ajuda inteira

## Por que ele existe

O `canal.mjs` foi desenhado para **uma sessao por papel**. Em 09/09/2026 duas
sessoes assumiram o papel `app` ao mesmo tempo, e tres defeitos apareceram
no mesmo dia:

| | O que acontecia | O que o interfone faz |
| --- | --- | --- |
| **Leitura destrutiva** | `ler` movia o arquivo para `_lidos`. **O primeiro leitor consumia a mensagem e o segundo nunca a via** — sem erro, sem rastro | `ler` **imprime e marca**. A marca e' por sessao, num arquivo proprio de cada uma. Arquivar virou ato deliberado, e **recusa** enquanto alguem nao leu |
| **Um registro por papel** | O `atalho:` nomeava a sessao errada com confianca | `sessoes.json` guarda **lista**, com `visto_em`. `enviar` diz quantas sessoes ha' no destino e **quais estao frias** |
| **Sem endereco de sessao** | O jeito de dizer "isto e' para o chat-mobile" era escrever na linha de assunto, em prosa que a ferramenta nao le' | `--para-sessao`. Quem divide o papel ainda ve' com `--todas`: saber o que o outro recebeu importa |

E um quarto, que era ausencia e nao defeito: **nada tocava**. Uma mensagem ficava
horas ate' alguem lembrar de olhar.

## Como uma janela entra — e por que isso deixou de depender de memoria

Ate 09/09/2026 a ferramenta morava numa pasta solta, fora de todo
repositorio, e **nada em lugar nenhum a mencionava**. Uma sessao inteira do
`ai-flow` trabalhou um dia sem saber que ela existia. A causa nao foi
desatencao: nao havia o que ler.

Hoje o harness pergunta sozinho. Tres hooks globais, em `~/.claude/settings.json`:

| Evento | O que acontece |
| --- | --- |
| `SessionStart` | descobre o papel do repositorio e **manda o assistente perguntar** se voce quer entrar |
| `UserPromptSubmit` | entrega as mensagens novas, e renova o sinal de vida |
| `SessionEnd` | da baixa da sessao |

**O papel vem de tres lugares, nesta ordem:** `.interfone.json` na raiz do
repositorio (a decisao explicita), o `repositorio` de cada papel no
`topologia.json` (a inferencia — os repos ja mapeados nao precisam de arquivo
nenhum), e por ultimo voce, respondendo a pergunta. Quando voce responde,
`entrar` **grava o arquivo**, e a janela seguinte ja entra sabendo.

    interfone entrar                  # o papel vem do repositorio
    interfone entrar <papel>          # entra num papel que ja existe, e grava
    interfone entrar <papel> --novo   # cria o papel, com este repo como casa
    interfone recusar                 # nao nesta janela, e nao pergunte de novo
    interfone ligar <a> <b> --mao-dupla   # quem pode falar com quem

## O que ele NAO faz, e nao vai fazer

**Ele nao toca, e o hook nao pergunta.** Arquivo em pasta nao acorda ninguem, e
hook imprime — nao abre dialogo. A pergunta e' feita pelo **assistente**, a
partir do texto que o hook injeta no contexto: isso e' conselho, e conselho
falha. A defesa e' o lembrete **voltar a cada mensagem** enquanto nao houver
decisao gravada, entrar ou recusar. Assim o esquecimento custa uma mensagem, e
nao a sessao inteira.

A **entrega da caixa**, essa sim, e' mecanismo: chega a cada mensagem sua, sem
ninguem lembrar de rodar nada.

**Registrado sem entrega e' pior que nao registrado** — parece que alguem esta'
escutando. Era o estado de toda sessao antes destes hooks.

### Anunciar nao e' ler, e confundir os dois custava contexto em todo turno

O hook listava **tudo que a sessao nao tinha aberto com `ler`**. Mas nao se le'
tudo que chega: mensagem de outro assunto fica pendente de proposito, e voltava
listada por extenso **a cada turno, para sempre**.

Medido no `acme-app` em 18/09/2026: **34 despejos, 567.401
bytes**, repetindo as **mesmas onze mensagens de 15/09** — tres dias velhas,
varias ja' resolvidas. O harness injeta ~2 KB de previa por despejo, entao foram
uns **68 KB de contexto** gastos em repeticao pura, numa conta que estourava
limite semanal.

Agora ha **dois** conjuntos por sessao, e eles respondem perguntas diferentes:

| conjunto | responde | quem grava |
| --- | --- | --- |
| `<papel>/lidos/<sessao>.json` | *ela abriu esta mensagem?* | o `ler` |
| `<papel>/anunciadas/<sessao>.json` | *ela ja' viu esta mensagem listada?* | o hook |

O primeiro continua sendo o que o `status` e o `arquivar` consultam — **anunciar
nunca conta como ter lido**, senao `arquivar` passaria a esconder mensagem que
ninguem abriu.

O que o hook imprime agora:

- **chegou coisa nova** — lista as novas por extenso, e resume o resto numa
  linha: `(+149 nao lida(s) ja listada(s) antes, 27 URGENTE(S) — interfone caixa …)`;
- **nada novo** — **uma** linha, com a contagem e os urgentes. Medido no mesmo
  caso: de **28.756 bytes para 153**.

**A linha nao some quando nao ha novidade**, e isso e' escolha: a sessao continua
com mensagem nao lida, e esquecer disso e' pior que uma linha por turno.

**O arquivo se poda sozinho** — grava-se a lista das pendentes de agora, entao id
lido ou arquivado sai na passada seguinte sem ninguem limpar nada.

**E ele falha para o lado barulhento, de proposito.** A leitura dele nao passa
pelo `lerJson`: aquele chama `erro()`, e `erro()` em modo hook faz
`process.exit(0)` — saida de processo **nao e' excecao**, entao `try/catch` em
volta nao pega nada. Com um arquivo corrompido de proposito o hook morria calado,
**zero linhas, canal mudo**. Medido, e consertado: hoje um arquivo ilegivel faz
tudo voltar a ser inedito, o hook lista tudo, e o arquivo se regrava bom na mesma
passada. Uma conveniencia de contexto nao pode ter poder de derrubar a entrega
de mensagem.

**Nao ha tipos de canal**, e a ausencia e' escolha: tres caixas viram tres
lugares para esquecer de olhar. O que existe e' **destino** (papel ou sessao) e
**prioridade** (`--urgente`).

## Travas — e isto nao e' mensagem

*"Estou nesta branch ate' devolver ao step 9"* nao e' recado: e' **estado**.
Mensagem se le' uma vez e esquece; estado se **consulta antes de agir**.

    interfone travas                       # ANTES de encostar em qualquer coisa
    interfone travar app doc/x "ate devolver ao step 9"
    interfone destravar doc/x

`travar` **recusa** recurso que ja' e' de outra sessao, dizendo quem, desde
quando e por que. A colisao de 09/09 — duas sessoes na mesma atividade, e um
worktree deixado no scratchpad de uma sessao alheia — teria sido evitada por uma
consulta de tres segundos.

`travas` marca como **orfa** a trava cuja sessao nao esta mais registrada.

## Semear a linha de base do vigia — e a armadilha que isto fecha

    interfone semear <papel> --sessao <s> [--arquivo <p>] [--forcar]

**Nao semeie a partir da saida do `caixa` a' mao.** A receita antiga fazia isso, e
ela tem uma armadilha: se houver mensagem pendente na hora de semear, ela entra na
linha de base como *"ja avisada"* **sem nunca ter sido lida**, e o vigia jamais
dispara sobre ela. Como o vigia existe para ninguem precisar lembrar de olhar, o
aviso perdido nao volta.

Por isso o `semear` **recusa** quando ha' pendencia, lista o que voce nao leu, e
sai com `1`. Com `--forcar` ele semeia e **diz quantas** vao ficar sem aviso.

**O que o vigia faz com o arquivo:** compara a caixa contra ele e **acrescenta**
o que anunciou. O arquivo guarda o ANUNCIADO, que nao e' o lido — um vigia que
olhasse so' o `caixa` reanunciaria a mesma mensagem de 90 em 90 s ate' alguem
ler. Estava so' implicito, e a sessao `acme-backoffice-fd` teve de
deduzir; deduziu certo, e deduzir nao devia ser necessario.

**Uma metade do relato original nao procede, e foi medida:** a caixa **nao**
esvazia e o `status` continua honesto — a mensagem segue listada como nao lida.
O que se perde e' so' o aviso. O achado e' da sessao `elcamargo-ai-flow-fe`.

## O sinal de vida se mantem sozinho

**Olhar a caixa E' o sinal de vida.** Cada `caixa` renova o `visto_em` da sessao
que chamou — e como o vigia chama `caixa` a cada 90 s, o frescor se mantem sem
comando nenhum para alguem esquecer.

Antes disto toda sessao aparecia `FRIA` depois de 30 minutos, inclusive as que
estavam trabalhando, e o aviso de frescor virava ruido que se aprende a ignorar.

## Onde mora o que

| | |
| --- | --- |
| O programa | `~/.interfone/interfone.mjs` |
| O comando | `~/.local/bin/interfone` — de qualquer pasta |
| Os dados | `~/.interfone/dados/` numa instalacao nova — caixas, `topologia.json`, `_lidos/`. Quem ja tinha caixas noutra pasta continua com elas |
| Os hooks | `~/.claude/settings.json` |
| O papel do repo | `.interfone.json` na raiz dele |

**O programa mudou de lugar; os dados nao.** O `canal.mjs` e as sessoes que
estavam no ar leem aquelas pastas por caminho absoluto, e mover tudo junto
quebraria quem estava rodando. `~/.interfone/config.json` diz onde os dados
estao, e `INTERFONE_RAIZ` sobrepoe — que e' como se testa sem encostar no que
vale. O caminho antigo do programa continua funcionando: virou um repasse.

## Fluxo de um dia

    interfone entrar                                # ou responda a pergunta do inicio
    interfone travas                                # quem esta com o que
    interfone caixa app                        # o que EU ainda nao li
    interfone ler app <id>                     # imprime e marca
    echo '...' | interfone enviar app backoffice 'assunto que diz o que resolve'
    interfone status <id>                           # quem leu, quem nao

**Texto livre entre aspas simples.** Entre aspas duplas o shell trata a crase
como substituicao de comando, e um assunto escrito na nossa voz — *"o `avancar`
falhou"* — chega ao destino **sem a palavra**, sem erro nenhum a conferir.

A sessao vem de `--sessao` ou de `INTERFONE_SESSAO`.

## O que fica igual

Os arquivos moram onde sempre moraram — `<papel>/inbox/`, `_lidos/`,
`topologia.json`. **Nenhuma mensagem foi migrada**, e o `canal.mjs` continua
lendo e escrevendo as mesmas pastas. As duas ferramentas convivem; o que o
`interfone` acrescenta sao `sessoes.json`, `travas.json` e `<papel>/lidos/`.

O `registro.json` do `canal.mjs` fica onde esta', e o `interfone` **nao o le'
nem o escreve** — ele guarda uma sessao por papel, que e' exatamente a premissa
que quebrou.
