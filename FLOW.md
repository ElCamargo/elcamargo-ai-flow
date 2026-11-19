# Fluxo de trabalho com IA — o núcleo

Este é o contrato do fluxo, na parte que **todo** step precisa. O resto mora em
`references/fluxo/`, e se lê quando o step precisa daquilo — o índice no fim
diz onde está cada regra. Uma remissão *"Ver `FLOW.md`, \*Título\*"* se resolve
por esse índice.

Até a 2.67.0 este arquivo tinha ~29 mil tokens e toda skill o lia inteiro antes
de começar. Medido de 02 a 15/11/2026, o `step-runner` respondia com 103 mil de
contexto médio e era 46% do custo. O núcleo existe para que um step nasça leve.

A definição legível por máquina está em `tools/flow-state/flow_state.py`
(`STEPS` e `TRILHAS`). Se os dois divergirem, o script vence — e o texto precisa
ser corrigido.

## Princípio

**O handoff entre steps é por arquivo, nunca por contexto de conversa.** Um step
lê arquivos, escreve arquivos e termina. O seguinte recebe o artefato, não o
raciocínio. É o que permite pausar por dias e retomar em outra sessão ou
worktree.

- **Um step por subagente**, do tipo `elcamargo-step-runner`, nunca um agente
  conduzindo vários. É a regra que mais pesa no custo (`subagentes.md`, *O que
  custa é o contexto acumulado*).
- **A fase A corre numa conversa.** A janela emenda os steps do 1 ao portão 7,
  leva cada pergunta em cards e **retoma o mesmo runner** com a resposta
  (`SendMessage`), em vez de redisparar. Detalhe: a porta, §4.
- **Quem dispara frente dispara bloqueando** (`run_in_background: false`). Em
  segundo plano a notificação não alcança quem está dentro de um subagente.
- **Documento não viaja.** CPF ou CNPJ por extenso num contexto faz toda chamada
  seguinte voltar com o 403 do guardrail (`references/documents-in-context.md`).

## Os steps

| # | Cargo | Componente | Entrega |
| --- | --- | --- | --- |
| 1 | Gestor da Atividade | `elcamargo-board-git-management` | Card lido, trilha decidida, atividade aberta |
| 2 | Revisor da Análise de Negócio | `elcamargo-business-analysis-reviewer` | Relatório ao analista + SDD de negócio |
| 3 | Analista de Sistema | `elcamargo-system-analyst` | SDD de sistema, já conferida contra o negócio |
| 4 | Revisor da Especificação | `elcamargo-system-analysis-reviewer` | Só na trilha `revisao`: a SDD de outra pessoa cobre o card? |
| 5 | **Portão humano · Especificação** | pessoa | A spec descreve o produto certo? |
| 6 | Revisor de UX | `elcamargo-ux-reviewer` | Decisões de tela documentadas |
| 7 | **Portão humano · Telas** | pessoa | O visual está certo? |
| 8 | Desenvolvedor | `elcamargo-developer` | Implementação, com os gates verdes |
| 9 | Revisor da Entrega | `elcamargo-development-reviewer` | Revisão em frentes + correções aplicadas |
| 10 | **Portão humano · Entrega** | pessoa | Está aceito? |

Desde a 2.69.0 a conferência da SDD (o antigo step 4) roda dentro do 3, num
subagente de contexto limpo, e o 3 entrega direto o portão 5. Nem toda trilha
passa por todos; `python3 $F fluxo` lista as trilhas e o
`status` diz o próximo. Trilhas e risco: `trilhas.md`.

**Portões.** Uma skill nunca atravessa um portão por conta própria: quem
atravessa é a pessoa, rodando o `avancar` ou clicando a opção de aprovação no
card do portão; só com esse clique a janela que conduz roda o `avancar`. A
skill que termina num portão imprime o comando exato; a do step seguinte, se
achar a atividade parada no portão, recusa começar e reimprime o comando.

**O portão chega como pergunta, nunca como leitura.** No máximo quatro cards
clicáveis, uma decisão por card, opções reais conferidas no código, a
consequência de cada uma e a sua recomendação. A aprovação é a última pergunta,
não a única. Na segunda passagem, rode `flow_state.py desde-aprovacao <id>` e
pergunte só o que saiu `[mudou]` ou `[novo]`. Detalhe: `steps.md`.

**Decisão achada no meio do caminho não espera o portão.** Traga na hora, uma a
uma, com opções que existem de fato, e siga com o que não depende dela. Se
nenhum artefato ia responder aquilo, é pergunta, não pressuposto.

**Na fase B (do step 8 ao portão 10) a lista é fechada.** Só sete motivos param
o step e chamam a pessoa, com `flow_state.py escalar`; fora deles, o step decide
e registra em `## Decisões da fase B`. O teste: muda o que o sistema faz para
quem usa, ou não se desfaz com um commit? Escala. Detalhe: `escalation.md`.

**Fale de cada step pelo cargo**, com o número junto: `9 · Revisor da Entrega`,
não `step 9`. O endereço (`elcamargo-...`) só aparece onde é acionável — no
comando.

## Obrigações de todo step de skill

Antes de tudo, este bloco, literalmente — ele acha o pacote de qualquer lugar,
worktree inclusive:

```bash
PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

1. Lê o estado (`python3 $F status <id>`) e confirma que o step é o dele.
2. Produz os artefatos em Markdown, no local que o `config.toml` define.
3. Registra cada artefato com `python3 $F artefato <id> --tipo ... --caminho ...`.
4. Roda o subagente de completude, quando tiver um, **antes** de commitar.
5. Emite o relatório de fronteira humana com `tools/elcamargo-report`, quando
   o step previr.
6. Chama a skill de Git do projeto para commitar.
7. Roda `python3 $F avancar <id> --nota '...'` e **entrega** o próximo step — sem
   executá-lo.

E quatro hábitos, que custaram caro cada um (`obrigacoes.md`):

- **Disparar não é terminar.** Quem dispara subagente espera por ele e
  consolida. Se ele não voltar, nomeie quem faltou e declare a entrega
  incompleta naquela dimensão.
- **Todo retorno passa por uma conferência de segundos:** o artefato existe? o
  comando que ele diz ter rodado passa? a afirmação que sustenta tudo é verdade?
  E conte: pediu seis, voltaram seis?
- **Persista enquanto trabalha.** Retorno bruto de cada subagente vai para um
  rascunho assim que chega. O que mora só no contexto morre com ele.
- **Quem não escreve há muito tempo está travado**, não pensando. Vigie com
  `tools/watch/watch.py`; mate, recolha e redispare dizendo de onde continuar.

**Texto livre vai entre aspas SIMPLES** em toda flag de prosa (`--nota`,
`--comentario`, `--titulo`, `--motivo`, `--detalhe`, `--admitir`). Entre
duplas, a crase vira substituição de comando e a palavra some calada. Com
apóstrofo, passe por variável: `--nota "$NOTA"`.

## A entrega entre steps

O step termina imprimindo o comando do próximo, e oferece o disparo como card
clicável dizendo o que o próximo vai fazer. **Não o executa.** O próximo roda em
contexto novo — sessão nova ou subagente —, porque precisa ler a SDD, e não o
raciocínio de quem a escreveu. Entre o 8 e o 9 isso é trava: o `avancar` para o
10 recusa quando o mesmo contexto fez os dois.

**Markdown é o formato canônico.** PDF e DOCX são exportação, só na fronteira
com humano. Documento que sai para o cliente leva `gerado_por:` (a skill) e o
`operador` do config (a pessoa).

## Onde está o resto

Leia a parte quando o step precisar dela, não antes. Todos em
`$PACOTE/references/fluxo/`.

| Arquivo | Seções |
| --- | --- |
| `steps.md` | **Os steps**; *Os três portões, e o que cada um compra*; *Decisão encontrada no meio do caminho não espera o portão*; *O portão humano chega como pergunta, nunca como leitura*; *O que o pacote garante, e o que depende de a skill ler isto*; *Chame cada step pelo cargo, e não pelo número*; *A passagem de step também é um clique*; *O portão 10 valida em homologação, e é decisão sua*; *O subagente de completude é o componente de maior valor*; *Steps 3 e 4 revisam coisas diferentes* |
| `trilhas.md` | **As trilhas**; *A trilha `revisao` — conferir o trabalho de outra pessoa*; *A trilha `rapida` — o Fluxo Rápido*; *O par `especificacao-*` → `construcao` — quando quem analisa não é quem constrói*; *A trilha `ultra-rapida` — pedida pela gerência, e o pacote não a recomenda*; *As trilhas `backend` e `frontend` — um card, duas entregas*; *O risco — o segundo eixo* |
| `subagentes.md` | **Os subagentes**; *O que custa é o contexto acumulado*; *Quem dispara subagente dispara bloqueando*; *As seis do step 9 rodam em levas, e não todas de uma vez*; *Duas delas escrevem, e por isso rodam em árvore própria*; *O que o step 6 entrega*; *Duas voltas entre quem faz e quem revisa. Em todo par.*; *O laço de correção do step 9* |
| `devolucoes.md` | **As duas devoluções**; *O step 4 tem saída, não limite*; *O crescimento precisa ficar visível* |
| `estado.md` | **Estado da atividade**; *Como uma skill acha o pacote*; *O lugar da atividade se preserva, e só muda por comando*; *O `iniciar` NÃO deriva o lugar do diretório*; *Texto livre vai entre aspas SIMPLES*; *Comandos*; *Vocabulário dos artefatos*; *As métricas se atualizam sozinhas* |
| `pacote.md` | **O pacote nunca se impõe**; **Capacidades: descubra antes de precisar**; *Ler o Figma é REST, e não MCP*; **Antes de abrir a atividade**; **A memória de rejeição**; **Especificação é documento de vida longa** |
| `anexar.md` | **Anexar é ação verificada**; *Verificar que subiu é do step, não do usuário*; *O card recebe pergunta, não relatório*; *Arquivo renomeado no meio da atividade* |
| `oficio.md` | **O manual do ofício** |
| `maquina.md` | **O que é da máquina**; *E o que é opcional*; **A conferência mecânica deixa rastro, e o `concluir` lê o rastro**; *O step 8 não passa para o 9 com portão vermelho* |
| `obrigacoes.md` | **Obrigações de todo step de skill**; *Disparar não é terminar*; *Todo retorno passa por uma conferência de segundos*; *Persista enquanto trabalha, não no fim*; *Um step que não escreve há muito tempo não está pensando*; **A entrega entre steps**; **Autoria dos documentos**; **Skills complementares do projeto**; **Formato dos artefatos**; **Configuração do projeto** |

As demais referências temáticas (`traceability.md`, `severity.md`,
`case-contract.md`, `model-policy.md`…) ficam em `$PACOTE/references/`, e cada
skill aponta as que usa.
