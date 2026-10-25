# hooks

`hooks.json` é carregado **por convenção** — o plugin não declara no manifesto.

Declarar `"hooks": "./hooks/hooks.json"` em `.claude-plugin/plugin.json` faz o
mesmo arquivo ser carregado duas vezes, e a instalação falha com
`Duplicate hooks file detected`. O campo do manifesto existe para apontar
arquivos **adicionais**, não para o padrão.

Isso passou pelo `claude plugin validate` sem um aviso sequer, nas duas
validações, inclusive `--strict`. O erro só apareceu no `plugin list`, depois de
instalado.

## O que roda em cada gancho

| Gancho | Ferramenta | Para quê |
| --- | --- | --- |
| `UserPromptSubmit` | `anchor`, `orchestrator-guard` | âncora do projeto e guarda do orquestrador |
| `PreToolUse` | `orchestrator-guard` | antes de cada ferramenta |
| `PreToolUse` (`Bash`) | `anchor --contexto` | grava sessão + subagente de quem vai chamar o `flow_state`; é o que a trava do step 9 compara |
| `SessionStart` (`resume\|compact`) | `orchestrator-guard retomou` | a janela voltou |
| `SessionStart` (`startup\|resume\|compact`) | `process_guard.py varrer --quieto` | contêiner e processo que a atividade anterior deixou de pé |

Quem instala pelo `install.sh`, e não como plugin, recebe as duas entradas da
`anchor` em `.claude/settings.local.json` (desde 2.63.0). As outras linhas são
só do plugin.

### Por que a varredura mora num gancho, e não só na skill

A conferência `sobra` roda ao consolidar, e as três atividades que travaram o
Mac em 02/10/2026 **nunca consolidaram**: as sessões morreram antes. Dez
contêineres e treze processos sobreviveram dois dias a elas, com 5,2 dos 6 GB
de swap em uso numa máquina de 16 GB.

Conferência que depende da atividade estar viva não cobre o modo de falha mais
comum deste fluxo, que é a janela ser fechada no meio. Quem encontra essa sobra
é a **janela seguinte** — daí o `startup` no matcher.

`--quieto` cala quando não há sobra e responde `0` sempre, inclusive fora de um
projeto do fluxo. Achar sobra não é erro da sessão que está abrindo: é recado
sobre a que morreu. Gancho que pinta de vermelho toda abertura de janela é
gancho que alguém desliga.
