#!/usr/bin/env python3
"""Confere que o servidor, atrás de um host público, não vaza o endereço de dentro.

Medido no app em 30/09/2026 (Bug 1093): um redirecionamento do servidor
Next montado a partir do `request.url` passou pelo step 9 e chegou ao QA. No
build standalone, atrás do proxy, o `Location` carregava o endereço de escuta
do contêiner (`0.0.0.0:3000`), e o navegador recebia 502. Na máquina de quem
revisa, o endereço do processo e o do navegador são o mesmo, e o defeito é
invisível por construção. Foi a segunda vez em três semanas: em 07/09 o link de
um e-mail saiu com o nome interno do serviço (1061).

    public_origin.py conferir --escuta http://127.0.0.1:3900 \\
        --publica https://app.exemplo.test [--rota /login --rota 'POST /sair']

Para cada rota, pede ao endereço de escuta **como se viesse do proxy**
(`Host`, `X-Forwarded-Host`, `X-Forwarded-Proto` da origem pública), sem seguir
redirecionamento, e confere:

- o `Location` de todo 3xx: relativo passa; absoluto tem de ser a origem pública;
- os links absolutos do corpo HTML (`href`, `src`, `action`, `content`): os que
  apontam para endereço de dentro são vazamento.

"De dentro" é: o host e a porta de escuta, `0.0.0.0`, `localhost`,
`127.0.0.1`, `[::]`, `[::1]`, e host sem ponto (nome de serviço de contêiner,
como `app-web`). Link para outro domínio público passa: não é da origem,
mas também não é vazamento.

Sai 1 se houver vazamento, 2 se o servidor não respondeu.

**O que ela não prova:** que o proxy de produção manda esses mesmos cabeçalhos.
Ela reproduz o que um proxy comum manda; se o de produção não manda
`X-Forwarded-Host`, rode também com `--sem-encaminhamento`, que manda só o
`Host`. E ela não vê link montado no navegador, por JavaScript: esse é da
passada na tela.
"""
from __future__ import annotations

import argparse
import http.client
import re
import sys
from urllib.parse import urljoin, urlsplit

INTERNOS = {"0.0.0.0", "localhost", "127.0.0.1", "::", "::1"}
LINK = re.compile(r"""(?:href|src|action|content)\s*=\s*["']([a-zA-Z][a-zA-Z0-9+.-]*://[^"'\s>]+)""", re.I)


def origem(url: str) -> tuple[str, str, int]:
    p = urlsplit(url)
    if not p.scheme or not p.hostname:
        raise ValueError(f"não é uma URL absoluta: {url}")
    porta = p.port or (443 if p.scheme == "https" else 80)
    return p.scheme, p.hostname.lower(), porta


def de_dentro(url: str, escuta: tuple[str, str, int]) -> str | None:
    """A razão de o endereço ser de dentro, ou None se não for."""
    try:
        esquema, host, porta = origem(url)
    except ValueError:
        return None
    if esquema not in ("http", "https"):
        return None
    if (host, porta) == (escuta[1], escuta[2]):
        return "o endereço de escuta do servidor"
    if host in INTERNOS:
        return f"host interno `{host}`"
    if "." not in host:
        return f"host sem domínio `{host}`, com cara de nome de serviço"
    return None


def pedir(escuta: str, metodo: str, rota: str, publica: str, encaminhar: bool,
          timeout: float) -> tuple[int, dict[str, str], str]:
    _, host, porta = origem(escuta)
    p_esquema, p_host, p_porta = origem(publica)
    padrao = 443 if p_esquema == "https" else 80
    cabeca_host = p_host if p_porta == padrao else f"{p_host}:{p_porta}"
    cabecalhos = {"Host": cabeca_host, "Accept": "text/html,*/*"}
    if encaminhar:
        cabecalhos.update({"X-Forwarded-Host": cabeca_host, "X-Forwarded-Proto": p_esquema,
                           "X-Forwarded-Port": str(p_porta)})
    classe = http.client.HTTPSConnection if urlsplit(escuta).scheme == "https" else http.client.HTTPConnection
    conexao = classe(host, porta, timeout=timeout)
    try:
        conexao.request(metodo, rota, headers=cabecalhos)
        r = conexao.getresponse()
        corpo = r.read(2_000_000).decode("utf-8", errors="replace")
        return r.status, {k.lower(): v for k, v in r.getheaders()}, corpo
    finally:
        conexao.close()


def conferir_resposta(status: int, cabecalhos: dict[str, str], corpo: str, publica: str,
                      escuta: tuple[str, str, int]) -> list[str]:
    achados = []
    local = cabecalhos.get("location")
    if 300 <= status < 400 and local:
        absoluto = urljoin(publica, local)
        razao = de_dentro(absoluto, escuta)
        if razao:
            achados.append(f"Location `{local}` aponta para {razao}")
        elif urlsplit(local).scheme and origem(absoluto)[:2] != origem(publica)[:2]:
            achados.append(f"Location `{local}` sai da origem pública `{publica}`")
    if "html" in cabecalhos.get("content-type", ""):
        vistos = set()
        for m in LINK.finditer(corpo):
            url = m.group(1)
            razao = de_dentro(url, escuta)
            if razao and url not in vistos:
                vistos.add(url)
                achados.append(f"link `{url}` no corpo aponta para {razao}")
    return achados


def cmd_conferir(args) -> int:
    escuta = origem(args.escuta)
    origem(args.publica)
    rotas = args.rota or ["/"]
    vazou = falhou = 0
    print(f"escuta {args.escuta} · origem pública {args.publica}"
          f"{'' if args.encaminhar else ' · só o Host, sem X-Forwarded-*'}\n")
    for item in rotas:
        metodo, _, rota = item.partition(" ") if " " in item else ("GET", "", item)
        try:
            status, cab, corpo = pedir(args.escuta, metodo.upper(), rota, args.publica,
                                       args.encaminhar, args.timeout)
        except (OSError, http.client.HTTPException) as e:
            print(f"  [SEM RESPOSTA] {metodo} {rota}: {e}")
            falhou += 1
            continue
        achados = conferir_resposta(status, cab, corpo, args.publica, escuta)
        rotulo = f"{metodo} {rota} → {status}" + (f" {cab['location']}" if cab.get("location") else "")
        if achados:
            vazou += 1
            print(f"  [VAZA] {rotulo}")
            for a in achados:
                print(f"         {a}")
        else:
            print(f"  [ok]   {rotulo}")
    print()
    if vazou:
        print(f"{vazou} rota(s) vazam o endereço de dentro. Atrás do proxy, o navegador vai a "
              "um endereço que ele não alcança.")
        return 1
    if falhou:
        print("O servidor não respondeu. Isso é ambiente, e a dimensão fica NÃO COBERTA; "
              "não reprove a entrega por isso.")
        return 2
    print("nenhuma rota vaza o endereço de dentro.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("conferir", help="pede como o proxy e confere Location e links absolutos")
    c.add_argument("--escuta", required=True, help="onde o build de produção escuta, ex. http://127.0.0.1:3900")
    c.add_argument("--publica", required=True, help="a origem que o navegador vê, ex. https://app.exemplo.test")
    c.add_argument("--rota", action="append", help="'/caminho' ou 'METODO /caminho'; repetível. Padrão: /")
    c.add_argument("--sem-encaminhamento", dest="encaminhar", action="store_false",
                   help="manda só o Host, sem X-Forwarded-*")
    c.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args(argv)
    try:
        return cmd_conferir(args)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Windows: com a saída em pipe, `print` usa cp1252 e estoura em `→`.
    # Ver `references/windows.md`.
    for _fluxo in (sys.stdout, sys.stderr):
        if hasattr(_fluxo, "reconfigure"):
            try:
                _fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    sys.exit(main())
