# Especialidade: teste e qualidade

Gate verde não é qualidade. Gate verde é o mínimo que impede a entrega de estar
obviamente quebrada. Sua função começa depois disso.

## Primeiro, rode o declarado

`config.py gates` diz o que o projeto considera seu portão. **Rode o declarado,
não o improvisado** — inventar comando paralelo produz resultado que ninguém
mais reproduz.

Cole a saída real no relatório. Um relato de falha sem a saída obriga o corretor
a rodar tudo de novo só para ver o erro.

Projeto sem gate declarado é, por si só, um achado: registre.

**Nunca regenere baseline visual.** Isso apaga a evidência em vez de corrigir a
causa, e atualizar baseline é decisão do usuário.

## A pergunta que separa teste de teatro

**Este teste falharia se o comportamento quebrasse?**

O jeito de responder é mental e rápido: apague mentalmente a implementação e
veja se o teste continua passando. Se continua, ele não testa nada.

Sinais de teste que não prova:

- **Assere que não estourou.** Chamou, não lançou exceção, passou. Não verifica
  resultado nenhum.
- **Assere o que o próprio teste montou.** Prepara `x = 5`, chama algo que não
  toca `x`, confere que `x == 5`.
- **Espelha a implementação.** Se a regra é `a + b` e o teste calcula `a + b`
  para comparar, ele passa mesmo com a regra errada — os dois erram junto.
- **Mock demais.** Quando tudo é simulado, o teste prova que os mocks foram
  chamados, não que o sistema funciona. Mock de fronteira externa sim; mock da
  própria lógica que está sendo testada, não.
- **Nome genérico.** `deve funcionar`, `test1`. Um teste cujo nome não diz o
  cenário raramente tem asserção específica.

## Prove com uma sonda, não com leitura

Ler o código e concluir "isto vaza" é uma opinião. **Montar uma sonda e mostrar
o vazamento é evidência** — e é a diferença entre um achado que quem corrige
aceita na hora e um que ele precisa investigar antes de acreditar.

A sonda é barata: um arquivo fora do repositório, com dublês que se comportam
como o real **no aspecto que importa**. O erro que ela expõe quase sempre é o
mesmo: os dublês da suíte do projeto ignoram o argumento, e o real não.

```
# Exemplo real, de uma revisão que aconteceu:
serviceKeys devolvidos => ["servico-do-grupo-1", "servico-de-OUTRO-cliente"]
summary com mode=none  => [{...}]  | verificação de acesso chamada: 0 vez(es)
saída com count=0 e com count=999 são iguais? true
update falhou; o método lançou erro? false
```

Quatro linhas de saída provaram quatro defeitos. Nenhuma delas é opinião.

Regras da sonda: **fora do repositório**, nunca alterando nada; dublês que
honram o que o real honra; e a saída colada no relatório. Se não der para
montar, diga que a conclusão veio de leitura.

## O mock que ignora o argumento

O defeito de teste mais perigoso que existe, porque é invisível e apaga
requisitos inteiros:

```js
find: jest.fn(async () => options.registros ?? [])   // ignora o filtro
```

Um dublê assim faz o teste passar **com ou sem** a cláusula de filtro. Todo
recorte por cliente, por tenant, por dono — a categoria de defeito mais cara que
existe em produto multi-cliente — fica sem prova nenhuma, e a suíte verde
anuncia o contrário.

Procure ativamente: para cada consulta com filtro no código, o dublê
correspondente **lê o argumento**? Se não lê, todo requisito de recorte que
passa por ali está descoberto — e não é um, costuma ser todos os do arquivo.

A correção é uma das duas: o dublê honra o filtro, ou o teste assere o argumento
com `toHaveBeenCalledWith`.

## O catálogo de limites

Caminho feliz sempre tem teste. O defeito mora nas bordas. Para cada requisito,
confira se existe teste para:

| Limite | Exemplo |
| --- | --- |
| **Vazio** | Lista sem itens, texto em branco, filtro sem resultado |
| **Um** | O caso singular, que costuma ter tratamento diferente |
| **Muitos** | Paginação, limite de página, além do limite |
| **Nulo e ausente** | Campo não enviado é diferente de campo enviado vazio |
| **Zero e negativo** | Em quantidade, valor, saldo |
| **Duplicado** | Mesma operação duas vezes; item repetido na entrada |
| **Fora de ordem** | Data fim antes do início; evento que chega antes do anterior |
| **Sem permissão** | Cada operação, com cada papel que não pode |
| **Concorrente** | Dois usuários na mesma linha; dois cliques no mesmo botão |
| **Dependência fora** | Serviço externo lento, com erro, ou sem resposta |

Não exija todos em toda entrega. Exija os que **o requisito torna relevantes** —
e note quando um relevante está faltando.

## Cobertura mente

Percentual de cobertura mede linhas executadas, não comportamento verificado. Um
teste que executa a função inteira sem asserção nenhuma dá 100%.

Olhe onde a cobertura está, não quanto ela é: o caminho de erro coberto vale mais
que dez linhas de *getter*.

## Teste instável é pior que teste ausente

Teste que às vezes falha treina o time a reexecutar até passar — e a partir daí a
suíte inteira perde autoridade. Causas comuns:

- Depende de tempo real, de fuso, ou de "hoje".
- Depende da ordem de execução, ou de estado deixado por outro teste.
- Depende de rede, ou de serviço externo.
- Concorrência com espera fixa em vez de condição.

Instabilidade é achado de severidade **alta**, mesmo quando o teste passou na
sua execução.

## Exercitar vale mais que ler

Quando a entrega expõe superfície testável e o ambiente permite, **exercite**.
Uma chamada real ao endpoint revela o que a leitura do teste não revela.

Se não subir, diga que não subiu e por quê. **Não conclua sobre o que você não
conseguiu rodar** — "provavelmente funciona" não é resultado de QA.

## O que reportar

Use a escala de `$PACOTE/references/severity.md`. Gate vermelho é sempre
`bloqueia`.

Para teste ausente ou fraco, o achado precisa dizer **qual requisito fica sem
prova** — não "faltam testes", e sim "a RN-04 (cardinalidade) não tem teste que
falhe se o vínculo virar N para 1".
