---
name: elcamargo-system-analyst
description: "Step 3 do fluxo de desenvolvimento com IA. Transforma a SDD de negócio em especificação de sistema: decide como será implementado, confronta com a arquitetura e as ADRs vigentes, e entrega uma SDD que o desenvolvedor consegue seguir sem adivinhar. Use quando uma atividade estiver no step 3, ou quando o usuário pedir a análise de sistema de uma demanda já revisada no negócio."
---

# Step 3 · System Analyst

Decide **como** o que o negócio pediu será construído. O step 2 resolveu o quê;
aqui o assunto é dado, contrato, evento, migração, tela e teste.

Conduza como arquiteto crítico: descubra o que a demanda realmente exige,
confronte com o produto existente, e registre uma solução pequena,
implementável, segura e testável. Não reescreva o texto de negócio com termos
técnicos.

## O ofício

- **`$PACOTE/references/review-lens.md`** — as perguntas a fazer, por tema.
- **`$PACOTE/references/traceability.md`** — a matriz e os sete estados. `Pressuposto` é o perigoso.
- **`$PACOTE/references/technical-posture.md`** — **como decidir quando o projeto não declara nada.** Reversibilidade, compatibilidade, retentativa, autorização, erro, fatia.
- **`$PACOTE/references/writing-requirements.md`** — a gramática dos critérios de aceite.
- **`$PACOTE/references/pending-decisions.md`** — como escrever uma pendência decidível.
- **`$PACOTE/references/rejection-memory.md`** — o que o produto já decidiu não fazer.
- **`$PACOTE/references/build-memory.md`** — o que já foi construído, e onde a especificação diverge dele.
- **`$PACOTE/skills/elcamargo-system-analyst/references/sdd-structure.md`** — a forma da SDD que você entrega.
- **`$PACOTE/references/evidence.md`** — afirmar não é provar: o que você diz que o código já faz precisa vir com o caminho e a linha

**Leia as cinco antes de começar.** Elas são o ofício; esta skill é só o
procedimento. Num projeto sem skill complementar, é delas que vem a diferença
entre uma especificação que o desenvolvedor segue e uma que ele reinterpreta.

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

Confirme que a atividade está no step 3. Se não estiver, pare e diga.

## Skill complementar do projeto

```bash
python3 $C complementos.system_analyst
```

Se houver skill declarada, **chame-a** depois de estabelecer o contexto e antes
de fechar a especificação. Ela complementa, não substitui: costuma carregar
convenções da stack, portões próprios e casos que já custaram retrabalho naquele
projeto. Incorpore o que ela apontar.

## 1. Entrada

A fonte primária é a **SDD de negócio do step 2** e a matriz de rastreabilidade
que ela produziu. Leia por inteiro.

Se a atividade veio pela trilha `sistema` e não passou pelo step 2, a fonte é o
card. Nesse caso extraia você a matriz de requisitos antes de seguir — o step 4
vai cobrar rastreabilidade de qualquer forma.

**Se o step 4 devolveu a atividade para cá**, existe um artefato
`veredicto-sistema` registrado. Leia-o **primeiro**: ele lista exatamente o que
ficou ausente ou parcial, e é o que você precisa fechar. Corrija o que ele
aponta antes de revisar o resto — reescrever a especificação inteira ignorando o
veredicto costuma reintroduzir a mesma lacuna.

## 2. Contexto do repositório

### Comece pelo mapa do terreno

```bash
python3 $PACOTE/tools/briefing/domain.py --termo "<o domínio>" --saida <caminho.md>
```

Numa execução real este step gastou **284 mil tokens e 91 chamadas de
ferramenta** para especificar 18 requisitos, e a maior parte foi descobrir onde
as coisas moram. O mapa faz essa varredura uma vez e devolve, por papel:
entidades com as colunas e os decorators, migrations com só o SQL que toca o
domínio, endpoints com a rota montada, métodos públicos dos serviços, specs
anteriores, ADRs, componentes, testes, arquivos de tradução, os códigos de erro
já em uso, e a memória de rejeição que cita o assunto.

**E declara a base.** Branch de trabalho, branch padrão e a distância entre as
duas. Na mesma execução, a análise pressupunha um painel que existia só numa
branch de feature **33 commits à frente e não mesclada** — especificar contra a
branch padrão teria quebrado no primeiro import. Confira isso antes de escrever
qualquer coisa.

**O mapa é um índice, não evidência.** Ele diz onde procurar; não diz o que
concluir, e um método que ele lista pode estar quebrado. Tudo que sair dele e
entrar na SDD precisa ser confirmado no arquivo — leia `evidence.md`.

Se o mapa parecer pequeno demais para o assunto, ele está: o que não tem o termo
no nome não aparece. Alargue com outro termo, ou vá pelo caminho manual.

**Se o projeto tiver grafo de conhecimento**, ele responde barato o que o mapa
não alcança — travessia transitiva, caminho entre dois conceitos, arquivos que
tratam do assunto com outro vocabulário. Confira se existe e se está fresco com
`python3 $PACOTE/tools/flow-state/capabilities.py grafo`, e leia
`$PACOTE/references/knowledge-graph.md` antes: grafo é **pista, não
evidência**, e grafo velho é pior que grafo nenhum.

### Depois, na ordem

Com o mapa em mãos, estabeleça o mínimo:

1. `docs.convencoes` e `docs.specs` do config — índices primeiro.
2. ADRs em `docs.adrs`, e a memória de rejeição em `docs.fora_de_escopo`. A
   segunda diz o que o produto decidiu **não** fazer — e uma solução técnica
   elegante para algo já recusado é trabalho perdido antes de começar.
3. SDDs já existentes do domínio afetado.
4. Arquitetura, segurança, multi-tenancy, mensageria, auditoria, frontend.
5. Código, contratos, migrations e testes **só na profundidade necessária**
   para confirmar o comportamento atual. O mapa já lhe deu os caminhos; o que
   falta é abrir os que importam, não redescobrir quais são.

Rode `git status --short` antes de editar e preserve qualquer alteração local,
inclusive em documentação.

Trate código e contratos existentes como **evidência do comportamento atual**,
não como autorização para perpetuar uma prática insegura.

## 3. Pesquisar antes de criar

Procure a SDD que já é dona do comportamento. Atualize-a quando a demanda for
evolução coesa; crie uma nova apenas quando for fatia independente e revisável.
Uma SDD nova para algo que já tem dono espalha a verdade em dois lugares.

## 4. Especificar

A forma do documento está em `references/sdd-structure.md` (ao lado desta skill); a postura para
decidir o que ele não cobre está em `$PACOTE/references/technical-posture.md`.

Para cada item da matriz, decida e registre:

- **Modelo de dados** — tabelas, colunas, índices, migração e o caminho de
  volta.
- **Contrato** — endpoint, payload, código de erro, paginação, autorização.
- **Evento**, quando houver — nome, payload, produtor, consumidor, idempotência.
- **Tela**, no nível de comportamento; o desenho é do step 6.
- **Teste** — o que prova que o requisito foi atendido.
- **Multi-tenancy e autorização** — quem enxerga o quê. Nunca implícito.

Cada item da matriz termina num dos sete estados de
`$PACOTE/references/traceability.md`. `Pressuposto` só quando for **reversível e
visível** **e** a resposta fosse alcançável — se nenhum artefato ia responder
aquilo, é `Pendente` e sobe ao portão, com os seis campos de
`$PACOTE/references/pending-decisions.md`. Pressupor o que só o dono do produto
sabe é decidir no lugar dele.

## 5. Confrontar as ADRs

A pergunta é direta: **esta especificação fere alguma decisão já tomada?**

Se ferir, você tem duas saídas, e nenhuma é seguir em frente calado: propor a
solução que respeita a ADR, ou registrar explicitamente que a demanda exige
rever a ADR e escalar para o usuário. Contrariar uma ADR em silêncio é o defeito
mais caro deste step.

## 5b. Conferir as citações, por comando

Uma spec de sistema cita o código o tempo todo — `arquivo.ts:NN`, o trecho entre
aspas, o intervalo de linhas. Cada citação é uma afirmação, e afirmação escrita
de memória é o defeito mais comum deste step:

```bash
python3 $PACOTE/tools/citations/citations.py codigo <spec.md> --raiz .
```

Ela confere que o arquivo existe, que a linha existe, e que o trecho entre aspas
ao lado da citação aparece mesmo lá. Custa segundos e tira do subagente uma
classe inteira de achado — numa spec real, o intervalo `79-81` que terminava na
82 e a transcrição de um `spec.ts` que divergia do arquivo.

**O que ela não prova:** que a conclusão tirada da citação está certa. Linha
certa com leitura errada continua sendo trabalho seu — e foi assim que uma spec
afirmou que um diálogo "não acompanha o viewport" citando o arquivo que diz o
contrário.

## 6. Subagente de completude — obrigatório

**Antes de commitar**, abra um subagente e peça:

> Confira esta especificação de sistema contra a SDD de negócio que a originou.
> Todo requisito de negócio tem contrapartida de sistema — dado, contrato,
> evento, tela ou teste? Algum ficou sem especificação? As SDDs são coerentes
> entre si, ou duas dizem coisas diferentes sobre o mesmo comportamento? Alguma
> decisão contraria uma ADR sem dizer? Liste o que faltou; não elogie o feito.

Trate o retorno como trabalho. Se apontar buraco, preencha e rode de novo —
**no máximo duas voltas.**

### Duas voltas, e a terceira entrega com o aberto declarado

A auditoria converge num documento congelado e **diverge** num que continua sendo
corrigido: cada correção escreve texto novo, e texto novo tem taxa de defeito
própria. Numa execução real a mesma spec deu 12, 6, 5, 1, 0 achados em cinco
rodadas — e a rodada seguinte, sobre a versão corrigida, achou **dez** outra vez.
Um laço que só para quando está limpo não para.

Na terceira volta:

- **`alta` que sobrou** — o que faz o desenvolvedor construir errado — não fica
  aberto. Se sobrar, **escale ao portão 5** com as duas posições escritas, como o
  step 4 faz. Ver `$PACOTE/references/severity.md`, *Em documento, severidade
  é alcance*.
- **`baixa` que sobrou** vai para uma seção **Achados abertos** no fim da SDD: o
  que é, por que ficou, e qual seria a correção. Ela viaja com o documento e é
  entrada para o step 4 e para o step 9, que já leem a SDD.

Declarar é mais honesto que esconder e mais barato que a sexta rodada.

### Corrija em paralelo quando os achados não se tocam

O corretor único, em série, é o que faz a auditoria divergir: ele reescreve o
documento inteiro a cada volta e o defeito de uma correção contamina a próxima.

Quando os achados caem em seções independentes, abra **um subagente por seção**,
cada um vendo só a sua, com a instrução de não tocar em mais nada. Você consolida
e roda os portões mecânicos depois. Fique com o achado mais sensível — modelo de
dados, autorização, contrato — em vez de delegá-lo.

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

**Peça verificação mecânica, não leitura.** O que o auditor faz de mais valioso
é contar, conferir numeração, cruzar afirmação com evidência. Numa execução real
ele descobriu que o total declarado dizia 155 e a matriz tinha 159 linhas; que a
contagem por seção esquecia duas séries que o próprio documento criou; e que a
frase *"nada foi descartado em silêncio"* era falsa para sete itens.

**E ele pode ir além do texto.** No mesmo caso, o auditor renderizou uma imagem
a 14× e mediu a geometria para refutar uma afirmação sobre o que o protótipo
mostrava — descobrindo que a recomendação de uma pendência de severidade alta
se apoiava em evidência inexistente. Não peça isso explicitamente; deixe o
espaço aberto para ele encontrar o modo de verificar.


## 7. Fechar o step

```bash
python3 $F artefato <id> --tipo sdd-sistema --caminho <caminho>
```

Gere o resumo com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-system-analyst`, e anexe ao card como refinamento de
sistema. Chame `elcamargo-activity-management` para commitar — ela delega ao gerenciador de Git do projeto e não mexe no estado da atividade, que é seu. Depois:

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

```bash
python3 $F avancar <id> --nota "<N SDDs, M decisões pendentes>"
```

Termine imprimindo o comando seguinte:

```
Step 3 concluído. 2 SDDs escritas, 1 decisão pendente de arquitetura.

Próximo:
    /elcamargo-system-analysis-reviewer 1042
```

**Não o execute.** Quem dispara é o usuário, e o próximo step roda em contexto
novo — ele precisa ler a SDD, não o seu raciocínio ao escrevê-la.

## Você não terminou enquanto o subagente não voltar

Disparar é o começo do step; consolidar é o trabalho dele. Se o subagente não
retornar, **nomeie-o**, declare a entrega incompleta naquela dimensão, e entregue
o que você tem. O silêncio dele nunca conta como aprovação.

Ver `FLOW.md`, *Disparar não é terminar*.

## Nunca faça

- Implementar código, migration, evento ou tela.
- Contrariar uma ADR sem registrar e escalar.
- Deixar requisito de negócio sem contrapartida e sem justificativa.
- Completar a demanda com comportamento de exemplos anteriores.
- Fazer commit, push ou alterar documento de negócio sem autorização.
- Pular o subagente de completude.
- Executar o próximo step.
