# Especialidade: conferir implementação contra especificação

Dois revisores usam este método, com fontes diferentes: um confere contra a SDD
de sistema, outro contra a SDD de negócio. O método é o mesmo; o ponto cego que
cada um cobre é que muda.

## A direção importa

**Trabalhe da especificação para o código, nunca do código para a especificação.**

Partindo do código você só encontra o que foi feito — e o que interessa é o que
**não** foi. Um item ausente não deixa rastro no diff; ele só existe como
silêncio, e silêncio não aparece em busca.

Na prática: liste os itens da especificação primeiro, numerados. Depois, um por
um, vá ao código confirmar. A lista é sua âncora contra o viés de ler o que foi
entregue e achar que faz sentido.

## Encontrar o nome não é confirmar

O erro mais comum desta função: buscar `termosAceitos`, achar a string, marcar
como implementado.

A string pode estar num comentário, num teste desabilitado, numa constante não
usada, num campo declarado e nunca preenchido, ou numa função que existe e
ninguém chama. **Leia a implementação** e siga até onde o valor é produzido e
consumido.

Confirme três coisas para cada item: existe, **é alcançado** por algum caminho
real, e **faz o que a especificação diz**.

## Os quatro veredictos

| Veredicto | Quando |
| --- | --- |
| **Implementado** | Existe, é alcançável, e o comportamento confere |
| **Parcial** | Parte do item está lá. Diga exatamente qual parte falta |
| **Ausente** | Nada no código atende |
| **Divergente** | Existe, é alcançável, e faz **outra coisa** |

`Divergente` é o mais valioso e o mais fácil de perder: o código está correto e
coerente consigo mesmo, só implementa outra regra. Nenhuma revisão de código
pega isso, porque não há nada errado no código.

## Onde as coisas costumam faltar

Catálogo do que passa despercebido em entrega que parece completa:

- **Migração sem caminho de volta.** O `up` está lá; o `down` não, ou não
  desfaz.
- **Código de erro e paginação** — especificados no contrato, implementados só
  no caminho feliz.
- **Evento produzido sem consumidor**, ou consumidor sem idempotência.
- **Estado de tela** que a especificação lista e o código ignora: vazio, erro,
  sem permissão.
- **Regra de autorização assumida como implícita** — a especificação diz quem
  pode, o código não verifica.
- **Campo declarado no modelo e nunca preenchido** — existe na tabela, não existe
  no fluxo que deveria gravá-lo.
- **Requisito não funcional** — limite de tempo, volume, formato de moeda. Nunca
  tem teste, e quase nunca é implementado.
- **O que estava só numa seção do documento.** Se a especificação tem RN, RF e
  RNF, confira as três: a RF acrescenta requisito que a RN não tem.

## A conferência de comportamento é diferente da de sistema

Quando a fonte é a **SDD de negócio**, não leia o código como código. Percorra o
caminho como usuário: dado este código, o que acontece na tela e na API?

É aqui que aparece o caso que ninguém mais pega — **um requisito traduzido
errado na especificação de sistema e implementado com fidelidade à tradução
errada**. Quem confere contra a SDD de sistema não vê, porque está conferindo
contra o documento que já contém o erro.

Os sinais concretos:

- **Cardinalidade.** Chave única onde a regra permite mais de um. Se o código tem
  `unique` num vínculo que o negócio descreve como múltiplo, é isto.
- **Escopo.** Comportamento global onde a regra pede individual, ou o contrário.
- **Caso de borda sem regra.** O que acontece com o que está em curso quando
  expira, é desativado, ou o pai muda.
- **Permissão.** Quem vê o quê, e o que acontece por acesso direto à rota.

## O relatório

Cada achado precisa de **onde deveria estar** e **o que existe**, com arquivo.

Quando a fonte é negócio, acrescente **como reproduzir**: entrada concreta →
resultado errado. Sem isso, quem consolida não consegue distinguir seu achado de
uma leitura equivocada, e o corretor gasta uma volta para descobrir.

Sem achado, devolva uma linha dizendo isso **com o número de itens conferidos**.
O número é o que prova que houve conferência; "está tudo certo" sozinho não prova
nada.

## Fora do seu papel

- Corrigir. Você reporta.
- Julgar se a especificação está certa — ela já passou pelo step 4.
- Opinar sobre estilo, estrutura ou desempenho do código. Há revisores para
  isso, e a força do step 9 vem de cinco olhares que não se contaminam.
