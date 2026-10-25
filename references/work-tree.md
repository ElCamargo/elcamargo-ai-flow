# A árvore de trabalho é compartilhada

As seis frentes do step 9 rodam sobre a mesma árvore, e **duas delas escrevem
por ofício**: a de qualidade insere mutantes no código-fonte, a de execução cria
fixtures e tokens. As outras quatro estão lendo essa árvore ao mesmo tempo.

## O que aconteceu

Em 08/09/2026 a máquina paginou até travar no meio de um step 9. Quando parou, a
frente de qualidade tinha três mutantes vivos em cima da validação de boot de um
segredo:

```ts
if (false && cfg.SECRET) { ... }
```

Ela restaurou — por segundos. Se tivesse perdido a corrida, o mutante ficaria na
árvore do usuário, e o commit seguinte o levaria junto. A frente de execução
deixou para trás um `.qa-token.mjs` e três JWT num diretório **servido**.

**E o efeito colateral foi pior que o risco.** As outras frentes leram aquela
árvore. Uma percebeu sozinha que duas leituras do mesmo arquivo devolviam
conteúdos diferentes, e passou a revisar contra o commit em vez do disco — foi o
que salvou a revisão dela. **Nenhuma linha do fluxo pedia aquilo.** As outras
três leram uma árvore que podia estar mutada e não souberam.

## Se você é uma das que escrevem

1. **Você deve estar em worktree própria.** O step 9 chama as duas com
   `isolation: worktree`. Confira: `git rev-parse --show-toplevel` contra a raiz
   do dossiê. Se não estiver isolada, **diga isso no relatório antes de escrever
   qualquer coisa**, e prefira o que não exige escrever.
2. **Restaure assim que a medição termina** — não no fim do raciocínio. O que
   matou a execução medida foi o intervalo entre "já medi" e "vou restaurar".
3. **Nada além do que o ofício exige.** Nem arquivo temporário "para conferir
   depois", nem instalar dependência na árvore de outro.

## Se você é uma das que leem

**Não escreva nada.** Nem arquivo temporário, nem `npm install`, nem tocar no
código para experimentar. Você lê e reporta.

E se duas leituras do mesmo arquivo divergirem, **isso é achado**: alguém está
escrevendo embaixo de você. Passe a revisar contra o commit, e diga no relatório
que fez isso e por quê.

## Quem confere

O orquestrador do step 9, com:

```bash
python3 $PACOTE/tools/tree-guard/tree_guard.py marcar   --id <id>   # antes
python3 $PACOTE/tools/tree-guard/tree_guard.py conferir --id <id>   # depois

python3 $PACOTE/tools/process-guard/process_guard.py marcar   --id <id>
python3 $PACOTE/tools/process-guard/process_guard.py conferir --id <id>
python3 $PACOTE/tools/process-guard/process_guard.py sobra    --id <id>
```

A comparação é por **conteúdo**, não pelo código do `git status`. É o que
importa no caso normal: a árvore já chega suja da entrega do step 8, então
`src/env.ts` já é ` M` antes de qualquer frente rodar — e um mutante por cima
produz a mesma linha, que uma conferência por código deixaria passar.

## O que isto NÃO resolve

**Não é garantia estrutural.** As seis frentes declaram `Bash`, e o pacote não
tem como impedir nenhuma delas de escrever. É contrato com conferência.

**Árvore limpa no fim não prova leitura limpa no meio.** Uma frente pode ter
lido no instante em que o mutante existia e devolvido o veredicto depois da
restauração: as duas marcas batem, e a leitura foi suja. Contra isso só o
isolamento serve — e ele cobre as duas que sabemos que escrevem, não as que
descumprirem o contrato.


## O irmão que faltava: isolamento de PROCESSO

Isolar a árvore protege o **disco**. Não protege a **máquina**, e são coisas
diferentes.

Em 10/09/2026 as três árvores voltaram limpas e conferidas — e quatro serviços
de outra atividade do usuário estavam no chão. A frente de execução limpou os
próprios processos com `pkill -f "nest start"`, e o padrão casou com o backend
do vizinho: portas 3001, 3002, 3003 e 3004.

**A frente tinha feito tudo certo.** Escolheu portas livres (3210, 3211, 3213,
3214), isolou banco e vhost, e detectou e declarou o próprio estrago. O que ela
não podia era religar, porque o prompt a proibia de executar na árvore do
usuário.

Duas regras saíram daí, e as duas são de mecanismo:

1. **Mate por PID, ou por grupo de processo próprio. Nunca por padrão de linha
   de comando.** `pkill -f` não sabe de quem é o processo, e isolar porta não
   protege disso.
2. **Marque antes, confira depois** — `process_guard.py`. Ele não impede: diz
   que houve. O que ele lista no `marcar` **não é seu**.
3. **Derrube o que você subiu, e PROVE que derrubou** — `sobra --id <id>`. É a
   pergunta oposta do `conferir`, sobre a mesma marca.

### E a terceira regra tem data própria: 02/10/2026

O `conferir` responde verde com dez contêineres seus de pé. Ele pergunta se o
que havia ANTES caiu, e imprime o que subiu como *esperado, se foram suas* —
leitura certa para o dano de 10/09, cega para este.

Nesse dia o Mac de referência travou com **5,2 dos 6 GB de swap em uso**. De
pé: dez contêineres de três stacks, de atividades cujos steps tinham terminado
dois dias antes, e treze processos `node` órfãos — entre eles dois `next dev`
que ninguém acessava havia 24 horas. **As worktrees tinham sido removidas; os
contêineres, não.**

E contêiner não é porta: no macOS quem escuta a porta publicada é o
`com.docker.backend`, um processo só para todos. Contêiner sem porta publicada
— a maioria dos bancos descartáveis deste fluxo — é invisível para o `lsof`. A
VM do Docker reserva 4 GB fixos com um contêiner ou com dez.

A limpeza já estava escrita em prosa aqui, na skill do step 9 e no chat do
Ederson em 30/09/2026. **Prosa não acontece.** Desde a 2.56.0 o `marcar` abre a
dívida `sobra` como `exigida` na tabela de Conferências, e ela segura o
`concluir` em toda trilha, inclusive na `revisao`.

E porque conferência que depende da atividade estar viva não cobre o modo de
falha mais comum deste fluxo — a janela fechada no meio —, há a varredura, que
o gancho de abertura de sessão roda sozinho:

```bash
python3 $PACOTE/tools/process-guard/process_guard.py varrer
```

E uma armadilha do conserto, que vale a doutrina: um `npm run dev` que sobe
vários serviços costuma ser **tudo-ou-nada** e manda `SIGTERM` nos irmãos quando
um falha. Religar com ele derruba de novo os que sobreviveram. Chame os scripts
individuais.
