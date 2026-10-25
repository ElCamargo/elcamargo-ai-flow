#!/usr/bin/env python3
"""Fumaça de honesty.py — e a prova de que a calibração não a cegou.

Esta lente errou três vezes contra um repositório real antes de acertar: acusou
3 casos, depois 35, depois 5, e todos eram legítimos. Cada correção estreitou a
regra. Uma lente estreitada até o silêncio é indistinguível de uma lente
quebrada — por isso metade deste arquivo são casos que ela AINDA precisa pegar.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import honesty as H  # noqa: E402

falhas: list[str] = []


def ok(cond: bool, rotulo: str, detalhe: str = "") -> None:
    print(f"  [{'ok' if cond else 'FALHA'}] {rotulo}")
    if not cond:
        falhas.append(rotulo)
        if detalhe:
            print(f"        {detalhe}")


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def varrer(nome: str, corpo: str, tmp: Path) -> dict[str, list[str]]:
    alvo = tmp / nome
    alvo.write_text(corpo, encoding="utf-8")
    return H.varrer(alvo, tmp)


def rodar_testes(nome: str, corpo: str, tmp: Path) -> tuple[int, str]:
    alvo = tmp / nome
    alvo.write_text(corpo, encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = H.cmd_testes(Args(arquivos=[str(alvo)], raiz=str(tmp)))
    return codigo, buf.getvalue()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="honestidade-"))

    print("\nO que ela PRECISA pegar")
    a = varrer("a.spec.ts", """
describe('x', () => {
  it.only('so este roda, e o resto do arquivo nao', () => { expect(f()).toBe(1); });
  it.skip('este nunca roda em ambiente nenhum', () => { expect(f()).toBe(2); });
  it.todo('nem este');
  it('nao prova nada', () => { expect(true).toBe(true); });
  it('so chama e vai embora', () => { f(); });
  it('so prova a fiacao', () => { const s = vi.fn(); g(s); expect(s).toHaveBeenCalled(); });
});
""", tmp)
    ok(len(a["only"]) == 1, "`.only` commitado", str(a["only"]))
    ok(len(a["pulo_estatico"]) == 2, "`.skip` com nome e `.todo` sao pulo estatico",
       str(a["pulo_estatico"]))
    ok(len(a["trivial"]) == 1, "`expect(true).toBe(true)` e trivialmente verdadeiro",
       str(a["trivial"]))
    ok(any("so chama" in i for i in a["sem_assercao"]),
       "caso sem assercao nenhuma", str(a["sem_assercao"]))
    ok(any("fiacao" in i for i in a["so_chamada"]),
       "caso cuja unica assercao e `toHaveBeenCalled()`", str(a["so_chamada"]))

    b = varrer("faq.service.spec.ts",
               "vi.mock('./faq.service');\nit('x', () => { expect(1).toBe(2); });\n", tmp)
    ok(len(b["auto_mock"]) == 1, "o arquivo que simula o modulo que testa", str(b))

    codigo, saida = rodar_testes("c.spec.ts",
                                 "it.only('x', () => { expect(f()).toBe(1); });\n", tmp)
    ok(codigo == 1, "`.only` reprova", saida)

    print("\nO que ela NAO PODE pegar - os tres erros de calibracao, em ordem")

    c = varrer("d.spec.ts", """
const expectRefusal = (r, code) => { expect(r).toEqual({ allowed: false, code }); };
it('recusa a transicao', () => {
  expectRefusal(canTransition('closed', 'active'), 'INVALID');
});
""", tmp)
    ok(not c["sem_assercao"],
       "1o erro (3 falsos): helper `expectRefusal` conta como assercao",
       str(c["sem_assercao"]))
    ok(not c["so_chamada"], "e nao cai no balde errado", str(c["so_chamada"]))

    d = varrer("e.spec.ts", """
it('ignora o evento sem occurredAt, sem tocar no banco', async () => {
  await consumer.handle({});
  expect(manager.save).not.toHaveBeenCalled();
  expect(auditEvents.write).not.toHaveBeenCalled();
});
""", tmp)
    ok(not d["so_chamada"],
       "2o erro (35 falsos): `.not.toHaveBeenCalled()` prova 'nao faz nada'",
       str(d["so_chamada"]))

    e = varrer("f.spec.ts", """
it('recria o canal fechado antes da proxima publicacao', async () => {
  await service.publish(e()); channel.emit('close'); await service.publish(e());
  expect(connect).toHaveBeenCalledTimes(1);
  expect(connection.createConfirmChannel).toHaveBeenCalledTimes(2);
});
it('pede a proxima pagina quando a lista chega ao fim', () => {
  fireEvent.scroll(caixa);
  expect(onLoadMore).toHaveBeenCalledTimes(1);
});
""", tmp)
    ok(not e["so_chamada"],
       "3o erro (5 falsos): quando o comportamento E a contagem, ela e a assercao",
       str(e["so_chamada"]))

    f = varrer("g.spec.ts", """
it('chama o gateway com o documento normalizado', () => {
  service.create({ document: '12345678900' });
  expect(gateway.send).toHaveBeenCalledWith({ document: '12345678900' });
});
""", tmp)
    ok(not f["so_chamada"],
       "e `toHaveBeenCalledWith` afirma o argumento, que e comportamento",
       str(f["so_chamada"]))

    g = varrer("h.spec.ts",
               "test.skip(Boolean(pular), pular?.motivo);\n"
               "it('x', () => { expect(f()).toBe(1); });\n", tmp)
    ok(not g["pulo_estatico"] and len(g["pulo_condicional"]) == 1,
       "pulo condicional com motivo e guarda declarada, nao achado", str(g))

    h = varrer("i.spec.ts", "vi.mock('./outro-modulo');\n"
                            "it('x', () => { expect(f()).toBe(1); });\n", tmp)
    ok(not h["auto_mock"], "simular OUTRO modulo e normal e nao e achado", str(h))

    i = varrer("j.spec.ts", "it('x', () => { expect(soma(2, 2)).toBe(4); });\n", tmp)
    ok(not any(i[k] for k in i), "e um teste comum nao gera achado nenhum", str(i))

    print("\nO rodape da rodada, capturado dos dois runners de verdade")
    vitest = "      Tests  1 passed | 1 skipped | 1 todo (3)\n"
    p = H.ler_rodape(vitest, "vitest")
    ok(p == {"passed": 1, "skipped": 1, "todo": 1, "total": 3},
       "vitest: passou, pulou, a fazer, total", str(p))

    jest = "Tests:       1 skipped, 1 todo, 1 passed, 3 total\n"
    p = H.ler_rodape(jest, "jest")
    ok(p.get("total") == 3 and p.get("skipped") == 1 and p.get("passed") == 1,
       "jest: o mesmo, noutra ordem e com outro separador", str(p))

    alvo = tmp / "saida.txt"
    alvo.write_text("Test Files  1 passed (1)\n" + vitest, encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = H.cmd_saida(Args(saida_da_rodada=str(alvo), formato="vitest"))
    saida = buf.getvalue()
    ok("2 nao rodaram" in saida.replace("ã", "a"), "diz quantos nao rodaram", saida)
    ok("[MEDIO]" in saida and "67%" in saida, "e a fatia que isso representa", saida)
    ok(codigo == 0,
       "e NAO reprova: procedencia estrutural nao reprova sozinha", saida)

    alvo.write_text("      Tests  9 passed (9)\n", encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        H.cmd_saida(Args(saida_da_rodada=str(alvo), formato="vitest"))
    ok("[MEDIO]" not in buf.getvalue(), "rodada sem pulo nao gera aviso", buf.getvalue())

    alvo.write_text("qualquer coisa sem rodape\n", encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        H.cmd_saida(Args(saida_da_rodada=str(alvo), formato="vitest"))
    ok("achei o rodap" in buf.getvalue(),
       "e saida sem rodape e declarada, nao vira zero silencioso", buf.getvalue())

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
        return 1
    print("Fumaca de honesty.py: tudo verde.")
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
