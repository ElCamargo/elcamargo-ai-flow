#!/usr/bin/env python3
"""Check that the package is internally consistent.

Catches the failures that only show up when someone tries to run the flow: a
skill whose declared name does not match its directory (Claude Code resolves by
directory, the flow refers to it by name), a step of the flow with no skill
behind it, or a subagent that a skill calls and nobody wrote.

    python3 test_package.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from flow_state import STEPS, TRILHAS  # noqa: E402

PACOTE = Path(__file__).resolve().parents[2]
falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


def front_matter(texto: str) -> dict[str, str]:
    if not texto.startswith("---\n"):
        return {}
    fim = texto.find("\n---\n", 4)
    if fim == -1:
        return {}
    meta = {}
    for linha in texto[4:fim].splitlines():
        chave, sep, valor = linha.partition(":")
        if sep:
            meta[chave.strip()] = valor.strip().strip('"')
    return meta


def instalacao_completa() -> None:
    """Se o pacote está instalado, está instalado INTEIRO?

    O `install.sh` cria um symlink por componente. Quem acrescenta um agente
    depois e esquece de rodar de novo fica com o pacote PARECENDO instalado e
    faltando uma peça — e a falha aparece só quando algum step tenta chamar o
    que não existe, sem mensagem que explique.

    Aconteceu com o `elcamargo-business-analysis-auditor`: 8 agentes no
    pacote, 7 visíveis. O step 2 só funcionou porque o subagente genérico
    carregou a doutrina à mão.

    Se o diretório de descoberta não existe, o pacote está desligado de
    propósito e não há o que conferir.
    """
    # O pacote pode estar em DOIS lugares, e confundi-los sai caro.
    #
    #   instalado   <projeto>/.agents/elcamargo-flow  -> há projeto hospedeiro
    #   proprio     a raiz do repositorio da ferramenta -> não há
    #
    # `PACOTE.parent.parent` presume o primeiro. No repositório próprio ele sobe
    # ATÉ A HOME de quem desenvolve, encontra `~/.claude/skills`, e afirma sobre
    # ela — reprovando por links que nunca deveriam estar lá. E o contrário é
    # pior: se a home tivesse links de outro projeto, o teste PASSARIA por eles.
    if PACOTE.parent.name != ".agents":
        checar(True, "pacote fora de projeto hospedeiro: nada a ligar, nada a conferir")
        return
    projeto = PACOTE.parent.parent
    for tipo, padrao in (("agents", "*.md"), ("skills", "*/")):
        origem = sorted(x.name.removesuffix(".md")
                        for x in (PACOTE / tipo).glob(padrao))
        destino_dir = projeto / ".claude" / tipo
        if not destino_dir.is_dir():
            continue
        ligados = sorted(x.name.removesuffix(".md")
                         for x in destino_dir.glob("elcamargo-*"))
        faltando = [n for n in origem if n not in ligados]
        checar(not faltando,
               f"{tipo}: todos os {len(origem)} componentes do pacote estão ligados"
               + (f" — FALTAM {', '.join(faltando)}, rode install.sh" if faltando else ""))


def quem_dispara_espera() -> None:
    """Todo step que dispara subagente sabe que precisa esperar por ele?

    Falhou quatro vezes na POC, em quatro steps diferentes — sempre do mesmo
    jeito: "disparei, estou aguardando", e o step parava ali. Numa delas o
    achado de uma violação de isolamento ficou órfão.

    A regra é prosa, e prosa não quebra build. Este teste faz quebrar.
    """
    texto = (PACOTE / "FLOW.md").read_text(encoding="utf-8")
    checar("Disparar não é terminar" in texto,
           "FLUXO declara que quem dispara subagente espera por ele")

    agentes = {a.stem for a in (PACOTE / "agents").glob("*.md")}
    for caminho in sorted((PACOTE / "skills").glob("*/SKILL.md")):
        corpo = caminho.read_text(encoding="utf-8")
        # Detectar o DISPARO, não a menção. Três skills falavam de subagente de
        # passagem — "o próximo step roda em sessão nova ou subagente", "os
        # subagentes do step 9 vão abrir" — e a primeira versão deste teste as
        # acusou de não saber uma regra que não se aplica a elas.
        dispara = any(nome in corpo for nome in agentes) or re.search(
            r"(abra|dispare|chame|acione)\b[^.\n]{0,40}subagente", corpo, re.I)
        if not dispara:
            continue
        sabe = ("Disparar não é terminar" in corpo
                or "não terminou enquanto" in corpo
                or "não retornar, o step não para" in corpo)
        checar(sabe, f"{caminho.parent.name} dispara subagente e sabe que precisa "
                     "esperar por ele")


def frente_de_execucao() -> None:
    """A frente que USA o sistema existe, e sabe os dois limites que a definem?

    Das 21 execucoes da POC, onze terminaram confessando "nao verifiquei em
    navegador". Era o maior ponto cego do fluxo: cinco frentes que leem e
    nenhuma que usa.

    Os dois limites sao o que impede a frente de virar ruido: ambiente que nao
    sobe nao reprova entrega, e ambiente compartilhado nao se toca.
    """
    caminho = PACOTE / "agents" / "elcamargo-runtime-reviewer.md"
    checar(caminho.exists(), "a frente de execução existe")
    if not caminho.exists():
        return
    corpo = " ".join(caminho.read_text(encoding="utf-8").split())
    checar("não subiu" in corpo or "não conseguido" in corpo or "não coberta" in corpo,
           "ela sabe declarar a dimensão como não coberta")
    checar("seu ambiente" in corpo and "Reprovar" in corpo,
           "e sabe que ambiente quebrado não reprova a entrega")
    checar("compartilhado" in corpo,
           "e que ambiente compartilhado é decisão do portão humano")
    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer" / "SKILL.md"
                     ).read_text(encoding="utf-8").split())
    checar("runtime-reviewer" in nove, "o step 9 dispara a frente de execução")
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("autorização explícita" in fluxo,
           "o FLUXO declara que homologação exige autorização explícita")


def a_frente_de_execucao_nao_e_dispensada_pelo_diff() -> None:
    """O gatilho da frente de execução pergunta por COMPORTAMENTO, não por ARQUIVO?

    Custou uma tela em homologação, com testador externo esperando. A regra
    dizia "roda quando a entrega tem tela -- quando o diff toca o frontend", e
    fechava com "numa entrega so' de backend nao ha' o que abrir".

    O defeito era `array_agg(opcao.label)` num adapter: a coluna real chama-se
    `value`, Postgres resolve nome na analise, e a rota respondia 500 em toda
    chamada contra tenant real. ZERO arquivos de frontend no diff. Tres frentes
    lendo codigo, em duas voltas, nao acharam -- porque a unica que usaria o
    sistema tinha sido dispensada pelo criterio.

    Este teste guarda a inversao do onus: nao e' a frente que prova que precisa
    rodar, e' a dispensa que precisa se justificar. E' a mesma doutrina do resto
    do pacote -- lacuna se declara, nao se presume.
    """
    caminho = PACOTE / "skills" / "elcamargo-development-reviewer" / "SKILL.md"
    nove = " ".join(caminho.read_text(encoding="utf-8").split())

    # A frase que causou o estrago nao pode voltar como REGRA. Ela continua no
    # arquivo dentro da caixa que conta o caso -- por isso a checagem e' do
    # criterio de dispensa, e nao da mera presenca das palavras.
    checar("Numa entrega só de backend não há o que abrir." not in nove,
           "a frase que dispensava entrega de backend saiu da regra")
    checar("roda sempre que a entrega toca código de aplicação" in nove,
           "a frente de execução roda por padrão, e não por exceção")
    checar("não é essa prova" in nove,
           "e o diff sem arquivo de frontend não vale como prova de dispensa")
    checar("não-coberta" in nove or "não coberta" in nove,
           "quando ela não sobe, o resultado é lacuna declarada")

    # O FLUXO nao pode continuar dizendo a regra velha em outra pagina: duas
    # fontes que discordam sao pior que uma errada, porque cada leitor acha uma.
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("acontece sempre que a entrega tem tela" not in fluxo,
           "o FLUXO não repete o gatilho por arquivo")


def a_descoberta_do_caso_e_comando_e_mora_no_step_1() -> None:
    """A trilha `revisao` descobre o caso por COMANDO, e no step 1?

    No primeiro uso real quem descobriu foi a PORTA: ela leu a branch e entregou
    ao step 1 com a resposta pronta. Funcionou, e a sessao que conduziu escreveu
    a frase que virou este teste: "se alguem entrar direto pelo step 1, ninguem
    descobre nada."

    A doutrina poe a descoberta no step 1 e o mecanismo estava na porta --
    divergencia entre doutrina e implementacao passa despercebida enquanto so' o
    caminho feliz e' exercitado.
    """
    ferramenta = PACOTE / "tools" / "prior-work" / "prior_work.py"
    checar(ferramenta.exists(), "o detector de caso existe")
    if not ferramenta.exists():
        return
    corpo = " ".join(ferramenta.read_text(encoding="utf-8").split())
    for caso in ("usou-o-fluxo", "especificou-fora", "nao-documentou"):
        checar(caso in corpo, f"e responde o caso `{caso}`")
    checar("NÃO responde" in corpo, "e declara o que ele não responde")

    um = (PACOTE / "skills" / "elcamargo-board-git-management"
          / "SKILL.md").read_text(encoding="utf-8")
    checar("prior_work.py" in um, "o step 1 roda o comando")
    checar("mesmo quando alguém já tiver dito o caso" in " ".join(um.split()),
           "e roda mesmo quando alguém já disse o caso — senão vira coincidência")

    porta = " ".join((PACOTE / "skills" / "elcamargo-ai-flow"
                      / "SKILL.md").read_text(encoding="utf-8").split())
    checar("não substitui o step 1" in porta,
           "e a porta sabe que pode adiantar, mas não substituir o step 1")


def matar_processo_e_por_pid_nunca_por_padrao() -> None:
    """A frente de execucao sabe que `pkill -f` derruba o processo do vizinho?

    Em 10/09/2026 ela terminou o trabalho e limpou com `pkill -f "nest start"`.
    O padrao casou com o backend de OUTRA atividade na mesma maquina: quatro
    servicos no chao, portas 3001 a 3004, e ela nao podia religar porque o
    prompt a proibia de executar naquela arvore.

    E o prompt estava CERTO -- ele avisava da outra atividade e mandava escolher
    portas livres. Ela escolheu 3210, 3211, 3213 e 3214, isolou banco e vhost, e
    ainda assim derrubou os alheios. Isolar porta nao protege de `pkill -f`, e
    por isso a regra e' de mecanismo e nao de cuidado.

    O guarda de arvore protege o DISCO. Este teste guarda o irmao que faltava.
    """
    guarda = PACOTE / "tools" / "process-guard" / "process_guard.py"
    checar(guarda.exists(), "o guarda de processo existe")
    if not guarda.exists():
        return
    corpo = " ".join(guarda.read_text(encoding="utf-8").split())
    checar("marcar" in corpo and "conferir" in corpo,
           "e tem o par marcar/conferir, como o guarda de árvore")
    checar("NÃO prova" in corpo or "NÃO SÃO SUAS" in corpo,
           "e declara o que ele não prova")

    # A regra so' vale se quem sobe processo a le'.
    oficio = " ".join((PACOTE / "references" / "specialties" / "system-usage.md"
                       ).read_text(encoding="utf-8").split())
    checar("mata por PID, nunca por padrão" in oficio,
           "o ofício de usar o sistema manda matar por PID")
    checar("pkill" in oficio and "proibido" in oficio,
           "e diz que `pkill` é proibido, com essa palavra")
    checar("isolar porta não protege" in oficio.lower(),
           "e explica por que escolher porta livre não bastou")
    checar("o que você subiu e o que você derrubou" in oficio.lower(),
           "e exige a seção do relatório que permitiu consertar em minutos")

    agente = " ".join((PACOTE / "agents" / "elcamargo-runtime-reviewer.md"
                       ).read_text(encoding="utf-8").split())
    checar("pkill" in agente, "a própria frente de execução carrega a regra")

    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("process_guard.py marcar" in nove,
           "e o step 9 marca os processos antes de disparar")


def a_trilha_de_revisao_nao_toca_no_trabalho_alheio() -> None:
    """A trilha `revisao` sabe que confere o trabalho de OUTRA pessoa?

    Ela e' a unica que nao produz software. As tres garantias que a definem
    saem da FORMA dela -- sem step 8 o step 9 nao tem a quem devolver correcao
    --, mas duas dependem de estar escritas: nao escrever no card de quem nao
    pediu, e rodar em worktree da branch do dev para nao parar o trabalho de
    quem revisa.

    O caso de uso: "preciso revisar o trabalho de outro dev, em outro card dele,
    sem refazer o trabalho todo -- e posso estar implementando algo na branch da
    maquina e nao posso parar."
    """
    doutrina = PACOTE / "references" / "foreign-review.md"
    checar(doutrina.exists(), "a doutrina de revisão de trabalho alheio existe")
    if not doutrina.exists():
        return
    corpo = " ".join(doutrina.read_text(encoding="utf-8").split())
    checar("objeto de revisão, não fonte da verdade" in corpo,
           "e diz que a SDD do dev é objeto de revisão, não fonte da verdade")
    checar("git worktree add" in corpo,
           "e mostra como abrir a worktree da branch dele")
    checar("não faça push" in corpo or "não commite" in corpo,
           "e proíbe commitar ou empurrar na árvore de outra pessoa")
    checar("não anexa nada" in corpo or "não escreve no card" in corpo.lower()
           or "Não escreve no card" in corpo,
           "e proíbe publicar no card de quem não pediu")

    # A doutrina so' vale se os steps que a trilha usa mandarem le-la.
    for nome in ("elcamargo-board-git-management",
                 "elcamargo-business-analysis-reviewer",
                 "elcamargo-system-analysis-reviewer",
                 "elcamargo-development-reviewer"):
        texto = (PACOTE / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
        checar("foreign-review.md" in texto,
               f"{nome} manda ler a doutrina quando a trilha é `revisao`")

    # A forma da trilha e' a garantia que nao depende de ninguem lembrar.
    sys.path.insert(0, str(PACOTE / "tools" / "flow-state"))
    import flow_state  # noqa: PLC0415
    trilha = flow_state.TRILHAS.get("revisao")
    checar(trilha == [1, 2, 4, 9, 10], "a trilha `revisao` é 1, 2, 4, 9, 10")
    checar("revisao-publicada" in flow_state.TIPOS_DE_ARTEFATO,
           "e o entregável dela tem nome no vocabulário: `revisao-publicada`")
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("`revisao-publicada`" in fluxo,
           "que também está na tabela do FLUXO — os dois lugares ou nenhum")
    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("--tipo revisao-publicada" in nove,
           "e o step 9 sabe qual usar quando não há step 8 para devolver")
    checar(trilha is not None and 8 not in trilha,
           "e não tem step 8 — é o que impede a revisão de consertar")


def step4_sabe_escalar() -> None:
    """O step 4 sabe que tem saída, e não limite?

    O step 9 para na terceira volta porque revisor que relê o mesmo diff fabrica
    achado. O step 4 relê documento que mudou — na POC, cada volta achou defeito
    real. O que ele precisa não é limite, é escalar ao portão humano quando a
    divergência deixa de ser defeito e vira decisão.
    """
    texto = (PACOTE / "FLOW.md").read_text(encoding="utf-8")
    checar("O step 4 tem saída, não limite" in texto,
           "FLUXO declara a saída do step 4 para o portão humano")
    quatro = (PACOTE / "skills" / "elcamargo-system-analysis-reviewer" / "SKILL.md"
              ).read_text(encoding="utf-8")
    normal = " ".join(quatro.split())
    checar("escale ao portão 5" in normal and "terceira passada" in normal,
           "o step 4 sabe escalar ao portão 5 na terceira reprovação")
    checar("duas posições" in quatro,
           "e sabe que escala com as DUAS posições escritas, não só a dele")


def pergunta_em_vez_de_pressuposto() -> None:
    """A decisão que só o dono do produto sabe vira pergunta, não Pressuposto?

    Numa execução real uma SDD marcou `Pressuposto` onde um item de menu entrava,
    porque "a barra lateral do Figma está vazia". Estava vazia por construção —
    aquele arquivo nunca desenhou navegação. O dono respondeu num clique, e
    respondeu diferente do que a SDD assumira. O teste é se a resposta era
    alcançável, e ele precisa estar escrito nos três lugares que decidem.
    """
    trilha = " ".join((PACOTE / "references" / "traceability.md"
                       ).read_text(encoding="utf-8").split())
    checar("Pressuposto exige que a resposta fosse alcançável" in trilha,
           "a rastreabilidade declara quando Pressuposto é indevido")
    checar("é **pergunta**, não pressuposto" in trilha,
           "e diz o que fazer quando nenhum artefato ia responder")

    tres = " ".join((PACOTE / "skills" / "elcamargo-system-analyst" / "SKILL.md"
                     ).read_text(encoding="utf-8").split())
    checar("alcançável" in tres,
           "o step 3 exige que a resposta fosse alcançável antes de pressupor")

    quatro = " ".join((PACOTE / "skills" / "elcamargo-system-analysis-reviewer"
                       / "SKILL.md").read_text(encoding="utf-8").split())
    checar("Pressuposto` que nenhum artefato ia responder" in quatro,
           "e o step 4 procura por Pressuposto indevido na conferência")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("Decisão encontrada no meio do caminho não espera o portão" in fluxo,
           "o FLUXO manda trazer a decisão na hora, sem esperar o portão")
    checar("Uma a uma." in fluxo and "Sem travar." in fluxo,
           "uma a uma, com opções reais, e sem travar o fluxo")


def a_prosa_nova_da_correcao() -> None:
    """A doutrina cobre a frase que a correção traz junto, não só o defeito?

    Quatro rodadas de auditoria sobre a mesma spec isolaram o padrão: re-editar o
    trecho funciona; o que falha é o parágrafo escrito para justificar a correção,
    onde a memória substitui a leitura. Numa delas, a afirmação errada era
    desmentida por um documento a dezesseis linhas do trecho citado.
    """
    texto = " ".join((PACOTE / "references" / "evidence.md"
                      ).read_text(encoding="utf-8").split())
    checar("A frase nova que a correção traz junto" in texto,
           "a doutrina de evidência cobre a prosa nova da correção")
    checar("Abra o arquivo antes de escrever a justificativa" in texto,
           "e diz o que fazer antes de escrever a justificativa")


def duas_voltas_em_todo_par() -> None:
    """O limite de duas voltas vale em todo par fazedor↔revisor, não só no 9?

    A auditoria converge num documento congelado e diverge num que continua sendo
    corrigido: cada correção escreve texto novo, e texto novo tem taxa de defeito
    própria. Numa spec real deu 12, 6, 5, 1, 0 achados em cinco rodadas — e a
    rodada seguinte, sobre a versão corrigida, achou dez outra vez. Sete horas de
    retrabalho, porque só o step 9 tinha limite.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("Duas voltas entre quem faz e quem revisa. Em todo par." in fluxo,
           "o FLUXO declara o limite para todo par fazedor/revisor")
    checar("Achados abertos" in fluxo,
           "e diz o que sai da terceira volta: o aberto declarado, não escondido")

    for nome, rotulo in [("elcamargo-business-analysis-reviewer", "step 2"),
                         ("elcamargo-system-analyst", "step 3")]:
        texto = " ".join((PACOTE / "skills" / nome / "SKILL.md"
                          ).read_text(encoding="utf-8").split())
        checar("no máximo duas voltas" in texto.lower(),
               f"o {rotulo} para na terceira volta da auditoria")
        checar("Achados abertos" in texto,
               f"e o {rotulo} declara o que ficou aberto em vez de esconder")

    sev = " ".join((PACOTE / "references" / "severity.md"
                    ).read_text(encoding="utf-8").split())
    checar("Em documento, severidade é alcance" in sev,
           "a severidade distingue documento de código")
    checar("chega ao desenvolvedor como instrução" in sev,
           "e o teste é se o achado alcança quem implementa")

    quatro = " ".join((PACOTE / "skills" / "elcamargo-system-analysis-reviewer"
                       / "SKILL.md").read_text(encoding="utf-8").split())
    checar("Cobertura e coerência têm réguas diferentes" in quatro,
           "o step 4 não confunde cobertura com coerência")


def citacao_conferida_por_comando() -> None:
    """A conferência de citação existe e está ligada em quem escreve e quem revisa?

    Citação escrita de memória foi a classe de defeito mais repetida numa spec
    real. O comando custa segundos; a rodada de subagente que a achava custava
    uma hora.
    """
    ferramenta = PACOTE / "tools" / "citations" / "citations.py"
    checar(ferramenta.is_file(), "a ferramenta de conferência de citação existe")
    fonte = ferramenta.read_text(encoding="utf-8")
    checar("git ls-files" in fonte,
           "e resolve nome solto pelo índice do git, não por varredura de disco")
    checar("29 conflitos, todos legítimos" in fonte,
           "e registra a verificação que foi derrubada, para ninguém repeti-la")

    for nome, rotulo in [("elcamargo-system-analyst", "step 3"),
                         ("elcamargo-system-analysis-reviewer", "step 4")]:
        texto = (PACOTE / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
        checar("citations/citations.py codigo" in texto,
               f"o {rotulo} roda a conferência de citação")


def portao_humano_pergunta() -> None:
    """Os três portões humanos chegam como card de pergunta, não como leitura?

    Pedir leitura transfere a quem decide o trabalho de achar a decisão. Uma spec
    de mil e novecentas linhas tem uma dúzia de decisões enterradas em prosa;
    quem a escreveu sabe quais são, quem vai decidir não tem como saber sem
    reler tudo.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("O portão humano chega como pergunta, nunca como leitura" in fluxo,
           "o FLUXO declara que portão humano chega como pergunta")
    checar("A aprovação é a última pergunta, não a única." in fluxo,
           "e que portão que só pergunta 'aprovado?' é carimbo, não portão")
    checar("No máximo quatro por vez" in fluxo,
           "e limita o número de cards, para não virar formulário")

    for nome, portao in [("elcamargo-system-analysis-reviewer", "5"),
                         ("elcamargo-ux-reviewer", "7"),
                         ("elcamargo-development-reviewer", "10")]:
        texto = " ".join((PACOTE / "skills" / nome / "SKILL.md"
                          ).read_text(encoding="utf-8").split())
        checar("Entregue o portão como perguntas, não como leitura" in texto,
               f"o step que entrega o portão {portao} traz as perguntas")


def anexo_conferido_e_registrado() -> None:
    """O step confere que o anexo subiu, e o estado da atividade registra?

    A verificação de ida e volta prova que o byte chegou íntegro. Ela não prova
    que o anexo aconteceu: numa execução real o `attach.py` mandava
    `Content-Type: application/pdf` e a API recusava todo PDF com 400. A
    obrigação estava escrita na skill, o comando estava lá, e o anexo nunca
    subiu — descoberto uma atividade depois, por acaso.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("Verificar que subiu é do step, não do usuário" in fluxo,
           "o FLUXO separa 'o byte chegou íntegro' de 'o anexo aconteceu'")
    checar("O card recebe pergunta, não relatório" in fluxo,
           "e declara quando o card recebe anexo, pelo critério do que pergunta")

    # O procedimento mora numa referência só, e não copiado em quatro skills:
    # eram 54 linhas idênticas, que é onde a divergência entra sem ninguém ver.
    manual = " ".join((PACOTE / "references" / "card-attachment.md"
                       ).read_text(encoding="utf-8").split())
    checar("attach.py --conferir" in manual,
           "a referência do anexo manda conferir que o anexo subiu")
    checar("--tipo anexo" in manual,
           "e registrar o anexo no estado da atividade")
    checar("--pendencia" in manual and "--origem" in manual,
           "e carrega o comando com a pendência declarada e conferida")

    anexam = ["elcamargo-business-analysis-reviewer", "elcamargo-system-analyst",
              "elcamargo-ux-reviewer", "elcamargo-development-reviewer"]
    for nome in anexam:
        texto = " ".join((PACOTE / "skills" / nome / "SKILL.md"
                          ).read_text(encoding="utf-8").split())
        curto = nome.replace("elcamargo-", "")
        checar("references/card-attachment.md" in texto,
               f"{curto} manda ler a referência do anexo antes de subir")
        # O critério de 2.19.0. Antes era "quem lê", e por ele os quatro steps
        # anexavam sempre — o card acumulava PDF que ninguém abria, e o que
        # pedia resposta se perdia no meio do que era só registro. A DECISÃO
        # fica na skill; só o procedimento foi para a referência.
        checar("pendência" in texto,
               f"{curto} decide pelo critério da pendência")
        checar("não anexe" in texto,
               f"e diz explicitamente para NÃO anexar quando não há")

    # E o portão é de máquina, não só de texto: a ferramenta recusa sozinha.
    ferramenta = (PACOTE / "tools" / "attach" / "attach.py"
                  ).read_text(encoding="utf-8")
    checar("def conferir_pendencias" in ferramenta,
           "e o attach.py recusa o anexo sem pendência, sem depender da skill")

    oito = (PACOTE / "skills" / "elcamargo-developer" / "SKILL.md"
            ).read_text(encoding="utf-8")
    checar("attach.py" not in oito,
           "o step 8 não anexa — resumo de implementação é técnico")


def passagem_de_step_e_clique() -> None:
    """O proximo step e oferecido como clique, sem deixar de ser autorizado?

    O comando impresso no fim do texto obriga a pessoa a copiar, e nao diz o que
    ela esta autorizando: "rodar o step 8" e "implementar quatro fatias, com duas
    migrations e a primeira rota a declarar editForm" sao a mesma acao, e so a
    segunda deixa decidir.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("A passagem de step também é um clique" in fluxo,
           "o FLUXO oferece o próximo step como card, não só como comando")
    checar("Clique é forma de autorizar, não atalho para pular o portão." in fluxo,
           "e o clique não vira atalho para pular a autorização")
    checar("contexto novo" in fluxo,
           "e o step seguinte continua rodando em contexto novo")


def step_tem_cargo_legivel() -> None:
    """Cada step tem cargo, e o cargo e' o que se le?

    "O step 3 respondeu ao step 4 e pode chamar o step 5" e' verdadeiro e
    ilegivel: quem le nao sabe quem faz o que ali. O endereco da skill serve
    para invocar, nao para nomear.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fs", PACOTE / "tools" / "flow-state" / "flow_state.py")
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)

    checar(all("cargo" in d for d in fs.STEPS.values()),
           "os dez steps têm cargo")
    checar(all(not d["cargo"].startswith("elcamargo-") for d in fs.STEPS.values()),
           "e nenhum cargo é o endereço da skill disfarçado")
    # O que o codigo decide por step mora em `STEPS` desde 2.62.0, e os mapas
    # se derivam dele. Chave com erro de digitacao some calada da derivacao --
    # `"verificaçao"` nao liga verificacao nenhuma --, por isso a lista fechada.
    chaves = {"nome", "tipo", "cargo", "confere", "verificacao", "modelo"}
    estranhas = sorted({c for d in fs.STEPS.values() for c in d} - chaves)
    checar(not estranhas, f"STEPS só tem chaves conhecidas ({estranhas or 'ok'})")
    for n, d in fs.STEPS.items():
        if "confere" in d:
            alvo = fs.STEPS.get(d["confere"], {})
            checar(d["confere"] < n and alvo.get("tipo") == "skill",
                   f"step {n} confere um step ANTERIOR que produz algo "
                   f"(confere {d['confere']})")
        if d.get("verificacao"):
            checar(d["tipo"] == "skill" and "confere" in d,
                   f"step {n}, de verificação, diz o que verifica")
        if "modelo" in d:
            checar(d["tipo"] == "skill" and d["modelo"] in ("sonnet", "opus", "haiku"),
                   f"step {n}: `modelo` só em skill, e um apelido válido")
    # Os valores de antes da mudanca, fixados: mover para `STEPS` nao podia
    # mudar o que a maquina decide. Mudar um deles agora e' decisao, e cai aqui.
    checar(fs.CONFERE_O_QUE_O_STEP_PRODUZ == {4: 3, 5: 3, 7: 6, 9: 8},
           "quem confere o que é o mesmo de antes")
    checar(fs.STEPS_DE_VERIFICACAO == {4, 9} and fs.STEPS_DE_PORTAO == {5, 7, 10},
           "verificação e portão são os mesmos de antes")
    checar(fs.MODELO_DO_DISPARO == {1: "sonnet"},
           "e o modelo do disparo também")
    fonte = (PACOTE / "tools" / "flow-state" / "flow_state.py").read_text(encoding="utf-8")
    checar(not re.search(r"^(CONFERE_O_QUE_O_STEP_PRODUZ|STEPS_DE_VERIFICACAO|"
                         r"MODELO_DO_DISPARO)\b[^=]*=\s*\{\s*\d", fonte, re.M),
           "nenhum dos três voltou a ser literal com número de step")

    checar(fs.rotulo(3) == "3 · Analista de Sistema",
           "o rótulo traz número e cargo, sem endereço")
    checar("elcamargo-system-analyst" in fs.rotulo_com_endereco(3),
           "e o endereço aparece onde é acionável")
    checar(fs.rotulo_com_endereco(5) == "5 · Portão humano · Especificação",
           "step humano não tem endereço a mostrar")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("Chame cada step pelo cargo, e não pelo número" in fluxo,
           "o FLUXO manda falar pelo cargo no chat")
    checar("Revisor da Entrega** está rodando as seis frentes" in fluxo,
           "e traz o exemplo exato da frase que funcionou")


def toda_skill_manda_ler_o_fluxo() -> None:
    """Toda skill de step abre mandando ler o FLUXO?

    Regra escrita na doutrina so' vale se quem executa a ler. Quatro das sete
    skills apenas CITAVAM o FLUXO em nota de rodape, e as regras transversais —
    como o portao humano e entregue, como se fala dos steps no chat — nao
    chegavam a quem instalasse o pacote noutro projeto.
    """
    for skill in sorted((PACOTE / "skills").iterdir()):
        arquivo = skill / "SKILL.md"
        if not arquivo.is_file():
            continue
        texto = " ".join(arquivo.read_text(encoding="utf-8").split())
        checar("Leia `$PACOTE/FLOW.md` antes de começar" in texto
               or "Leia `$PACOTE/FLOW.md` antes de qualquer coisa" in texto
               or "Leia `elcamargo-flow/FLOW.md`" in texto,
               f"{skill.name.replace('elcamargo-', '')} manda ler o FLUXO")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("O que o pacote garante, e o que depende de a skill ler isto" in fluxo,
           "e o FLUXO separa o que é código do que é doutrina")


def contexto_de_agente_nao_e_lugar_de_guardar() -> None:
    """O step longo persiste enquanto trabalha, e o travamento e' detectavel?

    O Revisor da Entrega rodou as seis frentes, todas voltaram, e ele travou na
    consolidacao: 52 minutos, seis revisoes sobre 6094 linhas, e zero artefato.
    Os retornos moravam no contexto dele.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("Persista enquanto trabalha, não no fim" in fluxo,
           "o FLUXO manda persistir durante, não no fim")
    checar("morre com ele" in fluxo,
           "e diz por quê: o que existe só no contexto morre com o agente")
    checar("Um step que não escreve há muito tempo não está pensando" in fluxo,
           "e ensina a distinguir agente travado de agente trabalhando")
    checar("stat -f" in fluxo,
           "com o comando que mede, não com um conselho de paciência")
    checar("tools/watch/watch.py" in fluxo,
           "e aponta a ferramenta que vigia, em vez de mandar esperar")
    checar((PACOTE / "tools" / "watch" / "watch.py").is_file(),
           "e a ferramenta existe")

    checar("Todo retorno passa por uma conferência de segundos" in fluxo,
           "o FLUXO manda conferir todo retorno de subagente")
    checar("segundos**, não uma segunda revisão" in fluxo,
           "e dá o orçamento, para a conferência não virar outro trabalho")
    checar("seis frentes foram pedidas, seis voltaram?" in fluxo,
           "e lembra da conferência mais barata: contar")


def venv_do_relatorio_nao_mora_em_tmp() -> None:
    """O venv do ReportLab esta fora do /tmp, que o sistema limpa?

    No meio de uma atividade o venv apareceu MEIO apagado: `reportlab/lib/` so'
    com `__pycache__`, e o `pip` do proprio venv sem executar. O sintoma nao e
    "nao instalado" — e instalado e quebrado, que e pior, porque a mensagem de
    erro fala de import e nao de faxina.
    """
    for nome in ["install.sh", "README.md", "tools/matrix/matrix.py",
                 "tools/elcamargo-report/generate.py",
                 "tools/elcamargo-report/style.py",
                 "tools/elcamargo-report/README.md"]:
        texto = (PACOTE / nome).read_text(encoding="utf-8")
        checar("/tmp/venv_report" not in texto,
               f"{nome} não manda instalar venv no /tmp")

    cap = (PACOTE / "tools" / "flow-state" / "capabilities.py"
           ).read_text(encoding="utf-8")
    checar(".cache" in cap and "elcamargo-flow" in cap,
           "a capacidade procura o venv num diretório durável")
    checar("/tmp/venv_report" in cap,
           "e ainda aceita o caminho herdado de quem já o tinha")


def ler_figma_nao_depende_de_mcp() -> None:
    """O pacote diz, onde a decisão é tomada, que leitura e' REST e nao MCP?

    Em 08/09/2026 uma frente irmã parou o step 6 "por falta de MCP da Figma":
    tentou o MCP, tentou o Chrome, tentou o navegador interno e parou num muro
    de login -- com o token instalado na mesma máquina e o arquivo legível em um
    comando. Três defeitos de uma vez, e os três são de texto do pacote:

      1. `capacidade_figma()` respondia em nomes de tool do MCP, e a estratégia
         `sem_mcp` mandava desistir da leitura -- o que e' FALSO.
      2. Ela devolvia `disponivel: None` quando o caminho REST e' detectável.
      3. A proibição do navegador morava só no AGENTE, que a skill nunca chegou
         a disparar porque desistiu antes.
    """
    sys.path.insert(0, str(PACOTE / "tools" / "flow-state"))
    import capabilities  # noqa: PLC0415
    figma = capabilities.capacidade_figma()
    estrategia = figma.get("estrategia", {})

    # Conferido no OBJETO, e nao no texto do arquivo: a frase antiga aparece de
    # proposito no docstring, contando o defeito. O que nao pode e' ela voltar a
    # ser a resposta que a sessao le.
    checar("sem_mcp" not in estrategia,
           "a estratégia `sem_mcp` sumiu: sem MCP a leitura continua possível")
    checar("REST" in estrategia.get("leitura", ""),
           "e a leitura e' declarada como REST")
    checar("get_code_connect_map" not in " ".join(estrategia.values()),
           "e a estratégia de leitura deixou de ser escrita em tool do MCP")
    checar("navegador" in figma.get("aviso", ""),
           "e o aviso contra o navegador viaja junto da capacidade")

    # A decisão de caminho e' da SKILL, na janela principal. A regra tem que
    # estar onde ela e' tomada -- estar só no agente foi o defeito.
    seis = (PACOTE / "skills" / "elcamargo-ux-reviewer" / "SKILL.md"
            ).read_text(encoding="utf-8")
    checar("tools/figma/figma.py" in seis,
           "o step 6 nomeia a ferramenta que le, antes de escolher o caminho")
    checar("plano B não é o navegador" in seis,
           "e proíbe o navegador na própria skill, nao só no agente")

    checar(figma["disponivel"] in (True, False),
           "e a resposta e' sim ou nao, nao mais um '?' que a sessão adivinha")
    checar("figma.py" in str(figma.get("comandos", "")),
           "carregando os comandos de leitura junto")


def as_frentes_do_step9_nao_derrubam_a_maquina() -> None:
    """As seis frentes rodam em levas, e as que escrevem nao sujam a arvore?

    Em 08/09/2026 o step 9 disparou as seis de uma vez numa maquina com 16 GB.
    Somaram mais de 3 GB por cima de 13,7 ja' usados, a maquina paginou ate'
    travar, e duas frentes morreram -- a revisao fechou com quatro de seis, e a
    que morreu era a unica que produz procedencia `execucao`.

    E no meio disso, a frente de qualidade tinha tres mutantes vivos em cima da
    validacao de boot de um segredo. Ela restaurou por pouco. As outras frentes
    estavam LENDO aquela arvore, e so' uma percebeu -- por conta propria.
    """
    nove = (PACOTE / "skills" / "elcamargo-development-reviewer" / "SKILL.md"
            ).read_text(encoding="utf-8")
    checar("Não dispare as seis de uma vez" in nove,
           "o step 9 proibe o disparo unico das seis frentes")
    checar("Espere uma leva voltar antes de abrir a próxima" in nove,
           "e espera cada leva, que e' o que limita o pico")
    checar("isolation: worktree" in nove,
           "as duas que escrevem rodam em arvore propria")
    checar("não escrevem nada" in nove,
           "e as outras quatro tem o contrato de nao escrever")
    checar("tree_guard.py marcar" in nove,
           "e a arvore e' marcada ANTES do disparo")
    # A tabela de levas lida como "rode estas seis" -- e na volta 2 rodam so' as
    # que falharam. A frente do app apontou a ambiguidade no primeiro uso.
    checar("não a lista de quem roda" in nove,
           "e a tabela diz que e' ORDEM, nao a lista de quem roda")

    # A frente de qualidade rendeu mais mutando do que rodando gates: cinco
    # mutacoes simultaneas deixaram 1582 casos verdes.
    especialidade = (PACOTE / "references" / "specialties" /
                     "test-and-quality.md").read_text(encoding="utf-8")
    checar("1582" in especialidade,
           "a especialidade de qualidade carrega o caso que a mutacao revelou")
    qa = (PACOTE / "agents" / "elcamargo-quality-reviewer.md"
          ).read_text(encoding="utf-8")
    checar("MUTANDO" in qa and "test-and-quality.md" in qa,
           "e o agente manda mutar, apontando para o procedimento")

    # A deriva do cinco/seis. `as cinco` sobrou de quando eram cinco frentes, e
    # "termine quando as cinco voltarem" e' exatamente o silencio que aquela
    # secao existe para proibir: contar cinco retornos quando sao seis.
    checar("enquanto as seis não voltarem" in nove,
           "e o step so' termina quando as SEIS voltarem")

    guarda = PACOTE / "tools" / "tree-guard" / "tree_guard.py"
    checar(guarda.is_file(), "o guarda de arvore existe")
    texto = guarda.read_text(encoding="utf-8")
    checar("sha256" in texto,
           "e compara CONTEUDO: a arvore ja' chega suja do step 8, e um mutante"
           " por cima daria o mesmo codigo de `git status`")
    checar("O que ela NÃO prova" in texto,
           "declarando que arvore limpa no fim nao prova leitura limpa no meio")


def texto_livre_vai_entre_aspas_simples() -> None:
    """Os exemplos nao convidam o shell a comer uma palavra?

    Entre aspas DUPLAS, crase e' substituicao de comando. Uma nota escrita na voz
    deste pacote -- "o `avancar` foi forcado porque..." -- chega ao comando SEM a
    palavra, e a ferramenta reporta sucesso: ela recebeu exatamente o que lhe foi
    passado, e o erro aconteceu antes dela. A nota do `avancar` e' permanente.

    Aconteceu em 09/09/2026 numa mensagem entre sessoes, e o pacote convidava ao
    mesmo: 29 exemplos de texto livre entre aspas duplas, num projeto cuja prosa
    inteira cita termo tecnico entre crases.
    """
    import re as _re
    flags = ("nota", "comentario", "titulo", "motivo", "detalhe", "admitir")
    # `--nota "$VAR"` fica de fora, e e' a saida documentada para texto com
    # apostrofo: substituicao de comando nao acontece sobre o VALOR de uma
    # variavel. O que se caca e' prosa literal entre aspas duplas.
    padrao = _re.compile(r'--(' + "|".join(flags) + r') "(?!\$)')
    alvos = [*(PACOTE / "skills").glob("*/SKILL.md"),
             *(PACOTE / "agents").glob("*.md"),
             *(PACOTE / "references").glob("**/*.md"),
             PACOTE / "FLOW.md"]
    culpados = sorted(str(a.relative_to(PACOTE)) for a in alvos
                      if padrao.search(a.read_text(encoding="utf-8")))
    checar(not culpados,
           f"nenhum exemplo passa texto livre entre aspas duplas "
           f"(achados: {culpados or 'nenhum'})")

    fluxo = (PACOTE / "FLOW.md").read_text(encoding="utf-8")
    checar("Texto livre vai entre aspas SIMPLES" in fluxo,
           "e o FLUXO diz por que, onde se aprende a invocar")


def o_instrumento_e_auditado() -> None:
    """O pacote audita as proprias skills e agentes?

    Todo o fluxo depende desses dezesseis arquivos, e nada os verificava. Deriva
    de nome, descricao que nao dispara e agente sem lista de ferramentas so'
    apareciam quando falhavam numa atividade real.
    """
    ferramenta = PACOTE / "tools" / "audit-package" / "audit_package.py"
    checar(ferramenta.is_file(), "o auditor do proprio pacote existe")

    import subprocess
    r = subprocess.run([sys.executable, str(ferramenta)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-500:])
    checar(r.returncode == 0,
           "e o pacote passa na propria auditoria, sem violacao grave")
    checar("NÃO verifica" in r.stdout,
           "e o auditor declara o que nao alcanca")


def procedencia_esta_no_eixo_certo() -> None:
    """Severidade e procedencia sao dois eixos, e as seis frentes declaram os dois?

    Sem procedencia, "o teste falha" e "acho que essa validacao esta errada"
    chegam ao consolidador no mesmo formato. Severidade responde quao ruim;
    procedencia responde como eu sei. Tres dos nove defeitos graves de uma
    revisao real so' existiam porque uma frente subiu a aplicacao.
    """
    sev = " ".join((PACOTE / "references" / "severity.md"
                    ).read_text(encoding="utf-8").split())
    checar("Procedência: como você sabe" in sev,
           "a escala distingue severidade de procedência")
    for palavra in ("execução", "leitura", "estrutural"):
        checar(f"**{palavra}**" in sev, f"e nomeia a procedência `{palavra}`")
    checar("não reprova sozinho" in sev,
           "e `estrutural` sozinho não reprova")
    checar("Vale igual quando o achado FECHA" in sev,
           "e a procedência vale também quando o achado é dado por fechado")

    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("A procedência decide quem derruba quem" in nove,
           "o step 9 usa a procedência para resolver empate")
    checar("Ganha a execução" in nove,
           "e leitura contra execução perde")

    frentes = ["code-reviewer", "security-reviewer", "quality-reviewer",
               "implemented-sdd-reviewer", "implemented-business-reviewer",
               "runtime-reviewer"]
    for frente in frentes:
        texto = (PACOTE / "agents" / f"elcamargo-{frente}.md"
                 ).read_text(encoding="utf-8")
        checar("Declare a procedência de cada achado" in texto,
               f"a frente {frente} declara a procedência")


def todo_achado_tem_destino() -> None:
    """A revisao conta quantos achados viraram mudanca, ou so' os lista?

    Uma revisao real produziu vinte e um achados e ninguem sabia quantos tinham
    virado mudanca: a informacao existia, espalhada em tres tabelas com tres
    vocabularios, e nenhuma somavel com as outras. Numa rotina de revisao
    automatica de porte industrial, 94% das propostas nunca foram tocadas.
    """
    dest = " ".join((PACOTE / "references" / "outcome.md"
                     ).read_text(encoding="utf-8").split())
    for palavra in ("corrigido", "descartado", "aceito", "aberto"):
        checar(f"**{palavra}**" in dest, f"a referência nomeia o destino `{palavra}`")
    checar("Negação não é destino" in dest,
           "e recusa 'não fechado' como destino")
    checar("O descartado fica na tabela" in dest,
           "e o descarte fica registrado, em vez de ser apagado")
    checar("Bloqueio tem duas saídas, não três" in dest,
           "e bloqueio não viaja aberto")
    checar("O número não é meta" in dest,
           "e a taxa de conversão não vira meta a perseguir")

    sev = " ".join((PACOTE / "references" / "severity.md"
                    ).read_text(encoding="utf-8").split())
    checar("E o terceiro eixo" in sev and "outcome.md" in sev,
           "a escala aponta para o terceiro eixo")

    ferramenta = PACOTE / "tools" / "outcome" / "outcome.py"
    checar(ferramenta.is_file(), "a conferência mecânica existe")
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("tools/outcome/outcome.py" in fluxo,
           "e o FLUXO a declara entre o que é da máquina")

    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("| **Destino** |" in nove,
           "o step 9 tem a coluna Destino na tabela de consolidação")
    checar("tools/outcome/outcome.py conferir" in nove,
           "e roda a conferência antes de gerar o relatório final")
    checar("Leve a distribuição que ela imprime para o portão 10" in nove,
           "e leva a distribuição para o portão humano")

    for skill in ("elcamargo-business-analysis-reviewer",
                  "elcamargo-system-analysis-reviewer"):
        texto = " ".join((PACOTE / "skills" / skill / "SKILL.md"
                          ).read_text(encoding="utf-8").split())
        checar("outcome.md" in texto,
               f"{skill} também escreve o destino de cada achado")


def a_catraca_separa_o_passivo() -> None:
    """Um portao vermelho diz de quem e' o vermelho?

    Na POC, tres vezes nao disse: um aviso de lint marcado "pre-existente" a'
    mao porque alguem por acaso sabia, 126 de 152 invariantes visuais ignoradas
    sem ninguem contar, e a volta 2 reprocessando o passivo da volta 1.
    """
    cat = " ".join((PACOTE / "references" / "ratchet.md"
                    ).read_text(encoding="utf-8").split())
    checar("A identidade não pode conter o que uma edição legítima muda" in cat,
           "a referência proíbe número de linha na identidade da falha")
    checar("185" in cat and "176" in cat,
           "e traz o caso medido: o mesmo aviso mudou de linha")
    checar("ela só aperta" in cat,
           "e declara que a catraca só encolhe")
    checar("Regenerar a base para a falha sumir" in cat,
           "e nomeia o gesto que a destrói")
    checar("nunca regenere baseline de imagem" in cat,
           "inclusive o baseline visual")
    checar("Que a falha conhecida é aceitável" in cat,
           "e diz o que ela não prova")

    ferramenta = PACOTE / "tools" / "ratchet" / "ratchet.py"
    checar(ferramenta.is_file(), "a ferramenta existe")
    codigo = ferramenta.read_text(encoding="utf-8")
    checar("saída real" in codigo or "capturada" in codigo or "runners" in codigo,
           "e declara contra que saída os parsers foram escritos")
    checar("`playwright` e `tsc` NÃO estão aqui" in codigo,
           "e declara o que ela NÃO lê, em vez de fingir que lê")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("tools/ratchet/ratchet.py" in fluxo,
           "o FLUXO a declara entre o que é da máquina")
    checar("regravar a base por cima do vermelho de hoje" in fluxo.lower(),
           "e o FLUXO nomeia o gesto que a destrói")

    oito = " ".join((PACOTE / "skills" / "elcamargo-developer" / "SKILL.md"
                     ).read_text(encoding="utf-8").split())
    checar("ratchet.py gravar" in oito,
           "o step 8 grava a base")
    checar("antes da primeira linha" in oito,
           "e grava antes de escrever código")
    checar("$F gates <id>" in oito and "catraca:<portão>" in oito,
           "e confere pela catraca, via `gates`, antes de decidir que o vermelho é dele")
    _gates = (PACOTE / "tools" / "flow-state" / "flow_state.py").read_text(encoding="utf-8")
    checar('"conferir", "--base"' in _gates and '"--registrar", ident' in _gates,
           "e o `gates` chama a catraca com --registrar, sem depender de lembrar")

    qa = " ".join((PACOTE / "agents" / "elcamargo-quality-reviewer.md"
                   ).read_text(encoding="utf-8").split())
    checar("ratchet.py conferir" in qa,
           "a frente de qualidade passa o vermelho pela catraca")
    checar("`conhecido` não" in qa,
           "e não reporta passivo conhecido como achado desta entrega")
    checar("declare que não sabe" in qa,
           "e sem catraca declarada, diz que não sabe de quem é")

    exemplo = (PACOTE / "config.example.toml").read_text(encoding="utf-8")
    checar("[catraca]" in exemplo and "[catraca.formatos]" in exemplo,
           "o config de exemplo declara a catraca")


def as_duas_lentes_que_faltavam() -> None:
    """Gate verde e' requisito provado? E a prova veio do sistema ou do duble?

    Onze testes verdes provavam nada numa entrega real, achados por mutacao. E o
    portao visual anunciou `145 passaram, 0 falharam` com 152 ignorados na mesma
    linha -- as duas frases verdadeiras, e a decisao tomada na primeira.
    """
    hon = " ".join((PACOTE / "references" / "test-honesty.md"
                    ).read_text(encoding="utf-8").split())
    checar("Gate verde não é requisito provado" in hon,
           "a referência separa portão verde de requisito provado")
    checar("152 ignorados" in hon,
           "e traz o caso medido: verde com 152 casos sem rodar")
    checar("Tudo isto é procedência `estrutural`" in hon,
           "e declara que a lente inteira é estrutural")
    checar("A única exceção é `.only`" in hon,
           "com uma exceção nomeada, e só uma")
    checar("O teste de verdade é a mutação" in hon,
           "e aponta a mutação como a prova de verdade")
    checar("A calibração, que é a metade cara" in hon,
           "e registra a calibração, que é onde a lente se ganha ou se perde")
    checar("135 arquivos de teste, zero achados" in hon,
           "com o resultado depois de calibrada")
    checar("ainda precisa pegar" in hon,
           "e o risco oposto: lente cega parece lente limpa")

    ferramenta = PACOTE / "tools" / "honesty" / "honesty.py"
    checar(ferramenta.is_file(), "a ferramenta existe")
    codigo = ferramenta.read_text(encoding="utf-8")
    checar("TUDO AQUI É PROCEDÊNCIA `estrutural`" in codigo,
           "e ela mesma declara a própria procedência")
    checar("35 falsos" in codigo and "5 falsos" in codigo,
           "e guarda os erros de calibração no corpo, para ninguém desfazê-los")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("tools/honesty/honesty.py" in fluxo,
           "o FLUXO a declara entre o que é da máquina")
    checar("todos eram legítimos" in fluxo,
           "e o FLUXO guarda a lição sobre construir lente estrutural")

    oito = " ".join((PACOTE / "skills" / "elcamargo-developer" / "SKILL.md"
                     ).read_text(encoding="utf-8").split())
    checar("honesty.py testes" in oito,
           "o step 8 varre o que escreveu antes de entregar")

    qa = " ".join((PACOTE / "agents" / "elcamargo-quality-reviewer.md"
                   ).read_text(encoding="utf-8").split())
    checar("honesty.py testes" in qa,
           "a frente de qualidade roda a varredura")
    checar("honesty.py saida" in qa,
           "e conta quantos casos não rodaram")
    checar("Nada disso reprova sozinho" in qa,
           "e sabe que achado estrutural não reprova sozinho")


def perfis_de_acesso_tem_mecanismo() -> None:
    """"Entrar com ator sem a permissao" tem como acontecer, ou e' so' frase?

    Numa atividade real a resposta foi "nao ha' ator so'-leitura no banco, e
    criar um exigiria conta e senha" -- e a decisao de merge saiu com a
    autorizacao provada na tela, nao no 403.
    """
    ref = " ".join((PACOTE / "references" / "access-profiles.md"
                    ).read_text(encoding="utf-8").split())
    checar("Todo \"não pode\" vem acompanhado de um \"pode\"" in ref,
           "a referência exige o par pode/não-pode")
    checar("máquina de verde falso" in ref,
           "e diz por que a negação sozinha não é evidência")
    checar("Credenciais nunca entram no fluxo" in ref,
           "e que nenhuma senha entra no fluxo")
    checar("Esconder um botão não é recusar uma requisição" in ref,
           "e separa a camada da tela da camada da API")
    checar("Homologação fica de fora por padrão" in ref,
           "e mantém homologação fora por padrão")
    checar("Que o esperado estava certo" in ref,
           "e declara o que não prova")

    ferramenta = PACOTE / "tools" / "profiles" / "profiles.py"
    checar(ferramenta.is_file(), "a ferramenta existe")
    codigo = ferramenta.read_text(encoding="utf-8")
    checar("ARMADILHAS DE PORTUGUES" in codigo,
           "e guarda as colisões de padrão que já custaram falso positivo")
    checar("RE_DOCUMENTO" in codigo,
           "e sabe que documento descreve autorização sem decidir nada")

    exemplo = (PACOTE / "config.example.toml").read_text(encoding="utf-8")
    checar("[perfis]" in exemplo and "[perfis.atores." in exemplo,
           "o config de exemplo declara o mecanismo e os atores")
    checar("NENHUMA SENHA MORA AQUI" in exemplo,
           "e diz em letras garrafais que senha não mora ali")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("tools/profiles/profiles.py" in fluxo,
           "o FLUXO a declara entre o que é da máquina")
    checar("Nenhuma senha entra no fluxo" in fluxo,
           "e o FLUXO repete a regra da credencial")

    exec_ = " ".join((PACOTE / "agents" / "elcamargo-runtime-reviewer.md"
                      ).read_text(encoding="utf-8").split())
    checar("profiles.py superficie" in exec_,
           "a frente de execução descobre se a passada é obrigatória")
    checar("profiles.py conferir" in exec_,
           "e confere a própria tabela antes de entregar")
    checar("declare a dimensão como não coberta" in exec_,
           "e sem [perfis] declarado ela nomeia em vez de silenciar")

    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("profiles.py conferir" in nove,
           "o step 9 confere a passada por perfis ao consolidar")


def a_versao_e_uma_so() -> None:
    """`VERSION` e `plugin.json` dizem o mesmo, e o pacote sabe de onde vem?

    O `git push` NAO atualiza ninguem: e' o campo `version` que sinaliza. Isso
    ja' mordeu uma vez -- um teste leu a 1.0.0 instalada enquanto o repositorio
    tinha a correcao, e quase concluiu que o conserto nao funcionava.

    Duas declaracoes de versao que podem divergir sao pior que uma: quem sobe o
    `plugin.json` e esquece o `VERSION` publica uma versao que nao existe.
    """
    arquivo = PACOTE / "VERSION"
    checar(arquivo.is_file(), "o pacote declara `VERSION` na raiz")
    if not arquivo.is_file():
        return
    versao = arquivo.read_text(encoding="utf-8").strip()
    checar(bool(re.fullmatch(r"\d+\.\d+\.\d+", versao)),
           f"e ela tem a forma x.y.z ({versao})")

    manifesto = PACOTE / ".claude-plugin" / "plugin.json"
    if manifesto.is_file():
        import json
        do_plugin = json.loads(manifesto.read_text(encoding="utf-8")).get("version")
        checar(do_plugin == versao,
               f"e o plugin.json diz o mesmo (VERSION {versao}, plugin.json {do_plugin})")

    sys.path.insert(0, str(PACOTE / "tools" / "flow-state"))
    import config as C  # noqa: E402
    checar(C.versao(PACOTE) == versao, "e `config.versao()` lê a mesma")
    checar(hasattr(C, "copias_do_pacote"),
           "e o pacote sabe enumerar de onde ele pode estar vindo")

    doutor = " ".join((PACOTE / "tools" / "doctor" / "doctor.py"
                       ).read_text(encoding="utf-8").split())
    checar("de onde vem o pacote que está valendo" in doutor,
           "o doutor diz de onde vem o pacote")
    checar("versões DIFERENTES" in doutor,
           "e reprova quando há duas fontes divergindo")
    # Este lembrete mudou de lugar: era um MEDIO, virou nota de cabeçalho
    # quando uma fonte só deixou de ser achado. O que a regra protege é que
    # ele CONTINUE sendo dito — não onde é impresso.
    checar("claude plugin update elcamargo-ai-flow@elcamargo" in doutor,
           "e diz como atualizar quem instalou pelo plugin")
    checar("Uma fonte só é o estado CERTO, não um achado" in doutor,
           "e uma fonte só não é mais tratada como defeito")


def o_fluxo_tem_porta() -> None:
    """Da' para chamar o fluxo pelo nome, ou so' pelo nome de um step dele?

    A entrada era `elcamargo-board-git-management` -- o nome do servico do
    step 1, e nao do que a pessoa quer. Quem queria o fluxo chamava um step, e o
    resto era sorte.
    """
    porta = PACOTE / "skills" / "elcamargo-ai-flow" / "SKILL.md"
    checar(porta.is_file(), "a porta existe")
    if not porta.is_file():
        return
    texto = " ".join(porta.read_text(encoding="utf-8").split())
    checar("Você **não faz o trabalho**" in texto,
           "e ela declara que nao faz o trabalho")
    checar("um ou mais cards" in texto or "vários cards" in texto.lower()
           or "Vários cards" in texto,
           "sabe receber mais de um card")
    checar("Não decida por heurística" in texto,
           "e nao escolhe o card principal sozinho")
    checar("Não crie card" in texto or "não crie card" in texto,
           "e nunca cria card no board")
    checar("vira o primeiro cômodo" in texto,
           "e sabe por que uma porta que trabalha esvazia o fluxo")

    ancora = PACOTE / "tools" / "anchor" / "anchor.py"
    checar(ancora.is_file(), "a âncora existe")
    if ancora.is_file():
        codigo = ancora.read_text(encoding="utf-8")
        checar("Quem executa é o harness" in codigo,
               "e ela e' hook, nao instrucao")
        checar("Silêncio é o comportamento" in codigo,
               "e cala quando nao ha atividade")
    instalador = (PACOTE / "install.sh").read_text(encoding="utf-8")
    checar("UserPromptSubmit" in instalador,
           "e o install liga o hook")
    checar("não sobrescrever" in instalador or "NÃO sobrescrever" in instalador,
           "sem sobrescrever config de ninguem")


def a_conferencia_deixa_rastro() -> None:
    """A obrigacao acontece, ou so' esta' escrita?

    "Entrar com ator sem a permissao" viveu meses na frente de execucao e nunca
    aconteceu uma vez -- ninguem registrava, e portanto ninguem sabia.
    """
    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("A conferência mecânica deixa rastro" in fluxo,
           "o FLUXO declara a tabela de conferências")
    for veredicto in ("exigida", "ok", "falhou", "nao-coberta"):
        checar(f"`{veredicto}`" in fluxo, f"e nomeia o veredicto `{veredicto}`")
    checar("Quem descobre a obrigação é quem a registra" in fluxo,
           "e que quem descobre a obrigação é quem a grava")
    checar("desde que declarada" in fluxo,
           "e que dimensão não coberta passa quando é declarada")

    estado = (PACOTE / "tools" / "flow-state" / "flow_state.py"
              ).read_text(encoding="utf-8")
    checar("def cmd_conferencia" in estado, "o comando existe")
    checar("def pendencias" in estado, "e o `concluir` sabe o que está pendente")
    checar("Conferência mecânica pendente" in estado,
           "e recusa encerrar dizendo o que falta")

    for ferramenta in ("ratchet", "profiles"):
        codigo = (PACOTE / "tools" / ferramenta / f"{ferramenta}.py"
                  ).read_text(encoding="utf-8")
        checar("--registrar" in codigo,
               f"{ferramenta} aceita --registrar")
        checar("registrado em" in codigo,
               f"e {ferramenta} diz que registrou, em vez de gravar em silêncio")

    oito = " ".join((PACOTE / "skills" / "elcamargo-developer" / "SKILL.md"
                     ).read_text(encoding="utf-8").split())
    checar("grava `gate:<nome>`" in oito or "gate:<nome>" in oito,
           "o step 8 sabe que o `gates` grava cada portão na tabela")
    exec_ = " ".join((PACOTE / "agents" / "elcamargo-runtime-reviewer.md"
                      ).read_text(encoding="utf-8").split())
    checar("--registrar <id>" in exec_,
           "a frente de execução registra a superfície de autorização")
    nove = " ".join((PACOTE / "skills" / "elcamargo-development-reviewer"
                     / "SKILL.md").read_text(encoding="utf-8").split())
    checar("recusa encerrar com conferência exigida" in nove,
           "e o step 9 sabe que o `concluir` lê o rastro")


def o_config_e_conferido_no_projeto_novo() -> None:
    """O pacote sabe dizer se o config bate com o repositorio onde ele esta'?

    O install.sh copia o exemplo do projeto de origem e avisa para ajustar. Quem
    nao ajusta leva tudo junto, e nada falha na hora.
    """
    ferramenta = PACOTE / "tools" / "doctor" / "doctor.py"
    checar(ferramenta.is_file(), "o doutor existe")
    codigo = ferramenta.read_text(encoding="utf-8")
    checar("COMPARAR COM O EXEMPLO NÃO SERVE" in codigo,
           "e guarda por que comparar com o exemplo não serve")
    checar("A verificação que NÃO existe aqui" in codigo,
           "e a checagem de config morto que foi derrubada, com as duas granularidades")

    checar("[complementos]" in codigo,
           "e confere os complementos declarados")
    checar("APOSENTADA" in codigo,
           "inclusive o que aponta para skill em retired/, que era o buraco")

    # O slot que o exemplo declara precisa ter leitor. Uma chave sem leitor e'
    # config que parece ligada e nao esta' — e foi por nao haver conferencia
    # nenhuma aqui que o par `system_analyst` ficou dois projetos sem resolver.
    exemplo_txt = (PACOTE / "config.example.toml").read_text(encoding="utf-8")
    slots, dentro = [], False
    for linha in exemplo_txt.splitlines():
        if linha.startswith("["):
            dentro = linha.strip() == "[complementos]"
        elif dentro and "=" in linha and not linha.lstrip().startswith("#"):
            slots.append(linha.split("=", 1)[0].strip())
    for slot in slots:
        leitores = [p.parent.name for p in sorted((PACOTE / "skills").glob("*/SKILL.md"))
                    if f"complementos.{slot}" in p.read_text(encoding="utf-8")]
        checar(bool(leitores),
               f"o slot `{slot}` do exemplo tem quem o leia "
               f"({', '.join(leitores) or 'ninguem'})")

    instalador = (PACOTE / "install.sh").read_text(encoding="utf-8")
    checar("doctor.py" in instalador, "o install.sh roda o doutor")

    fluxo = " ".join((PACOTE / "FLOW.md").read_text(encoding="utf-8").split())
    checar("tools/doctor/doctor.py" in fluxo,
           "e o FLUXO o declara entre o que é da máquina")
    checar("antes da primeira atividade" in fluxo,
           "e diz quando rodar")

    exemplo = (PACOTE / "config.example.toml").read_text(encoding="utf-8")
    skill = ""
    for linha in exemplo.splitlines():
        if linha.startswith("skill = "):
            skill = linha.split("=", 1)[1].strip().strip('"')
            break
    # Nos DOIS lugares: as skills do pacote e as do projeto, ao lado dele. A
    # replicacao para outro repositorio pegou este mesmo defeito aqui, logo
    # depois de eu o consertar no doutor.
    pastas = (PACOTE / "skills", PACOTE.parent / "skills")
    checar(not skill or any((pasta / skill).is_dir() for pasta in pastas),
           f"a skill de Git do exemplo existe ({skill or 'vazia'})")

    # O EXEMPLO SAI VAZIO, e isto e' o teste de "instalavel em repositorio
    # vazio". Instalado num repo novo, o exemplo antigo produzia SEIS achados
    # altos e seis medios, todos valor do projeto de origem — e o teste do
    # pacote se declarava incoerente na propria instalacao limpa.
    #
    # A regra: valor que so' vale num projeto nao viaja no exemplo. O que viaja
    # e' o MECANISMO, com o comentario dizendo quando liga-lo.
    import tomllib as _toml
    ex = _toml.loads(exemplo)

    def _vazio(caminho: str):
        atual = ex
        for parte in caminho.split("."):
            if not isinstance(atual, dict) or parte not in atual:
                return True
            atual = atual[parte]
        return atual in ("", [], {}, None)

    especificos = ["projeto.nome", "projeto.descricao", "git.skill",
                   "docs.specs", "docs.adrs", "docs.fora_de_escopo",
                   "docs.classes_de_defeito", "producao.subir", "producao.escuta",
                   "producao.origem_publica", "producao.rotas",
                   "gates.lint", "gates.test", "gates.build",
                   "frontend.componentes", "frontend.tokens",
                   "perfis.comando", "perfis.injecao", "perfis.atores",
                   "complementos.system_analyst", "stack.linguagens",
                   "documento.cliente", "documento.produto", "documento.operador",
                   "documento.integrantes.cliente",
                   "documento.integrantes.fornecedor"]
    sujos = [c for c in especificos if not _vazio(c)]
    checar(not sujos,
           "o config.example sai vazio do que e' de um projeto so'"
           + (f" — preenchido: {', '.join(sujos)}" if sujos else ""))

    # Dado pessoal nao viaja num pacote feito para ser zipado e mandado adiante.
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", exemplo)
    checar(not emails,
           "e sem e-mail de pessoa nenhuma"
           + (f" — achei: {', '.join(sorted(set(emails)))}" if emails else ""))

    # O install.sh preenche o unico valor derivavel, para o projeto novo nao
    # comecar acusado por um nome que ninguem tinha como acertar antes.
    checar("basename \"$PROJETO\"" in instalador,
           "e o install.sh deriva `projeto.nome` do repositório")

    doutor = ferramenta.read_text(encoding="utf-8")
    checar("A_LIBERAR" in doutor,
           "o doutor lista o que ainda não está declarado, separado do que está errado")


def destinos_de_devolucao() -> None:
    """Os destinos que o FLUXO promete para cada portão humano existem?

    O FLUXO afirma que o portão 5 devolve ao step 3, o 7 ao step 6 e o 10 ao
    step 8. Se alguém renumerar os steps e esquecer o texto, a doutrina passa a
    mandar devolver para o lugar errado — e ninguém percebe, porque é prosa.
    """
    texto = (PACOTE / "FLOW.md").read_text(encoding="utf-8")
    checar("As duas devoluções" in texto,
           "FLUXO declara a diferença entre devolução por defeito e por escopo")
    for portao, destino in ((5, 3), (7, 6), (10, 8)):
        checar(STEPS.get(portao, {}).get("tipo") == "humano",
               f"step {portao} é portão humano")
        checar(STEPS.get(destino, {}).get("tipo") == "skill",
               f"o destino do portão {portao} — step {destino} — é step de skill")
    nove = (PACOTE / "skills" / "elcamargo-development-reviewer" / "SKILL.md"
            ).read_text(encoding="utf-8")
    checar("reinicia" in nove,
           "o step 9 sabe que o contador de voltas reinicia na devolução por escopo")
    oito = (PACOTE / "skills" / "elcamargo-developer" / "SKILL.md"
            ).read_text(encoding="utf-8")
    checar("volta para você" in oito.lower() or "voltou por" in oito.lower(),
           "o step 8 sabe distinguir por que o trabalho voltou")


def o_que_escapou_tem_onde_morar() -> None:
    """O registro de classes de defeito e o build atrás do host público estão ligados?

    Pedido do app em 30/09/2026, depois do Bug 1093: um redirect montado do
    `request.url` passou pelo step 9, invisível na máquina de quem revisa, e a
    revisão não tinha onde guardar que já errara assim três semanas antes. São
    prosa em várias pontas; este teste impede que uma ponta suma calada.
    """
    import tomllib as _toml
    ex = _toml.loads((PACOTE / "config.example.toml").read_text(encoding="utf-8"))
    checar("classes_de_defeito" in ex.get("docs", {}),
           "o config.example declara `docs.classes_de_defeito`")
    checar(set(ex.get("producao", {})) >= {"subir", "escuta", "origem_publica", "rotas"},
           "e o bloco `[producao]` inteiro")
    passo9 = (PACOTE / "skills/elcamargo-development-reviewer/SKILL.md").read_text(encoding="utf-8")
    passo8 = (PACOTE / "skills/elcamargo-developer/SKILL.md").read_text(encoding="utf-8")
    checar("references/defect-classes.md" in passo9,
           "o step 9 entrega o registro às frentes")
    checar("references/defect-classes.md" in passo8,
           "o step 8 acrescenta a classe")
    frentes = ["code-reviewer", "implemented-business-reviewer", "implemented-sdd-reviewer",
               "quality-reviewer", "runtime-reviewer", "security-reviewer"]
    sem = [f for f in frentes
           if "references/defect-classes.md" not in
           (PACOTE / f"agents/elcamargo-{f}.md").read_text(encoding="utf-8")]
    checar(not sem, "as seis frentes do 9 citam o registro"
           + (f" — faltam: {', '.join(sem)}" if sem else ""))
    execucao = (PACOTE / "agents/elcamargo-runtime-reviewer.md").read_text(encoding="utf-8")
    checar("public_origin.py" in execucao and "[producao]" in execucao,
           "a frente de execução roda o public_origin com `[producao]`, e diz o que fazer sem")
    checar((PACOTE / "tools/public-origin/public_origin.py").exists(),
           "e a ferramenta existe")


def a_perna_sombra_tem_quem_compare() -> None:
    """A perna sombra do step 9 está ligada de ponta a ponta?

    O desenho ficou de 04 a 30/09/2026 no experimento, sem ferramenta e sem
    step que o rodasse, e a política de modelo esperava por ele. São quatro
    pontas em prosa; este teste impede que uma suma calada.
    """
    import tomllib as _toml
    ex = _toml.loads((PACOTE / "config.example.toml").read_text(encoding="utf-8"))
    checar(ex.get("capacidades", {}).get("perna_sombra") == "off",
           "o config.example declara `capacidades.perna_sombra`, e nasce `off`")
    passo9 = (PACOTE / "skills/elcamargo-development-reviewer/SKILL.md").read_text(encoding="utf-8")
    checar("perna_sombra" in passo9 and "references/shadow-leg.md" in passo9,
           "o step 9 diz quando ligar e aponta o passo a passo")
    checar("shadow-leg.md" in (PACOTE / "references/model-policy.md").read_text(encoding="utf-8"),
           "a política de modelo aponta para a comparação")
    checar((PACOTE / "tools/shadow-leg/shadow_leg.py").exists()
           and (PACOTE / "references/shadow-leg.md").exists(),
           "a ferramenta e a referência existem")
    sys.path.insert(0, str(PACOTE / "tools/flow-state"))
    import capabilities as _cap
    checar("sonnet" in _cap.ACOES_DE_ESCOLHA.get("perna_sombra", ()),
           "o doutor aceita `perna_sombra = \"sonnet\"`, o valor que liga a ação")


def suite_nao_derruba_a_maquina() -> None:
    """Quem roda suíte de teste sabe limitar os workers?

    Em 01/10/2026 duas suítes jest em paralelo, sem `--maxWorkers`, somaram 18
    processos node de 1,6 GB e travaram a máquina. A regra é prosa em três
    lugares; este teste impede que um deles a perca.
    """
    import tomllib as _toml
    ex = _toml.loads((PACOTE / "config.example.toml").read_text(encoding="utf-8"))
    checar(ex.get("recursos", {}).get("max_workers_teste") == 2,
           "o config.example declara `recursos.max_workers_teste = 2`")
    checar((PACOTE / "references/test-resources.md").exists(), "a referência existe")
    for rel in ("agents/elcamargo-quality-reviewer.md",
                "agents/elcamargo-runtime-reviewer.md",
                "skills/elcamargo-developer/SKILL.md"):
        texto = (PACOTE / rel).read_text(encoding="utf-8")
        checar("references/test-resources.md" in texto and "--maxWorkers" in texto,
               f"{rel} limita os workers e aponta a referência")


def documento_nao_viaja() -> None:
    """CPF e CNPJ por extenso ficam fora de todo contexto do fluxo?

    Medido em 30/09/2026, no step 9 da 1052: o CPF de teste saiu da SDD de
    negócio, entrou no relatório da volta 1, e quem leu esse relatório teve TODA
    chamada barrada com o 403 do guardrail. Retomar não resolveu. A regra é
    prosa em dez agentes e três lugares de quem dispara; este teste impede que
    o próximo agente nasça sem ela.
    """
    print("\nDocumento não viaja: CPF e CNPJ fora do contexto")
    ref = "references/documents-in-context.md"
    checar((PACOTE / "tools" / "doc-mask" / "doc_mask.py").exists(),
           "o filtro `doc_mask.py` está no pacote")
    for agente in sorted((PACOTE / "agents").glob("*.md")):
        checar(f"$PACOTE/{ref}" in agente.read_text(encoding="utf-8"),
               f"{agente.stem} cita {ref}")
    runner = (PACOTE / "agents" / "elcamargo-step-runner.md").read_text(encoding="utf-8")
    checar("doc_mask.py conferir" in runner,
           "o step-runner confere o artefato antes de devolver")
    orq = (PACOTE / "references" / "orchestration.md").read_text(encoding="utf-8")
    checar("guardrail" in orq and "doc_mask.py" in orq and "devolucoes" in orq,
           "orchestration.md diz o que fazer com o 403, e ela chega aos steps 2, 3, 6 e 9")
    porta = (PACOTE / "skills" / "elcamargo-ai-flow" / "SKILL.md").read_text(encoding="utf-8")
    checar("403 do guardrail" in porta, "a porta sabe que o 403 não se retoma")
    guarda = (PACOTE / "tools" / "orchestrator-guard" / "guard.py").read_text(encoding="utf-8")
    checar("devolucoes" in guarda.split("REGRAS =", 1)[1].split('"""', 2)[1],
           "as regras da janela orquestradora trazem a recuperação do 403")


def main() -> int:
    print("Skills")
    skills = {}
    for d in sorted((PACOTE / "skills").glob("*/")):
        arquivo = d / "SKILL.md"
        if not arquivo.exists():
            checar(False, f"{d.name} tem SKILL.md")
            continue
        meta = front_matter(arquivo.read_text(encoding="utf-8"))
        # Claude Code resolve pela pasta; o fluxo se refere pelo `name`. Se os
        # dois divergirem, a skill existe mas o step não a encontra.
        checar(meta.get("name") == d.name,
               f"{d.name}: `name` bate com o diretório")
        checar(bool(meta.get("description")), f"{d.name}: tem description")
        skills[d.name] = meta

    print("\nAgents")
    agents = {}
    for arquivo in sorted((PACOTE / "agents").glob("*.md")):
        meta = front_matter(arquivo.read_text(encoding="utf-8"))
        esperado = arquivo.stem
        checar(meta.get("name") == esperado,
               f"{esperado}: `name` bate com o arquivo")
        checar(bool(meta.get("description")), f"{esperado}: tem description")
        checar("tools:" in arquivo.read_text(encoding="utf-8"),
               f"{esperado}: declara tools")
        # `model` é opcional: sem ele o agente herda de quem dispara. Com ele,
        # só um apelido que o Claude Code resolve.
        checar(meta.get("model", "inherit") in ("sonnet", "opus", "haiku", "inherit"),
               f"{esperado}: `model`, se declarado, é um apelido válido")
        agents[esperado] = meta

    print("\nCobertura do fluxo")
    for numero, dados in STEPS.items():
        if dados["tipo"] != "skill":
            continue
        checar(dados["nome"] in skills,
               f"step {numero} tem a skill {dados['nome']}")

    print("\nReferências entre componentes")
    # Todo subagente citado por uma skill precisa existir, senão o step 8 chama
    # o vazio no meio da revisão.
    citados = set()
    for nome, _ in skills.items():
        texto = (PACOTE / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
        citados |= set(re.findall(r"`(elcamargo-[a-z-]+)`", texto))
    conhecidos = set(skills) | set(agents)
    orfaos = sorted(c for c in citados if c not in conhecidos)
    checar(not orfaos, f"nenhuma referência órfã (achadas: {orfaos or 'nenhuma'})")

    usados = set()
    for nome in skills:
        texto = (PACOTE / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
        usados |= {a for a in agents if a in texto}
    nunca = sorted(set(agents) - usados)
    checar(not nunca, f"nenhum agent sem quem o chame (achados: {nunca or 'nenhum'})")

    print("\nReferências do ofício")
    # Uma skill que aponta para referência inexistente perde justamente o que a
    # torna boa fora do projeto de origem — e falha em silencio, lendo nada.
    compartilhadas = sorted((PACOTE / "references").glob("*.md"))
    checar(bool(compartilhadas),
           f"o manual do ofício existe ({len(compartilhadas)} referências)")
    citadas = set()
    for arquivo in [*(PACOTE / "skills").glob("*/SKILL.md"),
                    *(PACOTE / "agents").glob("*.md")]:
        texto = arquivo.read_text(encoding="utf-8")
        alvos = re.findall(r"`\$PACOTE/([^`]+\.md)`", texto)
        rotulo = (arquivo.parent.name if arquivo.name == "SKILL.md"
                  else arquivo.stem)
        for alvo in alvos:
            citadas.add(alvo)
            checar((PACOTE / alvo).exists(), f"{rotulo}: {alvo} existe")
    orfas = sorted(f"references/{r.name}" for r in compartilhadas
                   if f"references/{r.name}" not in citadas)
    checar(not orfas, f"nenhuma referência sem quem a leia ({orfas or 'ok'})")

    print("\nNumeração dos steps na prosa")
    # Renumerar o fluxo deixa referência velha espalhada pelo texto, e o texto
    # é o que a skill lê para decidir. Cada arquivo declara de que step é, no
    # título, e isso tem de bater com STEPS.
    por_nome = {d["nome"]: n for n, d in STEPS.items()}
    # DUAS SKILLS NAO SAO STEP, e cada uma por sua razao:
    #
    # `elcamargo-ai-flow` e' A PORTA -- resolve onde a atividade esta' e
    # entrega ao step certo. Exigir que ela declare um numero seria exigir que
    # a porta fosse um comodo.
    #
    # `elcamargo-config` acontece ANTES de qualquer step existir: ela prepara
    # o projeto para que os steps possam rodar. Numera-la a colocaria dentro do
    # fluxo que ela habilita.
    #
    # A lista e' fechada de proposito. Toda skill nova que nao for uma destas
    # duas continua tendo que dizer de que step e' -- senao a excecao vira
    # porta dos fundos, e a numeracao para de valer calada.
    FORA_DO_FLUXO = ("elcamargo-ai-flow", "elcamargo-config")
    for nome in [n for n in skills if n not in FORA_DO_FLUXO]:
        texto = (PACOTE / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
        titulo = re.search(r"^#\s*Step\s+(\d+)\s*·", texto, re.M)
        checar(titulo is not None, f"{nome}: título diz de que step é")
        if titulo:
            checar(int(titulo.group(1)) == por_nome.get(nome),
                   f"{nome}: título diz step {titulo.group(1)}, "
                   f"STEPS diz {por_nome.get(nome)}")

    # Nenhum arquivo pode citar step que não existe.
    for arquivo in [*(PACOTE / "skills").glob("*/SKILL.md"),
                    *(PACOTE / "agents").glob("*.md"),
                    PACOTE / "FLOW.md"]:
        citados = {int(n) for n in
                   re.findall(r"[Ss]tep (\d+)", arquivo.read_text(encoding="utf-8"))}
        inexistentes = sorted(citados - set(STEPS))
        checar(not inexistentes,
               f"{arquivo.parent.name if arquivo.name == 'SKILL.md' else arquivo.name}: "
               f"não cita step inexistente ({inexistentes or 'ok'})")

    print("\nTrilhas")
    for nome, steps in TRILHAS.items():
        checar(steps == sorted(steps), f"trilha {nome} está em ordem")
        checar(all(s in STEPS for s in steps),
               f"trilha {nome} só tem step existente")
        checar(steps[0] == 1, f"trilha {nome} começa no step 1")

    destinos_de_devolucao()
    pergunta_em_vez_de_pressuposto()
    a_prosa_nova_da_correcao()
    duas_voltas_em_todo_par()
    citacao_conferida_por_comando()
    portao_humano_pergunta()
    anexo_conferido_e_registrado()
    ler_figma_nao_depende_de_mcp()
    as_frentes_do_step9_nao_derrubam_a_maquina()
    texto_livre_vai_entre_aspas_simples()
    passagem_de_step_e_clique()
    step_tem_cargo_legivel()
    toda_skill_manda_ler_o_fluxo()
    contexto_de_agente_nao_e_lugar_de_guardar()
    venv_do_relatorio_nao_mora_em_tmp()
    o_instrumento_e_auditado()
    procedencia_esta_no_eixo_certo()
    todo_achado_tem_destino()
    a_catraca_separa_o_passivo()
    as_duas_lentes_que_faltavam()
    perfis_de_acesso_tem_mecanismo()
    a_conferencia_deixa_rastro()
    o_fluxo_tem_porta()
    a_versao_e_uma_so()
    o_config_e_conferido_no_projeto_novo()
    instalacao_completa()
    quem_dispara_espera()
    step4_sabe_escalar()
    frente_de_execucao()
    a_frente_de_execucao_nao_e_dispensada_pelo_diff()
    a_trilha_de_revisao_nao_toca_no_trabalho_alheio()
    matar_processo_e_por_pid_nunca_por_padrao()
    a_descoberta_do_caso_e_comando_e_mora_no_step_1()
    documento_nao_viaja()
    o_que_escapou_tem_onde_morar()
    a_perna_sombra_tem_quem_compare()
    suite_nao_derruba_a_maquina()

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1

    print("Tudo passou.")
    return 0


if __name__ == "__main__":
    # Windows: com a saída em pipe, `print` usa a codificação da região
    # (cp1252) e ESTOURA em `→`, que este pacote usa às pencas. Ver
    # `references/windows.md`.
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
