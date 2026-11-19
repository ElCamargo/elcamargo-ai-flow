# Fluxo · O que é da máquina

Parte do contrato do fluxo, fora do núcleo. O núcleo é o `FLOW.md`, que
toda skill lê; este arquivo se lê quando o step precisa do que está aqui.

## O que é da máquina

O que o fluxo fazia com modelo e passou a fazer com comando. Não é
economia por economia: a máquina conta certo, e não erra sem perceber que errou.

| Ferramenta | O que resolve | Quem usa |
| --- | --- | --- |
| `tools/matrix/matrix.py extrair` | Enumera seções, acha identificadores, conta por seção. Lê `.md`, `.docx` com tabelas, e `.pdf` | 2 |
| `tools/matrix/matrix.py conferir` | Reprova matriz incompleta, item sem estado, item sem destino, seção que anuncia um tipo e entrega zero | 2, 3, 4 |
| `tools/briefing/briefing.py` | Levanta uma vez o que as seis frentes redescobriam seis vezes | 9 |
| `tools/tree-guard/tree_guard.py` | Marca a árvore antes do disparo das frentes e confere depois, por conteúdo | 9 |
| `tools/prior-work/prior_work.py` | Em qual dos três casos da trilha `revisao` a entrega está: o dev usou o fluxo, especificou fora dele, ou não documentou nada | 1, na trilha `revisao` |
| `tools/process-guard/process_guard.py` | Marca quem já escutava e quais contêineres estavam de pé antes do disparo, e depois confere as duas direções — o que caiu (`conferir`) e o que a atividade deixou de pé (`sobra`) —, amostrando o pico de memória durante as levas | 9, `runtime-reviewer`, gancho de abertura de sessão |
| `tools/outcome/outcome.py` | Conta o que aconteceu com cada achado. Reprova destino ausente, negado, ambíguo ou sem prova | 2, 4, 9 |
| `tools/ratchet/ratchet.py` | Separa o que a entrega quebrou do que já falhava. Só aperta: base consertada encolhe e não volta | 8, 9 |
| `flow_state.py gates` | Roda os portões de `[gates]`, um por vez, e grava o código de saída de cada um como `gate:<nome>`. O `avancar` 8→9 lê essa tabela | 8, 9 |
| `tools/anchor/anchor.py --contexto` | Gancho de `PreToolUse` de Bash: grava sessão + subagente de quem vai rodar o comando. O `avancar` 8→9 guarda o do 8, e o 9→10 recusa o mesmo | 8, 9 |
| `flow_state.py status` no step 9 | Avisa quando o contexto é o que fez o 8, e diz o `model` de cada frente com `[revisao.modelo]` — só vale com veredito `adota` da perna sombra | 9 |
| `flow_state.py desde-aprovacao` | O que mudou nos artefatos e no código desde a saída do último portão, que o `avancar` e o `concluir` gravam sozinhos | 4, 6, 9 — antes das perguntas do portão |
| `tools/matrix/matrix.py casos` | O contrato de casos: um por `CT` da SDD, a fase vermelha antes da implementação, o `passa` escrito pela saída da suíte. `conferir-testes` cruza tudo com a SDD | 8, 9 |
| `tools/gate-guard/gate_guard.py` | Gancho de fim de turno: lembra, uma vez, a janela do step 8 que encerra com portão sem `ok` | 8 |
| `tools/honesty/honesty.py` | `.only` commitado, pulo estático, asserção trivial, teste que simula o que testa, e quantos casos não rodaram | 8, 9 |
| `tools/profiles/profiles.py` | O diff toca autorização? E a passada por perfis prova o que diz, ou só o que não pode? | 9 |
| `tools/doctor/doctor.py` | O config deste projeto bate com este projeto? Roda ao instalar, antes da primeira atividade | instalação |
| `tools/briefing/domain.py` | Mapeia o terreno do domínio: entidades, migrations, rotas, métodos, specs, ADRs, códigos de erro — e a base da branch | 3 |
| `tools/already-exists/already_exists.py` | Isto já existe? E se existe, o que a demanda **acrescenta**? Acha a spec dona e mede o delta | 1 |
| `tools/figma/figma.py` | Lê o Figma por API REST, em camadas — `GET` não consegue escrever | 6 |
| `[ambiente]` do config | Como subir a aplicação: infra, apps, url, espera. A frente de execução usa | 9 |

**A matriz.** Extrair 167 itens à mão custou quinze minutos e uma contagem
errada que ninguém notou — o total dizia 155. O comando faz em segundos e
denuncia sozinho quatro coisas que a leitura não pega: seção do sumário que saiu
vazia (costuma ser imagem), seção que anuncia um tipo e entrega zero,
identificador citado e nunca definido, lacuna de numeração.

O que ele **não** faz é o que vale: decidir o estado de cada item, dizer onde
ele foi parar, achar contradição e cardinalidade. Isso continua sendo leitura.

**O dossiê.** As cinco frentes do step 9 gastaram 310 mil tokens em 36 linhas de
diff, e a maior parte foi redescoberta idêntica. O dossiê levanta os fatos uma
vez — diff (inclusive não commitado), arquivos com os não rastreados marcados,
símbolos de API e quem os referencia, portões, documentos, stack.

**O mapa do terreno.** O step 3 gastou 284 mil tokens e 91 chamadas para
especificar 18 requisitos, e a maior parte foi descobrir onde as coisas moram.
O mapa varre uma vez e devolve por papel: entidades com colunas e decorators,
migrations com só o SQL do domínio, rotas montadas, métodos públicos, specs
anteriores, ADRs, testes, traduções, códigos de erro em uso, e a memória de
rejeição que cita o assunto.

**E declara a base.** Na mesma execução a análise pressupunha um módulo que
existia só numa branch 33 commits à frente e não mesclada — especificar contra
a branch padrão teria quebrado no primeiro import.

**Ele não carrega nenhum achado, de propósito.** As frentes valem porque julgam
de forma independente; um dossiê que apontasse faria as seis olharem para o
mesmo lugar. Fato entra, julgamento é de cada uma.

**O destino.** Uma revisão real produziu vinte e um achados, e ninguém sabia
quantos tinham virado mudança. A informação existia — espalhada em três tabelas
com três vocabulários, e nenhuma somável com as outras. O comando lê a coluna
**Destino** e conta: corrigidos, descartados, aceitos, abertos.

Ele acusa quatro coisas que a leitura não pega. Achado sem destino. Destino
escrito por negação — *"não fechado"* diz o que não aconteceu e some com o que
aconteceu, e a primeira versão da própria ferramenta leu cinco linhas assim como
fechadas, inflando a taxa para o lado que agrada. `corrigido` sem nada que o
sustente. E bloqueio que ficou aberto, ou que foi aceito sem portão humano.

O número não é meta — perseguir taxa de conversão produz achado fácil inventado
e achado difícil não escrito. Ele existe para a pergunta ser feita, e hoje ela
não é feita nenhuma vez. Ver `references/outcome.md`.

**O doutor.** O `install.sh` copia o `config.example.toml` — que carrega os
valores do projeto onde o pacote nasceu — e avisa para ajustar. Quem não ajusta
leva tudo junto, e nada falha na hora: uma skill de Git declarada e inexistente
faz o step 1 delegar para o nada; um gate apontando para script que não existe
só aparece quando o step 8 tenta rodar.

Ele confere o que está declarado contra o repositório: a skill existe, os
caminhos existem, os gates são scripts que existem, a catraca é coerente com os
gates, o comando de perfil roda, e o backend de anexo tem o que precisa. **Rode
ao instalar num projeto novo, antes da primeira atividade.**

O que ele **não** prova: que os valores estão certos. Ele confere que o que está
declarado existe — não que é o que você queria declarar.

**Os perfis de acesso.** *"Entrar com ator sem a permissão"* é a instrução mais
antiga da frente de execução e a que mais falhou — porque não tinha mecanismo.
Numa atividade real a resposta foi *"não há ator só-leitura no banco, e criar um
exigiria conta e senha"*, e a decisão de merge saiu com a autorização provada na
tela e não no `403`.

O projeto declara em `[perfis]` um comando que recebe o nome do ator e devolve um
token. **Nenhuma senha entra no fluxo.** Quando o diff toca superfície de
autorização, a passada por perfis deixa de ser recomendação e reprova quando
falta.

**E há uma regra que decide se ela vale alguma coisa: todo "não pode" vem com um
"pode", do mesmo ator na mesma sessão.** Um teste negativo passa trivialmente
quando a conta está quebrada — *"não consegui editar"* é verde tanto para a
permissão negada quanto para o login que falhou, a role renomeada, o seed que não
rodou. Sem o par, a matriz de perfis é verde falso com cara de cobertura.

Duas camadas, e elas respondem perguntas diferentes: **esconder um botão não é
recusar uma requisição.** A matriz mora na camada barata — perfis × rotas contra
as guardas de produção, dezenas de células em segundos. O navegador cobre só o
que ela não alcança, em dois perfis e não em sete.

Homologação fica fora por padrão: perfil de escrita cria linha que outras pessoas
veem. Ver `references/access-profiles.md`.

**A honestidade do teste.** Gate verde não é requisito provado. Numa entrega
real onze testes verdes provavam nada — achados por mutação, não por leitura —, e
o portão visual da mesma entrega fechou anunciando `145 passaram, 0 falharam`
com **152 ignorados na mesma linha**. As duas frases eram verdadeiras, e a
decisão foi tomada em cima da primeira.

A varredura acha `.only` commitado — que faz o resto do arquivo não rodar —,
pulo estático, asserção trivialmente verdadeira, caso sem asserção, caso que só
prova a fiação, e o arquivo que simula o próprio módulo que testa. A contagem diz
quantos não rodaram.

**Tudo isso é procedência `estrutural` e não reprova sozinho** — a exceção é
`.only`, que não tem leitura que o salve. O teste de verdade continua sendo a
mutação: quebre a implementação e veja se algum teste reprova.

E há uma lição sobre construir lente estrutural, que custou três rodadas: a
lente acusou 3, depois 35, depois 5 achados contra um repositório real, **e
todos eram legítimos**. Uma regra plausível encontra o padrão certo e a intenção
errada. Calibrar contra código real não é polimento — é a diferença entre uma
ferramenta e um gerador de ruído. Ver `references/test-honesty.md`.

**A catraca.** Um portão vermelho não diz se a entrega quebrou algo ou se já
estava assim, e quem recebe o vermelho tem três saídas ruins: caçar defeito que
não é dele, ignorar o portão, ou marcar "pré-existente" de memória — que foi o
que a POC fez, três vezes.

Ela guarda o conjunto de falhas conhecidas na base e classifica: **novo**
reprova, **conhecido** não, **consertado** faz a base encolher. O terceiro é o
que a faz catraca e não lista — o que foi consertado não volta em silêncio.

**A identidade de uma falha não pode conter o que uma edição legítima muda.** Um
aviso pré-existente foi registrado como `app-shell.tsx:176`; a entrega inseriu
código acima, e hoje o mesmo aviso mora na **185**. Guardar o número da linha
faria a catraca devolver a entrega por um aviso que ninguém tocou. A identidade é
`arquivo :: regra`, e para teste `arquivo > suíte > nome`.

E o gesto que a destrói tem nome: **regravar a base por cima do vermelho de
hoje**, que transforma regressão em passivo conhecido com uma linha de comando.
`gravar` recusa quando já há base; `apertar` só encolhe; admitir falha nova exige
`--admitir '<por quê>'`, e o motivo é impresso em toda conferência seguinte. Ver
`references/ratchet.md`.

**O delta.** A pergunta mais cara do fluxo é *"isto já existe?"*, e a segunda
mais cara é *"então o que esta demanda acrescenta?"*. Respondidas por leitura,
custam o módulo inteiro; respondidas por varredura, custam segundos.

O comando acha a especificação que já é **dona** do comportamento e mede quanto
da demanda ela já cobre. O que sobra é o candidato a delta — e é isso que muda o
fluxo:

**Complemento não reabre o módulo.** O step 2 revisa o delta, o step 3
**atualiza a SDD existente** em vez de escrever outra, o step 4 confere o delta.
Sem essa declaração cada step decide o escopo sozinho, e decide largo — porque
largo parece seguro. Largo aqui é só mais caro, mais lento, e produz
especificação duplicada que alguém vai ter que reconciliar.

### E o que é opcional

Um grafo de conhecimento do repositório responde barato o que o mapa não
alcança: travessia transitiva, caminho entre conceitos, arquivos que tratam do
assunto com outro vocabulário. **Nunca é dependência** — o pacote precisa
funcionar com zero instalação, e é isso que permite zipá-lo e mandá-lo.

Detecte com `python3 tools/flow-state/capabilities.py grafo`, declare em
`[capacidades] grafo`, e leia `references/knowledge-graph.md`. As três
regras, em uma linha cada: **grafo é pista, não evidência**; **aresta inferida
não é aresta observada**; **grafo velho é pior que grafo nenhum.**

## A conferência mecânica deixa rastro, e o `concluir` lê o rastro

Uma obrigação escrita em prosa não acontece. *"Entrar com ator sem a permissão"*
viveu meses na frente de execução e **nunca aconteceu uma vez** — ninguém
registrava, e portanto ninguém sabia.

O arquivo da atividade ganhou uma terceira tabela, **Conferências**, com quatro
veredictos:

| | |
| --- | --- |
| `exigida` | A ferramenta descobriu a obrigação. **Segura o `concluir`** |
| `ok` | A conferência rodou e passou |
| `falhou` | Rodou e reprovou. **Segura o `concluir`** |
| `nao-coberta` | Não deu para cobrir. **Passa, e fica visível** |

**Quem descobre a obrigação é quem a registra.** `profiles.py superficie
--registrar <id>` grava `exigida` sozinho quando o diff toca autorização — um
step que rodou a detecção não consegue mais "esquecer" de exercitar, porque a
exigência já está no arquivo antes de ele decidir qualquer coisa.

E o quarto veredicto é o que impede a regra de virar bloqueio burro: o fluxo
inteiro aceita dimensão não coberta **desde que declarada**. O que ele não aceita
é que ela suma.

### O step 8 não passa para o 9 com portão vermelho

A mesma tabela fecha o step 8. `flow_state gates <id>` roda o que `[gates]`
declara e grava `gate:<nome>`; o `avancar` do 8 para o 9 **recusa, mesmo com
`--forcar`**, enquanto algum portão declarado não tiver `ok` ou `nao-coberta`
gravado **depois da última entrada no 8**, ou enquanto a última conferência
`casos` estiver `exigida` ou `falhou`. A fatia por data é o que faz a volta de
correção do 9 rodar os portões de novo: o verde de antes da correção não serve.

Vermelho que a catraca reconhece inteiro como da base vira `ok` com o motivo no
detalhe, desde que ela tenha nomeado ao menos uma falha e nenhum elo de uma
cadeia `&&` tenha ficado sem rodar (ver `references/ratchet.md`). Para ver os
comandos sem rodar, `gates <id> --listar`. Portão que não se aplica se declara
`nao-coberta` com o porquê. O
`resumo.json` em `atividades/<id>-gates/` guarda a impressão da árvore; o
`gates <id> --conferir` diz ao step 9 se o resultado ainda vale, e a frente de
qualidade lê em vez de rodar de novo. Ver `references/case-contract.md` para o
contrato de casos.

Dois ganchos lembram o que o comando já trava: o de fim de turno avisa, uma vez
por conjunto de faltas, a janela do 8 que encerra com portão sem `ok`; o de
PreToolUse recusa editar o `-casos.json` à mão.

**O que isto NÃO prova:** que os testes provam o requisito. Prova que o comando
declarado devolveu aquele código naquela árvore.
