# Evidência: afirmar não é provar

Quem produz afirma. Quem revisa prova. Foi o desequilíbrio que a POC mediu, e é
o que esta referência corrige: **a disciplina de evidência vale para os dois
lados.**

## O que aconteceu

Na revisão de uma entrega, o revisor de qualidade não acreditou que o filtro
funcionava. Construiu uma sonda com dados falsos, rodou, e mostrou a saída. O
filtro não honrava o cliente. Ninguém pediu que ele fizesse isso — a doutrina
não previa sonda nenhuma.

Na mesma execução, a etapa de análise afirmou o que uma tela mostrava, e
recomendou uma mudança apoiada nessa leitura. **A tela não mostrava aquilo.**
Ninguém tinha medido; a afirmação veio de suposição sobre como a tela
provavelmente era. A recomendação foi para o relatório com severidade alta.

A diferença entre os dois não é competência. É que um tinha o hábito de provar e
o outro tinha o hábito de concluir.

## A regra

**Toda afirmação sobre um artefato que você não criou precisa vir com o modo
como você a verificou.**

Não é sobre desconfiar de você mesmo. É que uma afirmação sem verificação e uma
afirmação com verificação são **indistinguíveis no texto** — as duas soam
igualmente seguras. Quem lê depois não tem como saber qual é qual, e a errada
viaja com a mesma força da certa.

## A frase nova que a correção traz junto

Corrigir um defeito quase nunca é trocar uma palavra. É escrever um parágrafo
explicando por que a correção é a certa — e **esse parágrafo é código novo, não
revisado por ninguém.**

Numa execução real, uma auditoria acompanhou quatro rodadas de correção da mesma
especificação e isolou o padrão:

| Rodada | O que falhou |
| --- | --- |
| 2ª | Um defeito foi "corrigido" citando o relatório do revisor, **sem abrir o teste**. A correção estava errada, e o texto original estava mais certo |
| 3ª | O trecho reeditado fechou. O furo migrou para as **tabelas** que ninguém revisitou |
| 4ª | O trecho no terceiro toque fechou inteiro. O defeito estava na **subseção escrita naquela rodada**, em quatro afirmações sobre componentes: três verificadas, uma não |

O diagnóstico dela, verbatim: *"re-editar o mesmo trecho está funcionando — o que
falha é a prosa nova escrita para justificar a correção"*.

E a afirmação que falhou era desmentida por um documento **a dezesseis linhas**
do trecho que a própria correção citava.

**A regra: `afirmar não é provar` vale para cada frase nova que a correção traz
junto, não só para o defeito corrigido.** Abra o arquivo antes de escrever a
justificativa. A tentação é o inverso — o defeito já foi localizado, a explicação
"se sabe" —, e é exatamente aí que a memória substitui a leitura.

Um sinal barato: se a correção acrescentou um parágrafo com três ou mais
afirmações sobre código, conte quantas você abriu. Se não forem todas, você
achou o próximo defeito.

## O que conta como evidência

| Tipo | Como se apresenta |
| --- | --- |
| Comando | a linha exata e a saída, colada |
| Arquivo | `caminho:linha`, com o trecho |
| Medição | o número e como foi obtido |
| Sonda | o código que você escreveu, e o que ele imprimiu |
| Ausência | o comando de busca que voltou vazio — `grep -rn "x" src/` sem resultado |

**Ausência é a mais esquecida.** "Não existe permissão para isto" é uma
afirmação forte, e prová-la é fácil: mostre a busca que não achou. Sem isso, é
indistinguível de "eu não procurei".

## O que não conta

- "parece que", "provavelmente", "deve ser"
- "o padrão do projeto sugere" — sugere onde? cite
- "o componente X normalmente faz Y" — normalmente não é neste caso
- concordância de outra pessoa ou de outro agente
- a sua própria conclusão anterior, repetida

## Quando você não consegue verificar

Diga. **Uma pendência declarada vale mais que uma conclusão inventada.**

> Não consegui confirmar se o filtro considera categoria: o teste que existe não
> exercita esse caminho e eu não tinha como rodar a aplicação. Se considerar,
> RN-09 está atendida; se não, é defeito.

Isso é trabalho útil. Já a mesma frase sem a ressalva é uma armadilha para quem
vier depois.

## Como escrever

Três partes, na ordem:

1. **A afirmação**, em uma linha.
2. **A evidência**, com o comando, o caminho ou o número.
3. **O que a derrubaria** — a observação que provaria você errado.

A terceira é a que separa análise de opinião. Se você não consegue dizer o que
mudaria de ideia, você não está afirmando um fato: está declarando uma
preferência.

> **O painel não filtra por cliente.**
> `orders.service.ts:214` — `this.orders.find({ where: { clientId } })`
> monta o `where` sem `clientId` quando o parâmetro chega vazio, e
> `orders.service.spec.ts:88` passa um mock que ignora argumentos, então
> o teste verde não prova nada.
> **Me derrubaria:** um filtro aplicado depois, na camada de saída — procurei em
> `controller` e `interceptor` e não achei.

## O caso especial: prova que o teste prova

Um teste verde não é evidência de comportamento correto. Ele é evidência de que
**aquele teste** passou.

Na POC, onze testes verdes conviviam com dois vazamentos entre clientes, porque
os mocks devolviam a mesma coisa independentemente dos argumentos recebidos.
Antes de citar um teste como prova, confira se ele **poderia falhar**: mude o
comportamento de propósito e veja se ele fica vermelho. Um teste que passa dos
dois jeitos não está testando.
