# Documento não viaja: CPF e CNPJ fora do contexto

Um CPF ou CNPJ **por extenso**, com dígito verificador válido, que entra no
contexto de um agente pode fazer toda chamada seguinte voltar com:

> `403 Requisicao bloqueada pelo guardrail` (`authentication_failed`)

Isso **não é falha passageira**. É o contexto que está contaminado, e toda
resposta relê o contexto inteiro. Retomar o mesmo agente, ou mandar a ele um
`SendMessage`, reenvia o documento e volta com o mesmo 403.

A regra tem duas metades: **prevenir**, que é de todo agente, e **recuperar**,
que é de quem dispara.

## O caso medido, em 30/09/2026

Sessão `acme-backoffice-90`, card 1052, step 9. Medido nos
transcritos, sem abrir número nenhum:

- a frente `implemented-business-reviewer` pegou o CPF de teste com `grep` e
  `sed` na **SDD de negócio**, e o devolveu pela chamada **`SubagentHandback`**,
  e não como texto final;
- o step-runner da volta 2 foi barrado logo depois de dar `cat` no **relatório
  da volta 1**, que trazia o CPF escrito;
- os dois arquivos estavam gravados na branch da atividade: a SDD de negócio e
  o relatório de revisão da volta 1. Havia mais seis specs antigas do projeto
  com documento por extenso.

**Consequência:** o documento viaja pelo **artefato gravado no repositório**, e
não só pela devolução. Um relatório escrito com o CPF contamina o próximo
agente que o ler, em outra volta, em outro dia. Por isso a prevenção alcança o
arquivo, e não só a última fala.

`SubagentHandback` apareceu em 11 de 198 subagentes dos três dias anteriores. É
um jeito novo de devolver, e está se espalhando. As ferramentas deste pacote o
leem como última fala.

## O que não sabemos

**Por que a frente leu o CPF e seguiu trabalhando, e o orquestrador foi
barrado.** Pode ser o volume, a posição no contexto, a forma do documento ou
outra coisa. A regra não depende da resposta: ela tira o documento do caminho de
todos, e a recuperação vale para quem quer que seja barrado.

## Prevenir: todo agente

1. **Marcador, nunca o número.** Onde o texto precisaria do documento, escreva
   `[CPF]` ou `[CNPJ]` e cite de onde ele veio (`arquivo:linha`). Quem precisar
   do valor abre a linha. Vale para relatório, SDD, achado, retorno, comentário
   de card e mensagem de commit.
2. **Saída de teste e de `grep` passa pelo filtro** quando pode trazer
   documento: fixture, seed, spec com exemplo, log de teste.

       comando 2>&1 | python3 $PACOTE/tools/doc-mask/doc_mask.py

3. **Fixture com documento se lê pelo `grep`, e não pela leitura inteira.** A
   ferramenta de ler arquivo não passa por filtro:

       grep -n 'padrão' arquivo | python3 $PACOTE/tools/doc-mask/doc_mask.py

4. **Confira o artefato antes de devolver.** Sai 1 e aponta a linha, sem nunca
   imprimir o número:

       python3 $PACOTE/tools/doc-mask/doc_mask.py conferir <arquivo>...

5. **Exemplo inventado também conta.** Quem desenha tela ou escreve spec não
   inventa CPF com dígito válido: use o marcador, ou um valor formatado que não
   feche o dígito.

O `flow_state artefato` avisa quando o arquivo registrado tem documento por
extenso. **Avisa, não recusa**, porque uma spec de campo CNPJ pode trazer
exemplo de propósito. O aviso é para você decidir, não para passar batido.

**O que conta como documento** está no cabeçalho do `doc_mask.py`: formatado
por inteiro, sempre; sem formatação, só quando o dígito verificador fecha. Por
isso timestamp, id e telefone passam.

## Recuperar: quem dispara

Quando um disparo volta com o 403, ou quando **você** passa a recebê-lo:

1. **Não retome e não mande `SendMessage`** a quem foi barrado. Não redispare o
   mesmo prompt com o mesmo relatório anexado.
2. **Colha as devoluções, mascaradas:**

       python3 $PACOTE/tools/doc-mask/doc_mask.py devolucoes --raiz <worktree>

   Ele lê os transcritos dos subagentes do projeto (`--raiz` é a worktree,
   quando houver), grava a última fala de cada um, mascarada, numa pasta, e
   marca `BLOQUEADA` a que morreu no 403.
3. **Dispare um contexto novo apontando a pasta.** Passe o endereço; não leia os
   arquivos na janela que orquestra. Quem **entregou** não se redispara: o
   trabalho dela está na pasta.
4. **Limpe o artefato que carregou o documento.** Rode o `conferir` na SDD e nos
   relatórios da atividade e troque o número pelo marcador
   (`doc_mask.py < arq > arq.novo`), senão o próximo leitor é barrado igual.

Se a janela principal for a barrada, a saída é a mesma, de fora: uma janela nova
roda o `devolucoes` e segue daí.
