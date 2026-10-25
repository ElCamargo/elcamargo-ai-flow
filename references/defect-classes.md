# Classes de defeito: a revisão que aprende com o que escapou

Um defeito que passa pelo step 9 e chega ao QA, ou à produção, quase nunca é um
caso isolado. É uma **classe**: um jeito de errar que a revisão não sabe
procurar. Consertar o caso fecha um bug; sem registrar a classe, a próxima
entrega erra igual e a revisão deixa passar igual.

O registro é um arquivo markdown do **projeto**, declarado em
`docs.classes_de_defeito`. O step 9 o entrega às frentes. O step 8 o aumenta.

## O caso que pediu isto, em 30/09/2026

A sessão do app, depois do Bug 1093:

- um redirecionamento do servidor Next, montado a partir do `request.url`,
  passou pelo step 9 e chegou ao QA. Atrás do proxy, o `Location` levava o
  endereço de escuta do contêiner, e o navegador recebia 502;
- **três semanas antes, a mesma classe**: o link de um e-mail saiu com o nome
  interno do serviço (1061, achado E-01).

Duas ocorrências da mesma classe, e nenhuma frente tinha como saber que devia
procurá-la. A revisão só procura o que conhece, e não tinha onde guardar o que
aprendeu.

## O formato de uma entrada

```markdown
## <id> · <a classe, numa frase>

- **origem:** <card, bug ou achado> · <PR ou commit> · <data>
- **como aparece:** <o sintoma, e onde ele NÃO aparece — é o que explica por
  que a revisão deixou passar>
- **como conferir:** <frente> — <o que ela procura no diff, ou o comando que
  roda>
- **vale para:** <a parte do código que pode ter a classe: rota, e-mail, job…>
```

O `id` é curto e estável (`DC-01`), porque é ele que o relatório do step 9
cita. A **classe** é o jeito de errar, e não o bug: *"URL absoluta montada do
endereço do processo"*, e não *"o redirect do login dá 502"*.

**Como conferir** é a parte que faz a entrada valer alguma coisa. Uma entrada
que diz só *"cuidado com URL"* não muda o que a frente faz. Diga **qual frente**
e **o quê**: um `grep` no diff, uma ferramenta, uma passada na tela.

## O step 9: entregar às frentes

Com o registro declarado, o step 9 passa o caminho a toda frente, junto com o
dossiê. Cada frente:

1. lê as entradas cuja **frente** é ela, ou cujo **vale para** o diff alcança;
2. confere cada uma dessas, pelo **como conferir**;
3. cita no relatório as entradas que conferiu, pelo `id`, com o resultado, e as
   que não se aplicavam, numa linha.

Quem não cita o registro não diz se o olhou. *"Conferi DC-01 e DC-03; DC-02 não
se aplica, o diff não monta URL"* é auditável; silêncio não é.

**Sem o registro declarado, nada muda**: as frentes revisam como antes, e o
relatório do step 9 não finge ter conferido o que não existe.

## O step 8: acrescentar a classe

Quando uma correção conserta uma **classe**, e não só um caso, o step 8
acrescenta a entrada na mesma entrega. Isso vale para achado do step 9 e para
bug que chegou do QA ou da produção.

A pergunta para decidir é: **isto pode acontecer de novo em outro lugar do
código, escrito por outra pessoa?** Se sim, é classe.

- Não registre erro de digitação, regra de negócio mal entendida num card, ou
  qualquer coisa que o próprio teste da correção já impede de voltar.
- Registre o jeito de errar que o teste da correção **não** alcança: o próximo
  redirect, o próximo e-mail, a próxima rota.
- Não repita classe. Se ela já existe, acrescente a nova **origem** na mesma
  entrada: duas ocorrências são o que prova que a classe é real.

## O que o registro não é

- **Não é a lista de bugs.** O board já tem. Uma entrada é uma classe, e ela
  pode ter nascido de três bugs.
- **Não é regra de lint.** Quando a conferência de uma classe cabe num lint ou
  num teste, ponha lá, e a entrada passa a dizer *"coberta por <gate>"*. É a
  melhor saída que uma entrada pode ter.
- **Não é do pacote.** Mora no repositório do projeto, como o
  `docs.fora_de_escopo`: a memória de onde o produto já errou é do produto.

Classe que depende do build de produção atrás do host público, como a do
1093, tem conferência por ferramenta: `[producao]` no config e
`tools/public-origin/public_origin.py`, que a frente de execução roda. Ver
`$PACOTE/agents/elcamargo-runtime-reviewer.md`.
