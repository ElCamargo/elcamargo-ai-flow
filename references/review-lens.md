# Banco de perguntas

Usado pelos steps 2, 3 e 4, e pelos revisores do 9. Não é checklist para
percorrer inteiro: **aplique a pergunta que a demanda torna relevante** e ignore
o resto. Perguntar sobre mensageria numa demanda que não tem evento é ruído.

## Domínio e uso

- Quem inicia, vê, altera, aprova, consome e dá suporte a este fluxo?
- Qual resultado observável muda? O que explicitamente **não** muda?
- Quais são os estados, as transições e as pré-condições de cada uma?
- O que acontece com o que está **em curso** quando algo é cancelado,
  desativado, expira, ou o item pai muda?
- Quais campos são obrigatórios, imutáveis, sensíveis, monetários, ou dependem
  de outro campo?
- Qual ação precisa de confirmação, de aviso de impacto, ou de bloqueio?

## Cardinalidade

A pergunta que mais escapou, em todo projeto onde este fluxo rodou:

- Toda vez que o texto disser "o" ou "a" no singular sobre um vínculo,
  **confirme se é mesmo um**.
- O usuário pode ter dois disso ao mesmo tempo? E ao longo do tempo?
- Se pode ter dois, o que acontece com o primeiro quando chega o segundo?
- A restrição é regra de negócio, ou é limitação que alguém assumiu?

Uma cardinalidade errada não aparece na revisão de código: o código está certo
para o modelo errado.

## Escopo e isolamento

- A ação é global, ou pertence a um cliente/organização? Há mistura?
- Qual é a fonte do escopo, e ela é confiável? Vem do token, ou do request?
- O acesso direto por identificador de outro escopo é rejeitado?
- Comportamento tratado como global precisa ser individual por subdomínio, ou o
  contrário?

## Dado

- Qual entidade é **dona** do dado, e qual é só projeção ou cópia?
- O que garante integridade: constraint, unicidade, índice, transação?
- O que acontece em criação parcial, reexecução, rollback, arquivamento?
- Há migração ou preenchimento retroativo? Quantos registros existem hoje?
- O que é auditado, e o que **não pode** entrar em log?

## Se a demanda tiver assincronia, integração ou volume

Só então, e só o que couber:

- **Assincronia** — quem produz, quem consome, e o consumidor aguenta receber
  duas vezes? O que acontece quando a dependência externa está fora?
- **Integração** — contrato, compatibilidade, e quem invalida o cache.
- **Volume** — quantos registros, quantos simultâneos, com que frequência? Há
  limite de tempo declarado, e como será medido? O que degrada primeiro quando
  o volume dobra?

Numa demanda de listagem e permissão isto é peso morto. Pule sem culpa.

## Se a demanda tiver herança, cópia ou propagação

Também só então. O sinal de entrada é o texto dizer que algo é **copiado de uma
origem**, **personalizado no destino**, ou **sincronizado** entre os dois.

"Sincronização automática" é a frase mais cara desta lista: ela parece decisão e
não responde nenhuma das perguntas abaixo. Cada linha da tabela é uma decisão
que alguém vai ter que tomar — na especificação agora, ou na implementação
depois, por quem tiver menos contexto.

| Sinal na análise | Decisão que ela exige |
| --- | --- |
| "Copia da origem" **e** "recebe alterações futuras" | O destino recebe cópia, projeção versionada, ou herança viva? Quem é a fonte de verdade? |
| Personalização por escopo, categoria ou item | Qual é a unidade de personalização, quais campos ficam liberados, e o que isso faz com as operações seguintes? |
| "Voltar a usar o padrão" | Tem prévia? Confirmação? O que é sobrescrito, o que é preservado, e o que fica em auditoria? |
| Dado novo aparece na origem | Quem é elegível, em que ordem propaga, e o que acontece com um destino já personalizado? |
| Alterar ou remover a origem, ou o vínculo | Atualização, inativação, exclusão e desvínculo são quatro comportamentos diferentes. Qual deles é, e o que cada um preserva? |
| Uma origem, muitos destinos | Exige `snapshot`/versão, operação assíncrona, consumidor idempotente, retentativa, destino de falha — e resultado **por destino**, não um "concluído" só. |
| Sobrescrita de só uma parte do dado | Quais campos podem divergir da origem e quais continuam mandados por ela? |
| Tela que lista os destinos vinculados | De onde vem esse indicador, quando ele atualiza depois da propagação, e o que cada status ali significa? |
| Outra superfície consome o dado | Qual contrato, qual autorização, qual cache — e o que ela vê quando a configuração não existe. |

Nenhuma linha impõe um modelo. Elas só impedem que a escolha entre os modelos
aconteça sem ninguém perceber que houve escolha.

## A pergunta final

Depois de todas: **o que nesta análise eu aceitei sem verificar?**

Costuma ser aí que está o defeito — não no que foi analisado e concluído errado,
mas no que pareceu óbvio e não foi olhado.
