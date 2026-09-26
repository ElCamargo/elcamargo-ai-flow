---
name: elcamargo-development-reviewer
description: "Step 9 do fluxo de desenvolvimento com IA. Revisa a implementação em seis frentes paralelas — código, SDD implementada, negócio implementado, segurança, qualidade e execução na tela — consolida os retornos, devolve as correções ao desenvolvedor e re-revisa até fechar, com no máximo duas voltas. Use quando uma atividade estiver no step 9, ou quando o usuário pedir a revisão completa de uma entrega."
---

# Step 9 · Development Reviewer

Seis olhares independentes sobre a mesma entrega, em paralelo, e um laço de
correção que termina. Cinco leem o código; o sexto **usa o sistema**.

Você **orquestra e consolida**. Não revisa você mesmo e não corrige: quem
corrige é o step 8. Um revisor que conserta passa a validar o próprio conserto.

## O ofício

- **`$PACOTE/references/severity.md`** — a escala, o teste do cenário concreto, e o que não é achado.
- **`$PACOTE/references/evidence.md`** — o padrão de prova que você exige de cada frente, e de si mesmo ao consolidar
- **`$PACOTE/references/outcome.md`** — o que aconteceu com cada achado, e por que isso precisa ser contado
- **`$PACOTE/references/root-cause-debugging.md`** — na volta 2, exija a causa raiz escrita de cada correção: foi ela que revelou quatro defeitos introduzidos ao corrigir treze

Os seis subagentes usam as duas primeiras. É a escala comum que torna a lista
consolidada priorizável em vez de seis escalas somadas. A terceira é sua: as
frentes abrem achados, e **quem fecha é você**.

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

A trilha da atividade decide quantas frentes rodam.

## 1. As frentes

| Subagente | Pergunta | Trilha |
| --- | --- | --- |
| `elcamargo-code-reviewer` | O código é legível, sem duplicação, mantível? | todas |
| `elcamargo-quality-reviewer` | Os gates passam? O teste prova o requisito? | todas |
| `elcamargo-security-reviewer` | Autorização, tenancy, dado sensível, entrada? | todas |
| `elcamargo-implemented-sdd-reviewer` | O código faz o que a SDD de sistema diz? | completa, sistema |
| `elcamargo-implemented-business-reviewer` | O comportamento é o que o negócio pediu? | **completa** |
| `elcamargo-runtime-reviewer` | A tela faz isso **de verdade**, incluindo os estados de erro? | quando a entrega tem tela |

O critério para pular uma frente é um só: **ela não tem contra o que conferir.**

- `implemented-sdd-reviewer` precisa de `sdd-sistema`, que a trilha `curta` não
  produz.
- `implemented-business-reviewer` precisa de `sdd-negocio`, que só a trilha
  `completa` produz — a `sistema` pula o step 2.
- `security-reviewer` **roda sempre**. Ele não lê SDD nenhuma: parte da stack
  declarada e do diff. Um ajuste de uma linha numa query ou numa rota é
  exatamente onde um vazamento entre tenants entra em produção, e a trilha
  `curta` existe para ser rápida, não para ser desprotegida.
- `code-reviewer` e `quality-reviewer` também rodam sempre.
- `runtime-reviewer` roda **quando a entrega tem tela** — quando o diff toca o
  frontend, ou quando a atividade passou pelo step 6. Numa entrega só de
  backend não há o que abrir.

### A frente que usa o sistema

As outras cinco leem. Esta **usa**, e é a única que pode achar o que a leitura
não alcança.

A POC mediu o buraco: das vinte e uma execuções do fluxo, **onze terminaram
confessando *"não verifiquei em navegador"***. E os achados que mudaram uma
decisão vieram todos de quem executou — a sonda que provou a escalação de
escrita, a imagem aberta que mostrou o portão visual aprovando o próprio
defeito, a mutação que revelou onze testes verdes provando nada.

**Ambiente que não sobe não reprova entrega.** Se ela não conseguir subir a
aplicação, isso é dimensão **não coberta** — nomeie e siga, como faria com uma
frente que não respondeu. Reprovar por ambiente manda o step 8 caçar defeito que
não existe.

E o contrário também: se ela não subiu, **ninguém pode dizer que funciona**.

### Prepare o dossiê uma vez, antes de disparar

```bash
python3 $PACOTE/tools/briefing/briefing.py --base <base> --saida <caminho.md>
```

Na POC as cinco frentes gastaram 310 mil tokens para revisar 36 linhas de diff.
A maior parte não foi revisão: foi cada uma rodar o mesmo `git diff`, abrir os
mesmos arquivos, procurar quem chama o mesmo método e redescobrir como se roda o
lint deste projeto. O dossiê faz esse levantamento **uma vez**.

Ele traz: o diff — **incluindo o que ainda não foi commitado** —, a lista de
arquivos com os não rastreados marcados, os símbolos de API tocados e quem os
referencia, os portões declarados, os caminhos dos documentos e a stack.

**Ele não contém nenhum achado, de propósito.** As frentes valem porque
julgam de forma independente — foi assim que dois vazamentos entre clientes
apareceram numa entrega com onze testes verdes. Um dossiê que dissesse "atenção
ao filtro por cliente" faria as cinco olharem para o mesmo lugar, e a
independência viraria eco.

Confira a saída antes de passar adiante. Se ela avisar que o diff foi truncado,
ou que há arquivo não rastreado, isso vale para você também.

### Dispare

**Todas de uma vez, num único bloco**, para rodarem em paralelo. Cada uma
recebe: o id da atividade, **o caminho do dossiê**, e os caminhos dos artefatos
que ela precisa conferir.

Diga a cada uma que o dossiê encurta a redescoberta e **não substitui a leitura
dela** — quem parar no dossiê revisa o resumo, não a entrega.

### Você não terminou enquanto as cinco não voltarem

**Dispare e espere.** Numa execução real o orquestrador disparou as frentes e
**retornou dizendo que aguardava os retornos** — o step ficou pela metade, com
cinco revisões em curso e ninguém para consolidá-las. A frente de segurança
tinha achado uma violação de isolamento, e o achado ficou órfão.

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

Quando todas retornarem, monte uma lista única. Para cada achado:

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

Num estudo de revisão com mandato adversarial, esse passo **derrubou cerca de
79% dos achados candidatos**. Se você está promovendo quase tudo que recebe, não
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

**A frente que usa o sistema é a única que produz `execução`** — três dos nove
defeitos graves de uma revisão real só existiam porque ela subiu a aplicação. Ela
não é superior nas outras dimensões; é **desempatadora**. E a régua vale igual
quando você **fecha** um achado: fechamento por leitura sem refazer o cenário é
o caminho mais comum para o defeito voltar pela metade.

### Concordância não é evidência

Não promova achado porque três revisores o apontaram: leram o mesmo diff com o
mesmo viés, e no mesmo estudo **dez endossaram por unanimidade uma
vulnerabilidade inexistente**. O que promove é a reprodução resistir à sua
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
sem revisão **e** parece que o fluxo funcionou. Aconteceu na primeira vez que o
portão 10 devolveu.

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

   A restrição não é economia, é qualidade. Revisão em passada única supera
   revisão multi-turno em precisão medida; nas voltas seguintes os revisores
   **fabricam achados quando os erros reais acabam**, e a taxa de falso positivo
   sobe mais de 60%. Uma frente que já foi revisada e corrigida não fica mais
   verdadeira se for revisada de novo por inteiro — fica mais ruidosa.

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
3. Chame `elcamargo-activity-management` para commitar o relatório.
4. Sem achado que bloqueia ou de severidade alta → **segue para o step 10**.
5. Com achado → devolva ao step 8 e imprima o comando para o usuário:
   ```bash
   python3 $F avancar <id> --step 8 --forcar --nota "volta N: M achados, K bloqueiam"
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
`gerado_por: elcamargo-development-reviewer`, e anexe ao card. Chame a skill

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
de Git para commitar. Depois avance e termine assim:

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
    python3 $F avancar 1042 --nota "entrega aceita"
    python3 $F concluir 1042 --nota "merge liberado"
```

**O `concluir` lê a tabela *Conferências*** e recusa encerrar com conferência
exigida em aberto ou reprovada. Não é burocracia: é o que faz a obrigação
acontecer em vez de ficar escrita. Uma dimensão que não deu para cobrir sai por
`--veredicto nao-coberta`, que **passa e fica visível** no arquivo da atividade.

O step 10 é humano. **Você para aqui.** O `concluir` também é da pessoa: é o
aceite, e nenhuma skill dá aceite no próprio trabalho. Sem esses dois comandos a
atividade nunca sai de "em andamento".

## Nunca faça

- Encerrar o step com frente pendente, sem dizer qual e sem declarar a revisão
  incompleta naquela dimensão.

- Revisar você mesmo em vez de disparar os subagentes.
- Corrigir o código — devolva ao step 8.
- Re-rodar as cinco frentes quando só uma falhou.
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
