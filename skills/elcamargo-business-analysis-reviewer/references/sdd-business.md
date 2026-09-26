# A forma de uma SDD de negócio

Ela responde **o que o produto deve fazer**, resolvido. Não é a análise recebida
reescrita: é a análise depois de você ter tirado as ambiguidades, fechado os
buracos e marcado o que só o negócio decide.

O critério de pronto: **o step 3 consegue especificar o sistema a partir dela sem
voltar ao documento original.**

Se você precisa dizer "consulte a análise original para o detalhe X", esse
detalhe deveria estar aqui.

## Núcleo

1. **Identificação** — código, título, status, card de origem, documentos e
   anexos lidos (com data e versão de cada um), SDDs de negócio relacionadas.
2. **Problema** — o que dói hoje, para quem, e com que frequência. Uma
   especificação que começa pela solução esconde se ela resolve algo.
3. **Resultado esperado** — o que passa a ser possível, observável de fora. E
   **o que explicitamente não muda** — essa linha evita metade do retrabalho.
4. **Atores** — quem inicia, vê, altera, aprova, é notificado, dá suporte. Papel
   por papel, não "o usuário".
5. **Glossário** — todo termo do domínio que aparece na especificação, definido
   uma vez. Se "pedido", "entrega" e "remessa" significam coisas diferentes para
   o negócio e para o sistema, é aqui que se resolve.

## Comportamento

6. **Regras** — numeradas, cada uma com origem rastreável (`RN-04 → análise
   p.12`). Uma regra por item; regra composta vira duas. Escreva no imperativo,
   sem "deveria" — `deveria` é o que sobra quando a decisão não foi tomada.
7. **Estados e transições** — o ciclo de vida do que a demanda cria ou muda.
   Para cada transição: quem dispara, o que exige, o que acontece com o que
   está em curso. Um diagrama quando o texto não fecha.
8. **Fluxos** — principal e alternassets, passo a passo. Um fluxo descrito por
   resultado ("o sistema vincula o participante") não é fluxo: descreva os
   passos, as decisões e as bifurcações.
9. **Casos de borda** — a lista que a análise raramente traz. No mínimo:
   vazio, primeiro uso, limite atingido, expiração, desativação, mudança no
   item pai, e o que acontece com quem estava no meio do processo.
10. **Permissões** — quem pode o quê, em linguagem de negócio. "Só o
    administrador vê o saldo dos outros clientes" é regra de negócio, não
    detalhe técnico.

## Fronteiras

11. **Escopo** — a fatia. **Fora de escopo**, item a item, com o motivo e para
    onde foi. Sem essa lista, tudo que você não especificou parece esquecimento.
12. **Dependências** — de outra atividade, de decisão externa, de dado que ainda
    não existe.
13. **Impacto no que existe** — que comportamento atual muda, e quem sente. Se
    a mudança é visível para o usuário final, diga como ele fica sabendo.

## Verificação

14. **Critérios de aceite** em Dado/Quando/Então, um por regra relevante,
    cobrindo o caminho de erro e o de permissão negada — não só o feliz.
15. **Matriz de rastreabilidade** — todo item da análise original, com o estado
    de `traceability.md` e onde ele foi parar nesta SDD.
16. **Decisões pendentes** — no formato de `pending-decisions.md`, com os seis
    campos. Elas aparecem **também** na conclusão do relatório ao analista.

## O que NÃO entra

Tabela, coluna, endpoint, payload, componente, migração, índice, nome de
classe. Tudo isso é step 3.

A fronteira **não é vocabulário técnico** — é **observabilidade pelo usuário**.

O teste do vocabulário falha justamente onde importa: "a lista vazia mostra a
ação de criar o primeiro" não usa termo técnico nenhum e descreve tela; e você
**precisa** escrever isso, porque os casos de borda são item obrigatório desta
SDD. Sem o estado vazio especificado, quem implementa inventa.

O teste que funciona: **um usuário consegue observar essa diferença?**

| Frase | Onde vive |
| --- | --- |
| "O total aparece na moeda configurada para a loja" | negócio — o usuário vê |
| "Quando o filtro não encontra nada, a tela oferece limpar o filtro" | negócio — o usuário vê |
| "O nome longo é truncado com reticências, e o valor inteiro fica acessível" | negócio — o usuário vê |
| "O saldo é `decimal(18,2)` com a moeda em coluna separada" | sistema |
| "O truncamento usa o componente de texto com tooltip" | sistema |

Comportamento observável é seu, mesmo quando acontece numa tela. **Como** aquilo
é construído é do step 3.

## Durável, não precisa

Esta especificação vai ficar parada. Entre escrevê-la e implementá-la há três
portões humanos, e ela pode esperar semanas enquanto o código se move embaixo
dela.

Por isso ela nomeia **tipo, assinatura, contrato e comportamento** — e **nunca
caminho de arquivo nem número de linha**. Uma especificação que diz "altere
`orders.service.ts:214`" está errada no dia em que alguém adiciona dez linhas
acima, e ninguém percebe que envelheceu: ela continua parecendo precisa.

Nomeie a coisa, não o lugar dela. `o serviço que resolve o vínculo automático`
sobrevive a refatoração; `linha 214` não.

A regra é **oposta** para achado de revisão: ali `arquivo:linha` é exatamente o
que faz o corretor achar o problema, e o achado é consumido na mesma hora. Vida
curta pede endereço; vida longa pede nome.

## Vícios que enfraquecem a SDD

- **"O sistema deve tratar adequadamente"** — não especifica nada. Tratar como?
  Com que resultado observável?
- **"Conforme regra de negócio"** — qual? Se ela existe, cite-a; se não existe,
  é uma pendência.
- **Repetir a mesma exigência em RN, RF e CA** como se fossem três. Consolide o
  comportamento, preserve as três origens.
- **Copiar o texto da análise** sem resolver a ambiguidade que você encontrou.
  Se copiou, não revisou.
- **Adjetivo no lugar de número.** "Rápido", "muitos", "grande volume". Pergunte
  quanto, e se ninguém souber, registre como pendência.
