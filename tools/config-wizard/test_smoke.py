#!/usr/bin/env python3
"""Fumaça do configure.py — o escritor de config que não pode perder comentário.

O `config.example.toml` tem 353 linhas, e a maior parte delas é **comentário
que explica o que a chave faz e quando vale a pena ligá-la**. Um escritor que
regrave o arquivo a partir do dicionário lido joga isso fora, e o próximo
humano que abrir o config encontra 48 chaves sem explicação nenhuma.

Por isso a escrita é cirurgia de linha, e por isso o primeiro bloco de testes
aqui é sobre preservar comentário — não sobre gravar valor.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import configure as C  # noqa: E402

PACOTE = Path(__file__).resolve().parents[2]
EXEMPLO = PACOTE / "config.example.toml"

falhas: list[str] = []
TEMPORARIOS: list[Path] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


def cenario() -> Path:
    raiz = Path(tempfile.mkdtemp(prefix="config-")).resolve()
    TEMPORARIOS.append(raiz)
    (raiz / ".agents").mkdir(parents=True)
    return raiz


def git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(raiz), *args],
                   capture_output=True, check=False)


def main() -> int:
    print("\nSerializar valor: o subconjunto de TOML que este config usa")
    ok(C.como_toml("abc") == '"abc"', "texto sai entre aspas")
    ok(C.como_toml('com "aspas"') == r'"com \"aspas\""', "aspas internas escapam",
       C.como_toml('com "aspas"'))
    ok(C.como_toml(True) == "true" and C.como_toml(False) == "false",
       "booleano em minuscula, como TOML manda")
    ok(C.como_toml(10) == "10", "inteiro sem ponto")
    ok(C.como_toml(1.5) == "1.5", "decimal com ponto")
    ok(C.como_toml(["a", "b"]) == '["a", "b"]', "lista de texto",
       C.como_toml(["a", "b"]))
    ok(C.como_toml([200.0, 30.0]) == "[200.0, 30.0]", "lista de numero",
       C.como_toml([200.0, 30.0]))
    ok(C.como_toml([]) == "[]", "lista vazia")

    print("\nO `0` e o `false` declarados NAO viram vazio")
    # Mesma armadilha que o coletor ja' documentou: `int(valor or padrao)` faz
    # o zero declarado virar o padrao. Aqui o risco e' o escritor pular a
    # chave achando que "nao tem valor".
    ok(C.como_toml(0) == "0", "zero e' valor, nao ausencia")
    ok(C.como_toml("") == '""', "texto vazio e' valor, nao ausencia")

    print("\nCriar o config a partir do exemplo preserva TODOS os comentarios")
    raiz = cenario()
    C.cmd_iniciar(C.Args(raiz=str(raiz)))
    alvo = raiz / ".agents" / "config.toml"
    ok(alvo.exists(), "o arquivo nasce")
    origem = EXEMPLO.read_text(encoding="utf-8")
    copia = alvo.read_text(encoding="utf-8")
    ok(copia.count("#") == origem.count("#"),
       "nenhum comentario se perde na criacao",
       f"exemplo={origem.count('#')} copia={copia.count('#')}")
    ok(copia == origem, "e' copia literal -- nada e' reescrito")

    print("\nEscrever uma chave nao toca em nenhuma outra linha")
    antes = alvo.read_text(encoding="utf-8").splitlines()
    C.cmd_definir(C.Args(raiz=str(raiz), chave="projeto.nome", valor="meu-repo"))
    depois = alvo.read_text(encoding="utf-8").splitlines()
    ok(len(antes) == len(depois), "o arquivo nao muda de tamanho",
       f"{len(antes)} -> {len(depois)}")
    diferentes = [i for i, (a, b) in enumerate(zip(antes, depois)) if a != b]
    ok(len(diferentes) == 1, "exatamente UMA linha mudou", str(diferentes))
    ok(depois[diferentes[0]].strip() == 'nome = "meu-repo"',
       "e e' a linha da chave", depois[diferentes[0]])

    print("\nA chave certa dentro da SECAO certa")
    # `org` existe em [anexos.azure]; `nome` existe em [projeto] e em
    # [documento.fornecedor]. Procurar so' pelo nome da chave escreveria na
    # primeira que aparecesse -- e a primeira nao e' a pedida.
    C.cmd_definir(C.Args(raiz=str(raiz), chave="documento.fornecedor.nome",
                         valor="Outra Empresa"))
    dados = C.ler(raiz)
    ok(dados["projeto"]["nome"] == "meu-repo",
       "o [projeto] nome continua o que era", str(dados["projeto"]["nome"]))
    ok(dados["documento"]["fornecedor"]["nome"] == "Outra Empresa",
       "e o do fornecedor mudou sozinho",
       str(dados["documento"]["fornecedor"]["nome"]))

    print("\nChave comentada no exemplo e' DESCOMENTADA, nao duplicada")
    # `orcamento_usd` e `assinaturas_usd_mes` vivem comentadas no exemplo, com
    # a explicacao em cima. Inserir uma linha nova deixaria a explicacao orfa'
    # e a chave sem contexto.
    C.cmd_definir(C.Args(raiz=str(raiz), chave="metricas.orcamento_usd", valor=50.0))
    # A palavra aparece tambem na PROSA que explica a chave, de proposito. O
    # que nao pode duplicar e' a LINHA de declaracao.
    linhas_da_chave = [l for l in alvo.read_text(encoding="utf-8").splitlines()
                       if l.strip().startswith("orcamento_usd")]
    ok(len(linhas_da_chave) == 1,
       "a linha da chave aparece UMA vez -- a comentada foi reaproveitada",
       str(linhas_da_chave))
    ok(C.ler(raiz)["metricas"]["orcamento_usd"] == 50.0,
       "e o valor e' lido de volta")

    print("\nChave que nao existe no exemplo e' RECUSADA, nao inventada")
    # Config que aceita qualquer chave e' config que nao faz o que diz: quem
    # digitou errado fica achando que declarou.
    erro = ""
    try:
        C.cmd_definir(C.Args(raiz=str(raiz), chave="projeto.nomee", valor="x"))
    except C.ConfigError as exc:
        erro = str(exc)
    ok("nomee" in erro, "o erro nomeia a chave recusada", erro[:120])
    ok("projeto.nome" in erro, "e sugere a mais parecida", erro[:200])

    print("\nDetectar: o que o repositorio responde sozinho")
    raiz2 = cenario()
    git(raiz2, "init", "-q", "-b", "main")
    git(raiz2, "remote", "add", "origin",
        "https://github.com/acme/minha-app.git")
    (raiz2 / "package.json").write_text(json.dumps({
        "name": "minha-app",
        "scripts": {"lint": "eslint .", "test": "vitest run",
                    "build": "next build", "dev": "next dev"},
        "dependencies": {"next": "15.0.0", "react": "19.0.0"},
    }), encoding="utf-8")
    d = C.detectar(raiz2)
    ok(d["board"]["tipo"] == "github",
       "o host do remote diz o board", str(d["board"]))
    ok(d["board"]["org"] == "acme" and d["board"]["repo"] == "minha-app",
       "org e repo saem da propria URL", str(d["board"]))
    ok(d["gates"]["lint"] == "npm run lint", "o gate de lint sai do package.json",
       str(d["gates"]))
    ok(d["gates"]["test"] == "npm run test", "o de teste tambem")
    ok(d["gates"]["build"] == "npm run build", "e o de build")
    ok("dev" not in json.dumps(d["gates"]),
       "e `dev` NAO vira gate -- servidor nao e' conferencia", str(d["gates"]))
    ok("typescript" in d["stack"]["frameworks"] + d["stack"]["linguagens"]
       or "next" in json.dumps(d["stack"]).lower(),
       "a stack sai das dependencias", json.dumps(d["stack"]))

    print("\nMonorepo: a raiz so' orquestra, e a stack mora um nivel abaixo")
    # Medido contra o acme-backoffice: o `package.json` da raiz tem
    # `scripts` e ZERO dependencia -- ele chama os subprojetos. Procurar stack
    # so' na raiz devolvia linguagem e framework vazios num repo TypeScript
    # inteiro, e o /config passaria a perguntar o que estava ali do lado.
    raizM = cenario()
    git(raizM, "init", "-q", "-b", "main")
    (raizM / "package.json").write_text(json.dumps({
        "name": "mono", "private": True,
        "scripts": {"lint": "npm -w frontend run lint"},
    }), encoding="utf-8")
    (raizM / "frontend").mkdir()
    (raizM / "frontend" / "package.json").write_text(json.dumps({
        "name": "frontend",
        "dependencies": {"next": "15.0.0"},
        "devDependencies": {"typescript": "5.6.0"},
    }), encoding="utf-8")
    (raizM / "frontend" / "components").mkdir()
    d = C.detectar(raizM)
    ok("typescript" in d["stack"]["linguagens"],
       "a linguagem sai do manifesto do subprojeto", json.dumps(d["stack"]))
    ok("next" in d["stack"]["frameworks"],
       "e os frameworks tambem", json.dumps(d["stack"]))
    ok(d["frontend"].get("componentes") == "frontend/components",
       "e a pasta de componentes e' achada onde ela esta' de verdade",
       json.dumps(d["frontend"]))
    ok(d["gates"]["lint"] == "npm run lint",
       "o gate continua saindo da RAIZ -- e' de la' que se roda", str(d["gates"]))

    print("\nDetectar Azure pelo host, e nao pelo nome do repositorio")
    raiz3 = cenario()
    git(raiz3, "init", "-q", "-b", "main")
    git(raiz3, "remote", "add", "origin",
        "https://acme@dev.azure.com/acme/Projeto/_git/github-clone")
    d = C.detectar(raiz3)
    ok(d["board"]["tipo"] == "azure",
       "um repo chamado `github-clone` no Azure ainda e' Azure", str(d["board"]))
    ok(d["board"]["org"] == "acme" and d["board"]["projeto"] == "Projeto",
       "org e projeto saem do caminho da URL", str(d["board"]))

    print("\nSem remote, ele NAO adivinha")
    raiz4 = cenario()
    git(raiz4, "init", "-q", "-b", "main")
    d = C.detectar(raiz4)
    ok(d["board"]["tipo"] is None,
       "board indeterminado fica None, e vira pergunta", str(d["board"]))

    print("\nEstado: o que falta, e o que trava por faltar")
    raiz5 = cenario()
    C.cmd_iniciar(C.Args(raiz=str(raiz5)))
    e = C.estado(raiz5)
    ok(e["blocos"], "ha' blocos")
    primeiro = e["blocos"][0]
    ok(primeiro["ordem"] == 1, "o primeiro bloco e' o primeiro a travar")
    ok(any(b["faltando"] for b in e["blocos"]),
       "num config recem-criado ha' o que faltar")
    ok(all("trava" in b for b in e["blocos"]),
       "todo bloco diz o que trava sem ele")

    print("\nChave COM padrao no exemplo nao e' 'falta' -- e' 'no padrao'")
    # `metricas.ligado = true` e `teto_leitura_min = 10` trazem padrao no
    # exemplo: nao declara-los e' legitimo, e o fluxo roda igual. Chamar isso
    # de falta e' o mesmo defeito de rotulo do prazo que dizia "ate' a entrega"
    # numa atividade que nao entregou -- a palavra promete o que o dado nao diz.
    # Config MINIMO, e nao a copia do exemplo: depois do `iniciar` o arquivo e'
    # copia literal, e ai' `ligado = true` esta' DECLARADO -- o caso que este
    # bloco existe para exercitar nem aparece.
    raiz6 = cenario()
    (raiz6 / ".agents" / "config.toml").write_text(
        '[projeto]\nnome = ""\n\n[metricas]\n', encoding="utf-8")
    e = C.estado(raiz6)
    m = next(b for b in e["blocos"] if b["bloco"] == "metricas")
    ok("metricas.ligado" in m["no_padrao"],
       "chave com padrao cai em `no_padrao`", str(m["no_padrao"])[:120])
    ok("metricas.ligado" not in m["faltando"],
       "e NAO aparece como faltando", str(m["faltando"])[:120])
    proj = next(b for b in e["blocos"] if b["bloco"] == "projeto")
    ok("projeto.nome" in proj["faltando"],
       "chave vazia no exemplo continua sendo falta de verdade",
       str(proj["faltando"]))
    ok(all("nada trava" in b["trava"] or b["faltando"] or b["no_padrao"] or b["declaradas"]
           for b in e["blocos"]), "todo bloco classifica todas as suas chaves")

    print("\nRepo sem config e' ESTADO, nao erro -- a skill le' o modo daqui")
    # Achado rodando a entrevista de verdade: a skill manda descobrir o modo
    # com `estado`, e o modo "repositorio novo" chegava como [erro] no stderr.
    raizN = cenario()
    e = C.estado(raizN)
    ok(e.get("configurado") is False,
       "estado responde `configurado: false` em vez de estourar", str(e)[:120])
    ok(e.get("proximo"), "e diz qual e' o proximo comando", str(e.get("proximo")))

    print("\nA trava so' aparece quando falta chave ESSENCIAL")
    # Achado no mesmo teste: o bloco 6 dizia "sem comando de lint, teste e
    # build o step 9 nao tem o que rodar" -- com os tres JA' declarados. So'
    # faltavam `visual` e `qualidade_de_tela`, que sao outra conversa.
    # E' a mesma classe do rotulo do prazo: a mensagem promete o que o dado
    # nao diz, e quem le' corre atras' do alarme errado.
    raizE = cenario()
    C.cmd_iniciar(C.Args(raiz=str(raizE)))
    for c, v in (("gates.lint", "npm run lint"), ("gates.test", "npm run test"),
                 ("gates.build", "npm run build")):
        C.cmd_definir(C.Args(raiz=str(raizE), chave=c, valor=v))
    g = next(b for b in C.estado(raizE)["blocos"] if b["bloco"] == "gates")
    ok(not g["faltando"],
       "com os tres essenciais declarados, nao falta nada essencial",
       str(g["faltando"]))
    ok("gates.visual" in g["opcional"],
       "o que sobra e' OPCIONAL, e nao falta", str(g["opcional"]))
    ok(not g.get("mostra_trava"),
       "e a trava NAO e' impressa: ela nao e' sobre o que sobrou")

    print("\nBloco onde nada trava nao pode dizer `falta`")
    cap = next(b for b in C.estado(raizE)["blocos"] if b["bloco"] == "capacidades")
    ok(not cap["faltando"],
       "capacidade opcional nao e' falta -- `nada trava` e `falta` se "
       "contradiziam no mesmo bloco", str(cap["faltando"]))

    print("\nTODA chave do exemplo esta' coberta pelo roteiro")
    # E' o teste que impede a deriva: alguem acrescenta chave no exemplo e
    # esquece de dizer como pergunta-la. Sem isto, o /config envelhece calado.
    do_exemplo = set(C.chaves_do_exemplo())
    do_roteiro = set(C.chaves_do_roteiro())
    orfas = sorted(do_exemplo - do_roteiro)
    ok(not orfas,
       "nenhuma chave do exemplo ficou fora do roteiro",
       f"{len(orfas)} orfa(s): {orfas[:8]}")
    fantasmas = sorted(do_roteiro - do_exemplo)
    ok(not fantasmas,
       "e o roteiro nao pergunta chave que nao existe",
       f"{len(fantasmas)}: {fantasmas[:8]}")

    for d in TEMPORARIOS:
        shutil.rmtree(d, ignore_errors=True)

    print("\nO `definir` grava TIPO, e nao texto -- o interruptor tem que desligar")
    # Medido ao ligar a publicacao no backoffice: `definir ... true` escrevia
    # `= "true"`, uma STRING. Em Python string nao vazia e' verdadeira, entao
    # `"false"` tambem seria -- o desligar ligava, e ninguem descobriria por
    # tentativa: descobriria por um `docs/` que continua sendo regravado depois
    # de alguem jurar ter desligado.
    ok(C.do_texto("true") is True and C.do_texto("false") is False,
       "`true`/`false` viram booleano de verdade",
       f"{C.do_texto('true')!r} / {C.do_texto('false')!r}")
    ok(C.do_texto("FALSE") is False, "e nao dependem de caixa")
    ok(C.do_texto("1500") == 1500 and isinstance(C.do_texto("1500"), int),
       "numero inteiro vira int", repr(C.do_texto("1500")))
    ok(C.do_texto("0.5") == 0.5, "e decimal vira float", repr(C.do_texto("0.5")))
    ok(C.do_texto("npm run lint") == "npm run lint",
       "comando continua texto, que e' o tipo certo dele")
    ok(C.do_texto("main") == "main", "e nome de branch tambem")
    ok(C.como_toml(C.do_texto("false")) == "false",
       "e o que sai no arquivo e' `false`, sem aspas",
       C.como_toml(C.do_texto("false")))

    print("\nChave que o config do projeto nao tem ainda")
    # O caso real: os dois ambientes do Acme tinham config nascido de um
    # exemplo anterior a `[capacidades]`. O `definir` recusava, e a promessa de
    # "configuravel a qualquer momento" valia so' para chave que ja estava la'.
    raiz = cenario()
    cfg = raiz / ".agents" / "config.toml"
    cfg.write_text('[projeto]\nnome = "antigo"\n', encoding="utf-8")

    class A: pass
    a = A(); a.raiz = str(raiz)
    a.chave, a.valor = "capacidades.figma_escrita", "on"
    C.cmd_definir(a)
    d = tomllib.loads(cfg.read_text(encoding="utf-8"))
    ok(d["capacidades"]["figma_escrita"] == "on",
       "secao ausente: a chave entra, com a secao junto")
    texto = cfg.read_text(encoding="utf-8")
    ok("nao tem `git revert`" in texto,
       "e a explicacao da CHAVE vem junto, nao so' a linha")
    ok("PODER    esta maquina" in texto,
       "e a explicacao da SECAO tambem — e' ela que diz por que a secao existe")

    a.chave, a.valor = "capacidades.navegador", "off"
    C.cmd_definir(a)
    d = tomllib.loads(cfg.read_text(encoding="utf-8"))
    ok(d["capacidades"] == {"figma_escrita": "on", "navegador": "off"},
       "secao existente: a segunda chave entra no fim dela, sem duplicar a secao")
    ok(texto.count("[capacidades]") == cfg.read_text(encoding="utf-8").count("[capacidades]"),
       "e a secao continua aparecendo uma vez so'")

    a.chave, a.valor = "capacidades.figma_escrita", "off"
    C.cmd_definir(a)
    ok(tomllib.loads(cfg.read_text(encoding="utf-8"))["capacidades"]["figma_escrita"] == "off",
       "chave ja presente continua indo pela cirurgia de linha")

    # A nota da divergencia: achada no config de outro projeto, com
    # `# NASCE off` tres linhas acima de `figma_escrita = "on"`.
    raiz2 = cenario()
    cfg2 = raiz2 / ".agents" / "config.toml"
    cfg2.write_text('[projeto]\nnome = "b"\n', encoding="utf-8")
    b = A(); b.raiz = str(raiz2)
    b.chave, b.valor = "capacidades.figma_escrita", "on"
    C.cmd_definir(b)
    t = cfg2.read_text(encoding="utf-8")
    ok('Declarado como "on"' in t and 'padrão do pacote é "off"' in t,
       "valor diferente do padrao entra com a divergencia declarada")
    ok(t.index("Declarado como") < t.index("figma_escrita ="),
       "e a nota fica colada em cima da chave, nao solta")

    b.valor = "off"
    C.cmd_definir(b)
    ok("Declarado como" not in cfg2.read_text(encoding="utf-8"),
       "voltar ao padrao apaga a nota — ela so' existe enquanto a divergencia existe")

    a.chave, a.valor = "capacidades.figma_escrit", "on"
    try:
        C.cmd_definir(a)
        ok(False, "chave fora do ESQUEMA continua recusada")
    except C.ConfigError as exc:
        ok("figma_escrita" in str(exc),
           "chave fora do esquema e' recusada, e a mensagem sugere a certa")

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de configure.py: tudo verde.")
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
    raise SystemExit(main())
