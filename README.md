# Elcamargo AI Flow

Modelo de trabalho com IA: da análise de negócio até a entrega revisada, com
portões humanos nos pontos em que a decisão é de gente.

**Este repositório é a ferramenta.** Ele não conhece projeto nenhum: tudo que é
específico entra pelo `config.toml` de quem instala. O que mora aqui é doutrina,
skills, subagentes e ferramentas de comando — nunca estado de atividade.


- **[FLOW.md](FLOW.md)** — o contrato: os 9 steps, as 3 trilhas, as
  obrigações de cada skill. Comece por aí.
- **[config.example.toml](config.example.toml)** — o que cada projeto declara.


## Convenções

**Nome de arquivo e de pasta em inglês, sempre.** O conteúdo é em português;
o caminho é o que se digita, e a ferramenta pode ser usada fora daqui.

Isto **não** vale para chave de config (`[catraca]`, `[perfis]`, `[metricas]`),
nome de subcomando (`painel`, `superficie`) nem rótulo de conferência
(`--ferramenta perfis`). Esses são API: renomeá-los quebraria o `config.toml` e
os arquivos de atividade de todo projeto já instalado — e a única coisa que os
protege é esta linha estar escrita.

## O que tem aqui

```
elcamargo-flow/
├── FLOW.md                      o contrato do fluxo
├── config.example.toml          template do config de projeto
├── install.sh                   symlinks + validação
├── references/                  o manual do ofício — o que os componentes sabem
│   └── specialties/            o que cada subagente sabe da SUA frente
├── skills/                      7 — as que têm porta de entrada
│   ├── elcamargo-activity-management          step 1
│   ├── elcamargo-business-analysis-reviewer    step 2
│   ├── elcamargo-system-analyst                step 3
│   ├── elcamargo-system-analysis-reviewer      step 4
│   ├── elcamargo-ux-reviewer                   step 6
│   ├── elcamargo-developer                     step 8
│   └── elcamargo-development-reviewer          step 9
├── agents/                      7 — só rodam como subagente
│   ├── elcamargo-figma-reader                  ┐ step 6
│   ├── elcamargo-screen-drawer                 ┘
│   ├── elcamargo-code-reviewer                 ┐
│   ├── elcamargo-implemented-sdd-reviewer      │
│   ├── elcamargo-implemented-business-reviewer │ step 9, em paralelo
│   ├── elcamargo-security-reviewer             │
│   └── elcamargo-quality-reviewer              ┘
└── tools/                       17 ferramentas de conferência mecânica
    ├── flow-state/              estado da atividade + leitura do config
    ├── metrics/                 projeto → atividade → step → agente, e o painel
    ├── doctor/                  o config declara o que existe de verdade?
    ├── ratchet/                 falha nova bloqueia, conhecida não
    ├── outcome/                 o que aconteceu com cada achado
    ├── profiles/                o diff toca autorização? a passada prova?
    ├── honesty/                 `.only`, pulo estático, asserção trivial
    ├── anchor/                  o hook que lembra onde a atividade está
    └── elcamargo-report/      Markdown → PDF para a fronteira humana
```

Os steps 5, 7 e 10 não têm componente: são portões humanos, e quem os
atravessa é a pessoa, rodando `avancar`.

`references/` é o que separa este pacote de um checklist. Cada SKILL.md diz o
que **fazer**; as referências dizem o que **saber** — as perguntas a fazer, a
forma de uma boa especificação, a postura quando o projeto não declara convenção
nenhuma, a escala de severidade comum a todos os revisores. É delas que vem a
diferença entre um componente que passa nos portões e um que faz um bom
trabalho.

Sete componentes são **agent definitions**, não skills, porque nunca são
invocados diretamente — só como subagente do step que os contém. Agent não entra
no contexto principal; skill entra. Com 14 skills você pagaria o custo de
descoberta das 14 em toda sessão.

## Instalação

Como plugin do Claude Code, que é o caminho normal:

```bash
claude plugin marketplace add ElCamargo/elcamargo-ai-flow
claude plugin install elcamargo-ai-flow@elcamargo
```

Depois, no projeto, copie o `config.example.toml` para `.agents/config.toml`,
ajuste, e confira com o doutor:

```bash
python3 ~/.claude/plugins/cache/elcamargo/elcamargo-ai-flow/*/tools/doctor/doctor.py conferir
```

Atualizar é `claude plugin update elcamargo-ai-flow@elcamargo`.

### Alternativa: cópia dentro do projeto

1. Copie `elcamargo-flow/` para o `.agents/` do projeto.
2. `cp elcamargo-flow/config.example.toml .agents/config.toml` e ajuste.
3. Rode `elcamargo-flow/install.sh` para criar os symlinks de skills e agents.
4. Confira: `python3 elcamargo-flow/tools/flow-state/flow_state.py fluxo`.

O `.agents/` fica fora do versionamento do projeto — é ferramental de IA, não
entregável do cliente. O jeito que funciona é `.git/info/exclude`, que é
local e não altera nenhum arquivo do repositório do cliente.

## Dependências

**Nenhuma para o fluxo.** Os scripts de estado e config usam só a stdlib do
Python 3.11+ (`tomllib`).

O gerador de relatórios precisa de ReportLab, e só é chamado na fronteira com
humano. Instale num venv descartável, para não registrar dependência no ambiente
do projeto:

```bash
python3 -m venv ~/.cache/elcamargo-flow/venv \\
  && ~/.cache/elcamargo-flow/venv/bin/python -m pip install reportlab
```

## Estado

Uma atividade é um arquivo em `<.agents>/atividades/<id>.md`, nunca uma linha num
arquivo compartilhado — worktrees paralelas escreveriam no mesmo lugar.

`<.agents>` é sempre o do repositório principal. Nunca resolva por caminho
relativo; use o script, que já trata os três casos que enganam:

```bash
python3 tools/flow-state/flow_state.py caminho
```

Os três: uma worktree não carrega `.agents` (é untracked, e vive só no
repositório principal); `.agents` é um repositório Git próprio, então de dentro
dele o `git rev-parse` descreve o repositório errado; e fora de qualquer
repositório vale `ELCAMARGO_AGENTS_DIR`.

## Teste

```bash
python3 tools/flow-state/test_smoke.py                  # estado
python3 tools/flow-state/test_package.py                  # coerência do pacote
~/.cache/elcamargo-flow/venv/bin/python tools/elcamargo-report/test_smoke.py   # 49
```

O primeiro roda o ciclo inteiro num diretório temporário, sem tocar no estado
real. O segundo confere o que só quebraria na hora de rodar o fluxo: nome de
skill que não bate com a pasta, step sem componente, agent que ninguém chama.
O `install.sh` roda os dois.

## No Windows

O pacote nasceu em POSIX. No Windows ele roda com três coisas no lugar:

| O quê | Por quê |
| --- | --- |
| Python 3.12 em `%LOCALAPPDATA%\Programs\Python\Python312` | `tomllib` é stdlib desde o 3.11 |
| `python3.exe` ao lado de `python.exe` naquela pasta | o instalador do Windows não cria `python3`, e é assim que todo script e o hook chamam |
| `PYTHONUTF8=1` no ambiente do usuário | sem isso o console é cp1252 e qualquer `→` ou `·` derruba o script no meio |

O venv do gerador de PDF fica em `~/.cache/elcamargo-flow/venv`.

**O que não funciona aqui:** `tools/figma` exige o token em arquivo com
permissão `600`, que o Windows não expressa — ele recusa a leitura sempre. O
step 6 com Figma é o único caminho que depende disso; sem Figma, o
`screen-drawer` desenha a partir da SDD e o resto do fluxo não toca nessa
ferramenta.

## Licença e manutenção

[MIT](LICENSE). Use, adapte e redistribua a sua cópia à vontade.

Este repositório é mantido só pelo autor. Relato de problema por issue é
bem-vindo; pull request não é aceito — quem quiser mudar a ferramenta faz isso
no próprio fork.
