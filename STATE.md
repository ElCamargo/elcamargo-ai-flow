# Estado do pacote — 31/08/2026

Condensação do que a POC do card 1057 produziu. Não é changelog: é o que alguém
que pegar este pacote precisa saber para não refazer o caminho.

## O que a POC mediu

Uma atividade real, de ponta a ponta: card 1057, "FAQ da Plataforma". Dez steps,
quatro portões humanos respondidos, entrega em produção pendente só de baseline
visual.

| | |
| --- | --- |
| Tempo de IA | ~24h |
| Espera humana | ~10min — **1% do total** |
| Código | 53 arquivos, 6.094 linhas, mais duas voltas de correção |
| Documentos | 9, somando ~7.000 linhas |
| Achados de revisão | 21 na volta 1 (9 `alta`), 2 novos da segurança na volta 2 |

**O gargalo nunca foi o humano.** Foram os pares fazedor↔revisor sem limite de
volta: cinco rodadas de auditoria dentro do step 3, duas reprovações do step 4, e
defeitos introduzidos ao corrigir. Estimados **~7h de retrabalho**.

## As sete regras que saíram daqui, e o erro que produziu cada uma

| Regra | O erro que a produziu |
| --- | --- |
| **Duas voltas em todo par fazedor↔revisor** | A auditoria convergiu a zero em cinco rodadas — e a rodada seguinte, sobre o texto corrigido, achou dez outra vez. Não converge porque cada correção escreve texto novo |
| **Severidade por alcance em documento** | 33 achados de coerência, ~13 alcançavam código. Os outros vinte custaram sete horas |
| **Portão humano chega como pergunta, não leitura** | Uma spec de 1.900 linhas tem uma dúzia de decisões enterradas em prosa. Pedir leitura transfere a quem decide o trabalho de achar a decisão |
| **Decisão que só o dono sabe vira pergunta, não `Pressuposto`** | A SDD assumiu onde entrava um item de menu porque "o Figma está vazio". Estava vazio **por construção** — aquele arquivo nunca desenhou navegação |
| **`Afirmar não é provar` vale para a frase que a correção traz junto** | Re-editar o trecho funciona; o que falha é a prosa nova escrita para justificar. Numa rodada, a afirmação errada era desmentida por um documento a dezesseis linhas do trecho citado |
| **Persista enquanto trabalha** | Um step rodou seis frentes, todas voltaram, e ele travou consolidando. 52 minutos, zero artefato |
| **Conferência de segundos em todo retorno** | Cada conferência pegou coisa: um defeito que não existia, um gate verde com 126 invariantes desligadas, um achado cuja correção reprovava a I2 |

## As ferramentas, e o que cada uma NÃO prova

- **`matrix.py`** — extrai e confere a matriz de rastreabilidade. Não prova que a decisão sobre cada item está certa.
- **`citations.py codigo`** — toda citação `arquivo.ts:NN` existe, a linha existe, e o trecho entre aspas aparece lá. **Não** prova que a conclusão tirada dela está certa.
- **`watch.py`** — quem está trabalhando e quem travou, por mtime do transcrito. Não prova utilidade, só vida; e não distingue travado de morto por interrupção.
- **`attach.py`** — sobe, baixa, compara hash. Prova que o byte chegou íntegro, **não** que o anexo aconteceu — daí a obrigação de `--conferir` depois.
- **`briefing.py` / `domain.py`** — dossiê e mapa do terreno. São índice, não evidência.
- **`audit_package.py`** — audita o instrumento: frontmatter, deriva de nome, tamanho. Não prova que a skill faz o que a descrição promete.
- **`outcome.py`** — conta o que aconteceu com cada achado. Não prova que a correção conserta, que o descarte era justo, nem que o aceite foi de uma pessoa.
- **`ratchet.py`** — separa o que a entrega quebrou do que já falhava. **Não** prova que a falha conhecida é aceitável: ela não reprova *esta* entrega, continua sendo de alguém.
- **`profiles.py`** — o diff toca autorização? E a passada por perfis prova o que diz? **Não** prova que o `Esperado` estava certo: se o perfil deveria poder e você escreveu `negado`, ele concorda e erra junto.
- **`honesty.py`** — `.only` commitado, pulo estático, asserção trivial, teste que simula o que testa, e quantos casos não rodaram. Procedência `estrutural` por inteiro: **não reprova sozinha**, exceto `.only`. Não substitui mutação.

### Uma verificação que foi derrubada, para ninguém tentar de novo

"O número declarado bate?" Tentada de dois jeitos: mesmo substantivo com dois
números (**29 falsos** numa spec limpa — em português se conta tudo) e contagem
declarada contra a lista abaixo (**34 em 38** — spec densa é quase toda tabela).
Entender a que lista o número se refere é leitura, não regra. O motivo está no
`citations.py`.

## Defeitos de ferramenta que a POC achou, e que valem como classe

Todos da mesma família: **a ferramenta entrega algo que parece completo e não é.**

- O conferidor de matriz lia `CS-01` como âncora de seção → 72 falsos `[ALTO]`.
- O mesmo conferidor lia tabela de changelog como matriz → 4 falsos.
- O `attach.py` mandava `Content-Type: application/pdf`, e a API só aceita três — **todo PDF era recusado, e ninguém percebeu por uma atividade inteira**.
- O dossiê trunca o diff em silêncio quando há arquivo não rastreado grande na árvore: reportou `+26903` onde o real era `+6094`, porque um PDF entrou como texto. **Duas vezes na mesma atividade.**
- O venv do ReportLab morava em `/tmp`, que o macOS limpa. Aparecia **meio apagado**, o que é pior que ausente.
- O relatório registrou um aviso de lint pré-existente como `app-shell.tsx:176`. A entrega inseriu código acima, e hoje o mesmo aviso mora na **185** — número de linha na identidade de uma falha conhecida faz a catraca devolver a entrega por um aviso que ninguém tocou.
- A detecção de superfície de autorização acusou **três `.md`** na primeira passada: uma especificação que *descreve* a regra casa com todos os padrões e não enforça nada. E o conferidor de perfis acusou uma observação bem escrita porque `n/?a` casa com **"na"** — *"seis categorias na tela"* — e `todo\b` casa com *"todo o menu"*. Em português, sigla curta como padrão é gerador de falso.
- A lente de honestidade acusou **3, depois 35, depois 5** achados contra o repositório real, e **todos eram legítimos**: helper de asserção com nome próprio, `.not.toHaveBeenCalled()` provando "não faz nada", e contagem que É o comportamento. Depois das três correções: 135 arquivos, zero achados. Uma regra plausível encontra o padrão certo e a intenção errada.
- A primeira versão do `outcome.py` leu **cinco `não fechado` como fechados** no relatório real da POC — a taxa de conversão subiu sozinha, para o lado que agrada. Achado pela própria ferramenta rodando contra o próprio relatório, e não pelo teste de fumaça, que só tinha casos bem escritos.

## O que a POC do 1057 fechou depois, e como

O card foi mesclado na `main` (`f5d7551`), e o fechamento das condições do portão
produziu três coisas que valem como padrão:

- **A matriz de autorização** — sete perfis × sete rotas contra as guardas de
  produção, `Reflector` de verdade lendo decorator de verdade. Cada mutação
  mordida por um perfil diferente; a troca de chave de `delete` por `write` só
  morre por causa do perfil **parcial**, e a chave vinda de tenant só morre por
  causa do perfil **tenant-scoped**. Matriz de tudo-ou-nada não veria nenhuma
  das duas.
- **O comando de perfil** (`192c02f`) — `npm run perfil -- <nome> --token`, sem
  criar conta e sem senha. Três dos quatro perfis derivam de role do banco. Ele
  pula a autenticação, não a autorização.
- **A prova por execução** — contra Kong e banco reais, o ator só-leitura lista
  com `200` e escreve com `403`, na mesma sessão. Era o último item da `G10-03`
  sem prova.

## A conferência que deixa rastro

Uma obrigação escrita em prosa não acontece: *"entrar com ator sem a permissão"*
viveu meses na frente de execução e **nunca aconteceu uma vez**, porque ninguém
registrava e portanto ninguém sabia.

O arquivo da atividade ganhou uma terceira tabela — **Conferências** — com quatro
veredictos: `exigida` e `falhou` seguram o `concluir`; `ok` libera; `nao-coberta`
**passa e fica visível**, que é a única saída honesta para o que não deu para
cobrir.

**Quem descobre a obrigação é quem a registra.** `profiles.py superficie
--registrar <id>` grava `exigida` sozinho quando o diff toca autorização — um
step que rodou a detecção não consegue mais esquecer de exercitar.

## O que continua aberto

- **O nome da porta se repete e não se distingue dos steps.** No seletor de skills a porta aparece como `elcamargo-ai-flow:elcamargo-ai-flow` — plugin e skill têm o mesmo nome, então o par sai duplicado —, e as **oito** skills do pacote começam com `elcamargo-`, o que faz a porta parecer uma opção entre iguais. Ela não é: o próprio SKILL.md dela declara que *"os steps têm skills próprias e não precisam ser chamados pelo nome"*. Um seletor onde as oito se parecem convida exatamente ao que o desenho recusa — chamar um step direto.

  **O ajuste é estreito, e é importante não confundir as duas metades.** O nome do **plugin** aparece em 22 arquivos, e ele tem que ficar: é o comando de instalação que já circula, o `marketplace.json` e o caminho do cache que o `config.py` usa para resolver `$PACOTE`. Só a metade da **skill** precisa mover — as ~19 ocorrências de `/elcamargo-ai-flow` em 15 arquivos. Renomeando só ela, o seletor passa a mostrar `elcamargo-ai-flow:<nome>`, sem duplicação.

  **As duas varreduras que morderiam se ficassem de fora:** `tools/anchor/anchor.py` imprime `/elcamargo-ai-flow` no hook de toda mensagem — esquecer ali faz a âncora sugerir um comando que não existe mais, em silêncio; e as sete SKILL.md dos steps citam a porta uma vez cada, para devolver quem entrou pelo lugar errado. O `test_package.py` prende `name` == pasta, então a pasta e o front matter mudam juntos.

  Direções, sem decidir: um verbo de entrada, ou o nome curto do fluxo. **Anotado durante a primeira chamada real, para ajustar depois do teste da trilha `curta`** — mexer no nome da porta antes de exercitá-la trocaria o teste de uma coisa pelo teste de outra.

- **Qualidade de tela: fechada em acessibilidade, SEO e boas práticas na 2.3.0; performance segue não coberta.** O formato `lighthouse` da catraca cataloga as auditorias **binárias** que reprovam, com id estável. **Performance não entra**: o score dela é dominado por rede e CPU de quem roda — a página que a captura quebrou de propósito tirou `performance = 1`. Piso por categoria exigiria série de medições do mesmo projeto para saber qual é a variação normal; sem ela é chute. Declarado como não coberto, não como pendente.

- **O dossiê que trunca** — o defeito está identificado e não corrigido.
- **Orçamento: fechado por atividade na 2.2.0; por step é impossível com o dado de hoje.** `[metricas] orcamento_usd` faz o `avancar` parar quando a última coleta passou do teto, e liberar com `--forcar --nota`. **Por step não dá:** o coletor só atribui step aos subagentes, e os turnos do orquestrador — 27,7% do gasto medido — não têm step. Fechar por step exigiria primeiro atribuir o orquestrador, que o transcrito não permite. Fica declarado como impossível, não como pendente.
- **A métrica não separa duas atividades na mesma branch.** O transcrito não diz de qual delas é cada turno. Ela acusa o par e mostra quanto entra duas vezes, em vez de inventar critério.
- **A limpeza do que uma frente de execução deixa** — servidores de pé, linhas no banco. Ela declara; ninguém recolhe.
- **A trilha `curta` nunca foi exercitada de ponta a ponta.** Era o segundo produto da rodada de 03/09/2026, e ela não aconteceu: a análise do card mostrou que ele exigia a trilha `completa`. Continua sendo a trilha de bug, e a que mais gente vai usar primeiro.
- **Quatro skills acima do teto de 12 KB** — medido em 03/09/2026 pelo `audit_package.py`: `development-reviewer` 22, `business-analysis-reviewer` 19, `system-analyst` 17, `developer` 13. O corpo inteiro entra na janela do step toda vez; o que é doutrina pertence a `references/`. Os números anteriores (17, 18, 15, e a contagem de três) estavam desatualizados: a conta certa sai do auditor, não da memória.
- **A mutação continua manual.** É a prova que derrubou onze testes verdes, e nada no fluxo a automatiza.
- **A catraca nunca foi gravada numa branch de verdade.** Ela roda dentro do step agora, mas nunca gravou base num ciclo real de entrega.
- **O login com senha real** continua sem cobertura: o comando de perfil o pula de propósito, e fechá-lo exige credenciais que só o dono do ambiente tem. Ela foi exercitada contra saída real de lint, e não contra um ciclo inteiro de entrega.

## Onde está o quê

`FLOW.md` é o contrato — steps, trilhas, portões, e as regras transversais. As
`references/` são o ofício. As `skills/` são procedimento, e todas abrem
mandando ler o `FLOW.md`. O `test_package.py` prende as regras nos arquivos: se
uma skill parar de mandar ler o fluxo, ele reprova.
