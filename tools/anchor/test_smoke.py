#!/usr/bin/env python3
"""Fumaca da ancora: o que ela imprime, e o par ligar/desligar do hook.

O par importa mais que parece. Um hook que duplica roda duas vezes por mensagem;
um que nao sai continua rodando com o pacote desligado; e um que reescreve o
settings errado leva junto os hooks de outra pessoa.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import anchor as A  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


ATIVIDADE = """---
id: {id}
titulo: {titulo}
{extra}trilha: completa
step: {step}
step_nome: {nome}
status: {status}
atualizado_em: {quando}
---

# {id}
"""


def escrever(dir_atividades, **kw):
    kw.setdefault("extra", "")
    kw.setdefault("status", "em_andamento")
    kw.setdefault("quando", "2026-08-31 10:00:00")
    (dir_atividades / f"{kw['id']}.md").write_text(ATIVIDADE.format(**kw), encoding="utf-8")


def main() -> int:
    raiz = pathlib.Path(tempfile.mkdtemp(prefix="ancora-"))
    atividades = raiz / ".agents" / "atividades"
    atividades.mkdir(parents=True)

    print("\nSilencio quando nao ha nada a ancorar")
    ok(A.principal(["--raiz", str(raiz)]) == 0, "sem atividade, sai sem falar")

    print("\nO que ela imprime")
    escrever(atividades, id="1061", titulo="Botao inconsistente", step="6",
             nome="elcamargo-ux-reviewer",
             extra="complementares: 1073 1064\nbranch: feat/1061_botao\n")
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        A.principal(["--raiz", str(raiz)])
    saida = buf.getvalue()
    ok("1061" in saida and "Botao inconsistente" in saida, "id e titulo", saida)
    ok("step 6" in saida and "ux-reviewer" in saida, "o step em que ela esta", saida)
    ok("1073 1064" in saida, "e os cards que o PR fecha junto", saida)
    ok("nao recomece nem improvise" in saida.replace("ã", "a").replace("é", "e"),
       "e a frase que impede a deriva", saida)

    print("\nAtividade concluida nao ancora nada")
    escrever(atividades, id="99999", titulo="Ja fechada", step="10",
             nome="Portao", status="concluido")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        A.principal(["--raiz", str(raiz)])
    ok("99999" not in buf.getvalue(), "so' as em andamento entram")

    print("\nTeto: o board inteiro nao vai para o contexto a cada mensagem")
    for n in range(5):
        escrever(atividades, id=f"8000{n}", titulo=f"Aberta {n}", step="3",
                 nome="elcamargo-system-analyst", quando=f"2026-08-30 0{n}:00:00")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        A.principal(["--raiz", str(raiz)])
    saida = buf.getvalue()
    ok(saida.count("  8") + saida.count("  1061") <= A.TETO,
       f"no maximo {A.TETO} nomeadas", saida)
    ok("e mais" in saida, "e diz quantas ficaram de fora", saida)

    print("\nNunca quebra a mensagem de ninguem")
    (atividades / "quebrada.md").write_text("isto nao e front matter", encoding="utf-8")
    ok(A.principal(["--raiz", str(raiz)]) == 0, "arquivo ilegivel nao derruba o hook")
    ok(A.principal(["--raiz", "/caminho/que/nao/existe"]) == 0,
       "e raiz sem .agents tambem nao")

    print("\nO par ligar/desligar do hook, contra um settings de mentira")
    sh = (pathlib.Path(__file__).resolve().parents[2] / "install.sh").read_text(encoding="utf-8")

    def corpo(marcador: str) -> str:
        # Depois do `<<'PY'` vem o RESTO DA LINHA antes do script. Extrair sem
        # descartar essa linha faz o teste rodar um `&& echo` como se fosse
        # Python: ele explode, o subprocess ignora, e a assercao passa pelo
        # motivo errado. Aconteceu.
        resto = sh.split(marcador, 1)[1]
        return resto.split("\n", 1)[1].split("\nPY\n")[0]

    ligar = corpo('if python3 - "$PROJETO" "$PACOTE" <<\'PY\'')
    desligar = corpo('python3 - "$PROJETO" <<\'PY\'')
    ok(desligar.lstrip().startswith("import json"),
       "a extracao pega o corpo, e nao a cauda da linha do heredoc")

    proj = pathlib.Path(tempfile.mkdtemp(prefix="settings-"))
    (proj / ".claude").mkdir()
    alvo = proj / ".claude" / "settings.local.json"
    alvo.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "outro-hook.sh"}]}]},
    }, indent=2), encoding="utf-8")

    def comandos():
        d = json.loads(alvo.read_text(encoding="utf-8"))
        return [h["command"] for e in d["hooks"].get("UserPromptSubmit", [])
                for h in e["hooks"]]

    subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"], check=True)
    ok(any("anchor.py" in c for c in comandos()), "liga", str(comandos()))
    subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"], check=True)
    ok(sum("anchor.py" in c for c in comandos()) == 1,
       "e ligar de novo nao duplica", str(comandos()))

    r = subprocess.run([sys.executable, "-c", desligar, str(proj)])
    ok(r.returncode == 0 and not any("anchor.py" in c for c in comandos()),
       "desliga", str(comandos()))
    r = subprocess.run([sys.executable, "-c", desligar, str(proj)])
    ok(r.returncode == 1, "e desligar o que ja saiu nao reescreve o arquivo")

    d = json.loads(alvo.read_text(encoding="utf-8"))
    ok("outro-hook.sh" in comandos(), "o hook de outra pessoa sobrevive aos quatro")
    ok(d["permissions"]["allow"] == ["Bash(ls:*)"], "e as permissions tambem")

    alvo.write_text("{ isto nao e json", encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"],
                       capture_output=True, text=True)
    ok(r.returncode != 0 and alvo.read_text(encoding="utf-8") == "{ isto nao e json",
       "settings quebrado: recusa e NAO sobrescreve", r.stderr.strip())

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaca da ancora: tudo verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
