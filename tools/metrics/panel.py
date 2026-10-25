#!/usr/bin/env python3
"""O painel HTML das métricas, com drill-down de projeto até agente.

Uma página só, sem servidor e sem rede: os JSON coletados entram embutidos.
Isso é requisito, não economia — o painel precisa abrir de um anexo, de um
compartilhamento e de uma máquina que nunca instalou nada.

O que ele NÃO faz: buscar dado novo. Ele mostra o que o `coletar` gravou, com
a data da coleta no rodapé. Painel que parece vivo e está velho é pior que
painel velho assumido.
"""
from __future__ import annotations

import json
from pathlib import Path

# A PALETA sai separada porque o `publish.py` a IMPORTA: a pagina publicada
# e o painel sao documentos diferentes com a MESMA identidade. Duas copias
# de uma cor divergem no primeiro ajuste, e foi assim que o manual apareceu
# branco numa maquina e navy em outra.
#
# Ela nao contem `%`, e um teste prende isso: `MODELO` e' montado com
# `%(chave)s`, entao um `%` solto aqui quebraria a formatacao do painel
# inteiro no dia em que alguem acrescentasse uma cor com `hsl(... 50%)`.
PALETA = """:root{
  /* Identidade Elcamargo: navy profundo e ciano. FIXA de proposito -- sem `prefers-color-scheme`. A pagina
     e' um documento de marca, e o tema do sistema operacional de quem abre nao
     tem por que decidir a cor dela. Foi isso que fez o manual aparecer branco
     numa maquina e navy em outra. */
  /* Sem isto o navegador ainda pinta barra de rolagem, campo e seletor com o
     chrome CLARO por baixo de uma pagina escura. */
  color-scheme:dark;
  --papel:#0A1A2B;
  --superficie:#0F2438;
  --superficie-2:#13293F;
  --linha:#1E3A52;
  --linha-forte:#2C5273;
  --tinta:#E6F1F8;
  --tinta-media:#A9C0D4;
  --tinta-fraca:#7C97AE;
  --acento:#22D3EE;
  --acento-fraco:#5FE3F5;
  --acento-lavado:#0E2E3E;
  --ok:#34D399;
  --ok-lavado:#0C2A22;
  --parcial:#FBBF24;
  --parcial-lavado:#2E2510;
  --falhou:#F87171;
  --falhou-lavado:#331A1A;
  --codigo-fundo:#061321;
  --codigo-tinta:#CFE3F2;
  --sombra:0 1px 2px rgba(0,0,0,.45), 0 10px 28px -12px rgba(0,0,0,.75);
}
"""

MODELO = """<title>Métricas do %(projeto)s</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
""" + PALETA + """
*{box-sizing:border-box}
body{margin:0;background:var(--papel);color:var(--tinta);
  font-family:"IBM Plex Sans",-apple-system,sans-serif;font-size:15px;line-height:1.6;
  -webkit-font-smoothing:antialiased}
h1,h2{font-family:Spectral,Georgia,serif;font-weight:600;margin:0;line-height:1.2;text-wrap:balance}
h1{font-size:clamp(1.6rem,3.6vw,2.3rem);letter-spacing:-.02em}
h2{font-size:1.25rem;letter-spacing:-.01em}
p{margin:0}
.mono,code{font-family:"IBM Plex Mono",ui-monospace,monospace}
code{background:var(--superficie-2);border:1px solid var(--linha);border-radius:3px;padding:.08em .34em;font-size:.86em}
.rotulo{font-family:"IBM Plex Mono",monospace;font-size:.68rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.13em;color:var(--tinta-fraca)}
.topo{border-bottom:1px solid var(--linha);background:var(--superficie)}
.topo-in{max-width:1120px;margin:0 auto;padding:16px 24px;display:flex;flex-wrap:wrap;gap:10px 22px;align-items:baseline}
.marca{font-family:Spectral,serif;font-weight:600;font-size:1rem}
.topo .rotulo{margin-left:auto}
.folha{max-width:1120px;margin:0 auto;padding:26px 24px 80px}
.trilha{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:22px;font-size:.86rem}
.trilha button{background:none;border:none;padding:2px 4px;font:inherit;color:var(--acento);cursor:pointer;
  border-radius:3px;text-decoration:underline;text-underline-offset:3px}
.trilha button:hover,.trilha button:focus-visible{background:var(--acento-lavado)}
.trilha span.sep{color:var(--tinta-fraca)}
.trilha span.aqui{color:var(--tinta-media)}
.placar{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:1px;
  background:var(--linha);border:1px solid var(--linha);margin:18px 0 28px;box-shadow:var(--sombra)}
.cel{background:var(--superficie);padding:16px 16px 14px}
.cel .n{font-family:"IBM Plex Mono",monospace;font-weight:500;font-size:1.7rem;line-height:1.1;
  letter-spacing:-.03em;font-variant-numeric:tabular-nums;display:block;margin-bottom:4px}
.cel .n .un{font-size:.46em;color:var(--tinta-fraca);margin-left:.2em;letter-spacing:0}
.cel .lg{font-size:.79rem;color:var(--tinta-fraca);line-height:1.4}
.cel.forte .n{color:var(--acento)}
.rolagem{overflow-x:auto;border:1px solid var(--linha);background:var(--superficie);box-shadow:var(--sombra);margin-bottom:26px}
table{border-collapse:collapse;width:100%%;font-size:.87rem}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--linha);vertical-align:middle}
thead th{font-family:"IBM Plex Mono",monospace;font-size:.65rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.1em;color:var(--tinta-fraca);background:var(--superficie-2);white-space:nowrap;
  border-bottom:1px solid var(--linha-forte)}
tbody tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.clicavel{cursor:pointer}
tr.clicavel:hover td,tr.clicavel:focus-visible td{background:var(--acento-lavado)}
tr.clicavel td:first-child::after{content:" ›";color:var(--acento);font-weight:600}
.barra{display:block;height:4px;background:var(--acento);border-radius:2px;min-width:2px}
.chip{display:inline-flex;align-items:center;gap:.4em;font-family:"IBM Plex Mono",monospace;font-size:.68rem;
  font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:.16em .5em;border-radius:3px;white-space:nowrap}
.chip::before{content:"";width:5px;height:5px;border-radius:50%%;background:currentColor}
.chip.ok{color:var(--ok);background:var(--ok-lavado)}
.chip.parcial{color:var(--parcial);background:var(--parcial-lavado)}
.chip.falhou{color:var(--falhou);background:var(--falhou-lavado)}
.chip.exigida{color:var(--acento);background:var(--acento-lavado)}
.aviso{border:1px solid var(--falhou);background:var(--falhou-lavado);padding:14px 16px;margin-bottom:24px;
  font-size:.88rem;color:var(--tinta-media)}
.aviso .rotulo{color:var(--falhou);display:block;margin-bottom:6px}
.nota{border-left:2px solid var(--linha-forte);padding:2px 0 2px 14px;font-size:.87rem;color:var(--tinta-media);max-width:74ch}
.rodape{margin-top:44px;padding-top:20px;border-top:1px solid var(--linha);font-size:.82rem;color:var(--tinta-fraca);
  display:flex;flex-direction:column;gap:6px}
.vazio{padding:26px;color:var(--tinta-fraca);font-size:.9rem;text-align:center}
@media (max-width:640px){.folha{padding:20px 16px 60px}}
</style>

<header class="topo"><div class="topo-in">
  <span class="marca">Elcamargo AI&nbsp;Flow</span>
  <span class="rotulo">Métricas · %(projeto)s</span>
  <span class="rotulo">coletado em %(gerado_em)s</span>
</div></header>

<div class="folha">
  <nav class="trilha" id="trilha" aria-label="Navegação em níveis"></nav>
  <main id="conteudo"></main>
  <footer class="rodape">
    <span><strong>O que isto não prova.</strong> O custo é de tabela de API: quem roda por assinatura não paga
      isso, é teto. A hora humana é modelo — teto de %(teto)s min de leitura por interação, mais %(reentrada)s min
      de reentrada de contexto. Pontos de função não são medidos: são declarados no arquivo da atividade.</span>
    <span>Números somados dos transcritos de sessão em disco, agente por agente. Regerar:
      <code>metrics.py coletar</code> e <code>metrics.py painel</code>.</span>
  </footer>
</div>

<script>
const DADOS = %(dados)s;
const NOMES_STEP = %(nomes_step)s;

const nf = new Intl.NumberFormat("pt-BR");
const money = n => "US$ " + n.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
// Espelha `prazo_esta_aberto` do metrics.py: sem entrega, o prazo vai até o
// último registro e ainda cresce. Registro anterior à 2.5.0 não tem a chave —
// aí a resposta sai de `concluido_em`, que está no esquema desde o começo.
const prazoAberto = a => a.prazo_aberto != null ? !!a.prazo_aberto
                                                : !(a.concluido_em || "").trim();

let nivel = {tipo:"projeto"};

function chip(v,n){
  const cls = v==="ok"?"ok":v==="falhou"?"falhou":v==="exigida"?"exigida":"parcial";
  return `<span class="chip ${cls}">${esc(v)} ${n}</span>`;
}
function placar(itens){
  return `<div class="placar">${itens.map(i=>`<div class="cel${i.forte?" forte":""}">
    <span class="n">${i.valor}${i.un?`<span class="un">${i.un}</span>`:""}</span>
    <span class="lg">${i.leg}</span></div>`).join("")}</div>`;
}
function barra(v,pico){
  const p = pico>0 ? Math.max(2,Math.round(v/pico*100)) : 2;
  return `<span class="barra" style="width:${p}%%"></span>`;
}

function verProjeto(){
  const p = DADOS.projeto;
  const pico = Math.max(...p.lista.map(a=>a.custo_usd), 1);
  let html = `<h1>${esc(p.projeto)}</h1>
    <p class="nota" style="margin-top:10px">${p.atividades} atividade(s) conduzidas pelo fluxo,
      ${p.concluidas} concluída(s).</p>`;
  html += placar([
    {valor:nf.format(p.turnos), leg:"turnos de assistente", forte:1},
    {valor:nf.format(p.agentes), leg:"agentes disparados"},
    {valor:money(p.custo_usd), leg:"custo em tabela de API", forte:1},
    {valor:p.humano_h.toFixed(1), un:"h", leg:`hora humana, em ${p.interacoes} interações`},
    {valor:nf.format(p.entrega.insercoes), leg:`linhas entregues em ${p.entrega.arquivos} arquivos`},
  ]);
  if((p.nao_atribuidas||[]).length){
    html += `<div class="aviso"><span class="rotulo">O total acima é de menos, não de zero</span>
      ${p.nao_atribuidas.length} atividade(s) ficaram fora por falta de prova de atribuição:
      <code>${esc(p.nao_atribuidas.join(", "))}</code>. Elas aparecem na tabela sem número, de
      propósito — zero formatado se lê como medição, e o que houve nelas não foi zero: não se
      sabe de quem foi.</div>`;
  }
  if((p.sobreposicoes||[]).length){
    const soma = p.sobreposicoes.reduce((s,x)=>s+x.custo_contado_duas_vezes_usd,0);
    html += `<div class="aviso"><span class="rotulo">O total acima soma trabalho duas vezes</span>
      ${p.sobreposicoes.length} par(es) de atividades dividem branch e janela, então o transcrito não
      diz de qual delas é cada turno — até ${money(soma)} entram duas vezes.
      <ul style="margin:8px 0 0;padding-left:1.1em">
      ${p.sobreposicoes.map(s=>`<li><code>${esc(s.atividades.join(" + "))}</code> em
        <code>${esc(s.branch)}</code></li>`).join("")}</ul></div>`;
  }
  const conf = Object.entries(p.conferencias||{}).sort();
  if(conf.length) html += `<p style="margin-bottom:18px">${conf.map(([v,n])=>chip(v,n)).join(" ")}</p>`;
  html += `<h2>Atividades</h2><p class="nota" style="margin:6px 0 14px">Clique para descer ao nível de step.</p>
    <div class="rolagem"><table><thead><tr>
    <th>Atividade</th><th>Step</th><th class="n">Turnos</th><th class="n">Agentes</th>
    <th class="n">US$</th><th class="n">Humanas</th><th class="n">Prazo</th><th style="width:15%%">Fatia</th>
    </tr></thead><tbody>` +
    p.lista.map(a=> a.atribuicao==="sem-prova"
      ? `<tr><td><strong>${esc(a.id)}</strong><br><span style="color:var(--tinta-fraca);font-size:.9em">${esc((a.titulo||"").slice(0,54))}</span></td>
      <td class="mono" style="font-size:.82rem">${esc(a.step)} · ${esc(a.trilha)}</td>
      <td colspan="6" style="color:var(--tinta-fraca)">não atribuída — ${esc(a.motivo_atribuicao||"")}</td></tr>`
      : `<tr class="clicavel" tabindex="0" data-id="${esc(a.id)}">
      <td><strong>${esc(a.id)}</strong><br><span style="color:var(--tinta-fraca);font-size:.9em">${esc((a.titulo||"").slice(0,54))}</span></td>
      <td class="mono" style="font-size:.82rem">${esc(a.step)} · ${esc(a.trilha)}</td>
      <td class="n">${nf.format(a.turnos)}</td><td class="n">${a.agentes}</td>
      <td class="n">${a.custo_usd.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})}</td>
      <td class="n">${a.humano.total_h.toFixed(2)}h</td><td class="n" title="${prazoAberto(a)?"em andamento: vai até agora, não até a entrega":"até a entrega"}">${a.prazo_h.toFixed(1)}h${prazoAberto(a)?"+":""}</td>
      <td>${barra(a.custo_usd,pico)}</td></tr>`).join("") +
    `</tbody></table></div>`;
  return html;
}

function verAtividade(id){
  const a = DADOS.atividades[id];
  if(!a) return `<div class="vazio">Atividade não coletada.</div>`;
  if(a.atribuicao==="sem-prova"){
    return `<h1>${esc(a.id)}</h1><p class="nota" style="margin-top:10px">${esc(a.titulo||"")}</p>
      <div class="aviso"><span class="rotulo">não consegui atribuir</span>
      ${esc(a.motivo_atribuicao||"")}. Não mostro custo, prazo nem hora humana: os três sairiam
      zero, e zero aqui não significa que nada aconteceu — significa que não se sabe de quem foi
      o que aconteceu.</div>`;
  }
  let html = `<h1>${esc(a.id)}</h1><p class="nota" style="margin-top:10px">${esc(a.titulo)}<br>
    trilha <code>${esc(a.trilha)}</code> · step ${esc(a.step)} · ${esc(a.status)} ·
    <code>${esc(a.branch)}</code></p>`;
  const itens = [
    {valor:nf.format(a.turnos), leg:"turnos de assistente", forte:1},
    {valor:money(a.custo_usd), leg:"custo em tabela de API", forte:1},
    {valor:a.humano.total_h.toFixed(2), un:"h", leg:`hora humana em ${a.humano.interacoes} interações`},
    {valor:a.prazo_h.toFixed(1), un:"h", leg:prazoAberto(a)
      ? "prazo, do primeiro registro até agora — ainda cresce"
      : "prazo, do primeiro registro à entrega"},
    {valor:a.humano.perguntas_portao, leg:"perguntas de portão respondidas"},
  ];
  if(a.cauda_h) itens.push({valor:a.cauda_h.toFixed(1), un:"h",
    leg:"cauda: trabalho na mesma worktree DEPOIS da entrega"});
  if(a.pf) itens.push({valor:a.pf, un:"PF", leg:`declarado · ${(a.h_por_pf_humano||0).toFixed(3)} h/PF`});
  if(a.pf_aferido) itens.push({valor:a.pf_aferido, un:"PF",
    leg:`aferido · ${(a.h_por_pf_humano_aferido||0).toFixed(3)} h/PF`});
  html += placar(itens);
  const dv = a.divergencia_pf;
  if(dv && dv.sentido!=="iguais"){
    const sinal = dv.absoluta>0 ? "+" : "";
    html += `<div class="aviso"><span class="rotulo">declarado e aferido divergem</span>
      ${sinal}${dv.absoluta} PF (${sinal}${dv.percentual.toFixed(1)}%%) — ${esc(dv.sentido)} que o
      entregue. Os dois NÃO são desempatados: nem o transcrito nem o Git dizem qual estava certo.
      ${a.pf_inventario ? `Confira <code>${esc(a.pf_inventario)}</code> antes de citar qualquer
      h/PF.` : "E não há inventário apontado para conferir."}</div>`;
  }
  if(!a.pf && !a.pf_aferido) html += `<p class="nota" style="margin-bottom:22px">Sem pontos de função:
    nada declarado no cabeçalho e nada aferido. A ferramenta não MEDE ponto de função — ela lê o que
    foi declarado. Para ver produtividade por PF, acrescente <code>pf: &lt;n&gt;</code> ao cabeçalho de
    <code>.agents/atividades/${esc(a.id)}.md</code>.</p>`;

  const e = a.entrega || {};
  if(e.arquivos) html += `<p class="nota" style="margin-bottom:22px"><strong>Entrega:</strong>
    ${e.arquivos} arquivos, +${nf.format(e.insercoes)} −${nf.format(e.remocoes)} em ${e.commits} commits.
    ${e.testes && e.testes.insercoes ? `Testes: +${nf.format(e.testes.insercoes)} em ${e.testes.arquivos} arquivos.` : ""}
    ${e.docs && e.docs.insercoes ? `Documentos: +${nf.format(e.docs.insercoes)}.` : ""}</p>`;

  if(a.steps.length){
    const pico = Math.max(...a.steps.map(s=>s.custo_usd), 1);
    html += `<h2>Steps</h2><p class="nota" style="margin:6px 0 14px">Clique para ver os agentes do step.</p>
      <div class="rolagem"><table><thead><tr><th>Step</th><th class="n">Agentes</th>
      <th class="n">Turnos</th><th class="n">US$</th><th style="width:26%%">Fatia</th></tr></thead><tbody>` +
      a.steps.map(s=>`<tr class="clicavel" tabindex="0" data-step="${s.step}">
        <td><strong>${s.step}</strong> · ${esc(NOMES_STEP[s.step]||"?")}</td>
        <td class="n">${s.agentes}</td><td class="n">${nf.format(s.turnos)}</td>
        <td class="n">${s.custo_usd.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})}</td>
        <td>${barra(s.custo_usd,pico)}</td></tr>`).join("") + `</tbody></table></div>`;
  }

  const porFerr = a.por_ferramenta || {};
  const chaves = Object.keys(porFerr).sort();
  if(chaves.length){
    html += `<h2>Conferências mecânicas</h2><p class="nota" style="margin:6px 0 14px">
      As linhas com <code>falhou</code> ou <code>nao-coberta</code> são onde a entrega foi devolvida
      ou onde a cobertura ficou declaradamente incompleta.</p>
      <div class="rolagem"><table><thead><tr><th>Ferramenta</th><th>Veredictos</th></tr></thead><tbody>` +
      chaves.map(f=>{
        const d = porFerr[f];
        const ruim = d.falhou || d["nao-coberta"] || d.exigida;
        return `<tr><td class="mono"${ruim?' style="font-weight:600"':""}>${esc(f)}</td>
          <td>${Object.entries(d).sort().map(([v,n])=>chip(v,n)).join(" ")}</td></tr>`;
      }).join("") + `</tbody></table></div>`;
  }
  return html;
}

function verStep(id, step){
  const a = DADOS.atividades[id];
  const agentes = (a.detalhe_agentes||[]).filter(g=>g.step===step);
  let html = `<h1>Step ${step} · ${esc(NOMES_STEP[step]||"?")}</h1>
    <p class="nota" style="margin-top:10px">Em <code>${esc(id)}</code> — ${agentes.length} agente(s).</p>`;
  if(!agentes.length) return html + `<div class="vazio">Nenhum agente atribuído a este step.</div>`;
  const pico = Math.max(...agentes.map(g=>g.custo_usd), 1);
  const soma = agentes.reduce((s,g)=>s+g.custo_usd,0);
  const turnos = agentes.reduce((s,g)=>s+g.turnos,0);
  html += placar([
    {valor:agentes.length, leg:"agentes neste step", forte:1},
    {valor:nf.format(turnos), leg:"turnos somados"},
    {valor:money(soma), leg:"custo do step", forte:1},
  ]);
  html += `<div class="rolagem"><table><thead><tr><th>Agente</th><th>Papel</th>
    <th class="n">Turnos</th><th class="n">Saída</th><th class="n">US$</th>
    <th style="width:16%%">Fatia</th></tr></thead><tbody>` +
    agentes.map(g=>`<tr><td class="mono">${esc(g.id)}<br>
      <span style="color:var(--tinta-fraca);font-size:.86em;font-family:'IBM Plex Sans',sans-serif">${esc(g.prompt.slice(0,64))}</span></td>
      <td><span class="chip ${g.papel==="titular"?"ok":g.papel==="auditor"?"exigida":"parcial"}">${esc(g.papel)}</span></td>
      <td class="n">${nf.format(g.turnos)}</td>
      <td class="n">${nf.format(g.tokens.saida)}</td>
      <td class="n">${g.custo_usd.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})}</td>
      <td>${barra(g.custo_usd,pico)}</td></tr>`).join("") + `</tbody></table></div>`;
  return html;
}

function trilha(){
  const t = document.getElementById("trilha");
  const partes = [`<button data-ir="projeto">Projeto</button>`];
  if(nivel.tipo!=="projeto"){
    partes.push(`<span class="sep">/</span>`);
    if(nivel.tipo==="step") partes.push(`<button data-ir="atividade">${esc(nivel.id)}</button>`);
    else partes.push(`<span class="aqui">${esc(nivel.id)}</span>`);
  }
  if(nivel.tipo==="step") partes.push(`<span class="sep">/</span><span class="aqui">Step ${nivel.step}</span>`);
  t.innerHTML = partes.join(" ");
  t.querySelectorAll("button").forEach(b=>b.onclick = ()=>{
    nivel = b.dataset.ir==="projeto" ? {tipo:"projeto"} : {tipo:"atividade", id:nivel.id};
    desenhar();
  });
}

function desenhar(){
  const alvo = document.getElementById("conteudo");
  alvo.innerHTML = nivel.tipo==="projeto" ? verProjeto()
    : nivel.tipo==="atividade" ? verAtividade(nivel.id)
    : verStep(nivel.id, nivel.step);
  trilha();
  alvo.querySelectorAll("tr.clicavel").forEach(tr=>{
    const ir = ()=>{
      if(tr.dataset.id) nivel = {tipo:"atividade", id:tr.dataset.id};
      else nivel = {tipo:"step", id:nivel.id, step:Number(tr.dataset.step)};
      desenhar();
      window.scrollTo({top:0});
    };
    tr.onclick = ir;
    tr.onkeydown = ev => { if(ev.key==="Enter"||ev.key===" "){ ev.preventDefault(); ir(); } };
  });
}

desenhar();
</script>
"""


# O `<meta charset>` NAO e' cerimonia: sem ele o navegador cai no encoding do
# sistema e a pagina abre "MÃ©tricas". Nao aparecia porque o painel so' tinha
# sido aberto de `file://` numa maquina que adivinhou certo -- servido por HTTP
# sem charset no cabecalho, ou aberto noutra locale, ele quebra. Achado ao
# publicar a pagina irma num servidor local.
CABECA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
"""

RODAPE = """
</body>
</html>
"""

FECHA_CABECA = "</style>"


def esqueleto(corpo: str) -> str:
    """O `</head><body>` entra logo DEPOIS do `</style>`, e não antes do `<title>`.

    O `MODELO` começa por título, fontes e folha de estilo — que são cabeça — e
    só então abre o `<header>`. Enfiar `<body>` antes de tudo deixaria o
    `<title>` dentro do corpo: o navegador conserta, o validador não, e um
    documento que só funciona por conserto de navegador é o tipo de coisa que
    quebra no próximo leitor (um cliente de e-mail, um conversor de PDF).
    """
    corpo = corpo.lstrip("\n")
    corte = corpo.find(FECHA_CABECA)
    if corte < 0:                       # sem folha de estilo, tudo é corpo
        return CABECA + "</head>\n<body>\n" + corpo + RODAPE
    corte += len(FECHA_CABECA)
    return (CABECA + corpo[:corte] + "\n</head>\n<body>\n"
            + corpo[corte:].lstrip("\n") + RODAPE)


def gerar(destino: Path, projeto: dict, atividades: dict,
          nomes_step: dict | None = None) -> Path:
    dados = json.dumps({"projeto": projeto, "atividades": atividades},
                       ensure_ascii=False)
    # Os nomes vêm do `STEPS` do flow_state, pelo `metrics.py`. Até a 2.56.0
    # eram uma cópia à mão aqui dentro — e cópia de nome de step é a que
    # envelhece calada quando um cargo muda de nome.
    if nomes_step is None:
        from metrics import NOMES_STEP as nomes_step
    p = projeto.get("parametros", {})
    html = MODELO % {
        "projeto": projeto.get("projeto", "projeto"),
        "gerado_em": projeto.get("gerado_em", "?"),
        "teto": p.get("teto_leitura_min", "?"),
        "reentrada": p.get("reentrada_min", "?"),
        "dados": dados,
        "nomes_step": json.dumps({str(k): v for k, v in nomes_step.items()},
                                 ensure_ascii=False),
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(esqueleto(html), encoding="utf-8")
    return destino
