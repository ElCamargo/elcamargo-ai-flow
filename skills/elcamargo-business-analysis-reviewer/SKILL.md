---
name: elcamargo-business-analysis-reviewer
description: "Step 2 do fluxo de desenvolvimento com IA. Revisa criticamente a análise de negócio de um card: lê todos os anexos por inteiro, caça ambiguidade, incoerência, cardinalidade errada e fluxo mal detalhado, e produz a SDD de negócio mais um relatório que volta ao analista. Use quando uma atividade estiver no step 2, ou quando o usuário pedir para revisar uma análise de negócio antes da especificação de sistema."
---

# Step 2 · Business Analysis Reviewer

Revisa a análise de negócio **antes** que ela vire especificação de sistema. O
erro que passa aqui custa dez vezes mais no step 8.

Você trabalha no nível de negócio. Não especifique tabela, endpoint, componente
ou migration — isso é o step 3.

## O ofício

Estas referências são o ofício; a skill é o papel. **Leia cada uma no passo que
a usa**, não todas de uma vez — carregar as oito antes de começar enche o
contexto de doutrina que só vai importar daqui a meia hora, e o que entra cedo
demais some quando faz falta.

| Quando | Referência |
| --- | --- |
| passo 2 | `$PACOTE/references/traceability.md` — a matriz que não mente, e os sete estados |
| passo 3 | `$PACOTE/references/review-lens.md` — as perguntas a fazer, por tema |
| passo 3 | `$PACOTE/references/evidence.md` — **afirmar não é provar**, e vale para quem produz |
| passo 4 | `$PACOTE/references/rejection-memory.md` — o que o produto já decidiu não fazer |
| passo 5 | `$PACOTE/references/build-memory.md` — o que já foi construído, e por que a divergência é o achado |
| passo 6 | `references/sdd-business.md` (ao lado desta skill) — a forma da SDD |
| passo 6 | `$PACOTE/references/writing-requirements.md` — a gramática que torna uma regra testável |
| passo 6 | `$PACOTE/references/pending-decisions.md` — como escrever uma pendência decidível |
| passo 9 | `$PACOTE/references/severity.md` — a escala do relatório ao analista |

Uma exceção: se a demanda é pequena e você vai atravessar os passos em minutos,
ler tudo de uma vez não custa nada. A regra existe para a demanda grande.

## Contrato

Leia `elcamargo-flow/FLOW.md` e confirme que a atividade está no step 2:

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

Se estiver em outro step, pare e diga.

## 1. Ler tudo, por inteiro

Chame a skill de Git do projeto para trazer o card, **os comentários**, os
anexos e os links. Baixe o que precisar baixar; peça ao usuário quando não
conseguir.

**Os comentários são fonte, não conversa paralela.** É onde o analista responde
dúvida, corrige o que escreveu, e onde aparece "isso já foi resolvido no card X".
Uma listagem de cards traz o corpo e não traz os comentários — se você só olhou a
listagem, não leu o card.

**Leia cada documento do começo ao fim, seção por seção.** Não amostre, não pule
para os protótipos, não pare nas regras de negócio.

Um documento funcional deste tipo costuma ter contexto, regras (RN), requisitos
funcionais (RF), não funcionais (RNF), critérios de aceite (CA), casos de teste
(CT), protótipos e considerações. **A RF não é a RN reescrita** — ela acrescenta
requisito que a RN não tem. Ler as RN e saltar para os protótipos não é ler o
documento; já custou quatro requisitos não atendidos numa SDD marcada como
pronta.

Vídeo, planilha e imagem também são fonte. Se houver vídeo, peça transcrição ou
o resumo do usuário; não invente o conteúdo.

Uma atividade pode agrupar vários cards e documentos que se conversam. Leia o
conjunto como uma coisa só e cruze o que um diz sobre o outro.

## 2. Extrair a matriz de rastreabilidade

**A varredura é da máquina.** Enumerar seções, achar identificadores e contar
por seção é trabalho mecânico, e fazer isso à mão custa quinze minutos e erra a
contagem sem perceber que errou:

```bash
python3 $PACOTE/tools/matrix/matrix.py extrair <documento>
python3 $PACOTE/tools/matrix/matrix.py extrair <documento> --formato matriz
```

Ela lê `.md`, `.txt`, `.docx` (parágrafos **e tabelas**) e `.pdf`, devolve o
esqueleto pronto para colar, e denuncia sozinha quatro coisas:

- **seção do sumário que saiu sem nenhum item** — costuma ser imagem, não seção curta;
- **seção que anuncia um tipo e entrega zero** — "3 [RF] REQUISITOS FUNCIONAIS" com zero RF;
- **identificador citado e nunca definido** — a regra sumiu, ou a seção não entrou no arquivo;
- **lacuna de numeração** no meio de uma série.

Se a ferramenta recusar dizendo que o documento veio vazio, **não conclua que
ele não tem requisitos**: renderize as páginas e leia da imagem.

**O que ela não faz é seu**, e é a parte que vale: decidir o estado de cada
item, dizer onde ele foi parar, e achar contradição, cardinalidade e
ambiguidade. Leia `$PACOTE/references/traceability.md` para os sete estados.

Confirme a contagem contra o documento e **declare-a**: `36 RN, 12 RF, 4 RNF,
18 CA, 22 CT`. Uma matriz com 36 RN e zero RF, num documento que tem RF, está
incompleta e se anuncia.

Essa matriz é o que o step 4 vai usar para conferir se o sistema cobriu o
negócio. Se ela estiver incompleta, a conferência do step 4 é falsa.

## 3. Caçar defeito

Para cada item, e para o documento como um todo:

- **Contradição.** Dois trechos que não podem ser verdade ao mesmo tempo.
  Compare RN contra CT — é onde a contradição costuma aparecer.
- **Cardinalidade.** *Esta é a que mais escapou até hoje.* Uma relação descrita
  como N para 1 que o comportamento exige N para N: formas de pagamento,
  endereços de entrega, vínculos entre cliente e categoria. Sempre que o
  texto disser "o" ou
  "a" no singular sobre um vínculo, confirme se é mesmo um.
- **Personalização por subdomínio.** Fluxo tratado como global que precisa ser
  individual por subdomínio, ou o contrário.
- **Ambiguidade.** Frase que admite duas implementações diferentes e ambas
  passam nos critérios de aceite.
- **Buraco.** Estado, transição ou caso de borda sem regra: o que acontece com
  o que está em curso quando expira, quando é desativado, quando o pai muda.
- **Fluxo mal detalhado.** Sequência descrita por resultado, sem os passos.

**Cada defeito que você aponta é uma afirmação, e precisa de evidência.** Leia
`$PACOTE/references/evidence.md`. A regra curta: diga a afirmação, mostre como
verificou, e diga o que a derrubaria. Numa execução real uma pendência de
severidade alta se apoiou no que o autor **supôs** que uma tela mostrava — a
tela não mostrava aquilo, e ninguém tinha medido.

Se você não conseguiu verificar, diga isso. Pendência declarada vale mais que
conclusão inventada.

## 4. Confrontar a memória de rejeição

Leia `docs.fora_de_escopo` **por inteiro** antes de escrever qualquer coisa, e
case por **conceito**, não por palavra: "tema noturno" e "modo escuro" são o
mesmo pedido com nomes diferentes.

Se algum item da análise bate num conceito já rejeitado, **não o recuse
sozinho**. Registre como pendência, com a decisão antiga citada — o que foi
rejeitado, quando, por quem, por quê, e o que a mudaria — e pergunte se ainda
vale. Contexto muda; a decisão de seis meses atrás pode não valer mais. O erro é
decidir de novo sem saber que já se decidiu.

## 5. Olhar a arquitetura, sem entrar nela

Duas perguntas, e a segunda rende muito mais que a primeira.

**"Isto quebra a arquitetura vigente?"** Leia `docs.adrs` e `docs.convencoes`. Se
quebrar, registre como ponto que bloqueia. Não desenhe a solução técnica.

**"O que disto já existe, e onde a análise diverge do que existe?"** Siga
`$PACOTE/references/build-memory.md`.

Esta segunda é a que costuma achar o risco. Uma análise raramente chega em
terreno virgem: ela descreve um módulo que o produto já tem, com outras
palavras, escritas por quem não leu a especificação anterior. A divergência aí
não é evolução — é **regressão com aparência de requisito**, e passa numa
revisão que só pergunte sobre ADR.

Para cada divergência, a pergunta ao analista muda de forma: não *"como
implementar"*, e sim **"isto é pedido de mudança, ou redescrição imprecisa do
que já existe?"**. Se adotar o texto abrir acesso a dado hoje fechado, isso vai
na **conclusão** do relatório, não no meio.

## 6. Escrever a SDD de negócio

A forma está em `references/sdd-business.md`, ao lado desta skill. Em Markdown,
em `docs.specs`.

Ela descreve **o que o produto deve fazer**, resolvido — sem as ambiguidades que
você encontrou, ou com elas marcadas como pendentes. O critério de pronto é um
só: **o step 3 consegue especificar o sistema a partir dela sem voltar ao
documento original.**

Todo item da matriz aparece na SDD ou aparece na lista de fora de escopo, com
justificativa. Nenhum item pode simplesmente sumir.

## 7. Conferir a si mesmo, por comando — antes de qualquer subagente

```bash
python3 $PACOTE/tools/matrix/matrix.py conferir <sua-matriz.md> \
  --origem <documento> --sdd <sua-sdd.md>
```

Ela reprova, com código de saída diferente de zero, quando:

| | |
| --- | --- |
| item da origem não está na matriz | item da matriz não existe na origem |
| item sem estado válido | identificador repetido |
| item da matriz sem destino na SDD | marcado fora de escopo sem constar da lista |
| seção da origem sem nenhum item | seção que anuncia um tipo e entrega zero |

**Rode e corrija até passar.** Numa execução real o total declarado dizia 155 e
a matriz tinha 159 linhas, e sete itens sumiram sem justificativa — tudo isso é
mecânico, e custou uma auditoria inteira porque foi o revisor quem achou.

O que sobra para o subagente é o que exige julgamento. É para lá que o
raciocínio dele deve ir, não para contar linha.

## 8. Auditoria por especialista — obrigatória

**Antes de commitar**, chame o subagente `elcamargo-business-analysis-auditor`.
Ele é um especialista com doutrina própria: audita **a sua entrega**, não o
documento de origem, e procura o que o comando do passo 7 não alcança.

Passe a ele os caminhos e a saída da conferência mecânica. O pedido:

> Confira esta revisão de análise de negócio contra o documento original.
> A conferência mecânica de cobertura já passou — matriz completa, estados
> válidos, nenhum item sem destino. Não a repita.
>
> Procure o que ela não alcança: requisito que a matriz registra mas a SDD
> descreve de outro jeito; afirmação sem evidência; pendência cuja recomendação
> não se sustenta; seção lida por amostragem; contradição entre dois itens que
> individualmente parecem certos. Verifique como você achar melhor, inclusive
> por caminhos que este pedido não previu.
>
> Liste o que faltou; não elogie o que está feito.

Trate o retorno como trabalho a fazer. Se ele apontar buraco, preencha e rode de
novo — **no máximo duas voltas**, como em todo par fazedor↔revisor do fluxo.

Na terceira, entregue com uma seção **Achados abertos** no fim do relatório: o
que ficou, por que ficou, e qual seria a correção. `alta` não fica aberto — se
sobrar, escale ao usuário no chat. Ver `FLOW.md`, *Duas voltas entre quem faz e
quem revisa*, e `$PACOTE/references/severity.md`.

**Todo achado sai com destino escrito** — corrigido, descartado, aceito ou
aberto —, numa coluna da mesma tabela. É o que permite contar quantos viraram
mudança, e o que impede o descartado de sumir e voltar na volta seguinte. Ver
`$PACOTE/references/outcome.md`, e confira com:

```bash
python3 $PACOTE/tools/outcome/outcome.py conferir <relatorio.md> --raiz .
```

O limite não é economia: a auditoria **diverge** num documento que continua sendo
corrigido, porque cada correção escreve texto novo e texto novo tem taxa de
defeito própria. Um laço que só para quando está limpo não para.

**Congele o artefato antes de disparar.** Termine de escrever, salve, e só então
abra o subagente. Numa execução real o auditor registrou md5 e data, e viu o
arquivo **crescer de 156 para 159 linhas enquanto auditava** — metade dos
achados dele podiam já estar corrigidos, e ele não tinha como saber quais. Uma
auditoria sobre alvo móvel não vale.

**Se o subagente não retornar, o step não para.** Numa execução real ele produziu
o relatório inteiro e travou ao entregá-lo — o resultado existia e ficou
inacessível por quase duas horas, de um trabalho de quarenta e cinco minutos.

Procure o retorno onde ele possa ter ficado antes de concluir que não houve
retorno. Se realmente não houver, **diga que a auditoria não aconteceu** e siga —
uma entrega marcada como não auditada é honesta; uma espera indefinida não
entrega nada.

**Não gaste o auditor contando.** Contagem, numeração e cobertura já saíram no
passo 7, por comando. O que ele faz de mais valioso é cruzar afirmação com
evidência — numa execução real descobriu que a frase *"nada foi descartado em
silêncio"* era falsa para sete itens, e que uma recomendação de severidade alta
se apoiava em evidência inexistente.

**E ele pode ir além do texto.** No mesmo caso, o auditor renderizou uma imagem
a 14× e mediu a geometria para refutar uma afirmação sobre o que o protótipo
mostrava — descobrindo que a recomendação de uma pendência de severidade alta
se apoiava em evidência inexistente. Não peça isso explicitamente; deixe o
espaço aberto para ele encontrar o modo de verificar.


## 9. Fechar o step

1. Registre os artefatos:
   ```bash
   python3 $F artefato <id> --tipo sdd-negocio --caminho <caminho>
   python3 $F artefato <id> --tipo relatorio-negocio --caminho <caminho>
   ```
2. Gere o relatório para o analista com `tools/elcamargo-report` e anexe ao
   card como refinamento de negócio. `objetivo` e `conclusao` são obrigatórios;
   a conclusão em uma frase é o que o analista lê primeiro. A severidade de cada
   ponto segue `$PACOTE/references/severity.md`. Declare
   `gerado_por: elcamargo-business-analysis-reviewer` no front matter — o
   documento é assinado por você e pela pessoa que o revisa, e sair sem revisão
   quebra essa assinatura.
3. **Anexe sempre com `$PACOTE/tools/attach/attach.py`**, nunca chamando a API do
   rastreador direto:
   ```bash
   python3 $PACOTE/tools/attach/attach.py <arquivo.pdf> --card <id> \
     --comentario "<o que é>"
   ```
   Ela verifica por ida e volta — sobe, baixa o que o servidor guardou, compara
   o hash — e **não vincula nada ao card se os bytes não baterem**. Isso existe
   porque um upload pode devolver 200 e guardar arquivo corrompido: `az rest
   --body "@arquivo"` trata binário como texto e sobe base64, o card mostra o
   anexo, e o PDF não abre. Só se descobre quando alguém tenta ler.
4. 
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
5. Chame `elcamargo-activity-management` para commitar — ela delega ao
   gerenciador de Git do projeto e não mexe no estado da atividade, que é seu.
6. Avance e entregue o próximo step:
   ```bash
   python3 $F avancar <id> --nota "<N pontos, M bloqueiam>"
   ```

## A entrega

Termine imprimindo o comando seguinte, pronto para rodar:

```
Step {n} concluído. {resumo em uma linha}

Próximo:
    /{proxima-skill} {id}
```

**Rode-o você não.** Quem dispara é o usuário, que assim vê a saída desta etapa
antes de gastar a próxima — e consegue apontar onde a cadeia quebrou quando ela
quebra.

**O próximo step roda em contexto novo**, sessão nova ou subagente, nunca esta
mesma janela. É por isso que o handoff é por arquivo: o step seguinte precisa
ler o artefato, não o raciocínio de quem o escreveu. Contexto herdado faz o
modelo responder ao próprio rastro em vez de responder à especificação.


## O relatório que volta ao analista

É o entregável mais importante deste step. Ele precisa dizer, nesta ordem:

1. A conclusão, numa frase — quantos pontos bloqueiam a especificação.
2. A tabela dos pontos: item, severidade, **quem decide**.
3. O detalhe de cada ponto que bloqueia, com a citação do trecho ambíguo.
4. As perguntas objetivas que precisam de resposta.

Separe o que a engenharia resolve do que só o negócio decide. Um ponto de
cardinalidade comercial não é decisão técnica, e apresentá-lo como se fosse
transfere para o time uma escolha que não é dele.

## Você não terminou enquanto o subagente não voltar

Disparar é o começo do step; consolidar é o trabalho dele. Se o subagente não
retornar, **nomeie-o**, declare a entrega incompleta naquela dimensão, e entregue
o que você tem. O silêncio dele nunca conta como aprovação.

Ver `FLOW.md`, *Disparar não é terminar*.

## Nunca faça

- Especificar tabela, endpoint, componente, migration ou tela.
- Marcar como resolvida uma ambiguidade que você decidiu sozinho — registre a
  pendência com os seis campos e diga quem decide.
- Abrir pendência sem opções e sem recomendação. Não recomendar parece
  neutralidade e é omissão: você leu o documento inteiro, quem decide não.
- Alterar o documento de negócio de origem.
- Pular a conferência por comando, ou o subagente de completude.
- Afirmar o que uma tela, um teste ou um trecho de código faz sem ter
  verificado — e sem dizer como verificou.
- Executar o próximo step.
