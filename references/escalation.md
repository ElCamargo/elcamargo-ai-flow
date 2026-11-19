# Quando a fase B chama você

A **fase B** vai da entrada no step 8 até o portão 10: o desenvolvedor, a
revisão da entrega e o laço entre os dois. Ela roda sem a pessoa na conversa. A
pessoa decidiu o que importa na fase A (portões 5 e 7) e volta no portão 10.

Rodar sem a pessoa tem dois jeitos de dar errado, e esta página existe contra os
dois:

- **Perguntar demais.** "Na dúvida, pergunte" transforma a fase B em fase A com
  mais espera. Cada pergunta que o step podia responder sozinho custa o tempo de
  alguém e não muda nada.
- **Decidir calado o que não era do step.** A pergunta de produto respondida por
  suposição só aparece no portão 10, depois de implementada e revisada. Aí ela
  custa a volta inteira.

Por isso a lista de motivos é **fechada**. Fora dela, o step decide e registra.

## O teste

> **A resposta muda o que o sistema faz para quem usa, ou o erro não se desfaz
> com um commit? Escala. Muda só *como* ele faz? Decide e registra.**

Na dúvida entre `produto` e decidir: **quem aceita no portão 10, usando o
sistema, notaria a diferença?** Se notaria, é dele.

## Os sete motivos

| Motivo | Quando | O que **não** é | Exemplo |
| --- | --- | --- | --- |
| `produto` | A resposta muda o comportamento para quem usa, e nenhum artefato (card, SDD, protótipo, ADR) a dá | Nome, estrutura interna, escolha entre bibliotecas que o projeto já usa | "O desconto vale para pedido já faturado?" |
| `contradicao` | Dois artefatos aprovados dizem coisas diferentes e a escolha muda o comportamento | Divergência que o portão já decidiu por escrito: vale a decisão registrada | SDD pede paginação de 20; o protótipo aprovado mostra rolagem infinita |
| `impossivel` | O especificado não cabe no sistema como ele é: a API externa não oferece, o dado não existe, ou cumprir exige mudar outra coisa aprovada | Difícil, demorado, ou mais trabalho que o previsto | A SDD filtra por data de entrega, e o serviço de pedidos não expõe esse campo |
| `irreversivel` | O passo não se desfaz com um commit: migração destrutiva, dado de produção, mensagem a terceiros, contrato público já consumido | Migração aditiva, ou qualquer coisa que só vive no ambiente local | Remover uma coluna que outro serviço ainda lê |
| `ambiente` | Falta o que só a pessoa dá: credencial, acesso, serviço fora do ar, dependência que não instala | Teste falhando por defeito do próprio código | O banco de homologação recusa a conexão |
| `laco` | A terceira volta 9→8 com `bloqueia` ou `alta` ainda aberto | A segunda volta: ela é do laço, não da pessoa | O mesmo achado de concorrência voltou duas vezes |
| `risco` | A entrega toca superfície que o risco declarado não previa: autenticação, autorização, dado pessoal, dinheiro | Atividade já aberta como `alto`, com os gates que isso pede | Um card `padrao` que, para funcionar, muda a checagem de permissão |

`produto` e `contradicao` apontam **defeito da fase A**: a SDD devia ter
respondido. Quando aparecem, o certo é escalar, e o número delas é o que mede a
fase A (ver *O que se mede*).

## O que não escala: decide e registra

Tudo que muda *como* o sistema faz, e não *o que* ele faz:

- nomes, estrutura de classe, divisão em arquivos;
- qual de duas formas equivalentes de implementar;
- biblioteca, quando o projeto já usa uma para aquilo;
- como testar, que caso extra cobrir, em que ordem implementar;
- texto de interface que nenhum artefato deu: siga o padrão do projeto, e ele
  vira card no portão 10.

Decidir não é decidir calado. Toda decisão desta lista que alguém poderia
questionar entra na nota de implementação, na seção `## Decisões da fase B`:

```markdown
## Decisões da fase B

| Decisão | Alternativa descartada | Por quê | Como desfazer |
| --- | --- | --- | --- |
| Cache do cálculo por pedido, 5 min | Sem cache | A SDD pede < 200 ms e o cálculo leva 800 | Remover o decorator em `PrecoService` (1 commit) |
```

**Como desfazer** é a coluna que importa. "1 commit" diz que a decisão é
técnica. Quando o desfazer custa mais que isso (migração, contrato, dado), a
decisão provavelmente era `irreversivel` e devia ter escalado.

Quem confere o registro:

- **No step 9**, as frentes de SDD implementada e de negócio implementado leem a
  tabela. Decisão de `produto` registrada como técnica é achado `alta`, na
  classe *"decisão de produto tomada sem a pessoa"*. Quem consolida abre a
  escalada `produto` com ela, em vez de devolver ao step 8: corrigir sem a
  resposta seria adivinhar de novo.
- **No portão 10**, decisão cujo desfazer custa mais que um commit vira card.

## Como se escala

1. **Siga com o que não depende da resposta, e commite.** A escalada para o
   step, não o trabalho.
2. **Junte as perguntas do mesmo step numa escalada só**, até quatro, cada uma
   no formato de `pending-decisions.md`: pergunta fechada, por que existe,
   opções reais conferidas no código, consequência de cada uma, recomendação.
3. **Registre:**

   ```bash
   python3 <pacote>/tools/flow-state/flow_state.py escalar <id> --motivo <motivo> --pergunta '<resumo de uma linha>'
   ```

   O estado passa a mostrar `AGUARDANDO VOCÊ`, o `listar` marca a atividade, e o
   `avancar` recusa, mesmo com `--forcar`: mandar à revisão o que depende de
   uma decisão que não veio é pagar a revisão duas vezes.
4. **Devolva** `parado: escalada <motivo>`, com as perguntas inteiras no
   retorno. Uma escalada aberta por vez; a segunda é recusada.
5. **A porta pergunta na hora**, em cards, como num portão. As outras atividades
   seguem. Com a resposta:

   ```bash
   python3 <pacote>/tools/flow-state/flow_state.py escalar <id> --resposta '<o que foi decidido>'
   ```

   E dispara de novo o **mesmo** step, com a resposta no pedido.
6. **Decisão que vale além deste card vira ADR** em `docs.adrs`. É uma escalada
   a menos em todo card depois dele, e é a ponte com a trilha de definição
   (`docs/ideias.md`).

No step 9, `laco` tem três respostas possíveis, e a pergunta as oferece:
aceitar com o achado declarado no portão 10, mais uma volta com a direção que a
pessoa der, ou devolver ao step 3, porque a spec é que não fecha.

## O que se mede

O `flow_state.py tempo <id>` conta as escaladas por motivo e a espera de cada
uma. A espera fica **dentro** do tempo de IA do step que parou, porque o step
continua aberto enquanto espera; leia o tempo do step 8 sabendo disso.

| Leitura | O que diz |
| --- | --- |
| Muita `produto` ou `contradicao` | A fase A deixou pergunta sem resposta. O defeito é da SDD, não do step 8 |
| Muita `ambiente` | O projeto não está pronto para rodar sem alguém. O defeito é de configuração |
| `laco` frequente | O par 8↔9 não converge. Olhe a classe dos achados que voltam |
| Zero escaladas, e achado *"decisão de produto tomada sem a pessoa"* no step 9 | A escalada que faltou. É o pior dos números, porque parece autonomia |

## O que isto não cobre

- **Orçamento por card.** Nada aqui para a fase B por custo ou tempo gastos.
  Uma atividade pode rodar voltas caras sem chegar a `laco`.
- **Fase A.** Lá a pessoa está na conversa, e vale a regra de trazer a decisão
  na hora (`fluxo/steps.md`). A lista fechada é da fase B.
- **Prova de que a decisão era técnica.** O registro é declarado por quem
  decidiu. Quem confere é o step 9, lendo a tabela, e ele pode não ver.
