# Grafo de conhecimento: acelerador opcional, nunca dependência

O fluxo gasta contexto descobrindo onde as coisas moram. Um grafo de
conhecimento do repositório responde parte disso barato, e vale a pena quando
existe. Esta referência diz o que ele resolve, o que ele **não** resolve, e as
três regras que impedem que ele estrague a disciplina de evidência.

A ferramenta avaliada é o **graphify** (`uv tool install graphifyy`). Nada aqui
depende dela: troque por outra que faça o mesmo e as regras continuam valendo.

## O veredito

**Sim como capacidade opcional. Não como dependência.**

O pacote precisa funcionar inteiro com **zero instalação** — é isso que permite
zipar e mandar para outro time. Um step que só funciona depois de instalar algo
deixa de ser replicável, e o primeiro projeto sem a ferramenta descobre isso na
pior hora.

Então: quando o grafo existe e está fresco, use. Quando não existe, o fluxo
roda igual — o mapa do terreno (`tools/briefing/domain.py`) é determinístico,
não instala nada, e cobre o essencial.

Declare em `config.toml`:

```toml
[capacidades]
grafo = "auto"   # auto | on | off
```

`auto` usa se existir e estiver fresco. `off` ignora mesmo existindo — útil
quando o time não confia no grafo daquele repositório.

## O que ele resolve, e o mapa do terreno não

O mapa é um índice: entidades, migrations, rotas, métodos, specs. Estrutura.

O grafo faz **travessia**, e é aí que ele ganha:

| Pergunta | Quem responde |
| --- | --- |
| Que entidade tem esta coluna? | mapa |
| Quais migrations tocam esta tabela? | mapa |
| O que chama este método, transitivamente? | grafo |
| Como o dado sai daqui e chega ali? | grafo |
| O que mais muda quando isto muda? | grafo |
| Que arquivos formam um assunto, sem eu saber os nomes? | grafo |

A última é a que mais rende. O mapa só acha o que tem o termo no nome; o grafo
agrupa por conexão, e mostra o arquivo que trata do assunto com outro
vocabulário — exatamente o que passa despercebido.

## O custo

**Código é de graça.** A extração é AST determinística: sem LLM, sem chave de
API, sem custo por token. `graphify .` num repositório de código não gasta
nada além de CPU.

**Documento não é.** Extração semântica de markdown, PDF e imagem usa modelo —
`GEMINI_API_KEY` se estiver posto, senão o próprio agente da sessão. Num
projeto como os nossos, cheio de spec em markdown, **é aí que o custo mora**,
não no código.

Consequência prática: construir o grafo **só do código** é barato e útil. Puxar
`docs/` inteiro para dentro dele é uma decisão de custo, não um detalhe.

## As três regras

### 1. Grafo é pista, não evidência

Nada que sai do grafo entra numa SDD, num relatório ou num achado sem ser
**confirmado no arquivo**, com caminho e linha. Leia `evidence.md`.

O grafo diz onde olhar. Ele não prova nada, e uma travessia convincente sobre
código que mudou é a forma mais eficiente de errar com confiança.

### 2. Aresta inferida não é aresta observada

O graphify marca cada aresta como `EXTRACTED`, `INFERRED` ou `AMBIGUOUS`, e
isso é uma virtude — a maioria das ferramentas não distingue.

**Só `EXTRACTED` é fato**, e mesmo assim precisa da regra 1. `INFERRED` é
hipótese da ferramenta; tratá-la como fato é herdar o palpite dela sem saber
que herdou.

### 3. Grafo velho é pior que grafo nenhum

Um grafo construído na segunda respondendo sobre o código de quarta responde
**com a mesma confiança** de um fresco. Não há sinal na resposta.

Antes de consultar:

```bash
python3 $PACOTE/tools/flow-state/capabilities.py grafo
```

Ele compara a data do grafo com o último commit e avisa quando está para trás,
com quantos arquivos mudaram desde então. Se estiver:

```bash
graphify . --update    # incremental, só o que mudou
```

Se você não vai atualizar, **não consulte**. Voltar ao mapa do terreno é a
opção correta, não o plano B.

## A fricção que você vai encontrar

O casamento de termos é **substring literal com IDF**: sem radical, sem
sinônimo, sem tradução. Nosso caso é justamente o difícil — especificação em
português, código em inglês. "cadastro de pedido" não acha `OrderEntity`.

A skill do graphify já trata isso, e do jeito certo: extrai o vocabulário real
do grafo e obriga a escolher tokens **daquela lista**, sem inventar sinônimo. O
efeito colateral é que a consulta vira duas etapas, e uma consulta mal expandida
volta vazia em vez de voltar errada — o que é o comportamento desejável.

Conte com isso ao decidir se vale: numa demanda pequena, o mapa do terreno
resolve antes de você terminar de expandir a consulta.

## Quando não usar

- **Para provar qualquer coisa.** Sempre arquivo e linha.
- **Quando o grafo está desatualizado** e você não vai atualizar.
- **Em demanda pequena**, onde o mapa do terreno já responde.
- **Como primeira parada.** Comece pelo mapa; vá ao grafo quando a pergunta for
  de travessia, e você souber que é.
