#!/usr/bin/env python3
"""Attach a file to a tracker item, and prove it arrived intact.

    attach.py relatorio.pdf --card 1088 --comentario "Refinamento de negócio"
    attach.py --conferir 1088

The reason this tool exists, instead of a line in a skill telling the agent to
call the tracker's API: an upload can succeed and still be wrong.

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
import tempfile
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

    def enviar(self, caminho: Path, dados: bytes, card: str) -> str:
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

        No GitHub o risco é o oposto e igualmente calado: o `--clobber` do
        `gh release upload` SUBSTITUI o asset homônimo, e a versão anterior
        deixa de existir. Nos dois casos o aviso é a única coisa que separa
        "atualizei" de "perdi".
        """
        try:
            existentes = [a for a in self.anexos(card) if a["nome"] == caminho.name]
        except (NotImplementedError, OSError, ValueError):
            return
        if not existentes:
            return
        print(f"  [aviso] o card {card} já tem {len(existentes)} anexo(s) chamados")
        print(f"          `{caminho.name}`.")
        if self.nome == "github":
            print("          O envio vai SUBSTITUIR o anterior — ele deixa de existir.")
        else:
            print("          O Azure aceita homônimos, e quem abrir o card não")
            print("          vai saber qual é a versão vigente.")
        print("          Considere versionar o nome antes de subir.")

    # -- the part that matters ------------------------------------------

    def anexar(self, caminho: Path, card: str, comentario: str = "") -> dict:
        dados = caminho.read_bytes()
        if not dados:
            raise FlowStateError(f"{caminho} está vazio.")
        antes = sha(dados)
        self._avisar_homonimo(caminho, card, antes)

        url = self.enviar(caminho, dados, card)

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
                capture_output=True, text=True)
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

    def enviar(self, caminho: Path, dados: bytes, card: str) -> str:
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


class GitHub(Anexador):
    """Anexo em repositório GitHub, por asset de release.

    A Issue do GitHub **não tem API de anexo**: o que a interface web chama de
    anexo é um upload para um host separado, por uma rota que não é pública. Um
    `gh issue comment` sobe texto e nada mais.

    O substituto é o asset de release, e ele não é um contorno pobre — é a
    única superfície do GitHub que aceita binário, devolve binário, e vale para
    repositório privado. Que é exatamente o que a verificação por ida e volta
    desta ferramenta exige. O PDF sobe num release de tag fixa, e a Issue recebe
    um comentário com o link.

    O nome do asset leva o card na frente (`1088-relatorio.pdf`) porque o
    release é do REPOSITÓRIO e não do item: sem o prefixo, dois cards que geram
    `relatorio-de-negocio.pdf` se sobrescrevem em silêncio, e `--conferir 1088`
    não teria como saber quais assets são daquele card.

    Tudo passa pelo `gh`, que já resolve autenticação, repositório e proxy —
    reimplementar isso com token à mão seria escrever de novo o que já está
    instalado.
    """

    nome = "github"

    def __init__(self, repo: str, tag: str) -> None:
        self.tag = tag or "flow-anexos"
        self._repo = repo
        self._release_ok = False

    # -- gh -------------------------------------------------------------

    def _gh(self, args, *, binario: bool = False):
        try:
            r = subprocess.run(["gh", *args], capture_output=True,
                               text=not binario)
        except FileNotFoundError:
            raise FlowStateError(
                "Backend `github` exige o `gh` instalado e autenticado.\n"
                "  Instale em https://cli.github.com e rode `gh auth login`."
            ) from None
        if r.returncode != 0:
            erro = r.stderr
            if not isinstance(erro, str):
                erro = erro.decode("utf-8", "replace")
            raise FlowStateError(
                "`gh " + " ".join(args[:3]) + "` falhou: " + erro.strip()[:400])
        return r.stdout

    @property
    def repo(self) -> str:
        if not self._repo:
            self._repo = str(self._gh(
                ["repo", "view", "--json", "nameWithOwner",
                 "-q", ".nameWithOwner"])).strip()
        return self._repo

    def _garantir_release(self) -> None:
        """Cria a tag de anexos na primeira vez, e só na primeira."""
        if self._release_ok:
            return
        try:
            self._gh(["release", "view", self.tag, "--repo", self.repo,
                      "--json", "tagName"])
        except FlowStateError:
            self._gh(["release", "create", self.tag, "--repo", self.repo,
                      "--title", "Anexos do fluxo",
                      "--notes", "Relatórios gerados pelo elcamargo-ai-flow e "
                                 "vinculados às issues por comentário. "
                                 "Não é um release de software."])
        self._release_ok = True

    def _assets(self) -> list[dict]:
        self._garantir_release()
        bruto = str(self._gh(["release", "view", self.tag, "--repo", self.repo,
                              "--json", "assets", "-q", ".assets"])).strip()
        return json.loads(bruto) if bruto else []

    # -- o contrato do Anexador -----------------------------------------

    def enviar(self, caminho: Path, dados: bytes, card: str) -> str:
        self._garantir_release()
        alvo = f"{card}-{caminho.name}"
        # `gh release upload` sobe um ARQUIVO, e o nome do asset é o nome do
        # arquivo. Daí a cópia temporária: é o único jeito de prefixar o card
        # sem renomear o original que o step acabou de gerar.
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / alvo
            copia.write_bytes(dados)
            self._gh(["release", "upload", self.tag, str(copia),
                      "--repo", self.repo, "--clobber"])
        for a in self._assets():
            if a.get("name") == alvo:
                return a["apiUrl"]
        raise FlowStateError(
            f"O `gh` disse que subiu, mas `{alvo}` não está nos assets de "
            f"`{self.tag}`. Nada foi vinculado à issue {card}.")

    def baixar(self, url: str) -> bytes:
        # `Accept: application/octet-stream` é o que faz a API devolver o
        # BINÁRIO do asset em vez do JSON que o descreve.
        return bytes(self._gh(["api", url, "-H",
                               "Accept: application/octet-stream"],
                              binario=True))

    def vincular(self, card: str, url: str, comentario: str) -> None:
        link = next((a.get("url") for a in self._assets()
                     if a.get("apiUrl") == url), url)
        corpo = (f"{comentario}\n\n" if comentario else "") + f"[anexo] {link}"
        self._gh(["issue", "comment", card, "--repo", self.repo,
                  "--body", corpo])

    def anexos(self, card: str) -> list[dict]:
        prefixo = f"{card}-"
        return [{"nome": a["name"][len(prefixo):], "url": a["apiUrl"]}
                for a in self._assets()
                if a.get("name", "").startswith(prefixo)]


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


def backend(agents: Path) -> Anexador:
    """O backend declarado; sem declaração, o que o rastreador do projeto pede.

    Antes só existia o Azure, e o padrão era `manual` — num repositório GitHub
    isso significava que todo relatório do fluxo parava na mão do usuário, sem
    que nada dissesse que havia caminho automático. Hoje `anexos.backend` vazio
    pergunta ao rastreador (`[tracker] backend`, ou o remote), e só cai em
    `manual` quando nem isso responde.
    """
    import config as cfg
    nome = cfg.obter("anexos.backend", "", agents) or cfg.rastreador(agents)
    if nome == "azure":
        return AzureDevOps(cfg.obter("anexos.azure.org", "", agents),
                           cfg.obter("anexos.azure.projeto", "", agents))
    if nome == "github":
        return GitHub(cfg.obter("anexos.github.repo", "", agents),
                      cfg.obter("anexos.github.tag", "", agents))
    if nome in ("manual", ""):
        return Manual()
    raise FlowStateError(
        f"Backend de anexo desconhecido: {nome}. "
        f"Use `azure`, `github` ou `manual`."
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="attach.py",
        description="Anexa arquivo ao card e prova que chegou íntegro.")
    p.add_argument("arquivo", nargs="?", type=Path)
    p.add_argument("--card", help="identificador do item no rastreador")
    p.add_argument("--comentario", default="")
    p.add_argument("--conferir", metavar="CARD",
                   help="baixa e confere os anexos já existentes")
    args = p.parse_args(argv)

    try:
        agents = resolve_agents_dir()
        b = backend(agents)

        if args.conferir:
            return cmd_conferir(b, args.conferir)

        if not args.arquivo or not args.card:
            p.error("informe o arquivo e --card, ou use --conferir")
        if not args.arquivo.exists():
            raise FlowStateError(f"Não encontrei {args.arquivo}.")

        r = b.anexar(args.arquivo, args.card, args.comentario)
        print(f"{args.arquivo.name} anexado ao card {args.card}")
        print(f"  {r['bytes']:,} bytes · sha256 {r['sha256'][:16]}…")
        print("  verificado por ida e volta: os bytes no servidor são os "
              "mesmos que subiram.")
        return 0
    except FlowStateError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
