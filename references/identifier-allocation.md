# Identificador alocado sem coordenador

Lida por: quem cria spec, quem cria migration, e quem numera regra dentro de um
documento. Ler **antes** de escolher o próximo número.

O pacote **não define a convenção de nomes** do seu projeto — ela mora no
`docs/specs/README.md` de cada repositório. O que está aqui é a classe de
defeito, que é a mesma em qualquer convenção, e as três regras que saíram de
medir o estrago.

## 1. "O próximo livre" colide por construção

Toda vez que alguém escolhe um identificador olhando **a própria cópia** do
repositório — o próximo número da série, o próximo carimbo da sequência, a
próxima letra da regra — está fazendo alocação distribuída sem coordenador.
Dois ramos paralelos sempre veem o mesmo "próximo livre", e sempre pegam o
mesmo.

**Não é azar recorrente, é o desenho.** Em 11 e 12/09/2026, quatro ocorrências
em dois repositórios, em um dia:

| Camada | O caso | O que custou |
| --- | --- | --- |
| Nome de arquivo | `CAM-032..037` alocados em dois ramos | renumerar para `CAM-039..044`: **106 arquivos, 467+/468−** |
| Regra dentro da spec | `S-28c` e `S-28d`, duas sessões na mesma `CAM-025` | renumeradas para `S-28e..S-28i` |
| Regra dentro da spec | regras **22 e 23** da `IDN-003` | sete regras, **378 citações em 32 arquivos** |
| Carimbo de migration | `1700000044000` em dois ramos; `1700001900000` duplicado | renumerar, e o segundo caso duas vezes em 24 h |

> [!atencao] Consertar o nome do arquivo não fecha a classe
> Nome único não toca no identificador **dentro** do documento. E a camada de
> dentro é pior: migration colidida quebra alto, **regra colidida produz uma
> spec internamente contraditória que passa em qualquer portão de citação.**

## 2. Aloque de uma fonte que já é única, e nunca mude depois

A saída não é coordenar melhor — é **não precisar de coordenação**:

| Em vez de | Use |
| --- | --- |
| próximo número da série | o **número do card** (quem aloca é o board, não a pessoa) |
| carimbo escolhido à mão | o gerador do framework (`Date.now()`) |
| próxima letra da regra | uma faixa reservada por atividade, declarada no histórico |

E a regra que vale para os três: **o identificador não muda depois de alocado.**
Renomear o passado para arrumar a série é exatamente o estrago que a regra
existe para evitar.

> [!erro] Carimbo de migration que já rodou não se troca — em nenhuma hipótese
> O carimbo é a **identidade gravada na tabela de controle**. Trocá-lo depois de
> a migration ter rodado em ambiente persistente faz o banco não a reconhecer e
> tentar rodá-la de novo.
>
> A colisão de 12/09 pôde ser consertada porque a migration só tinha rodado em
> Postgres efêmero. **É a diferença entre um conserto de trinta segundos e um
> incidente.** Confira onde ela rodou antes de mexer; se rodou, o caminho é
> outro carimbo para a nova, e a colidida fica como está.

## 3. Quando renumerar for inevitável, remapeie por LISTA

Renumerar citação **não é substituir ocorrência**. O caso real, de quem estava
fazendo:

```
antes:  regras 26 e 27
depois: regras 28 e 27      ← o 27 não vinha precedido de "regra"
```

A busca casava `regra 26` e não casava o `27` que vinha logo depois, na mesma
frase. **Meio renumerado é pior que não ter mexido**: some o sinal de que há algo
errado, e o documento fica plausível e falso.

Portanto:

- Monte o **mapa completo** de origem → destino antes de tocar em qualquer
  arquivo.
- Aplique **por número**, não por ocorrência: todo `26` daquele domínio vira
  `28`, esteja ele precedido de "regra", de vírgula, de "e", ou de nada.
- Cuidado com a ordem: remapear `26→28` e depois `28→30` transforma o primeiro
  duas vezes. Remapeie em **uma passada**, ou para nomes temporários.
- Confira a contagem no fim. Se antes havia 41 citações e depois há 39, duas
  viraram outra coisa.

## 4. O que o pacote garante, e o que ele não garante

**Garante:** a varredura de trabalho anterior (`already_exists.py`) não presume
largura de número. Ela aceita `CAM-025`, `CAM-1091`, `CAM-1234567` e
`IDN-20260912`. Um teto escolhido por conforto é defeito agendado — a primeira
correção pôs `\d{2,6}` e já estava errada, só que mais tarde.

**Não garante:** que o identificador citado exista. Ela devolve documento que
existe com aquele nome; citação inventada não vira dona de nada.

**Não define:** o formato. Se o seu projeto mudar a convenção, mude o
`docs/specs/README.md` — é de lá que os steps leem.
