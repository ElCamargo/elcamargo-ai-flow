# hooks

`hooks.json` é carregado **por convenção** — o plugin não declara no manifesto.

Declarar `"hooks": "./hooks/hooks.json"` em `.claude-plugin/plugin.json` faz o
mesmo arquivo ser carregado duas vezes, e a instalação falha com
`Duplicate hooks file detected`. O campo do manifesto existe para apontar
arquivos **adicionais**, não para o padrão.

Isso passou pelo `claude plugin validate` sem um aviso sequer, nas duas
validações, inclusive `--strict`. O erro só apareceu no `plugin list`, depois de
instalado.
