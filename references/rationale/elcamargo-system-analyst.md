# Rationale — Step 3 · System Analyst

Explicação da skill `elcamargo-system-analyst` (step 3): história, incidentes, números medidos e justificativas longas que a SKILL.md carregava. Isto **não é instrução** — quem executa o step segue a SKILL.md; este arquivo só documenta o porquê.

## O MODO do disparo decide se você vai esperar

Foi assim que um step 9 gastou **193.310 tokens em três turnos dizendo que aguardava**, e entregou zero.

## O que o FLOW.md cobre

Ele é o contrato do fluxo, e traz o que nenhuma skill repete por inteiro: como o portão humano é entregue, como você fala dos steps no chat, o limite de voltas entre quem faz e quem revisa, e o que todo step deve ao próximo.

## Onde a ferramenta mora: os três lugares

# Onde a FERRAMENTA mora. Três lugares possíveis, em ordem de confiança, e
# cada linha só corre se a anterior não achou uma pasta que existe:
#
#   1. `CLAUDE_PLUGIN_ROOT`  o harness diz. Não confie que ela SEMPRE chega
#      aqui — ela é documentada para hook, e para skill não está confirmado.
#   2. `.agents/elcamargo-flow`  o pacote copiado dentro do projeto.
#   3. o cache de plugin instalado, a versão mais alta.
#
# A terceira existe porque a primeira é incerta: sem ela, um projeto que só tem
# o plugin ficaria sem pacote se a variável não chegasse. Com ela, o pior caso
# é achar pelo caminho mais feio — e não falhar.
#
# O estado do PROJETO — `config.toml` e `atividades/` — continua no `.agents`
# nos três casos. Só a ferramenta se move.

## Skill complementar: o que ela costuma carregar

Costuma carregar convenções da stack, portões próprios e casos que já custaram retrabalho naquele projeto.

## Por que extrair a matriz mesmo sem o step 2

O step 4 vai cobrar rastreabilidade de qualquer forma.

## Por que não reescrever tudo ao corrigir o veredicto

Reescrever a especificação inteira ignorando o veredicto costuma reintroduzir a mesma lacuna.

## O mapa do terreno: o custo medido e o que ele devolve

Numa execução real este step gastou **284 mil tokens e 91 chamadas de ferramenta** para especificar 18 requisitos, e a maior parte foi descobrir onde as coisas moram. O mapa devolve, por papel: entidades com as colunas e os decorators, migrations com só o SQL que toca o domínio, endpoints com a rota montada, métodos públicos dos serviços, specs anteriores, ADRs, componentes, testes, arquivos de tradução, os códigos de erro já em uso, e a memória de rejeição que cita o assunto.

## A base: a branch errada por 33 commits

Na mesma execução, a análise pressupunha um painel que existia só numa branch de feature **33 commits à frente e não mesclada** — especificar contra a branch padrão teria quebrado no primeiro import.

## O grafo de conhecimento: o que ele alcança

Ele responde barato o que o mapa não alcança — travessia transitiva, caminho entre dois conceitos, arquivos que tratam do assunto com outro vocabulário.

## Por que ler a memória de rejeição

A segunda diz o que o produto decidiu **não** fazer — e uma solução técnica elegante para algo já recusado é trabalho perdido antes de começar.

## Por que só a profundidade necessária

O mapa já lhe deu os caminhos; o que falta é abrir os que importam, não redescobrir quais são.

## Por que não criar SDD nova para algo que já tem dono

Uma SDD nova para algo que já tem dono espalha a verdade em dois lugares.

## Por que identifier-allocation.md antes de numerar

Pegar "o próximo livre" que você vê na sua cópia colide com o outro ramo por construção — e a regra numerada dentro da spec colide **em silêncio**, produzindo documento contraditório que passa em qualquer portão de citação.

## A segunda SDD não é rascunho

Na trilha `backend`, o `sdd-frontend` é o que o time mobile consome — e esse time não está neste fluxo, não lê o arquivo da atividade e não vai perguntar.

## O contrato verificável: quem chama e o que sobra sem isso

O step 9 vai chamar cada uma delas e comparar. Uma linha de contrato que não dá para exercitar é uma linha que ninguém vai conferir.

## Por que registrar o sdd-frontend como artefato

Quem vai construir a tela trabalha num card próprio, noutro repositório, e não alcança `docs/specs/` — sem o registro, o `concluir` avisa e ninguém do outro lado recebe nada.

## Por que completar em vez de reescrever a SDD da outra camada

Ela pode ter sido escrita pela outra metade semanas atrás, e reescrevê-la apaga decisão que alguém já tomou e que pode já estar implementada.

## A conferência que só a frontend faz

Some a isto uma conferência que só ela pode fazer: **o backend pode ter andado** desde a outra metade.

## O custo de contrariar uma ADR em silêncio

Contrariar uma ADR em silêncio é o defeito mais caro deste step.

## Por que conferir citação por comando

Uma spec de sistema cita o código o tempo todo — `arquivo.ts:NN`, o trecho entre aspas, o intervalo de linhas. Afirmação escrita de memória é o defeito mais comum deste step.

## O achado que a conferência de citação já pegou

Custa segundos e tira do subagente uma classe inteira de achado — numa spec real, o intervalo `79-81` que terminava na 82 e a transcrição de um `spec.ts` que divergia do arquivo.

## O que a citação certa não prova

Foi assim que uma spec afirmou que um diálogo "não acompanha o viewport" citando o arquivo que diz o contrário.

## Por que a auditoria diverge: os números de uma rodada real

A auditoria converge num documento congelado e **diverge** num que continua sendo corrigido: cada correção escreve texto novo, e texto novo tem taxa de defeito própria. Numa execução real a mesma spec deu 12, 6, 5, 1, 0 achados em cinco rodadas — e a rodada seguinte, sobre a versão corrigida, achou **dez** outra vez.

## Achados abertos: quem consome, e por que declarar

Ela viaja com o documento e é entrada para o step 4 e para o step 9, que já leem a SDD. Declarar é mais honesto que esconder e mais barato que a sexta rodada.

## Por que o corretor único faz a auditoria divergir

O corretor único, em série, é o que faz a auditoria divergir: ele reescreve o documento inteiro a cada volta e o defeito de uma correção contamina a próxima.

## O artefato que cresceu durante a auditoria

Numa execução real o auditor registrou md5 e data, e viu o arquivo **crescer de 156 para 159 linhas enquanto auditava** — metade dos achados dele podiam já estar corrigidos, e ele não tinha como saber quais.

## O relatório que travou ao entregar

Numa execução real ele produziu o relatório inteiro e travou ao entregá-lo — o resultado existia e ficou inacessível por quase duas horas, de um trabalho de quarenta e cinco minutos. Uma entrega marcada como não auditada é honesta; uma espera indefinida não entrega nada.

## O que a verificação mecânica já achou

Numa execução real ele descobriu que o total declarado dizia 155 e a matriz tinha 159 linhas; que a contagem por seção esquecia duas séries que o próprio documento criou; e que a frase "nada foi descartado em silêncio" era falsa para sete itens.

## Além do texto: a imagem renderizada a 14×

No mesmo caso, o auditor renderizou uma imagem a 14× e mediu a geometria para refutar uma afirmação sobre o que o protótipo mostrava — descobrindo que a recomendação de uma pendência de severidade alta se apoiava em evidência inexistente.

## As obrigações do anexo vieram de falhas medidas

As três vieram de falhas medidas, e duas delas só apareceram uma atividade depois.

## O mecanismo: por que a notificação não chega no subagente

Ali a notificação de conclusão não chega — o turno acaba com as frentes rodando e ninguém para consolidá-las.

## O mecanismo dos dois modos na janela principal

Bloqueante prende a janela até a leva voltar; segundo plano a devolve, e a notificação reinvoca a sessão.

## Por que a mesma leva vai numa única mensagem

Senão elas não rodam em paralelo, e a leva deixa de ser leva.

## Este step dispara subagentes

Este step dispara subagentes e **esperar o retorno é o trabalho dele**.

## O mapa é índice: o método pode estar quebrado

Um método que ele lista pode estar quebrado.

## Por que o mapa pode parecer pequeno demais

O que não tem o termo no nome não aparece.

## Grafo velho é pior que grafo nenhum

Grafo velho é pior que grafo nenhum.

## O ofício: por que Pressuposto é o estado perigoso

`Pressuposto` é o perigoso.

## O ofício: os temas de technical-posture.md

Reversibilidade, compatibilidade, retentativa, autorização, erro, fatia.

## O que a conferência de citação confere

Ela confere que o arquivo existe, que a linha existe, e que o trecho entre aspas ao lado da citação aparece mesmo lá.

## O que o auditor faz de mais valioso

Contar, conferir numeração, cruzar afirmação com evidência.

## Uma auditoria sobre alvo móvel não vale

Uma auditoria sobre alvo móvel não vale.

## Por que registrar o sdd-frontend como artefato

É por ele que o `concluir` acha o contrato e o **anexa ao card**.

## Por que board-git-management não mexe no estado da atividade

Ela delega ao gerenciador de Git do projeto e não mexe no estado da atividade, que é seu.

## Por que não executar o comando do próximo step

Quem dispara é o usuário, e o próximo step roda em contexto novo — ele precisa ler a SDD, não o seu raciocínio ao escrevê-la.

## Disparar é o começo do step; consolidar é o trabalho dele

Disparar é o começo do step; consolidar é o trabalho dele.

## Transição removida (redundante com o título da próxima seção)

Se ele vai ao card, é o que a próxima seção decide.

## Zero pendências é o caso normal

Zero pendências é o caso **normal**, não uma falha sua.

## O que o procedimento de anexo cobre

O comando, o que a ferramenta recusa e por quê, a conferência obrigatória depois de anexar, e a linha de assinatura que abre todo comentário no card.

## O que o step 2 já resolveu

O step 2 resolveu o quê; aqui o assunto é dado, contrato, evento, migração, tela e teste.

## O que o mapa devolve

O mapa faz essa varredura uma vez, por papel, e devolve onde as coisas moram.

## O ofício: afirmar não é provar

Afirmar não é provar.

## Nenhuma saída é seguir em frente calado

Nenhuma das duas saídas é seguir em frente calado.

## A skill complementar completa, não substitui

Ela complementa, não substitui.

## O silêncio do subagente nunca conta como aprovação

O silêncio dele nunca conta como aprovação.

## Antes de anexar, decida se o card deve receber isto

Antes de anexar, decida se o card deve receber isto.

## O artefato fica junto dos que a seção já registrou

O documento fica registrado junto dos artefatos que esta seção já registrou.

## Num projeto sem skill complementar

Num projeto sem skill complementar, é delas que vem a diferença entre uma especificação que o desenvolvedor segue e uma que ele reinterpreta.

## Onde a trilha é declarada

A atividade declara `escopo` no front matter.

## O custo de um contrato vago

Contrato vago custa o trabalho de outro time, semanas depois.

## Evidência não é autorização

Não trate código existente como autorização para perpetuar uma prática insegura.

## Como escolher entre bloqueante e segundo plano

Escolha pelo que a janela precisa fazer enquanto espera.

## O auditor pode ir além do texto

Ele pode ir além do texto — não é preciso pedir.

## A preservação vale também para documentação

A alteração local preservada inclui documentação.

## Por que `alta` que sobrou não pode ficar aberto

É o que faz o desenvolvedor construir errado.
