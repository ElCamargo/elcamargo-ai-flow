#!/usr/bin/env python3
"""O backend de anexo do GitHub — que não tem API de anexo.

Chama-se `test_domain.py` e não `test_github.py` de propósito: o portão do
projeto varre `test_smoke.py`, `test_domain.py` e `test_package.py`, e um
arquivo fora desses três nomes **não é rodado por ninguém**. Foi assim que a
2.0.1 nasceu — "o rename quebrou o gerador de PDF, e a suíte que provava isso
era a única que eu não rodava".

O GitHub **não permite** subir arquivo em issue pela API: upload em comentário
só acontece pela interface web. E o contrato do `attach.py` é "sobe, baixa de
volta, compara o hash" — nascido de um defeito medido em que o `az rest`
base64-encodava binário, a API devolvia 200, o anexo aparecia no card **e
estava corrompido**. Esse contrato não pode ser afrouxado para caber no GitHub.

A adaptação não é contorno: o artefato entra no **repositório**, e a conferência
de hash passa pelo **object store do Git**. Fica versionado, revisável em PR e
recuperável — mais forte que anexo de card, não menos.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flow-state"))
import attach as A  # noqa: E402

falhas: list[str] = []
TEMPORARIOS: list[Path] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


def repo() -> Path:
    raiz = Path(tempfile.mkdtemp(prefix="anexo-gh-")).resolve()
    TEMPORARIOS.append(raiz)
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(raiz), *args], capture_output=True)
    return raiz


class GhFalso:
    def __init__(self):
        self.chamadas: list[list[str]] = []

    def __call__(self, argv: list[str], **kw) -> str:
        self.chamadas.append(argv)
        return ""


def main() -> int:
    raiz = repo()
    origem = raiz / "relatorio.pdf"
    # Binário de verdade, com byte nulo: é exatamente o que o base64 acidental
    # estraga, e o que um round-trip de texto não sobrevive.
    dados = b"%PDF-1.7\x00\x01\x02\xff\xfe binario \xc3\xa9 de verdade \x00 fim"
    origem.write_bytes(dados)

    gh = GhFalso()
    b = A.GitHubRepo(raiz=raiz, org="acme", repo="app", pasta="docs/anexos",
                     executar=gh)

    print("\nO round-trip passa pelo object store do Git")
    r = b.anexar(origem, "42", "SDD de sistema")
    ok(r["verificado"], "o anexo foi verificado", str(r))
    ok(r["sha256"] == A.sha(dados), "e o hash e' o do arquivo original")
    ok(r["bytes"] == len(dados), "com o tamanho intacto", str(r["bytes"]))

    print("\nO binario sobrevive -- byte a byte, e nao 'parecido'")
    destino = raiz / "docs" / "anexos" / "42" / "relatorio.pdf"
    ok(destino.exists(), "o arquivo entrou no repositorio", str(destino))
    ok(destino.read_bytes() == dados,
       "e e' identico ao original, com o byte nulo no lugar")

    print("\nO blob esta' no Git, e nao so' no disco")
    # E' isso que torna a conferencia mais forte que anexo de card: o objeto e'
    # enderecado por conteudo, versionado e recuperavel.
    sha_git = subprocess.run(["git", "-C", str(raiz), "hash-object", str(destino)],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    existe = subprocess.run(["git", "-C", str(raiz), "cat-file", "-e", sha_git],
                            capture_output=True)
    ok(existe.returncode == 0, "o blob existe no object store", sha_git)
    ok(sha_git in r["url"], "e o localizador nomeia o blob", r["url"])

    print("\nO comentario na issue diz onde o arquivo esta'")
    comentarios = [c for c in gh.chamadas if "comment" in c]
    ok(comentarios, "houve comentario na issue", str(gh.chamadas))
    corpo = " ".join(comentarios[0]) if comentarios else ""
    ok("42" in corpo, "no numero certo da issue", corpo[:120])
    ok("docs/anexos/42/relatorio.pdf" in corpo,
       "com o caminho do arquivo", corpo[:200])
    ok("acme/app" in corpo, "e no repositorio certo", corpo[:160])

    print("\nO anexo NAO e' commitado por conta propria")
    # Commitar no meio de um anexo mexeria no historico sem ninguem ter pedido.
    # O `git add` basta para o blob existir; o commit e' do fluxo, e da pessoa.
    log = subprocess.run(["git", "-C", str(raiz), "log", "--oneline"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok(not log.stdout.strip(), "nenhum commit foi criado", log.stdout[:80])
    staged = subprocess.run(["git", "-C", str(raiz), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    ok("docs/anexos/42/relatorio.pdf" in staged,
       "mas o arquivo esta' preparado para o commit do fluxo", staged[:120])

    print("\nArquivo vazio e' recusado, como no backend do Azure")
    vazio = raiz / "vazio.pdf"
    vazio.write_bytes(b"")
    erro = ""
    try:
        b.anexar(vazio, "42")
    except Exception as exc:
        erro = str(exc)
    ok("vazi" in erro.lower(), "o erro diz que o arquivo esta' vazio", erro[:100])

    print("\nPasta IGNORADA pelo Git e' recusada, e a regra e' nomeada")
    # Achado no primeiro teste deste arquivo: o padrao era `.agents/anexos`, e
    # o `git add` recusou -- `.agents` esta' no gitignore global desta maquina.
    # Um anexo que o Git ignora nao entra no PR, nao vai para o remoto e some
    # na primeira maquina limpa. Gravar em silencio seria pior que recusar.
    (raiz / ".gitignore").write_text("segredos/\n", encoding="utf-8")
    bi = A.GitHubRepo(raiz=raiz, org="acme", repo="app", pasta="segredos",
                      executar=GhFalso())
    erro = ""
    try:
        bi.anexar(origem, "42")
    except Exception as exc:
        erro = str(exc)
    ok("ignorado" in erro, "o erro diz que o caminho e' ignorado", erro[:110])
    ok(".gitignore" in erro and "segredos" in erro,
       "e NOMEIA a regra que barrou, em vez de so' reclamar", erro[:220])
    ok(not (raiz / "segredos" / "42" / "relatorio.pdf").exists(),
       "e nao deixa arquivo orfao para tras")
    ok(A.GitHubRepo.PASTA_PADRAO == "docs/anexos",
       "o padrao e' uma pasta que costuma ser versionada",
       A.GitHubRepo.PASTA_PADRAO)

    print("\nO backend e' escolhido por declaracao, e o desconhecido e' recusado")
    ok("github" in A.BACKENDS_DE_ANEXO,
       "`github` e' um backend declarado", str(A.BACKENDS_DE_ANEXO))

    for d in TEMPORARIOS:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça do anexo no GitHub: tudo verde.")
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
