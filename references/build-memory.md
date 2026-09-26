# O que o produto já construiu

A memória de rejeição diz o que o produto decidiu **não** fazer. Esta diz o que
ele **já fez** — e é a que mais escapa, porque parece óbvia.

## A pergunta

Não é *"isto quebra a arquitetura?"*. Essa é estreita e quase sempre a resposta é
não. A pergunta é:

> **O que desta análise já existe, e onde ela diverge do que existe?**

Uma análise de negócio raramente chega num terreno virgem. Ela costuma descrever
um módulo que o produto já tem, com outras palavras, escritas por alguém que não
leu a especificação anterior. E aí a divergência não é evolução: é **regressão
com aparência de requisito**.

## O caso que motivou isto

Uma especificação de 27 páginas descrevia a gestão de pedidos. O produto já
tinha o módulo inteiro construído e especificado — dezoito documentos.

O texto divergia do construído em **seis pontos**. Implementar ao pé da letra
causaria regressão em todos, e **três deles abriam acesso a dado hoje fechado**.

Nenhum desses seis quebrava a arquitetura. Todos passariam numa revisão que só
perguntasse "isto fere alguma ADR?".

## Como fazer

**Antes de escrever qualquer regra**, levante o que já existe sobre o assunto:

1. As especificações do domínio, pelo índice — não pelo texto da análise, que
   usa outro vocabulário.
2. O comportamento real do código nos pontos que a análise toca.
3. As decisões registradas que governam aquele comportamento.

Depois, para cada requisito da análise, classifique:

| Situação | O que fazer |
| --- | --- |
| **Já existe, e a análise descreve igual** | Confirme e siga. Não reespecifique. |
| **Já existe, e a análise descreve diferente** | **Pare.** Isto é o achado. |
| **Não existe** | É o trabalho novo. |

## A divergência é a pergunta, não a resposta

Quando a análise diverge do construído, você **não sabe** qual das duas está
certa. São duas hipóteses, e a diferença importa:

- **Pedido de mudança** — o negócio quer mudar o que existe, e sabe disso.
- **Redescrição imprecisa** — alguém escreveu de memória, sem ler o que já
  havia, e a diferença é acidental.

A segunda é muito mais comum, e a mais cara: ninguém decidiu mudar nada, e a
mudança entra assim mesmo.

Então a pergunta ao analista muda de forma. Não é *"como implementar isto"*, é:

> **"Isto é pedido de mudança, ou redescrição imprecisa do que já existe?"**

Para cada divergência, mostre lado a lado o que existe e o que o texto pede, e
diga o que se perde ao adotar o texto. Se a adoção abre acesso a dado hoje
fechado, ou remove uma restrição vigente, **isso vai na conclusão do relatório**,
não no meio.

## O que não fazer

- **Não presuma que o construído está certo.** O produto pode ter um defeito que
  a análise está corrigindo sem dizer.
- **Não presuma que a análise está certa.** É o erro simétrico, e o mais caro
  aqui.
- **Não resolva sozinho.** Divergência entre o texto e o produto é decisão de
  produto, com dono e consequência — vai para pendência, no formato dos seis
  campos.
