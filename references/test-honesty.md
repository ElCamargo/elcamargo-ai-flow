# Gate verde não é requisito provado

Duas lentes que a revisão não tinha, e que só se enxergam contando:

| Lente | A pergunta |
| --- | --- |
| **Honestidade de teste** | O teste rodou? E se rodou, ele reprovaria se o comportamento quebrasse? |
| **Alegação simulada** | A prova veio do sistema, ou do dublê que o substitui? |

Numa entrega real, **onze testes verdes provavam nada** — descobriu-se por
mutação, não por leitura. E o portão visual da mesma entrega fechou anunciando
`145 passaram, 0 falharam`, com **152 ignorados na mesma linha**. As duas frases
eram verdadeiras. A decisão foi tomada em cima da primeira.

## O que a lente procura

| | Por que importa |
| --- | --- |
| `.only` commitado | Um `.only` faz **todo o resto do arquivo não rodar**, e a suíte continua verde. É o jeito mais barato de desligar testes sem que ninguém veja |
| Pulo estático — `it.skip('nome', …)`, `it.todo`, `xit` | Não roda em ambiente nenhum, e a cobertura conta o arquivo como coberto |
| Asserção trivialmente verdadeira | `expect(true).toBe(true)` passa com a implementação removida |
| Caso sem asserção nenhuma | Prova que o caminho não lança. Pode ser o que se queria — **declare** |
| Caso cuja única asserção é `toHaveBeenCalled()` | Prova a fiação. O valor de retorno e o efeito continuam sem prova |
| O arquivo que simula o próprio módulo que testa | O que passa é o dublê. Trocar a implementação por `return null` não quebraria este teste |
| Quantos **não rodaram** na rodada | "Passaram, 0 falharam" é verdade e não é a história inteira |

```bash
python3 $PACOTE/tools/honesty/honesty.py testes --raiz .
python3 $PACOTE/tools/honesty/honesty.py saida --formato vitest -
```

## Tudo isto é procedência `estrutural`

Padrão, contagem e ausência dizem **onde olhar**, não o que reprovar — ver
`severity.md`, *Procedência: como você sabe*. Um achado desta lente só reprova
depois de promovido por leitura ou por execução. Sozinho, ele viaja como achado
aberto.

A única exceção é `.only` commitado, que não tem leitura que o salve: ou é
descuido, ou é o resto do arquivo desligado de propósito.

**O teste de verdade é a mutação.** Quebre a implementação e veja se algum teste
reprova. Foi assim que os onze verdes caíram, e é o que nenhuma varredura
estrutural substitui.

## A calibração, que é a metade cara

Esta lente errou **três vezes seguidas** contra um repositório real antes de
acertar. Vale escrever porque o erro é o mesmo em qualquer lente estrutural:
uma regra plausível encontra o padrão certo e a intenção errada.

| | Acusou | Todos falsos porque |
| --- | --- | --- |
| 1ª | 3 casos "sem asserção" | Os testes afirmam por um helper — `expectRefusal(...)`, com as asserções dentro |
| 2ª | 35 casos "só afirma que foi chamado" | `.not.toHaveBeenCalled()` é a **única** forma de provar "não faz nada" |
| 3ª | 5 casos idem | Quando o comportamento **é** a contagem, ela é a asserção: "recria o canal fechado" quer dizer duas chamadas |

Depois das três correções: **135 arquivos de teste, zero achados** — que é o
resultado honesto, porque o repositório de fato não tem teste desonesto.

Havia um quarto candidato, derrubado antes de nascer: `test.skip(condição,
motivo)` aparece 13 vezes no mesmo repositório e é **guarda declarada** — o teste
existe, roda quando dá, e diz por que não deu. Uma lente que não separasse isso
de `it.skip('nome', …)` teria acusado treze falsos na primeira execução.

**E uma lente que erra na primeira execução ninguém roda de novo.** É por isso
que a calibração contra código real não é polimento: é a diferença entre uma
ferramenta e um gerador de ruído. Estreitar até o silêncio, porém, tem o risco
oposto — uma lente cega é indistinguível de uma lente limpa. Por isso metade do
teste de fumaça são casos que ela **ainda precisa pegar**.

## Onde ela entra no fluxo

**Step 8**, antes de fechar: o desenvolvedor roda a varredura no que escreveu. É
mais barato consertar um `.only` esquecido agora do que ver seis frentes
reportando uma suíte que não rodou.

**Step 9**, na frente de qualidade: a varredura e a contagem de não-rodados
entram no relatório — a primeira como candidatos a achado, a segunda como
contexto para o portão humano.

O número de casos que não rodaram vai ao **portão 10** junto da distribuição de
destinos e do tamanho da catraca. Quem decide tem direito aos três.
