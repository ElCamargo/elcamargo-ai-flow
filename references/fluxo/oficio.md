# Fluxo · O manual do ofício

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## O manual do ofício

`references/` guarda o que os componentes precisam **saber** — separado do que
eles precisam **fazer**, que é o SKILL.md de cada um.

| Referência | O que ensina | Quem lê |
| --- | --- | --- |
| `review-lens.md` | O banco de perguntas, por tema | 2, 3, 4, `implemented-business-reviewer` |
| `traceability.md` | A matriz que não mente, e os sete estados | 2, 3, 4 |
| `pending-decisions.md` | Como escrever uma pendência decidível | 2, 3, 4, 6 |
| `technical-posture.md` | Como decidir quando o projeto não declara nada | 3, 8, `code-reviewer`, `quality-reviewer`, `security-reviewer` |
| `screen-specification.md` | O que é uma tela especificada | 6, 8, `figma-reader`, `screen-drawer` |
| `writing-requirements.md` | A gramática que torna um requisito testável | 2, 3 |
| `severity.md` | A mesma escala em todos os revisores | 4, 9 e os seis revisores |
| `check-first.md` | As três verificações que vêm antes de abrir a atividade | 1 |
| `rejection-memory.md` | O que o produto já decidiu não fazer | 1, 2, 3 |
| `build-memory.md` | O que o produto já construiu, e por que a divergência é o achado | 2, 3 |
| `evidence.md` | Afirmar não é provar — vale para quem produz, não só para quem revisa | 2, 3, 6, 8, 9 e todos os revisores |
| `knowledge-graph.md` | Quando um grafo do repositório ajuda, e as três regras que impedem que ele vire evidência falsa | 3, 8 |
| `capacidades.md` | Poder e política são eixos diferentes: o que a máquina consegue e o que o projeto quer, e por que escrever no Figma nasce desligado | 6, e quem for ligar ou desligar uma ação |
| `card-attachment.md` | O que vai ao card e o que fica no repositório, e as três falhas que moldaram o `attach.py` | 2, 3, 6, 9 |
| `work-tree.md` | A árvore do step 9 é compartilhada: quem pode escrever nela, quem não pode, e o que a conferência não prova | 9, `quality-reviewer`, `runtime-reviewer` |
| `metrics.md` | O que a métrica mede, os quatro erros de atribuição que a moldaram, e o que ela NÃO prova | 9, e quem cita qualquer número do painel |
| `root-cause-debugging.md` | Causa raiz antes da correção: as quatro fases, a regra das três tentativas, e o que uma correção precisa deixar escrito | 8, 9, `code-reviewer` |
| `half-delivery.md` | Um card em duas metades: cada uma especifica as duas camadas e implementa uma, e o contrato se prova por execução | 1, 3, 4, 8, 9, quando a trilha é `backend` ou `frontend` |
| `documents-in-context.md` | CPF e CNPJ nunca por extenso num contexto, e por que o 403 do guardrail não se retoma | os dez agentes, e quem dispara step ou frente |
| `shadow-leg.md` | A perna sombra: uma frente do step 9 em dois modelos, com o mesmo prompt, e o critério que decide se ela desce de modelo | step 9, com `capacidades.perna_sombra` |
| `defect-classes.md` | O registro das classes de defeito que escaparam da revisão: o formato, quem confere e quem acrescenta | steps 8 e 9, e as seis frentes do 9 |

E `references/specialties/`, que é o que faz de cada subagente um
especialista em vez de um leitor de checklist:

| Especialidade | Quem lê |
| --- | --- |
| `code-review.md` | `code-reviewer` |
| `security.md` | `security-reviewer` |
| `test-and-quality.md` | `quality-reviewer` |
| `screen-design.md` | `screen-drawer`, `figma-reader` |
| `implementation-check.md` | `implemented-sdd-reviewer`, `implemented-business-reviewer` |
| `system-usage.md` | `runtime-reviewer` |
| `evidence.md` (compartilhada) | `business-analysis-auditor` |
| `executable-prototype.md` | `screen-drawer`, step 6 |
| `figma-reading.md` | `figma-reader` |
| `figma-writing.md` | `ux-reviewer`, `screen-drawer` |
| `implement.md` | step 8 |

Seis revisores só valem mais que um se cada um souber de fato a sua frente. Sem
isso, são seis leituras genéricas do mesmo diff, e a paralelização custa seis
vezes para entregar o mesmo.

A separação existe por dois motivos. O primeiro é que vários ofícios se repetem:
"como escrever uma decisão que alguém consegue decidir" serve a cinco
componentes, e duplicá-la em cinco arquivos garante que as cinco cópias divirjam.

O segundo é o que faz o pacote valer fora daqui. **Sem essas referências, um
componente sabe o procedimento e não sabe o ofício** — segue o checklist e
entrega algo que passa nos portões sem ser bom. Num projeto que já tem skill
complementar isso não aparece, porque a skill do projeto cobre o buraco. Num
projeto novo, aparece na primeira atividade.
