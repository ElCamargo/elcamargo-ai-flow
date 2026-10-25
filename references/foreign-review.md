# Revisar o trabalho de outra pessoa

Lida por: steps 1, 2, 4 e 9, **quando a trilha é `revisao`**.

O cenário que originou este arquivo: *"preciso revisar o trabalho de outro dev,
em outro card dele, onde não sei se ele revisou negócio, se especificou, se leu
Figma, se implementou certo e se ficou com a qualidade que queremos — sem eu ter
que refazer o trabalho todo."*

A trilha é `1 → 2 → 4 → 9 → 10`. Ela não produz software: confere o que já foi
entregue contra o que o card pediu.

## 1. O card é a âncora, e é o único que não é trabalho do dev

Numa atividade normal, o step 9 confere o código contra as SDDs que o próprio
fluxo produziu. Aqui essas SDDs ou não existem, ou foram escritas pela pessoa
que você está revisando.

**Conferir o código contra a SDD do próprio dev só prova coerência interna.** Se
a SDD leu o card errado, o código implementa a leitura errada com fidelidade e
todas as frentes passam. É o mesmo buraco que faz o fluxo normal ter duas
frentes separadas — uma contra a SDD e outra contra o negócio:

> Um requisito pode atravessar a especificação de sistema **traduzido errado** e
> ser implementado com fidelidade à tradução errada. Quem confere contra a
> especificação de sistema não vê, porque confere contra o documento que já
> contém o erro.

Por isso o step 2 roda **sempre** nesta trilha, mesmo quando o dev escreveu
documentação: o card é a única peça do conjunto que não saiu das mãos dele.

## 2. Os três casos, e o que muda em cada um

O step 1 descobre em qual você está, e grava no histórico. **Por comando, não
por leitura:**

```bash
python3 $PACOTE/tools/prior-work/prior_work.py --base origin/<base-do-pr>
```

A ordem de custo é a da tabela — de baixo para cima.

| O que o dev deixou | Como descobrir | O que a trilha faz |
| --- | --- | --- |
| **Usou o AI Flow** | há arquivo em `.agents/atividades/` para o card, ou a branch tem os commits do fluxo | O step 2 continua produzindo a baseline, mas o step 4 confronta com a **tabela de Conferências** dele: o que foi conferido já está declarado, inclusive as `não-coberta`. O step 9 concentra as frentes no que ficou descoberto |
| **Escreveu SDDs fora do fluxo** | especificações no diff, ou citadas no card | O step 4 confere a SDD dele contra a baseline, item a item. É o caso mais caro: há documento a ler, e ele é **objeto de revisão, não fonte da verdade** |
| **Não escreveu nada** | nem uma coisa nem outra | O step 4 registra a ausência como achado — *"entregou sem especificar"* é informação para o portão 10 — e passa direto. O step 9 confere o código contra a baseline |

> [!atencao] A ausência de documento é achado, não obstáculo
> Um dev que entregou sem especificar não trava esta trilha. O que ele fez é
> conferível contra o card do mesmo jeito. O que muda é que ninguém pode dizer
> onde ele pretendia chegar — e isso vira linha do relatório, não desculpa para
> parar.

## 3. Onde ela roda: worktree da branch dele

**Nunca na árvore em que você está trabalhando.** Uma revisão que faz `checkout`
da branch de outra pessoa interrompe o que você estava implementando, e o step 9
tem duas frentes que escrevem no disco — a de qualidade insere mutantes no
código-fonte, a de execução cria fixtures e tokens.

```bash
git fetch origin
git worktree add ../revisao-<card> origin/<branch-do-dev>
```

A branch é dele; a worktree é sua. **Não crie branch nova, não commite, não faça
push, não force nada nessa árvore.** Se alguma frente precisar escrever, ela já
roda em árvore própria — ver `references/work-tree.md`.

E ao terminar, `git worktree remove`. Árvore esquecida é a próxima que alguém
confunde com a de verdade.

**A worktree é `detached`, e isso é de propósito** — você não cria branch, fica
no commit que o dev entregou. O pacote sabe disso: quando `rev-parse
--abbrev-ref HEAD` responde a string literal `HEAD`, ele cai para a referência
remota que aponta para o commit (`origin/feat/...`) e, se não houver nenhuma,
para o commit curto. **`branch: HEAD` não descreve lugar nenhum** — dois commits
diferentes gravariam o mesmo texto.

Pelo mesmo motivo, `corrigir --branch origin/feat/...` **não exige `--forcar`**:
a branch é do outro dev e existe aqui só como referência remota, que é o caso
normal desta trilha. Gastar a saída de emergência no caso normal ensina a usar
`--forcar` por hábito.

## 4. O que esta trilha não faz

**Não conserta.** Ela não tem step 8, então o step 9 não tem a quem devolver
correção. Isso não é limitação, é a forma: quem conserta é o dono do card, e
corrigir o código de alguém enquanto se revisa destrói a evidência do que estava
errado — a próxima leitura vê o conserto, não o defeito.

**Não escreve no card dele.** O relatório é seu. Publicar crítica no card de
outra pessoa, sem ela ter pedido, é decisão dela e não sua — e o step 1 sabe
disso: nesta trilha ele lê o board e não anexa nada.

**Não refaz a análise.** O step 2 aqui extrai o que dá para cobrar do card. Ele
não reescreve o produto nem propõe o que o card deveria ter pedido. Se o card
está mal escrito, isso é achado do relatório — não convite para especificar de
novo.

> [!erro] O `concluir` já deixou arquivo pronto para commit na árvore de outra
> pessoa
> Em 12/09/2026, numa revisão do PR 2210, o `concluir` regerou `README.md`,
> `docs/metricas.md` e `docs/metricas.html` e **indexou os três** — na worktree
> detached da branch da autora. Nenhum commit chegou a ser criado, mas o index
> estava montado e o comando oferecia o commit.
>
> Duas coisas erradas de uma vez: eram números **parciais** (a coleta rodava com
> a cobertura da worktree, 2 pastas de 13 — consertado na 2.30.0/2.32.0), e o
> resumo do projeto não é entregável desta trilha em nenhuma versão.
>
> Desde a **2.33.0** o `publicar` recusa em dois lugares, e **fala nos dois**:
> na trilha `revisao`, sempre; e em qualquer trilha quando a árvore de trabalho
> não é a principal. A medida continua sendo gravada em `.agents/`, que não é
> versionado — recusa-se **publicar**, não medir.

## 4.1. O vermelho desta trilha é o produto, não a dívida

`concluir` segura quando uma conferência mecânica ficou em `falhou` — **menos
aqui**. Nas trilhas que constroem, vermelho é dívida de quem encerra: alguém
ainda vai consertar. Nesta, o defeito **é o que você foi achar**.

O caso que produziu a regra, em 11/09/2026: uma revisão fechou com `perfis` em
`falhou`. Dos doze pares exercitados com ator e sessão reais, dez provaram o que
o perfil **não** pode, e os dois que falharam eram o bloqueador e uma alta — já
publicados no PR. **Não existia caminho que tornasse aquilo verde**, porque a
trilha não conserta, não commita e não faz push.

| Veredicto | Na `revisao` | Por quê |
| --- | --- | --- |
| `falhou` | **não trava**, mas exige `--nota` | é o achado, e ele tem endereço |
| `exigida` | **trava**, como em toda trilha | não diz "achei defeito", diz "ninguém rodou" |
| `nao-coberta` | passa e aparece | igual em toda trilha |

A nota precisa dizer **onde o achado foi publicado**: número do PR, da thread, do
card. E o `concluir` grava os vermelhos no histórico por conta própria, sem
depender de alguém escrever.

> [!erro] Não re-registre a conferência como `ok` para o comando passar
> É a saída mais fácil e a pior: apagaria do histórico o achado que a revisão
> existiu para produzir. Quem abrir a atividade depois veria uma revisão limpa
> sobre uma entrega que tinha bloqueador.

## 4.2. O entregável tem nome: `revisao-publicada`

O produto desta trilha é o relatório **entregue a quem é dono do card** — no PR,
na thread, no card. Registre-o como artefato, com o tipo certo:

```bash
python3 $PACOTE/tools/flow-state/flow_state.py artefato <id> \
    --tipo revisao-publicada --caminho <onde ele está>
```

`revisao-desenvolvimento` é outra coisa: é o relatório que o step 9 produz a cada
volta, e nas trilhas que constroem ele volta para o step 8. **Aqui não há step
8** — o relatório sai do fluxo, como o `relatorio-negocio` do step 2 sai para o
analista.

> [!atencao] Tipo que ninguém reconhece some para quem procura
> No primeiro uso da trilha o entregável foi registrado como `comentario-pr`, no
> chute, e o comando aceitou calado. O artefato ficou gravado e invisível para
> qualquer step que o procurasse pelo nome. Hoje o comando avisa e lista o
> vocabulário — mas continua registrando, porque perder o registro é pior que o
> rótulo errado.

## 5. O tamanho da revisão é o tamanho do diff

O step 9 medido em atividades reais gastou 10 a 12 agentes e 1.600 a 1.900
turnos. **Isso é hora de máquina, e ninguém deve prometer minutos.** O que
controla o custo é o diff e o número de frentes, não a trilha.

O que é curto é a **sua** hora: você lê o card, responde o portão 10, e pronto.
É o mesmo padrão do resto do fluxo — a espera humana medida na POC foi de ~10
min em 24 h de atividade.

Se a entrega for grande demais para uma passada, **dimensione antes de disparar**
— a mesma regra que o step 9 já aplica: fatiar é decisão declarada, não
desempate silencioso.

## 6. A frente de execução é o que salva esta trilha

Você conhece o diff e mais nada. É exatamente a posição em que gatilho por
arquivo erra — e erra na direção pior.

Isso já custou uma tela em homologação: `array_agg(opcao.label)` num adapter de
backend, coluna real `value`, `500` em toda chamada contra tenant real. **Zero
arquivos de frontend no diff**, e três frentes lendo código não acharam.

Aqui vale a regra do step 9 sem exceção: a frente de execução **roda sempre que
a entrega toca código de aplicação**, e "o diff não tem arquivo de frontend" não
dispensa nada. Se ela não subir, o resultado é `não-coberta` **escrito** — que
numa revisão de trabalho alheio é a diferença entre *"conferi e está bom"* e
*"não consegui conferir"*.
