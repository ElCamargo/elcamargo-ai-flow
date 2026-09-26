#!/usr/bin/env python3
"""Smoke test for the attachment tool.

    python3 test_smoke.py

Uses fake backends, so it never touches a real tracker. The case that matters
is the one that already happened in production: an upload that succeeds, gets
a 200, shows up on the card, and holds a corrupted file.
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).parent.resolve()
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent / "flow-state"))

import attach  # noqa: E402
from attach import Anexador, FlowStateError, Manual, sha  # noqa: E402

falhas: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


class Fake(Anexador):
    """Guarda em memória. `corromper` reproduz o defeito real."""

    def __init__(self, corromper: str = "") -> None:
        self.corromper = corromper
        self.guardado: dict[str, bytes] = {}
        self.vinculados: list[tuple[str, str, str]] = []

    def enviar(self, caminho: Path, dados: bytes, card: str = "1") -> str:
        if self.corromper == "base64":
            # Exatamente o que `az rest --body @arquivo` faz: trata binário
            # como texto e sobe a representação em base64.
            dados = base64.b64encode(dados)
        elif self.corromper == "truncado":
            dados = dados[: len(dados) // 2]
        elif self.corromper == "vazio":
            dados = b""
        url = f"fake://{len(self.guardado)}"
        self.guardado[url] = dados
        return url

    def baixar(self, url: str) -> bytes:
        return self.guardado[url]

    def vincular(self, card: str, url: str, comentario: str) -> None:
        self.vinculados.append((card, url, comentario))

    def anexos(self, card: str) -> list[dict]:
        return [{"nome": "arquivo.pdf", "url": u} for u in self.guardado]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="anexar-"))
    pdf = tmp / "relatorio.pdf"
    # Assinatura de PDF real, para o detector de suspeita ter o que checar.
    pdf.write_bytes(b"%PDF-1.4\n" + b"conteudo binario \x00\x01\x02" * 200)

    print("Envio íntegro")
    b = Fake()
    r = b.anexar(pdf, "123", "com comentário")
    checar(r["verificado"], "anexo íntegro é reportado como verificado")
    checar(r["sha256"] == sha(pdf.read_bytes()), "o hash confere com o arquivo")
    checar(len(b.vinculados) == 1, "e foi vinculado ao card")
    checar(b.vinculados[0] == ("123", r["url"], "com comentário"),
           "com o card e o comentário certos")

    print("\nEnvio corrompido — o caso que aconteceu de verdade")
    for modo, descricao in (("base64", "base64 (o defeito do az rest)"),
                            ("truncado", "arquivo truncado"),
                            ("vazio", "servidor guardou vazio")):
        b = Fake(corromper=modo)
        try:
            b.anexar(pdf, "123")
            checar(False, f"{descricao} é recusado")
        except FlowStateError as exc:
            checar(True, f"{descricao} é recusado")
            checar(not b.vinculados,
                   f"  e NADA é vinculado ao card quando {modo} acontece")
            if modo == "base64":
                checar("base64" in str(exc),
                       "  e o erro nomeia a causa provável")

    print("\nA mensagem é acionável")
    b = Fake(corromper="base64")
    try:
        b.anexar(pdf, "123")
    except FlowStateError as exc:
        texto = str(exc)
        checar("sha256" in texto, "traz os dois hashes")
        checar("bytes" in texto, "traz os dois tamanhos")
        checar("Nada foi anexado" in texto,
               "diz explicitamente que nada foi anexado")

    print("\nArquivo vazio na origem")
    vazio = tmp / "vazio.pdf"
    vazio.write_bytes(b"")
    try:
        Fake().anexar(vazio, "123")
        checar(False, "arquivo vazio é recusado antes de subir")
    except FlowStateError:
        checar(True, "arquivo vazio é recusado antes de subir")

    print("\nSem backend configurado")
    try:
        Manual().anexar(pdf, "123")
        checar(False, "backend manual instrui em vez de falhar em silêncio")
    except FlowStateError as exc:
        checar("Anexe à mão" in str(exc),
               "backend manual instrui em vez de falhar em silêncio")

    print("\nO Content-Type que o Azure aceita")
    # A API de anexos aceita exatamente tres tipos, e o do arquivo nao e um
    # deles: um PDF enviado como `application/pdf` volta 400 com uma mensagem
    # sobre o cabecalho, que se le como problema do arquivo. Aconteceu de
    # verdade, ao anexar o refinamento de sistema do card 1057.
    vistos = {}

    class Espiao(attach.AzureDevOps):
        def __init__(self):
            self.org, self.projeto, self._token = "https://x", "P", "t"

        def _req(self, url, *, metodo="GET", corpo=None, tipo=None):
            vistos["tipo"] = tipo
            vistos["url"] = url
            return b'{"url": "https://x/anexo/1"}'

    Espiao().enviar(pdf, pdf.read_bytes(), "1057")
    checar(vistos["tipo"] == "application/octet-stream",
           "o upload sobe como octet-stream, nunca com o tipo do arquivo")
    checar("fileName=relatorio.pdf" in vistos["url"],
           "e o nome do arquivo vai na query, que e' o que decide como ele abre")


    print("\nGitHub: a Issue nao tem API de anexo, e o asset de release e' o substituto")
    # Nada aqui chama o `gh`: o que se prova e' o CONTRATO do backend, que e'
    # onde mora o risco. O asset e' do repositorio e nao do item, entao dois
    # cards com relatorio homonimo so' nao colidem por causa do prefixo -- e
    # `--conferir <card>` so' acha os do card pelo mesmo prefixo.
    chamadas = []

    class GHFalso(attach.GitHub):
        def __init__(self):
            super().__init__("dono/repo", "")
            self._release_ok = True
            self.guardado = {}

        def _gh(self, args, *, binario=False):
            chamadas.append(args)
            if args[:2] == ["release", "upload"]:
                caminho = Path(args[3])
                self.guardado[caminho.name] = caminho.read_bytes()
                return ""
            if args[:2] == ["release", "view"]:
                return json.dumps([
                    {"name": n, "apiUrl": f"api://{n}", "url": f"web://{n}"}
                    for n in self.guardado])
            if args[0] == "api":
                return self.guardado[args[1].removeprefix("api://")]
            return ""

    gh = GHFalso()
    r = gh.anexar(pdf, "1061", "Refinamento de negocio")
    checar(r["verificado"] and "1061-relatorio.pdf" in gh.guardado,
           "o asset leva o card no nome, porque o release e' do repositorio")
    checar([a["nome"] for a in gh.anexos("1061")] == ["relatorio.pdf"],
           "e `anexos` devolve o nome sem o prefixo, que e' o que o card mostra")
    checar(gh.anexos("1073") == [],
           "e nao entrega a outro card um anexo que nao e' dele")
    comentou = [a for a in chamadas if a[:2] == ["issue", "comment"]]
    checar(len(comentou) == 1 and "web://1061-relatorio.pdf" in comentou[0][-1],
           "a issue recebe comentario com o link do asset, nao com a URL da API")
    checar(any(a[:2] == ["release", "upload"] and "--clobber" in a
               for a in chamadas),
           "e o upload usa --clobber, porque reenviar e' o caso normal")

    print("\nConferência de anexos já existentes")
    b = Fake(corromper="base64")
    b.enviar(pdf, pdf.read_bytes(), "123")
    codigo = attach.cmd_conferir(b, "123")
    checar(codigo == 1, "conferir detecta anexo corrompido pré-existente")
    b2 = Fake()
    b2.enviar(pdf, pdf.read_bytes(), "123")
    checar(attach.cmd_conferir(b2, "123") == 0, "e aprova o íntegro")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print("\nAnexo homonimo: o card aceita dois com o mesmo nome, e ninguem sabe qual vale")



    class _Falso(Anexador):

        def __init__(self, existentes):

            self._existentes = existentes


        def anexos(self, card):

            return [{"nome": n, "url": "u"} for n in self._existentes]



    import io as _io, contextlib as _ctx  # noqa: E402

    _alvo = Path(tempfile.mkdtemp(prefix="anexo-")) / "relatorio.pdf"

    _alvo.write_bytes(b"conteudo")


    _buf = _io.StringIO()

    with _ctx.redirect_stdout(_buf):

        _Falso(["relatorio.pdf"])._avisar_homonimo(_alvo, "1", "h")

    checar("ja' tem" in _buf.getvalue().replace("já", "ja'"),

           "avisa quando o card ja tem anexo com o mesmo nome")


    _buf = _io.StringIO()

    with _ctx.redirect_stdout(_buf):

        _Falso(["outro.pdf"])._avisar_homonimo(_alvo, "1", "h")

    checar(_buf.getvalue() == "", "e cala quando o nome e' novo")


    _buf = _io.StringIO()

    with _ctx.redirect_stdout(_buf):

        Anexador.__new__(Anexador)._avisar_homonimo(_alvo, "1", "h")

    checar(_buf.getvalue() == "",

           "e backend que nao lista anexos nao quebra o envio por causa do aviso")


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
