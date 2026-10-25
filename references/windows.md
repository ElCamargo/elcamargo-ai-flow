# Windows

O pacote é escrito e medido em macOS e Linux. Em 22/09/2026 uma instalação
Windows rodou a suíte e **seis conferências reprovaram** — e nenhuma era
artefato de teste. Os testes estavam certos: faltavam mecanismos.

Esta página é o que se sabe de lá, o que foi consertado e **o que continua sem
prova**.

## O que estava quebrado, e o que era

### 1. A trava do estado não existia

`trava()` serializa toda mutação entre processos. Fora do POSIX ela era isto:

```python
if fcntl is None:
    yield  # Windows: no flock. Parallel worktrees are unprotected there.
    return
```

Um `yield` e mais nada. Duas sessões escrevendo a mesma atividade liam o mesmo
estado, escreviam por cima uma da outra, e **as duas reportavam sucesso** — que
é exatamente o defeito que a trava existe para impedir, e exatamente o que a
suíte de lá acusou.

O comentário dizia *"Documented in README"*. **O README nunca teve uma linha
sobre Windows.** Duas ausências empilhadas: o mecanismo não existia, e o aviso
que declararia a lacuna também não. A garantia da ferramenta — *"nenhuma escrita
foi perdida"* — valia sem nada a sustentando.

**Agora existe**, por `msvcrt.locking`. A diferença de forma importa: `msvcrt`
não espera, trava ou falha. Por isso há laço e prazo — e **o prazo estoura em
erro**, nunca em seguir sem a trava. Seguir sem ela é o defeito.

Plataforma que não tenha `fcntl` nem `msvcrt` **declara em voz alta** a cada
processo, em vez de seguir calada. Recusar bloquearia o pacote numa plataforma
exótica, o que é pior que o risco; calar foi o que produziu o defeito.

### 2. A saída morria na codificação da região

No Windows, com a saída em **pipe** — que é como toda skill e toda suíte chamam
estas ferramentas —, `print` usa a codificação da região, `cp1252`. Este pacote
imprime `→` às pencas: 28 vezes só em `tools/`, e é o separador das trilhas.

`cp1252` não tem `→`. O resultado é `UnicodeEncodeError` e a ferramenta morre —
sem relação nenhuma com o que ela ia fazer.

São 35 caracteres distintos fora do `cp1252` no pacote (`→ ✖ − ● ← ↔ ∪ ✓` …), 93
ocorrências. Agora toda ferramenta reconfigura `stdout` e `stderr` para UTF-8 no
próprio ponto de entrada.

### 3. A leitura de `git` decodificava pela região

Toda chamada de subprocesso usava `text=True` **sem `encoding=`**, o que decodifica
pela região. O `git` responde em UTF-8; branch, nota ou caminho com acento
chegava truncado ou levantava `UnicodeDecodeError` — que `_git` **não capturava**,
porque só tratava `OSError` e `CalledProcessError`.

Era o que derrubava as conferências de branch e worktree. Sessenta e quatro
sítios, agora com `encoding="utf-8", errors="replace"`.

## O que prende, e roda em qualquer plataforma

Dois dos três consertos se conferem daqui, e é de propósito: defeito que só a
máquina de lá enxerga é defeito que ninguém daqui conserta com confiança.

- **A codificação** se reproduz com `PYTHONIOENCODING=cp1252` e a saída em pipe.
  O teste tem o **controle** junto: sem a reconfiguração, o mesmo ambiente
  derruba.
- **O caminho da trava fora do POSIX** se confere com dublê: que ele é escolhido,
  que solta, que o prazo estoura em **erro**, e que plataforma sem primitiva
  nenhuma declara a lacuna.

## O que continua SEM PROVA, e não se presume

- **`msvcrt.locking` nunca foi executado.** O caminho até ele está preso por
  teste; a chamada em si só a máquina de lá exercita. Rodar a suíte no Windows
  é o que fecha isso — e é o pedido a quem estiver lá.
- **Os symlinks do `install.sh`.** Ele usa `ln -s`, e no Windows symlink exige
  Modo de Desenvolvedor ou privilégio de administrador; sem isso o Git Bash
  copia em vez de ligar, e o pacote passa a viver em duas cópias que divergem.
  **Não foi medido.** Se a instalação de lá foi feita copiando arquivos à mão, é
  provável que seja este o motivo.
- **Terminação de linha.** Nada no pacote depende de `LF`, até onde se leu, mas
  `git config core.autocrlf` não foi conferido contra os arquivos de estado.

## Se você está no Windows

Rode a suíte inteira antes de confiar no pacote:

```bash
for t in $(find . -name "test_*.py" -not -path "*/__pycache__/*"); do
    (cd $(dirname $t) && python3 $(basename $t) >/dev/null 2>&1) \
        || echo "VERMELHA: $t"
done
```

Duas reprovam em qualquer plataforma e são conhecidas: `elcamargo-report`
quer `reportlab` num venv, e `presentation` cobra do manual referências que
nunca entraram nele. **Qualquer outra vermelha é achado** — e vale mais que esta
página, porque veio da máquina de verdade.
