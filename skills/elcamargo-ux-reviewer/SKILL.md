---
name: elcamargo-ux-reviewer
description: "Step 6 do fluxo de desenvolvimento com IA. Orquestra a validação ou a criação dos protótipos de tela: pergunta se há link de Figma, dispara o leitor de Figma ou o desenhista de telas em subagente, e documenta as decisões visuais que o desenvolvedor vai seguir. Use quando uma atividade estiver no step 6, ou quando o usuário pedir para validar protótipos contra as SDDs."
---

# Step 6 · UX Reviewer

Fecha as decisões de tela **antes** da implementação, para o step 8 não
inventá-las. Você orquestra: quem faz o trabalho visual é um subagente.

Este step só começa depois do portão humano do step 5. Se a especificação não
foi aprovada, prototipar é gastar em cima de uma base que pode mudar.

## O ofício

- **`$PACOTE/references/screen-specification.md`** — **o que é uma tela especificada** — os sete estados, validações com texto, permissão, acessibilidade, responsivo.
- **`$PACOTE/references/specialties/executable-prototype.md`** — **o artefato que você entrega ao step 8.**
- **`$PACOTE/references/pending-decisions.md`** — como escalar a divergência que muda regra de negócio.
- **`$PACOTE/references/evidence.md`** — afirmar não é provar — meça o que você diz que a tela mostra

## Contrato

**Leia `$PACOTE/FLOW.md` antes de começar.** Ele é o contrato do fluxo, e traz o
que nenhuma skill repete por inteiro: como o portão humano é entregue, como você
fala dos steps no chat, o limite de voltas entre quem faz e quem revisa, e o que
todo step deve ao próximo.

```bash
# Onde a FERRAMENTA mora. Três lugares possíveis, em ordem de confiança, e
# cada linha só corre se a anterior não achou uma pasta que existe:
#
#   1. `CLAUDE_PLUGIN_ROOT`  o harness diz. Não confie que ela SEMPRE chega
#      aqui — ela é documentada para hook, e para skill não está confirmado.
#   2. `.agents/elcamargo-flow`  o pacote copiado dentro do projeto.
#   3. o cache de plugin instalado, a versão mais alta.
#
# A terceira existe porque a primeira é incerta: sem ela, um projeto que só tem
# o plugin ficaria sem pacote se a variável não chegasse. Com ela, o pior caso
# é achar pelo caminho mais feio — e não falhar.
#
# O estado do PROJETO — `config.toml` e `atividades/` — continua no `.agents`
# nos três casos. Só a ferramenta se move.
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

Confirme o step 6. Se a atividade estiver no **5**, o portão da especificação
ainda não foi atravessado: **pare** e devolva o comando, em vez de só avisar.

```
A atividade está no portão humano do step 5. Aprove a especificação e rode:
    python3 $F avancar <id> --nota "especificação aprovada"
depois me chame de novo.
```

## 1. Perguntar — portão

Pergunte ao usuário, e espere:

> Tem protótipo no Figma para esta atividade? Se tiver, me passa o link. Se não
> tiver, eu gero as telas de preview a partir das SDDs.

Não decida sozinho, e não presuma que não há porque ninguém mencionou.

## 2. Disparar o subagente

**Com link de Figma** → subagente `elcamargo-figma-reader`, passando o link,
os caminhos das SDDs de negócio e de sistema, e o id da atividade.

**Sem link** → subagente `elcamargo-screen-drawer`, passando as SDDs, o id, e
os caminhos das convenções de frontend do projeto.

Um ou outro, nunca os dois. Aguarde o retorno antes de seguir.

## 3. Conferir o protótipo antes de aceitar

O subagente devolve o protótipo. **Não o repasse sem olhar:**

- Ele **compila**? Propriedade inventada de componente é o defeito mais comum.
- Todos os estados estão lá e são **alternáveis** — inicial, carregando, vazio
  (os dois), com dado, erro, sem permissão, parcial?
- Foi **renderizado e visto**, nas larguras do projeto? Se não, ele disse isso?
- Ele separou o que reusou de padrão existente do que **inventou**?

O que ele inventou é o que o portão 7 precisa olhar com mais atenção: confirmar
um protótipo do Figma é decisão diferente de confirmar o que uma IA deduziu de
um texto.

## 4. Consolidar as decisões

O subagente devolve divergências ou artefatos; **a decisão é sua**, e é ela que
o step 8 vai seguir. Documente em Markdown, em `docs.specs`:

- Cada tela, com **todos** os estados de `$PACOTE/references/screen-specification.md`:
  inicial, carregando, vazio, com dado, erro, sem permissão, parcial. "Não se
  aplica" é resposta; ausência não é.
- Cada campo com rótulo, obrigatoriedade, máscara e **o texto de cada
  validação** — a mensagem que o usuário lê é especificação, não detalhe.
- Cada divergência entre protótipo e SDD: o que o Figma mostra, o que a SDD diz,
  **qual prevalece e por quê**.
- Componentes e biblioteca do projeto que cada tela deve usar.
- O que ficou pendente de decisão humana.

Uma divergência não resolvida aqui vira retrabalho no step 8 ou, pior, uma tela
implementada contra a regra de negócio.

## 5. Regra do Figma

O Figma tem **prioridade**, não autoridade automática. Onde ele contraria a SDD:

- Registre a diferença explicitamente. Nunca a absorva em silêncio.
- Se a diferença for só visual, o Figma prevalece e você anota.
- Se a diferença mudar **comportamento ou regra de negócio**, ela não é decisão
  de UX. Pare, registre como pendência e escale ao usuário.

Um botão em outra cor é decisão de UX. Um campo que o Figma torna opcional e a
RN exige obrigatório não é.

## 6. Fechar o step

```bash
python3 $F artefato <id> --tipo decisoes-ux --caminho <caminho>
python3 $F artefato <id> --tipo prototipo --caminho <caminho do componente>
```

### Publicar no Figma — opcional, e sempre autorizado

Quando o protótipo nasceu do `screen-drawer` e o Figma não tem aquela tela, faz
sentido devolvê-la para lá, para o design não descolar do produto.

**Nunca por padrão.** Escrever num arquivo de design compartilhado é ação para
fora, no arquivo de outra pessoa: **pergunte a cada vez**, e só ofereça quando o
`whoami` indicar seat que permite.

E não construa dependência nisso: o recurso de escrita é beta e a Figma avisa
que passará a ser cobrado por uso. Se sumir, perdemos uma conveniência, não uma
etapa — **o artefato que garante a qualidade do desenvolvimento é o protótipo no
repositório**, não a tela no Figma.

Gere o resumo com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-ux-reviewer`, e anexe ao card como refinamento de UX.

**Anexe sempre com `$PACOTE/tools/attach/attach.py`**, nunca chamando a API do
rastreador direto:

```bash
python3 $PACOTE/tools/attach/attach.py <arquivo.pdf> --card <id> \
  --comentario "<o que é>"
```

Ela verifica por ida e volta — sobe, baixa o que o servidor guardou, compara o
hash — e **não vincula nada ao card se os bytes não baterem**. Isso existe
porque um upload pode devolver 200 e guardar arquivo corrompido: `az rest
--body "@arquivo"` trata binário como texto e sobe base64, o card mostra o
anexo, e o PDF não abre. Só se descobre quando alguém tenta ler.


**Confira que subiu, e registre.** A verificação de ida e volta prova que o byte
chegou íntegro; ela não prova que o anexo aconteceu. Numa execução real a
ferramenta estava quebrada e recusava todo PDF com 400 — a obrigação estava
escrita, o comando estava lá, e o anexo nunca subiu. Descobriu-se uma atividade
depois.

```bash
python3 $PACOTE/tools/attach/attach.py --conferir <id>
python3 $F artefato <id> --tipo anexo --caminho <nome-do-pdf>
```

**Não se declare concluído com o anexo em dúvida.** Se falhou, diga que falhou e
por quê. Ver `FLOW.md`, *Verificar que subiu é do step, não do usuário*.

Todo comentário ou anexo que você publica no card abre com a linha:

> *Gerado com assistência de IA e revisado antes de publicar.*

É a mesma regra da assinatura compartilhada dos documentos, aplicada ao que
circula no board: quem lê tem direito de saber como aquilo foi produzido, e a
frase só é verdadeira se a revisão aconteceu de fato.
Chame `elcamargo-activity-management` para commitar — ela delega ao gerenciador de Git do projeto e não mexe no estado da atividade, que é seu. Depois avance e termine assim:

```
Step 6 concluído. 4 telas documentadas, 2 divergências resolvidas, 0 pendentes.


### Entregue o portão como perguntas, não como leitura

**Não peça para a pessoa ler o documento e opinar.** Levante as decisões que
o desenhista ou o leitor de Figma tomou sobre a tela — divergência com o
protótipo, componente escolhido, estado que não estava desenhado e traga cada uma como **card de pergunta clicável**, no máximo quatro
por vez, com opções reais e a consequência de cada uma. A pessoa lê, entende e
responde.

A regra inteira — o que vira card, o que não vira, e como escrever — está em
`FLOW.md`, *O portão humano chega como pergunta, nunca como leitura*.

Três linhas de contexto antes das perguntas: o que este step fez, o que os
portões mecânicos disseram, e onde ler se a pessoa quiser. O documento continua
sendo a evidência; ele só deixa de ser o pedido.

**A aprovação é a última pergunta, não a única.** Portão que só pergunta
"aprovado?" é carimbo, não portão.

Próximo: PORTÃO HUMANO — revisão das telas (step 7).
Artefatos em docs/specs/...

Quando aprovar, rode você mesmo:
    python3 $F avancar 1042 --nota "telas aprovadas"
    /elcamargo-developer 1042
```

O step 7 é humano. **Você para aqui.** Quem roda o `avancar` é a pessoa. Imprima
os dois comandos: sem eles a atividade fica parada no 7 para sempre.

Diga explicitamente **como as telas foram produzidas** — lidas do Figma ou
desenhadas pelo `screen-drawer`. Quem revisa precisa saber se está confirmando
um protótipo que o cliente já viu ou uma tela que a IA inventou a partir do
texto da SDD. São decisões de peso diferente.

## Você não terminou enquanto o subagente não voltar

Disparar é o começo do step; consolidar é o trabalho dele. Se o subagente não
retornar, **nomeie-o**, declare a entrega incompleta naquela dimensão, e entregue
o que você tem. O silêncio dele nunca conta como aprovação.

Ver `FLOW.md`, *Disparar não é terminar*.

## O roteiro que a execução vai percorrer

Os estados que você especifica não são descrição: **são o roteiro que o step 9
vai exercitar na tela**. A frente de execução lê o seu artefato para saber o que
tentar, e o que ela não conseguir alcançar vira achado.

Por isso, para cada tela, deixe os estados **enumerados e nomeados**, não
diluídos na prosa — e diga, quando souber, **como se chega** a cada um: qual
filtro não acha nada, qual permissão falta, qual chamada precisa falhar.

Um estado que você especifica e ninguém consegue provocar é, em si, um achado: ou
a condição não acontece, ou outra guarda dispara antes. Ver
`$PACOTE/references/specialties/system-usage.md`.

## Nunca faça

- Começar antes da aprovação humana do step 5.
- Rodar os dois subagentes.
- Aceitar do Figma uma mudança de regra de negócio sem escalar.
- Implementar a tela — isso é o step 8.
- Atravessar o portão humano do step 7.
