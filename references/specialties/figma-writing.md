# Especialidade: escrever no Figma sem estragar arquivo dos outros

Ler é seguro por construção: `tools/figma/figma.py` usa a API REST, que **não
consegue escrever**. Escrever joga fora essa garantia. Tudo aqui existe para
recuperar parte dela por disciplina, já que a ferramenta não a dá mais.

Duas regras que não se negociam:

- **Nunca escreva numa página que o UX mantém.** Página própria, sempre.
- **Nunca escreva sem a sonda.** Sem ela você não sabe em qual dos três casos
  está, e o erro mais comum não é escrever errado — é escrever bonito no sistema
  errado.

## 1. A sonda de reconhecimento

Antes de qualquer traço, rode isto no arquivo de destino. É read-only e barato.

```js
const paginas = figma.root.children.map(p => p.name);

let colecoesDeLibrary = [];
try {
  const cols = await figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync();
  for (const c of cols) {
    let n = null;
    try { n = (await figma.teamLibrary.getVariablesInLibraryCollectionAsync(c.key)).length; } catch (e) { n = 'erro'; }
    colecoesDeLibrary.push({ library: c.libraryName, colecao: c.name, variaveis: n, key: c.key });
  }
} catch (e) { colecoesDeLibrary = 'erro: ' + String(e); }

const colecoesLocais = (await figma.variables.getLocalVariableCollectionsAsync())
  .map(c => ({ nome: c.name, variaveis: c.variableIds.length, ocultaParaPublicar: c.hiddenFromPublishing }));

const estilosLocais = {
  texto: (await figma.getLocalTextStylesAsync()).length,
  cor: (await figma.getLocalPaintStylesAsync()).length,
  efeito: (await figma.getLocalEffectStylesAsync()).length
};

return { paginas, colecoesDeLibrary, colecoesLocais, estilosLocais };
```

### Ler o resultado

`colecoesDeLibrary` só vem preenchida se o arquivo **assinar** a library.
Vazia não significa que não existe library — significa que este arquivo não a
assina. Assinar é ação de interface; peça ao usuário.

Três casos, e o tratamento muda inteiro:

| O que a sonda mostra | Caso | O que fazer |
|---|---|---|
| `colecoesLocais` cheia | **base local** | Use o que está ali. Não precisa publicar nada. |
| `colecoesDeLibrary` cheia | **library assinada** | Use os tokens dela. Componentes exigem a chave — veja abaixo. |
| as duas vazias | **sem base** | Extraia do código e crie coleção local marcada como derivada. Nunca invente paleta. |

`paginas` revela a convenção de nomes do arquivo. Siga-a: se as páginas do
projeto usam prefixo para seção e para tela, a sua nasce no mesmo padrão. É por
ela que o revisor humano acha o que você desenhou.

### Componentes não vêm na sonda

Coleção de variável a Plugin API entrega; componente publicado, não. Use
`search_design_system` **sempre com `includeLibraryKeys`**, com a chave que a
sonda devolveu.

Sem a chave, a busca ignora as libraries do time e devolve o que estiver
indexado — inclusive design system de terceiros, sem erro nenhum. O agente monta
a tela inteira no sistema errado e nada acusa. Esse é o pior modo de falha desta
especialidade, porque o resultado *parece* certo.

## 2. As armadilhas que falham caladas

Nenhuma destas dá erro. Todas produzem tela errada com aparência de tela certa.

1. **`resize()` depois de definir o modo de dimensionamento reseta para fixo.**
   Defina `layoutSizingHorizontal` / `layoutSizingVertical` **depois** do resize,
   nunca antes. Sintoma: caixa de 10px com o texto vazando por fora — ou uma
   folha de variantes que se recusa a quebrar em linhas.
2. **`figma.createAutoLayout()` nasce com preenchimento branco opaco.** Se você
   não limpar, ele esconde o token que deveria aparecer — e a tela parece boa
   por acidente.
3. **Id de nó não sobrevive entre execuções.** Guardar o id de um component set
   e usá-lo na chamada seguinte falha com `null`. Reimporte por chave, que é
   idempotente.
4. **`node.query()` não aceita acento no seletor.** `query('[name^=Ação]')`
   quebra. Use `findAll` com predicado.
5. **`vectorPaths` não aceita o comando `A` (arco).** Círculo é Bézier cúbica —
   ou, melhor, `createNodeFromSvg`, que aceita o `d` inteiro.
6. **`hiddenFromPublishing` não existe em componente**, só em variável e estilo.
   Depreciar componente é por nome e descrição.
7. **`clone()` descarta as `componentPropertyReferences`.** A cópia nasce com o
   texto e o ícone soltos, e o `setProperties` seguinte grava o valor sem que
   nada apareça: a instância continua mostrando o padrão do componente. Sintoma:
   seis itens de menu diferentes, todos escritos "Item de menu". Depois de
   clonar, reatribua a referência em cada nó.
8. **Criar o nó de texto não cria a propriedade.** Sem `addComponentProperty` a
   chave não existe, o `setProperties` não tem onde escrever e não reclama. Mesmo
   sintoma do item anterior, causa diferente — e é por isso que vale conferir o
   resultado, não a chamada.
9. **A instância guarda o `minWidth` do componente antigo depois do swap** — e
   `minWidth` não é sobrescrevível em instância, a API recusa a escrita. O botão
   continua esticado sem nada no arquivo explicando por quê. Recriar a instância
   a partir do componente novo é o único jeito.
10. **`upload_assets` deposita na página corrente**, que não é necessariamente a
    que você setou na chamada anterior. Ache o nó pelo id que o upload devolveu,
    nunca pela página onde você imagina que ele caiu.
11. **O gate acusa transbordo falso dentro de SVG importado.** Grupo de recorte
    tem conteúdo maior que a própria caixa por construção. Descarte os nós com
    `clipsContent`, e não confunda com defeito.
12. **Nó escondido por propriedade booleana some da árvore da instância.** O
    Figma o poda, então `findOne` devolve `null` e a leitura natural — "o slot
    não existe" — está errada: ele existe e está desligado. Para conferir um slot
    opcional, ligue a propriedade primeiro. Quem lê o `null` como defeito
    "conserta" um componente que estava certo.

## 3. As que dão erro — com a mensagem longe da causa

Estas param a execução, o que é sorte sua. O custo é que a mensagem descreve o
sintoma, e o sintoma mora longe do erro.

- **`resetOverrides()` desfaz o `swapComponent()`.** Trocar o componente de uma
  instância conta como sobrescrita, então o reset devolve a instância ao
  componente *antigo* — e as propriedades que só existem no novo somem junto. A
  mensagem vem no `setProperties` seguinte: "Could not find a component
  property". Para voltar ao componente novo, recrie a instância.
- **`componentPropertyDefinitions` só existe em conjunto ou em componente sem
  variante.** Ler a propriedade numa variante estoura. Leia sempre no
  `COMPONENT_SET`.
- **`parent.children.indexOf(no)` devolve `-1`.** Cada leitura de `children`
  entrega proxies novos, e `indexOf` compara por referência. Use
  `findIndex(c => c.id === no.id)`. O sintoma é um `insertChild` recusando
  índice negativo.
- **`getLocalTextStylesAsync()` volta vazio no arquivo que consome a library.**
  Os estilos são remotos, não locais. Monte um índice nome → `textStyleId`
  varrendo nós que já os usam, e resolva por ali.
- **Navegação de protótipo só liga quadros de topo da MESMA página.** Fluxo
  espalhado em páginas diferentes é recusado. Junte as telas numa página só.
- **`page.prototypeStartNodeID` não existe.** O ponto de partida é
  `page.flowStartingPoints = [{ nodeId, name }]`.

E uma boa notícia que economiza limpeza: **execução que dá erro é revertida
inteira.** Não sobra estado pela metade — corrija e rode de novo.

## 4. O gate de aderência

Depois de desenhar, meça. Passe o id do nó raiz do que você criou.

```js
const RAIZ = 'COLE_O_ID_AQUI';
const raiz = await figma.getNodeByIdAsync(RAIZ);
const todos = raiz.findAll(() => true);

// o interior de uma instância é responsabilidade da library, não sua
function dentroDeInstancia(n) {
  let p = n.parent;
  while (p && p !== raiz) { if (p.type === 'INSTANCE') return true; p = p.parent; }
  return false;
}
const meus = todos.filter(n => !dentroDeInstancia(n));
const pct = (a, b) => b ? Math.round(a * 100 / b) + '% (' + a + '/' + b + ')' : 'n/a';

const comFill = meus.filter(n => n.fills && n.fills !== figma.mixed && n.fills.length);
const comStroke = meus.filter(n => n.strokes && n.strokes.length);
const textos = meus.filter(n => n.type === 'TEXT');
const ligado = p => p.boundVariables && p.boundVariables.color;

// transbordo: caixa menor que o conteúdo — o defeito que a medida externa não pega
const transbordo = meus.filter(n => n.children && n.children.length &&
  n.children.some(c => c.y + c.height > n.height + 1 || c.x + c.width > n.width + 1))
  .map(n => n.name);

// de onde vêm as instâncias
const inst = todos.filter(n => n.type === 'INSTANCE' && !dentroDeInstancia(n));
const origem = {};
for (const i of inst) {
  const mc = await i.getMainComponentAsync();
  const k = !mc ? 'sem componente' : (mc.remote ? 'library' : 'local');
  origem[k] = (origem[k] || 0) + 1;
}

return {
  fillsLigados: pct(comFill.filter(n => n.fills.some(ligado)).length, comFill.length),
  strokesLigados: pct(comStroke.filter(n => n.strokes.some(ligado)).length, comStroke.length),
  textosComEstilo: pct(textos.filter(t => t.textStyleId && t.textStyleId !== figma.mixed && t.textStyleId !== '').length, textos.length),
  instancias: inst.length,
  origemDasInstancias: origem,
  transbordo: [...new Set(transbordo)]
};
```

### O que reprova

- **`transbordo` não vazio reprova sempre.** É defeito, não estilo.
- **`origemDasInstancias` com `local` onde havia library reprova.** Significa
  que você desenhou o que já existia.
- **O gate não enxerga o interior das instâncias, de propósito** — aquilo é
  responsabilidade da library. O preço é que uma sobrescrita *sua* lá dentro
  passa batida: um botão espremido dentro de um componente não aparece em
  `transbordo`. Se você sobrescreveu algo dentro de uma instância, meça à mão.
- **Cor e tipografia comparam com o arquivo, não com um número fixo.** Meça uma
  página que o UX manteve e use como alvo. Ficar abaixo da média do próprio
  arquivo é o que reprova; um número absoluto não diz nada, porque cada projeto
  tokeniza numa profundidade.

Rode o gate na página do UX antes de desenhar, guarde o número, e compare no
fim. Sem essa linha de base o gate vira opinião.

## 5. Não redesenhe o que já existe em arquivo

Ícone e logo do produto moram no repositório. Redesenhar de memória produz um
glifo parecido, e parecido é o pior resultado possível: ninguém percebe, e a
library passa a ensinar uma forma que o código não usa.

- **Ícones**: o pacote traz o `d` de cada glifo. Em `lucide-react`, cada
  `dist/esm/icons/<nome>.mjs` exporta `__iconNode` com os elementos e seus
  atributos. Monte o SVG a partir dali e passe para `figma.createNodeFromSvg`,
  que aceita arco — ao contrário de `vectorPaths`. Reduza com `rescale()`, que
  escala a espessura do traço junto: 24 para 16 deixa o traço 2 em 1,33, que é o
  que a tela mostra.
- **Marcas e bandeiras**: `upload_assets` aceita `image/svg+xml` e importa como
  árvore de vetor editável, sem passar os bytes pelo seu contexto. Suba o
  arquivo de `public/`; não desenhe logo à mão, nunca.

Confira a contagem de elementos do que você montou contra a do arquivo de
origem. Um `path` a menos passa despercebido — foi assim que um `settings` ficou
sem a engrenagem e um `bell` sem o corpo, e os dois pareciam ícones normais.

E **audite o centro**: glifo desenhado a partir da origem encosta no canto
superior esquerdo da caixa. Doze ícones desta library ficaram assim, deslocados
de 1,5 a 5,8px, e ninguém viu até um deles cair ao lado de um texto.

## 6. O relatório de lacunas

Improviso silencioso é o que degrada design system. Quando faltar componente,
ícone ou variante, **use o mais próximo e declare** — nunca desenhe um
substituto sem dizer.

O relatório sai junto com a tela e lista, em uma linha cada: o que faltou, o que
foi usado no lugar, e onde. Quem revisa decide se cria na library ou aceita o
substituto. Sem esse relatório, a decisão nunca chega a ninguém.

## 7. Como verificar que publicou

Publicar e assinar library **não estão na Plugin API** — são ações de interface.
Você não faz; pede.

E não confirme publicação por `get_libraries`: o campo
`libraries_available_to_add` lista apenas kits de comunidade, e library de time
nunca aparece ali, publicada ou não.

Duas provas servem, e nenhuma precisa de arquivo virgem:

- **o índice publicado.** `search_design_system` com a chave da library traz
  `updatedAt` por componente. O que você acabou de publicar carimba a hora; o
  resto continua com a data anterior. É a diferença entre os dois que prova, não
  o carimbo isolado.
- **`importComponentSetByKeyAsync`**, que devolve a versão publicada mesmo num
  arquivo que já consome a library.

O que **não** prova é medir as instâncias do arquivo consumidor: elas ficam na
versão que aquele arquivo aceitou, e aceitar atualização é ação de interface. No
mesmo arquivo e no mesmo instante, o import devolveu 8 variantes enquanto as
instâncias ainda tinham 3 — as duas respostas estão certas, e respondem a
perguntas diferentes. Confundir as duas faz você acusar de falha uma publicação
que deu certo.

Ao conferir geometria, desça no **interior**: um componente com a altura externa
certa pode ter os filhos achatados por dentro.

### O que chega sozinho na instância, e o que exige recriar

Nem toda mudança publicada alcança as instâncias do mesmo jeito, e a diferença
não é o tamanho da mudança — é a natureza dela.

| O que mudou | O que acontece na instância |
|---|---|
| conteúdo, com a **mesma chave e a mesma estrutura** — redesenhar um ícone, corrigir uma cor, mexer numa medida interna | chega sozinho |
| **estrutura** — variante nova, variante renomeada, propriedade nova, conjunto refeito | a instância fica presa na versão antiga; só recriar resolve |

Doze ícones foram substituídos pelos glifos reais e apareceram consertados em
tudo que já os usava, sem uma linha a mais. No mesmo dia, um `Button` que ganhou
uma dimensão de variante deixou todas as instâncias para trás, e cada uma teve de
ser recriada com `createInstance` no índice do pai.

Daí uma regra de método: **quando for corrigir algo que já está publicado,
preserve a chave.** Refazer o componente do zero — `combineAsVariants` sobre nós
novos, por exemplo — gera chave nova e transfere para você o trabalho de
reconstruir cada instância. Editar o conteúdo do componente existente entrega a
correção de graça.
