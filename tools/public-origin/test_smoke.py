#!/usr/bin/env python3
"""Fumaça do public_origin: um servidor que respeita a origem pública e um que vaza."""
from __future__ import annotations

import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import public_origin as P  # noqa: E402

FERRAMENTA = AQUI / "public_origin.py"
PUBLICA = "https://app.exemplo.test"
falhas: list[str] = []


def checar(cond: bool, descricao: str) -> None:
    print(f"  [{'ok  ' if cond else 'FALHA'}] {descricao}")
    if not cond:
        falhas.append(descricao)


class Base(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, status: int, location: str | None = None, corpo: str = "") -> None:
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        dados = corpo.encode()
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


class Respeita(Base):
    """Monta o endereço pelo X-Forwarded-*, como o conserto do 1093."""
    def do_GET(self):
        proto = self.headers.get("X-Forwarded-Proto", "http")
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host")
        if self.path == "/sair":
            self.responder(307, f"{proto}://{host}/login")
        elif self.path == "/relativo":
            self.responder(302, "/login")
        else:
            self.responder(200, corpo=f'<a href="{proto}://{host}/x">x</a>'
                                      '<img src="https://cdn.outro.test/a.png">')


class Vaza(Base):
    """Monta o endereço pelo socket, como o `request.url` do build standalone."""
    def do_GET(self):
        escuta = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
        if self.path == "/sair":
            self.responder(307, f"{escuta}/login")
        elif self.path == "/zero":
            self.responder(307, "http://0.0.0.0:3000/login")
        else:
            self.responder(200, corpo='<a href="http://app-web:3000/confirmar">confirmar</a>')


def subir(classe) -> tuple[ThreadingHTTPServer, str]:
    s = ThreadingHTTPServer(("127.0.0.1", 0), classe)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


def rodar(*args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(FERRAMENTA), *args],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    print("O que é de dentro")
    escuta = ("http", "127.0.0.1", 3900)
    checar(P.de_dentro("http://0.0.0.0:3000/x", escuta) is not None, "0.0.0.0 é de dentro")
    checar(P.de_dentro("http://localhost/x", escuta) is not None, "localhost é de dentro")
    checar(P.de_dentro("http://app-web:3000/x", escuta) is not None,
           "nome de serviço sem domínio é de dentro")
    checar(P.de_dentro("http://[::1]:3000/x", escuta) is not None, "[::1] é de dentro")
    checar(P.de_dentro("https://app.exemplo.test/x", escuta) is None, "a origem pública não é")
    checar(P.de_dentro("https://cdn.outro.test/a.png", escuta) is None,
           "outro domínio público não é vazamento")
    checar(P.de_dentro("mailto:a@b.test", escuta) is None, "mailto não é endereço de rede")

    print("\nServidor que respeita a origem pública")
    s, url = subir(Respeita)
    try:
        rc, saida = rodar("conferir", "--escuta", url, "--publica", PUBLICA,
                          "--rota", "/", "--rota", "/sair", "--rota", "/relativo")
        checar(rc == 0, f"sai 0 (saiu {rc})")
        checar("[VAZA]" not in saida, "nenhuma rota marcada")
        rc, saida = rodar("conferir", "--escuta", url, "--publica", PUBLICA,
                          "--rota", "/sair", "--sem-encaminhamento")
        checar(rc == 1 and "sai da origem pública" in saida,
               "sem X-Forwarded-Proto o esquema cai para http, e isso é marcado")
    finally:
        s.shutdown()

    print("\nServidor que vaza o endereço de escuta")
    s, url = subir(Vaza)
    try:
        rc, saida = rodar("conferir", "--escuta", url, "--publica", PUBLICA,
                          "--rota", "/sair", "--rota", "/zero", "--rota", "/")
        checar(rc == 1, f"sai 1 (saiu {rc})")
        checar(saida.count("[VAZA]") == 3, "as três rotas marcadas")
        checar("endereço de escuta" in saida, "o Location do socket é nomeado")
        checar("0.0.0.0" in saida, "o 0.0.0.0 do contêiner é nomeado")
        checar("app-web" in saida, "o link do corpo com nome de serviço é nomeado")
    finally:
        s.shutdown()

    print("\nServidor fora do ar")
    rc, saida = rodar("conferir", "--escuta", url, "--publica", PUBLICA, "--timeout", "2")
    checar(rc == 2, f"sai 2, e não 1 (saiu {rc})")
    checar("NÃO COBERTA" in saida, "diz que a dimensão fica não coberta")

    rc, saida = rodar("conferir", "--escuta", "127.0.0.1:3900", "--publica", PUBLICA)
    checar(rc == 2, "URL sem esquema é recusada")

    print()
    if falhas:
        print(f"{len(falhas)} falha(s).")
        return 1
    print("tudo ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
