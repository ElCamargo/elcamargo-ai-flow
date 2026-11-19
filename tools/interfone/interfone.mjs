#!/usr/bin/env node
/**
 * interfone — o canal entre sessoes de IA, e o que o `canal.mjs` nao dava conta.
 *
 * ## O que quebrou, e por que isto existe
 *
 * O `canal.mjs` foi desenhado para **uma sessao por papel**. Em 2026-09-09 duas
 * sessoes assumiram o papel `app` ao mesmo tempo, e tres defeitos
 * apareceram no mesmo dia:
 *
 *  1. **A leitura era destrutiva.** `ler` imprimia e movia o arquivo para
 *     `_lidos`. Com dois leitores, **o primeiro consumia a mensagem e o segundo
 *     nunca a via** — sem erro, sem rastro. E' o defeito que perde informacao, e
 *     e' o motivo principal deste arquivo existir.
 *  2. **O registro guardava uma sessao por papel.** O `atalho:` impresso ao
 *     enviar nomeava a sessao errada com confianca.
 *  3. **Nao havia como enderecar uma sessao.** O jeito de dizer "isto e' para o
 *     chat-mobile" era escrever o nome na linha de assunto, em prosa que a
 *     ferramenta nao le'.
 *
 * E um quarto, que nao e' defeito da ferramenta e sim ausencia dela: **nada
 * tocava**. Uma mensagem ficava horas na pasta ate' alguem lembrar de olhar.
 *
 * ## As quatro decisoes de desenho
 *
 * **Papel e sessao sao coisas diferentes.** O papel e' estavel — o repositorio,
 * o dominio. A sessao e' efemera e pertence a um papel. O `canal.mjs` os
 * confundia, e por isso nao conseguia representar duas sessoes no mesmo papel.
 *
 * **Ler nao consome.** A marca de leitura e' **por sessao**, num arquivo
 * proprio de cada uma — entao duas sessoes nunca disputam o mesmo arquivo, e o
 * que uma leu nao some para a outra. Arquivar continua existindo, e agora e'
 * **ato deliberado**, nao efeito colateral de ler.
 *
 * **Trava nao e' mensagem.** *"Estou nesta branch ate' devolver ao step 9"* nao
 * e' recado: e' **estado**. Mensagem se le' uma vez e esquece; estado se
 * **consulta antes de agir**. A colisao de 09/09 inteira teria sido evitada por
 * um `travas` consultado antes de encostar na atividade.
 *
 * **Uma caixa so'.** Nao ha tipos de canal, e a ausencia e' deliberada: tres
 * caixas viram tres lugares para esquecer de olhar. O que existe e' **destino**
 * (papel ou sessao) e **prioridade** (`--urgente`), que resolvem o mesmo com um
 * lugar so' de verdade.
 *
 * ## O que este arquivo NAO faz
 *
 * Ele nao toca. Arquivo em pasta nao acorda ninguem, e nenhum truque em Node
 * muda isso. Quem toca e' o **vigia** que a sessao instala no proprio harness, e
 * por isso o `registrar` imprime a receita dele e o `caixa` **avisa quando a
 * sessao esta registrada sem vigia**. Registrado sem vigia e' pior que nao
 * registrado: parece que alguem esta escutando.
 */

import {
  existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmdirSync, statSync, writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

const AQUI = dirname(fileURLToPath(import.meta.url));

/**
 * **O programa mudou de lugar; os dados nao.**
 *
 * Ate 09/09/2026 os dois moravam na mesma pasta, e `RAIZ` era simplesmente o
 * diretorio do arquivo. Isso amarrava a ferramenta a um projeto: ela vivia
 * numa pasta solta, com nome de um dos papeis, e ninguem que abrisse um
 * repositorio novo tinha como topar com ela.
 *
 * O programa foi para `~/.interfone`. Os **dados** ficaram: as caixas, o
 * `topologia.json` e o `_lidos/` continuam onde o `canal.mjs` e as sessoes que
 * ja estao no ar os procuram. Mover os dois junto quebraria quem esta rodando.
 */
function raizDados() {
  if (process.env.INTERFONE_RAIZ) return process.env.INTERFONE_RAIZ;
  const cfg = join(AQUI, 'config.json');
  if (existsSync(cfg)) {
    try {
      const r = JSON.parse(readFileSync(cfg, 'utf8')).raiz;
      if (r) return r.startsWith('~') ? join(homedir(), r.slice(1)) : r;
    } catch { /* config ilegivel cai no padrao de instalacao antiga */ }
  }
  return AQUI; // instalacao antiga: programa e dados na mesma pasta
}

const RAIZ = raizDados();
const FRESCOR_MIN = 30; // uma sessao sem sinal ha mais que isto esta "fria"

/** O arquivo que diz de que papel ESTE repositorio participa. */
const ARQ_REPO = '.interfone.json';

/**
 * **Um hook que falha atrapalha TODA mensagem.** Ele nunca deve ser o motivo de
 * uma sessao quebrar, entao dentro do modo hook qualquer erro sai como silencio
 * e codigo 0 — inclusive `topologia.json` ilegivel, que e' o caso realista.
 */
let MODO_HOOK = false;
const erro = (m) => {
  if (MODO_HOOK) process.exit(0);
  console.error(`interfone: ${m}`);
  process.exit(1);
};
const agora = () => new Date().toISOString();

/** Leitura de JSON que nunca explode por arquivo ausente ou vazio. */
function lerJson(caminho, padrao) {
  if (!existsSync(caminho)) return padrao;
  const bruto = readFileSync(caminho, 'utf8').trim();
  if (!bruto) return padrao;
  try { return JSON.parse(bruto); } catch { erro(`${caminho} nao e' JSON valido.`); }
}

function gravarJson(caminho, valor) {
  mkdirSync(dirname(caminho), { recursive: true });
  const temp = `${caminho}.${process.pid}.tmp`;
  writeFileSync(temp, `${JSON.stringify(valor, null, 2)}\n`);
  renameSync(temp, caminho); // rename e' atomico no mesmo sistema de arquivos
}

/**
 * Secao critica por `mkdir`, que e' atomico em POSIX.
 *
 * So' os arquivos COMPARTILHADOS precisam disto — `sessoes.json` e
 * `travas.json`. As marcas de leitura sao um arquivo por sessao **de
 * proposito**, para nao precisarem de trava nenhuma: quem le' muito nao disputa
 * com ninguem.
 */
function comTrava(nome, fn) {
  const porta = join(RAIZ, `.trava-${nome}`);
  // A secao critica dura milissegundos. Uma porta mais velha que isto e' de um
  // processo que morreu no meio — e nao de alguem trabalhando.
  const VELHA_MS = 30_000;
  for (let tentativa = 0; tentativa < 50; tentativa++) {
    try {
      mkdirSync(porta);
      try { return fn(); } finally { try { rmdirSync(porta); } catch {} }
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      /**
       * **Retomada de porta vazada.** A versao anterior mandava a pessoa
       * `apague-o`, e isso e' saida morta: num canal com varias sessoes ninguem
       * sabe de quem e' a porta, entao ou se apaga no escuro ou se desiste. E
       * desistir aqui trava `travar` e `registrar` para todo mundo.
       *
       * O criterio e' idade, e nao dono, porque a secao critica **nao dura**: se
       * a porta existe ha mais de 30 s, quem a criou nao esta mais la'.
       */
      try {
        const idade = Date.now() - statSync(porta).mtimeMs;
        if (idade > VELHA_MS) {
          rmdirSync(porta);
          console.error(`interfone: porta "${nome}" estava vazada ha ${Math.round(idade / 1000)}s e foi retomada.`);
          continue;
        }
      } catch { /* sumiu entre o erro e a leitura: a proxima volta pega */ }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20); // 20 ms
    }
  }
  erro(`nao consegui a trava "${nome}" apos 50 tentativas — ha contencao real, ou um processo a segura ha menos de ${VELHA_MS / 1000}s.`);
}

const topologia = () => lerJson(join(RAIZ, 'topologia.json'), { papeis: {}, arestas: [] });

function exigePapel(papel, onde) {
  const t = topologia();
  if (!papel) erro(`falta o papel em "${onde}". Papeis: ${Object.keys(t.papeis).join(', ')}`);
  if (!t.papeis[papel]) erro(`"${papel}" nao e' papel. Papeis: ${Object.keys(t.papeis).join(', ')}`);
}

function exigeAresta(de, para) {
  if (de === para) return; // duas sessoes do mesmo papel se falam sem aresta declarada
  const ok = topologia().arestas.some(([a, b]) => a === de && b === para);
  if (!ok) erro(`a topologia nao tem a aresta ${de} -> ${para}. Declare-a em topologia.json.`);
}

/** A sessao de quem chama: `--sessao`, ou `INTERFONE_SESSAO`, ou erro. */
function exigeSessao(explicita) {
  const s = explicita || process.env.INTERFONE_SESSAO;
  if (!s) erro('nao sei quem e voce. Passe --sessao <nome> ou exporte INTERFONE_SESSAO.');
  return s;
}

// ─── registro de sessoes ──────────────────────────────────────────────────────

const CAMINHO_SESSOES = () => join(RAIZ, 'sessoes.json');

function registrar(papel, sessao) {
  exigePapel(papel, 'registrar');
  if (!sessao) erro('registrar <papel> <sessao>');
  comTrava('sessoes', () => {
    const d = lerJson(CAMINHO_SESSOES(), { papeis: {} });
    const lista = (d.papeis[papel] ??= []);
    const ja = lista.find((s) => s.sessao === sessao);
    if (ja) ja.visto_em = agora();
    else lista.push({ sessao, visto_em: agora(), desde: agora() });
    gravarJson(CAMINHO_SESSOES(), d);
  });
  const outras = sessoesDe(papel).filter((s) => s.sessao !== sessao);
  console.log(`registrado: ${sessao} no papel "${papel}".`);
  if (outras.length) {
    console.log(`\nATENCAO: voce NAO esta sozinho neste papel. Tambem estao:`);
    for (const o of outras) console.log(`  ${o.sessao}  ${frescor(o)}`);
    console.log(`\nAntes de encostar em branch ou atividade, rode:  interfone travas`);
  }
  console.log(`\nO interfone NAO toca sozinho. Quem entrega e o hook global, a cada mensagem sua:`);
  console.log(`  interfone hook mensagem      (instalado em ~/.claude/settings.json)`);
  console.log(`Sem o hook, a caixa so' aparece se alguem lembrar de pedir:`);
  console.log(`  interfone caixa ${papel} --sessao ${sessao}`);
}

function tocarSinalDeVida(papel, sessao) {
  try {
    comTrava('sessoes', () => {
      const d = lerJson(CAMINHO_SESSOES(), { papeis: {} });
      const s = (d.papeis[papel] ?? []).find((x) => x.sessao === sessao);
      if (!s) return; // sessao nao registrada nao ganha frescor por olhar
      s.visto_em = agora();
      gravarJson(CAMINHO_SESSOES(), d);
    });
  } catch { /* frescor e' informativo: nunca derruba a leitura da caixa */ }
}

function sessoesDe(papel) {
  return lerJson(CAMINHO_SESSOES(), { papeis: {} }).papeis[papel] ?? [];
}

function frescor(s) {
  const min = Math.round((Date.now() - new Date(s.visto_em).getTime()) / 60000);
  return min <= FRESCOR_MIN ? `(vista ha ${min} min)` : `(FRIA — sem sinal ha ${min} min)`;
}

function quem(papel) {
  const papeis = papel ? [papel] : Object.keys(topologia().papeis);
  for (const p of papeis) {
    const lista = sessoesDe(p);
    console.log(`${p}: ${lista.length === 0 ? 'ninguem registrado' : ''}`);
    for (const s of lista) console.log(`  ${s.sessao}  ${frescor(s)}`);
  }
}

// ─── mensagens ────────────────────────────────────────────────────────────────

function enviar(de, para, assunto, o) {
  exigePapel(de, 'enviar (de)');
  exigePapel(para, 'enviar (para)');
  exigeAresta(de, para);
  if (!assunto || assunto.trim().length < 8) {
    erro('o assunto precisa ter ao menos 8 caracteres e dizer o que a mensagem resolve.');
  }
  const corpo = readFileSync(0, 'utf8');
  if (!corpo.trim()) erro('o corpo veio vazio (ele e lido do stdin).');

  const remetente = exigeSessao(o.sessao);
  // O id carrega a SESSAO, e nao so o papel: duas sessoes do mesmo papel
  // enviando no mesmo milissegundo sobrescreviam uma a outra em silencio.
  const id = `${agora().replace(/[:.]/g, '-')}-${de}-${remetente}`;
  const destino = join(RAIZ, para, 'inbox');
  mkdirSync(destino, { recursive: true });

  const envelope = [
    '---', `id: ${id}`, `de: ${de}`, `de_sessao: ${remetente}`, `para: ${para}`,
    ...(o.paraSessao ? [`para_sessao: ${o.paraSessao}`] : []),
    `assunto: ${assunto}`, `data: ${agora()}`,
    `prioridade: ${o.urgente ? 'urgente' : 'normal'}`,
    `requer_resposta: ${o.requerResposta ? 'sim' : 'nao'}`,
    ...(o.respondeA ? [`responde_a: ${o.respondeA}`] : []),
    '---', '',
  ].join('\n');

  writeFileSync(join(destino, `${id}.md`), envelope + corpo.replace(/\s*$/, '') + '\n');
  console.log(`enviado: ${id} -> ${para}/inbox${o.urgente ? '  [URGENTE]' : ''}`);

  const lista = sessoesDe(para);
  if (!lista.length) {
    console.log(`AVISO: nenhuma sessao registrada em "${para}". Ninguem vai ler isto tao cedo.`);
  } else {
    const frias = lista.filter((s) => !frescor(s).startsWith('(vista'));
    console.log(`${lista.length} sessao(oes) em "${para}"${frias.length ? `, ${frias.length} FRIA(S)` : ''}:`);
    for (const s of lista) console.log(`  ${s.sessao}  ${frescor(s)}`);
  }
  if (o.paraSessao && !lista.some((s) => s.sessao === o.paraSessao)) {
    console.log(`AVISO: "${o.paraSessao}" nao esta registrada em "${para}". A mensagem foi gravada assim mesmo.`);
  }
}

const caminhoLidos = (papel, sessao) => join(RAIZ, papel, 'lidos', `${sessao}.json`);
const lidosDe = (papel, sessao) => new Set(lerJson(caminhoLidos(papel, sessao), []));

/**
 * **Anunciar nao e' ler, e confundir as duas coisas custou 68 KB de contexto.**
 *
 * `pendentesDe` responde *"o que esta sessao ainda nao abriu com `ler`"*. O hook
 * usava isso como *"o que ainda nao mostrei"*, e as duas perguntas so' coincidem
 * enquanto a sessao le' tudo que chega. Ela nao le': mensagem endereçada a outro
 * assunto fica pendente de proposito, e volta a cada turno para sempre.
 *
 * Medido numa sessao real do `acme-app` em 18/09/2026:
 * **34 despejos, 567.401 bytes**, repetindo **as mesmas onze mensagens de
 * 15/09** — tres dias velhas, varias ja' resolvidas. O harness injeta ~2 KB de
 * previa por despejo, entao foram ~68 KB de contexto gastos em repeticao pura,
 * numa conta que estourava limite semanal.
 *
 * O conserto e' um segundo conjunto, por sessao: o que ela **ja' viu listado**.
 * Ele nao substitui `lidos` — `lidos` continua sendo o que o `status` e o
 * `arquivar` consultam para saber quem de fato abriu a mensagem, e anunciar nao
 * pode contar como ter aberto.
 *
 * **O arquivo se poda sozinho:** grava-se a lista das pendentes de agora, entao
 * id lido ou arquivado sai na proxima passada sem ninguem limpar nada.
 */
const caminhoAnunciadas = (papel, sessao) => join(RAIZ, papel, 'anunciadas', `${sessao}.json`);
const anunciadasDe = (papel, sessao) => {
  /**
   * **Le sem passar pelo `lerJson`, e isso e' deliberado.**
   *
   * `lerJson` chama `erro()` quando o JSON nao presta, e `erro()` em modo hook
   * faz `process.exit(0)`. Saida de processo **nao e' excecao**: um `try/catch`
   * em volta nao pega nada, e o hook morre calado — medido, com um arquivo
   * corrompido de proposito: zero linhas impressas, canal mudo.
   *
   * Seria a pior troca possivel. Este arquivo e' uma conveniencia de contexto;
   * ele nao pode ter poder de derrubar a entrega de mensagem. Entao aqui a
   * leitura e' propria e falha para o lado barulhento: sem conjunto, tudo volta
   * a ser inedito, o hook lista tudo, e a sessao seguinte regrava o arquivo bom.
   */
  try {
    const caminho = caminhoAnunciadas(papel, sessao);
    if (!existsSync(caminho)) return new Set();
    const bruto = readFileSync(caminho, 'utf8').trim();
    if (!bruto) return new Set();
    const lista = JSON.parse(bruto);
    return new Set(Array.isArray(lista) ? lista : []);
  } catch { return new Set(); }
};

/**
 * O que ESTA sessao ainda nao viu — a mesma regra em tres lugares (`caixa`,
 * `semear` e o hook), e por isso um lugar so'. Mensagem endereçada a outra
 * sessao nao conta, e o proprio eco tambem nao: em 09/09 o vigia acordou a
 * sessao com a mensagem que ela mesma tinha mandado, duas vezes.
 */
function pendentesDe(papel, sessao) {
  const lidos = lidosDe(papel, sessao);
  return mensagens(papel).filter((m) => {
    if (lidos.has(m.id)) return false;
    const paraSessao = cabecalho(m.texto, 'para_sessao');
    if (paraSessao && paraSessao !== sessao) return false;
    return cabecalho(m.texto, 'de_sessao') !== sessao;
  });
}

function marcarLido(papel, sessao, id) {
  const s = lidosDe(papel, sessao);
  s.add(id);
  gravarJson(caminhoLidos(papel, sessao), [...s].sort());
}

function cabecalho(texto, chave) {
  return new RegExp(`^${chave}: (.+)$`, 'm').exec(texto)?.[1];
}

function mensagens(papel) {
  const pasta = join(RAIZ, papel, 'inbox');
  if (!existsSync(pasta)) return [];
  return readdirSync(pasta).filter((f) => f.endsWith('.md')).sort().map((f) => {
    const texto = readFileSync(join(pasta, f), 'utf8');
    return { id: f.replace(/\.md$/, ''), arquivo: join(pasta, f), texto };
  });
}

function caixa(papel, o) {
  exigePapel(papel, 'caixa');
  const sessao = exigeSessao(o.sessao);
  // **Olhar a caixa E' o sinal de vida.** O vigia chama `caixa` a cada 90 s,
  // entao o `visto_em` se renova sozinho e ninguem precisa lembrar de um
  // comando de heartbeat. Sem isto toda sessao aparecia FRIA depois de 30 min,
  // e o aviso de frescor virava ruido que se aprende a ignorar.
  tocarSinalDeVida(papel, sessao);
  const lidos = lidosDe(papel, sessao);
  const todas = mensagens(papel);

  const registrada = sessoesDe(papel).some((s) => s.sessao === sessao);
  if (!registrada) {
    console.log(`AVISO: "${sessao}" nao esta registrada em "${papel}". Rode: interfone registrar ${papel} ${sessao}\n`);
  }

  let mostradas = 0;
  for (const m of todas) {
    const jaLi = lidos.has(m.id);
    if (jaLi && !o.todas) continue;
    const paraSessao = cabecalho(m.texto, 'para_sessao');
    // Mensagem endereçada a OUTRA sessao aparece esmaecida, e nao some: quem
    // divide o papel precisa saber o que o outro recebeu.
    const deOutro = paraSessao && paraSessao !== sessao;
    if (deOutro && !o.todas) continue;
    // **A propria mensagem nao volta como novidade.** Quando duas sessoes
    // dividem o papel, o que uma manda cai na caixa do papel — e portanto na
    // dela tambem. Sem esta linha o vigia acorda a sessao no proprio eco, que
    // foi exatamente o que aconteceu em 09/09, duas vezes.
    if (cabecalho(m.texto, 'de_sessao') === sessao && !o.todas) continue;
    mostradas++;
    const marcas = [
      cabecalho(m.texto, 'prioridade') === 'urgente' ? '[URGENTE]' : '',
      cabecalho(m.texto, 'requer_resposta') === 'sim' ? '[REQUER RESPOSTA]' : '',
      jaLi ? '[lida]' : '',
      paraSessao ? `[para ${paraSessao}]` : '',
    ].filter(Boolean).join(' ');
    console.log(`${m.id}${marcas ? `  ${marcas}` : ''}`);
    console.log(`  de: ${cabecalho(m.texto, 'de')} · ${cabecalho(m.texto, 'de_sessao') ?? '?'}`);
    const responde = cabecalho(m.texto, 'responde_a');
    if (responde) console.log(`  responde a: ${responde}`);
    console.log(`  ${cabecalho(m.texto, 'assunto')}`);
  }
  if (!mostradas) console.log(o.todas ? 'caixa vazia' : 'nada novo para esta sessao');
}

function ler(papel, id, o) {
  exigePapel(papel, 'ler');
  const sessao = exigeSessao(o.sessao);
  const m = mensagens(papel).find((x) => x.id === id);
  if (!m) erro(`nao achei ${id} na caixa de ${papel}. Ja foi arquivada? veja _lidos/`);
  process.stdout.write(m.texto);
  // NAO move. Marca. E' a diferenca inteira entre esta ferramenta e a anterior.
  marcarLido(papel, sessao, id);
}

function status(id) {
  for (const papel of Object.keys(topologia().papeis)) {
    const m = mensagens(papel).find((x) => x.id === id);
    if (!m) continue;
    const enviada = cabecalho(m.texto, 'data');
    const min = Math.round((Date.now() - new Date(enviada).getTime()) / 60000);
    console.log(`${id}\n  para: ${papel}  ·  enviada ha ${min} min  ·  ${cabecalho(m.texto, 'assunto')}`);
    const lista = sessoesDe(papel);
    if (!lista.length) return console.log('  NINGUEM registrado neste papel — ninguem leu.');
    for (const s of lista) {
      const leu = lidosDe(papel, s.sessao).has(id);
      console.log(`  ${leu ? 'LIDA por  ' : 'nao lida: '} ${s.sessao}  ${frescor(s)}`);
    }
    return;
  }
  erro(`nao achei ${id} em caixa nenhuma.`);
}

function arquivar(papel, id, o) {
  exigePapel(papel, 'arquivar');
  const m = mensagens(papel).find((x) => x.id === id);
  if (!m) erro(`nao achei ${id} na caixa de ${papel}.`);
  const naoLeram = sessoesDe(papel).filter((s) => !lidosDe(papel, s.sessao).has(id));
  if (naoLeram.length && !o.forcar) {
    erro(`${naoLeram.length} sessao(oes) ainda nao leram: ${naoLeram.map((s) => s.sessao).join(', ')}.\n` +
         `  Arquivar agora esconde a mensagem delas. Use --forcar se e' isso mesmo que voce quer.`);
  }
  if (naoLeram.length) {
    console.log(`AVISO: arquivando com --forcar, e ${naoLeram.length} sessao(oes) nunca leram: ` +
                `${naoLeram.map((s) => s.sessao).join(', ')}. Para elas a mensagem some.`);
  }
  const lidos = join(RAIZ, '_lidos');
  mkdirSync(lidos, { recursive: true });
  renameSync(m.arquivo, join(lidos, `${papel}--${id}.md`));
  console.log(`arquivada: ${id} -> _lidos/`);
}

/**
 * Semeia a linha de base do vigia — e **recusa** esconder o que nunca foi lido.
 *
 * A receita antiga mandava semear a partir da saida do `caixa`. Quem tivesse
 * mensagem pendente na hora de semear punha-a na linha de base como "ja avisada"
 * **sem nunca te-la lido**: o vigia jamais dispararia sobre ela, e ninguem
 * lembraria de rodar `caixa` — que e' exatamente o buraco que esta ferramenta
 * existe para fechar, chegando por outra porta.
 *
 * O achado e' da sessao `elcamargo-ai-flow-fe`, em 2026-09-09, que escapou por
 * acaso: leu a mensagem pendente antes de semear porque era a que estava
 * tratando.
 *
 * **Uma metade do relato dela nao procede, e conferi:** a caixa **nao** esvazia,
 * e o `status` continua dizendo a verdade — a mensagem segue listada como nao
 * lida. O que se perde e' so' o **aviso**. Como o vigia existe para ninguem
 * precisar lembrar, perder o aviso basta para ser defeito.
 */
function semear(papel, o) {
  exigePapel(papel, 'semear');
  const sessao = exigeSessao(o.sessao);
  const pendentes = pendentesDe(papel, sessao);

  if (pendentes.length && !o.forcar) {
    console.error(`interfone: ha ${pendentes.length} mensagem(ns) que voce nunca leu.`);
    console.error('  Semear agora poe cada uma na linha de base do vigia, e ele NUNCA vai avisar sobre elas.');
    console.error('  Leia-as primeiro, ou use --forcar se voce ja as tratou por fora.\n');
    for (const m of pendentes) console.error(`  ${m.id}  ${cabecalho(m.texto, 'assunto')}`);
    process.exit(1);
  }

  const arquivo = o.arquivo || join(RAIZ, `.vistos-${papel}-${sessao}.txt`);
  writeFileSync(arquivo, mensagens(papel).map((m) => m.id).join('\n') + '\n');
  console.log(`linha de base escrita em ${arquivo} (${mensagens(papel).length} id(s)).`);
  if (pendentes.length) {
    console.log(`AVISO: ${pendentes.length} delas voce NUNCA leu, e o vigia nao vai avisar. Elas continuam no \`caixa\`.`);
  }
  console.log(`Aponte o vigia para esse arquivo.`);
}

// ─── travas ───────────────────────────────────────────────────────────────────

const CAMINHO_TRAVAS = () => join(RAIZ, 'travas.json');

function travar(papel, recurso, motivo, o) {
  exigePapel(papel, 'travar');
  const sessao = exigeSessao(o.sessao);
  if (!recurso) erro('travar <papel> <recurso> "<motivo>"  — o recurso e a branch, o worktree ou a atividade');
  if (!motivo || motivo.trim().length < 8) erro('o motivo precisa dizer ate quando e por que.');
  comTrava('travas', () => {
    const d = lerJson(CAMINHO_TRAVAS(), { travas: [] });
    const dona = d.travas.find((t) => t.recurso === recurso);
    if (dona && dona.sessao !== sessao) {
      erro(`"${recurso}" ja esta travado por ${dona.sessao} (${dona.papel}) desde ${dona.desde}.\n` +
           `  Motivo: ${dona.motivo}\n  Fale com ela antes. Para assumir mesmo assim: destravar e travar de novo.`);
    }
    if (dona) { dona.motivo = motivo; dona.desde = agora(); }
    else d.travas.push({ recurso, papel, sessao, motivo, desde: agora() });
    gravarJson(CAMINHO_TRAVAS(), d);
  });
  console.log(`travado: ${recurso}  por ${sessao}`);
}

function travas() {
  const d = lerJson(CAMINHO_TRAVAS(), { travas: [] });
  if (!d.travas.length) return console.log('nenhuma trava. Ninguem reivindicou nada.');
  for (const t of d.travas) {
    const viva = sessoesDe(t.papel).find((s) => s.sessao === t.sessao);
    const est = viva ? frescor(viva) : '(sessao NAO REGISTRADA — trava provavelmente orfa)';
    console.log(`${t.recurso}\n  ${t.sessao} (${t.papel}) desde ${t.desde}  ${est}\n  ${t.motivo}`);
  }
}

function destravar(recurso, o) {
  const sessao = exigeSessao(o.sessao);
  comTrava('travas', () => {
    const d = lerJson(CAMINHO_TRAVAS(), { travas: [] });
    const i = d.travas.findIndex((t) => t.recurso === recurso);
    if (i < 0) erro(`"${recurso}" nao esta travado.`);
    if (d.travas[i].sessao !== sessao && !o.forcar) {
      erro(`"${recurso}" e de ${d.travas[i].sessao}, nao sua. Use --forcar se ela morreu.`);
    }
    d.travas.splice(i, 1);
    gravarJson(CAMINHO_TRAVAS(), d);
  });
  console.log(`destravado: ${recurso}`);
}

// ─── o papel deste repositorio, e a decisao desta sessao ─────────────────────

/**
 * **Por que o papel mora num arquivo do repositorio.**
 *
 * Ate 09/09/2026 o papel era digitado a mao em todo comando, e o mapa de quem
 * e' quem vivia so' no `topologia.json`, dentro da pasta da ferramenta. Quem
 * abrisse um chat num repositorio novo nao tinha como saber que o interfone
 * existia, muito menos de que papel aquele repositorio participava.
 *
 * `.interfone.json` na raiz responde isso onde a pergunta nasce. A janela
 * seguinte ja entra sabendo, sem ninguem lembrar de nada.
 */
function acharArquivoRepo(inicio) {
  let d = resolve(inicio);
  for (;;) {
    const alvo = join(d, ARQ_REPO);
    if (existsSync(alvo)) return alvo;
    const pai = dirname(d);
    if (pai === d) return null;
    d = pai;
  }
}

function papelDoRepo(inicio) {
  const arquivo = acharArquivoRepo(inicio);
  if (!arquivo) return null;
  const d = lerJson(arquivo, {});
  return d.papel ? { papel: d.papel, arquivo, raizRepo: dirname(arquivo) } : null;
}

/**
 * **Zero configuracao para quem ja esta no mapa.** O `topologia.json` ja diz o
 * repositorio de cada papel desde o primeiro dia. Exigir tambem um arquivo no
 * repo para reconhece-lo seria pedir duas vezes a mesma informacao — e deixaria
 * os repositorios ja declarados sem resposta ate alguem escrever o arquivo.
 *
 * O arquivo continua sendo a fonte quando existe: ele e' a decisao explicita, e
 * o mapa e' a inferencia.
 */
function papelPorTopologia(raizRepo) {
  const alvo = resolve(raizRepo);
  for (const [papel, d] of Object.entries(topologia().papeis)) {
    if (!d?.repositorio) continue;
    const r = resolve(d.repositorio);
    if (alvo === r || alvo.startsWith(`${r}/`)) return { papel, repositorio: r };
  }
  return null;
}

function gravarPapelDoRepo(raizRepo, papel) {
  const alvo = join(raizRepo, ARQ_REPO);
  const d = lerJson(alvo, {});
  d.papel = papel;
  d.porque ??= 'De que papel do interfone este repositorio participa. Quem abre um chat aqui entra neste papel.';
  gravarJson(alvo, d);
  return alvo;
}

/**
 * O nome da sessao: o repositorio mais dois caracteres do id da janela.
 *
 * O repositorio sozinho nao serve — foi exatamente a premissa que quebrou no
 * `canal.mjs`, com duas janelas no mesmo papel. Os dois caracteres vem do id
 * que o harness da a' sessao, entao duas janelas do mesmo repo se distinguem, e
 * a MESMA janela reaberta continua com o mesmo nome.
 */
function nomeDeSessao(raizRepo, idSessao) {
  const sufixo = (idSessao || '').replace(/[^a-z0-9]/gi, '').slice(0, 2);
  if (!sufixo) return null; // sem id nao ha nome: ver `exigeNomeDeSessao`
  return `${basename(resolve(raizRepo))}-${sufixo}`;
}

/**
 * **Nome inventado e' pior que nome ausente.**
 *
 * A primeira versao caia para o sufixo `xx` quando ninguem passava id. Duas
 * janelas do mesmo repositorio viravam a MESMA sessao — a premissa exata que
 * derrubou o `canal.mjs` — e, pior, o nome inventado nao batia com o que o hook
 * calcula do id real: a decisao ficava gravada num nome e a entrega era
 * conferida noutro, cada um em silencio.
 *
 * O id da janela nao e' adivinhavel, mas esta' a' vista de quem chama: o
 * diretorio de scratchpad da sessao termina nele.
 */
function exigeNomeDeSessao(raizRepo, idSessao) {
  const nome = nomeDeSessao(raizRepo, idSessao);
  if (nome) return nome;
  erro('nao sei que janela e voce, e inventar um nome faria duas janelas virarem uma.\n' +
       '  O hook imprime o comando ja' + "'" + ' com o --sessao certo: use aquele.\n' +
       '  Sem ele: os dois primeiros caracteres do id desta sessao (o final do caminho\n' +
       '  do seu scratchpad) sao o sufixo. Ex.: interfone entrar --id <id-da-sessao>');
}

const CAMINHO_DECISOES = () => join(RAIZ, 'decisoes.json');
const decisaoDe = (sessao) => lerJson(CAMINHO_DECISOES(), {})[sessao] ?? null;

/**
 * A decisao fica gravada porque **recusar tambem e' resposta**. Sem registrar o
 * "nao", o lembrete voltaria a cada mensagem para sempre — e lembrete que se
 * aprende a ignorar e' pior que lembrete nenhum.
 */
function gravarDecisao(sessao, estado, extra = {}) {
  comTrava('decisoes', () => {
    const d = lerJson(CAMINHO_DECISOES(), {});
    d[sessao] = { estado, em: agora(), ...extra };
    gravarJson(CAMINHO_DECISOES(), d);
  });
}

function criarPapel(papel, raizRepo, descricao) {
  comTrava('topologia', () => {
    const caminho = join(RAIZ, 'topologia.json');
    const t = lerJson(caminho, { papeis: {}, arestas: [] });
    t.papeis[papel] = {
      repositorio: raizRepo,
      descricao: descricao || `Criado por "interfone entrar" em ${agora()}.`,
    };
    gravarJson(caminho, t);
  });
}

function entrar(papelArg, o) {
  const raizRepo = resolve(o.repo || process.cwd());
  const doRepo = papelDoRepo(raizRepo);
  const papel = papelArg || doRepo?.papel || papelPorTopologia(raizRepo)?.papel;
  const sessao = o.sessao || process.env.INTERFONE_SESSAO
    || exigeNomeDeSessao(doRepo?.raizRepo ?? raizRepo, o.id);
  const t = topologia();

  if (!papel) {
    erro(`este repositorio nao declara papel (nao ha ${ARQ_REPO} aqui nem acima, e ele nao esta no topologia.json).\n` +
         `  Papeis que existem: ${Object.keys(t.papeis).join(', ')}\n` +
         `  entrar num deles:   interfone entrar <papel>\n` +
         `  criar um novo:      interfone entrar <papel> --novo`);
  }

  if (!t.papeis[papel]) {
    if (!o.novo) {
      erro(`"${papel}" ainda nao e' papel. Papeis: ${Object.keys(t.papeis).join(', ')}\n` +
           `  Para criar este:  interfone entrar ${papel} --novo`);
    }
    criarPapel(papel, raizRepo, o.descricao);
    console.log(`papel "${papel}" criado, com repositorio ${raizRepo}.`);
    console.log(`ATENCAO: ele ainda nao fala com ninguem. Quem pode falar com quem e' declarado:`);
    console.log(`  interfone ligar ${papel} <outro> --mao-dupla\n`);
  }

  registrar(papel, sessao);

  if (doRepo?.papel !== papel) {
    const alvo = gravarPapelDoRepo(raizRepo, papel);
    console.log(`\ngravado em ${alvo}: este repositorio participa de "${papel}".`);
    console.log(`A proxima janela aberta aqui ja entra sabendo.`);
  }
  gravarDecisao(sessao, 'entrou', { papel, repo: raizRepo });

  console.log('');
  caixa(papel, { ...o, sessao });
}

/**
 * A baixa ao fechar a janela. Sem ela, `quem` acumulava sessao morta e o unico
 * sinal era o frescor — que nao distingue "fechou" de "esta pensando ha 40 min".
 *
 * **Trava nao se solta sozinha aqui.** Uma trava pode representar trabalho
 * pela metade, e solta-la em silencio no fim da sessao entrega a branch a quem
 * chegar depois sem ninguem decidir isso. Ela vira ORFA no `travas`, que e'
 * visivel e nao e' automatico.
 */
function sair(o) {
  const sessao = exigeSessao(o.sessao);
  let de = null;
  comTrava('sessoes', () => {
    const d = lerJson(CAMINHO_SESSOES(), { papeis: {} });
    for (const [papel, lista] of Object.entries(d.papeis)) {
      const i = lista.findIndex((s) => s.sessao === sessao);
      if (i >= 0) { lista.splice(i, 1); de = papel; }
    }
    gravarJson(CAMINHO_SESSOES(), d);
  });
  console.log(de ? `baixa: ${sessao} saiu de "${de}".` : `"${sessao}" nao estava registrada.`);
  const minhas = lerJson(CAMINHO_TRAVAS(), { travas: [] }).travas.filter((t) => t.sessao === sessao);
  if (minhas.length) {
    console.log(`AVISO: ${minhas.length} trava(s) desta sessao ficam ORFAS — ninguem as soltou:`);
    for (const t of minhas) console.log(`  ${t.recurso} — ${t.motivo}`);
  }
}

function recusar(o) {
  const sessao = exigeSessao(o.sessao);
  gravarDecisao(sessao, 'recusou');
  console.log(`ok: nao lembro mais o interfone nesta sessao (${sessao}).`);
  console.log(`Para mudar de ideia a qualquer momento:  interfone entrar`);
}

function ligar(a, b, o) {
  exigePapel(a, 'ligar'); exigePapel(b, 'ligar');
  comTrava('topologia', () => {
    const caminho = join(RAIZ, 'topologia.json');
    const t = lerJson(caminho, { papeis: {}, arestas: [] });
    const por = (x, y) => { if (!t.arestas.some(([p, q]) => p === x && q === y)) t.arestas.push([x, y]); };
    por(a, b);
    if (o.maoDupla) por(b, a);
    gravarJson(caminho, t);
  });
  console.log(`ligado: ${a} -> ${b}${o.maoDupla ? `, e ${b} -> ${a}` : ''}`);
  if (!o.maoDupla) console.log(`(mao unica: ${b} ainda nao pode responder. --mao-dupla declara a volta.)`);
}

// ─── o hook: o unico jeito de isto acontecer sem alguem lembrar ──────────────

/**
 * **Uma obrigacao escrita em prosa nao acontece.**
 *
 * O interfone existia ha dois dias, num diretorio fora de todo repositorio, e
 * uma sessao inteira do `ai-flow` passou sem saber que ele existia. A causa nao
 * foi ma vontade: nao havia nada, em lugar nenhum, que uma janela nova lesse.
 *
 * **O que o hook consegue e o que nao consegue.** Ele imprime; ele nao abre
 * dialogo. A pergunta "voce quer entrar?" e' feita pelo assistente, a partir do
 * que este texto injeta no contexto — isso e' conselho, e conselho falha. A
 * defesa e' o lembrete VOLTAR a cada mensagem enquanto a decisao nao existir:
 * o esquecimento custa uma mensagem, nao a sessao inteira.
 *
 * A entrega da caixa, essa sim, e' mecanismo: nao depende de ninguem lembrar.
 */
function lerStdinSeguro() {
  try {
    if (process.stdin.isTTY) return '';
    return readFileSync(0, 'utf8');
  } catch { return ''; }
}

function hook(evento, o) {
  const bruto = lerStdinSeguro();
  let j = {};
  try { j = bruto ? JSON.parse(bruto) : {}; } catch { j = {}; }

  const cwd = resolve(j.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd());
  const id = j.session_id || process.env.CLAUDE_SESSION_ID || '';
  const doRepo = papelDoRepo(cwd);
  const sessao = o.sessao || nomeDeSessao(doRepo?.raizRepo ?? cwd, id);
  if (!sessao) return; // o harness nao mandou id: calar e' melhor que inventar
  const decisao = decisaoDe(sessao);

  if (evento === 'fim') {
    if (decisao?.estado === 'entrou') sair({ sessao });
    return;
  }

  if (decisao?.estado === 'recusou') return; // ele ja respondeu. Silencio e' a resposta.

  if (decisao?.estado === 'entrou') {
    const papel = decisao.papel;
    if (!topologia().papeis[papel]) return;
    tocarSinalDeVida(papel, sessao); // olhar a caixa E' o sinal de vida
    const novas = pendentesDe(papel, sessao);
    if (!novas.length) return; // silencio e' o comportamento correto quase sempre
    const urgente = (m) => cabecalho(m.texto, 'prioridade') === 'urgente';
    const urgentes = novas.filter(urgente).length;

    const jaVistas = anunciadasDe(papel, sessao);
    const ineditas = novas.filter((m) => !jaVistas.has(m.id));
    const repetidas = novas.length - ineditas.length;

    // Grava ANTES de imprimir: se o processo morrer no meio, o pior desfecho e'
    // repetir uma vez, nunca engolir uma mensagem que ninguem viu.
    try { gravarJson(caminhoAnunciadas(papel, sessao), novas.map((m) => m.id).sort()); } catch { /* repetir e' melhor que quebrar */ }

    if (!ineditas.length) {
      // Nada novo desde o turno passado. **A linha nao some**: a sessao continua
      // com mensagem nao lida, e esquecer disso e' pior que uma linha por turno.
      console.log(`[interfone] ${novas.length} nao lida(s) em "${papel}"${urgentes ? `, ${urgentes} URGENTE(S)` : ''} — ja listadas nesta sessao. Ver: interfone caixa ${papel} --sessao ${sessao}`);
      return;
    }

    const urgentesIneditas = ineditas.filter(urgente).length;
    console.log(`[interfone] ${ineditas.length} mensagem(ns) nova(s) em "${papel}"${urgentesIneditas ? `, ${urgentesIneditas} URGENTE(S)` : ''}:`);
    for (const m of ineditas) console.log(`  ${m.id}\n    ${cabecalho(m.texto, 'assunto')}`);
    if (repetidas) console.log(`  (+${repetidas} nao lida(s) ja listada(s) antes${urgentes - urgentesIneditas ? `, ${urgentes - urgentesIneditas} URGENTE(S)` : ''} — interfone caixa ${papel} --sessao ${sessao})`);
    console.log(`Leia com:  interfone ler ${papel} <id> --sessao ${sessao}`);
    return;
  }

  // Sem decisao. A pergunta e' do usuario, e quem pergunta e' o assistente.
  const doMapa = doRepo ? null : papelPorTopologia(cwd);
  if (doRepo || doMapa) {
    const papel = doRepo?.papel ?? doMapa.papel;
    const fonte = doRepo ? doRepo.arquivo : 'declarado no topologia.json';
    console.log(`[interfone] Este repositorio participa do papel "${papel}" (${fonte}), e esta janela nao entrou.`);
    console.log(`PERGUNTE AO USUARIO se ele quer entrar no interfone nesta sessao — ele pediu para ser perguntado, nao para entrar sozinho.`);
    console.log(`  se sim:  interfone entrar --sessao ${sessao}`);
    console.log(`  se nao:  interfone recusar --sessao ${sessao}`);
    return;
  }


  // Repositorio que ainda nao declarou papel: a oferta sai UMA vez, no inicio.
  // Repetir a cada mensagem em pasta que nao participa de nada e' ruido.
  if (evento !== 'inicio') return;
  const nomes = Object.keys(topologia().papeis);
  console.log(`[interfone] Este repositorio nao declara papel (nao ha ${ARQ_REPO} aqui nem acima).`);
  console.log(`PERGUNTE AO USUARIO se esta sessao deve entrar no interfone, e com que papel — um dos que existem ou um novo.`);
  console.log(`  papeis de hoje: ${nomes.join(', ') || '(nenhum)'}`);
  console.log(`  entrar num:  interfone entrar <papel> --sessao ${sessao}`);
  console.log(`  criar novo:  interfone entrar <papel> --novo --sessao ${sessao}`);
  console.log(`  nao:         interfone recusar --sessao ${sessao}`);
  console.log(`Entrar grava ${ARQ_REPO} na raiz, e a proxima janela aberta aqui ja sabe o papel.`);
}

// ─── linha de comando ─────────────────────────────────────────────────────────

const [comando, ...resto] = process.argv.slice(2);
const opt = (nome) => (resto.includes(nome) ? resto[resto.indexOf(nome) + 1] : null);
const o = {
  arquivo: opt('--arquivo'), sessao: opt('--sessao'), paraSessao: opt('--para-sessao'), respondeA: opt('--responde-a'),
  repo: opt('--repo'), id: opt('--id'), descricao: opt('--descricao'),
  urgente: resto.includes('--urgente'), requerResposta: resto.includes('--requer-resposta'),
  todas: resto.includes('--todas'), forcar: resto.includes('--forcar'),
  novo: resto.includes('--novo'), maoDupla: resto.includes('--mao-dupla'),
};
const comValor = new Set(['--sessao', '--para-sessao', '--responde-a', '--arquivo', '--repo', '--id', '--descricao']);
const pos = resto.filter((a, i) => !a.startsWith('--') && !comValor.has(resto[i - 1]));

switch (comando) {
  case 'entrar':    entrar(pos[0], o); break;
  case 'sair':      sair(o); break;
  case 'recusar':   recusar(o); break;
  case 'ligar':     ligar(pos[0], pos[1], o); break;
  case 'hook':
    MODO_HOOK = true;
    try { hook(pos[0], o); } catch { /* silencio: ver o comentario em `erro` */ }
    process.exit(0);
  case 'registrar': registrar(pos[0], pos[1]); break;
  case 'quem':      quem(pos[0]); break;
  case 'enviar':    enviar(pos[0], pos[1], pos[2], o); break;
  case 'caixa':     caixa(pos[0], o); break;
  case 'ler':       ler(pos[0], pos[1], o); break;
  case 'status':    status(pos[0]); break;
  case 'arquivar':  arquivar(pos[0], pos[1], o); break;
  case 'travar':    travar(pos[0], pos[1], pos[2], o); break;
  case 'semear':    semear(pos[0], o); break;
  case 'travas':    travas(); break;
  case 'destravar': destravar(pos[0], o); break;
  default:
    console.log(`interfone — o canal entre sessoes de IA.

  Uma JANELA de chat e' uma sessao. Um REPOSITORIO e' um papel. O papel deste
  repositorio fica em ${ARQ_REPO} na raiz dele; a sessao vem de --sessao ou de
  INTERFONE_SESSAO. Dados em ${RAIZ}

  entrar [<papel>] [--id <id-da-sessao>] [--novo]   entra pelo papel do repositorio, e GRAVA o papel nele
        o --id e' o id DESTA janela (o fim do caminho do seu scratchpad); sem ele a
        ferramenta recusa, porque inventar nome faz duas janelas virarem uma
  sair                                    da baixa ao fechar a janela
  recusar                                 silencia o convite nesta sessao
  ligar <a> <b> [--mao-dupla]             declara quem pode falar com quem
  quem [<papel>]                          quem esta em cada papel, e ha quanto tempo
  registrar <papel> <sessao>              entra sem passar pelo repositorio (o jeito antigo)
  enviar <de> <para> '<assunto>'          corpo pelo stdin
        [--para-sessao <s>] [--urgente] [--requer-resposta] [--responde-a <id>]
  caixa <papel> [--todas]                 o que ESTA sessao ainda nao leu
  ler <papel> <id>                        imprime e marca — NAO move
  status <id>                             quem leu, quem nao leu, ha quanto tempo
  arquivar <papel> <id> [--forcar]        move para _lidos; recusa se alguem nao leu
  semear <papel> [--arquivo <p>] [--forcar]  linha de base do vigia; RECUSA se voce nao leu tudo

  travar <papel> <recurso> '<motivo>'     reivindica branch, worktree ou atividade
  travas                                  quem reivindica o que — CONSULTE ANTES DE AGIR
  destravar <recurso> [--forcar]

  hook <inicio|mensagem|fim>              chamado pelo harness; le o JSON do evento no stdin

  Texto livre entre ASPAS SIMPLES: entre aspas duplas o shell come a crase e o
  argumento chega mutilado, sem erro nenhum.`);
}
