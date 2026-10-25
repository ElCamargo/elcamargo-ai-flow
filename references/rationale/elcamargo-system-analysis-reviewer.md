# Rationale — Step 4 · System Analysis Reviewer

Esta é a explicação da skill `elcamargo-system-analysis-reviewer` (step 4), não instrução. As regras ficam em `SKILL.md`; aqui ficam a história, os incidentes e os números que as sustentam.

## Por que este step existe, se o step 3 já se auto-revisa

Lentes diferentes, e nenhuma substitui a outra:

- O subagente do step 3 pergunta *"eu fiz tudo que essa skill deveria fazer?"* —
  olha para a própria saída, e herda os pontos cegos de quem a produziu.
- Você pergunta *"os dois documentos fecham entre si?"* — olha para os dois, sem
  ter participado da escrita de nenhum.

Um autor conferindo o próprio trabalho não encontra o requisito que ele nunca
percebeu que existia.

## Onde a ferramenta mora, e por que três lugares

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
```

### Por que você não pode herdar a matriz

Nada, sozinha. Ela prova quando **outra pessoa a reconstrói do zero e chega ao
mesmo lugar** — é por isso que o step 4 é proibido de herdar a matriz do step 2.
Duas listas independentes que divergem é informação. Uma lista copiada é
cerimônia.

## 4. Veredicto — o número medido

Numa execução real, sete rodadas de revisão produziram 33 achados de coerência, e
**uns 13 alcançavam código**. Os outros vinte devolveram a especificação e
custaram sete horas — pelo erro de tratar "está errado no texto" como se fosse
"chega ao desenvolvedor como instrução".

## Quando parar de devolver — o exemplo

Terceira reprovação não é revisão, é sinal de que falta uma decisão que nem você
nem o step 3 podem tomar. Numa execução real foi uma pergunta de arquitetura —
decidir dentro ou fora da transação. O step 3 escolheu, você mostrou que a
escolha não tinha chegado a duas seções, e uma quarta volta só produziria a
mesma discussão com outras palavras.
