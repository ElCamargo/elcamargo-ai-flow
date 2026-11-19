# Fluxo · Obrigações de todo step de skill

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## Obrigações de todo step de skill

### Disparar não é terminar

**Quem dispara subagente espera por ele.** Parece óbvio e falhou quatro vezes na
POC, em quatro steps diferentes: o step 2 aguardando a completude, o step 3
aguardando a auditoria, o step 3 de novo numa segunda rodada, e o step 9
aguardando as cinco frentes. Todos retornaram dizendo *"disparei, estou
aguardando"* — e o step ficou pela metade, com trabalho em curso e ninguém para
recolhê-lo.

Numa dessas, a frente de segurança tinha achado uma violação de isolamento, e o
achado ficou órfão.

O trabalho do step é **consolidar**. Disparar é o começo dele.

**Se o subagente não retornar**, procure o retorno onde ele possa ter ficado
antes de concluir que não houve — já aconteceu de o resultado existir e ficar
inacessível por quase duas horas, de um trabalho de quarenta e cinco minutos. Se
realmente não houver:

- **nomeie** o subagente que ficou sem resposta;
- declare a entrega **incompleta naquela dimensão**, no artefato e na nota;
- entregue o que você tem.

### Todo retorno passa por uma conferência de segundos

**Não aja sobre o que um subagente disse sem conferir que ele fez.** E a
conferência tem orçamento: **segundos**, não uma segunda revisão. Se está
custando mais de um minuto, deixou de ser conferência e virou outro trabalho —
essa é uma decisão sua, e consciente.

O que se confere é **o que foi pedido**, e o prompt é o contrato. Três perguntas,
nessa ordem, e pare na primeira que responder:

| Pergunta | Como custa segundos |
| --- | --- |
| **O artefato existe?** | `ls` no caminho que ele disse ter escrito, e o tamanho bate com o que ele descreveu |
| **O comando que ele diz ter rodado passa?** | Rode o mais barato e decisivo. O gate, o teste, o portão mecânico |
| **A afirmação que sustenta tudo é verdade?** | Abra **uma** — a que, se falsa, derruba o resto |

Não é desconfiança: é que a alternativa custa mais. Nesta POC, cada conferência
de retorno pegou coisa — o step 4 apontando um defeito que não existia, o step 8
declarando gate verde que tinha 126 invariantes desligadas, e uma auditoria
mandando remover um limiar cuja remoção reprovava a I2 em duas larguras.

E a conferência mais barata de todas é **contar**: seis frentes foram pedidas,
seis voltaram? Um step que dispara cinco e entrega o relatório de seis não
mente — ele não percebeu.

### Persista enquanto trabalha, não no fim

**O que existe só no contexto de um agente morre com ele.**

O `Revisor da Entrega` rodou as seis frentes, **todas voltaram**, e ele travou na
consolidação. Cinquenta e dois minutos, seis frentes de revisão sobre 6094
linhas, e **zero artefato** — os retornos moravam no contexto dele e foram junto.
A execução seguinte começou do zero.

Todo step longo escreve num arquivo de rascunho **conforme trabalha**:

- assim que cada subagente volta, o retorno **bruto** dele, antes de consolidar;
- durante a consolidação, cada achado conforme é julgado.

Custa segundos de escrita. O que ele compra é que um travamento vire *"continue
de onde parou"* em vez de *"comece de novo"*.

A regra vale para você, que dispara — e para o que você pede a quem dispara por
você.

### Um step que não escreve há muito tempo não está pensando

Um agente parado numa chamada de ferramenta **parece** um agente trabalhando: os
dois não respondem. A diferença é observável, e barata:

```bash
stat -f "modificado=%Sm" <arquivo de saída da tarefa>
```

Se o transcrito não é escrito há dezenas de minutos, ele não está pensando — está
travado. Um agente que trabalha escreve a cada chamada de ferramenta.

**Não fique esperando indefinidamente.** Confira, e se estiver parado: mate,
recolha o que foi persistido, e redispare dizendo de onde continuar. A espera
educada não entrega nada, e o usuário deste fluxo pediu orçamento de tempo para
subagente **duas vezes** antes de isto acontecer — a segunda vez, respondi que
não insistiria no assunto. Ele estava certo.

**Vigie, em vez de esperar.** A ferramenta que mede está pronta:

```bash
python3 $PACOTE/tools/watch/watch.py --dir <tasks da sessão>
python3 $PACOTE/tools/watch/watch.py --agente <id>     # os que você espera
```

Ela separa quem entregou de quem parou no meio, ignora comando em background, e
não lista agente de ontem. E declara o que não sabe: agente morto por interrupção
também para no meio, e de fora isso é igual a travado.

**Comando curto, uma coisa por chamada.** A execução que travou morreu num
`Bash` com vários `grep` concatenados por `;`. Não é prova de causa, e é barato
o bastante para valer como hábito.

Uma entrega marcada como não auditada é honesta. Uma espera indefinida não
entrega nada, e o silêncio de um subagente **nunca** conta como aprovação dele.



Todo step que é skill, sem exceção:

1. Lê o estado da atividade antes de começar e confirma que o step é o dele.
2. Produz seus artefatos em Markdown, no local que o `config.toml` define.
3. Registra cada artefato com `flow_state.py artefato`.
4. Roda seu subagente de completude, quando tiver um, **antes** de commitar.
5. Emite o relatório de fronteira humana com `tools/elcamargo-report` e anexa
   ao card, quando o step previr isso.
6. Chama a skill de Git do projeto para commitar.
7. Roda `flow_state.py avancar` e **entrega** o próximo step — sem executá-lo.

## A entrega entre steps

Um step termina imprimindo o comando seguinte, pronto para rodar:

```
Step 2 concluído. 4 pontos levantados, 2 bloqueiam a especificação.

Próximo:
    /elcamargo-system-analyst 1042
```

Duas regras, e as duas têm o mesmo motivo:

**A skill não executa a próxima.** Ela imprime o comando. Quem dispara é o
usuário — que assim vê a saída de cada etapa antes de gastar a seguinte, e
consegue apontar onde a cadeia quebrou quando quebra.

**O próximo step roda em contexto novo** — sessão nova ou subagente, nunca a
mesma janela. O handoff é por arquivo justamente para isso: o step seguinte
precisa ler a SDD, não o raciocínio de quem a escreveu. Contexto herdado faz o
modelo responder ao rastro anterior em vez de responder à especificação, e é
onde a fidelidade cai.

**Entre o 8 e o 9 a regra é trava, não só prosa.** É o par em que ela mais pesa:
a janela que escreveu o código e o revisa tende a concordar com o próprio
raciocínio. Contexto é **sessão mais subagente** — no modo orquestrador o 8 e o
9 rodam na mesma sessão, em subagentes distintos, e está certo. Um hook de
`PreToolUse` grava quem vai rodar cada Bash; o `avancar` do 8 para o 9 guarda
quem fez o 8; o `status` do step 9 avisa quando é o mesmo contexto, e o
`avancar` para o 10 **recusa**. Voltar ao 8 para corrigir passa, porque não
aprova nada. Atravessar é `--forcar --nota`, e fica escrito. Sem o hook —
outro harness, ou comando digitado no terminal — a trava não sabe, e cala em
vez de acusar.

## Autoria dos documentos

Todo documento que sai para o cliente é assinado por **dois**: a skill que o
gerou e a pessoa que o revisou.

No front matter, a skill declara `gerado_por: <nome-da-skill>`. O `operador` do
config nomeia a pessoa. Uma linha do controle de versões sem nome explícito é
assinada pelos dois, e a página do termo de responsabilidade registra que o
documento teve assistência de IA e foi revisado antes de circular.

Assinar só a ferramenta esconde que alguém respondeu pelo conteúdo. Assinar só a
pessoa esconde como o documento foi produzido. Os dois nomes juntos são a única
versão verdadeira, e é por isso que a saída **precisa** ser revisada antes de
sair: a responsabilidade é compartilhada de fato, não de fachada.

## Skills complementares do projeto

Um step genérico pode ter uma skill do projeto que o **complementa**, declarada
em `[complementos]` no config:

```toml
[complementos]
system_analyst = "acme-system-analyst"
```

O step genérico roda primeiro e chama a complementar para o que só faz sentido
naquele projeto. Complementar, não substituir: uma skill de projeto costuma
carregar aprendizado que não cabe no pacote — casos que já custaram retrabalho
ali, convenções da stack, portões próprios. Descartar isso numa migração é
perder justamente o mais caro.

## Formato dos artefatos

**Markdown é o formato canônico.** Tudo que uma skill produz e outra consome é
MD versionado. PDF e DOCX são exportações, geradas por
`tools/elcamargo-report` **apenas na fronteira com humano**: o relatório que
volta para o analista de negócio, o anexo do card.

O motivo é operacional: o `implemented-sdd-reviewer` precisa *ler* a SDD para
conferir a implementação. PDF não é diffável, não é greppável, e não versiona
com sentido.

## Configuração do projeto

O pacote não sabe nada de nenhum projeto. Tudo que é específico entra por
`<.agents>/config.toml`. Ver `config.example.toml`.
