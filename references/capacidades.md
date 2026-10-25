# Poder e política: o que a máquina consegue, e o que o projeto quer

São duas perguntas, e o fluxo precisava das duas separadas. Elas divergem, e é
na divergência que estava o buraco.

| Pergunta | Quem responde |
|---|---|
| Esta máquina, esta conta, este seat **conseguem**? | `tools/flow-state/capabilities.py` |
| Este projeto **quer**? | `[capacidades]` no `config.toml` |

O caso que obrigou a separação é o Figma. O MCP pode estar autenticado e
funcionando — poder sim — e o projeto continuar não querendo que ninguém
escreva no arquivo que o UX mantém. Antes disto, entre "consegue" e "faz" havia
uma frase numa skill pedindo autorização: negociação em tempo de execução, não
política de projeto. Cada atividade renegociava do zero, e a resposta dependia
de quem estava na sessão naquele dia.

## O vocabulário

Três valores, iguais para todas as ações:

```toml
[capacidades]
grafo         = "auto"
figma_leitura = "auto"
figma_escrita = "off"
navegador     = "auto"
```

- **`auto`** — usa se der; quando não der, **declara a lacuna** e segue. É o
  padrão, e é o que faz o pacote poder ser zipado e mandado: nada exige nada.
- **`on`** — exige. Se não der, reclama alto em vez de degradar calado. Serve
  para o projeto que considera aquela capacidade parte do contrato.
- **`off`** — não faz, mesmo podendo.

## Os três valores respondem, e há um quarto estado

`auto`, `on` e `off` são a **política**. O que a saída mostra é o cruzamento
dela com a **capacidade**, e o cruzamento tem quatro resultados:

| Marcador | O que significa | O que fazer |
| --- | --- | --- |
| `[sim ]` | A política deixa e a máquina consegue | Aja |
| `[NÃO ]` | A política desligou, **ou** a máquina não consegue | O `porque` diz qual dos dois — e a razão muda o que fazer: política pede parar, acesso pede degradar e declarar |
| `[?   ]` | A política deixa e **este processo não sabe** se a máquina consegue | **Confirme na sessão antes de agir**, e nunca leia como sim |

O `?` não é um buraco: é a resposta certa para o que só a sessão enxerga. O
`figma_escrita` é o caso — quem responde se há `use_figma` são as ferramentas da
sessão, não um comando de linha.

**Não confunda `on` com "consegue".** Em 08/09/2026 um projeto com
`figma_escrita = "on"` não tinha o MCP: o portão da política abria e nada
executava. Pior, por um dia a saída dizia `[sim]` com um detalhe que falava de
**leitura por REST** — porque a ação de escrita herdava a detecção do token, e um
token prova leitura e não diz nada sobre o MCP. Duas ações, duas fontes: é por
isso que elas são separadas.

## Por que a lista é fechada

Chave fora da lista é quase sempre erro de digitação, e `figma_escrit = "on"`
deixa a escrita desligada enquanto o config afirma que ligou. O doutor acusa —
e só consegue acusar porque a lista é fechada.

A lista fechada também sustenta a segunda garantia: **nenhuma ação entra sem
um leitor.** O doutor procura o nome da ação nos `SKILL.md` e nos agentes do
pacote, e acusa a que ninguém consulta. Flag morta é o pior estado de um
portão: parece controle e não é.

Foi por essa regra que `anexo_no_card` ficou de fora do primeiro corte. A ideia
era boa e nada a consultava — então ela não existe até existir.

## `off` viaja com a entrega

Ação desligada não é falha. É escolha, e some do relatório se ninguém disser —
e aí a entrega parece completa quando não é.

Vale a mesma regra dos steps desligados, que o `[fluxo] steps` já aplica: a
lista do que ficou de fora acompanha a atividade e todo relatório dela. Uma tela
que não foi desenhada porque o projeto proíbe diz isso na própria cara, no lugar
onde alguém vai procurar depois.

## Política não substitui consentimento

`figma_escrita = "on"` **não** autoriza escrever. Autoriza *oferecer*.

São dois portões, e eles respondem a coisas diferentes:

1. **Política** — decidida uma vez, para todas as atividades, por quem responde
   pelo projeto.
2. **Consentimento** — pedido toda vez, a quem está na sessão.

Com `off`, o primeiro portão fecha e o segundo nem chega a ser aberto: não
ofereça, não sugira, não construa "para o caso de". Insistir contra a política
do projeto é o mesmo que rodar um step desligado.

## Por que `figma_escrita` nasce `off`

Não por cautela genérica — por precedente do próprio pacote. O
`metricas.publicar_no_repo` já é `false` por padrão, com a razão escrita ali:
*um pacote não começa a escrever no repositório de ninguém sem alguém ter dito
que sim.*

Arquivo de Figma é a mesma fronteira, com uma diferença que pesa contra:
**não tem `git revert`.**

## Como consultar

```bash
python3 $PACOTE/tools/flow-state/capabilities.py figma_escrita
python3 $PACOTE/tools/flow-state/capabilities.py figma_escrita --json
```

A resposta cruza os dois eixos e diz **por quê**, não só sim ou não:

```json
{ "politica": "off", "disponivel": null, "permitido": false,
  "porque": "desligado no config do projeto" }
```

O `porque` existe porque um "não" sem motivo faz a sessão tentar de novo por
outro caminho — e a razão muda o que ela deve fazer. Falta de acesso pede
fallback; política pede parar e declarar.

## Onde se mexe

No `/config`, bloco **"O que este projeto deixa o fluxo fazer"**. Na instalação
ou no meio do caminho: um projeto que libera a escrita no Figma depois de o
time ganhar confiança muda uma chave, e não reinstala nada.
