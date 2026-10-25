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

## Procedência e citação verificável respondem perguntas diferentes

**Procedência** responde *de onde veio isto*. **Citação verificável** responde
*isto é verdade*. Elas parecem a mesma exigência e não são — e a diferença
aparece exatamente quando você mais precisa dela, porque **a cadeia se perde**.

Medido em 18/09/2026, na sessão `acme-backoffice`: um step 4 disparou
duas subfrentes e entregou um relatório contendo as duas seções. Depois, ninguém
conseguiu estabelecer se as subfrentes chegaram a voltar ou se o agente fez o
trabalho sozinho após desistir delas — os transcritos delas não foram
encontrados, e a investigação parou por retorno decrescente.

**A entrega se sustentou assim mesmo, e não por sorte:** o veredicto nomeava
arquivo e linha, e a volta seguinte foi conferir e achou as citações reais.

Se aquele step tivesse escrito *"as citações foram conferidas e estão corretas"*
sem os endereços, não haveria como distinguir trabalho de alegação, e o defeito
viajaria com a cara de revisado.

> Quando a cadeia se perde, só a citação verificável ainda funciona.

**E ela também tem teto, e o teto tem duas faces.** Medidas no mesmo dia, em
casas diferentes:

| face | o que passa verde | onde foi medido |
| --- | --- | --- |
| **endereço errado** | a citação aponta um lugar que **existe** mas não é o da afirmação — cinco numa única regra | `acme-backoffice` |
| **conclusão errada** | o endereço é o **certo** e a conclusão tirada dele é falsa — o `V2-01`: a spec dava um achado por fechado com um `CHECK` de `varchar(64)` que **existe e faz o que diz**, mas o achado era sobre `uuid`, que normaliza hífen e chaves — **quatro grafias, não duas** | `acme-app` |

**A segunda é a pior**, porque nenhuma conferência mecânica a alcança: o portão
confirma exatamente o que promete confirmar, e a afirmação apoiada ali continua
falsa.

> **Sobre o exemplo da segunda linha, e por que ele foi trocado.** A primeira
> redação usava *"quatro dos cinco `alta`"*, de uma frase que a sessão
> `acme-app-18` mandou em 18/09 às 13:23 citando o step 4 da
> `INT-004`: *"nenhum dos cinco `alta` estava ao alcance dela — quatro moram em
> citações CORRETAS com conclusão errada"*. A citação é fiel. **Mas uma sessão
> irmã da mesma casa, horas depois, não conseguiu situar o caso** — para ela os
> quatro `alta` daquela volta eram achados **fechados**, não citações mal lidas.
> O `V2-01` acima está no lugar porque é atestado por quem o mediu. A frase
> original fica registrada aqui, com o dono e a hora, em vez de sumir: **doutrina
> apoiada em exemplo que ninguém consegue reabrir envelhece mal.**

## Medição correta com escopo menor que a afirmação

Uma terceira família, e ela não é endereço errado nem leitura errada. **A
medição existe, está correta, e cobre menos do que a frase que ela sustenta.**

Medido em 18/09/2026 pela sessão `acme-app`: uma spec afirmava
*"o que ele fecha, e foi medido — não argumentado"*, com tabela. A medição
existia e estava certa. Ela usou **uma nota em cada lado** — que é o único
arranjo em que os conjuntos de trava coincidem — e a conclusão foi escrita como
**geral**. Uma frente depois reproduziu os dois modos de falha declarados
fechados.

A conferência mecânica não alcança, a citação confere, e **a palavra "medido"
carrega autoridade que aquela medição não tinha**.

> **A pergunta que a pega:** *qual arranjo eu montei, e qual é o vizinho que eu
> não montei?*

É a pergunta mais barata deste arquivo e a que mais defende contra si mesmo: ela
se responde antes de escrever a frase, não depois de alguém reproduzir a falha. É por isso que `citations.py` promete pouco de propósito — ela confere que
o endereço existe, e **quem lê o trecho é você**.

## A âncora que sobrevive é seção mais trecho, nunca número de linha

Medido em 18/09/2026: um step corrigiu citações, o preâmbulo empurrou o arquivo
em **11 linhas**, ele reancorou — e **as linhas envelheceram de novo na edição
seguinte**.

Número de linha não sobrevive nem à sessão que o escreve, quando essa sessão está
editando o mesmo arquivo. O que sobrevive é **a seção mais um trecho literal
grep-ável**: ele se reencontra depois de qualquer deslocamento, e reencontrar é
o que a citação existe para permitir.

## O teste que pode falhar, e mesmo assim prova um caminho morto

A conferência de mutação da seção anterior pega o teste que **não pode falhar**.
Existe um segundo modo, e ela **não** o alcança: o teste é válido, fica vermelho
quando você muda o comportamento, e ainda assim prova um caminho que **a
produção nunca percorre**.

Medido em 18/09/2026, achado `A-03` da sessão `acme-backoffice`: um
teste de integração *"backoffice fora do ar responde 500"* passava. Com o
backoffice realmente derrubado, **a auditoria do guard falha antes do handler**, e
o código testado nunca roda. Teste verde, requisito citado, caminho morto.

O teste estava certo sobre si mesmo e errado sobre o sistema. Nenhuma leitura o
pegaria — nem a de código, nem a de spec, nem a conferência de mutação —, porque
todas elas partem do mesmo pressuposto que o teste: que aquele ponto é
alcançável.

**Só apareceu porque alguém derrubou o serviço de verdade em vez de simular.** É
o argumento mais forte que este pacote tem a favor da frente que **usa** o
sistema: ela é a única que não herda os pressupostos de quem escreveu o código.

**E quem foi procurar o padrão em casa declarou o que NÃO varreu.** A sessão
`acme-app` procurou testes com essa forma no repositório dela e
achou o contrário do esquecimento: `travessia-do-reenvio.integracao.ts`
documenta o risco **duas vezes**, em `:67` e `:281` — alguém já tropeçou e
escreveu. Mas ela declarou o limite junto: olhou **uma classe** de teste, a de
travessia, procurando afirmação de upstream fora do ar; **não varreu a suíte
inteira** atrás de teste cujo caminho morre antes do código sob teste.

Sem essa segunda frase, o achado viraria *"o app está limpo"* — que é o que
a medição não diz.
