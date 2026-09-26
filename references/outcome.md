# Destino: o que aconteceu com o achado

Um achado tem três eixos, e faltava o terceiro:

| Eixo | Responde | Onde está |
| --- | --- | --- |
| **Severidade** | Quão ruim é | `severity.md` |
| **Procedência** | Como eu sei | `severity.md`, *Procedência: como você sabe* |
| **Destino** | **O que aconteceu com ele** | aqui |

Sem o terceiro, uma revisão produz uma lista e nada mais. A nossa última produziu
**vinte e um achados**, e ninguém sabia quantos tinham virado mudança — não por
descuido, mas porque o destino de cada um vivia na cabeça de quem corrigiu. Numa
rotina de revisão automática de porte industrial, **94% das propostas nunca
foram tocadas**, e só se descobriu porque alguém contou.

Contar é barato. Não contar tem um custo que só aparece tarde: uma revisão que
não muda nada é indistinguível, no relatório, de uma revisão que mudou tudo.

## Os quatro destinos

Todo achado sai da revisão com **um**, e só um.

| Destino | O que significa | O que a linha precisa trazer junto |
| --- | --- | --- |
| **corrigido** | O código mudou por causa dele | A prova do fechamento — o teste que reprovava e agora passa, a tela conferida de novo, o commit |
| **descartado** | Não resistiu à tentativa de derrubá-lo | Por que caiu, com o que você mediu |
| **aceito** | É real, e alguém decidiu conviver com ele | Quem decidiu. Se bloqueia, **o portão humano que aceitou** |
| **aberto** | Ninguém fechou, e ele viaja adiante | O que ficou, e qual seria a correção |

Só isso. Não há "parcialmente corrigido": meia correção é um achado corrigido e
um achado novo, e escrever assim faz a metade que falta ter dono.

## `corrigido` exige prova, e é aqui que a régua afrouxa

Vale a mesma escala de procedência que vale ao abrir. *"Corrigi, e o teste que
reprovava agora passa"* é `execução`. *"Corrigi, e reli o código"* é `leitura`,
com o cenário refeito. **"Corrigi" não fecha nada.**

Nesta POC um defeito foi declarado fechado e voltou pela metade: o aviso de
inativação existia, e não nomeava a categoria. Fechamento por leitura sem
refazer o cenário é o caminho mais curto para isso.

## Negação não é destino

*"Não fechado"* diz o que **não** aconteceu, e some com o que aconteceu. Voltou
aberto? Virou decisão? Foi descartado?

O relatório final de uma revisão real trazia **cinco linhas assim**, e a
primeira versão da ferramenta de contagem leu as cinco como `fechado` — a taxa
de conversão subiu sozinha, para o lado que agrada. Escreva a palavra, e o
porquê ao lado.

## O descartado fica na tabela

A tentação é apagar: se caiu, não é achado, então some. Não some — por dois
motivos.

**O descarte é registro.** Sem ele, o mesmo falso positivo volta na próxima
volta e custa a mesma investigação. É o que a memória de rejeição faz para o
fluxo inteiro, e a tabela faz para a revisão.

**E é o descarte que mede a consolidação.** Consolidar é tentar derrubar: num
estudo com mandato adversarial, esse passo derrubou perto de **79%** dos
candidatos. Um relatório com vinte achados e zero descartes quase nunca
significa que os vinte eram bons; significa que o consolidador encaminhou.

Um achado apagado é indistinguível de um achado que nunca existiu, e as duas
coisas dizem coisas opostas sobre a revisão.

## Bloqueio tem duas saídas, não três

Um achado que **bloqueia** não vira `aberto`. Ou fecha, ou **escala ao portão
humano** com nome de quem decide — e aí vira `aceito`, com o portão escrito na
linha. Aceitar um bloqueio é decisão de gente; um relatório que aceita sozinho
está dando aceite no próprio trabalho.

O que fica `aberto` é `baixa`, e às vezes `alta` de documento que não alcança
código — ver `severity.md`, *Em documento, severidade é alcance*. E o que fica
aberto tem que aparecer na seção **Achados abertos**, que é o que viaja para
quem vem depois. Aberto na tabela e ausente na seção é dívida escondida, não
achado declarado.

## Uma tabela, não três

O relatório real da POC tinha toda a informação — e espalhada em três tabelas
com três vocabulários: os corrigidos sob `Situação`/`fechado`, os descartados sob
`Por que caiu`, os abertos em prosa. Cada uma legível sozinha, e nenhuma
somável com as outras.

O formato é este, e as duas últimas colunas são as que importam:

```
| # | Frente | Severidade · Procedência | Onde | O que quebra | Destino | Prova |
| A-01 | segurança | bloqueia · execução | dto.ts:44 | ... | corrigido | teste que reprovava passa |
| A-02 | código | baixa · leitura | app.tsx:12 | ... | descartado | coberto por app.spec.ts:88 |
| A-03 | negócio | alta · leitura | — | ... | aceito | portão 10: aceite condicionado |
| A-04 | qualidade | baixa · estrutural | — | ... | aberto | vira card da próxima fatia |
```

O mesmo achado pode aparecer em mais de uma volta — `aberto` na volta 1,
`corrigido` na volta 2. Mantenha as duas linhas: a contagem vale a última, e o
histórico mostra o laço funcionando.

## A conferência mecânica

```bash
python3 $PACOTE/tools/outcome/outcome.py conferir <relatorio.md> --raiz .
```

Ela reprova achado sem destino, destino escrito por negação, dois destinos na
mesma célula, `corrigido` sem nada ao lado, bloqueio aberto ou aceito sem
portão, e aberto que não está na seção que viaja. E imprime a distribuição, que
é o número que ninguém tinha.

**O que ela não faz:** dizer se a correção conserta, se o descarte era justo, ou
se o aceite foi mesmo de uma pessoa. Ela conta destinos e cobra que cada um
esteja escrito.

## O número não é meta

A taxa de conversão existe para ser **olhada**, não perseguida. Uma revisão com
100% de corrigidos pode ser excelente ou pode ser um consolidador que não
derruba nada; uma com 40% pode ser um revisor ruidoso ou um consolidador
rigoroso. O número não decide — ele obriga a pergunta a ser feita, e hoje ela
não é feita nenhuma vez.

Transformá-lo em meta produz exatamente o pior desfecho: achados fáceis
inventados para serem corrigidos, e achados difíceis não escritos.
