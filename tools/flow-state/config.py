#!/usr/bin/env python3
"""Read the project configuration that parameterises the flow for one project.

The package knows nothing about any project. Everything project-specific comes
from `<.agents>/config.toml` — see `config.example.toml`. Skills read it through
this module so that a missing key fails in one place, with one message, instead
of each skill inventing its own default.

Stdlib only: `tomllib` ships with Python since 3.11.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

# Importable both as a script and as a module from another directory: a skill
# calling `import config` should not have to know where this file lives.
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from flow_state import FlowStateError, resolve_agents_dir  # noqa: E402

CONFIG_NAME = "config.toml"

# One read per file per process. Seven skills each reading several keys would
# otherwise reparse the TOML dozens of times per step, and could see the file
# change halfway through a single step.
_cache: dict[Path, tuple[float, dict[str, Any]]] = {}


def config_path(agents: Path | None = None) -> Path:
    return (agents or resolve_agents_dir()) / CONFIG_NAME


def carregar(agents: Path | None = None) -> dict[str, Any]:
    path = config_path(agents)
    if not path.exists():
        raise FlowStateError(
            f"Não encontrei {path}. Copie elcamargo-flow/config.example.toml "
            "para lá e ajuste antes de rodar o fluxo."
        )
    marca = path.stat().st_mtime
    if path in _cache and _cache[path][0] == marca:
        return _cache[path][1]
    try:
        dados = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise FlowStateError(f"{path} não é TOML válido: {exc}") from exc
    _cache[path] = (marca, dados)
    return dados


def obter(caminho: str, padrao: Any = None, agents: Path | None = None) -> Any:
    """Read one value by dotted path, e.g. `gates.visual`.

    Returns `padrao` when the key is absent or empty. An empty string in the
    config means "this project does not declare it", which is different from a
    missing section and is handled the same way on purpose: the caller decides
    what to do without a declaration.
    """
    atual: Any = carregar(agents)
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    if atual == "" or atual == []:
        return padrao
    return atual


# Pastas que nenhuma varredura precisa ler. A lista estava HARDCODED em dois
# lugares, com conteúdos diferentes que ninguém tinha decidido: `domain.py`
# excluía `build` e os lockfiles, `already_exists.py` excluía `.next`. Duas listas que
# deveriam ser uma divergiram em silêncio — a mesma família do parser de front
# matter duplicado, que fez o conserto ser aplicado no arquivo errado.
#
# Isto NÃO é segurança: é ruído. Um `git grep` que entra em `node_modules`
# devolve mil arquivos de dependência onde o sinal eram três do projeto. O que o
# agente pode LER se controla noutro lugar — ver `references/leitura.md`.
IGNORAR_PADRAO = ["node_modules", "dist", "build", ".next", "out", "coverage",
                  ".turbo"]


def versao(pacote: Path | None = None) -> str:
    """A versão do pacote, lida do arquivo `VERSION` na raiz dele.

    Num arquivo próprio, e não só no `plugin.json`, porque o pacote existe de
    duas formas: instalado como plugin, e copiado dentro do `.agents` de um
    projeto. A cópia não leva o `.claude-plugin/`, e ficaria sem versão nenhuma
    — que é pior que ter uma velha, porque não dá nem para comparar.
    """
    raiz = pacote or Path(__file__).resolve().parents[2]
    try:
        return (raiz / "VERSION").read_text(encoding="utf-8").strip() or "?"
    except OSError:
        return "?"


def copias_do_pacote(raiz_do_projeto: Path) -> list[tuple[str, Path, str]]:
    """Onde o pacote está, na MESMA ordem em que as skills o procuram.

    Devolve (origem, caminho, versão). A primeira da lista é a que vence — e é
    justamente isso que ninguém enxerga quando há mais de uma: o projeto pode
    ter uma cópia em `.agents` e o plugin instalado, e usar a cópia sem saber.
    """
    achadas: list[tuple[str, Path, str]] = []
    copia = raiz_do_projeto / ".agents" / "elcamargo-flow"
    if copia.is_dir():
        achadas.append(("cópia em .agents", copia, versao(copia)))
    # SÓ a versão mais nova do cache, porque é só ela que as skills usam:
    # elas resolvem com `ls -d .../elcamargo-ai-flow/*/ | sort -V | tail -1`.
    #
    # `claude plugin update` NÃO apaga a versão anterior — o cache guarda
    # 1.0.0, 1.0.1, 1.0.2... lado a lado. Listar todas fazia o doutor gritar
    # `[ALTO] versões DIFERENTES` logo depois de uma atualização bem-sucedida,
    # acusando de divergência o que é só histórico inerte. Medido no minuto
    # seguinte ao push do 1.0.4.
    cache = Path.home() / ".claude" / "plugins" / "cache"
    versoes = sorted(cache.glob("*/elcamargo-ai-flow/*/VERSION"),
                     key=lambda m: _ordem(m.parent.name))
    if versoes:
        alvo = versoes[-1].parent
        achadas.append(("plugin instalado", alvo, versao(alvo)))
    return achadas


def _ordem(nome: str) -> tuple:
    """Ordena `1.0.10` DEPOIS de `1.0.9` — o que a ordem alfabética não faz."""
    return tuple(int(p) if p.isdigit() else -1 for p in nome.split("."))


def pathspec_ignorar(extras: list[str] | None = None,
                     agents: Path | None = None) -> list[str]:
    """Os `:!*pasta*` para passar ao `git grep`/`git ls-files`.

    `extras` é o que a ferramenta exclui por razão PRÓPRIA — `ja_existe` não
    quer documentação porque procura comportamento em código, e isso não é
    ruído para as outras. Achatar as duas coisas numa lista só perderia a
    diferença.
    """
    try:
        pastas = obter("leitura.ignorar", IGNORAR_PADRAO, agents)
    except Exception:  # noqa: BLE001  — sem config, o padrão serve
        pastas = IGNORAR_PADRAO
    return [f":!*{p}*" for p in pastas] + list(extras or [])


def exigir(caminho: str, agents: Path | None = None) -> Any:
    """Read a value the flow cannot proceed without."""
    valor = obter(caminho, None, agents)
    if valor is None:
        raise FlowStateError(
            f"`{caminho}` não está declarado em {config_path(agents)}. "
            "O fluxo não pode seguir adivinhando esse valor."
        )
    return valor


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="config.py",
        description="Lê o config.toml do projeto.",
    )
    p.add_argument("caminho", nargs="?",
                   help="chave em notação de ponto, ex: gates.visual. "
                        "Sem isso, imprime o config inteiro em JSON.")
    p.add_argument("--exigir", action="store_true",
                   help="falha se a chave não estiver declarada")
    args = p.parse_args(argv)

    try:
        if not args.caminho:
            print(json.dumps(carregar(), indent=2, ensure_ascii=False))
            return 0
        valor = exigir(args.caminho) if args.exigir else obter(args.caminho)
        if valor is None:
            return 1  # not declared; caller decides, no noise on stdout
        print(valor if isinstance(valor, str) else
              json.dumps(valor, ensure_ascii=False))
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
