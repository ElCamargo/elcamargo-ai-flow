#!/usr/bin/env bash
# Instala o interfone nesta máquina: o canal entre janelas de chat.
#
#     bash tools/interfone/instalar.sh                 # dados em ~/.interfone/dados
#     bash tools/interfone/instalar.sh --dados <pasta> # dados noutro lugar
#     bash tools/interfone/instalar.sh --sem-hooks     # sem mexer no ~/.claude/settings.json
#
# O guia é o INSTALAR.md, ao lado deste arquivo.
#
# Por que ele é da MÁQUINA, e não do projeto, nem do plugin: o interfone liga
# janelas de repositórios diferentes. Ele precisa morar num caminho que não
# muda quando o plugin muda de versão (o cache do plugin troca a pasta a cada
# `plugin update`), e os hooks dele vão no settings GLOBAL, porque a janela
# que precisa ser perguntada pode estar em qualquer repositório.
#
# O que ele faz, e o que nunca faz:
# - copia o programa para ~/.interfone/ (a cópia anterior, se diferente, vira
#   um `.anterior-<data>` ao lado);
# - cria o ~/.interfone/config.json SÓ quando não existe: quem já tem caixas
#   noutro lugar continua com elas lá;
# - escreve o comando ~/.local/bin/interfone;
# - acrescenta três hooks ao ~/.claude/settings.json, sem tocar nos outros, e
#   recusa reescrever um settings ilegível;
# - nunca move, apaga ou migra mensagem.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="$HOME/.interfone"
DADOS="~/.interfone/dados"
HOOKS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dados) DADOS="${2:?--dados precisa de uma pasta}"; shift 2 ;;
    --sem-hooks) HOOKS=0; shift ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

verde()   { printf '  \033[32mok\033[0m       %s\n' "$1"; }
amarelo() { printf '  \033[33matenção\033[0m  %s\n' "$1"; }

# 1. O node. O programa é ESM com `node:` nos imports: abaixo do 18 não roda.
NODE="$(command -v node 2>/dev/null || true)"
if [[ -z "$NODE" ]]; then
  echo "interfone precisa do node (18 ou mais novo), e não achei nenhum no PATH." >&2
  exit 1
fi
MAIOR="$("$NODE" -p 'process.versions.node.split(".")[0]')"
if (( MAIOR < 18 )); then
  echo "interfone precisa do node 18 ou mais novo; este é o $("$NODE" --version)." >&2
  exit 1
fi
verde "node $("$NODE" --version)"

# 2. O programa, num caminho que não muda de versão para versão.
mkdir -p "$DESTINO"
for arq in interfone.mjs INTERFONE.md; do
  alvo="$DESTINO/$arq"
  if [[ -f "$alvo" ]] && ! cmp -s "$AQUI/$arq" "$alvo"; then
    cp -p "$alvo" "$alvo.anterior-$(date +%Y%m%d-%H%M%S)"
    amarelo "$arq diferente do pacote: a cópia antiga ficou como $arq.anterior-*"
  fi
  cp "$AQUI/$arq" "$alvo"
done
chmod +x "$DESTINO/interfone.mjs"
verde "programa em ${DESTINO/#$HOME/~}"

# 3. Onde moram as caixas. Só se ainda não há resposta: mudar a raiz de quem
# já usa esconderia todas as mensagens dele, sem erro nenhum.
if [[ -f "$DESTINO/config.json" ]]; then
  verde "config.json já existe, mantido: $(sed -n 's/.*"raiz": *"\([^"]*\)".*/\1/p' "$DESTINO/config.json")"
else
  "$NODE" -e '
    const [arq, raiz] = process.argv.slice(1);
    require("fs").writeFileSync(arq, JSON.stringify({ raiz }, null, 2) + "\n");
  ' "$DESTINO/config.json" "$DADOS"
  # O programa cria as pastas DENTRO da raiz, mas não a raiz: sem ela, o
  # primeiro `entrar` quebra com ENOENT (medido no teste desta instalação).
  mkdir -p "${DADOS/#\~/$HOME}"
  verde "dados em $DADOS (config.json criado)"
fi

# 4. O comando, de qualquer pasta. O node do PATH primeiro; sem ele, o do nvm
# ou do Homebrew, porque um hook nem sempre roda num shell que carregou o nvm,
# e hook que falha por PATH some em silêncio.
mkdir -p "$HOME/.local/bin"
LANCADOR="$HOME/.local/bin/interfone"
NOVO="$(mktemp)"
cat > "$NOVO" <<'SH'
#!/bin/sh
# O interfone, alcançável de qualquer pasta. Instalado por
# elcamargo-ai-flow/tools/interfone/instalar.sh; o programa mora em ~/.interfone.
NODE=$(command -v node 2>/dev/null)
if [ -z "$NODE" ]; then
  for c in "$HOME"/.nvm/versions/node/*/bin/node /opt/homebrew/bin/node /usr/local/bin/node; do
    [ -x "$c" ] && NODE="$c"
  done
fi
if [ -z "$NODE" ]; then
  echo "interfone: node não encontrado (PATH, ~/.nvm, Homebrew)" >&2
  exit 1
fi
exec "$NODE" "$HOME/.interfone/interfone.mjs" "$@"
SH
if [[ -f "$LANCADOR" ]] && ! cmp -s "$NOVO" "$LANCADOR"; then
  cp -p "$LANCADOR" "$LANCADOR.anterior-$(date +%Y%m%d-%H%M%S)"
  amarelo "comando interfone diferente: o antigo ficou como interfone.anterior-*"
fi
mv "$NOVO" "$LANCADOR"
chmod +x "$LANCADOR"
verde "comando em ~/.local/bin/interfone"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) amarelo "~/.local/bin não está no PATH: acrescente ao ~/.zshrc  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# 5. Os hooks globais. Escritos com o node, porque editar JSON com sed é como
# o arquivo se perde.
if (( HOOKS == 0 )); then
  amarelo "hooks NÃO instalados (--sem-hooks): nenhuma janela vai ser perguntada nem receber a caixa sozinha"
  exit 0
fi
mkdir -p "$HOME/.claude"
"$NODE" - "$HOME/.claude/settings.json" <<'JS'
const fs = require('fs');
const alvo = process.argv[2];
let dados = {};
if (fs.existsSync(alvo)) {
  try {
    dados = JSON.parse(fs.readFileSync(alvo, 'utf8'));
  } catch {
    // Config quebrada: NÃO sobrescrever. Perder os hooks de alguém para
    // instalar os nossos seria o pior desfecho possível.
    console.error('  ~/.claude/settings.json ilegível: não mexi. Conserte o arquivo e rode de novo.');
    process.exit(1);
  }
}
// Testa o comando antes de chamá-lo: apagado o ~/.local/bin/interfone, o
// hook cala, em vez de dar erro a cada mensagem de toda janela.
const cmd = (ev) =>
  `[ ! -x "$HOME/.local/bin/interfone" ] || "$HOME/.local/bin/interfone" hook ${ev}`;
const GANCHOS = [['SessionStart', 'inicio'], ['UserPromptSubmit', 'mensagem'], ['SessionEnd', 'fim']];
const hooks = (dados.hooks ??= {});
let mudou = false;
for (const [evento, ev] of GANCHOS) {
  const entradas = (hooks[evento] ??= []);
  const nosso = (c) => /interfone/.test(c ?? '') && new RegExp(`hook ${ev}\\b`).test(c);
  const achado = entradas.flatMap((e) => e.hooks ?? []).find((h) => nosso(h.command));
  if (achado) {
    if (achado.command !== cmd(ev)) { achado.command = cmd(ev); mudou = true; }
  } else {
    entradas.push({ hooks: [{ type: 'command', command: cmd(ev), timeout: 10 }] });
    mudou = true;
  }
}
if (mudou) fs.writeFileSync(alvo, JSON.stringify(dados, null, 2) + '\n');
console.log(mudou ? '  \x1b[32mok\x1b[0m       hooks SessionStart, UserPromptSubmit e SessionEnd em ~/.claude/settings.json'
                  : '  \x1b[32mok\x1b[0m       hooks já estavam em ~/.claude/settings.json');
JS

echo
echo "Pronto. Abra uma janela nova do Claude Code num repositório: ela vai perguntar"
echo "se você quer entrar no interfone. O passo a passo está em tools/interfone/INSTALAR.md."
