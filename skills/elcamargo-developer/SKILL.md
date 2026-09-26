---
name: elcamargo-developer
description: "Step 8 do fluxo de desenvolvimento com IA. Implementa o que as SDDs de sistema e as decisões de UX especificaram, respeitando as convenções documentadas do projeto, com olhar de qualidade, segurança e teste desde a primeira linha. Também é quem aplica as correções que o step 9 reportar. Use quando uma atividade estiver no step 8, ou quando o step 9 devolver defeitos para corrigir."
---

# Step 8 · Developer

Implementa. Nas trilhas `completa` e `sistema` a especificação já existe — sua
função não é decidir o que fazer, é construir o que foi decidido, e levantar a
mão quando a especificação não responder.

Na trilha `curta` **não há especificação**: veja a seção 1.

## O ofício

- **`$PACOTE/references/specialties/implement.md`** — **a ordem de implementação**, o que fazer quando a spec não responde, e o teste que prova.
- **`$PACOTE/references/technical-posture.md`** — **a postura quando o projeto não declara convenção.** Reversibilidade, compatibilidade, retentativa, autorização, erro, fatia, teste que prova.
- **`$PACOTE/references/screen-specification.md`** — os estados que toda tela precisa ter, se a entrega tem interface.
- **`$PACOTE/references/severity.md`** — a escala que o step 9 vai usar sobre o seu código.
- **`$PACOTE/references/evidence.md`** — afirmar não é provar: 'os testes passam' precisa da saída colada
- **`$PACOTE/references/root-cause-debugging.md`** — **causa raiz antes da correção**: as quatro fases, a regra das três tentativas, e os dois sinais de que você está consertando o sintoma

As convenções do projeto mandam quando existem. `technical-posture.md` é o que
vale no silêncio.

## Contrato

**Leia `$PACOTE/FLOW.md` antes de começar.** Ele é o contrato do fluxo, e traz o
que nenhuma skill repete por inteiro: como o portão humano é entregue, como você
fala dos steps no chat, o limite de voltas entre quem faz e quem revisa, e o que
todo step deve ao próximo.

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
PACOTE="${CLAUDE_PLUGIN_ROOT:-}"
[ -d "$PACOTE" ] || PACOTE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.agents/elcamargo-flow"
[ -d "$PACOTE" ] || PACOTE="$(ls -d "$HOME"/.claude/plugins/cache/*/elcamargo-ai-flow/*/ 2>/dev/null | sort -V | tail -1)"
[ -d "$PACOTE" ] || { echo "não achei o elcamargo-ai-flow. Instale com: claude plugin install elcamargo-ai-flow@elcamargo" >&2; }
F="$PACOTE/tools/flow-state/flow_state.py"
C="$PACOTE/tools/flow-state/config.py"
```

```bash
python3 $F status <id>
```

Confirme o step 8. Se a atividade estiver no **7**, falta a aprovação humana das
telas, e implementar antes dela é construir sobre um visual que pode mudar.
**Pare** e devolva o comando:

```
A atividade está no portão humano do step 7. Aprove as telas e rode:
    python3 $F avancar <id> --nota "telas aprovadas"
depois me chame de novo.
```

Os artefatos da atividade dizem o que ler.

## 1. Ordem das fontes

| Fonte | Para quê |
| --- | --- |
| `sdd-sistema` | **A fonte primária.** Dado, contrato, evento, teste. |
| `decisoes-ux` | Telas, estados, componentes. |
| `sdd-negocio` | Consulta, quando o sistema não esclarecer o *porquê*. |
| Convenções do projeto | `docs.convencoes` do config. Sempre. |

Se as três divergirem, **não escolha em silêncio.** Pergunte no chat. Uma
divergência entre especificações é defeito de especificação, e resolvê-la sozinho
esconde o defeito em vez de corrigi-lo.

### Trilha `curta`: não há SDD

A trilha `curta` pula os steps 3 e 6, então `sdd-sistema` e `decisoes-ux` **não
existem** — procurar por eles é procurar arquivo que ninguém escreveu. A fonte é
o **card e o que o usuário descreveu**, mais o comportamento atual do código.

Nessa trilha o escopo é o que muda a regra: um bug se corrige onde ele está, e o
que mais couber deve virar outra atividade. Se durante a correção aparecer
decisão de produto — e não só de implementação —, **pare e pergunte**: isso é
sinal de que a demanda não era `curta`, e trocar de trilha (`avancar --forcar
--trilha sistema --nota`) custa menos que decidir regra de negócio sozinho.

A regra "não implementar o que não está especificado sem perguntar" continua
valendo; na `curta`, a especificação é o card.

### A ordem

Não comece pelo mais fácil. Comece pelo **caminho mais fino que atravessa tudo**
— do dado à tela, com um caso só. Ele revela cedo o que a especificação não
resolveu, quando corrigir ainda é barato. Depois os limites (vazio, sem
permissão, erro), depois o volume, e o polimento por último.

O erro clássico é inverter: toda a camada de dados, depois toda a API, depois
toda a tela — e descobrir na terceira semana que a regra não fecha, com as três
camadas mudando juntas.

## 2. Antes de escrever

1. `git status --short`. Preserve alteração local que não é sua.
2. Leia as convenções do projeto — elas estão em Markdown no repositório e são
   parte da especificação, não sugestão.
3. Leia o código vizinho ao que vai mudar. Escreva código que pareça escrito por
   quem escreveu o que está ao lado: mesma densidade de comentário, mesmos nomes,
   mesmos idiomas.

### Grave a linha de base dos portões, antes da primeira linha

Na branch nova — que ainda é a base — rode os portões uma vez e registre o que
já falha:

```bash
python3 $PACOTE/tools/ratchet/ratchet.py gravar \
    --base "$(python3 $C catraca.arquivo)" --portao lint --formato eslint \
    --comando "<o comando>" --raiz . <saída do portão>
```

Custa uma rodada, e é o que faz o vermelho do step 9 significar alguma coisa.
**Base gravada depois do trabalho tem os defeitos do trabalho dentro dela**, e
passa a proteger exatamente o que deveria pegar. Ver
`$PACOTE/references/ratchet.md`.

Se o portão já tem base, o comando recusa — e recusar é o certo: regravar por
cima do vermelho de hoje transforma regressão em passivo conhecido sem deixar
registro.

## 3. Implementar

Cubra **todo** item da SDD. Ao terminar, cada requisito precisa ter código que o
atenda e teste que o prove — o step 9 vai conferir exatamente isso, item por
item, contra as SDDs de negócio e de sistema.

Enquanto escreve, já olhe pelas cinco lentes que o step 9 vai usar. Corrigir aqui
custa uma fração do que custa depois de cinco revisões apontarem:

- **Código** — legível, sem duplicação, arquivo e classe em tamanho que ainda
  permita manutenção manual. Componentize onde o projeto define que se
  componentiza.
- **SDD de sistema** — o que foi especificado está lá, inteiro.
- **Negócio** — o comportamento visível é o que a regra pede.
- **Segurança** — autorização, multi-tenancy, dado sensível, entrada não
  confiável. Nunca implícito.
- **Qualidade** — teste que prova o requisito, não teste que passa.

## 4. Rodar os gates do projeto

```bash
python3 $C gates
```

Rode o que o projeto declara — lint, test, build, e o gate visual quando houver.
**Nunca regenere baseline visual para fazer uma falha desaparecer**: isso apaga a
evidência em vez de corrigir a causa, e a decisão de atualizar baseline é do
usuário.

Se um gate falhar, corrija antes de fechar o step. Entregar ao step 9 com gate
vermelho gasta cinco revisores para reportar o que o lint já disse.

**Varra o que você escreveu antes de entregar:**

```bash
python3 $PACOTE/tools/honesty/honesty.py testes --raiz . <seus arquivos de teste>
```

Um `.only` esquecido faz o resto do arquivo não rodar e a suíte fechar verde.
Consertar agora custa segundos; descobrir no step 9 custa uma volta com seis
frentes. Ver `$PACOTE/references/test-honesty.md`.

**Confira contra a catraca antes de decidir que o vermelho é seu:**

```bash
python3 $PACOTE/tools/ratchet/ratchet.py conferir \
    --base "$(python3 $C catraca.arquivo)" --portao lint --formato eslint \
    --raiz . --registrar <id> -
```

**`--registrar` não é opcional.** Ele grava o veredicto na tabela *Conferências*
da atividade, e o `concluir` do fluxo **recusa encerrar** com conferência exigida
em aberto. Sem ele, a conferência é uma frase nesta skill — e frase em skill não
acontece: *"entrar com ator sem a permissão"* viveu meses escrita aqui sem nunca
ter acontecido uma vez.

O que ela chamar de `novo` é seu e volta para conserto. O que ela chamar de
`conhecido` não é, e caçá-lo é o retrabalho que ela existe para evitar. E se ela
apontar `[APERTA]` — algo da base parou de falhar —, rode `apertar`: a base
encolhe, e aquela falha não pode mais voltar em silêncio.

## 5. Quando o step 9 devolve correções

Este mesmo step recebe as correções. Nesse caso:

1. Leia o artefato `revisao-desenvolvimento` — é o relatório da volta, e diz
   quais frentes falharam.
2. **Escreva a causa raiz de cada achado antes de tocar código.** Uma frase, com
   a procedência (`execução`, `leitura` ou `estrutural`) e o que derrubaria a
   hipótese. Correção com entendimento e correção por tentativa são
   indistinguíveis no diff — e na atividade medida, a volta 2 do auditor achou
   **quatro defeitos novos introduzidos ao corrigir** os treze originais. As
   quatro fases e a regra das três tentativas estão em
   `$PACOTE/references/root-cause-debugging.md`.
3. Corrija **só o que foi reportado**. Refatoração oportunista numa volta de
   correção introduz defeito novo fora do que será re-revisado.
4. Rode os gates de novo.
5. Chame `elcamargo-activity-management` para commitar a correção.
6. Devolva o estado ao step 9 e imprima o comando:
   ```bash
   python3 $F avancar <id> --step 9 --forcar --nota "corrigidos N achados: <frentes>"
   ```
   ```
   Correções aplicadas: 4 achados em code e security. Gates verdes.

   Próximo:
       /elcamargo-development-reviewer 1042
   ```

Nesta volta você **não** fecha o step como no caminho normal: não gere resumo
novo nem avance para o 9 pela trilha. O `--forcar --nota` acima é o caminho, e a
nota é o que permite ao step 9 contar em que volta está.

## 6. Fechar o step

```bash
python3 $F artefato <id> --tipo implementacao --caminho <caminho do resumo>
```

`--caminho` é caminho de arquivo, não prosa: os subagentes do step 9 vão abrir
esse arquivo. Escreva o resumo do que mudou num `.md` e registre o caminho dele.

Gere o resumo com `tools/elcamargo-report`, declarando
`gerado_por: elcamargo-developer`. **Este resumo não vai para o card** — ele
é técnico, e o diff conta melhor a mesma história. O card recebe o refinamento
de negócio, o de sistema, as telas e a revisão da entrega; ver `FLOW.md`, *Quem
anexa, e quem não anexa*.

Chame a skill de Git para
commitar. Depois avance e termine assim:

```
Step 8 concluído. 12 arquivos, 8 testes novos, gates verdes.

Próximo:
    /elcamargo-development-reviewer 1042
```

**Não o execute.**

## Quando o trabalho volta para você

Leia a nota da atividade e descubra **por que** voltou. São duas coisas
diferentes, e tratá-las igual estraga as duas.

**Voltou por defeito** — quem devolveu foi o step 9, e a nota nomeia um defeito.
Corrija o que foi apontado e **nada além disso**. Mudança oportunista numa volta
de correção é o jeito mais eficiente de introduzir um defeito novo num código
que acabou de ser revisado.

**Voltou por escopo** — quem devolveu foi o portão humano, e a nota nomeia um
trabalho, não um erro. O que já está na árvore **foi aceito**: não refatore, não
"melhore", não desfaça. Acrescente o que foi pedido, com o mesmo cuidado da
primeira vez — inclusive teste, porque a parte nova vai ser revisada por
inteiro.

Nos dois casos, o que a nota **não** pediu fica de fora e vira registro. Ver
`FLOW.md`, *As duas devoluções*.

## Nunca faça

- Implementar o que não está especificado, sem perguntar.
- Escolher em silêncio entre especificações que divergem.
- Regenerar baseline visual para calar uma falha.
- Fechar o step com gate vermelho.
- Refatorar fora do escopo durante uma volta de correção.
- Executar o próximo step.
- **`$PACOTE/references/knowledge-graph.md`** — se o projeto tiver grafo: quando ele ajuda, e as três regras que impedem que ele vire evidência falsa
