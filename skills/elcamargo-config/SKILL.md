---
name: elcamargo-config
description: "Configura o projeto para o fluxo por conversa, em vez de por edição de TOML. Detecta o que o repositório já responde — board pelo remote, gates pelo manifesto, stack pelas dependências — e pergunta só o que é decisão. Use quando o usuário disser `/config`, pedir para configurar ou instalar o fluxo num repositório novo, perguntar o que ainda falta configurar, ou quando um step reclamar de uma chave não declarada."
---

# Configuração · a entrevista

Leia `$PACOTE/FLOW.md` antes de começar. É lá que estão os steps, as trilhas e
os portões — e você precisa deles para explicar o que cada chave destrava, em
vez de pedir preenchimento no escuro.

Você **não edita o `config.toml` à mão**, e não pede que a pessoa edite. Quem
escreve é o `configure.py`, chave a chave, preservando os comentários que
explicam cada uma. Você conversa e decide o que perguntar.

O objetivo não é encher 55 chaves. É **fazer o projeto rodar até onde ele
precisa hoje**, e dizer com clareza o que ainda não dá para fazer.

```bash
CFG=$PACOTE/tools/config-wizard/configure.py

python3 $CFG estado   --raiz .          # por onde começar
python3 $CFG detectar --raiz .          # o que não precisa ser perguntado
python3 $CFG iniciar  --raiz .          # só se não existir config ainda
python3 $CFG definir <chave> <valor> --raiz .
python3 $CFG definir <chave> '<json>' --json --raiz .   # lista, número, booleano
```

## Os três modos

Descubra em qual você está **antes de perguntar qualquer coisa**, rodando
`estado`. Ele já responde.

**Repositório novo** — o `estado` responde `configurado: false` e já diz o
próximo comando. Rode `iniciar` e percorra os blocos na ordem dele, que é a
ordem em que as coisas travam.

**Repositório em uso** — o config existe e faltam chaves. Mostre o que falta e
**pergunte só isso**. Ninguém quer reconfirmar onze blocos para declarar um.

**Um bloco só** — a pessoa disse `/config figma`, `/config gates`. Vá direto,
sem atravessar o resto.

## Detecte antes de perguntar

Perguntar o que dá para descobrir é o que faz configuração virar formulário.
Rode `detectar` **primeiro** e use o resultado como resposta proposta, não como
pergunta:

> Peguei do repositório: board **Azure**, org `acme`, projeto
> `SoftwareStudio`. Gates `npm run lint`, `test` e `build`. Stack TypeScript
> sobre Node, com Next e NestJS. Componentes em `frontend/components`.
>
> Confirma? Se algo estiver errado me diga qual, que eu corrijo só esse.

Uma confirmação em bloco vale por seis perguntas. Só vire pergunta o que o
`detectar` devolveu vazio.

**O que ele nunca descobre, e por isso é sempre pergunta:** links de Figma, URL
de homologação, quais steps valem neste projeto, quais trilhas fazem sentido,
orçamento, assinaturas, e o backend de anexo. São **decisões**, não fatos do
disco — e é exatamente por isso que uma pessoa precisa respondê-las.

## Grave enquanto anda, nunca no fim

Cada bloco respondido vira `definir` **antes de o próximo começar**.

É a regra "persista enquanto trabalha" que já vale no resto do fluxo, e que
nasceu de um step que rodou seis frentes, todas voltaram, e ele travou
consolidando: **52 minutos, zero artefato**. Uma entrevista de vinte perguntas
que perde tudo na décima nona é o mesmo defeito com outra roupa.

Depois de cada bloco, rode o doutor e mostre só o que mudou:

```bash
python3 $PACOTE/tools/doctor/doctor.py conferir --raiz .
```

Ele é quem confere; você não reimplementa a regra dele. Se ele reprovar o que
você acabou de gravar, **conserte antes de seguir** — deixar para o fim faz a
pessoa responder mais dez perguntas sobre uma base que já está errada.

## Como perguntar

**Uma decisão por vez, com recomendação.** Não recomendar parece neutralidade e
é omissão: você leu o repositório, quem responde muitas vezes não.

**Diga o que acontece se ficar vazio.** Quase toda chave tem um comportamento
declarado para o caso de ausência, e ele costuma ser aceitável. Uma pessoa que
sabe disso responde mais rápido e mente menos:

> `perfis.comando` — o comando do projeto que emite token por perfil de acesso.
>
> **Vazio é resposta válida:** a passada por perfis vira dimensão **não coberta
> declarada**, nomeada no relatório do step 9 em vez de prometida e ausente.
>
> Recomendo deixar vazio agora e voltar quando houver autenticação e um script
> que emita token.

**Nunca invente valor para calar um aviso.** Se a pessoa não sabe, a resposta é
deixar vazio e seguir — não é você escolher um plausível. Chave declarada
errada é pior que chave ausente, porque quem declarou acredita ter configurado.

**Nem toda ausência é falta.** O `estado` classifica em quatro, e só o primeiro
grupo é conversa obrigatória:

| | O que é | O que fazer |
| --- | --- | --- |
| `faltando` | essencial, e o bloco trava sem ela | pergunte |
| `opcional` | sem padrão, mas o fluxo roda — só não roda aquela parte | ofereça, aceite "depois" |
| `no_padrao` | o pacote já tem um valor documentado | mencione de passagem, ou nem isso |
| `declaradas` | resolvida | não repita |

O `mostra_trava` do bloco diz se o aviso de travamento vale: ele só é verdadeiro
quando falta chave **essencial**. Não repita a trava de um bloco que só tem
opcionais em aberto — o aviso seria sobre chaves que não são o problema.

## Valores que não são texto

Lista, número e booleano vão com `--json`:

```bash
python3 $CFG definir fluxo.steps '[1,3,4,5,6,7,8,9,10]' --json --raiz .
python3 $CFG definir metricas.assinaturas_usd_mes '[200.0, 30.0]' --json --raiz .
python3 $CFG definir metricas.ligado 'false' --json --raiz .
```

Se o `configure.py` recusar a chave, **ele já sugere a mais parecida** — leia a
mensagem antes de tentar outra grafia. Chave que não está no
`config.example.toml` não é lida por ninguém.

## Termine dizendo o que ainda NÃO dá para fazer

*"Tudo pronto para iniciar"* é a frase mais fácil de escrever e a mais fácil de
estar errada. O fecho correto tem três partes:

1. **O que já roda.** Quais steps estão prontos, nomeados.
2. **O que está bloqueado, e por qual chave.** Não "faltam 4 chaves" — sim
   *"o step 9 não roda a passada por perfis, porque `perfis.comando` está
   vazio"*.
3. **Qual é o próximo comando.** Um, concreto, para copiar e colar.

É a mesma doutrina do quarto veredicto do fluxo: cobertura incompleta é aceita
**desde que declarada**. O que não se aceita é a lacuna sumir dentro de um
relatório verde.

## O que esta skill não faz

**Não cria o repositório, não instala o plugin e não roda `az login`.** Se algo
disso faltar, diga o comando e deixe a pessoa rodar — configuração que executa
autenticação em nome de alguém é o tipo de conveniência que ninguém pediu.

**Não edita `config.toml` com editor de texto.** Toda escrita passa pelo
`configure.py`, que garante que o TOML continua válido e que os comentários
sobrevivem. Uma edição à mão que quebre o arquivo derruba **todos** os steps de
uma vez, e o erro aparece longe daqui.

**Não decide por ninguém.** Recomende, explique a consequência, e registre o
que a pessoa escolheu.

## Se a máquina é Windows

**Pergunte, e não deduza pelo repositório.** O pacote é escrito e medido em
macOS e Linux, e três defeitos de plataforma só apareceram quando alguém rodou
de lá, em 22/09/2026: a trava do estado não existia, a saída morria em `cp1252`
e a leitura do `git` decodificava pela região. Estão consertados.

O que ainda **não tem prova** está em `$PACOTE/references/windows.md` — leia
antes de dizer que está tudo certo, e repasse o que de lá é pedido: rodar a
suíte inteira na máquina, porque duas das correções nunca foram executadas
naquela plataforma. Reprovação diferente das duas conhecidas é achado, e vale
mais que a página.

## Quando terminar

Anuncie o próximo passo, não o execute. Se o projeto acabou de ser configurado,
o caminho normal é abrir a primeira atividade pela porta do fluxo — e quem faz
isso é o step 1, não você.
