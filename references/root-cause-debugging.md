# Causa raiz antes da correção

Quem corrige sem entender troca um defeito por dois. Isso não é advertência: foi
medido nesta ferramenta, na primeira atividade que ela conduziu de ponta a ponta.

## O que aconteceu

Na atividade `crud-de-categorias`, a segunda volta do auditor — restrita às
correções da primeira, e não uma revisão nova — encontrou que **quatro defeitos
novos foram introduzidos ao corrigir** os treze originais. Dez dos treze
fecharam inteiro; três fecharam pela metade.

Sem essa segunda volta obrigatória, os quatro teriam entrado no relatório como
conserto. E o relatório teria dito verde.

Há um segundo rastro, e ele é mais revelador. Uma hora e meia depois do merge
entrou um PR de conserto com dois defeitos de tela em uso, em dez arquivos e 154
linhas — e **seis desses dez arquivos eram componentes compartilhados, fora do
escopo da entrega.** Consertar um sintoma local mexendo em peça compartilhada é
a assinatura de quem não achou a causa: a mudança vai onde o sintoma aparece, e
não onde ele nasce.

## A regra

**Nenhuma correção antes de a causa raiz estar escrita.**

Escrita, não pensada. Uma correção feita com entendimento e uma correção feita
por tentativa são **indistinguíveis no diff** — as duas trocam as mesmas linhas.
Quem lê depois não tem como saber qual é qual, e a errada viaja com a mesma
força da certa. É a mesma razão de `evidence.md`, aplicada ao conserto.

## As quatro fases, nesta ordem

**1. Colher evidência — nas fronteiras, não no meio.** Instrumente onde um
componente entrega ao outro, e compare o que saiu com o que entrou. O meio de
uma função raramente mente; a fronteira entre duas camadas mente sempre que uma
delas assume o formato da outra.

**2. Comparar com o que funciona.** Ache um caso adjacente que passa, e
pergunte o que o quebrado tem de diferente. É mais rápido que raciocinar do
zero, e produz uma hipótese que já vem com contraexemplo.

**3. Uma hipótese, e a menor mudança que a testa.** Uma por vez. Duas mudanças
simultâneas que corrigem o sintoma não dizem qual delas era necessária — e a
desnecessária fica no código para sempre, sem ninguém saber que é dispensável.

**4. Só então implementar, com teste que falha antes.** O teste que passa na
primeira execução não provou nada: ele pode estar medindo o comportamento que já
existia. Ver `test-honesty.md`.

> A ordem das quatro fases vem de doutrina pública de terceiro
> (`obra/superpowers`, MIT). Ela entrou aqui como conceito, não como instalação
> — e ganhou a quinta regra abaixo, que é nossa.

## A terceira tentativa não é uma terceira tentativa

**Depois de três tentativas falhas, pare de tentar e questione a premissa.**

Insistir na mesma direção é o sinal de que a direção está errada. Se três
hipóteses formuladas com método não fecharam, o problema quase nunca é a quarta
hipótese: é a suposição comum às três — sobre onde o dado nasce, sobre quem é o
dono daquele estado, ou sobre a camada estar onde você pensa que está.

Esta regra é irmã da regra das **duas voltas** em todo par fazedor↔revisor. As
duas dizem a mesma coisa em escalas diferentes: repetição sem convergência não é
esforço, é sintoma. Na POC, a auditoria convergiu a zero em cinco rodadas — e a
rodada seguinte, sobre o texto corrigido, achou dez outra vez.

## O que a correção precisa deixar escrito

Um achado corrigido leva três coisas, e nenhuma delas é opcional:

| O quê | Por quê |
| --- | --- |
| **A causa raiz**, em uma frase | Sem ela, `corrigido` é autodeclaração. Ver `outcome.md` |
| **A procedência** — `execução`, `leitura` ou `estrutural` | Diz como você sabe, e é o eixo que `severity.md` exige de todo achado |
| **O que derrubaria a hipótese** | Uma causa raiz que nada refutaria não é causa raiz, é narrativa |

## Os dois sinais de que você está consertando o sintoma

**A correção toca arquivo fora do escopo da atividade.** Não é proibido — às
vezes a causa está mesmo na peça compartilhada. Mas é o momento de escrever por
que, porque foi exatamente essa a forma dos dois defeitos que escaparam.

**A correção precisa de um parágrafo para se justificar.** Re-editar o trecho
funciona; o que falha é a prosa nova escrita para explicar. Esse parágrafo é
**código novo que ninguém revisou** — e numa rodada medida, a afirmação errada
dele era desmentida por um documento a dezesseis linhas do trecho citado.

## O que isto NÃO prova

**Não prova que a causa raiz declarada é a certa.** Uma causa plausível e errada
tem exatamente a mesma forma de uma certa — é a família de falso que a lente de
honestidade produziu três vezes contra o repositório real, e nas três os achados
eram legítimos e a leitura estava errada. A causa raiz escrita é **auditável**,
que é diferente de correta.

**Não substitui o teste.** Causa raiz escrita com teste ausente continua sendo
afirmação. Ela torna a afirmação conferível, não verdadeira.

**Não é licença para investigar sem limite.** A regra das três tentativas existe
para o lado oposto: o custo de procurar também é custo. Na atividade medida,
especificar e revisar a especificação custaram **2,3× mais** que construir — e
investigação sem trava é a versão dessa conta aplicada ao conserto.
