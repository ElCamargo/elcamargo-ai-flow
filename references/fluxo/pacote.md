# Fluxo · O pacote nunca se impõe

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## O pacote nunca se impõe

Três garantias, e elas valem juntas:

**Você pode trabalhar sem o fluxo.** As skills só rodam quando você as invoca —
não há hook, não há gatilho automático, nenhuma delas se oferece sozinha. Ter o
pacote instalado e tocar uma atividade à mão é um modo de uso legítimo, não uma
violação.

**Você pode desligar o pacote inteiro** com `install.sh --desligar`. Ele
continua no disco e some da vista de todas as sessões.

**Você pode usar só parte dele.** `fluxo.steps` no config declara quais steps
este projeto usa. É política de projeto, não escolha por atividade — um time
onde o UX é de outra pessoa legitimamente não roda o step 6.

Desligar step é permitido, **nunca silencioso**. Desligar portão humano (5, 7,
10) ou verificação (4, 9) imprime aviso alto, e a lista do que ficou de fora vai
para o front matter da atividade, para o histórico e para todo relatório. Uma
entrega que pulou verificação diz isso na própria cara.

O motivo da trava: um fluxo com toda a cerimônia e nenhuma conferência é **pior**
que não usar fluxo nenhum, porque parece rigoroso.

## Capacidades: descubra antes de precisar

O pacote roda em máquinas diferentes, para pessoas com contas e acessos
diferentes. Uma skill que assume capacidade que não tem falha no meio da
atividade; uma que pergunta antes degrada de propósito.

```bash
python3 tools/flow-state/capabilities.py         # tudo
python3 tools/flow-state/capabilities.py figma   # uma só
```

**Nenhum "não" impede o fluxo.** Cada um tem caminho alternativo previsto:

| Capacidade | Sem ela |
| --- | --- |
| Figma acessível | Step 6 vai pelo `screen-drawer` — o outro caminho previsto, não degradação |
| Orçamento de Figma largo | Estratégia de racionamento: uma navegação, uma leitura, e para |
| ReportLab | Relatório em Markdown; o PDF só importa na fronteira com humano |
| Navegador | Protótipo sem screenshot, **dizendo** que a conferência visual não foi feita |
| Gates declarados | O `quality-reviewer` improvisa — e reporta a ausência como achado |
| Skill de Git do projeto | O step 1 assume o papel inteiro |

A regra é sempre a mesma: **degrade e diga o que não foi feito, nunca finja.**

### Ler o Figma é REST, e não MCP

A leitura do step 6 é a **API REST**, pelo `tools/figma/figma.py`, com um token
pessoal fora de todo repositório. Sem MCP, sem app desktop, sem navegador
logado. O MCP é o caminho da **escrita**, que é ação separada e nasce
desligada.

A razão não é conveniência: **`GET` não consegue escrever.** Num arquivo da
empresa, com gente trabalhando dentro, essa garantia vale mais que qualquer
comodidade — e é por isso que **o plano B nunca é o navegador**. Quando a
leitura falha, o step para, diz o que falhou, e pede export ao usuário.

Se há token é pergunta de máquina, e o pacote responde:

```bash
python3 tools/flow-state/capabilities.py figma_leitura
```

Ele cruza o que o projeto **quer** com o que a máquina **consegue**, e imprime
os comandos de leitura — ou o comando exato de instalar o que falta. Isso existe
porque a resposta anterior era `?`, escrita em nomes de tool do MCP, e uma
frente irmã leu nela que sem MCP não havia leitura. Havia.

A disciplina que continua valendo é a do **custo de contexto**: comece raso
(`paginas`), escolha o nó, e só então desça (`resumo`). Descer direto na árvore
inteira gasta numa chamada o que a atividade toda deveria gastar. Os orçamentos
por seat da tabela do MCP valem para o MCP — na REST o que limita é o que a
conta do token alcança, mais o `429` que a API devolve quando se insiste.

## Antes de abrir a atividade

Três verificações baratas, no step 1, que evitam gastar dez steps no que não
precisava de nenhum: **já foi rejeitado? já está implementado? a alegação se
confirma?**

O resultado muda a trilha, então vem antes de escolhê-la — um bug que não
reproduz não é `curta`, é pergunta ao reportador. Sem isso, a trilha `curta` vai
do step 1 ao 8 e o developer "conserta" o que ninguém confirmou estar quebrado.

A terceira tem um desfecho que se disfarça: **"não havia detalhe para tentar" é
diferente de "tentei e não reproduziu"**, e é o sinal mais forte de que falta
informação. Ver `references/check-first.md`.

## A memória de rejeição

O que o produto decidiu **não** fazer vive em `docs.fora_de_escopo` — um arquivo
por **conceito**, não por card — e é consultado antes de qualquer análise, por
conceito e não por palavra.

Ela fica no repositório do **projeto**, e não no `.agents`. É a única parte deste
pacote que sai do ferramental de propósito: decisão de produto precisa sobreviver
à troca de ferramenta, à saída de quem decidiu, e a alguém remover o `.agents`
inteiro.

Quando um pedido bate num conceito rejeitado, **nenhuma skill recusa sozinha**:
mostra a decisão antiga, com o que a mudaria, e pergunta se ainda vale. Ver
`references/rejection-memory.md`.

## Especificação é documento de vida longa

Uma SDD atravessa três portões humanos entre ser escrita e ser implementada, e
pode esperar semanas enquanto o código se move embaixo dela.

Por isso ela nomeia **tipo, contrato e comportamento**, e nunca caminho de
arquivo nem número de linha. "Altere `orders.service.ts:214`" fica errado no
dia em que alguém insere dez linhas acima — e continua *parecendo* preciso.

A regra é **oposta** para achado de revisão: ali `arquivo:linha` é o que faz o
corretor achar o problema, e o achado é consumido na mesma hora. **Vida curta
pede endereço; vida longa pede nome.**
