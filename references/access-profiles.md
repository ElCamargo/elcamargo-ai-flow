# Perfis de acesso: quem pode, quem não pode, e quem provou

A frente de execução já mandava *"entrar com ator sem a permissão"*. Numa
atividade real a resposta foi:

> *"Não há ator só-leitura no banco local, e criar um exigiria criar conta e
> senha."*

A dimensão foi declarada não coberta, e a decisão de merge foi tomada com a
autorização provada **na tela** e não no `403`. **Obrigação escrita sem mecanismo
por trás produz isso toda vez.** O que faltava não era disciplina: era o projeto
declarar como se assume um perfil.

## Duas camadas, e elas respondem perguntas diferentes

Isso decide o custo, e é a parte que se erra pensando em "testar tudo com todos
os perfis".

| | Pergunta | Custo |
| --- | --- | --- |
| **API** | O servidor **recusa**? | dezenas de células em segundos |
| **Navegador** | A interface **não oferece**, e o que ela diz quando recusa? | minutos por perfil |

**Esconder um botão não é recusar uma requisição.** São dois defeitos diferentes,
e nenhum cobre o outro. Numa entrega real o defeito era o primeiro tipo: um
registro ativo abria **editável** para quem só tinha a chave de leitura, com o
servidor recusando corretamente por trás.

Daí a divisão: **a matriz mora na camada barata** — perfis × rotas contra as
guardas de produção, em teste unitário. O navegador cobre só o que ela não
alcança, e em dois perfis, não em sete.

## A regra que faz isto valer alguma coisa

> **Todo "não pode" vem acompanhado de um "pode", com o mesmo ator na mesma
> sessão.**

Um teste negativo passa trivialmente quando a conta está quebrada. *"Não
consegui editar"* é verde para **"a permissão foi negada"** e também para: o
login falhou, a conta expirou, a role foi renomeada, o seed não rodou, o token
venceu.

Sem o par, a matriz de perfis é uma máquina de verde falso — e **pior que não
ter**, porque parece cobertura. O perfil só-leitura precisa provar que *consegue
listar* antes de valer como prova de que *não consegue editar*.

## Credenciais nunca entram no fluxo

O projeto declara **como assumir um perfil**, não as senhas:

```toml
[perfis]
comando = "npm run perfil --silent --"   # recebe o nome, imprime o token
injecao = "localStorage:app.session"
ambiente = "localhost"

[perfis.atores.somente-leitura]
descricao = "lê e não escreve"
chaves = ["platform_faq.read"]
```

O comando é do projeto e as credenciais ficam no cofre dele. Nenhuma senha entra
no config versionado, no pacote, ou no contexto de quem executa o fluxo. Sem
`[perfis]` declarado, a passada é **dimensão não coberta declarada** — nomeada no
relatório, não silenciosa.

**`chaves` é conferido antes de confiar no resultado.** É a mesma regra do par,
aplicada ao ator: se ele não tem o que diz ter, toda negação dele é verde por
motivo errado.

## Quando é obrigação, e quando é recomendação

```bash
python3 $PACOTE/tools/profiles/profiles.py superficie --base <ref> --raiz .
```

**A entrega toca superfície de autorização POR PERFIL?** Chave exigida por rota,
pilha de guardas, guarda nova, leitura de permissão, visibilidade condicionada a
chave. Se toca, a passada por perfis deixa de ser recomendação e reprova quando
falta.

**A palavra "por perfil" não é enfeite.** Os padrões são todos de autorização por
perfil de **usuário**. Autorização por outro eixo — allowlist de chamador de
serviço, credencial entre sistemas, regra de rede, escopo de token — **não passa
por eles**, e a resposta verde não fala sobre isso. Em 22/09/2026 uma entrega
acrescentou uma linha a uma allowlist de chamador de serviço, alargando o que
outro repositório alcança por credencial, e a conferência fechou como `ok` — a
ferramenta estava certa em não medir aquele eixo, e a frase é que afirmava mais
do que ela sabia. Achado pela frente de execução, lendo a tabela da atividade;
nenhuma das quatro frentes de leitura viu.

**Se o seu projeto tem um eixo assim, declare-o** em `[[perfis.padroes]]` do
config, com `arquivo` (casa o caminho), `regex` (casa a linha acrescentada) e
`rotulo`. Eles **somam** aos de pilha, e entram na frase da resposta. O comando
acha o `.agents/config.toml` da raiz sozinho — exigir a bandeira seria o mesmo
defeito noutro lugar.

Duas coisas **não** são superfície, e as duas saíram de calibrar contra um diff
real:

- **Documento.** Uma especificação que *descreve* a regra casa com todos os
  padrões e não enforça nada. Metade dos arquivos acusados na primeira passada
  eram `.md`.
- **Teste.** Um spec que fala de permissão é a rede em volta da superfície. Contá-lo
  faria a obrigação disparar justamente para quem acabou de cumpri-la.

## Homologação fica de fora por padrão

Perfil de escrita cria linha que outras pessoas veem, e homologação é dado
compartilhado. O padrão é `ambiente = "localhost"`; rodar em homologação segue a
regra que já existe — **ambiente compartilhado exige autorização explícita no
portão humano**.

Perfil só de leitura em homologação é a exceção defensável, e continua sendo
decisão de quem responde pelo ambiente.

## O que a frente escreve, e como se confere

Uma tabela, e é ela que o comando lê:

```
| Perfil | Ação | Esperado | Observado |
| somente-leitura | listar FAQ | permitido | 200, seis categorias na tela |
| somente-leitura | editar categoria | negado | botão ausente; PATCH direto → 403 |
```

```bash
python3 $PACOTE/tools/profiles/profiles.py conferir <relatorio.md> --config <config.toml>
```

Ela reprova perfil que só provou o que não pode, linha sem `Observado`, linha
cujo observado **confessa que não mediu**, e `Esperado` escrito por negação —
*"não permitido"* diz o que não se esperava e some com o que se esperava. E
nomeia, sem reprovar, o perfil declarado no config que a passada nunca tocou.

**Note a segunda coluna do exemplo negado.** Duas medições na mesma linha: o
botão ausente (a interface não oferece) e o `PATCH` direto (o servidor recusa).
São as duas camadas, e uma linha honesta traz as duas quando alcança as duas.

## O que isto não prova

**Que o esperado estava certo.** Se o perfil deveria poder e você escreveu
`negado`, a conferência concorda com você e erra junto. Ela verifica que houve
medição e que a negação tem contraprova — não que a regra de negócio é a que
está no `Esperado`.

E não prova que um ator real, autenticado ponta a ponta, receba o mesmo
resultado, quando o token é emitido por atalho de desenvolvimento. Fica provado
tudo o que vem **depois** da identidade, que é onde os defeitos moram.
