# Fluxo · Anexar é ação verificada

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## Anexar é ação verificada

Todo relatório que vai para o card sobe por `tools/attach/attach.py`, nunca pela
API do rastreador direto. A ferramenta **verifica por ida e volta**: envia,
baixa o que o servidor guardou, compara o hash, e só vincula ao card se os bytes
baterem.

**Um upload que mente é pior que um que falha** — já aconteceu aqui, com a API
devolvendo 200 sobre um PDF que não abria. Por isso a verificação não é opção e
não tem flag para desligar.

Para conferir o que está no card:

```bash
python3 tools/attach/attach.py --conferir <card>
```

### Verificar que subiu é do step, não do usuário

A verificação de ida e volta prova que **o byte chegou íntegro**. Ela não prova
que **o anexo aconteceu** — e essa é outra falha, que já custou uma atividade
inteira: a ferramenta recusava todo PDF com 400, a obrigação estava escrita na
skill, e ninguém percebeu até alguém perguntar se os resumos estavam no card.

Daí duas obrigações depois de anexar, e as duas são baratas: rodar `--conferir`,
e registrar o anexo no estado da atividade com `artefato --tipo anexo`. **O step
não se declara concluído com o anexo em dúvida** — uma entrega marcada como não
anexada é honesta; uma que diz "anexado" sem ter conferido é a que custou a
atividade.

Os três defeitos por inteiro, com os números que os provaram, estão em
`references/card-attachment.md` — junto do procedimento que eles moldaram.

### O card recebe pergunta, não relatório

O critério antigo era **quem lê**: ia ao card o artefato com leitor fora do time
técnico. Ele parecia certo e produziu o defeito oposto ao que evitava — quatro
steps produzem documento com leitor de negócio, então quatro anexavam, e o card
virou uma pilha de PDF em que o que precisava de resposta se perdia no meio do
que era só registro. **Um card com seis anexos não tem nenhum.**

O critério agora é **o que exige resposta**:

> Vai ao card o documento que **pergunta** alguma coisa que **só uma pessoa de
> fora do time técnico pode responder**. Todo o resto fica no repositório.

Não é uma regra sobre importância. O resumo do step 9 é o documento mais denso
do fluxo e continua não indo ao card quando não pergunta nada: ele é versionado,
diffável e greppável no repositório, e o card não é nenhuma das três coisas.

**Quem decide é a pendência.** Uma pendência aberta, com os seis campos de
`references/pending-decisions.md` e dono fora do time técnico, é exatamente "algo
que só o analista pode responder" — e é o que abre o portão: sem `--pendencia`,
o `attach.py` **recusa**.

O procedimento inteiro — o comando, o que a ferramenta recusa e por quê, e a
conferência obrigatória depois de anexar — está em
`references/card-attachment.md`, num lugar só. Ele já esteve copiado em quatro
skills, que é onde a divergência entra sem ninguém ver.

| Step | Quando vai ao card |
| --- | --- |
| 2 · análise de negócio | Quando a revisão abriu pendência para o analista |
| 3 · análise de sistema | Quando a SDD tem decisão que só o negócio fecha |
| 6 · telas | Quando uma divergência de tela ficou sem dono técnico |
| 9 · revisão da entrega | Quando um achado ficou aberto e depende de decisão de fora |
| 4 · revisão da spec | Nunca: veredicto é instrumento do fluxo, serve ao step 3 |
| 8 · desenvolvimento | Nunca: resumo de implementação é técnico, e o diff o conta melhor |
| `concluir` da trilha `backend` | **Sempre**: o `sdd-frontend` sobe como contrato — ver abaixo |

**A segunda razão, e ela não é pergunta.** De 15/09/2026: sobe ao card também o
documento de que alguém precisa **e cujo repositório essa pessoa não alcança**.
É o `sdd-frontend` que a trilha `backend` escreve — o contrato que outro time
vai construir contra, num card próprio, sem acesso a este repositório. Sem o
anexo ele não recebe nada, e o critério de cima o deixaria de fora com razão:
contrato não pergunta, informa.

`attach.py --contrato "<quem>"` declara isso, **exige nomear o público** e faz o
comentário do card dizer, na linha, que não há o que responder. As duas razões
não se combinam: documento que pergunta *e* informa sobe como pergunta. O
`concluir` da `backend` anexa sozinho, e avisa alto quando a atividade não
registrou nenhum `sdd-frontend` — ele é o produto de verdade daquela trilha.

Zero pendências é o caso **normal**, não a exceção — e nele o step registra o
artefato e segue:

```bash
python3 $F artefato <id> --tipo <tipo> --caminho <caminho>
```

### Arquivo renomeado no meio da atividade

O `artefato` só acrescentava, e isso produzia **ponteiro morto**. Medido em
24/09/2026: uma spec renomeada durante a atividade fez o `status` listar **três**
`sdd-sistema`, um deles apontando para arquivo que não existia mais. As seis
frentes do step 9 **abrem** esses caminhos — a que não achar reporta *"a spec não
existe"*, e o achado parece defeito da entrega quando é ponteiro velho.

Renomeação **troca**, não acrescenta:

```bash
python3 $F artefato <id> --tipo <tipo> \
    --substituir <caminho antigo> --caminho <caminho novo>
```

Artefato que deixou de existir **sai com explicação**:

```bash
python3 $F artefato <id> --tipo <tipo> --caminho <caminho> \
    --retirar --nota 'por quê'
```

`--nota` é obrigatória ali porque um registro que some sem explicação é
indistinguível de um que nunca houve — a mesma razão do rastro no `corrigir`.

**E o `status` marca `(AUSENTE)`** o caminho que parece arquivo e não existe nem
na raiz do projeto nem na worktree da atividade. Registrar um assim **avisa na
hora e registra assim mesmo**: recusar perderia o registro de um artefato que
existe, que é a mesma razão pela qual tipo fora do vocabulário passa.

A conferência só roda no que **parece arquivo** — barra e extensão no último
segmento, sem esquema de URL. `prototipo` recebe caminho de componente do Figma,
`anexo` recebe nome de anexo de card, e nenhum dos dois vira alarme.

As decisões dos portões continuam sem virar anexo: elas moram no repositório, ao
lado da spec que governam, e quem as tomou foi a pessoa que leria o card.

**O portão humano não depende do anexo.** Os steps 6 e 9 entregam o portão como
perguntas — cartões clicáveis, no máximo quatro — e não pedindo que alguém leia
um PDF. Um anexo a mais nunca foi o que fez o portão andar.
