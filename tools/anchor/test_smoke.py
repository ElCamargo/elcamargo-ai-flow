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
from pathlib import Path

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

    def comandos(evento="UserPromptSubmit"):
        d = json.loads(alvo.read_text(encoding="utf-8"))
        return [h["command"] for e in d["hooks"].get(evento, [])
                for h in e["hooks"]]

    def pre_bash():
        d = json.loads(alvo.read_text(encoding="utf-8"))
        return [(e.get("matcher"), h) for e in d["hooks"].get("PreToolUse", [])
                for h in e["hooks"] if "anchor.py" in h["command"]]

    subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"], check=True)
    ok(any("anchor.py" in c for c in comandos()), "liga", str(comandos()))
    ok(not any("--contexto" in c for c in comandos()),
       "a ancora de mensagem nao leva o `--contexto`", str(comandos()))
    # Ate 2.62.0 so' o plugin ligava este, e quem instalava por aqui ficava
    # com a trava do step 9 muda -- sem registro ela nao acusa, e nao avisa.
    ok(len(pre_bash()) == 1 and pre_bash()[0][0] == "Bash"
       and pre_bash()[0][1]["command"].endswith("anchor.py --contexto")
       and pre_bash()[0][1].get("timeout"),
       "liga tambem o PreToolUse de Bash, com teto", str(pre_bash()))
    subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"], check=True)
    ok(sum("anchor.py" in c for c in comandos()) == 1,
       "e ligar de novo nao duplica", str(comandos()))
    ok(len(pre_bash()) == 1, "nem o PreToolUse", str(pre_bash()))

    # Instalacao anterior a 2.63.0: so' a ancora de mensagem. Rodar o
    # install.sh de novo acrescenta a outra, e nao troca uma pela outra.
    d = json.loads(alvo.read_text(encoding="utf-8"))
    d["hooks"].pop("PreToolUse")
    alvo.write_text(json.dumps(d), encoding="utf-8")
    subprocess.run([sys.executable, "-c", ligar, str(proj), "/novo"], check=True)
    ok([c for c in comandos() if "anchor.py" in c] == ["python3 /novo/tools/anchor/anchor.py"]
       and len(pre_bash()) == 1
       and "/novo/" in pre_bash()[0][1]["command"],
       "reinstalar sobre a versao antiga reaponta uma e acrescenta a outra",
       f"{comandos()} {pre_bash()}")

    d = json.loads(alvo.read_text(encoding="utf-8"))
    d["hooks"]["PreToolUse"].append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guarda-alheia.sh"}]})
    alvo.write_text(json.dumps(d), encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", desligar, str(proj)])
    ok(r.returncode == 0 and not any("anchor.py" in c for c in comandos()),
       "desliga", str(comandos()))
    ok(not pre_bash() and comandos("PreToolUse") == ["guarda-alheia.sh"],
       "desliga o PreToolUse, e o PreToolUse alheio fica", str(comandos("PreToolUse")))
    r = subprocess.run([sys.executable, "-c", desligar, str(proj)])
    ok(r.returncode == 1, "e desligar o que ja saiu nao reescreve o arquivo")

    d = json.loads(alvo.read_text(encoding="utf-8"))
    ok("outro-hook.sh" in comandos(), "o hook de outra pessoa sobrevive aos quatro")
    ok(d["permissions"]["allow"] == ["Bash(ls:*)"], "e as permissions tambem")

    alvo.write_text("{ isto nao e json", encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", ligar, str(proj), "/pac"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok(r.returncode != 0 and alvo.read_text(encoding="utf-8") == "{ isto nao e json",
       "settings quebrado: recusa e NAO sobrescreve", r.stderr.strip())

    # ----------------------------------------------------------------------
    # A sessao que fala agora, gravada para o `flow_state` achar.
    #
    # E' a unica fonte autoritativa: nao ha variavel de ambiente com o id da
    # sessao, e adivinhar pelo transcrito mais recente seria heuristica onde
    # existe registro. Foi por falta disto que o custo de uma revisao inteira
    # foi parar na atividade VIZINHA, medido em 11/09/2026.
    print("\nA sessao que fala agora")
    t2 = Path(tempfile.mkdtemp()).resolve()
    (t2 / ".agents" / "atividades").mkdir(parents=True)
    r = subprocess.run([sys.executable, str(pathlib.Path(A.__file__)), "--raiz", str(t2)],
                       input=json.dumps({"session_id": "abc-123"}),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    marca = t2 / ".agents" / ".sessao-atual"
    ok(r.returncode == 0, "o hook responde 0 ao anotar a sessao")
    ok(marca.exists() and marca.read_text(encoding="utf-8") == "abc-123",
       "e grava o `session_id` que o harness entregou")

    r = subprocess.run([sys.executable, str(pathlib.Path(A.__file__)), "--raiz", str(t2)],
                       input="isto nao e' json", capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok(r.returncode == 0,
       "entrada invalida nao quebra o hook -- ele roda em TODA mensagem")
    ok(marca.read_text(encoding="utf-8") == "abc-123",
       "e nao destroi o que ja estava gravado")

    # ----------------------------------------------------------------------
    # O contexto que vai chamar o `flow_state`: sessao MAIS subagente. E' o
    # que a trava do step 9 compara -- no modo orquestrador o 8 e o 9 rodam na
    # mesma sessao, e o que os separa e' o `agent_id`.
    print("\nO contexto que vai chamar o flow_state")
    ctx = t2 / ".agents" / ".contexto-atual"

    def pre(evento, cwd=None):
        return subprocess.run(
            [sys.executable, str(pathlib.Path(A.__file__)), "--raiz",
             str(cwd or t2), "--contexto"],
            input=json.dumps(evento), capture_output=True, text=True,
            encoding="utf-8", errors="replace")

    r = pre({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    ok(r.returncode == 0 and not ctx.exists(), "sem `session_id` nao grava nada")
    r = pre({"session_id": "s1", "tool_name": "Bash", "agent_id": "ag-8",
             "tool_input": {"command": "python3 $F avancar 123 --nota x"}})
    gravado = json.loads(ctx.read_text(encoding="utf-8")) if ctx.exists() else {}
    ok(r.returncode == 0 and gravado.get("sessao") == "s1"
       and gravado.get("agente") == "ag-8" and gravado.get("quando"),
       "grava sessao, subagente e quando -- mesmo com o `$F` das skills, "
       "que nao cita o flow_state", str(gravado))
    ok(r.stdout == "" and r.stderr == "",
       "e cala: PreToolUse que fala aparece em toda chamada")
    pre({"session_id": "s1", "tool_name": "Read",
         "tool_input": {"command": "flow_state"}})
    ok(json.loads(ctx.read_text(encoding="utf-8")).get("agente") == "ag-8",
       "ferramenta que nao e' Bash nao troca o registro")
    pre({"session_id": "s1", "tool_name": "Bash",
         "tool_input": {"command": "python3 flow_state.py status 123"}})
    ok(json.loads(ctx.read_text(encoding="utf-8")).get("agente") == "",
       "a janela principal grava agente vazio")
    sub = t2 / "sub" / "dir"
    sub.mkdir(parents=True)
    ctx.unlink()
    pre({"session_id": "s2", "tool_name": "Bash", "cwd": str(sub),
         "tool_input": {"command": "flow_state status"}}, cwd="/")
    ok(ctx.exists() and json.loads(ctx.read_text(encoding="utf-8"))["sessao"] == "s2",
       "acha o .agents subindo do `cwd` do evento")
    r = pre({"tool_name": "Bash", "tool_input": "nao e' dict"})
    ok(r.returncode == 0, "evento torto nao quebra o hook")

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaca da ancora: tudo verde.")
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
