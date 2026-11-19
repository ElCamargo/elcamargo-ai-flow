# Suíte de teste não pode derrubar a máquina

A regra vale para quem roda comando node pesado (jest, vitest, playwright,
stryker, `tsc`, build): o step 8 e as frentes quality e runtime do step 9.

**Pode rodar agora? Uma regra só, e ela mora na ferramenta.**

```bash
python3 $PACOTE/tools/process-guard/fila_pesada.py estado   # sai 0: pode; 1: não
```

A linha `portão:` é a resposta, e a linha `regra:` diz o critério com os
números em vigor: recusa com folga abaixo de 20% ou com memória **entrando** no
swap acima de 1 MB/s. Swap alto e **parado** não impede: é sobra de pico, e o
macOS não o devolve sem reiniciar. Não guarde número de swap seu (em memória de
sessão, em nota, em prompt): a fila, o `gates` e o gancho usam este critério, e
uma regra mais rígida em outro lugar só para o trabalho sem aliviar a máquina.
Fila ocupada não é "não": o `rodar` espera a vez.

1. **Rode pela fila da máquina.** Um comando pesado por raia **na máquina
   inteira**, entre frentes e entre sessões. Desde 2.82.0 são duas raias: a
   **curta** (build, `tsc`, typecheck) e a **longa** (teste, e2e, mutação,
   runner de QA, e todo comando que a fila não reconhece). A fila escolhe a
   raia pelo comando; `rodar --raia curta|longa` escolhe por ela. Um build não
   espera mais o runner de QA de vinte minutos, e dois builds, ou dois testes,
   continuam um por vez. Os dois juntos só entram se o portão da memória
   deixar, e a vigia derruba o que afundar a máquina depois:

   ```bash
   python3 $PACOTE/tools/process-guard/fila_pesada.py rodar -- 'npx jest --maxWorkers=2'
   ```

   Use timeout longo no Bash. A fila espera a vez por até 300 s
   (`--espera <s>`) e, com a vez na mão, **lê a memória** (ver "O que a fila
   lê da memória", abaixo). Recusa da fila sai com `75`, e o comando **não
   rodou**: não conte como vermelho do teste, e não contorne. Diga à pessoa o
   que a fila mostrou. Seguir assim mesmo é decisão dela
   (`ELCAMARGO_SWAP_FORCAR=1`). `fila_pesada.py estado` diz quem está com a
   vez, há quanto tempo, quanto aquele comando costuma levar (a mediana das
   últimas cinco vezes, desde 2.81.0) e se o portão deixaria entrar agora.
   Sem histórico do comando, ele diz que não há estimativa, e não chuta.

   O `python3 $F gates <id>` já passa por ela por dentro, sem embrulho.
2. **Limite os workers.** O `N` vem de `python3 $C recursos.max_workers_teste`,
   e quando a chave falta vale `2`:

   | Runner | Flag |
   | --- | --- |
   | jest | `--maxWorkers=2` |
   | vitest | `vitest run --maxWorkers=2` |
   | playwright | `playwright test --workers=2` |
   | stryker | `--concurrency=2` |

   Se o gate é um script do npm, o limite vai depois do `--`:
   `npm run test:unit -- --maxWorkers=2`.
3. **A frente paralela não roda suíte por conta própria.** Ela entra na fila
   como qualquer outra. A base e a entrega rodam **em sequência**, e o mesmo vale
   para unit e integração. Uma suíte em background enquanto outra roda conta
   como paralelo, e a fila a recusa.
4. **Não suba serviço pesado com uma suíte ainda rodando.** Isso inclui Postgres
   no Docker e browser. Espere a suíte acabar, ou pare a suíte antes.

## Quem está comendo a memória

Quando a fila recusa, ou o `estado` sai 1, a pergunta seguinte é de quem é a
memória. Desde 2.83.0:

```bash
python3 $PACOTE/tools/process-guard/fila_pesada.py memoria
```

Só lê. Mostra os processos agrupados por app (a VM do Docker junto com o app
do Docker), por sessão do Claude Code e por worktree (node, python e java
soltos, pela pasta onde rodam); os contêineres do Docker por projeto do
compose, avisando a pilha cujo worktree já foi apagado; e o limite de memória
da VM do Docker contra o que os contêineres usam agora. Parar pilha e mudar o
limite são decisões da pessoa: diga o que a leitura mostrou e pergunte.

## O gancho que recusa

Com o plugin (ou o `install.sh`, desde 2.64.0), um gancho `PreToolUse` de Bash
lê cada comando. Ele **recusa** o pesado que vem fora da fila e o jest, vitest,
playwright ou stryker que vem sem limite de workers, e responde com o comando
certo já montado. Ele não reescreve o comando: quem roda é o modelo, com a
permissão da pessoa.

O que ele **não** vê:

- script do npm com nome que não diz o que faz quando o `package.json` não
  está à vista: workspace apontado por nome (`--filter`, `--workspace`) e os
  `pre`/`post` do npm. Desde 2.81.0, `npm --prefix frontend run gate` e
  `cd web && npm run verificar` são lidos no `package.json` da pasta;
- o runner que está atrás do `npm test`, e por isso os workers dele;
- servidor de desenvolvimento (`next dev`), que fica fora de propósito porque
  não termina e prenderia a fila;
- o que a pessoa roda no próprio terminal.

## O que a fila lê da memória

Três números, e não um (desde 2.65.0):

| Leitura | De onde | Recusa quando |
|---|---|---|
| swap **mexendo** | `Swapouts` do `vm_stat` (linux: `pswpout`), duas leituras com 3 s entre elas | mais de 1 MB/s indo para o swap (`ELCAMARGO_SWAP_ATIVO_MB_S`), em três amostras seguidas |
| folga | `memory_pressure -Q` (linux: `MemAvailable`) | menos de 20% livre (`ELCAMARGO_FOLGA_MIN_PCT`) |
| swap parado | `vm.swapusage` (linux: `SwapTotal - SwapFree`) | **nunca sozinho**: acima de 4 GB (`ELCAMARGO_SWAP_TETO_GB`) só recusa se não deu para medir se ele está mexendo |

O swap do macOS não baixa quando a pressão passa: depois de um pico, ficam GBs
lá por horas, com a máquina ociosa. A 2.64.0 recusava por esse número sozinho,
e recusava sem motivo. Swap alto e **parado** é sobra; o que trava a máquina é
memória indo para o swap **agora**, ou folga que não comporta o comando. Swap
alto e parado segue, com o aviso "é sobra de um pico anterior".

**A vigia.** O portão vê a máquina antes, e quem a afunda é o comando que ele
acabou de deixar entrar. Enquanto o comando roda, a fila mede a cada 10 s
(`ELCAMARGO_VIGIA_S`) e derruba o grupo de processos **do próprio comando**,
pelo PID, quando duas leituras seguidas mostram a folga abaixo de 10%
(`ELCAMARGO_FOLGA_CRITICA_PCT`), ou o swap 1,5 GB acima do que estava na
entrada (`ELCAMARGO_SWAP_CRESCIMENTO_GB`) e ainda entrando. Derrubado, sai
com `75` e "Interrompido pela vigia": o resultado não vale como vermelho nem
como verde. A vigia não obedece ao `ELCAMARGO_SWAP_FORCAR`: forçar é aceitar
começar com a memória apertada, e não deixar a máquina travar.

**A versão nova sem reiniciar.** Uma sessão aberta antes de um `plugin update`
chama a pasta da versão antiga até o `/reload-plugins`. A fila, chamada de
uma pasta do cache, procura a versão instalada mais nova e passa a vez a ela
(desde 2.65.0). O `flow_state gates` faz o mesmo ao carregar a fila.

Rodar o gate com o limite não é "comando improvisado": o comando continua sendo
o declarado. Muda só quanto da máquina ele ocupa. O resultado dos testes é o
mesmo, só mais lento.

## O caso que escreveu a regra

Em 01/10/2026, às 14:02Z, a frente quality do step 9 do backoffice rodou
`npx jest` duas vezes em background, uma na base e outra na entrega, para
separar a falha pré-existente da nova. Nenhuma das duas tinha `--maxWorkers`.
Num Mac de 10 núcleos e 16 GB, isso deu 9 workers por suíte: **18 processos
node de cerca de 1,6 GB cada**. Às 14:47Z, com as suítes ainda rodando, a frente
subiu um Postgres no Docker.

A máquina travou de 14:51Z a 15:03Z, e a sessão de quem acompanhava caiu. Não
houve como pedir a ninguém para olhar: quando trava, a janela que poderia
investigar trava junto.

Com a perna sombra do step 9, uma mesma frente pode rodar duas vezes. Sem o
limite, o risco dobra.

## A terceira vez, e por que virou código

Em 19/10/2026 o mesmo Mac travou com **14,5 GB de swap**. O retrato tinha nove
processos `node` de PIDs consecutivos, de 1,7 a 2,6 GB cada: um jest no padrão
de `núcleos - 1` workers. Era a terceira vez, depois de 01/10 (duas suítes em
paralelo) e 02/10 (sobras de atividades mortas, 5,2 de 6 GB de swap).

As três regras acima estavam escritas desde 01/10, e o jest rodou sem limite
do mesmo jeito. Por isso, desde 2.64.0, a fila, o teto de swap e o gancho:
o que a prosa pedia, o código agora recusa.
