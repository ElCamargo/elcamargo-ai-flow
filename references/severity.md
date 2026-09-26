# Severidade, do mesmo jeito em todo lugar

Cinco revisores em paralelo, cada um com uma escala própria, produzem uma lista
que ninguém consegue priorizar. Esta é a escala do fluxo, e todos usam a mesma.

| Severidade | Critério | O que acontece |
| --- | --- | --- |
| **bloqueia** | Vai a produção e alguém perde dado, acesso indevido, ou o requisito não é atendido | O step não passa. Volta para correção. |
| **alta** | Defeito real, com caminho de falha demonstrável, mas contornável ou de baixo alcance | O step não passa. Volta para correção. |
| **baixa** | Melhoria que não tem caminho de falha: legibilidade, duplicação pequena, teste que poderia ser mais forte | Registrado. Não bloqueia. |

Só **baixa** deixa o step passar. Se você hesitar entre `alta` e `baixa`,
pergunte: *existe entrada concreta que produz resultado errado?* Se existe, é
`alta` no mínimo.

## Em documento, severidade é alcance — não é "está errado"

Revisando **código**, a pergunta acima basta: a entrada existe ou não existe.
Revisando **documento** — especificação, análise, veredicto —, ela não basta,
porque quase tudo num documento longo "está errado" de algum jeito, e a escala
inteira desaba para `alta`.

A pergunta certa é outra: **isto chega ao desenvolvedor como instrução?**

| | `alta` | `baixa` |
| --- | --- | --- |
| O quê | Quem implementar seguindo o documento **constrói errado** | O texto está errado e quem implementa **não se engana** |
| Exemplo real | O inventário de rota declara quatro estados, e os dois que a especificação manda medir não estão lá: o gate passa verde sem medir o diálogo | A célula de custo diz "15 baselines" em negrito e "21" três frases abaixo, na mesma célula |
| Por quê | Nenhuma leitura salva: a informação que faltava não está em lugar nenhum | O leitor tropeça, olha a linha ao lado e segue |

Numa especificação real, sete rodadas de auditoria produziram **33 achados, e
uns 13 alcançavam código.** Os outros vinte custaram sete horas de rodada e
teriam custado ao desenvolvedor alguns segundos de releitura.

Isso **não** é licença para deixar erro no texto. É a diferença entre o que
devolve o documento e o que viaja com ele numa lista de achados abertos. Erro de
número, citação torta e contagem que não fecha continuam sendo achado, continuam
sendo corrigidos — só não param o fluxo.

### O teste, quando você hesitar

Escreva a frase: *"o desenvolvedor lê isto e faz ___"*. Se você consegue
completar com algo errado e concreto, é `alta`. Se a frase vira *"o
desenvolvedor lê isto e percebe que está errado"*, é `baixa`.

## Procedência: como você sabe

Severidade responde **quão ruim**. Procedência responde **como eu sei**. São dois
eixos, e usar um só faz opinião e prova chegarem ao consolidador no mesmo
formato.

Todo achado declara a sua, em uma palavra:

| Procedência | O que sustenta | Exemplo |
| --- | --- | --- |
| **execução** | Você rodou e viu | O teste falhou; a tela mostrou; o comando devolveu 500 |
| **leitura** | Você leu o código e concluiu | Este `if` nunca é verdadeiro, porque a condição acima o exclui |
| **estrutural** | Padrão, contagem ou ausência | Não há teste citando este arquivo; a chave não aparece no catálogo |

### A regra que muda o resultado

**Achado `estrutural` não reprova sozinho.** Ele aponta onde olhar; não é
conclusão. "Não há teste para isto" pode significar que falta teste — ou que o
comportamento é coberto por outro, com outro nome. Promova-o a `leitura` indo
ler, ou a `execução` indo rodar. Se não der para promover, ele viaja como achado
aberto.

**Achado de `leitura` reprova**, e é a maior parte do que uma revisão produz. Mas
ele carrega o ônus do cenário concreto — ver abaixo.

**Achado de `execução` é o mais caro de produzir e o mais barato de aceitar.**
Numa revisão real, três dos nove defeitos graves **só existiam** porque uma
frente subiu a aplicação contra o servidor de verdade; nenhuma leitura os
alcançava. Quem consolida deve tratá-los assim: um `execução` que contradiz um
`leitura` derruba o `leitura`, e não o contrário.

### Vale igual quando o achado FECHA

Dizer que um defeito foi corrigido também tem procedência, e é onde a régua
costuma afrouxar:

| | |
| --- | --- |
| *"Corrigi, e o teste que reprovava agora passa"* | `execução` — fecha |
| *"Corrigi, e reli o código"* | `leitura` — fecha, com o cenário refeito |
| *"Corrigi"* | não fecha nada |

Numa execução real, um defeito foi declarado fechado e voltou pela metade: o
aviso existia, e não nomeava a categoria. O estado guardava o nome, e ninguém
lia. Fechamento por `leitura` sem refazer o cenário é o caminho mais comum para
isso.

### Onde ela vai

Na linha do achado, ao lado da severidade: `alta · execução`, `baixa ·
estrutural`. Uma palavra. Se você hesitar entre duas, é `estrutural` — a
procedência mais fraca das candidatas, porque afirmar demais é o defeito que
esta escala existe para conter.

### E o terceiro eixo

Severidade responde **quão ruim**, procedência responde **como eu sei**, e falta
**o que aconteceu com ele** — corrigido, descartado, aceito ou aberto. Está em
`outcome.md`, e é o eixo que permite contar quantos achados de uma revisão
viraram mudança.

## O teste do cenário

**Nenhum achado `bloqueia` ou `alta` é válido sem cenário concreto de falha:**
entrada específica → resultado errado observável.

"Isso pode causar problema de performance" não é cenário. "Com 500 pedidos no
escopo, a listagem faz 500 consultas — uma por linha — e o gate de 2s da RNF-01
não passa" é.

O motivo é prático: quem corrige precisa reproduzir. Um achado sem cenário custa
ao corretor o trabalho de descobrir se o defeito existe, e às vezes ele não
existe — o revisor leu errado.

## Concordância não é evidência

Não promova achado porque vários revisores o apontaram — eles leram o mesmo material com o mesmo viés. O que promove é a reprodução resistir a uma tentativa de derrubá-la.

O detalhe de como consolidar assim está na skill do step 9, que é quem consolida.

## Inflação de severidade

Marcar `bloqueia` para chamar atenção destrói a escala. Depois de duas vezes,
quem consolida passa a descontar tudo que você reporta, e o `bloqueia` de
verdade se perde junto.

Se um achado `baixa` importa muito para você, diga isso na descrição. Não mexa
na severidade.

## O que não é achado

- Preferência de estilo que o linter não cobre e o projeto não declarou.
- "Poderia ser mais elegante", "eu faria diferente".
- Defeito pré-existente que a entrega não tocou — reporte separado, marcado
  como fora do escopo, para não fazer o corretor mexer no que não é dele.
- Suspeita sem verificação. Confira antes; um falso positivo custa uma volta.
