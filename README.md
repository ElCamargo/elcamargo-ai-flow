# Elcamargo AI Flow

Modelo de trabalho com IA: da análise de negócio até a entrega revisada, com
portões humanos nos pontos em que a decisão é de gente.

**Este repositório é a ferramenta.** Ele não conhece projeto nenhum: tudo que é
específico entra pelo `config.toml` de quem instala. O que mora aqui é doutrina,
skills, subagentes e ferramentas de comando — nunca estado de atividade.

- **[FLOW.md](FLOW.md)** — o contrato: os steps, as trilhas, as obrigações de
  cada skill. Comece por aí.
- **[config.example.toml](config.example.toml)** — o que cada projeto declara.
- **[references/](references/)** — o manual do ofício, e em
  [`references/rationale/`](references/rationale/) o porquê de cada skill.

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
│   ├── specialties/            o que cada subagente sabe da SUA frente
│   └── rationale/              o porquê de cada skill
├── skills/                      9 — as que têm porta de entrada
│   ├── elcamargo-ai-flow                       a porta do fluxo
│   ├── elcamargo-config                        configura o projeto
│   ├── elcamargo-board-git-management          step 1
│   ├── elcamargo-business-analysis-reviewer    step 2
│   ├── elcamargo-system-analyst                step 3
│   ├── elcamargo-system-analysis-reviewer      step 4
│   ├── elcamargo-ux-reviewer                   step 6
│   ├── elcamargo-developer                     step 8
│   └── elcamargo-development-reviewer          step 9
├── agents/                      10 — só rodam como subagente
│   ├── elcamargo-step-runner                   a janela que dispara um step
│   ├── elcamargo-business-analysis-auditor     step 2
│   ├── elcamargo-figma-reader                  ┐ step 6
│   ├── elcamargo-screen-drawer                 ┘
│   ├── elcamargo-code-reviewer                 ┐
│   ├── elcamargo-implemented-sdd-reviewer      │
│   ├── elcamargo-implemented-business-reviewer │ step 9, em paralelo
│   ├── elcamargo-security-reviewer             │
│   ├── elcamargo-quality-reviewer              │
│   └── elcamargo-runtime-reviewer              ┘
└── tools/                       28 ferramentas de conferência mecânica, entre elas
    ├── flow-state/              estado da atividade + leitura do config
    ├── board/                   lê o board — Azure Boards, GitHub, ou nenhum
    ├── config-wizard/           escreve o config.toml sem destruir o que ele explica
    ├── metrics/                 projeto → atividade → step → agente, e o painel
    ├── doctor/                  o config declara o que existe de verdade?
    ├── ratchet/                 falha nova bloqueia, conhecida não
    ├── outcome/                 o que aconteceu com cada achado
    ├── profiles/                o diff toca autorização? a passada prova?
    ├── honesty/                 `.only`, pulo estático, asserção trivial
    ├── doc-mask/                tira CPF e CNPJ do caminho antes do contexto
    ├── public-origin/           o servidor atrás de host público vaza o de dentro?
    ├── orchestrator-guard/      a janela que distribui steps não faz o trabalho deles
    ├── tree-guard/              a árvore está como antes de disparar as frentes?
    ├── shadow-leg/              uma frente, dois modelos, a mesma chamada
    ├── anchor/                  o hook que lembra onde a atividade está
    └── elcamargo-report/        Markdown → PDF para a fronteira humana
```

Os steps 5, 7 e 10 não têm componente: são portões humanos, e quem os
atravessa é a pessoa, rodando `avancar`.

`references/` é o que separa este pacote de um checklist. Cada SKILL.md diz o
que **fazer**; as referências dizem o que **saber** — as perguntas a fazer, a
forma de uma boa especificação, a postura quando o projeto não declara convenção
nenhuma, a escala de severidade comum a todos os revisores. É delas que vem a
diferença entre um componente que passa nos portões e um que faz um bom
trabalho.

Dez componentes são **agent definitions**, não skills, porque nunca são
invocados diretamente — só como subagente do step que os contém, ou da janela
que dispara um step (`elcamargo-step-runner`). Agent não entra no contexto
principal; skill entra. Com 19 skills você pagaria o custo de descoberta das 19
em toda sessão.

## Instalação

Como plugin do Claude Code, que é o caminho normal:

```bash
claude plugin marketplace add ElCamargo/elcamargo-ai-flow
claude plugin install elcamargo-ai-flow@elcamargo
```

Depois, no projeto, rode `/elcamargo-config`: ele detecta o board pelo host do
`git remote`, escreve o `.agents/config.toml` e confere com o doutor.

Atualizar é `claude plugin update elcamargo-ai-flow@elcamargo`.

### Alternativa: cópia dentro do projeto

1. Copie `elcamargo-flow/` para o `.agents/` do projeto.
2. `cp elcamargo-flow/config.example.toml .agents/config.toml` e ajuste.
3. Rode `elcamargo-flow/install.sh` para criar os symlinks de skills e agents.
4. Confira: `python3 elcamargo-flow/tools/flow-state/flow_state.py fluxo`.

O `.agents/` fica fora do versionamento do projeto — é ferramental de IA, não
entregável. O jeito que funciona é `.git/info/exclude`, que é local e não altera
nenhum arquivo do repositório do projeto.

### No Windows

**Rode a suíte antes de confiar.** O pacote é medido em macOS e Linux; três
defeitos de plataforma só apareceram quando alguém rodou no Windows — a trava do
estado não existia, a saída morria em `cp1252` e a leitura de `git` decodificava
pela região. Estão consertados, e o que ainda não tem prova está dito em
[`references/windows.md`](references/windows.md).

## Dependências

**Nenhuma para o fluxo.** Os scripts de estado e config usam só a stdlib do
Python 3.11+ (`tomllib`).

O gerador de relatórios precisa de ReportLab, e só é chamado na fronteira com
humano. Instale num venv descartável, para não registrar dependência no ambiente
do projeto:

```bash
python3 -m venv ~/.cache/elcamargo-flow/venv \
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
python3 tools/flow-state/test_package.py                # coerência do pacote
~/.cache/elcamargo-flow/venv/bin/python tools/elcamargo-report/test_smoke.py
```

O primeiro roda o ciclo inteiro num diretório temporário, sem tocar no estado
real. O segundo confere o que só quebraria na hora de rodar o fluxo: nome de
skill que não bate com a pasta, step sem componente, agent que ninguém chama.
O `install.sh` roda os dois.

O `elcamargo-report` é a única que precisa do venv: ela depende do `reportlab`,
e rodá-la com o `python3` do sistema falha por import — o que se lê como suíte
quebrada e não é.

## Licença e manutenção

[MIT](LICENSE). Use, adapte e redistribua a sua cópia à vontade.

Este repositório é mantido só pelo autor. Relato de problema por issue é
bem-vindo; pull request não é aceito — quem quiser mudar a ferramenta faz isso
no próprio fork.
