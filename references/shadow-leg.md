# A perna sombra: uma frente do step 9, dois modelos, a mesma chamada

A política de modelo (`model-policy.md`) só baixa de modelo onde o erro não
passa calado, e deixa as frentes do step 9 no modelo de quem dispara até haver
comparação. A perna sombra é essa comparação, rodando junto com o trabalho de
verdade, e não num experimento à parte.

Medido de 29 a 30/09/2026, as seis frentes do step 9 somam mais de 30% do custo
do backoffice e do app, todas em Opus. É a maior parte do fluxo que ainda
não tem resposta sobre o modelo.

O desenho vem de um experimento de 04/09/2026, cuja primeira rodada falhou
por defeito de desenho. Leia esta página inteira antes de mexer nas regras.

## Ligar

```toml
[capacidades]
perna_sombra = "sonnet"   # off | sonnet
```

Nasce `off`, porque ligar custa: uma frente a mais por atividade. É o preço de
medir, e o coletor o separa pelo modelo (`por_modelo`), então quem quiser o custo
da entrega sozinha subtrai a perna sombra.

## O que acontece no step 9

Só na **volta 1**. Na volta 2 rodam só as frentes que falharam, com escopo
fechado nos achados, e a comparação deixaria de ser a mesma chamada.

1. **Escolha a frente da vez**, entre as que rodam nesta volta:

   ```bash
   REG="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/perna-sombra.jsonl"
   python3 $PACOTE/tools/shadow-leg/shadow_leg.py escolher --registro "$REG" \
       --frentes code-reviewer,security-reviewer,quality-reviewer
   ```

   É rodízio: sai a que tem menos pares no registro. Em seis atividades há um par
   de cada frente, sem experimento dedicado e sem dobrar a conta.

2. **Dispare a frente duas vezes, com o mesmo prompt palavra por palavra.** A
   principal vai como sempre. A sombra leva `model: "sonnet"` na chamada, e
   nada mais muda. Se a frente escreve (`quality`, `runtime`), a sombra também
   ganha `isolation: worktree` e roda **numa leva própria, logo depois da
   principal**: duas suítes de mutação ou duas aplicações ao mesmo tempo disputam
   a máquina, e é por isso que essas frentes já rodam sozinhas. As de leitura vão
   com a principal na leva 1. O código não muda durante a volta, então rodar
   depois não altera a entrada.

3. **Grave os dois retornos** ao lado do relatório da volta, como
   `<frente>-principal.md` e `<frente>-sombra.md`, e compare:

   ```bash
   python3 $PACOTE/tools/shadow-leg/shadow_leg.py comparar --registro "$REG" \
       --atividade <id> --frente <frente> --principal <...-principal.md> \
       --sombra <...-sombra.md> --saida <...-perna-sombra.md>
   python3 $F artefato <id> --tipo perna-sombra --caminho <...-perna-sombra.md>
   ```

4. **Consolide só a principal.** Os achados da sombra não entram na lista, e não
   vão ao step 8. Misturar as duas no meio do caminho faria a volta 2 herdar a
   sombra, e a comparação da próxima atividade mediria outra coisa.

5. **No portão 10, a comparação vai junto do relatório**, numa seção própria.
   Todo `bloqueia` que só uma perna viu vem nomeado, e a pessoa decide: se o que
   só a sombra viu se sustenta, vira achado dali em diante; se não se sustenta, é
   falso positivo da sombra. As pernas se encontram no portão humano, e não
   antes, porque a pessoa não consegue esquecer o que leu.

## O que decide

```bash
python3 $PACOTE/tools/shadow-leg/shadow_leg.py resumo --registro "$REG"
```

O critério é o do experimento, declarado antes do primeiro número:

| Medida | Adota Sonnet na frente | Rejeita | Inconclusivo |
| --- | --- | --- | --- |
| Recall de `bloqueia`+`alta` da principal | ≥ 80% | < 60% | entre, e **não adota** |
| Falso positivo da sombra | ≤ 20% | > 40% | entre |

**Veto: um único `bloqueia` da principal que a sombra não viu reprova a frente.**
O `bloqueia` que a sombra viu com severidade menor não é veto, porque um `alta`
também vai ao step 8, mas o `resumo` o conta como rebaixado.

Abaixo de cinco pares numa frente, o `resumo` não dá veredito. O falso positivo
é contado pela pessoa no portão 10, e não pela ferramenta: só quem lê o código
sabe se o achado se sustenta.

## Depois do veredito: `[revisao.modelo]`

Com `adota` numa frente, a descida se declara no config do projeto:

```toml
[revisao.modelo]
code-reviewer = "sonnet"
```

O `status` do step 9 lê este registro **a cada atividade** e só deixa a linha
valer enquanto o `resumo` disser `adota` para aquela frente e aquele modelo. Um
`bloqueia` perdido num par novo derruba a linha sozinho, e ela volta a sair como
`IGNORADA`. Por isso vale manter a perna sombra ligada depois de descer: é ela
que continua conferindo.

O `adota` da ferramenta não inclui o falso positivo, que é contado à mão. Quem
escreve a linha é a pessoa, e é ela que confere essa metade antes.

## O que isto não prova

- **Casar por `arquivo:linha` é aproximação.** Dois achados na mesma linha podem
  ser defeitos diferentes, e o mesmo defeito pode ser ancorado em linhas
  diferentes. O que não tem âncora vai para uma lista de conferir à mão.
- **O gabarito é o relatório bruto da principal**, antes da consolidação. Um
  achado que a consolidação derrubaria conta como perdido pela sombra.
- **A variação entre duas rodadas do mesmo modelo não está medida.** Um par
  Opus × Opus de vez em quando daria essa régua, e ainda não está feito.
- **Não separa modelo de effort.** Opus em effort menor pode ser a resposta
  melhor que Sonnet, e isto não mede isso.
- **Vale para a frente medida, e só para ela.** Sonnet aprovado na `code` não diz
  nada sobre a `runtime`.
