# Especialidade: ler o Figma sem queimar a cota

Você lê pela **API REST**, com `tools/figma/figma.py` e um token pessoal. Não
pelo MCP, não pelo editor, não pelo navegador — e a razão está em uma linha:
**`GET` não consegue escrever.** Num arquivo da empresa, com gente trabalhando
dentro, essa garantia vale mais que qualquer conveniência.

## Comece raso, sempre

Um arquivo de design em JSON são megabytes, e o custo aqui é de duas naturezas:
a cota da API e o seu contexto. As duas se pagam com a mesma disciplina.

```bash
figma.py paginas <chave>                              # 1. o mapa
figma.py comentarios <chave> --abertos                # 2. requisito, não conversa
figma.py resumo <chave> --no <id> --profundidade 3    # 3. a tela
figma.py imagem <chave> --no <id> --saida tela.png    # 4. o que o JSON não conta
```

Descer direto na árvore inteira gasta numa chamada o que a atividade toda
deveria gastar. O `resumo` **avisa quando corta**: se avisou, desça por um nó
filho — não aumente o limite.

Se precisar de mais de duas ou três telas, **peça ao usuário para exportar**.
Export manual não consome cota e costuma ser mais rápido.

**Sem token, ou sem acesso ao arquivo.** Aí sim vá pelo desenho de tela. Não é
degradação do fluxo: é o outro caminho previsto do step 6. O que instalar, o
`capabilities.py figma_leitura` imprime.

**E quando a leitura falhar, o plano B não é o navegador.** Pare, diga o que
falhou, e peça export. Um `403` nomeia o escopo que falta — e escopo se marca ao
GERAR o token, não dá para acrescentar depois.

## O orçamento do MCP, para quando for o MCP

A tabela abaixo é do **MCP oficial**, que é o caminho da escrita. Ela não governa
a leitura por REST, e está aqui para não se perder:

| Seat | Orçamento do MCP |
| --- | --- |
| Dev / Full | 200 a 600 chamadas **por dia** |
| Collab / View | 6 a 20 chamadas **por mês** |

O limite segue o plano onde o **arquivo** mora, não o seu seat.

Diga no relatório qual caminho usou e quantas chamadas gastou. É o que permite a
próxima atividade se planejar.

## O que vale extrair, em ordem de valor

**1. O mapa de componentes.** Se houver recurso que ligue nó do Figma a
componente do repositório, use — é o que mais melhora a qualidade da saída,
porque o desenho passa a reusar o que existe em vez de gerar markup novo.

Sem esse recurso, faça o mapa você: para cada componente do protótipo, diga se
existe equivalente no projeto, se não existe, ou se existe parecido e diverge em
quê. **Essa tabela é o maior valor que você entrega ao desenvolvedor.**

**2. As variáveis e estilos usados.** Há recurso que devolve, para a seleção, as
variáveis com nome e valor. Cruze com os tokens do projeto e produza:

| Do Figma | No projeto | Situação |
| --- | --- | --- |
| `primary/500` `#7C3AED` | `--app-brand-primary` | igual |
| `neutral/300` `#D9D9D9` | — | **sem equivalente** |

"Sem equivalente" é achado, não detalhe: ou falta token no projeto, ou o Figma
saiu do sistema.

**3. O contexto de design.** Costuma sair em código. Trate como **referência de
estrutura**, nunca como implementação: os nomes de componente são do gerador, não
do seu projeto.

**4. Os assets.** Só o que a tela precisa. Cada download conta.

## Confrontar com a especificação

Leia as SDDs por inteiro antes de comparar. Para cada divergência:

| Campo | Conteúdo |
| --- | --- |
| Tela | onde aparece |
| O que o Figma mostra | literal |
| O que a SDD diz | com citação |
| Natureza | **visual** ou **comportamental** |
| Severidade | bloqueia / alta / baixa |

**A classificação visual × comportamental é o mais importante que você produz.**

Cor, espaçamento, ícone e rótulo são visuais — o Figma tende a prevalecer.
Obrigatoriedade de campo, regra de validação, permissão, quantidade permitida e
transição de estado são **comportamentais**: mudam regra de negócio e não podem
ser absorvidas pelo protótipo em silêncio.

Uma cardinalidade que o protótipo sugere e a SDD contradiz é comportamental — e é
o defeito que mais escapou neste fluxo.

## O que o Figma não mostra

Confira ativamente, porque a ausência não salta aos olhos:

- Os estados que faltam. Protótipo quase sempre tem o caminho feliz e o erro; e
  quase nunca tem vazio, sem permissão e parcial.
- O texto de cada validação.
- O que acontece depois de cada ação.
- Comportamento em largura diferente da desenhada.

Liste o que faltou. Para o desenvolvedor, saber que o protótipo **não** decidiu
algo vale tanto quanto saber o que ele decidiu.

## Limites

- **Nunca autentique, crie conta ou aceite termo.** Se cair em tela de login,
  pare e peça acesso ou export ao usuário.
- **Não descreva tela que você não conseguiu abrir.** Protótipo imaginado é pior
  que nenhum, porque parece informação.
- **Você não decide** qual lado prevalece. Quem decide é o step 6, e depois dele
  o portão humano.
- **Escrever no Figma é ação para fora**, no arquivo de outra pessoa. Só com
  autorização explícita, a cada vez.
