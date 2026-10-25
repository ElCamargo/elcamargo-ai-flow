# Suíte de teste não pode derrubar a máquina

A regra vale para quem roda suíte de teste com jest ou vitest: o step 8 e as
frentes quality e runtime do step 9.

1. **Limite os workers.** Rode com `--maxWorkers=<N>`. O `N` vem de
   `python3 $C recursos.max_workers_teste`, e quando a chave falta vale `2`. Se o
   gate é um script do npm, o limite vai depois do `--`:
   `npm run test:unit -- --maxWorkers=2`. O jest e o vitest aceitam a mesma flag.
2. **Rode uma suíte por vez.** A base e a entrega rodam **em sequência**, nunca
   em paralelo, e o mesmo vale para unit e integração. Uma suíte em background
   enquanto outra roda conta como paralelo.
3. **Não suba serviço pesado com uma suíte ainda rodando.** Isso inclui Postgres
   no Docker, build e browser. Espere a suíte acabar, ou pare a suíte antes.

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
