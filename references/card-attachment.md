# O que vai ao card, e o que fica no repositório

O card e o repositório guardam coisas diferentes, e confundir os dois estraga os
dois. O repositório guarda **o que foi produzido**; o card guarda **o que está
sendo pedido a alguém**.

Esta página é o procedimento de anexar. A regra de fluxo — quais steps anexam, e
por quê — está em `FLOW.md`, *O card recebe pergunta, não relatório*.

## A regra

> Vai ao card o documento que **pergunta** alguma coisa que **só uma pessoa de
> fora do time técnico pode responder**. Todo o resto fica no repositório.

Não é uma regra sobre importância. O resumo do step 9 é o documento mais denso
do fluxo e não vai ao card quando não pergunta nada — no repositório ele é
versionado, diffável e greppável, e o card não é nenhuma das três coisas.

**Quem decide é a pendência.** Uma pendência aberta, com os seis campos de
`pending-decisions.md` e dono fora do time técnico, é exatamente "algo que só o
analista pode responder".

### Zero pendências é o caso normal

Não é falha sua, e não é sinal de que a revisão foi rasa. A maior parte do que
os steps produzem é **registro**, e registro tem lugar próprio:

```bash
python3 $F artefato <id> --tipo <tipo> --caminho <caminho>
```

O critério anterior era *quem lê*: ia ao card o artefato com leitor fora do time
técnico. Parecia certo e produziu o defeito oposto ao que evitava — quatro steps
produzem documento com leitor de negócio, então quatro anexavam sempre, e o que
precisava de resposta se perdia no meio do que era só registro. **Um card com
seis anexos não tem nenhum.**

## Com pendência, anexe pela ferramenta

Sempre com `$PACOTE/tools/attach/attach.py`, nunca chamando a API do rastreador
direto:

```bash
python3 $PACOTE/tools/attach/attach.py <arquivo.pdf> --card <id> \
  --comentario '<o que é>' --pendencia P-03 --pendencia P-07 \
  --origem <relatorio.md>
```

`--origem` é o Markdown que gerou o PDF. Cada identificador declarado é
conferido contra ele: **declarar pendência que não está escrita no documento não
passa**. É o mesmo idioma do `flow_state pf`, que recusa `--aferido` sem
`--inventario` — a declaração sem a conta que a sustenta é palpite.

Os identificadores vão junto no comentário do anexo, que é o que o card mostra
na lista:

> *Refinamento de negócio — 2 pendências para responder: P-03, P-07*

Quem abre o card sabe o que está sendo pedido **antes** de abrir o arquivo.

## A segunda razão de subir: o contrato

De 15/09/2026, com as trilhas `backend` e `frontend`. O critério de cima é
*"pergunta alguma coisa"* — e há um documento que não pergunta nada e mesmo
assim precisa subir: **aquele de que alguém precisa e cujo repositório essa
pessoa não alcança.**

É o `sdd-frontend` que a trilha `backend` escreve. Quem constrói contra ele
trabalha num card próprio, no repositório da outra superfície: `docs/specs/` não
o alcança, e sem o anexo ele não recebe nada.

```bash
python3 $PACOTE/tools/attach/attach.py <arquivo> --card <card> \
  --contrato 'quem vai construir a camada de tela'
```

`--contrato` **exige nomear o público** — sem ele a razão vira palavra mágica, e
palavra mágica é o que o portão da pendência existe para não ser. O comentário
do card diz na linha que aquilo não pergunta nada, para ninguém abrir o arquivo
procurando o que responder.

**As duas razões não se combinam.** Documento que pergunta *e* informa sobe como
pergunta, com `--pendencia`: a resposta é o que tem prazo. Passar as duas é
recusado.

O `concluir` da trilha `backend` faz isso sozinho, e avisa alto quando a
atividade não registrou `sdd-frontend`.

## As três falhas que moldaram a ferramenta

**1. O card entulhado.** A que está acima: o critério de *quem lê* enchia o card
de PDF. Por isso o `attach.py` **recusa o anexo sem `--pendencia`**.

**2. O upload que mente.** Um PDF foi anexado com `az rest --body "@arquivo"`,
que trata binário como texto e sobe **base64**. A API devolveu 200, o anexo
apareceu no card, e o arquivo não abria — 14.640 bytes onde havia 10.979,
exatamente 4/3, e começando com `JVBERi0x` em vez de `%PDF`. Nada na resposta
dizia isso.

Por isso todo envio é verificado **por ida e volta**: sobe, baixa o que o
servidor guardou, compara o hash, e **não vincula nada ao card se os bytes não
baterem**. Não é opção e não tem flag para desligar.

**3. O anexo que nunca aconteceu.** A ida e volta prova que o byte chegou
íntegro. Ela não prova que o anexo aconteceu — e essa é outra falha, que já
custou uma atividade inteira. O `attach.py` mandava `Content-Type:
application/pdf`, e a API do Azure só aceita três tipos, nenhum deles o do
arquivo. **Todo PDF era recusado com 400.** A obrigação estava escrita na skill,
o comando estava lá, e o anexo nunca subiu. Descobriu-se uma atividade depois,
por acaso, quando alguém perguntou se os resumos estavam no card.

Por isso, depois de anexar:

```bash
python3 $PACOTE/tools/attach/attach.py --conferir <id>
python3 $F artefato <id> --tipo anexo --caminho <nome-do-pdf>
```

**Não se declare concluído com o anexo em dúvida.** Se falhou, diga que falhou e
por quê — uma entrega marcada como não anexada é honesta; uma que diz "anexado"
sem ter conferido é a que custou a atividade.

## A assinatura

Todo comentário ou anexo publicado no card abre com a linha:

> *Gerado com assistência de IA e revisado antes de publicar.*

É a mesma regra da assinatura compartilhada dos documentos, aplicada ao que
circula no board: quem lê tem direito de saber como aquilo foi produzido, e a
frase só é verdadeira se a revisão aconteceu de fato.

## O que isto NÃO resolve

O portão prova que **existe** pendência, não que ela é **boa**. Pendência aberta
por preguiça de decidir abre o card igual — e os três casos de *Quando NÃO abrir
pendência*, em `pending-decisions.md`, são o que segura esse lado. Isso é texto,
não máquina.

Se o card voltar a encher, é aí que se olha primeiro.
