#!/usr/bin/env python3
"""Fumaça do board.py — o leitor de board que não sabe criar card.

O pacote não lia board nenhum: quem lia era a skill de Git do projeto, quando
havia uma. Isso funcionava no Acme, que tem a sua, e deixava sem caminho
qualquer projeto que não tivesse — que é a maioria de quem instala o pacote.

Os testes aqui NÃO chamam `gh` nem `az`. Eles injetam a saída do CLI, porque o
que precisa ser provado é a leitura: que a mesma forma sai dos dois boards, que
`criar` não existe, e que um CLI ausente vira instrução em vez de traceback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board as B  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class CLIFalso:
    """Devolve o que o CLI devolveria, e registra o que foi pedido."""

    def __init__(self, respostas: dict[str, str]):
        self.respostas = respostas
        self.chamadas: list[list[str]] = []

    def __call__(self, argv: list[str], **kw) -> str:
        self.chamadas.append(argv)
        for chave, valor in self.respostas.items():
            if chave in " ".join(argv):
                return valor
        return ""


CARD_AZURE = json.dumps({
    "id": 1061,
    "fields": {
        "System.Title": "Acesso do Cliente",
        "System.State": "Active",
        "System.WorkItemType": "User Story",
        "System.Description": "<div>O app precisa entrar</div>",
        "System.AssignedTo": {"displayName": "Ederson"},
    },
})

CARD_GITHUB = json.dumps({
    "number": 42,
    "title": "Acesso do Cliente",
    "state": "OPEN",
    "body": "O app precisa entrar",
    "assignees": [{"login": "edersoncamargo"}],
    "labels": [{"name": "feature"}],
})


def main() -> int:
    print("\nA MESMA forma sai dos dois boards")
    # Sem isto o step 1 teria que saber de qual board veio o card, e o
    # acoplamento so' teria mudado de lugar.
    az = B.criar_board({"tipo": "azure", "org": "o", "projeto": "p"},
                       executar=CLIFalso({"az boards work-item show": CARD_AZURE}))
    gh = B.criar_board({"tipo": "github", "org": "acme", "repo": "app"},
                       executar=CLIFalso({"gh issue view": CARD_GITHUB}))
    a, g = az.ler("1061"), gh.ler("42")
    ok(set(a) == set(g), "as chaves do card sao as mesmas nos dois",
       f"azure={sorted(a)} github={sorted(g)}")
    for campo in ("id", "titulo", "estado", "tipo", "corpo", "responsavel", "url"):
        ok(campo in a, f"o card traz `{campo}`")
    ok(a["titulo"] == g["titulo"] == "Acesso do Cliente",
       "e o titulo sai igual dos dois", f"{a['titulo']!r} {g['titulo']!r}")

    print("\nItem e' escopado por ORG; consulta e' que e' por PROJETO")
    # Medido contra o board de verdade, e confirmado no proprio `--help`:
    # `az boards work-item show --project X` responde `unrecognized arguments`.
    # O id do work item ja' e' unico na organizacao. So' o `query` aceita os dois.
    cli = CLIFalso({"az boards work-item show": CARD_AZURE})
    bz = B.criar_board({"tipo": "azure", "org": "o", "projeto": "Projeto Exemplo"},
                       executar=cli)
    bz.ler("1061")
    argv = cli.chamadas[0]
    ok("--project" not in argv,
       "ler um card NAO manda --project, porque o comando nao aceita", str(argv))
    ok("--org" in argv, "mas manda --org, que ele aceita", str(argv))
    ok(not any(a.startswith("--org=") for a in argv),
       "e como argumento proprio, para sobreviver a espaco no valor", str(argv))

    cli2 = CLIFalso({"az boards query": "[]"})
    B.criar_board({"tipo": "azure", "org": "o", "projeto": "Projeto Exemplo"},
                  executar=cli2).listar()
    argv2 = cli2.chamadas[0]
    ok("--project" in argv2 and "Projeto Exemplo" in argv2,
       "a CONSULTA manda --project, com o espaco intacto", str(argv2))

    print("\nLer card nao exige `projeto` -- so' listar exige")
    # Exigir a chave para um comando que a ignora faria o fluxo travar a' toa.
    so_org = B.criar_board({"tipo": "azure", "org": "o"},
                           executar=CLIFalso({"az boards work-item show": CARD_AZURE}))
    ok(so_org.ler("1061")["titulo"] == "Acesso do Cliente",
       "com so' `org` declarado, ler funciona")
    erro = ""
    try:
        B.criar_board({"tipo": "azure", "org": "o"},
                      executar=CLIFalso({"az boards query": "[]"})).listar()
    except B.BoardError as exc:
        erro = str(exc)
    ok("projeto" in erro, "e listar diz que precisa de `projeto`", erro[:120])

    print("\nO HTML do Azure vira texto -- ninguem le' `<div>` num card")
    ok("<div>" not in a["corpo"] and "app precisa entrar" in a["corpo"],
       "a descricao chega legivel", repr(a["corpo"]))

    print("\nBug nao tem `System.Description` -- o corpo dele e' ReproSteps")
    # Medido lendo o bug 1091 do board real: o leitor devolvia corpo VAZIO em
    # silencio, porque so' olhava `System.Description`. Um step que recebe corpo
    # vazio escreve SDD sobre nada, e nunca fica sabendo que o card tinha texto.
    BUG = json.dumps({"id": 1091, "fields": {
        "System.Title": "Ajustes em Cadastro",
        "System.WorkItemType": "Bug",
        "Microsoft.VSTS.TCM.ReproSteps": "<div>Em anexo os ajustes.</div>"}})
    bug = B.criar_board({"tipo": "azure", "org": "o"},
                        executar=CLIFalso({"az boards work-item show": BUG})).ler("1091")
    ok(bug["corpo"] == "Em anexo os ajustes.",
       "o corpo sai do campo do TIPO do item", repr(bug["corpo"]))
    ok("System.Description" in B.AzureBoards.CAMPOS_DE_CORPO
       and "Microsoft.VSTS.TCM.ReproSteps" in B.AzureBoards.CAMPOS_DE_CORPO,
       "e a cadeia de campos e' declarada, nao adivinhada",
       str(B.AzureBoards.CAMPOS_DE_CORPO))

    print("\n`criar` NAO existe, e isso e' regra e nao esquecimento")
    # "O board e' do solicitante; abrir item la' e' decisao de gestao."
    for nome, b in (("azure", az), ("github", gh)):
        ok(not hasattr(b, "criar"), f"{nome}: sem metodo `criar`")
    ok("criar" not in B.VERBOS, "e o contrato lista so' os quatro verbos",
       str(B.VERBOS))

    print("\nO que NAO foi validado se declara no codigo, e nao so' na prosa")
    # Ausencia declarada e' aceita; ausencia esquecida vira promessa. O Azure
    # foi escrito contra a documentacao e a execucao real derrubou quatro
    # suposicoes de quatro -- o GitHub nao tem motivo para ter tido mais sorte.
    ok(B.AzureBoards.validado_contra_servico_real is True,
       "o Azure se declara validado -- foi exercitado contra o board real")
    ok(B.GitHub.validado_contra_servico_real is False,
       "e o GitHub se declara NAO validado, ate' alguem rodar contra um de verdade")

    print("\nO backend `nenhum` nao inventa card, e diz o que fazer")
    n = B.criar_board({"tipo": "nenhum"}, executar=CLIFalso({}))
    erro = ""
    try:
        n.ler("1061")
    except B.BoardError as exc:
        erro = str(exc)
    ok("nenhum" in erro or "não declarado" in erro or "cole" in erro.lower(),
       "ele explica em vez de estourar", erro[:140])

    print("\nCLI ausente vira instrucao, nao traceback")
    def sem_cli(argv, **kw):
        raise FileNotFoundError(argv[0])
    b = B.criar_board({"tipo": "github", "org": "a", "repo": "b"}, executar=sem_cli)
    erro = ""
    try:
        b.ler("1")
    except B.BoardError as exc:
        erro = str(exc)
    ok("gh" in erro and ("instal" in erro or "https://" in erro),
       "diz qual CLI falta e como resolver", erro[:160])

    print("\nTipo desconhecido e' recusado com a lista do que existe")
    erro = ""
    try:
        B.criar_board({"tipo": "jira"}, executar=CLIFalso({}))
    except B.BoardError as exc:
        erro = str(exc)
    ok("jira" in erro and "azure" in erro and "github" in erro,
       "nomeia o pedido e lista os aceitos", erro[:160])

    print("\nComentarios sao lidos -- e' onde o analista responde duvida")
    cli = CLIFalso({"az boards work-item show": CARD_AZURE,
                    "gh issue view": json.dumps({"comments": [
                        {"author": {"login": "ana"}, "body": "isso mudou no card 51"}]})})
    gh2 = B.criar_board({"tipo": "github", "org": "a", "repo": "b"}, executar=cli)
    cs = gh2.comentarios("42")
    ok(cs and cs[0]["autor"] == "ana" and "card 51" in cs[0]["texto"],
       "autor e texto de cada comentario", str(cs)[:140])

    print("\nO `listar` pede o board, e nao adivinha do disco")
    cli = CLIFalso({"gh issue list": json.dumps(
        [{"number": 7, "title": "Bug do filtro", "state": "OPEN"}])})
    gh3 = B.criar_board({"tipo": "github", "org": "a", "repo": "b"}, executar=cli)
    itens = gh3.listar()
    ok(itens and itens[0]["id"] == "7" and itens[0]["titulo"] == "Bug do filtro",
       "a listagem sai normalizada", str(itens)[:120])
    ok(any("--repo" in " ".join(c) for c in cli.chamadas),
       "e o repositorio vai no comando, nao no diretorio corrente",
       str(cli.chamadas))

    print("\nO quinto verbo: `marcar` poe etiqueta e NADA mais")
    # As trilhas `backend` e `frontend` entregam um card em duas vezes, e entre
    # uma e outra o card fica com `Aguardando frontend`. Etiqueta posta a' mao
    # e' etiqueta que um dia nao se poe.
    cli = CLIFalso({"az boards work-item show": json.dumps(
        {"id": 1081, "fields": {"System.Title": "FAQ",
                                 "System.Tags": "app; urgente"}})})
    az = B.criar_board({"tipo": "azure", "org": "o", "projeto": "p"}, executar=cli)
    az.marcar("1081", "Aguardando frontend", "[fluxo] so' o backend")
    _update = next((c for c in cli.chamadas if "update" in " ".join(c)), [])
    _campos = next((c for c in _update if c.startswith("System.Tags=")), "")
    ok("app" in _campos and "urgente" in _campos
       and "Aguardando frontend" in _campos,
       "no Azure a etiqueta e' SOMADA as que ja existem, nao escrita por cima",
       _campos)
    ok("--discussion" in _update,
       "e a justificativa vai junto: etiqueta sem motivo obriga a perguntar")
    for _proibido in ("System.State", "System.AssignedTo"):
        ok(not any(_proibido in c for c in _update),
           f"e ela nao toca em `{_proibido}` -- o board e' do solicitante")

    cli2 = CLIFalso({"az boards work-item show": json.dumps(
        {"id": 1081, "fields": {"System.Tags": "app; Aguardando frontend"}})})
    az2 = B.criar_board({"tipo": "azure", "org": "o", "projeto": "p"}, executar=cli2)
    az2.marcar("1081", "Aguardando frontend", "[fluxo] a tela fechou",
               remover=True)
    _u2 = next((c for c in cli2.chamadas if "update" in " ".join(c)), [])
    _c2 = next((c for c in _u2 if c.startswith("System.Tags=")), "")
    ok("Aguardando frontend" not in _c2 and "app" in _c2,
       "e remover tira SO' ela, deixando as outras", _c2)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de board.py: tudo verde.")
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
