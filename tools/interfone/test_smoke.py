#!/usr/bin/env python3
"""O instalador do interfone, num HOME temporário: nunca encosta na máquina.

    python3 tools/interfone/test_smoke.py

Prova que o instalar.sh põe o programa, o comando e os três hooks no lugar, que
rodar duas vezes não duplica nada, que config e hooks de outra pessoa
sobrevivem, que settings ilegível não é reescrito, e que duas janelas
instaladas assim conversam de verdade. Sem `node`, sai com 0 dizendo que não
testou: o interfone não roda sem ele.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
INSTALAR = AQUI / "instalar.sh"
FALHAS: list[str] = []


def ok(cond: bool, nome: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {nome}")
    if not cond:
        FALHAS.append(nome)
        if detalhe:
            print(f"        {detalhe[:600]}")


def rodar(casa: Path, *args: str, entrada: str = "", cwd: Path | None = None,
          env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(casa), **(env_extra or {})}
    env.pop("INTERFONE_RAIZ", None)
    env.pop("INTERFONE_SESSAO", None)
    return subprocess.run(list(args), input=entrada, text=True, capture_output=True,
                          env=env, cwd=cwd)


def hooks_do_interfone(casa: Path) -> dict[str, list[str]]:
    dados = json.loads((casa / ".claude" / "settings.json").read_text(encoding="utf-8"))
    fora: dict[str, list[str]] = {}
    for evento, entradas in dados.get("hooks", {}).items():
        for e in entradas:
            for h in e.get("hooks", []):
                if "interfone" in h.get("command", ""):
                    fora.setdefault(evento, []).append(h["command"])
    return fora


def main() -> int:
    if not shutil.which("node"):
        print("  [pulado] sem node no PATH: o interfone não roda sem ele")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        print("instalação limpa")
        casa = tmp / "casa"
        casa.mkdir()
        r = rodar(casa, "bash", str(INSTALAR))
        ok(r.returncode == 0, "o instalador termina com 0", r.stdout + r.stderr)
        prog = casa / ".interfone" / "interfone.mjs"
        ok(prog.is_file() and prog.read_bytes() == (AQUI / "interfone.mjs").read_bytes(),
           "o programa é a cópia do pacote")
        cfg = json.loads((casa / ".interfone" / "config.json").read_text(encoding="utf-8"))
        ok(cfg == {"raiz": "~/.interfone/dados"}, "os dados vão para ~/.interfone/dados", str(cfg))
        lancador = casa / ".local" / "bin" / "interfone"
        ok(lancador.is_file() and os.access(lancador, os.X_OK), "o comando é executável")
        hooks = hooks_do_interfone(casa)
        ok(sorted(hooks) == ["SessionEnd", "SessionStart", "UserPromptSubmit"]
           and all(len(v) == 1 for v in hooks.values()),
           "um hook em cada um dos três eventos", str(hooks))

        print("de novo, por cima")
        r = rodar(casa, "bash", str(INSTALAR))
        ok(r.returncode == 0 and "já estavam" in r.stdout, "rodar de novo diz que já estavam",
           r.stdout + r.stderr)
        ok(all(len(v) == 1 for v in hooks_do_interfone(casa).values()), "e não duplica")
        ok(not list((casa / ".interfone").glob("*.anterior-*")),
           "programa igual não gera cópia .anterior")

        print("quem já usa: config, hooks e settings alheios")
        casa2 = tmp / "casa2"
        (casa2 / ".interfone").mkdir(parents=True)
        (casa2 / ".claude").mkdir()
        (casa2 / ".interfone" / "config.json").write_text('{"raiz": "/outro/lugar"}\n')
        (casa2 / ".interfone" / "interfone.mjs").write_text("// versão velha\n")
        (casa2 / ".claude" / "settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls:*)"]},
            "hooks": {
                "UserPromptSubmit": [{"hooks": [
                    {"type": "command", "command": "outro-hook.sh"},
                    {"type": "command", "command": '"$HOME/.local/bin/interfone" hook mensagem'},
                ]}],
            },
        }))
        r = rodar(casa2, "bash", str(INSTALAR))
        ok(r.returncode == 0, "instala por cima de quem já usa", r.stdout + r.stderr)
        ok(json.loads((casa2 / ".interfone" / "config.json").read_text())["raiz"] == "/outro/lugar",
           "config.json existente é mantido: as caixas continuam onde estavam")
        ok(len(list((casa2 / ".interfone").glob("interfone.mjs.anterior-*"))) == 1,
           "o programa antigo, diferente, vira .anterior")
        dados = json.loads((casa2 / ".claude" / "settings.json").read_text())
        ok(dados.get("permissions") == {"allow": ["Bash(ls:*)"]}, "as permissions sobrevivem")
        comandos = [h["command"] for e in dados["hooks"]["UserPromptSubmit"] for h in e["hooks"]]
        ok("outro-hook.sh" in comandos, "o hook de outra pessoa sobrevive", str(comandos))
        ok(sum("interfone" in c for c in comandos) == 1 and any(c.startswith("[ ! -x") for c in comandos),
           "o hook antigo do interfone é reapontado, e não duplicado", str(comandos))

        print("settings ilegível")
        casa3 = tmp / "casa3"
        (casa3 / ".claude").mkdir(parents=True)
        quebrado = '{"hooks": {'
        (casa3 / ".claude" / "settings.json").write_text(quebrado)
        r = rodar(casa3, "bash", str(INSTALAR))
        ok(r.returncode != 0 and "ilegível" in r.stderr, "recusa e diz por quê", r.stdout + r.stderr)
        ok((casa3 / ".claude" / "settings.json").read_text() == quebrado, "e não reescreve o arquivo")

        print("--sem-hooks e --dados")
        casa4 = tmp / "casa4"
        casa4.mkdir()
        equipe = tmp / "dados da equipe"
        r = rodar(casa4, "bash", str(INSTALAR), "--sem-hooks", "--dados", str(equipe))
        ok(r.returncode == 0 and not (casa4 / ".claude" / "settings.json").exists(),
           "--sem-hooks não cria o settings", r.stdout + r.stderr)
        ok(json.loads((casa4 / ".interfone" / "config.json").read_text())["raiz"] == str(equipe) and equipe.is_dir(),
           "--dados vai para o config.json, e a pasta é criada")

        print("o hook com o comando apagado")
        for evento, cmds in hooks_do_interfone(casa).items():
            r = rodar(tmp / "casa-sem-nada", "sh", "-c", cmds[0], entrada="{}")
            ok(r.returncode == 0 and not r.stderr, f"{evento}: sem o comando, cala com 0",
               f"{r.returncode} {r.stderr}")

        print("duas janelas conversando, pelo comando instalado")
        repo_a, repo_b = tmp / "repo-a", tmp / "repo-b"
        for repo in (repo_a, repo_b):
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        i = str(lancador)
        evento_b = json.dumps({"cwd": str(repo_b), "session_id": "b1", "source": "startup"})
        r = rodar(casa, "sh", "-c", hooks_do_interfone(casa)["SessionStart"][0],
                  entrada=evento_b, cwd=repo_b)
        ok(r.returncode == 0 and "PERGUNTE" in r.stdout,
           "janela nova: o hook manda perguntar se entra", r.stdout + r.stderr)
        r1 = rodar(casa, i, "entrar", "alfa", "--novo", "--sessao", "repo-a-a1", cwd=repo_a)
        r2 = rodar(casa, i, "entrar", "beta", "--novo", "--sessao", "repo-b-b1", cwd=repo_b)
        ok(r1.returncode == 0 and r2.returncode == 0 and (repo_a / ".interfone.json").is_file(),
           "entrar --novo cria o papel e grava o .interfone.json", r1.stdout + r1.stderr)
        r = rodar(casa, i, "ligar", "alfa", "beta", "--mao-dupla")
        ok(r.returncode == 0, "ligar alfa e beta", r.stdout + r.stderr)
        r = rodar(casa, i, "enviar", "alfa", "beta", "teste do instalador", "--sessao", "repo-a-a1",
                  entrada="corpo da mensagem\n")
        ok(r.returncode == 0 and "enviado" in r.stdout, "alfa envia para beta", r.stdout + r.stderr)
        evento_b = json.dumps({"cwd": str(repo_b), "session_id": "b1"})
        r = rodar(casa, "sh", "-c", hooks_do_interfone(casa)["UserPromptSubmit"][0],
                  entrada=evento_b, cwd=repo_b)
        ok(r.returncode == 0 and "teste do instalador" in r.stdout,
           "e o hook de mensagem entrega a caixa na janela de beta", r.stdout + r.stderr)
        ok((casa / ".interfone" / "dados" / "beta" / "inbox").is_dir(),
           "a mensagem mora em ~/.interfone/dados")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} FALHA(S): " + "; ".join(FALHAS))
        return 1
    print("tudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
