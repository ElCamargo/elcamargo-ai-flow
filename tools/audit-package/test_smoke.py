#!/usr/bin/env python3
"""Fumaça do auditor de pacote — o que ele DEVE pegar e o que NÃO pode.

Auditor que acusa demais é removido, e auditor que não acusa nada é decoração.
Cada verificação tem um caso plantado e um caso legítimo que se parece com ele.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_package as A  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


DESCRICAO = ("Descricao suficientemente longa para nao cair no aviso de "
             "descricao curta, porque e ela que decide se a skill dispara.")


def montar(raiz: Path, skills: dict, agentes: dict) -> None:
    shutil.rmtree(raiz, ignore_errors=True)
    for nome, corpo in skills.items():
        d = raiz / "skills" / nome
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(corpo, encoding="utf-8")
    (raiz / "agents").mkdir(parents=True, exist_ok=True)
    for nome, corpo in agentes.items():
        (raiz / "agents" / f"{nome}.md").write_text(corpo, encoding="utf-8")


def skill(nome: str, descricao: str = DESCRICAO, corpo: str = "# Procedimento\n") -> str:
    return f"---\nname: {nome}\ndescription: \"{descricao}\"\n---\n\n{corpo}"


def agente(nome: str, tools: str | None = "Read, Grep") -> str:
    linha = f"tools: {tools}\n" if tools is not None else ""
    return f"---\nname: {nome}\ndescription: {DESCRICAO}\n{linha}---\n\ncorpo\n"


def rodar(raiz: Path) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = A.main(["--raiz", str(raiz)])
    return codigo, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="auditar-"))

    print("O conjunto correto passa")
    montar(tmp, {"boa-skill": skill("boa-skill")}, {"bom-agente": agente("bom-agente")})
    codigo, saida = rodar(tmp)
    ok(codigo == 0 and "Nenhuma violação" in saida, "pacote limpo sai 0", saida)

    print("\nO que ela DEVE pegar")
    montar(tmp, {"nome-do-diretorio": skill("outro-nome")}, {})
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "deriva de nome" in saida,
       "nome do frontmatter diferente do diretório", saida)

    montar(tmp, {"sem-desc": skill("sem-desc", descricao="")}, {})
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "nunca dispara" in saida,
       "descrição vazia, com o motivo de importar", saida)

    montar(tmp, {"sem-fm": "# Sem frontmatter nenhum\n"}, {})
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "sem frontmatter" in saida, "arquivo sem frontmatter", saida)

    montar(tmp, {}, {"solto": agente("solto", tools=None)})
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "herda TODAS as ferramentas" in saida,
       "agente sem `tools` é acusado, e o motivo é a permissão implícita", saida)

    montar(tmp, {}, {"curinga": agente("curinga", tools="*")})
    codigo, saida = rodar(tmp)
    ok(codigo == 1 and "curinga" in saida, "`tools: *` é o mesmo que não declarar", saida)

    montar(tmp, {"gorda": skill("gorda", corpo="x" * 20000)}, {})
    codigo, saida = rodar(tmp)
    ok("acima de 12 KB" in saida, "skill acima do teto é apontada", saida)
    ok(codigo == 0, "mas tamanho não reprova — é medio, não alto", saida)

    print("\nO que ela NÃO PODE pegar")
    montar(tmp, {"no-limite": skill("no-limite", corpo="x" * 11000)}, {})
    codigo, saida = rodar(tmp)
    ok("acima de" not in saida, "skill logo abaixo do teto não é apontada", saida)

    montar(tmp, {}, {"lista-longa": agente("lista-longa", tools="Read, Grep, Glob, Bash")})
    codigo, saida = rodar(tmp)
    ok(codigo == 0, "lista de ferramentas explícita e longa não é curinga", saida)

    print("\nA saída declara o próprio limite")
    montar(tmp, {"boa-skill": skill("boa-skill")}, {})
    _, saida = rodar(tmp)
    ok("NÃO verifica" in saida and "descrição promete" in saida,
       "diz que não verifica se a skill faz o que promete", saida)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S)")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("tudo passou")
    return 0


if __name__ == "__main__":
    sys.exit(main())
