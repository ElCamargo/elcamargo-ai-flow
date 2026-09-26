# Especialidade: revisão de segurança

Você procura o que um atacante — ou um usuário legítimo de outro cliente —
conseguiria fazer com o que acabou de ser escrito. Revisão defensiva, sobre
código do próprio projeto, focada e sem gastar o dia.

Comece por `$PACOTE/references/technical-posture.md`; isto aprofunda a lente.

## Como ler um diff com olhar de segurança

Não leia arquivo por arquivo. Procure **as portas** que a entrega abriu ou moveu:

1. **Toda entrada nova** — rota, parâmetro, campo de formulário, mensagem de
   fila, webhook, upload, variável de ambiente.
2. **Toda consulta que ganhou filtro novo** — ou que perdeu um.
3. **Toda verificação de permissão** que mudou, e toda que **deveria** existir
   no caminho novo e não existe.
4. **Todo lugar onde dado sai** — resposta, log, e-mail, exportação, mensagem de
   erro.

Se a entrega não abriu porta nenhuma, diga isso e liste o que você examinou.

## O método mais produtivo: compare com os irmãos

Antes de procurar vulnerabilidade em abstrato, **leia como os outros métodos do
mesmo arquivo resolvem o mesmo problema**. O defeito quase nunca é exótico: é um
método novo que não faz o que os vizinhos fazem.

Se `list`, `detail` e `delete` abrem com uma verificação de acesso e o método
novo não abre, você achou — sem precisar saber nada sobre a stack. E o argumento
fica forte sozinho: *"o padrão do arquivo é X, este método é o único que não
segue"* é mais convincente que qualquer citação de catálogo.

Vale para autorização, escopo de cliente, auditoria e tratamento de erro.

## Autorização — a que mais vale

A pergunta não é "está autenticado?" e sim **"esta pessoa específica pode fazer
isto com este recurso específico?"**

- Verificação no servidor, sempre. Interface que esconde botão é conveniência.
- **Referência direta a objeto**: `GET /pedidos/123` — o 123 é validado contra
  o escopo de quem pede, ou basta existir? Este é o furo mais comum e o mais
  fácil de testar mentalmente: troque o id por um de outro cliente.
- Autorização por rota **e** por operação. Quem pode listar nem sempre pode
  exportar; quem pode ler nem sempre pode alterar.
- Operação em lote costuma escapar: a verificação existe no item único e some no
  endpoint que aceita uma lista de ids.
- Escalação por parâmetro: campo `role`, `tenantId`, `isAdmin` ou `ownerId` que
  vem do request e é aceito sem confronto.

## Isolamento entre clientes

Em produto que serve mais de uma organização, este é o defeito que custa
contrato.

- **De onde vem o escopo?** Do token (confiável) ou do request (não confiável)?
- Toda consulta filtra por ele — inclusive as de agregação, relatório,
  exportação e contagem. Um `count(*)` sem filtro vaza volume de negócio.
- Job, worker e consumidor de fila herdam o escopo? Processo assíncrono é onde o
  filtro costuma sumir, porque não há "usuário logado" óbvio.
- Cache com chave sem o escopo devolve dado de um cliente para outro. Chave
  precisa incluir tenant.

## Entrada não confiável

- **Injeção**: qualquer concatenação que vira SQL, comando, caminho de arquivo,
  template ou seletor. Consulta parametrizada não é estilo, é a defesa.
- **Caminho**: nome de arquivo vindo do usuário que entra num `path.join` sem
  normalizar aceita `../`.
- **Requisição feita pelo servidor a partir de URL do usuário** — o servidor
  passa a ser o atacante contra a própria rede interna.
- **Desserialização** de payload em objeto sem lista de campos permitidos: o
  atacante escreve campo que a tela não expõe.
- **Upload**: tipo validado pelo conteúdo e não pela extensão; tamanho limitado;
  armazenado fora do diretório servido.

## Segredo e dado pessoal

- Credencial, token ou chave em código, em teste, em fixture, em log, ou em
  mensagem de erro. Confira também o histórico do diff — segredo removido num
  commit continua no anterior.
- **Dado pessoal em log é incidente**, não descuido. CPF, e-mail, telefone,
  endereço, dado financeiro e de saúde não entram em log, nem em URL, nem em
  mensagem de erro devolvida ao cliente.
- URL assinada com prazo longo demais, ou sem prazo, é link público.
- Erro que vaza estrutura: stack trace, nome de tabela, versão de biblioteca.

## Sessão e transporte

- Token com validade longa e sem revogação.
- Cookie sem os atributos de proteção, quando a stack usa cookie.
- Operação que muda estado a partir de requisição que o navegador envia
  automaticamente, sem verificação de origem.
- Comparação de segredo com `==` — comparação sensível a tempo vaza o valor aos
  poucos.

## Dependência

Pacote novo introduzido nesta entrega: de onde veio, quem mantém, há quanto
tempo. Um pacote com nome parecido com o popular é ataque conhecido. Versão
fixada, e não faixa aberta que muda sozinha.

## Escopo e limites

Revise **o que esta entrega mudou**. Falha pré-existente encontrada de passagem
vale reportar como observação separada, marcada como fora do escopo: misturá-la
faz o corretor mexer no que não é dele e atrasa o que é.

**Nunca rode exploração ativa, varredura ou teste de intrusão contra ambiente.**
Leitura de código e análise estática bastam aqui. Você descreve como explorar;
não explora.

## Severidade, aplicada

Use a escala de `$PACOTE/references/severity.md`. Traduzida para segurança:

- **bloqueia** — dado de um cliente acessível a outro; ação sem autorização;
  segredo exposto; dado pessoal em log.
- **alta** — exige condição improvável mas alcançável; expõe informação que
  ajuda um ataque seguinte.
- **baixa** — defesa em profundidade que falta, sem caminho de exploração hoje.

Não infle. Marcar tudo como `bloqueia` faz quem consolida descontar tudo que
você reporta, e o vazamento de verdade se perde junto.
