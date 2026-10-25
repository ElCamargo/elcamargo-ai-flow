"""O contrato de casos: cada critério de aceite da SDD, e a prova de cada um.

A matriz diz que o requisito foi PARAR em algum lugar. Isto diz se ele foi
provado. Até 2.57.0 a pergunta "cada CT virou teste automatizado?" era leitura
da frente de QA no step 9, e leitura acha o que procura.

    gerar             extrai os casos da SDD e grava `<id>-casos.json`, todos
                      com `passa: false`
    vermelho          lê a saída da suíte rodada ANTES da implementação e marca
                      os casos cujo teste falhou — a fase vermelha
    verde             lê a saída da suíte depois, e marca `passa` só para o
                      caso que tem teste e não está entre as falhas
    conferir-testes   o step 9: o texto de cada caso ainda é o da SDD, cada um
                      tem teste, cada um passa

**Quem escreve `passa` é o script, nunca o modelo.** A avaliação que pediu isto
sugeria que o dev mudasse só o campo `passa`; mas um campo que o dev muda é uma
afirmação do dev, e é exatamente a afirmação que esta casa não aceita como
prova. Aqui ele sai da saída da suíte.

**O texto não tem como ser afrouxado em silêncio**, porque a fonte da verdade
não é o JSON: é a SDD aprovada no portão. `conferir-testes` reextrai os casos de
lá e compara a impressão de cada um. Editar o JSON não muda o que a SDD diz.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "flow-state"))
sys.path.insert(0, str(AQUI.parent / "ratchet"))

VERSAO = 1

# Pastas que não têm teste do projeto. Mesma família do `IGNORAR_PADRAO` do
# config, mais o que só faz sentido aqui.
NAO_DESCER = {"node_modules", "dist", "build", ".next", "out", "coverage",
              ".turbo", ".git", ".agents", "vendor", "__pycache__", ".venv",
              "venv", "target", "bin", "obj"}
RE_ARQUIVO_DE_TESTE = re.compile(
    r"(\.(test|spec|e2e|cy)\.[cm]?[jt]sx?$)|(^test_.*\.py$)|(_test\.(py|go)$)"
    r"|(Tests?\.(java|kt|cs)$)|(\.feature$)", re.I)
PASTAS_DE_TESTE = {"test", "tests", "__tests__", "e2e", "cypress", "spec"}
BYTES_POR_ARQUIVO = 1_000_000


class CasosError(Exception):
    pass


def agora() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def impressao(texto: str) -> str:
    return hashlib.sha256(normalizar(texto).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# De onde os casos saem
# --------------------------------------------------------------------------
def _bloco(linhas: list[str], inicio: int, eh_definicao) -> str:
    """O texto do caso: a linha que o define e o que vem logo abaixo.

    Título (`### CT-01 — ...`) leva o corpo até o próximo título do mesmo nível
    ou acima — é onde mora o Dado/Quando/Então. Linha de tabela ou de lista
    vai até a linha em branco, o próximo título ou a próxima definição.
    """
    primeira = linhas[inicio]
    titulo = re.match(r"^(#{1,6})\s", primeira)
    saida = [primeira]
    for linha in linhas[inicio + 1: inicio + 40]:
        outro_titulo = re.match(r"^(#{1,6})\s", linha)
        if titulo:
            if outro_titulo and len(outro_titulo.group(1)) <= len(titulo.group(1)):
                break
        elif not linha.strip() or outro_titulo:
            break
        if eh_definicao(linha):
            break
        saida.append(linha)
    return "\n".join(saida)


def extrair_casos(caminho: Path, prefixos: list[str] | None) -> tuple[list[str], list[dict]]:
    """Os casos de UMA fonte. Sem prefixo pedido: CT se houver, senão CA."""
    import matrix as M
    texto = M.ler_documento(caminho)
    linhas = texto.splitlines()
    if not prefixos:
        _, ocs = M.varrer(texto, ["CT", "CA"])
        definidos = {o.prefixo for o in ocs if o.tipo == "definicao"}
        prefixos = ["CT"] if "CT" in definidos else ["CA"]
    _, ocorrencias = M.varrer(texto, prefixos)
    padrao = M.padrao_ident(prefixos)

    def eh_definicao(linha: str) -> bool:
        return any(M.classificar(linha, m.start()) == "definicao"
                   for m in padrao.finditer(linha))

    casos = []
    for oc in M.definicoes_unicas(ocorrencias).values():
        bloco = _bloco(linhas, oc.linha - 1, eh_definicao)
        # O texto é para LER; a impressão é do bloco cru. Tirar as barras da
        # tabela não muda o que a impressão compara.
        legivel = "\n".join(l.strip().strip("|").replace(" | ", " — ")
                             for l in bloco.splitlines())
        casos.append({"id": oc.ident, "fonte": str(caminho), "linha": oc.linha,
                      "texto": normalizar(legivel)[:2000], "sha": impressao(bloco)})
    return prefixos, casos


def sha_do_arquivo(caminho: Path) -> str:
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


# --------------------------------------------------------------------------
# Onde os testes estão
# --------------------------------------------------------------------------
def arquivos_de_teste(raiz: Path):
    for pasta, dirs, arquivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in NAO_DESCER]
        dentro = PASTAS_DE_TESTE & set(Path(pasta).relative_to(raiz).parts)
        for nome in arquivos:
            if RE_ARQUIVO_DE_TESTE.search(nome) or (
                    dentro and re.search(r"\.(py|[cm]?[jt]sx?|go|java|kt|cs|rb)$", nome)):
                yield Path(pasta) / nome


def achar_testes(raiz: Path, ids: list[str], prefixos: list[str]) -> dict[str, list[str]]:
    """`id -> ['arquivo:linha', ...]` — onde cada caso é citado num teste.

    Citação no nome do teste ou num comentário vale igual: o que se pede é que
    alguém consiga ir do caso ao teste sem perguntar.
    """
    import matrix as M
    padrao = M.padrao_ident(prefixos)
    procurados = set(ids)
    achados: dict[str, list[str]] = {i: [] for i in ids}
    for arq in arquivos_de_teste(raiz):
        try:
            if arq.stat().st_size > BYTES_POR_ARQUIVO:
                continue
            texto = arq.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            for m in padrao.finditer(linha):
                ident = f"{m.group(1).upper()}-{int(m.group(2)):02d}" + (m.group(3) or "")
                if ident in procurados:
                    achados[ident].append(f"{arq.relative_to(raiz)}:{n}")
    return achados


def ids_em(texto: str, prefixos: list[str]) -> set[str]:
    import matrix as M
    return {f"{m.group(1).upper()}-{int(m.group(2)):02d}" + (m.group(3) or "")
            for m in M.padrao_ident(prefixos).finditer(texto)}


RE_COMENTARIO = re.compile(r"^\s*(?://|#|\*|/\*|--)")


def ids_no_teste(chave: str, raiz: Path, prefixos: list[str]) -> set[str]:
    """Os ids citados no COMENTÁRIO logo acima do teste que a chave nomeia.

    `// CT-02` em cima de `it('recusa vencido')` é a outra forma que a skill
    aceita, e a suíte só imprime o nome. Abre o arquivo, acha a linha do nome e
    lê ela e os comentários colados acima dela — parando no primeiro que não é
    comentário, para não herdar o id do teste vizinho.
    """
    partes = [p.strip() for p in chave.split(" > ")]
    if len(partes) < 2:
        return set()
    arquivo, nome = raiz / partes[0], partes[-1]
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    achados: set[str] = set()
    for i, linha in enumerate(linhas):
        if nome not in linha:
            continue
        achados |= ids_em(linha, prefixos)
        j = i - 1
        while j >= 0 and RE_COMENTARIO.match(linhas[j]):
            achados |= ids_em(linhas[j], prefixos)
            j -= 1
    return achados


def falhas_por_caso(saida: str, formato: str, padrao: str, raiz: Path,
                    ids: list[str], prefixos: list[str],
                    testes: dict[str, list[str]]) -> dict[str, str]:
    """`id -> a falha que o nomeia`, lida da saída da suíte pela catraca.

    O erro de COLETA — o arquivo nem subiu, o caso mais comum da fase vermelha,
    porque o teste importa o que ainda não existe — vem sem nome de teste. Ele
    conta para todo caso citado naquele arquivo.
    """
    import ratchet as R
    falhas = R.extrair(saida, formato, raiz, padrao or None)
    por_caso: dict[str, str] = {"": str(len(falhas))}
    for chave in falhas:
        citados = ids_em(chave, prefixos) or ids_no_teste(chave, raiz, prefixos)
        for ident in citados & set(ids):
            por_caso.setdefault(ident, chave)
        arquivo = chave.split(" > ")[0].strip()
        if " > " not in chave and arquivo:
            for ident in ids:
                if any(t.split(":")[0].endswith(arquivo) or arquivo.endswith(t.split(":")[0])
                       for t in testes.get(ident, [])):
                    por_caso.setdefault(ident, f"{chave} (erro de coleta)")
    return por_caso


def _sem_total(falhas: dict[str, str]) -> tuple[dict[str, str], int]:
    """Separa a contagem de falhas nomeadas, que viaja na chave vazia."""
    total = int(falhas.pop("", "0") or 0)
    return falhas, total


# --------------------------------------------------------------------------
# O arquivo e o estado da atividade
# --------------------------------------------------------------------------
def _flow_state():
    import flow_state as F
    return F


def caminho_do_contrato(atividade: str) -> Path:
    F = _flow_state()
    try:
        return F.casos_path(F.resolve_agents_dir(), atividade)
    except F.FlowStateError as exc:
        raise CasosError(str(exc)) from exc


def ler(atividade: str) -> tuple[Path, dict]:
    caminho = caminho_do_contrato(atividade)
    if not caminho.is_file():
        raise CasosError(
            f"{atividade} não tem contrato de casos. Gere no começo do step 8:\n"
            f"    matrix.py casos gerar --atividade {atividade} --sdd <sdd-sistema>")
    try:
        return caminho, json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CasosError(f"{caminho} ilegível: {exc}") from exc


def gravar(caminho: Path, dados: dict) -> None:
    temp = caminho.with_suffix(".tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    temp.replace(caminho)


def registrar(atividade: str, veredicto: str, detalhe: str) -> None:
    F = _flow_state()
    try:
        F.main(["conferencia", atividade, "--ferramenta", "casos",
                "--veredicto", veredicto, "--detalhe", detalhe[:200]])
    except SystemExit:
        pass


def _resumo(casos: list[dict]) -> str:
    sem = [c["id"] for c in casos if not c.get("passa")]
    if not sem:
        return f"{len(casos)} de {len(casos)} com teste verde"
    lista = ", ".join(sem[:8]) + ("…" if len(sem) > 8 else "")
    return f"{len(casos) - len(sem)} de {len(casos)} provados; sem prova: {lista}"


# --------------------------------------------------------------------------
# comandos
# --------------------------------------------------------------------------
def cmd_gerar(args) -> int:
    destino = caminho_do_contrato(args.atividade)
    pedidos = [p.strip().upper() for p in (args.prefixos or "").split(",") if p.strip()]
    antigo = {}
    if destino.is_file():
        if not args.refazer:
            raise CasosError(
                f"{destino} já existe. O contrato nasce uma vez, no começo do "
                "step 8; regerar por cima apagaria a fase vermelha já gravada.\n"
                "  Se a SDD mudou de propósito: --refazer. Caso cujo texto não "
                "mudou guarda o estado; o que mudou volta a `passa: false`.")
        antigo = {c["id"]: c for c in json.loads(destino.read_text(encoding="utf-8"))["casos"]}

    fontes, casos, prefixos = [], [], pedidos
    for sdd in args.sdd:
        caminho = Path(sdd).expanduser().resolve()
        usados, achados = extrair_casos(caminho, pedidos or None)
        prefixos = sorted(set(prefixos) | set(usados))
        fontes.append({"caminho": str(caminho), "sha": sha_do_arquivo(caminho)})
        casos += achados
    vistos = set()
    for c in casos:
        if c["id"] in vistos:
            raise CasosError(f"{c['id']} definido em mais de uma fonte: "
                             "o contrato não sabe qual texto vale.")
        vistos.add(c["id"])
        velho = antigo.get(c["id"])
        mantido = velho and velho.get("sha") == c["sha"]
        c["vermelho"] = velho.get("vermelho") if mantido else None
        c["passa"] = bool(velho.get("passa")) if mantido else False
        c["teste"] = velho.get("teste", []) if mantido else []

    if not casos:
        registrar(args.atividade, "nao-coberta",
                  f"a SDD não define {'/'.join(prefixos or ['CT', 'CA'])}")
        print(f"{args.atividade}: nenhuma fonte define caso "
              f"({'/'.join(prefixos or ['CT', 'CA'])}). Nada a contratar —")
        print("  e isso fica escrito: uma SDD sem critério de aceite numerado é")
        print("  achado do step 3, não do 8.")
        return 0

    gravar(destino, {"versao": VERSAO, "atividade": args.atividade,
                     "gerado_em": agora(), "prefixos": prefixos,
                     "fontes": fontes, "casos": casos})
    registrar(args.atividade, "exigida",
              f"contrato de {len(casos)} caso(s); {_resumo(casos)}")
    print(f"{args.atividade}: {len(casos)} caso(s) em {destino}")
    for c in casos:
        print(f"  {c['id']:<8} {c['texto'][:90]}")
    print()
    print("Agora a fase vermelha: escreva o teste de cada caso, citando o id no")
    print("nome ou num comentário, e rode a suíte ANTES de implementar:")
    print(f"    <suíte> 2>&1 | matrix.py casos vermelho --atividade {args.atividade} --formato <vitest|jest> -")
    return 0


def _entrada(caminho: str) -> str:
    if caminho == "-":
        return sys.stdin.read()
    p = Path(caminho)
    if not p.is_file():
        raise CasosError(f"saída da suíte não encontrada: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def cmd_vermelho(args) -> int:
    if not (args.formato or args.padrao):
        raise CasosError("diga como ler a saída: --formato vitest|jest, ou --padrao.")
    caminho, dados = ler(args.atividade)
    raiz = Path(args.raiz).resolve()
    casos, prefixos = dados["casos"], dados["prefixos"]
    ids = [c["id"] for c in casos]
    testes = achar_testes(raiz, ids, prefixos)
    falhas, _ = _sem_total(falhas_por_caso(
        _entrada(args.saida_do_teste_opt or args.saida_do_teste), args.formato,
        args.padrao, raiz, ids, prefixos, testes))
    quando = agora()
    for c in casos:
        c["teste"] = testes[c["id"]]
        if c["id"] in falhas and not c.get("vermelho"):
            c["vermelho"] = {"quando": quando, "falha": falhas[c["id"]][:200]}
    gravar(caminho, dados)

    vermelhos = [c for c in casos if c.get("vermelho")]
    print(f"{args.atividade}: {len(vermelhos)} de {len(casos)} caso(s) com fase vermelha")
    for c in casos:
        if c.get("vermelho"):
            print(f"  [vermelho] {c['id']:<8} {c['vermelho']['falha'][:90]}")
        elif not c["teste"]:
            print(f"  [sem teste] {c['id']:<8} nenhum arquivo de teste cita este id")
        else:
            print(f"  [PASSOU]   {c['id']:<8} {c['teste'][0]} — passou sem a implementação")
    if any(c["teste"] and not c.get("vermelho") for c in casos):
        print()
        print("Teste que passa antes de existir o código não prova o caso: ou ele")
        print("não exercita o comportamento, ou o comportamento já existia. Diga qual")
        print("no resumo do step — o step 9 vai ver esta linha.")
    return 0


def cmd_verde(args) -> int:
    caminho, dados = ler(args.atividade)
    raiz = Path(args.raiz).resolve()
    casos, prefixos = dados["casos"], dados["prefixos"]
    ids = [c["id"] for c in casos]
    testes = achar_testes(raiz, ids, prefixos)
    saida = _entrada(args.saida_do_teste_opt or args.saida_do_teste)
    falhas, nomeadas = (_sem_total(falhas_por_caso(
        saida, args.formato, args.padrao, raiz, ids, prefixos, testes))
        if args.formato or args.padrao else ({}, 0))
    for c in casos:
        c["teste"] = testes[c["id"]]
        if not c["teste"]:
            c["passa"], c["motivo"] = False, "nenhum teste cita o id"
        elif c["id"] in falhas:
            c["passa"], c["motivo"] = False, f"falhando: {falhas[c['id']][:160]}"
        elif args.codigo == 0:
            c["passa"], c["motivo"] = True, ""
        elif nomeadas:
            # A suíte fechou vermelha por OUTRO teste — conhecido da catraca ou
            # não — e este caso não está entre as falhas que ela nomeou.
            c["passa"], c["motivo"] = True, ""
        else:
            # Vermelha sem nomear ninguém: estourou o tempo, caiu antes de
            # rodar, ou não há formato para ler. Dar `passa` aqui seria ler
            # silêncio como sucesso.
            c["passa"], c["motivo"] = False, (
                "a suíte não fechou verde e a saída não diz quem falhou")
    dados["verde_em"] = agora()
    gravar(caminho, dados)
    todos = all(c["passa"] for c in casos)
    registrar(args.atividade, "ok" if todos else "falhou", _resumo(casos))
    print(f"{args.atividade}: contrato de casos — {_resumo(casos)}")
    for c in casos:
        if not c["passa"]:
            print(f"  [sem prova] {c['id']:<8} {c['motivo']}")
    return 0 if todos else 1


def cmd_conferir_testes(args) -> int:
    caminho, dados = ler(args.atividade)
    raiz = Path(args.raiz).resolve()
    casos, prefixos = dados["casos"], dados["prefixos"]
    no_contrato = {c["id"]: c for c in casos}

    bloqueia: list[str] = []
    alerta: list[str] = []
    na_sdd: dict[str, dict] = {}
    for fonte in dados.get("fontes", []):
        p = Path(fonte["caminho"])
        try:
            _, achados = extrair_casos(p, prefixos)
        except Exception as exc:  # documento sumiu, ficou vazio, virou imagem
            bloqueia.append(f"a fonte {p} não leu: {exc}")
            continue
        if sha_do_arquivo(p) != fonte.get("sha"):
            alerta.append(f"{p.name} mudou depois do contrato — confira se o "
                          "portão aprovou esta versão")
        na_sdd.update({c["id"]: c for c in achados})

    for ident, c in na_sdd.items():
        if ident not in no_contrato:
            bloqueia.append(f"{ident} está na SDD e não está no contrato")
        elif no_contrato[ident].get("sha") != c["sha"]:
            bloqueia.append(f"{ident}: o texto no contrato difere do da SDD")
    if dados.get("fontes"):
        for ident in no_contrato:
            if ident not in na_sdd:
                bloqueia.append(f"{ident} está no contrato e a SDD não o define")

    testes = achar_testes(raiz, list(no_contrato), prefixos)
    for ident, c in no_contrato.items():
        if not testes[ident]:
            bloqueia.append(f"{ident}: nenhum teste nesta árvore cita o id")
        elif not c.get("passa"):
            bloqueia.append(f"{ident}: sem teste verde ({c.get('motivo') or 'passa: false'})")
        if not c.get("vermelho"):
            alerta.append(f"{ident}: sem fase vermelha registrada")

    print(f"{args.atividade}: {len(no_contrato)} caso(s) no contrato, "
          f"{len(na_sdd)} na SDD, árvore {raiz}")
    for c in no_contrato.values():
        onde = (testes[c['id']] or ["—"])[0]
        print(f"  {c['id']:<8} passa={'sim' if c.get('passa') else 'não'}  "
              f"vermelho={'sim' if c.get('vermelho') else 'não'}  {onde}")
    if bloqueia:
        print(f"\n[ALTO] {len(bloqueia)}")
        for b in bloqueia:
            print(f"    {b}")
    if alerta:
        print(f"\n[ESTRUTURAL] {len(alerta)}")
        for a in alerta:
            print(f"    {a}")
    print()
    print("O que isto NÃO prova: que o teste exercita o comportamento. Prova que")
    print("o caso existe na SDD com este texto, que um teste o cita e que a suíte")
    print("não o nomeou entre as falhas. Teste com `.skip` também \"passa\" — a")
    print("varredura do `honesty.py` é quem o acha.")
    if args.registrar:
        registrar(args.atividade, "falhou" if bloqueia else "ok",
                  f"step 9: {len(bloqueia)} bloqueio(s), {len(alerta)} alerta(s)")
    return 1 if bloqueia else 0


def montar(sub) -> None:
    """Pendura `casos <op>` e `conferir-testes` no parser do matrix.py."""
    c = sub.add_parser("casos", help="o contrato de casos de uma atividade")
    ops = c.add_subparsers(dest="op", required=True)

    g = ops.add_parser("gerar", help="extrai os casos da SDD, todos sem prova")
    g.add_argument("--atividade", required=True)
    g.add_argument("--sdd", required=True, action="append",
                   help="a SDD de sistema (repita para backend e frontend)")
    g.add_argument("--prefixos", default="", help="padrão: CT se houver, senão CA")
    g.add_argument("--refazer", action="store_true")
    g.set_defaults(func=cmd_gerar)

    for nome, fn, ajuda in (("vermelho", cmd_vermelho, "a suíte ANTES da implementação"),
                            ("verde", cmd_verde, "a suíte depois; quem marca `passa`")):
        o = ops.add_parser(nome, help=ajuda)
        o.add_argument("saida_do_teste", nargs="?", default="-")
        o.add_argument("--saida-do-teste", dest="saida_do_teste_opt", default="")
        o.add_argument("--atividade", required=True)
        o.add_argument("--formato", default="", help="vitest, jest")
        o.add_argument("--padrao", default="", help="regex com grupo `id`")
        o.add_argument("--raiz", default=".")
        if nome == "verde":
            o.add_argument("--codigo", type=int, required=True,
                           help="o código de saída da suíte")
        o.set_defaults(func=fn)

    t = sub.add_parser("conferir-testes",
                       help="step 9: cada caso da SDD tem teste, e o teste passa")
    t.add_argument("--atividade", required=True)
    t.add_argument("--raiz", default=".")
    t.add_argument("--registrar", action="store_true",
                   help="grava o veredicto como a conferência `casos`")
    t.set_defaults(func=cmd_conferir_testes)
