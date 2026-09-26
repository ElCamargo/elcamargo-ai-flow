# A forma de uma SDD pronta para implementação

Comece pelo template do repositório, se houver. Sem template, use este
esqueleto. Inclua a seção quando ela se aplica; **não mantenha cabeçalho vazio**
e não esconda decisão em nota solta.

O critério de pronto é um só: **um desenvolvedor que não participou da análise
consegue implementar sem adivinhar, e um revisor consegue conferir sem
perguntar.**

## Núcleo

1. **Identificação** — código, título, status, análise de origem, SDDs
   relacionadas.
2. **Contexto validado** — o problema, a evidência do comportamento atual, e as
   divergências que você encontrou entre o que o negócio pediu e o que existe.
3. **Objetivo e fronteiras** — o que muda, onde, e quem é dono do
   comportamento.
4. **Decisões de referência** — ADRs, documentos de arquitetura e o impacto de
   cada um sobre esta demanda. Link real, não menção.
5. **Escopo e fora de escopo** — a fatia implementável. Cada item fora de escopo
   com justificativa e, quando couber, para onde ele foi.
6. **Atores e permissões** — quem inicia, vê, altera, aprova. Escopo de
   autorização e visibilidade de interface.
7. **Regras consolidadas** — numeradas, inequívocas, cada uma ligada à origem.
8. **Fluxo e estados** — principal, alternassets, erros. Um diagrama quando o
   texto sozinho não fecha.

## Contrato técnico

Inclua o que a demanda tocar; ignore o resto.

1. **Dados e persistência** — entidades, campos, tipos, constraints, índices,
   estados. Migração, e **o caminho de volta**.
2. **API** — método, rota, autorização, request, response, validações,
   paginação, ordenação, códigos de erro.
3. **Eventos e assincronia** — nome, payload, produtor, consumidor,
   idempotência, retentativa, o que acontece quando falha de vez.
4. **Isolamento entre clientes** — quando o produto serve mais de um cliente ou
   organização: qual é a fonte do escopo, onde ela é validada, e o que acontece
   com um identificador de outro escopo.
5. **Auditoria e observabilidade** — o que fica registrado, com qual ator e
   origem, e **o que não pode entrar em log**.
6. **Interface** — rota, componentes, campos, formato de valor, e os estados
   `carregando`, `vazio`, `erro`, `sem permissão`. O desenho é do step 6; aqui é
   comportamento.
7. **Integrações** — contrato, compatibilidade, invalidação de cache, e de quem
   é a responsabilidade de cada lado.

## Validação e entrega

1. **Critérios de aceite** em Dado/Quando/Então, cobrindo autorização, erro,
   concorrência e efeito assíncrono — não só o caminho feliz.
2. **Matriz de rastreabilidade** — cada requisito de origem, a decisão da SDD e
   o cenário de teste correspondente.
3. **Testes esperados** — unidade, integração, contrato, migração, evento e
   interface, conforme o risco de cada parte.
4. **Sequência de implementação** — fatias verticais e suas dependências, sem
   prescrever código.
5. **Documentação afetada** e os comandos de validação que a implementação
   deverá rodar.
6. **Decisões pendentes** — ver `decisoes-e-traceability.md`.

## Durável, não precisa

Esta especificação vai ficar parada. Entre escrevê-la e implementá-la há três
portões humanos, e ela pode esperar semanas enquanto o código se move embaixo
dela.

Por isso ela nomeia **tipo, assinatura, contrato e comportamento** — e **nunca
caminho de arquivo nem número de linha**. Uma especificação que diz "altere
`orders.service.ts:214`" está errada no dia em que alguém adiciona dez linhas
acima, e ninguém percebe que envelheceu: ela continua parecendo precisa.

Nomeie a coisa, não o lugar dela. `o serviço que resolve o vínculo automático`
sobrevive a refatoração; `linha 214` não.

A regra é **oposta** para achado de revisão: ali `arquivo:linha` é exatamente o
que faz o corretor achar o problema, e o achado é consumido na mesma hora. Vida
curta pede endereço; vida longa pede nome.

## Precisão mínima

Use identificador técnico plausível **apenas depois de confirmar o padrão no
repositório**. Inventar um nome de tabela, rota ou evento que não segue a
convenção local produz uma SDD que parece pronta e não é.

Nunca deixe passar uma frase como "criar endpoint", "sincronizar
automaticamente", "validar permissões" ou "registrar auditoria" sem **sujeito,
método, objeto, estado e resultado observável**. Essas frases são o defeito mais
comum de uma especificação ruim: parecem decisão e são adiamento.

Se a demanda altera comportamento já especificado, diga qual SDD ou contrato é
substituído, qual a compatibilidade esperada e qual a estratégia de migração. Se
não altera, cite a dependência sem duplicar a especificação dela.
