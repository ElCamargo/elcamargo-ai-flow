# Rationale — elcamargo-developer (step 8)

Isto é a explicação da skill do step 8 (Desenvolvedor), não instrução. As
regras estão em `skills/elcamargo-developer/SKILL.md`; aqui fica o porquê,
com os casos medidos, movido para fora do que o step lê a cada resposta.

## Incidente

Sobre `--registrar` não ser opcional, ao conferir contra a catraca:

> Sem ele, a conferência é uma frase nesta skill — e frase em skill não
> acontece: *"entrar com ator sem a permissão"* viveu meses escrita aqui sem
> nunca ter acontecido uma vez.

## Número medido

Sobre escrever a causa raiz antes de tocar código:

> Correção com entendimento e correção por tentativa são indistinguíveis no
> diff — e na atividade medida, a volta 2 do auditor achou **quatro defeitos
> novos introduzidos ao corrigir** os treze originais.

## O erro que produziu isto

Sobre furar o escopo nas trilhas `backend`/`frontend`:

> **Furar o escopo é o erro caro desta trilha.** Entregar "só um
> endpointzinho" da outra camada entrega código que nunca passou pelo step 9
> daquela metade — e ele chega ao portão 10 dentro de uma entrega que diz não
> conter aquilo.

Sobre a ordem de implementação (o caminho mais fino primeiro):

> O erro clássico é inverter: toda a camada de dados, depois toda a API,
> depois toda a tela — e descobrir na terceira semana que a regra não fecha,
> com as três camadas mudando juntas.

## Exemplo longo

Sobre onde a ferramenta (`$PACOTE`) mora, o comentário original do resolvedor:

```bash
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
```

## Justificativa de mais de uma frase

Sobre ler `FLOW.md` antes de começar:

> Ele é o contrato do fluxo, e traz o que nenhuma skill repete por inteiro:
> como o portão humano é entregue, como você fala dos steps no chat, o limite
> de voltas entre quem faz e quem revisa, e o que todo step deve ao próximo.

Sobre confirmar o step 8 antes de implementar:

> e implementar antes dela é construir sobre um visual que pode mudar.

Sobre não escolher em silêncio quando as fontes divergem:

> Uma divergência entre especificações é defeito de especificação, e
> resolvê-la sozinho esconde o defeito em vez de corrigi-lo.

Sobre decisão de produto aparecer na trilha `curta`:

> isso é sinal de que a demanda não era `curta`, e trocar de trilha (`avancar
> --forcar --trilha sistema --nota`) custa menos que decidir regra de negócio
> sozinho.

Sobre a camada que falta na trilha `backend`/`frontend`:

> Buraco achado vira especificação e pendência, e a implementação é de outra
> atividade.

Sobre começar pelo caminho mais fino:

> Ele revela cedo o que a especificação não resolveu, quando corrigir ainda é
> barato.

Sobre olhar pelas cinco lentes do step 9 enquanto implementa:

> Corrigir aqui custa uma fração do que custa depois de cinco revisões
> apontarem.

Sobre gravar a linha de base dos portões antes da primeira linha:

> Custa uma rodada, e é o que faz o vermelho do step 9 significar alguma
> coisa. **Base gravada depois do trabalho tem os defeitos do trabalho dentro
> dela**, e passa a proteger exatamente o que deveria pegar.

Sobre o comando recusar quando o portão já tem base:

> e recusar é o certo: regravar por cima do vermelho de hoje transforma
> regressão em passivo conhecido sem deixar registro.

Sobre entregar ao step 9 com gate vermelho:

> Entregar ao step 9 com gate vermelho gasta cinco revisores para reportar o
> que o lint já disse.

Sobre varrer os testes escritos antes de entregar:

> Um `.only` esquecido faz o resto do arquivo não rodar e a suíte fechar
> verde. Consertar agora custa segundos; descobrir no step 9 custa uma volta
> com seis frentes.

Sobre o resumo técnico ao fechar o step:

> ele é técnico, e o diff conta melhor a mesma história. O card recebe o
> refinamento de negócio, o de sistema, as telas e a revisão da entrega.

Sobre ler a nota quando o trabalho volta:

> São duas coisas diferentes, e tratá-las igual estraga as duas.

Sobre corrigir só o que foi reportado, quando voltou por defeito:

> Mudança oportunista numa volta de correção é o jeito mais eficiente de
> introduzir um defeito novo num código que acabou de ser revisado.

Sobre acrescentar teste quando voltou por escopo:

> porque a parte nova vai ser revisada por inteiro.

Sobre não fechar o step normalmente numa volta de correção:

> e a nota é o que permite ao step 9 contar em que volta está.
