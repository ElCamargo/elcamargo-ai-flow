# A catraca: o que já falhava, e o que esta entrega quebrou

Um portão vermelho não diz qual dos dois é. Quem recebe o vermelho tem três
saídas ruins: caçar defeito que não é dele, ignorar o portão inteiro, ou marcar
"pré-existente" de memória — que foi o que aconteceu na POC, três vezes.

A catraca guarda o conjunto de falhas conhecidas na base e compara:

| | | |
| --- | --- | --- |
| **novo** | Falha hoje, não estava na base | **Reprova.** Esta entrega introduziu |
| **conhecido** | Já falhava antes | Não reprova. Não é dela |
| **consertado** | Estava na base e passou | **A base encolhe** |

O terceiro é o que a faz catraca, e não lista: **ela só aperta.** Uma falha
consertada sai da base e não pode voltar em silêncio.

## A identidade não pode conter o que uma edição legítima muda

Esta é a regra que decide se a ferramenta funciona, e o exemplo é medido.

O relatório de uma revisão real registrou um aviso de lint pré-existente como
`app-shell.tsx:176`. A entrega inseriu código acima dele. Hoje o mesmo aviso, da
mesma linha de código, mora na **185** — e uma catraca que guardasse o número
diria "falha nova" e devolveria a entrega por um aviso que ninguém tocou.

| Portão | Identidade |
| --- | --- |
| Teste | `arquivo > suíte > nome do teste` |
| Lint | `arquivo :: regra` — sem linha, sem coluna, **e sem a mensagem**, que muda quando a regra é reescrita numa atualização de dependência |

Para lint a catraca guarda **quantas vezes**, não só se: a mesma regra reincide
no mesmo arquivo, e de uma ocorrência para duas é regressão.

## Onde a base é gravada

**Na branch, antes da primeira linha de código.** Uma base gravada depois do
trabalho tem os defeitos do trabalho dentro dela, e a catraca passa a proteger
exatamente o que deveria pegar.

Custa uma rodada de portão. É o preço de saber de quem é o vermelho.

E ela viaja com o projeto, não com a máquina: uma base que não atravessa branch
e pessoa não é linha de base, é cache local, e o segundo a rodar o portão grava o
ruído da própria máquina como verdade. Declare o caminho em `[catraca] arquivo`
do `config.toml`; o padrão é `.elcamargo/catraca.json`, versionado.

## Regenerar a base para a falha sumir é o único jeito de perder

A catraca inteira depende de a base ser mais antiga que o trabalho. Regravá-la
por cima do vermelho de hoje transforma a regressão em passivo conhecido, com
uma linha de comando e nenhum registro.

Por isso `gravar` **recusa** quando o portão já tem base, e `apertar` **só
encolhe** — uma falha que falha hoje e não estava na base não entra por ali.

Admitir falha nova na base existe, e é gesto explícito com motivo escrito:

```bash
ratchet.py gravar --base <arquivo> --portao <nome> --admitir '<por quê>' <saída>
```

O motivo fica no arquivo e é impresso em **toda** conferência seguinte. Uma
concessão que ninguém relê vira norma; uma que reaparece a cada rodada continua
sendo concessão.

O mesmo vale para o portão visual: **nunca regenere baseline de imagem para
fazer uma falha desaparecer.** Na POC, 126 de 152 invariantes visuais estavam
ignoradas, e ninguém sabia — não porque alguém escondeu, mas porque nada contava.

## Os comandos

```bash
# uma vez, na branch nova, antes de codar
python3 $PACOTE/tools/ratchet/ratchet.py gravar \
    --base .elcamargo/catraca.json --portao lint --formato eslint \
    --comando "npm run lint" --raiz . saida-do-lint.txt

# a cada rodada de portão
python3 $PACOTE/tools/ratchet/ratchet.py conferir \
    --base .elcamargo/catraca.json --portao lint --formato eslint --raiz . -

# quando algo da base parou de falhar
python3 $PACOTE/tools/ratchet/ratchet.py apertar \
    --base .elcamargo/catraca.json --portao lint --formato eslint --raiz . -
```

A saída do portão vem por arquivo ou por `-` (stdin).

## Os formatos que ela lê, e por que não são mais

`vitest`, `jest`, `eslint` e `lighthouse` foram escritos **contra saída real**,
capturada rodando cada runner com uma falha de mentira. Playwright e `tsc` não
estão lá porque escrevê-los de memória seria procedência `leitura` — e
`severity.md` não aceita leitura como prova quando execução era possível.

Para esses, `--padrao` recebe um regex com um grupo nomeado `id`, escrito à
vista da saída que você tem na mão:

```bash
--padrao '^\s*\d+\)\s*\[.+?\]\s*›\s*(?P<id>.+?)\s*$'
```

Quem capturar a saída real de um portão novo, escreva o parser e o caso de teste
com ela — é assim que a lista cresce.

### `lighthouse`: o portão de qualidade de tela

A entrada é o JSON de `lighthouse <url> --output=json`. A identidade é
**`caminho da URL :: id da auditoria`** — sem host e sem porta, pela razão do
começo desta referência: a mesma tela em `localhost:8731` e em homologação é a
mesma tela, e a catraca não pode chamar de nova uma falha que só mudou de
ambiente.

**Só as auditorias `binary` com score 0 contam.** Os outros modos ficam fora, e
cada um por um motivo diferente:

| Modo | Por que não conta |
| --- | --- |
| `numeric` | Medida contínua. Na captura, LCP saiu 767,18 ms — catraca sobre medida oscila com a rede e a CPU de quem roda |
| `metricSavings` | **O caso perigoso**: parece falha. `unsized-images` — imagens sem `width` e `height`, defeito de verdade — veio com score **0,5**. Score fracionário é medida, não veredicto |
| `informative`, `notApplicable`, `manual` | Não afirmam nada sobre a página |

Na captura que escreveu o parser, as onze binárias que reprovaram foram
`button-name`, `color-contrast`, `document-title`, `errors-in-console`,
`html-has-lang`, `image-alt`, `label`, `landmark-one-main`, `link-name`,
`meta-description` e `tabindex`. Todas com id estável, e é isso que as torna
catraqueáveis.

**O que este portão NÃO cobre, e fica dito: regressão de performance.** O score
de performance é dominado por rede e CPU de quem roda — a página que a captura
quebrou de propósito, sem `title`, sem `lang` e com imagem sem `alt`, tirou
`performance = 1`. Piso por categoria seria portão que passa na máquina de quem
escreveu e reprova no runner de CI: devolveria entrega por ruído, que é a mesma
família do número de linha na identidade.

Quem quiser piso de performance precisa antes de uma **série de medições do
mesmo projeto** que mostre qual é a variação normal. Sem ela, qualquer piso é
chutado.

## O que a catraca não prova

**Que a falha conhecida é aceitável.** Ela não reprova *esta* entrega porque não
é dela; continua sendo de alguém. Uma base que só cresce, mesmo com motivo
escrito em cada linha, é um projeto apodrecendo devagar com registro caprichado.

Leve o tamanho da base ao portão humano junto da distribuição de destinos: `3
falhas conhecidas, 1 admitida nesta entrega` é informação que muda decisão.
