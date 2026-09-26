# elcamargo-report

Markdown → PDF para a fronteira com humano: o relatório que volta ao analista de
negócio, o anexo do card.

**Não é uma skill, é um tool.** Renderizar PDF é código determinístico; não gasta
contexto e sai igual toda vez. As skills chamam por linha de comando.

## Por que a entrada é Markdown

Markdown é o formato canônico do fluxo inteiro: toda skill escreve, toda skill
lê. O `implemented-sdd-reviewer` precisa *ler* a SDD para conferir a
implementação — PDF não é diffável nem greppável.

O gerador de relatórios do projeto Linx, que serviu de base para este, tem o
conteúdo de cada relatório como um módulo Python. Funciona lá, com poucos
relatórios escritos à mão. Aqui, oito skills emitem relatório em toda atividade;
Markdown é o único formato que oito produtores conseguem emitir de forma
consistente.

## Ambiente

ReportLab só é necessário na fronteira humana. Instale num venv descartável,
para não registrar dependência no ambiente do projeto:

```bash
python3 -m venv ~/.cache/elcamargo-flow/venv && ~/.cache/elcamargo-flow/venv/bin/python -m pip install reportlab pypdfium2
```

## Uso

```bash
~/.cache/elcamargo-flow/venv/bin/python generate.py relatorio.md
~/.cache/elcamargo-flow/venv/bin/python generate.py relatorio.md -o saida.pdf --conferir
```

| Flag | Efeito |
| --- | --- |
| `-o`, `--saida` | PDF de destino. Padrão: mesmo nome, `.pdf` |
| `--rodape` | Sobrescreve o rodapé do front matter |
| `--conferir` | Renderiza cada página em PNG para inspeção visual |
| `--estrito` | Falha se algum caractere não couber na fonte |

## Front matter

```markdown
---
titulo: Revisão da análise de negócio
subtitulo: Cadastro de produtos e regras por categoria
atividade: 1042
tipo: revisao-negocio
versao: 2
data: 2026-08-26
autor: Elcamargo Business Analysis Reviewer
objetivo: Apontar ambiguidades antes que a análise vire especificação.
conclusao: Quatro pontos bloqueiam; dois exigem decisão do negócio.
mudancas: Reescrita a seção 3 após a resposta do analista.
rodape: Elcamargo | Acme | Atividade 1042
---
```

`titulo`, `objetivo` e `conclusao` são **obrigatórios** e o gerador recusa o
documento sem eles. Não é burocracia: é a pirâmide aplicada mecanicamente. Os
dois vão para a primeira página, antes da seção 1 — a resposta antes da
evidência. Uma skill que não consegue enunciar a conclusão numa frase não
terminou de pensar.

`mudancas` vira uma caixa âmbar na capa. Preencha em toda revisão: o documento
circula, e quem já leu a versão anterior precisa saber o que mudou.

## Markdown suportado

| Escreve | Vira |
| --- | --- |
| `## Título` | Seção |
| `### Sub` / `#### Sub-sub` | Subseção |
| `- item` / `1. item` | Lista |
| `\| a \| b \|` | Tabela, com largura de coluna proporcional ao conteúdo |
| ` ```…``` ` | Bloco monoespaçado |
| `---` | Régua |
| `**forte**` `*fraco*` `` `cod` `` | Negrito, itálico, monoespaçado |
| `> [!ok]` `> [!atencao]` `> [!erro]` `> [!nota]` | Caixa verde / âmbar / vermelha / azul |

Linhas `>` consecutivas formam **um** parágrafo, como em Markdown. Uma linha `>`
vazia separa dois.

## Convenções

Herdadas do time Linx, que pagou por elas:

**Numere as seções à mão** (`## 1. Sumário executivo`) e **mantenha a numeração
estável entre revisões.** O gerador não renumera de propósito: se ele
renumerasse, inserir uma seção deslocaria todas as seguintes e os comentários já
feitos no card deixariam de fazer sentido.

**Confira a diagramação antes de enviar.** `--conferir` renderiza as páginas em
PNG; olhe as imagens. Título órfão, tabela cortada e viúva no topo de página são
invisíveis no fonte e óbvios na imagem.

**Escreva para quem decide, não para quem implementa.** Explique o porquê antes
do como, e traduza jargão.

**Nunca inclua credencial, token, dado de cliente ou de contribuinte.**

## Caracteres

As fontes padrão do ReportLab usam WinAnsiEncoding. Um caractere fora dela vira
um retângulo preto no PDF pronto — em silêncio, que é onde o time Linx encontrou
os deles.

O gerador trata isso sozinho: `→ ✓ ≥ ×` e afins viram equivalentes ASCII, o
resto é aproximado e **reportado no stderr**. Acentuação PT-BR, travessão e `•`
passam intactos. Use `--estrito` quando quiser que um caractere não mapeável
falhe em vez de ser aproximado.

## Arquivos

| Arquivo | Papel |
| --- | --- |
| `style.py` | Paleta, estilos e blocos. Nenhum conteúdo de documento. |
| `markdown_pdf.py` | Front matter, sanitização, parser Markdown, montagem. |
| `generate.py` | CLI e verificação visual. |
| `test_smoke.py` | 28 verificações, incluindo a do título órfão. |

## Teste

```bash
~/.cache/elcamargo-flow/venv/bin/python test_smoke.py
```
