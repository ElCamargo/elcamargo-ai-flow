#!/usr/bin/env python3
"""Attach a file to a tracker item, and prove it arrived intact.

    attach.py relatorio.pdf --card 1088 --comentario "Refinamento de negócio" \
        --pendencia P-03 --pendencia P-07 --origem relatorio.md
    attach.py CAM-1081-sdd-frontend.md --card 1081 --contrato "o time mobile"
    attach.py --conferir 1088

Two different failures shaped this tool, and it guards against both.

**O card não é o repositório.** Um anexo por step que produz documento enche o
card de PDF que ninguém abre, e aí o que precisava de resposta se perde no meio
do que era só registro. Por isso o anexo exige `--pendencia`: só sobe ao card o
documento que **pergunta** algo que só uma pessoa de fora do time técnico pode
responder. O resto mora no repositório, onde é versionado e diffável.

Há uma segunda razão, de 15/09/2026, e ela não é pergunta: **quem precisa do
documento não alcança o repositório onde ele mora.** É o `sdd-frontend` que a
trilha `backend` escreve — o contrato que outro time vai construir contra, e
esse time lê o card e mais nada. `--contrato "<quem>"` declara isso, exige
nomear o público, e o comentário do card diz na linha que não há o que
responder. As duas razões não se combinam: documento que pergunta E informa sobe
como pergunta.

O segundo: an upload can succeed and still be wrong.

`az rest --body "@arquivo"` treats the body as text and base64-encodes binary.
The API accepts it, returns 200, the attachment appears on the card — and the
PDF is unopenable. Nothing in the response says so. That happened, and the only
reason it was caught is that a person tried to open the file.

So every upload here is verified by **round trip**: upload, download what the
server now has, compare the hash. An attachment is only reported as attached
when the bytes that came back are the bytes that went up.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))

from flow_state import FlowStateError, resolve_agents_dir  # noqa: E402

# Azure DevOps application id, required to mint a token for its API.
ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


class Anexador:
    """Base. A backend uploads and downloads; verification is not overridable."""

    nome = "?"

    def enviar(self, caminho: Path, dados: bytes) -> str:
        raise NotImplementedError

    def baixar(self, url: str) -> bytes:
        raise NotImplementedError

    def vincular(self, card: str, url: str, comentario: str) -> None:
        raise NotImplementedError

    def anexos(self, card: str) -> list[dict]:
        raise NotImplementedError

    def _avisar_homonimo(self, caminho: Path, card: str, hash_novo: str) -> None:
        """Avisa quando o card já tem anexo com este nome.

        O Azure aceita dois anexos homônimos sem reclamar, e quem abre o card vê
        duas linhas iguais e nenhuma pista de qual é a vigente. Aconteceu ao
        atualizar um relatório de estado: a versão antiga e a nova ficaram lado a
        lado, com o mesmo nome e tamanhos diferentes.
        """
        try:
            existentes = [a for a in self.anexos(card) if a["nome"] == caminho.name]
        except (NotImplementedError, OSError, ValueError):
            return
        if not existentes:
            return
        print(f"  [aviso] o card {card} já tem {len(existentes)} anexo(s) chamados")
        print(f"          `{caminho.name}`. O Azure aceita homônimos, e quem abrir")
        print("          o card não vai saber qual é a versão vigente.")
        print("          Considere versionar o nome, ou remover a antiga à mão.")

    # -- the part that matters ------------------------------------------

    def anexar(self, caminho: Path, card: str, comentario: str = "") -> dict:
        dados = caminho.read_bytes()
        if not dados:
            raise FlowStateError(f"{caminho} está vazio.")
        antes = sha(dados)
        self._avisar_homonimo(caminho, card, antes)

        url = self.enviar(caminho, dados)

        # Round trip. Not optional, and not a flag: the failure this catches
        # returns 200 and looks like success.
        volta = self.baixar(url)
        depois = sha(volta)
        if depois != antes:
            raise FlowStateError(
                f"O anexo chegou corrompido e NÃO foi vinculado ao card.\n"
                f"  enviado:  {len(dados):,} bytes  sha256 {antes[:16]}…\n"
                f"  no servidor: {len(volta):,} bytes  sha256 {depois[:16]}…\n"
                + ("  O servidor guardou o arquivo em base64 — o envio foi "
                   "feito como texto, não como binário.\n"
                   if len(volta) > len(dados) and volta[:4] != dados[:4]
                   else "")
                + "  Nada foi anexado. Corrija o envio e tente de novo."
            )

        self.vincular(card, url, comentario)
        return {"url": url, "bytes": len(dados), "sha256": antes,
                "verificado": True}


class AzureDevOps(Anexador):
    nome = "azure"

    def __init__(self, org: str, projeto: str) -> None:
        if not org or not projeto:
            raise FlowStateError(
                "Backend `azure` exige `anexos.azure.org` e "
                "`anexos.azure.projeto` no config."
            )
        self.org = org.rstrip("/")
        self.projeto = projeto
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            r = subprocess.run(
                ["az", "account", "get-access-token", "--resource",
                 ADO_RESOURCE, "--query", "accessToken", "-o", "tsv"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise FlowStateError(
                    "Não consegui obter token do Azure. Rode `az login`.\n  "
                    + (r.stderr or "").strip().splitlines()[0:1][0]
                    if r.stderr else "Não consegui obter token do Azure."
                )
            self._token = r.stdout.strip()
        return self._token

    def _req(self, url: str, *, metodo: str = "GET",
             corpo: bytes | None = None, tipo: str | None = None) -> bytes:
        req = urllib.request.Request(url, data=corpo, method=metodo)
        req.add_header("Authorization", f"Bearer {self.token()}")
        if tipo:
            req.add_header("Content-Type", tipo)
        try:
            with urllib.request.urlopen(req) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            detalhe = exc.read().decode("utf-8", "replace")[:400]
            raise FlowStateError(
                f"{metodo} {url.split('?')[0]} devolveu {exc.code}: {detalhe}"
            ) from None

    def enviar(self, caminho: Path, dados: bytes) -> str:
        # Bytes, sempre. É aqui que o `az rest --body @arquivo` estraga tudo:
        # ele lê o arquivo como texto e sobe base64.
        nome = urllib.parse.quote(caminho.name)
        url = (f"{self.org}/_apis/wit/attachments"
               f"?fileName={nome}&api-version=7.1")
        # `application/octet-stream` SEMPRE, e não o tipo real do arquivo.
        #
        # A API de anexos do Azure DevOps aceita exatamente três: `application/json`,
        # `application/json-patch+json` e `application/octet-stream`. Mandar o tipo
        # verdadeiro devolve 400 — um PDF sobe como `application/pdf` e é recusado
        # com "Content-Type … which is not supported", que é uma mensagem sobre o
        # cabeçalho e não sobre o arquivo, e por isso se lê como problema do PDF.
        #
        # O nome do arquivo, que é o que decide como o navegador abre o anexo, vai
        # na query `fileName` e não depende disto.
        resposta = json.loads(self._req(url, metodo="POST", corpo=dados,
                                        tipo="application/octet-stream"))
        return resposta["url"]

    def baixar(self, url: str) -> bytes:
        return self._req(url)

    def _item_url(self, card: str) -> str:
        projeto = urllib.parse.quote(self.projeto)
        return (f"{self.org}/{projeto}/_apis/wit/workitems/{card}"
                f"?api-version=7.1")

    def vincular(self, card: str, url: str, comentario: str) -> None:
        patch = [{"op": "add", "path": "/relations/-", "value": {
            "rel": "AttachedFile", "url": url,
            "attributes": {"comment": comentario} if comentario else {}}}]
        self._req(self._item_url(card), metodo="PATCH",
                  corpo=json.dumps(patch).encode("utf-8"),
                  tipo="application/json-patch+json")

    def anexos(self, card: str) -> list[dict]:
        url = self._item_url(card).replace("?api-version",
                                           "?$expand=relations&api-version")
        item = json.loads(self._req(url))
        return [
            {"nome": r.get("attributes", {}).get("name")
             or urllib.parse.parse_qs(
                 urllib.parse.urlparse(r["url"]).query).get("fileName", ["?"])[0],
             "url": r["url"]}
            for r in item.get("relations", [])
            if r.get("rel") == "AttachedFile"
        ]


class GitHubRepo(Anexador):
    """O GitHub não tem API de anexo em issue — e o contrato não afrouxa.

    Upload de arquivo em comentário só acontece pela interface web. O contrato
    desta base é "sobe, baixa de volta, compara o hash", e ele nasceu de um
    defeito medido: o `az rest` base64-encodava binário, a API devolvia 200, o
    anexo aparecia no card **e estava corrompido**. Encolher esse contrato para
    caber no GitHub seria trocar a garantia pela conveniência.

    A adaptação não é contorno. O artefato entra no REPOSITÓRIO, e o round-trip
    passa pelo object store do Git: `git add` grava o blob, `git cat-file` lê de
    volta, e a comparação é do conteúdo endereçado por hash. Fica versionado,
    revisável em PR e recuperável — mais forte que anexo de card, não menos.

    E NÃO COMMITA. `git add` basta para o blob existir; criar commit no meio de
    um anexo mexeria no histórico sem ninguém ter pedido. O commit é do fluxo.

    IMPLEMENTADO E NÃO VALIDADO. Escrito contra a documentação do `gh`, e não
    exercitado contra um GitHub de verdade — o `gh` não estava instalado na
    máquina onde isto nasceu. O lado Azure foi escrito da mesma forma, e a
    execução real derrubou QUATRO suposições de QUATRO. Confira os nomes de
    campo no primeiro uso, antes de confiar no resultado.
    """

    nome = "github"
    validado_contra_servico_real = False

    # `docs/anexos`, e NAO `.agents/anexos`. Medido no primeiro teste: o
    # `git add` recusou com "paths are ignored by one of your .gitignore
    # files: .agents". E' justamente a pasta que costuma ser ignorada — e um
    # anexo ignorado pelo Git anula o proposito inteiro deste backend, que e'
    # o artefato ficar versionado e revisavel em PR.
    PASTA_PADRAO = "docs/anexos"

    def __init__(self, raiz: Path, org: str, repo: str,
                 pasta: str = PASTA_PADRAO, executar=None):
        self.raiz, self.org, self.repo, self.pasta = Path(raiz), org, repo, pasta
        self._executar = executar or self._gh

    @staticmethod
    def _gh(argv: list[str], **kw) -> str:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        except FileNotFoundError:
            raise FlowStateError(
                "o `gh` não está instalado, e o backend de anexo é `github`.\n"
                "  Instale o GitHub CLI e rode `gh auth login`: https://cli.github.com\n"
                "  Ou declare `[anexos] backend = \"manual\"` e anexe à mão."
            ) from None
        if r.returncode != 0:
            raise FlowStateError(f"`gh` falhou: {(r.stderr or r.stdout).strip()[:400]}")
        return r.stdout

    def _git(self, *args: str) -> str:
        r = subprocess.run(["git", "-C", str(self.raiz), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0:
            raise FlowStateError(f"`git {args[0]}` falhou: "
                                 f"{(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout

    def enviar(self, caminho: Path, dados: bytes) -> str:
        destino = self.raiz / self.pasta / self._card / caminho.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
        rel = destino.relative_to(self.raiz).as_posix()

        # Um anexo que o Git ignora não é anexo: ele não entra no PR, não vai
        # para o remoto, e some na primeira máquina limpa. Melhor recusar aqui,
        # dizendo qual regra o barrou, que gravar um arquivo que ninguém vai ver.
        ignorado = subprocess.run(
            ["git", "-C", str(self.raiz), "check-ignore", "-v", "--", rel],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if ignorado.returncode == 0:
            destino.unlink(missing_ok=True)
            raise FlowStateError(
                f"`{rel}` é ignorado pelo Git, e um anexo ignorado não chega a "
                f"ninguém.\n"
                f"  Regra que o barrou: {ignorado.stdout.strip()[:200]}\n"
                f"  Declare outra pasta em `[anexos.github] pasta`, ou tire a "
                f"regra do `.gitignore`."
            )

        # `git add` grava o blob no object store. Sem isso o `cat-file` do
        # round-trip leria o disco, e o disco é justamente o que já sabemos.
        self._git("add", "--", rel)
        blob = self._git("hash-object", "--", str(destino)).strip()
        return f"git:{blob}:{rel}"

    def baixar(self, url: str) -> bytes:
        blob = url.split(":", 2)[1]
        r = subprocess.run(["git", "-C", str(self.raiz), "cat-file", "blob", blob],
                           capture_output=True, timeout=60)
        if r.returncode != 0:
            raise FlowStateError(f"o blob `{blob[:12]}…` não está no object store.")
        return r.stdout

    def vincular(self, card: str, url: str, comentario: str) -> None:
        rel = url.split(":", 2)[2]
        corpo = (f"{comentario}\n\n" if comentario else "") + (
            f"Artefato do fluxo em `{rel}`, no repositório "
            f"`{self.org}/{self.repo}`.\n"
            f"Ele entra com o commit da branch desta atividade — o anexo é "
            f"versionado, e não um arquivo solto no card.")
        self._executar(["gh", "issue", "comment", str(card),
                        "--repo", f"{self.org}/{self.repo}", "--body", corpo])

    def anexos(self, card: str) -> list[dict]:
        pasta = self.raiz / self.pasta / str(card)
        if not pasta.is_dir():
            return []
        return [{"nome": p.name, "bytes": p.stat().st_size}
                for p in sorted(pasta.iterdir()) if p.is_file()]

    def anexar(self, caminho: Path, card: str, comentario: str = "") -> dict:
        # O destino depende do card, e a base chama `enviar` sem ele. Guardar
        # aqui é mais honesto que mudar a assinatura da base por um backend.
        self._card = str(card)
        return super().anexar(caminho, card, comentario)


class Manual(Anexador):
    """Sem backend: o fluxo não trava, o usuário anexa."""

    nome = "manual"

    def anexar(self, caminho: Path, card: str, comentario: str = "") -> dict:
        raise FlowStateError(
            f"Nenhum backend de anexo configurado para este projeto.\n"
            f"  Anexe à mão: {caminho}\n"
            f"  No card: {card}\n"
            f"  Para automatizar, declare `anexos.backend` no config.toml."
        )

    def anexos(self, card: str) -> list[dict]:
        return []


BACKENDS_DE_ANEXO = ("azure", "github", "manual")


def backend(agents: Path) -> Anexador:
    import config as cfg
    nome = cfg.obter("anexos.backend", "manual", agents)
    if nome == "azure":
        return AzureDevOps(cfg.obter("anexos.azure.org", "", agents),
                           cfg.obter("anexos.azure.projeto", "", agents))
    if nome == "github":
        return GitHubRepo(raiz=agents.parent,
                          org=cfg.obter("board.org", "", agents),
                          repo=cfg.obter("board.repo", "", agents),
                          pasta=cfg.obter("anexos.github.pasta",
                                          GitHubRepo.PASTA_PADRAO, agents))
    if nome == "manual":
        return Manual()
    raise FlowStateError(
        f"Backend de anexo desconhecido: {nome}. "
        f"Use {', '.join(f'`{b}`' for b in BACKENDS_DE_ANEXO)}."
    )


def cmd_conferir(b: Anexador, card: str) -> int:
    """Baixa cada anexo do card e diz se ele abre.

    Serve para o caso que já aconteceu: anexo que subiu corrompido antes de
    esta ferramenta existir.
    """
    lista = b.anexos(card)
    if not lista:
        print(f"Card {card}: nenhum anexo.")
        return 0
    print(f"Card {card}: {len(lista)} anexo(s)\n")
    ruins = 0
    for a in lista:
        try:
            dados = b.baixar(a["url"])
        except FlowStateError as exc:
            print(f"  [FALHA] {a['nome']}: {exc}")
            ruins += 1
            continue
        assinatura = dados[:5]
        suspeito = (a["nome"].lower().endswith(".pdf")
                    and not assinatura.startswith(b"%PDF"))
        marca = "SUSPEITO" if suspeito else "ok      "
        print(f"  [{marca}] {a['nome']:<40} {len(dados):>9,} bytes  "
              f"sha256 {sha(dados)[:16]}…")
        if suspeito:
            print(f"             começa com {assinatura!r} — deveria começar "
                  f"com b'%PDF'. Provável envio como texto.")
            ruins += 1
    print()
    print("Todos íntegros." if not ruins else
          f"{ruins} anexo(s) com problema. Reenvie com esta ferramenta.")
    return 1 if ruins else 0


# -- o portão do card ------------------------------------------------------
#
# O critério não é "quem lê", que foi o que produziu o card entulhado: por ele
# todo artefato com leitor fora do time técnico virava anexo, e são quatro
# steps. O critério é **o que exige resposta** — o card recebe o documento que
# faz uma pergunta que só quem está fora do time técnico pode responder.
#
# Uma pendência é exatamente isso, e `references/pending-decisions.md` diz o que
# ela precisa ter. Por isso o identificador dela é o que abre o portão: sem
# pendência aberta, o documento não tem o que pedir ao card.


def _tem_forma_de_identificador(ident: str) -> bool:
    """`P-03` sim; `sim` não.

    Sem isto, `--pendencia ok` passaria, e o portão viraria uma palavra mágica.
    """
    return len(ident) >= 3 and any(c.isdigit() for c in ident)


def conferir_pendencias(ids: list[str], origem: Path) -> list[str]:
    """As pendências declaradas existem no documento que vai ao card?

    `--pendencia` sozinho seria promessa. A conferência contra o Markdown de
    origem é o que a torna verificável — a mesma razão pela qual `flow_state pf`
    recusa `--aferido` sem `--inventario`: o número sem a conta que o sustenta é
    palpite com casas decimais.
    """
    limpos = [i.strip() for parte in ids for i in parte.split(",") if i.strip()]
    if not limpos:
        raise FlowStateError(
            "--pendencia não pode ser vazia."
        )

    torto = [i for i in limpos if not _tem_forma_de_identificador(i)]
    if torto:
        raise FlowStateError(
            f"Isto não parece identificador de pendência: "
            f"{', '.join(repr(i) for i in torto)}.\n"
            f"  Use o identificador com que ela aparece no documento — `P-03`, "
            f"`RN-04`.\n"
            f"  O portão existe para que o card só receba o que pergunta algo; "
            f"uma palavra genérica no lugar do identificador o desliga."
        )

    if not origem.exists():
        raise FlowStateError(
            f"Não encontrei {origem}, o Markdown de origem do relatório.\n"
            f"  É contra ele que as pendências declaradas são conferidas."
        )
    texto = origem.read_text(encoding="utf-8", errors="replace").lower()
    ausentes = [i for i in limpos if i.lower() not in texto]
    if ausentes:
        raise FlowStateError(
            f"Pendência declarada que não está em {origem.name}: "
            f"{', '.join(ausentes)}.\n"
            f"  Nada foi anexado. Ou a pendência não foi escrita, ou o "
            f"identificador está diferente no documento.\n"
            f"  Uma pendência que não aparece onde a pessoa lê não foi "
            f"comunicada — ver `references/pending-decisions.md`, *Onde a "
            f"pendência aparece*."
        )
    return limpos


def compor_comentario_de_contrato(comentario: str, publico: str) -> str:
    """O que a pessoa vê na lista do card quando o anexo é contrato.

    A segunda razão legítima de um arquivo subir ao card, e ela não é pergunta:
    **quem precisa dele não alcança o repositório onde ele mora.** O comentário
    precisa dizer isso na linha, senão o leitor abre o PDF para descobrir se
    tem algo a responder — e não tem.
    """
    aviso = (f"CONTRATO para {publico} — não pergunta nada: é a especificação "
             "da camada que ainda não foi implementada, para quem vai "
             "construí-la")
    return f"{comentario} — {aviso}" if comentario else aviso


def compor_comentario(comentario: str, pendencias: list[str]) -> str:
    """O que a pessoa vê antes de decidir abrir o PDF.

    O card mostra o comentário do anexo na lista. Se ele disser só "Refinamento
    de negócio", abrir o arquivo é a única forma de saber se há algo para
    responder. Com as pendências na linha, não é.
    """
    quantas = len(pendencias)
    pedido = (f"{quantas} pendência" + ("s" if quantas > 1 else "")
              + " para responder: " + ", ".join(pendencias))
    return f"{comentario} — {pedido}" if comentario else pedido


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="attach.py",
        description="Anexa arquivo ao card e prova que chegou íntegro.")
    p.add_argument("arquivo", nargs="?", type=Path)
    p.add_argument("--card", help="identificador do item no rastreador")
    p.add_argument("--comentario", default="")
    p.add_argument("--pendencia", action="append", default=[], metavar="ID",
                   help="identificador da pendência que só quem lê o card pode "
                        "responder. Sem pelo menos uma, o anexo é recusado")
    p.add_argument("--origem", type=Path, metavar="RELATORIO.md",
                   help="o Markdown que gerou o PDF; é nele que as pendências "
                        "declaradas são conferidas")
    p.add_argument("--contrato", metavar="QUEM", default="",
                   help="a OUTRA razão de subir ao card: quem precisa do "
                        "documento não alcança o repositório. Nomeie quem é. "
                        "Dispensa --pendencia, e não se combina com ela")
    p.add_argument("--conferir", metavar="CARD",
                   help="baixa e confere os anexos já existentes")
    args = p.parse_args(argv)

    try:
        if args.conferir:
            return cmd_conferir(backend(resolve_agents_dir()), args.conferir)

        if not args.arquivo or not args.card:
            p.error("informe o arquivo e --card, ou use --conferir")
        if not args.arquivo.exists():
            raise FlowStateError(f"Não encontrei {args.arquivo}.")

        # A SEGUNDA razão legítima, de 15/09/2026: o documento não pergunta
        # nada, e mesmo assim tem de subir — porque quem precisa dele não tem o
        # repositório. É o caso do `sdd-frontend` que a trilha `backend`
        # escreve: ele é o contrato que outro time vai construir contra, e esse
        # time lê o card e mais nada.
        #
        # Ela NÃO afrouxa o portão da pendência: exige nomear o público, e o
        # comentário do card diz, na linha, que não há o que responder. As duas
        # juntas seriam a porta larga que o portão existe para não ser —
        # documento que pergunta E informa sobe como pergunta.
        if args.contrato and args.pendencia:
            raise FlowStateError(
                "`--contrato` e `--pendencia` não se combinam: são as duas "
                "razões de um arquivo subir ao card, e elas pedem coisas "
                "diferentes de quem lê.\n"
                "  Documento que pergunta sobe como pergunta, com "
                "`--pendencia`. Contrato informa."
            )
        if args.contrato and not args.contrato.strip():
            raise FlowStateError(
                "`--contrato` exige dizer PARA QUEM. Sem o público nomeado, "
                "ninguém sabe quem\n  não alcança o repositório — e a razão "
                "vira palavra mágica, que é o que o portão\n  da pendência "
                "existe para não ser."
            )
        # O portão vem antes do backend de propósito: recusar por falta de
        # pendência é resposta sobre o pedido, e não deve depender de o projeto
        # ter rastreador configurado nem de o `az login` estar válido.
        if not args.pendencia and not args.contrato:
            raise FlowStateError(
                "O card só recebe o documento que pergunta algo que só quem "
                "está fora do time técnico pode responder.\n"
                "  Este não declarou nenhuma pendência, então ele fica no "
                "repositório — registrado no estado da atividade:\n"
                "    python3 tools/flow-state/flow_state.py artefato <id> "
                "--tipo <tipo> --caminho <caminho>\n"
                "  Se há pendência, declare-a:\n"
                "    --pendencia P-03 --origem <relatorio.md>\n"
                "  Ver `FLOW.md`, *O card recebe pergunta, não relatório*."
            )
        if args.pendencia and not args.origem:
            p.error("--pendencia exige --origem: é no Markdown de origem que "
                    "as pendências declaradas são conferidas")
        if args.contrato:
            pendencias_ = []
            comentario = compor_comentario_de_contrato(
                args.comentario, args.contrato.strip())
        else:
            pendencias_ = conferir_pendencias(args.pendencia, args.origem)
            comentario = compor_comentario(args.comentario, pendencias_)

        b = backend(resolve_agents_dir())
        r = b.anexar(args.arquivo, args.card, comentario)
        print(f"{args.arquivo.name} anexado ao card {args.card}")
        if args.contrato:
            print(f"  contrato para {args.contrato.strip()} — não pergunta nada")
        else:
            print(f"  {len(pendencias_)} pendência(s): {', '.join(pendencias_)}")
        print(f"  {r['bytes']:,} bytes · sha256 {r['sha256'][:16]}…")
        print("  verificado por ida e volta: os bytes no servidor são os "
              "mesmos que subiram.")
        return 0
    except FlowStateError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


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
