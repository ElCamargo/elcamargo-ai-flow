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
    checar("Quem anexa, e quem não anexa" in fluxo,
           "e declara quais steps anexam, pelo critério de quem lê")

    anexam = ["elcamargo-business-analysis-reviewer", "elcamargo-system-analyst",
              "elcamargo-ux-reviewer", "elcamargo-development-reviewer"]
    for nome in anexam:
        texto = " ".join((PACOTE / "skills" / nome / "SKILL.md"
                          ).read_text(encoding="utf-8").split())
        checar("attach.py --conferir" in texto,
               f"{nome.replace('elcamargo-', '')} confere que o anexo subiu")
        checar("--tipo anexo" in texto,
               f"e registra o anexo no estado da atividade")

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
                       capture_output=True, text=True)
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
    checar("ratchet.py conferir" in oito,
           "e confere antes de decidir que o vermelho é dele")

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

    A entrada era `elcamargo-activity-management` -- o nome do servico do
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
    checar("`--registrar` não é opcional" in oito,
           "o step 8 sabe que --registrar não é opcional")
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
    # A PORTA NAO E' UM STEP. `elcamargo-ai-flow` resolve onde a atividade
    # esta' e entrega ao step certo; exigir que ela declare um numero seria
    # exigir que a porta fosse um comodo. Toda skill que NAO for a porta
    # continua tendo que dizer de que step e'.
    for nome in [n for n in skills if n != "elcamargo-ai-flow"]:
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

    print()
    if falhas:
        print(f"{len(falhas)} falha(s):")
        for f in falhas:
            print(f"  - {f}")
        return 1

    print("Tudo passou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
