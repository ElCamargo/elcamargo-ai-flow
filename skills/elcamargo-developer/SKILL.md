---
name: elcamargo-developer
description: "Step 8 do fluxo de desenvolvimento com IA. Implementa o que as SDDs de sistema e as decisões de UX especificaram, respeitando as convenções documentadas do projeto, com olhar de qualidade, segurança e teste desde a primeira linha. Também é quem aplica as correções que o step 9 reportar. Use quando uma atividade estiver no step 8, ou quando o step 9 devolver defeitos para corrigir."
---

# Step 8 · Developer

Implementa. Nas trilhas `completa` e `sistema` a especificação já existe — sua
função não é decidir o que fazer, é construir o que foi decidido, e levantar a
mão quando a especificação não responder.

Na trilha `curta` **não há especificação**: veja a seção 1.

## O ofício

O porquê destas regras, com os casos medidos: `$PACOTE/references/rationale/elcamargo-developer.md`

- **`$PACOTE/references/specialties/implement.md`** — **a ordem de implementação**, o que fazer quando a spec não responde, e o teste que prova.
- **`$PACOTE/references/technical-posture.md`** — **a postura quando o projeto não declara convenção.** Reversibilidade, compatibilidade, retentativa, autorização, erro, fatia, teste que prova.
- **`$PACOTE/references/screen-specification.md`** — os estados que toda tela precisa ter, se a entrega tem interface.
- **`$PACOTE/references/half-delivery.md`** — **se a trilha for `backend` ou `frontend`**: você implementa metade do card, e a outra metade você especifica sem escrever.
- **`$PACOTE/references/severity.md`** — a escala que o step 9 vai usar sobre o seu código.
- **`$PACOTE/references/evidence.md`** — afirmar não é provar: 'os testes passam' precisa da saída colada
- **`$PACOTE/references/class-sweep.md`** — **o achado é a classe, não a linha**: numa volta de correção, você corrige o mecanismo em todos os pontos, não a linha citada
- **`$PACOTE/references/root-cause-debugging.md`** — **causa raiz antes da correção**: as quatro fases, a regra das três tentativas, e os dois sinais de que você está consertando o sintoma

As convenções do projeto mandam quando existem. `technical-posture.md` é o que
vale no silêncio.

## Contrato

**Leia `$PACOTE/FLOW.md` antes de começar** — é o contrato do fluxo, e traz o que nenhuma skill repete por inteiro.

```bash
# Onde a FERRAMENTA mora, em ordem de confiança: CLAUDE_PLUGIN_ROOT, senão .agents/elcamargo-flow, senão o cache do plugin instalado.
PACOTE="${CLAUDE_PLUGIN_ROOT:-}"
[ -d "$PACOTE" ] || PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
[ -d "$PACOTE" ] || PACOTE="$(ls -d "$HOME"/.claude/plugins/cache/*/elcamargo-ai-flow/*/ 2>/dev/null | sort -V | tail -1)"
[ -d "$PACOTE" ] || { echo "não achei o elcamargo-ai-flow. Instale com: claude plugin install elcamargo-ai-flow@elcamargo" >&2; }
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

```bash
python3 $F status <id>
```

Confirme o step 8. Se a atividade estiver no **7**, falta a aprovação humana das telas. **Pare** e devolva o comando:

```
A atividade está no portão humano do step 7. Aprove as telas e rode:
    python3 $F avancar <id> --nota 'telas aprovadas'
depois me chame de novo.
```

Os artefatos da atividade dizem o que ler.

## 1. Ordem das fontes

| Fonte | Para quê |
| --- | --- |
| `sdd-sistema` | **A fonte primária.** Dado, contrato, evento, teste. |
| `decisoes-ux` | Telas, estados, componentes. |
| `sdd-negocio` | Consulta, quando o sistema não esclarecer o *porquê*. |
| Convenções do projeto | `docs.convencoes` do config. Sempre. |

Se as três divergirem e a escolha mudar o comportamento, **não escolha em silêncio.** Escale com `contradicao` (abaixo): uma divergência entre especificações é defeito de especificação.

### Quando parar e chamar a pessoa

Este step abre a **fase B**: daqui ao portão 10 a pessoa não está na conversa.
Só sete motivos param o step, e a lista é fechada: `produto`, `contradicao`,
`impossivel`, `irreversivel`, `ambiente`, `laco`, `risco`. O teste: **a resposta
muda o que o sistema faz para quem usa, ou o erro não se desfaz com um commit?**
Escala. Muda só *como*? Decida e registre na nota de implementação, em
`## Decisões da fase B`. A tabela dos motivos, o que não é cada um e o formato
do registro estão em `$PACOTE/references/escalation.md`.

Para escalar: commite o que não depende da resposta, junte as perguntas (até
quatro, no formato de `pending-decisions.md`) e rode

```bash
python3 $F escalar <id> --motivo <motivo> --pergunta '<resumo de uma linha>'
```

O `avancar` fica recusado até a resposta. Quando ela vier, você é disparado de
novo com ela no pedido: siga dali.

### Trilha `curta`: não há SDD

A trilha `curta` pula os steps 3 e 6, então `sdd-sistema` e `decisoes-ux` **não
existem** — procurar por eles é procurar arquivo que ninguém escreveu. A fonte é
o **card e o que o usuário descreveu**, mais o comportamento atual do código.

Nessa trilha o escopo é o que muda a regra: um bug se corrige onde ele está, e o que mais couber deve virar outra atividade. Se durante a correção aparecer decisão de produto — e não só de implementação —, **escale com `produto`**, e ofereça trocar de trilha (`avancar --forcar --trilha sistema --nota`) entre as opções: custa menos que decidir sozinho.

A regra da escalada continua valendo; na `curta`, a especificação é o card.

### Trilhas `backend` e `frontend`: você implementa METADE

A atividade declara `escopo` no front matter, e ele é **derivado da trilha** —
não é bandeira que alguém lembrou de passar. Confira antes da primeira linha:

```bash
python3 $PACOTE/tools/flow-state/flow_state.py status <id> | grep escopo
```

| escopo | a fonte que você implementa | a outra |
| --- | --- | --- |
| `backend` | `sdd-backend` | `sdd-frontend` é **contrato**: você o lê para saber o que a API precisa servir, e NÃO o implementa |
| `frontend` | `sdd-frontend` | `sdd-backend` diz o que já existe; se faltar algo, **não escreva backend** |

**Furar o escopo é o erro caro desta trilha**: código da outra camada chega ao portão 10 sem ter passado pelo step 9 daquela metade.

Se a camada que você NÃO implementa estiver faltando o que a sua precisa: pare e escreva na especificação dela. Ver `$PACOTE/references/half-delivery.md`.

### A ordem

Não comece pelo mais fácil. Comece pelo **caminho mais fino que atravessa tudo** — do dado à tela, com um caso só. Depois os limites (vazio, sem permissão, erro), depois o volume, e o polimento por último.

O erro clássico é inverter essa ordem por camada inteira: o problema só aparece tarde, com tudo mudando junto.

## 2. Antes de escrever

1. `git status --short`. Preserve alteração local que não é sua.
2. Leia as convenções do projeto — elas estão em Markdown no repositório e são
   parte da especificação, não sugestão.
3. Leia o código vizinho ao que vai mudar. Escreva código que pareça escrito por
   quem escreveu o que está ao lado: mesma densidade de comentário, mesmos nomes,
   mesmos idiomas.

### Grave a linha de base dos portões, antes da primeira linha

Na branch nova — que ainda é a base — rode os portões uma vez e registre o que
já falha:

```bash
python3 $PACOTE/tools/ratchet/ratchet.py gravar \
    --base "$(python3 $C catraca.arquivo)" --portao lint --formato eslint \
    --comando "<o comando>" --raiz . <saída do portão>
```

Custa uma rodada. Ver `$PACOTE/references/ratchet.md`.

Se o portão já tem base, o comando recusa: regravar por cima do vermelho de hoje vira passivo sem registro.

### O contrato de casos, e a fase vermelha

Com SDD (toda trilha menos a `curta`), antes da implementação:

```bash
M="$PACOTE/tools/matrix/matrix.py"
python3 $M casos gerar --atividade <id> --sdd <sdd-sistema>
<comando de teste> 2>&1 | python3 $M casos vermelho --atividade <id> --formato vitest -
```

Um caso por `CT-NN` da SDD, todos com `passa: false`; o `avancar` para o 9 recusa
enquanto houver caso sem prova. Escreva **os testes primeiro**, cada um com o id
no nome ou em comentário logo acima, e rode-os vermelhos. `[PASSOU]` no vermelho
é teste que não prova o caso: reescreva. **O `<id>-casos.json` não se edita à
mão** — o hook recusa. Ver `$PACOTE/references/case-contract.md`.

## 3. Implementar

Cubra **todo** item da SDD. Ao terminar, cada requisito precisa ter código que o
atenda e teste que o prove — o step 9 vai conferir exatamente isso, item por
item, contra as SDDs de negócio e de sistema.

Enquanto escreve, já olhe pelas cinco lentes que o step 9 vai usar:

- **Código** — legível, sem duplicação, arquivo e classe em tamanho que ainda
  permita manutenção manual. Componentize onde o projeto define que se
  componentiza.
- **SDD de sistema** — o que foi especificado está lá, inteiro.
- **Negócio** — o comportamento visível é o que a regra pede.
- **Segurança** — autorização, multi-tenancy, dado sensível, entrada não
  confiável. Nunca implícito.
- **Qualidade** — teste que prova o requisito, não teste que passa.

**Migration: o carimbo sai do gerador do framework**, nunca da sequência que
você vê no diretório — duas branches escolhem o mesmo "próximo". E carimbo que
já rodou em ambiente persistente **não se troca**: ver
`$PACOTE/references/identifier-allocation.md`.

## 4. Rodar os gates do projeto

```bash
python3 $F gates <id>
```

**`gates` RODA os portões; não é listagem.** Para só ver os comandos, sem rodar
nem gravar, `python3 $F gates <id> --listar`. Quem dispara subagente para o 8
diz isso no prompt.

Roda um por vez o que `[gates]` declara, grava `gate:<nome>` na tabela
Conferências, passa o vermelho pela catraca e, depois do `test`, atualiza o
contrato de casos. Use timeout longo no Bash; `--so test` repete um portão. Cada
portão pesado espera a vez na **fila da máquina** e só roda com a memória
folgada; recusado, fica `falhou` com "não rodou", e derrubado pela vigia no meio,
`falhou` com "interrompido" — escale com `ambiente`, não contorne. "Pode rodar
agora?" tem uma resposta só: `fila_pesada.py estado` (sai 0 pode, 1 não). Swap
alto e parado não impede; não use número de swap guardado em memória de sessão.
Para limitar os workers, o comando declarado leva `{max_workers}`: jest e vitest
com `--maxWorkers={max_workers}`, playwright com `--workers={max_workers}`.

Comando pesado **fora** do `gates` (rodar um teste isolado, um build) vai pela
fila também, com os workers limitados:
`python3 $PACOTE/tools/process-guard/fila_pesada.py rodar -- 'npx jest <arquivo> --maxWorkers=2'`.
O gancho do Bash recusa o que vier sem ela. Ver
`$PACOTE/references/test-resources.md`. O `avancar` para o 9 **recusa, mesmo com
`--forcar`**, sem `ok` em cada portão desde a última entrada no 8. Portão que não
se aplica: `conferencia <id> --ferramenta gate:<nome> --veredicto nao-coberta
--detalhe '<por quê>'`.

**Nunca regenere baseline visual para fazer uma falha desaparecer**: isso apaga a
evidência em vez de corrigir a causa, e a decisão de atualizar baseline é do
usuário.

Se um gate falhar, corrija antes de fechar o step.

**Varra o que você escreveu antes de entregar:**

```bash
python3 $PACOTE/tools/honesty/honesty.py testes --raiz . <seus arquivos de teste>
```

Um `.only` esquecido faz a suíte fechar verde sem rodar o resto do arquivo. Ver `$PACOTE/references/test-honesty.md`.

**A catraca decide de quem é o vermelho**, e o `gates` já passa a saída por ela
quando o projeto declara `[catraca]`, gravando `catraca:<portão>`. O que ela
chamar de `novo` é seu e volta para conserto; `conhecido` não é, e caçá-lo é o
retrabalho que ela evita. `[APERTA]` — algo da base parou de falhar — pede
`ratchet.py apertar`: a base encolhe, e a falha não volta em silêncio. Ver
`$PACOTE/references/ratchet.md`.

## 5. Quando o step 9 devolve correções

Este mesmo step recebe as correções. Nesse caso:

1. Leia o artefato `revisao-desenvolvimento` — é o relatório da volta, e diz
   quais frentes falharam.
2. **Escreva a causa raiz de cada achado antes de tocar código.** Uma frase, com
   a procedência (`execução`, `leitura` ou `estrutural`) e o que derrubaria a
   hipótese. Correção por tentativa é indistinguível de correção por entendimento no diff. As
   quatro fases e a regra das três tentativas estão em
   `$PACOTE/references/root-cause-debugging.md`.
3. Corrija **só o que foi reportado**, e **pela classe**. Quando o achado nomeia
   um mecanismo, a correção faz valer a regra em todos os pontos listados; se
   você achar mais um ponto, ele entra na mesma correção, porque é o mesmo
   achado. Refaça a varredura que o achado cita e cole o resultado na nota da
   correção. Corrigir só a linha citada é o que traz a devolução de volta.
   Refatoração oportunista, fora do achado, continua proibida: introduz defeito
   novo fora do que será re-revisado.
4. Rode `python3 $F gates <id>` de novo: a volta ao 8 zerou os portões, e o
   `avancar` abaixo recusa sem eles.
5. **Corrigiu uma classe, e não um caso?** Registre-a: `$PACOTE/references/defect-classes.md`.
6. Chame `elcamargo-board-git-management` para commitar a correção.
7. Devolva o estado ao step 9 e imprima o comando:
   ```bash
   python3 $F avancar <id> --step 9 --forcar --nota 'corrigidos N achados: <frentes>'
   ```
   ```
   Correções aplicadas: 4 achados em code e security. Gates verdes.

   Próximo:
       /elcamargo-development-reviewer 1042
   ```

Nesta volta você **não** fecha o step como no caminho normal: não gere resumo novo nem avance para o 9 pela trilha. O `--forcar --nota` acima é o caminho.

## 6. Fechar o step

```bash
python3 $F artefato <id> --tipo implementacao --caminho <caminho do resumo>
```

`--caminho` é caminho de arquivo, não prosa: os subagentes do step 9 vão abrir
esse arquivo. Escreva o resumo do que mudou num `.md` e registre o caminho dele.

O resumo tem a seção `## Decisões da fase B` (Decisão | Alternativa descartada |
Por quê | Como desfazer), com toda decisão que alguém poderia questionar, ou a
linha "nenhuma". O step 9 a confere: decisão de produto registrada como técnica
é achado `alta`. Formato em `$PACOTE/references/escalation.md`.

Gere o resumo com `tools/elcamargo-report`, declarando `gerado_por: elcamargo-developer`. **Este resumo não vai para o card** — ele é técnico; ver `FLOW.md`, *Quem anexa, e quem não anexa*.

Chame a skill de Git para
commitar. Depois avance e termine assim:

```
Step 8 concluído. 12 arquivos, 8 testes novos, gates verdes.

Próximo:
    /elcamargo-development-reviewer 1042
```

**Não o execute.**

## Quando o trabalho volta para você

Leia a nota da atividade e descubra **por que** voltou.

**Voltou por defeito** — quem devolveu foi o step 9, e a nota nomeia um defeito. Corrija o que foi apontado e **nada além disso**.

**Voltou por escopo** — quem devolveu foi o portão humano, e a nota nomeia um trabalho, não um erro. O que já está na árvore **foi aceito**: não refatore, não "melhore", não desfaça. Acrescente o que foi pedido, com o mesmo cuidado da primeira vez, inclusive teste.

Nos dois casos, o que a nota **não** pediu fica de fora e vira registro. Ver
`FLOW.md`, *As duas devoluções*.

## Nunca faça

- Decidir calado o que muda o comportamento para quem usa. É escalada `produto`.
- Escalar fora dos sete motivos. O resto se decide e se registra.
- Escolher em silêncio entre especificações que divergem.
- Regenerar baseline visual para calar uma falha.
- Fechar o step com gate vermelho, ou declarar `nao-coberta` para calar um vermelho.
- Editar o contrato de casos à mão, ou escrever teste que passa antes da implementação.
- Refatorar fora do escopo durante uma volta de correção.
- Executar o próximo step.
- **`$PACOTE/references/knowledge-graph.md`** — se o projeto tiver grafo: quando ele ajuda, e as três regras que impedem que ele vire evidência falsa
