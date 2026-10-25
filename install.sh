#!/usr/bin/env bash
# Instala o elcamargo-flow no projeto atual.
#
# Cria os symlinks que Claude Code e Codex usam para descobrir skills e agents,
# confere o config e valida o ferramental. Idempotente: rode quantas vezes
# quiser.
#
#   .agents/elcamargo-flow/install.sh              liga
#   .agents/elcamargo-flow/install.sh --desligar   desliga
#   .agents/elcamargo-flow/install.sh --status     mostra em qual estado está
#
# Ligar e desligar mexe SÓ nos symlinks de descoberta. O pacote em si nunca é
# tocado: desligado, ele continua inteiro no disco, só deixa de ser visível para
# as sessões. Use quando o pacote ainda não foi validado, ou quando outra
# sessão está trabalhando no projeto e você não quer que ela veja skills novas.
#
# Branch no .agents não serve para isso: as sessões leem o mesmo working tree
# pelos symlinks, então trocar de branch trocaria os arquivos debaixo de todas
# ao mesmo tempo.
set -euo pipefail

PACOTE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS="$(dirname "$PACOTE")"
PROJETO="$(dirname "$AGENTS")"

verde() { printf '  \033[32m%s\033[0m %s\n' "ok" "$1"; }
amarelo() { printf '  \033[33m%s\033[0m %s\n' "--" "$1"; }
vermelho() { printf '  \033[31m%s\033[0m %s\n' "!!" "$1"; }

falhas=0
MODO="${1:-ligar}"

# Escopo: por padrão a raiz do projeto.
#
# MEDIDO, e não suposto. Um projeto de teste com uma skill na raiz e outra em
# `sub/.claude/skills/` respondeu assim:
#
#   sessão aberta na raiz    vê só a da raiz
#   sessão aberta em `sub/`  vê AS DUAS, e sem prefixo no nome
#
# Ou seja, a descoberta é por ONDE A SESSÃO ABRIU, subindo a árvore. Ela
# acrescenta e nunca subtrai: a skill da raiz continua valendo lá dentro.
#
# Duas consequências práticas:
#
#   Não existe "raiz ligada menos uma pasta". Para excluir de verdade, é a
#   outra topologia — raiz desligada e pasta a pasta.
#
#   `--escopo <pasta>` só serve a quem ABRE A SESSÃO ali dentro. Para quem abre
#   na raiz, é como se não existisse.
#
# Escrito assim porque eu afirmei duas coisas erradas antes de medir: que uma
# pasta estava "desligada" quando a raiz já a cobria, e que a skill de subpasta
# apareceria com nome prefixado.
ESCOPO="$PROJETO"
if [[ "$MODO" == "--escopo" ]]; then
  [[ -n "${2:-}" ]] || { echo "erro: --escopo exige a pasta. Ex: --escopo mobile" >&2; exit 2; }
  [[ -d "$PROJETO/$2" ]] || { echo "erro: $PROJETO/$2 não existe" >&2; exit 2; }
  ESCOPO="$PROJETO/$2"
  # `--escopo <pasta> --desligar` desliga só ali. Sem isso, a única forma de
  # tirar uma pasta seria desligar o repositório inteiro — e quem cuida do
  # mobile não deveria precisar apagar o fluxo de todo mundo para sair.
  MODO="${3:-ligar}"
  echo "Escopo: $2 — as skills valem só dentro dela."
fi

contar_links() {
  local n=0
  for d in "$PROJETO/.claude/skills" "$PROJETO/.claude/agents" \
           "$PROJETO"/*/.claude/skills "$PROJETO"/*/.claude/agents \
           "$HOME/.codex/skills"; do
    [[ -d "$d" ]] || continue
    n=$((n + $(find "$d" -maxdepth 1 -name 'elcamargo-*' | wc -l | tr -d ' ')))
  done
  echo "$n"
}

if [[ "$MODO" == "--status" ]]; then
  n="$(contar_links)"
  if [[ "$n" -eq 0 ]]; then
    echo "elcamargo-flow: DESLIGADO — o pacote está no disco e invisível para as sessões."
    echo "  Para ligar: $0"
  else
    echo "elcamargo-flow: LIGADO — $n link(s) de descoberta assets."
    echo "  Para desligar: $0 --desligar"
  fi
  exit 0
fi

if [[ "$MODO" == "--desligar" ]]; then
  echo "elcamargo-flow — desligando"
  removidos=0
  # Com escopo, o desligar respeita o escopo — e o `~/.codex/skills`, que é
  # global, fica de fora: ele não é desta pasta, é da máquina.
  if [[ "$ESCOPO" != "$PROJETO" ]]; then
    lugares=("$ESCOPO/.claude/skills" "$ESCOPO/.claude/agents")
  else
    lugares=("$PROJETO/.claude/skills" "$PROJETO/.claude/agents"
             "$PROJETO"/*/.claude/skills "$PROJETO"/*/.claude/agents
             "$HOME/.codex/skills")
  fi
  for d in "${lugares[@]}"; do
    [[ -d "$d" ]] || continue
    while IFS= read -r alvo; do
      [[ -n "$alvo" ]] || continue
      rm -rf "$alvo"
      printf '  removido  %s\n' "${alvo/#$HOME/~}"
      removidos=$((removidos + 1))
    done < <(find "$d" -maxdepth 1 -name 'elcamargo-*')
  done
  # A âncora sai junto, nos dois eventos: um hook que aponta para pacote
  # desligado roda a cada mensagem, e a cada Bash, e não acha nada. Só a nossa
  # entrada é removida — os outros hooks do projeto ficam.
  if [[ "$ESCOPO" == "$PROJETO" ]] && command -v python3 >/dev/null; then
    python3 - "$PROJETO" <<'PY' && echo "  removido  âncora de .claude/settings.local.json"
import json, pathlib, sys
alvo = pathlib.Path(sys.argv[1]) / ".claude" / "settings.local.json"
if not alvo.exists():
    sys.exit(1)
try:
    dados = json.loads(alvo.read_text(encoding="utf-8"))
except json.JSONDecodeError:
    sys.exit(1)
removeu = False
for evento in ("UserPromptSubmit", "PreToolUse"):
    sobram = []
    for entrada in dados.get("hooks", {}).get(evento, []):
        hooks = entrada.get("hooks", [])
        limpos = [h for h in hooks if "anchor.py" not in h.get("command", "")]
        if len(limpos) != len(hooks):
            removeu = True
        if limpos:
            entrada["hooks"] = limpos
            sobram.append(entrada)
    if evento not in dados.get("hooks", {}):
        continue
    if sobram:
        dados["hooks"][evento] = sobram
    else:
        dados["hooks"].pop(evento, None)
if not removeu:
    sys.exit(1)          # nada nosso ali: não reescrever o arquivo de ninguém
alvo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
PY
  fi

  # Só remove o diretório de agents se ele ficou vazio e foi criado por nós.
  rmdir "$PROJETO/.claude/agents" 2>/dev/null && echo "  removido  .claude/agents (vazio)"
  echo
  if [[ "$removidos" -eq 0 ]]; then
    echo "Já estava desligado."
  else
    echo "Desligado. O pacote continua inteiro em $PACOTE."
    echo "Nenhuma sessão vê as skills ou os agents até você rodar $0."
  fi
  exit 0
fi

if [[ "$MODO" != "ligar" ]]; then
  echo "uso: $0 [--desligar | --status]" >&2
  exit 2
fi

echo "elcamargo-flow"
echo "  pacote:  $PACOTE"
echo "  agents:  $AGENTS"
echo "  projeto: $PROJETO"
echo

# --------------------------------------------------------------------------
echo "Config"
# --------------------------------------------------------------------------
if [[ -f "$AGENTS/config.toml" ]]; then
  verde "config.toml presente"
else
  cp "$PACOTE/config.example.toml" "$AGENTS/config.toml"
  # O exemplo sai VAZIO de propósito — ver o cabeçalho dele. O único valor que
  # dá para derivar sem perguntar é o nome do repositório, então derive: um
  # campo a menos para alguém esquecer, e o doutor deixa de acusar o projeto
  # novo por um nome que ninguém tinha como acertar antes de instalar.
  nome_repo="$(basename "$PROJETO")"
  perl -0pi -e "s/^nome = \"\"\$/nome = \"$nome_repo\"/m" "$AGENTS/config.toml"
  amarelo "config.toml criado a partir do exemplo (projeto: $nome_repo)"
  amarelo "  ele sai VAZIO: preencha cada seção quando o que ela declara existir"
fi

if python3 -c "import tomllib,sys; tomllib.loads(open(sys.argv[1]).read())" \
     "$AGENTS/config.toml" 2>/dev/null; then
  verde "config.toml é TOML válido"
else
  vermelho "config.toml não é TOML válido"
  falhas=$((falhas + 1))
fi

# --------------------------------------------------------------------------
echo
echo "Symlinks"
# --------------------------------------------------------------------------
# O conteúdo canônico vive no pacote; cada agente lê por symlink. Editar aqui
# atualiza todos.
ligar() {
  local origem="$1" destino="$2" rotulo="$3"
  [[ -e "$origem" ]] || return 0
  mkdir -p "$(dirname "$destino")"
  ln -sfn "$origem" "$destino"
  verde "$rotulo"
}

# Symlink de componente que o pacote não tem mais.
#
# Um componente RENOMEADO some da origem e o link antigo continua no destino,
# apontando para nada. Aconteceu quando a skill do step 1 deixou de se chamar
# `elcamargo-azure-git-management`: quem já tinha o pacote instalado ficava com
# o nome velho pendurado, e a sessão descobria duas skills para o mesmo step —
# uma delas quebrada. O link só é removido se for symlink QUEBRADO e do
# prefixo do pacote; arquivo de verdade e link de outro dono não se toca.
podar() {
  local pasta="$1" removidos=0
  [[ -d "$pasta" ]] || return 0
  for velho in "$pasta"/elcamargo-*; do
    [[ -L "$velho" && ! -e "$velho" ]] || continue
    rm -f "$velho"
    removidos=$((removidos + 1))
  done
  [[ $removidos -gt 0 ]] && amarelo "$pasta: $removidos link(s) órfão(s) removido(s)"
  return 0
}

podar "$ESCOPO/.claude/skills"
podar "$ESCOPO/.claude/agents"
podar "$HOME/.codex/skills"

# Skill é um diretório com SKILL.md; agent é um único .md. Os dois são ligados
# por symlink, mas a forma é diferente.
contagem=0
for caminho in "$PACOTE/skills"/*/; do
  [[ -d "$caminho" ]] || continue
  nome="$(basename "$caminho")"
  ligar "$caminho" "$ESCOPO/.claude/skills/$nome" "skills/$nome"
  contagem=$((contagem + 1))
done
[[ $contagem -eq 0 ]] && amarelo "skills/ está vazio"

contagem=0
for caminho in "$PACOTE/agents"/*.md; do
  [[ -f "$caminho" ]] || continue
  nome="$(basename "$caminho")"
  ligar "$caminho" "$ESCOPO/.claude/agents/$nome" "agents/${nome%.md}"
  contagem=$((contagem + 1))
done
[[ $contagem -eq 0 ]] && amarelo "agents/ está vazio"

# --------------------------------------------------------------------------
# A âncora. Um hook de `UserPromptSubmit`, e não mais uma instrução: quem
# executa é o harness, antes de o modelo ver a mensagem, então não depende de
# ninguém lembrar. É o que impede a sessão de abandonar o fluxo no meio.
#
# E um de `PreToolUse` no Bash, o `--contexto`: grava sessão e subagente de quem
# vai chamar o `flow_state`, que é o que a trava do step 9 compara (2.61.0). Até
# 2.62.0 só o `hooks/hooks.json` do plugin o ligava, e quem instalava por aqui
# ficava com a trava muda — ela não acusa sem registro, e não avisa que falta.
#
# Vive em `.claude/settings.local.json`, que é local e ignorado pelo git do
# cliente. Escrito com Python porque editar JSON com sed é como o arquivo se
# perde.
if [[ "$ESCOPO" == "$PROJETO" ]] && command -v python3 >/dev/null; then
  if python3 - "$PROJETO" "$PACOTE" <<'PY'
import json, pathlib, sys
projeto, pacote = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
alvo = projeto / ".claude" / "settings.local.json"
comando = f"python3 {pacote}/tools/anchor/anchor.py"
dados = {}
if alvo.exists():
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Config quebrada: NÃO sobrescrever. Perder os hooks de alguém para
        # instalar o nosso seria o pior desfecho possível.
        print("settings.local.json ilegível — não mexi", file=sys.stderr)
        sys.exit(1)
hooks = dados.setdefault("hooks", {})
# (evento, matcher, comando, é o nosso?). O `--contexto` separa os dois: sem
# ele, o PreToolUse reapontaria a âncora de mensagem, e vice-versa.
GANCHOS = (
    ("UserPromptSubmit", None, comando,
     lambda c: "anchor.py" in c and "--contexto" not in c),
    ("PreToolUse", "Bash", f"{comando} --contexto",
     lambda c: "anchor.py" in c and "--contexto" in c),
)
for evento, matcher, cmd, nosso in GANCHOS:
    entradas = hooks.setdefault(evento, [])
    for entrada in entradas:
        for h in entrada.get("hooks", []):
            if nosso(h.get("command", "")):
                h["command"] = cmd          # já existe: só reaponta
                break
        else:
            continue
        break
    else:
        nova = {"hooks": [{"type": "command", "command": cmd}]}
        if matcher:
            # Roda antes de TODO Bash: preso, segura a sessão inteira. O
            # mesmo teto do `hooks/hooks.json`.
            nova = {"matcher": matcher, **nova}
            nova["hooks"][0]["timeout"] = 5
        entradas.append(nova)
alvo.parent.mkdir(parents=True, exist_ok=True)
alvo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
PY
  then
    verde "âncora ligada em .claude/settings.local.json (UserPromptSubmit e PreToolUse de Bash)"
  else
    amarelo "âncora NÃO ligada — a sessão pode abandonar o fluxo no meio, e a trava do step 9 fica muda"
  fi
fi

# Codex resolve por caminho absoluto, e só para skills.
#
# ATENÇÃO: `~/.codex/skills` é GLOBAL, e não por projeto. Com o pacote instalado
# em dois repositórios, o segundo `install.sh` sequestrava os links do primeiro
# em silêncio — e uma sessão do Codex no projeto A passava a ler as skills do
# projeto B. Aconteceu ao replicar o pacote para o segundo repositório.
#
# Agora o link só é criado quando aponta para lugar nenhum ou já aponta para
# ESTE pacote. Apontando para outro, avisa e não mexe: desligar lá é decisão de
# quem trabalha lá.
if [[ -d "$HOME/.codex/skills" && -d "$PACOTE/skills" ]]; then
  ligadas=0; alheias=0; dono=""
  for caminho in "$PACOTE/skills"/*/; do
    [[ -d "$caminho" ]] || continue
    nome="$(basename "$caminho")"
    destino="$HOME/.codex/skills/$nome"
    atual="$(readlink "$destino" 2>/dev/null || true)"
    if [[ -n "$atual" && "${atual%/}" != "${caminho%/}" ]]; then
      alheias=$((alheias + 1))
      dono="$atual"
      continue
    fi
    ln -sfn "$caminho" "$destino"
    ligadas=$((ligadas + 1))
  done
  if [[ "$alheias" -gt 0 ]]; then
    amarelo "~/.codex/skills: $alheias skill(s) apontam para OUTRO projeto — não mexi"
    printf '     %s\n' "${dono/#$HOME/~}"
    printf '     Codex é global: só um projeto por vez. Desligue lá antes.\n'
  fi
  [[ "$ligadas" -gt 0 ]] && verde "$ligadas skill(s) ligadas em ~/.codex/skills"
fi

# --------------------------------------------------------------------------
echo
echo "Exclusão do versionamento do cliente"
# --------------------------------------------------------------------------
# .agents é ferramental de IA, não entregável. Fica fora por .git/info/exclude,
# que é local: nenhum arquivo do repositório do cliente é alterado.
EXCLUDE="$(git -C "$PROJETO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)/info/exclude"
if [[ -f "$EXCLUDE" ]]; then
  if grep -qx '\.agents/' "$EXCLUDE" 2>/dev/null; then
    verde ".agents/ já está em .git/info/exclude"
  else
    printf '.agents/\n' >> "$EXCLUDE"
    verde ".agents/ adicionado a .git/info/exclude"
  fi
else
  amarelo "não achei .git/info/exclude — garanta que .agents/ fique fora do versionamento"
fi

# --------------------------------------------------------------------------
echo
echo "Ferramental"
# --------------------------------------------------------------------------
if python3 "$PACOTE/tools/flow-state/flow_state.py" caminho >/dev/null 2>&1; then
  verde "flow-state responde"
else
  vermelho "flow-state não resolveu o .agents"
  falhas=$((falhas + 1))
fi

if python3 "$PACOTE/tools/flow-state/test_smoke.py" >/dev/null 2>&1; then
  verde "teste de fumaça do flow-state passou"
else
  vermelho "teste de fumaça do flow-state FALHOU"
  falhas=$((falhas + 1))
fi

# Nome que não bate com a pasta, step sem skill ou agent sem quem o chame só
# aparecem quando alguém tenta rodar o fluxo. Melhor aparecer aqui.
if python3 "$PACOTE/tools/flow-state/test_package.py" >/dev/null 2>&1; then
  verde "pacote coerente: nomes, cobertura dos steps e referências"
else
  vermelho "pacote INCOERENTE — rode tools/flow-state/test_package.py"
  falhas=$((falhas + 1))
fi

if python3 "$PACOTE/tools/attach/test_smoke.py" >/dev/null 2>&1; then
  verde "anexo verificado: recusa upload corrompido"
else
  vermelho "teste do anexador FALHOU"
  falhas=$((falhas + 1))
fi

VENV_RELATORIO="$HOME/.cache/elcamargo-flow/venv"
if [[ -x "$VENV_RELATORIO/bin/python" ]] &&
   "$VENV_RELATORIO/bin/python" -c "import reportlab" 2>/dev/null; then
  verde "reportlab disponível em $VENV_RELATORIO"
else
  amarelo "reportlab ausente. Só é preciso para gerar PDF:"
  echo "       python3 -m venv $VENV_RELATORIO && $VENV_RELATORIO/bin/python -m pip install reportlab pypdfium2"
fi

# --------------------------------------------------------------------------
echo
if [[ $falhas -eq 0 ]]; then
  echo
  echo "Conferindo o config contra este repositório..."
  python3 "$PACOTE/tools/doctor/doctor.py" conferir \
      --config "$AGENTS/config.toml" --raiz "$(dirname "$AGENTS")" || true
  echo "Instalado. Próximo passo: revise $AGENTS/config.toml e leia $PACOTE/FLOW.md"
else
  echo "Instalado com $falhas problema(s) acima."
  exit 1
fi
