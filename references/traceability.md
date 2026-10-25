# Rastreabilidade: a matriz que não mente

A matriz liga cada requisito de origem ao que foi decidido sobre ele. Ela é o
que permite o step 4 conferir, o step 9 validar a implementação, e você provar
que nada sumiu.

## A armadilha

**Uma matriz que cobre só um tipo de requisito tem exatamente a aparência de uma
matriz completa.**

Isso já custou quatro requisitos numa especificação marcada como pronta,
revisada, aprovada e mergeada. A análise tinha 39 páginas; foram lidas
integralmente as regras de negócio e os protótipos, e ficaram de fora as vinte
páginas de requisitos funcionais e não funcionais no meio. Três das quatro
lacunas estavam **apenas** na seção RF; a quarta, apenas na RNF.

A hipótese implícita era que a RF reafirma a RN em outra voz. Ela não reafirma:
**acrescenta requisito que a RN não tem**. No caso, acrescentou duas colunas e
uma restrição de perfil — e a restrição de perfil era exposição de dado a quem o
documento não autorizava.

A regra que sai disso: **enumere as seções do documento antes de extrair, e
declare quantos itens saíram de cada uma.** Uma matriz com 64 RN e zero RF, num
documento que tem RF, está incompleta e se anuncia.

## Seção vazia é extração perdida, não seção curta

A armadilha que a contagem não pega sozinha: **uma seção pode existir e sair
vazia sem erro nenhum.**

Numa execução real, a seção de Protótipos de uma especificação de 27 páginas era
uma imagem. A extração de texto devolveu vazio, silenciosamente, e a extração
pronta que o usuário ofereceu já vinha assim. Aquela seção continha **22 itens de
requisito** que o texto não trazia — entre eles um filtro que nenhuma regra
previa, a ausência de outro que cinco itens exigiam, e o único número de tamanho
de página do documento inteiro.

A regra que sai disso: **conte as seções do sumário e confirme que cada uma tem
conteúdo.** Seção que aparece no sumário e sai vazia é sinal de extração perdida
— vá buscar por outro caminho. Renderize a página como imagem e leia dali.

E desconfie de extração pronta que alguém te entregou. Ela pode ter perdido
justamente a parte que ninguém percebeu que existia.

## Como extrair

1. Liste as seções do documento de origem, todas, antes de ler o conteúdo.
   **Confirme que cada uma tem conteúdo antes de seguir.**
2. Extraia item por item, com o identificador original preservado.
3. Ao final, conte por seção e confira contra o documento: `64 RN, 18 RF, 6 RNF,
   25 CA, 31 CT`.
4. Nada de "as demais seguem o mesmo padrão". Se são 64, são 64 linhas.

## Os estados

Cada item da matriz termina em um destes. O vocabulário é o mesmo em todo o
fluxo.

| Estado | Quando usar |
| --- | --- |
| **Confirmado** | Está na análise, ou é sustentado por contrato, código ou decisão vigente |
| **Confirmado com correção** | O requisito vale, mas o texto tem erro que precisa voltar ao analista |
| **Proposto** | É solução sua para uma lacuna; ainda depende de revisão |
| **Pressuposto** | Permite avançar sem mudar contrato material; reversível e visível |
| **Pendente** | Depende de aprovação de negócio, produto, segurança ou arquitetura |
| **Conflito** | Duas fontes determinam comportamentos incompatíveis |
| **Fora de escopo** | Não entra nesta fatia, com justificativa e destino |

`Confirmado com correção` existe porque faltava. Um requisito cujo título
contradiz o corpo, ou cuja numeração está errada, **é do cliente e vale** — mas
marcá-lo como `Proposto` faz o step 3 ler requisito do cliente como sugestão
sua. Numa execução real isso aconteceu com três itens, e o auditor pegou.

`Pressuposto` é o mais perigoso: é onde você decide sozinho e segue. Use só
quando for **reversível** e **visível** — alguém tem que conseguir achar e
desfazer. Se não for reversível, é `Pendente`.

## Pressuposto exige que a resposta fosse alcançável

`Pressuposto` só é legítimo quando a informação **existia e você não a
alcançou** — o documento é ambíguo, o código não decide, o protótipo cala sobre
algo que ele poderia dizer.

Quando a fonte **nunca** ia responder aquilo, pressupor é decidir no lugar de
quem decide. Isso vira pergunta ao humano, no portão, com as opções reais e a
consequência de cada uma.

Numa execução real, uma SDD marcou como `Pressuposto` onde o item de menu de uma
tela nova entraria, justificando que "a barra lateral do Figma está vazia nos
treze quadros". Estava vazia **por construção**: aquele arquivo de protótipo não
desenha navegação, e nunca ia desenhar. O dono do produto respondeu em um clique
— e respondeu diferente do que a SDD tinha assumido.

O teste, antes de escrever `Pressuposto`:

**"Existe algum artefato que eu poderia ter lido e que responderia isto?"**

- **Sim, e eu não li** — vá ler.
- **Sim, e ele é ambíguo** — `Pressuposto`, reversível e visível.
- **Não existe** — é **pergunta**, não pressuposto. Vai para
  `pending-decisions.md` com opções, e sobe ao portão.

A mesma prova vale para a seção "o que não consegui verificar". Uma linha que
diz "o step 6 confirma" quando **nenhum step vai confirmar** é pressuposto
disfarçado de pendência. Se o único caminho para a resposta é perguntar,
pergunte.

`Conflito` nunca se resolve em silêncio. Ele vira pendência com opções, no
formato de `pending-decisions.md`.

## Não multiplique o mesmo requisito

Texto repetido em RN, RF e critério de aceite não são três decisões. Consolide o
comportamento numa linha, **preservando as três origens**. A matriz precisa
mostrar de onde cada exigência veio, sem inventar três exigências onde há uma.


## O identificador se ALOCA, e alocar mal custa caro

Antes de numerar: **quem escolhe "o próximo livre" olhando a própria cópia
colide por construção.** Em 12/09/2026 isso custou 106 arquivos num caso e 378
citações em 32 arquivos em outro — e a camada que dói mais não é o nome do
arquivo, é a regra numerada **dentro** dele, que colide em silêncio e produz
documento internamente contraditório.

Como alocar, quando o identificador não pode mais mudar, e como remapear se for
inevitável: `references/identifier-allocation.md`.

## Requisito sem identificador só entra se ganhar um

A matriz se ancora no identificador: `RN-01`, `CT-14`. Uma lista de escopo não
numerada — *"o sistema deve permitir X, Y e Z"* — **não entra na conferência**,
porque não há o que rastrear.

Isso não é para ser contornado em silêncio. Numere a lista na SDD de origem, e
se o prefixo que você escolheu não for um dos padrão (`RN`, `RF`, `RNF`, `CA`,
`CT`, `RNG`, `US`, `REQ`), **declare-o**:

```bash
python3 $PACOTE/tools/matrix/matrix.py extrair <doc> --prefixos RN,RF,ESC
```

Sem a declaração o identificador novo é invisível para a ferramenta, e a saída
diz "0 itens" com a mesma cara de um documento vazio. Foram três tentativas até
alguém achar a flag — por isso ela está escrita aqui, e não só no `--help`.
