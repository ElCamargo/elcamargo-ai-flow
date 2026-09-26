# Especialidade: ler o Figma sem queimar a cota

O gargalo do step 6 não é a ferramenta, é a **conta**. Antes de qualquer leitura,
descubra o orçamento — e conduza por ele.

## O orçamento decide tudo

Os limites de leitura seguem o **seat**, e valem pelo plano onde o **arquivo**
mora, não pelo seu:

| Seat | Orçamento de leitura |
| --- | --- |
| Dev / Full | 200 a 600 chamadas **por dia** |
| Collab / View | 6 a 20 chamadas **por mês** |

Com seat Collab, uma tela mal conduzida queima o mês inteiro. Uma varredura
exploratória é o erro mais caro que você pode cometer aqui, e ele não avisa: as
chamadas passam e a cota acaba depois.

**Chame `whoami` antes de qualquer outra coisa.** Ele devolve plano e seat.

## Estratégia por orçamento

**Largo (Dev/Full).** Navegue com o recurso de metadados — ele devolve estrutura
esparsa, barata, sem estourar contexto. Depois leia o contexto de design das
telas que interessam, puxe as variáveis usadas e baixe os assets necessários.

**Apertado (Collab/View).** Uma navegação, uma leitura da tela alvo, e **pare**.
Nada de explorar o arquivo. Se precisar de mais de duas ou três telas, **peça ao
usuário para exportar** — export manual não consome cota, e é mais rápido que
gastar o mês.

**Sem MCP ou sem acesso.** Vá pelo desenho de tela. Não é degradação do fluxo: é
o outro caminho previsto do step 6.

Diga no relatório qual estratégia usou e quantas chamadas gastou. É o que
permite a próxima atividade se planejar.

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
