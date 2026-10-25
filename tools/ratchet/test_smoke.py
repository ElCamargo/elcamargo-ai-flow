#!/usr/bin/env python3
"""Fumaça de ratchet.py — contra saída real, e nos dois sentidos.

As três amostras de saída deste arquivo não foram escritas de memória: saíram de
rodar vitest, jest e eslint neste projeto com uma falha de mentira. É a diferença
entre um parser que funciona e um que parece funcionar.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ratchet as C  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class Args:
    def __init__(self, **kw):
        self.__dict__.setdefault("padrao", "")
        self.__dict__.setdefault("formato", "")
        self.__dict__.setdefault("raiz", ".")
        self.__dict__.setdefault("registrar", "")
        self.__dict__.setdefault("comando", "")
        self.__dict__.setdefault("admitir", "")
        self.__dict__.update(kw)


def rodar(fn, **kw) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = fn(Args(**kw))
    return codigo, buf.getvalue()


# Saída de `npx vitest run` neste projeto, recortada.
VITEST = """ RUN  v4.1.10 /repo/frontend

 ❯ amostra.spec.ts (2 tests | 1 failed) 3ms
     × falha de proposito 2ms

⎯⎯⎯ Failed Tests 1 ⎯⎯⎯

 FAIL  amostra.spec.ts > catraca amostra > falha de proposito
AssertionError: expected 1 to be 2 // Object.is equality

 Test Files  1 failed (1)
      Tests  1 failed | 1 passed (2)
"""

# Saída de `npx jest` neste projeto, recortada.
JEST = """FAIL apps/api/src/amostra.spec.ts
  ● catraca amostra › falha de proposito

    expect(received).toBe(expected) // Object.is equality

      at Object.<anonymous> (apps/api/src/amostra.spec.ts:2:46)

Test Suites: 1 failed, 1 total
Tests:       1 failed, 1 passed, 2 total
"""

# Saída de `npx eslint components/app-shell.tsx`, verbatim.
ESLINT = ("/repo/frontend/components/app-shell.tsx\n"
          "  185:5  warning  Do not use `window.location.href` to navigate to internal"
          " Next.js pages. Use `redirect()` in the render phase, or `useRouter().push()`"
          " in Client Components' event handlers instead. See:"
          " https://nextjs.org/docs/messages/no-location-assign-relative-destination"
          "  @next/next/no-location-assign-relative-destination\n"
          "\n"
          "✖ 1 problem (0 errors, 1 warning)\n")

REGRA = "components/app-shell.tsx :: @next/next/no-location-assign-relative-destination"



# Saída real de `npx lighthouse@latest` (13.4.1) contra uma página deste
# projeto quebrada de propósito: sem `<title>`, sem `lang`, imagem sem `alt`,
# botão sem nome, contraste ruim. Recortada, nunca reescrita — a mesma regra
# das três amostras acima.
#
# Ela carrega de propósito os quatro casos que NÃO são falha de catraca, e o
# último é o perigoso: `unsized-images` parece falha, É defeito real, e tem
# score CONTÍNUO (0.5). Catraca em medida contínua oscila.
LIGHTHOUSE = """{
  "lighthouseVersion": "13.4.1",
  "finalDisplayedUrl": "http://127.0.0.1:8731/grupos",
  "categories": {
    "performance":    {"id": "performance",    "score": 1},
    "accessibility":  {"id": "accessibility",  "score": 0.23},
    "best-practices": {"id": "best-practices", "score": 0.96},
    "seo":            {"id": "seo",            "score": 0.73}
  },
  "audits": {
    "color-contrast":    {"id": "color-contrast",    "score": 0, "scoreDisplayMode": "binary",
                          "title": "Background and foreground colors do not have a sufficient contrast ratio."},
    "image-alt":         {"id": "image-alt",         "score": 0, "scoreDisplayMode": "binary",
                          "title": "Image elements do not have `[alt]` attributes"},
    "label":             {"id": "label",             "score": 0, "scoreDisplayMode": "binary",
                          "title": "Form elements do not have associated labels"},
    "html-has-lang":     {"id": "html-has-lang",     "score": 0, "scoreDisplayMode": "binary",
                          "title": "`<html>` element does not have a `[lang]` attribute"},
    "document-title":    {"id": "document-title",    "score": 0, "scoreDisplayMode": "binary",
                          "title": "Document doesn't have a `<title>` element"},
    "meta-description":  {"id": "meta-description",  "score": 0, "scoreDisplayMode": "binary",
                          "title": "Document does not have a meta description"},
    "is-on-https":       {"id": "is-on-https",       "score": 1, "scoreDisplayMode": "binary",
                          "title": "Uses HTTPS"},
    "largest-contentful-paint": {"id": "largest-contentful-paint", "score": 1,
                          "scoreDisplayMode": "numeric", "title": "Largest Contentful Paint"},
    "final-screenshot":  {"id": "final-screenshot",  "score": 1, "scoreDisplayMode": "informative",
                          "title": "Final Screenshot"},
    "redirects-http":    {"id": "redirects-http",    "score": null, "scoreDisplayMode": "notApplicable",
                          "title": "Redirects HTTP traffic to HTTPS"},
    "custom-controls-labels": {"id": "custom-controls-labels", "score": null,
                          "scoreDisplayMode": "manual", "title": "Custom controls have associated labels"},
    "unsized-images":    {"id": "unsized-images",    "score": 0.5, "scoreDisplayMode": "metricSavings",
                          "title": "Image elements do not have explicit `width` and `height`"}
  }
}"""

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="catraca-"))
    raiz = Path("/repo/frontend")

    # ----------------------------------------------------------------
    print("\nOs três formatos, contra a saída que os runners realmente imprimem")
    v = C.extrair(VITEST, "vitest", raiz, None)
    ok(v == {"amostra.spec.ts > catraca amostra > falha de proposito": 1},
       "vitest: um teste, com arquivo, suíte e nome", str(v))

    j = C.extrair(JEST, "jest", raiz, None)
    ok(j == {"apps/api/src/amostra.spec.ts > catraca amostra > falha de proposito": 1},
       "jest: o arquivo vem do FAIL, o nome vem do bullet", str(j))

    e = C.extrair(ESLINT, "eslint", raiz, None)
    ok(e == {REGRA: 1}, "eslint: arquivo e regra, e a mensagem fica de fora", str(e))
    ok(not any(c.isdigit() for c in list(e)[0].split("::")[0]),
       "e a linha 185 não entra na identidade", str(e))

    print("\nNenhum dos três confunde o rodapé de resumo com falha")
    for nome, texto, formato in (("vitest", VITEST, "vitest"),
                                 ("jest", JEST, "jest"),
                                 ("eslint", ESLINT, "eslint")):
        r = C.extrair(texto, formato, raiz, None)
        ok(len(r) == 1, f"{nome}: exatamente uma falha, não o sumário junto", str(r))

    print("\nSaída limpa não produz falha nenhuma")
    for formato, limpo in (("vitest", " Test Files  1 passed (1)\n      Tests  9 passed (9)\n"),
                           ("jest", "PASS apps/api/src/a.spec.ts\n\nTests: 9 passed, 9 total\n"),
                           ("eslint", "")):
        ok(C.extrair(limpo, formato, raiz, None) == {},
           f"{formato}: portão verde é conjunto vazio")

    print("\nA mesma regra duas vezes no mesmo arquivo conta duas")
    dobrado = ESLINT.replace("\n\n✖", "\n  9:1  warning  Outra coisa aqui"
                             "  @next/next/no-location-assign-relative-destination\n\n✖")
    ok(C.extrair(dobrado, "eslint", raiz, None) == {REGRA: 2},
       "lint conta ocorrência, porque a regra reincide", str(C.extrair(dobrado, "eslint", raiz, None)))

    # ----------------------------------------------------------------
    print("\nGravar a base, e o que ela protege")
    base = tmp / "catraca.json"
    entrada = tmp / "lint.txt"
    entrada.write_text(ESLINT, encoding="utf-8")
    codigo, saida = rodar(C.cmd_gravar, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz),
                          comando="npm run lint")
    ok(codigo == 0 and "1 falha(s) conhecida(s)" in saida, "grava a base", saida)
    dados = json.loads(base.read_text(encoding="utf-8"))
    ok(dados["portoes"]["lint"]["falhas"] == {REGRA: 1}, "com a identidade certa", str(dados))

    codigo, saida = rodar(C.cmd_gravar, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 1 and "já tem linha de base" in saida,
       "e regravar por cima é recusado — seria o jeito de a catraca afrouxar", saida)

    # ----------------------------------------------------------------
    print("\nA mesma falha, com o arquivo deslocado nove linhas")
    movido = ESLINT.replace("185:5", "176:5")
    entrada.write_text(movido, encoding="utf-8")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 0, "não reprova: é o mesmo aviso, noutra linha", saida)
    ok("0 nova(s), 1 conhecida(s)" in saida, "e é contada como conhecida", saida)

    print("\nUma falha nova no mesmo arquivo reprova")
    nova = ESLINT.replace("\n\n✖", "\n  12:3  error  Sem isto  regra/inventada\n\n✖")
    entrada.write_text(nova, encoding="utf-8")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 1 and "falha nova (1)" in saida, "reprova", saida)
    ok("regra/inventada" in saida, "e diz qual é", saida)
    ok("1 nova(s), 1 conhecida(s)" in saida, "sem misturar com o passivo", saida)

    print("\nA mesma regra, mais vezes que antes, também reprova")
    entrada.write_text(dobrado, encoding="utf-8")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 1 and "aumentou (1)" in saida and "1 → 2" in saida,
       "de uma para duas ocorrências é regressão", saida)

    # ----------------------------------------------------------------
    print("\nO que faz dela catraca: ela só aperta")
    entrada.write_text("✖ 0 problems\n", encoding="utf-8")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 0 and "[APERTA]" in saida, "conserto conhecido pede aperto", saida)
    ok("ratchet.py apertar" in saida, "e imprime o comando", saida)

    codigo, saida = rodar(C.cmd_apertar, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 0 and "1 → 0 falha(s)" in saida, "a base encolhe", saida)
    dados = json.loads(base.read_text(encoding="utf-8"))
    ok(dados["portoes"]["lint"]["falhas"] == {}, "e fica vazia", str(dados))

    print("\nE o mesmo aviso, voltando depois, agora reprova")
    entrada.write_text(ESLINT, encoding="utf-8")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 1 and "falha nova (1)" in saida,
       "o que saiu da base não volta em silêncio", saida)

    print("\nApertar não é o caminho para admitir falha nova")
    codigo, saida = rodar(C.cmd_apertar, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok(codigo == 1 and "NÃO entraram na base" in saida,
       "apertar recusa crescer, e diz por quê", saida)
    dados = json.loads(base.read_text(encoding="utf-8"))
    ok(dados["portoes"]["lint"]["falhas"] == {}, "e a base continua vazia", str(dados))

    print("\nAdmitir é gesto explícito, com motivo escrito")
    codigo, saida = rodar(C.cmd_gravar, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz),
                          admitir="pré-existente do módulo de navegação, card 1070")
    ok(codigo == 0 and "Admitido:" in saida, "com --admitir, grava", saida)
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="lint", formato="eslint", raiz=str(raiz))
    ok("base admitida com motivo" in saida and "card 1070" in saida,
       "e a conferência mostra o motivo toda vez", saida)

    # ----------------------------------------------------------------
    print("\nSem linha de base, a catraca não finge que tem")
    codigo, saida = rodar(C.cmd_conferir, saida_do_portao=str(entrada), base=str(base),
                          portao="inexistente", formato="eslint", raiz=str(raiz))
    ok(codigo == 2 and "não tem linha de base" in saida,
       "não passa e não reprova: diz que não sabe", saida)

    print("\nO formato que ninguém capturou usa --padrao")
    pw = ("  1) [chromium] › i2-no-overflow.spec.ts:49:5 › sem overflow em 375\n"
          "  2) [chromium] › i8-baseline.spec.ts:12:3 › baseline do diálogo\n")
    r = C.extrair(pw, "", raiz, r"^\s*\d+\)\s*\[.+?\]\s*›\s*(?P<id>.+?)\s*$")
    ok(len(r) == 2 and any("i2-no-overflow" in k for k in r),
       "regex com grupo id serve de parser", str(r))
    try:
        C.extrair(pw, "", raiz, r"^(\d+)")
        ok(False, "padrão sem grupo `id` é recusado")
    except C.CatracaError as exc:
        ok("grupo nomeado `id`" in str(exc), "padrão sem grupo `id` é recusado", str(exc))

    print("\nFormato desconhecido não vira conjunto vazio silencioso")
    try:
        C.extrair(VITEST, "playwright", raiz, None)
        ok(False, "formato desconhecido reclama")
    except C.CatracaError as exc:
        ok("formato desconhecido" in str(exc), "formato desconhecido reclama", str(exc))

    print("\nLighthouse: portao de tela por auditoria binaria")
    achados = C.extrair(LIGHTHOUSE, "lighthouse", Path("."), None)
    ok(len(achados) == 6, "as seis auditorias binarias com score 0 entram", str(sorted(achados)))
    ok("/grupos :: color-contrast" in achados,
       "identidade e' `caminho :: id da auditoria`", str(sorted(achados))[:120])
    ok(all(v == 1 for v in achados.values()),
       "conta 1 por auditoria, nao o numero de nos do DOM", str(achados))

    print("\nE os cinco que NAO sao falha de catraca")
    ok("/grupos :: is-on-https" not in achados, "binaria que PASSOU nao entra")
    ok(not any("largest-contentful-paint" in k for k in achados),
       "numeric nao entra: e' medida continua, e catraca em medida oscila")
    ok(not any("final-screenshot" in k for k in achados), "informative nao entra")
    ok(not any("redirects-http" in k for k in achados), "notApplicable nao entra")
    ok(not any("custom-controls-labels" in k for k in achados), "manual nao entra")
    # O perigoso: parece falha, E' defeito real, e tem score 0.5.
    ok(not any("unsized-images" in k for k in achados),
       "metricSavings com score 0,5 NAO entra -- parece falha e e' medida continua")

    print("\nA identidade nao carrega host nem porta")
    outro = LIGHTHOUSE.replace("http://127.0.0.1:8731/grupos",
                               "https://homolog.exemplo.com/grupos")
    ok(set(C.extrair(outro, "lighthouse", Path("."), None)) == set(achados),
       "a mesma auditoria em local e em homologacao da' a MESMA chave",
       str(sorted(set(C.extrair(outro, "lighthouse", Path("."), None)) ^ set(achados))))
    # Mesma razao do numero de linha: nada que uma mudanca legitima mova.
    raiz_so = LIGHTHOUSE.replace("http://127.0.0.1:8731/grupos", "http://127.0.0.1:8731/")
    ok("/ :: color-contrast" in C.extrair(raiz_so, "lighthouse", Path("."), None),
       "e a raiz do site tem caminho `/`")

    print("\nJSON que nao e' JSON reclama em vez de contar zero falha")
    try:
        C.extrair("isto nao e json", "lighthouse", Path("."), None)
        ok(False, "JSON invalido levanta CatracaError")
    except C.CatracaError as exc:
        ok("lighthouse" in str(exc).lower() or "json" in str(exc).lower(),
           "JSON invalido levanta CatracaError legivel", str(exc))


    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaça de ratchet.py: tudo verde.")
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
