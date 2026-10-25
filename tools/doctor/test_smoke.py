#!/usr/bin/env python3
"""Fumaca de doctor.py — nos dois sentidos, e com o falso que ele ja' teve.

A primeira versao comparava o config com o `config.example.toml`. O exemplo
nasceu do projeto onde o pacote foi escrito, entao la' os valores sao iguais POR
SEREM CERTOS: a checagem acusava para sempre o unico projeto em que nao deveria
acusar nada. Virou caso negativo permanente.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctor as D  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def projeto(config: str, scripts: dict | None = None, nome_git: str = "meu-repo",
            skill_propria: str = "", lugar_padrao: bool = False,
            coletado: dict | None = None,
            atividades: int = 0) -> tuple[int, str]:
    """Monta um projeto de mentira e roda o doutor nele.

    `lugar_padrao=True` NAO passa `--config`: escreve o config onde o doutor
    tem que procurar sozinho, em `<raiz>/.agents/config.toml`. Existe porque
    todos os casos passavam `--config` explicito, entao o ramo que calcula o
    caminho padrao nunca corria -- e foi exatamente ali que ele quebrou quando
    o plugin virou a unica fonte do pacote.

    `skill_propria` cria uma skill do PROJETO em `.agents/skills/`. Antes esse
    caso lia a arvore real e se calava (`if irmas.is_dir()`) quando o pacote
    nao estava dentro de um `.agents` -- ou seja, a regressao que ele guarda
    ficava sem guarda justamente na topologia de plugin.
    """
    raiz = Path(tempfile.mkdtemp(prefix="doutor-"))
    subprocess.run(["git", "init", "-q"], cwd=raiz, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin",
                    f"https://exemplo/org/{nome_git}.git"], cwd=raiz, capture_output=True)
    if scripts is not None:
        (raiz / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    if skill_propria:
        d = raiz / ".agents" / "skills" / skill_propria
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {skill_propria}\n---\n", encoding="utf-8")
    if atividades:
        d = raiz / ".agents" / "atividades"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(atividades):
            (d / f"300{i}.md").write_text(f"---\nid: 300{i}\n---\n",
                                          encoding="utf-8")
    if coletado is not None:
        # `<raiz>/.agents/metricas/` e' onde o coletor grava. O doutor le'
        # daqui para dizer se a coleta ligada nunca rodou e se a ultima
        # rodada deixou atividade sem prova de atribuicao.
        d = raiz / ".agents" / "metrics"
        d.mkdir(parents=True, exist_ok=True)
        (d / "projeto.json").write_text(json.dumps(coletado), encoding="utf-8")
    if lugar_padrao:
        alvo = raiz / ".agents" / "config.toml"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(config, encoding="utf-8")
        passado = None
    else:
        alvo = raiz / "config.toml"
        alvo.write_text(config, encoding="utf-8")
        passado = str(alvo)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = D.cmd_conferir(Args(config=passado, raiz=str(raiz)))
    return codigo, buf.getvalue()


BASE = '[projeto]\nnome = "meu-repo"\n'


def main() -> int:
    print("\nO config que bate com o repositorio passa limpo")
    c, o = projeto(BASE)
    ok(c == 0 and "Nada declarado que não exista" in o, "sem achado nenhum", o)

    print("\nO falso que ele ja' teve: o projeto de origem")
    c, o = projeto(BASE, nome_git="meu-repo")
    ok("não foi ajustado" not in o,
       "nome igual ao do repositorio nao e' 'config nao ajustado'", o)
    c, o = projeto('[projeto]\nnome = "projeto-de-origem"\n', nome_git="repo-novo")
    ok("`[projeto] nome" in o and "repo-novo" in o,
       "mas nome de OUTRO projeto e' denunciado, com os dois lados", o)

    print("\nSkill de Git declarada que nao existe")
    c, o = projeto(BASE + '\n[git]\nskill = "nao-existe"\n')
    ok(c == 1 and "` não existe." in o, "reprova", o)
    ok("Disponíveis:" in o, "e lista as que existem", o)
    c, o = projeto(BASE + '\n[git]\nskill = "elcamargo-developer"\n')
    ok("` não existe." not in o, "skill do PACOTE passa", o)

    # A regressao que este caso existe para nunca mais deixar acontecer: o
    # projeto pode ter skills PROPRIAS ao lado do pacote, em `.agents/skills/`.
    # Uma versao anterior olhava so' dentro do pacote, declarou inexistente a
    # skill de Git do projeto -- que existia e estava em uso -- e o config foi
    # "corrigido" para apontar para outra.
    c, o = projeto(BASE + '\n[git]\nskill = "git-do-projeto"\n',
                   skill_propria="git-do-projeto")
    ok("` não existe." not in o,
       "e skill PROPRIA do projeto (.agents/skills/) tambem passa", o)

    print("\nO config sai de <raiz>/.agents/, e nao de onde o pacote mora")
    # Sem `--config`. Com o pacote instalado como plugin, `pacote.parent` e' a
    # pasta do cache: o doutor morria em "config não encontrado".
    c, o = projeto(BASE, lugar_padrao=True)
    ok(c == 0 and "não encontrado" not in o,
       "acha o config sozinho quando ninguem passa --config", o)

    print("\nGate apontando para script npm que nao existe")
    c, o = projeto(BASE + '\n[gates]\nlint = "npm run lint"\n', scripts={"test": "x"})
    ok(c == 1 and "não há esse script npm" in o, "reprova", o)
    c, o = projeto(BASE + '\n[gates]\nlint = "npm run lint"\n', scripts={"lint": "x"})
    ok("não há esse script" not in o, "e script que existe passa", o)
    c, o = projeto(BASE + '\n[gates]\nlint = "npm --prefix frontend run lint"\n',
                   scripts={"lint": "x"})
    ok("não há esse script" in o,
       "e `--prefix` de subprojeto inexistente tambem e' pego", o)

    print("\nCaminho declarado que nao existe")
    c, o = projeto(BASE + '\n[docs]\nspecs = "docs/specs"\n')
    ok("`docs.specs" in o and "não existe" in o, "denunciado como MEDIO", o)
    ok(c == 0, "e nao reprova sozinho — caminho some por muito motivo", o)

    print("\nCatraca incoerente com os gates")
    c, o = projeto(BASE + '\n[gates]\nlint = "npm run lint"\n'
                   '\n[catraca.formatos]\nvisual = "playwright"\n', scripts={"lint": "x"})
    ok("não tem gate correspondente" in o, "formato para portao que nao existe", o)
    ok(c == 1 and "formato desconhecido" in o,
       "e formato que a ferramenta nao le' reprova", o)
    c, o = projeto(BASE + '\n[gates]\nvisual = "npm run gate"\n'
                   '\n[catraca.formatos]\nvisual = "playwright"\n'
                   '\n[catraca.padroes]\nvisual = "x(?P<id>y)"\n', scripts={"gate": "x"})
    ok("formato desconhecido" not in o,
       "mas com regex declarado em [catraca.padroes] ele passa", o)

    print("\nAnexo por Azure sem org nem projeto")
    c, o = projeto(BASE + '\n[anexos]\nbackend = "azure"\n')
    ok(c == 1 and o.count("vazio — todo anexo vai falhar") == 2,
       "as duas chaves vazias sao denunciadas", o)
    c, o = projeto(BASE + '\n[anexos]\nbackend = "manual"\n')
    ok("todo anexo vai falhar" not in o, "e backend manual nao exige org", o)

    print("\nAtores de perfil sem comando que os assuma")
    c, o = projeto(BASE + '\n[perfis.atores.leitor]\nchaves = ["x.read"]\n')
    ok(c == 1 and "sem `[perfis] comando`" in o,
       "declarar ator sem mecanismo de assumir e' achado", o)

    print("\nDuas fontes do pacote: a que vence, e a divergencia")

    import sys as _sys

    _sys.path.insert(0, str(Path(D.__file__).resolve().parents[1] / "flow-state"))

    import config as _C  # noqa: E402


    _t = Path(tempfile.mkdtemp(prefix="fontes-"))

    _copia = _t / ".agents" / "elcamargo-flow"

    _copia.mkdir(parents=True)

    (_copia / "VERSION").write_text("1.0.2\n", encoding="utf-8")

    _home = _t / "home"

    _cache = _home / ".claude" / "plugins" / "cache" / "pm" / "elcamargo-ai-flow" / "1.1.0"

    _cache.mkdir(parents=True)

    (_cache / "VERSION").write_text("1.1.0\n", encoding="utf-8")


    _orig = Path.home

    Path.home = staticmethod(lambda: _home)

    try:

        _achadas = _C.copias_do_pacote(_t)

    finally:

        Path.home = _orig


    ok(len(_achadas) == 2, "acha a copia e o plugin", str(_achadas))

    ok(_achadas[0][0] == "cópia em .agents",

       "e a copia vem PRIMEIRO -- e' ela que vence na resolucao das skills",

       str(_achadas))

    ok([v for _, _, v in _achadas] == ["1.0.2", "1.1.0"],

       "com as duas versoes lidas do arquivo VERSION", str(_achadas))


    ok(_C.versao(_copia) == "1.0.2", "versao() le' do VERSION")

    ok(_C.versao(_t / "nao-existe") == "?",

       "e devolve `?` sem explodir quando o arquivo nao esta' la'")


    # `claude plugin update` NAO apaga a versao anterior: o cache guarda todas
    # lado a lado. Listar as antigas fazia o doutor gritar `[ALTO] versoes
    # DIFERENTES` logo depois de uma atualizacao BEM-SUCEDIDA. Medido de
    # verdade, no minuto seguinte ao push do 1.0.4.
    for _v in ("1.0.9", "1.0.10"):
        _d = _home / ".claude" / "plugins" / "cache" / "pm" / "elcamargo-ai-flow" / _v
        _d.mkdir(parents=True, exist_ok=True)
        (_d / "VERSION").write_text(_v + "\n", encoding="utf-8")
    Path.home = staticmethod(lambda: _home)
    try:
        _muitas = _C.copias_do_pacote(_t)
    finally:
        Path.home = _orig
    _plugins = [c for c in _muitas if c[0] == "plugin instalado"]
    ok(len(_plugins) == 1,
       "cache com 3 versoes lista UMA -- versao velha nao e' segunda fonte",
       str(_muitas))
    ok(_plugins and _plugins[0][2] == "1.1.0",
       "e e' a mais nova, a mesma que as skills resolvem", str(_muitas))

    _so_cache = Path(tempfile.mkdtemp(prefix="ordem-"))
    _h2 = _so_cache / "home"
    for _v in ("1.0.9", "1.0.10"):
        _d = _h2 / ".claude" / "plugins" / "cache" / "pm" / "elcamargo-ai-flow" / _v
        _d.mkdir(parents=True, exist_ok=True)
        (_d / "VERSION").write_text(_v + "\n", encoding="utf-8")
    Path.home = staticmethod(lambda: _h2)
    try:
        _ordem = _C.copias_do_pacote(_so_cache)
    finally:
        Path.home = _orig
    ok(_ordem and _ordem[0][2] == "1.0.10",
       "e 1.0.10 vence 1.0.9 -- ordem de versao, nao alfabetica", str(_ordem))
    shutil.rmtree(_so_cache, ignore_errors=True)

    shutil.rmtree(_t, ignore_errors=True)


    print("\n[metricas]: reprova o que encolhe o numero, informa o que muda")
    # A assimetria nao e' gosto: ela esta' escrita no proprio coletor --
    # "subestimar a hora humana INFLA o ganho da ferramenta: e' o erro que
    # nao se pode cometer". Entao o que faz o numero sair MENOR reprova; o
    # que faz sair DIFERENTE informa.
    c, o = projeto(BASE + '\n[metricas]\nteto_leitura_min = 0\n')
    ok(c == 1 and "teto" in o, "teto zerado reprova", o)
    ok("MENOR" in o, "e diz por que: a hora humana sai menor do que e'", o)

    c, o = projeto(BASE + '\n[metricas]\nreentrada_min = -1\n')
    ok(c == 1, "reentrada negativa reprova -- ela SUBTRAI hora humana", o)

    # Reentrada 0 e' diferente de teto 0: o teto corta uma medida TOMADA, a
    # reentrada declina de MODELAR um custo. Declinar do modelo e' escolha
    # de contabilidade; descartar medida nao e'.
    c, o = projeto(BASE + '\n[metricas]\nreentrada_min = 0\n')
    ok(c == 0 and "reentrada" in o, "reentrada 0 informa, nao reprova", o)

    c, o = projeto(BASE + '\n[metricas]\nteto_leitura_min = "dez"\n')
    ok(c == 1 and "int()" in o,
       "valor nao numerico reprova: a coleta morre e o gancho engole", o)

    c, o = projeto(BASE + '\n[metricas.precos]\nsaida = 0.0\n')
    ok(c == 1 and "MENOR" in o, "preco zerado reprova -- US$ 75 viram US$ 0", o)

    # O falso permanente que o caso do projeto de origem guarda contra: quem
    # roda outro modelo tem preco legitimamente diferente da tabela do pacote.
    c, o = projeto(BASE + '\n[metricas.precos]\nsaida = 30.0\n')
    ok(c == 0, "preco divergente do padrao NAO reprova", o)
    ok("nao sabe qual modelo" in o or "não sabe qual modelo" in o,
       "e diz por que nao pode reprovar", o)

    c, o = projeto(BASE + '\n[metricas.precos]\n"saída" = 30.0\n')
    ok(c == 0 and "IGNORADA" in o,
       "chave de preco com typo e' denunciada como ignorada, sem reprovar", o)

    print("\nEstado da coleta: nunca rodou, e o que ficou sem atribuicao")
    c, o = projeto(BASE, atividades=2, coletado={"nao_atribuidas": []})
    ok("nunca rodou" not in o, "coleta que ja' rodou nao e' acusada", o)
    c, o = projeto(BASE, atividades=2)
    ok("nunca rodou" in o, "ligada, com atividade, e sem nada gravado", o)
    # Projeto recem-instalado nao tem atividade: acusar ali seria ruido
    # em todo primeiro doutor, e tiraria a saida limpa de quem acabou
    # de instalar -- que e' justamente o primeiro caso deste arquivo.
    c, o = projeto(BASE)
    ok("nunca rodou" not in o, "mas projeto sem atividade nenhuma nao e' acusado", o)
    c, o = projeto(BASE + '\n[metricas]\nligado = false\n', atividades=2)
    ok("nunca rodou" not in o, "e desligada nao e' acusada de nao ter rodado", o)

    c, o = projeto(BASE, atividades=2,
                   coletado={"nao_atribuidas": ["1066", "1069"]})
    ok(c == 0 and "1066" in o and "1069" in o,
       "as nao atribuidas da ultima coleta sao nomeadas", o)
    ok("DE MENOS" in o, "e o doutor diz que o total esta' de menos", o)

    print("\nO formato `lighthouse` e' conhecido -- portao de tela")
    c, o = projeto(BASE + '\n[gates]\nqualidade_de_tela = "npm run gate:tela"\n'
                   '\n[catraca.formatos]\nqualidade_de_tela = "lighthouse"\n',
                   scripts={"gate:tela": "x"})
    ok("formato desconhecido" not in o,
       "catraca declarada em lighthouse nao e' acusada de formato desconhecido", o)
    ok(c == 0, "e o config passa limpo", o)

    print("\nOrcamento: o que reprova, e a incoerencia que o deixa inerte")
    c, o = projeto(BASE + '\n[metricas]\norcamento_usd = 1500.0\n')
    ok(c == 0 and "orcamento_usd" not in o and "orcamento" not in o.split("Ainda")[0],
       "orcamento bem declarado nao produz achado", o)

    c, o = projeto(BASE + '\n[metricas]\norcamento_usd = "mil"\n')
    ok(c == 1 and "nao confere nada" in o.replace("ã", "a").replace("é", "e"),
       "valor nao numerico reprova: o teto existe no config e nao vale nada", o)

    # Zero nao pode ser honrado: teto de US$ 0,00 barraria todo `avancar` para
    # sempre. Ele desliga -- e a declaracao parece dizer o contrario.
    c, o = projeto(BASE + '\n[metricas]\norcamento_usd = 0\n')
    ok(c == 0 and "DESLIGADO" in o, "zero informa que esta' desligado, sem reprovar", o)

    # A mesma familia do ator de perfil sem comando que o assuma: controle
    # declarado sem mecanismo que o execute.
    c, o = projeto(BASE + '\n[metricas]\nligado = false\norcamento_usd = 1500.0\n')
    ok(c == 1 and "INERTE" in o,
       "orcamento com a coleta DESLIGADA reprova: nada coleta, o teto nunca dispara", o)

    print("\n`metricas.ligado` entra na lista do que ainda nao foi declarado")
    c, o = projeto(BASE)
    ok("metricas.ligado" in o, "aparece em `ainda nao declarado`", o)
    ok("metricas.orcamento_usd" in o, "e o orcamento tambem", o)
    ok("ligado = false" in o, "com a forma de desligar escrita", o)
    c, o = projeto(BASE + '\n[metricas]\nligado = true\n')
    ok("metricas.ligado" not in o.split("Ainda não declarado")[-1],
       "e sai da lista quando declarado", o)


    print("\nO token do Figma: o unico pre-requisito da leitura, e nao era conferido")
    # Em 08/09/2026 uma frente parou o step 6 "por falta de MCP da Figma".
    # Leitura nao usa MCP, usa este token -- e nada checava se ele existia.
    _tmp = Path(tempfile.mkdtemp(prefix="tok-"))
    _real = D.caminho_do_token_figma
    try:
        D.caminho_do_token_figma = lambda pacote: _tmp / "figma-token"
        c, o = projeto(BASE)
        ok("token do Figma" in o and "MEDIO" in o,
           "sem token, acusa como medio e diz que ler NAO usa MCP", o)
        ok("figma.py" in o, "e nomeia a ferramenta que le", o)

        c, o = projeto(BASE + '\n[capacidades]\nfigma_leitura = "off"\n')
        ok("token do Figma" not in o,
           "com `figma_leitura = off` cala: nao ter token ali e' coerente", o)

        c, o = projeto(BASE + '\n[capacidades]\nfigma_leitura = "on"\n')
        ok("ALTO" in o and "token do Figma" in o,
           "com `on` vira ALTO: a politica exige e a maquina nao consegue", o)

        alvo = _tmp / "figma-token"
        alvo.write_text("tok", encoding="utf-8")
        alvo.chmod(0o644)
        c, o = projeto(BASE)
        ok("ALTO" in o and "permissão 644" in o,
           "token legivel por outros e' ALTO: a ferramenta o recusa", o)

        alvo.chmod(0o600)
        c, o = projeto(BASE)
        ok("token do Figma" not in o, "e com token instalado e 600, cala", o)

        alvo.write_text("   \n", encoding="utf-8")
        c, o = projeto(BASE)
        ok("vazio" in o, "token vazio nao passa por instalado", o)
    finally:
        D.caminho_do_token_figma = _real
        import shutil as _sh
        _sh.rmtree(_tmp, ignore_errors=True)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaca de doctor.py: tudo verde.")
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
