# Como escrever um requisito que dá para testar

Vale para o step 2 (regras de negócio) e o step 3 (critérios de aceite). Prosa
livre produz requisito que parece claro e admite duas implementações; gramática
fixa não.

## A forma

**QUANDO `<gatilho>` O SISTEMA DEVE `<resposta observável>`**

Cinco variações cobrem quase tudo:

| Situação | Forma |
| --- | --- |
| Sempre vale | O SISTEMA DEVE `<resposta>` |
| Ao acontecer algo | QUANDO `<gatilho>` O SISTEMA DEVE `<resposta>` |
| Enquanto num estado | ENQUANTO `<estado>` O SISTEMA DEVE `<resposta>` |
| Só se uma condição | SE `<condição>` ENTÃO O SISTEMA DEVE `<resposta>` |
| Recurso opcional | ONDE `<recurso existir>` O SISTEMA DEVE `<resposta>` |

Combináveis: *SE o cliente não tiver permissão de criação, ENTÃO QUANDO ele
abrir o painel O SISTEMA DEVE ocultar o botão Novo Pedido.*

A gramática obriga a nomear três coisas que a prosa deixa passar: **o gatilho**
(quando isso acontece?), **o sujeito** (quem faz? "deve ser validado" esconde por
quem) e a **resposta observável** (o que muda que alguém consegue ver — é o que
vira asserção de teste).

## O teste do requisito ruim

Antes de aceitar um requisito, escrito por você ou por outro, três perguntas:

- **Consigo escrever um teste que falha se isso não for feito?** Se não consigo,
  não é requisito — é intenção.
- **Duas pessoas implementariam igual?** Se admite duas leituras, é ambiguidade,
  e ambiguidade vira pendência, não pressuposto.
- **Tem número onde precisa?** "Rápido", "muitos", "grande volume" não são
  requisitos. Pergunte quanto; se ninguém souber, é pendência.

## Vícios que a gramática expõe

| Escrito assim | Problema |
| --- | --- |
| "O sistema deve tratar adequadamente os erros" | Sem gatilho, sem resposta observável |
| "Validar permissões" | Sem sujeito e sem o que acontece quando falha |
| "Sincronizar automaticamente" | Quando? Com o quê? O que se vê ao terminar? |
| "Registrar auditoria" | Registrar o quê, com qual ator, e quem consegue ler? |
| "Deveria exibir" | `deveria` é o que sobra quando a decisão não foi tomada |

## Onde não forçar

Contexto, justificativa e descrição de problema são prosa — e devem ser. A
gramática vale para **regra, requisito e critério de aceite**, que são o que
alguém vai implementar e conferir.

Forçar a forma em texto explicativo produz documento ilegível, e documento
ilegível não é lido.
