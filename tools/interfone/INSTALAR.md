# Instalar o interfone

O interfone é o canal entre **janelas de chat** na mesma máquina. A sessão do
backoffice pede algo ao ai-flow, a do ai-flow avisa quando entregou, e cada
uma recebe a caixa sozinha a cada mensagem sua. Como ele funciona, e por que
cada regra existe, está em [INTERFONE.md](INTERFONE.md).

Ele vai junto do elcamargo-ai-flow, mas **não é ligado pelo plugin**. É da
máquina, e não do projeto: liga repositórios diferentes, e por isso precisa
morar num caminho que não muda a cada versão do plugin.

## O que precisa

- `node` 18 ou mais novo (`node --version`).
- `bash` e `git`. No Windows, o Git Bash; **não foi testado no Windows**.
- Claude Code. Os hooks são dele; o Codex não recebe a caixa sozinho.

## Instalar

Da pasta do elcamargo-ai-flow (o clone ou o zip extraído):

```bash
bash tools/interfone/instalar.sh
```

Ele faz quatro coisas, e diz cada uma:

| | Onde | Se já existe |
| --- | --- | --- |
| O programa | `~/.interfone/interfone.mjs` | Diferente, a cópia velha fica como `.anterior-<data>` |
| Onde moram as mensagens | `~/.interfone/config.json` → `~/.interfone/dados` | **Mantido.** Quem já tem caixas noutro lugar continua com elas |
| O comando | `~/.local/bin/interfone` | Diferente, o velho fica como `.anterior-<data>` |
| Três hooks | `~/.claude/settings.json` | Reapontados, sem duplicar. Os outros hooks e as permissions ficam |

Opções:

- `--dados <pasta>`: as mensagens noutro lugar. Só vale na primeira instalação.
- `--sem-hooks`: não mexe no `settings.json`. Nada pergunta e nada entrega
  sozinho; você roda `interfone caixa` à mão.

Se o `settings.json` estiver ilegível, o instalador **recusa e não o reescreve**.
Conserte o arquivo e rode de novo.

Se ele avisar que `~/.local/bin` não está no PATH, acrescente ao `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## O primeiro dia: duas janelas conversando

1. **Abra uma janela nova do Claude Code** num repositório. O hook de início
   manda o assistente **perguntar** se essa janela entra no interfone. O hook
   não decide: quem responde é você.
2. **Responda que sim, e dê um nome ao papel do repositório**: o domínio, como
   `backoffice` ou `ai-flow`. A primeira vez, o assistente roda
   `interfone entrar <papel> --novo --sessao <o nome que o hook sugeriu>`.
   Isso grava um `.interfone.json` na raiz do repositório, e a próxima janela
   aberta ali já sabe o papel.
3. **Faça o mesmo na outra janela**, no outro repositório.
4. **Diga quem fala com quem**, uma vez:

   ```bash
   interfone ligar backoffice ai-flow --mao-dupla
   ```

5. **Peça ao assistente de uma janela para mandar algo à outra.** A mensagem
   aparece na outra janela na próxima vez que você escrever nela.

Para não entrar, responda que não: `interfone recusar` silencia o convite
naquela janela.

## O dia a dia

Você pede em português, e o assistente roda os comandos. Os que valem saber:

```bash
interfone caixa <papel>          # o que esta janela ainda não leu
interfone caixa <papel> --todas  # inclusive o que foi para outra janela do mesmo papel
interfone travas                 # quem está com que branch ou atividade, ANTES de agir
interfone quem                   # que janelas estão em cada papel, e há quanto tempo
interfone                        # a ajuda inteira
```

Texto livre vai **entre aspas simples**. Entre aspas duplas, o shell come o que
estiver entre crases, e a mensagem chega mutilada sem erro nenhum.

## Atualizar

O programa vem no pacote. A cada versão nova do elcamargo-ai-flow, rode o
`instalar.sh` de novo. As mensagens e os papéis não são tocados.

## Remover

Nada disto apaga mensagem. Para tirar:

1. Em `~/.claude/settings.json`, apague os três hooks que contêm `interfone`
   (`SessionStart`, `UserPromptSubmit`, `SessionEnd`).
2. Apague `~/.local/bin/interfone`.
3. Se quiser apagar também as mensagens, apague `~/.interfone`. Isso não tem volta.

## O que ele NÃO faz

- **Não atravessa máquinas.** As mensagens são arquivos numa pasta local. O
  interfone de casa e o do trabalho são dois canais separados.
- **Não toca.** A mensagem só aparece quando você escreve na janela que a recebe.
- **Não protege as mensagens.** São texto puro em `~/.interfone/dados`. Não
  ponha senha nem token numa mensagem.
- **Não decide sozinho se uma janela entra.** O hook só manda o assistente perguntar.
