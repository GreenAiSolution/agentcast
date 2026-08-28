"""Render a Session into one self-contained HTML file (no external assets)."""
from __future__ import annotations

import html
import json
import os

from .model import Session
from .redact import redact_obj
from .util import shorten_home, parse_ts
from . import __version__

ACTIVE_GAP_CAP_S = 300  # gaps longer than this are not counted as "active" time


def active_seconds(s: Session) -> float:
    prev = None
    total = 0.0
    for st in s.steps:
        if not st.t:
            continue
        cur = parse_ts(st.t)
        if prev is not None:
            total += min(ACTIVE_GAP_CAP_S, max(0.0, (cur - prev).total_seconds()))
        prev = cur
    return total


def session_payload(s: Session, do_redact: bool = True, anon_paths: bool = True) -> dict:
    d = s.to_dict()
    d["active_s"] = active_seconds(s)
    d["agentcast_version"] = __version__
    if anon_paths:
        d["cwd"] = shorten_home(d["cwd"])
        d["source"] = shorten_home(d["source"])
        home = os.path.expanduser("~")
        if home and len(home) > 3:
            txt = json.dumps(d)
            txt = txt.replace(json.dumps(home)[1:-1], "~")
            d = json.loads(txt)
    if do_redact:
        d = redact_obj(d)
    return d


def render_html(s: Session, do_redact: bool = True, anon_paths: bool = True) -> str:
    payload = session_payload(s, do_redact, anon_paths)
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(payload.get("title") or "agentcast replay")
    return TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · agentcast</title>
<style>
:root{--bg:#0b0d10;--bg2:#12151a;--bg3:#1a1e25;--line:#262b34;--fg:#e6e8eb;--dim:#8b93a1;--mute:#5c6470;
--prompt:#f5c451;--say:#7cc4ff;--think:#b58cff;--tool:#5ee3a1;--err:#ff6b6b;--note:#8b93a1;--add:#1f4d33;--del:#5a2430;--addfg:#a6f4c5;--delfg:#ffb3b3;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme: light){:root{--bg:#f7f8fa;--bg2:#ffffff;--bg3:#eef1f5;--line:#dde2ea;--fg:#14171c;--dim:#5b6472;--mute:#8a93a2;--add:#dcfce7;--del:#fee2e2;--addfg:#166534;--delfg:#991b1b;--say:#0f6fd6;--tool:#118a55;--think:#7a3ff2;--prompt:#b7791f}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 var(--sans);overflow:hidden}
a{color:inherit}
#app{display:grid;grid-template-rows:auto auto 1fr;height:100vh}
header{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;padding:12px 18px;border-bottom:1px solid var(--line);background:var(--bg2)}
header h1{font-size:16px;margin:0;font-weight:650;letter-spacing:-.01em;max-width:52vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{font:600 11px/1 var(--mono);padding:5px 8px;border-radius:6px;background:var(--bg3);color:var(--dim);border:1px solid var(--line);white-space:nowrap}
.badge.agent{color:var(--tool);border-color:var(--tool)}
.stats{display:flex;gap:16px;margin-left:auto;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;align-items:flex-end;line-height:1.15}
.stat b{font:650 15px var(--mono);color:var(--fg)}.stat span{font-size:10.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
#strip{position:relative;height:34px;border-bottom:1px solid var(--line);background:var(--bg2);display:flex;align-items:stretch;padding:6px 18px;gap:0;cursor:pointer}
#strip .seg{flex:1 1 0;min-width:1px;margin:0 .5px;border-radius:1px;opacity:.55;background:var(--mute)}
#strip .seg.prompt{background:var(--prompt)}#strip .seg.say{background:var(--say)}#strip .seg.think{background:var(--think)}#strip .seg.tool{background:var(--tool)}#strip .seg.err{background:var(--err)}#strip .seg.note{background:var(--note)}
#strip .seg.cur{opacity:1;box-shadow:0 0 0 1.5px var(--fg)}#strip .seg.past{opacity:.9}
main{display:grid;grid-template-columns:380px 1fr;min-height:0}
#left{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0;background:var(--bg2)}
#toolbar{display:flex;gap:6px;padding:10px 12px;border-bottom:1px solid var(--line);align-items:center;flex-wrap:wrap}
#toolbar input{flex:1 1 120px;background:var(--bg);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:6px 9px;font:13px var(--sans);outline:none}
#toolbar input:focus{border-color:var(--say)}
.chip{font:600 11px var(--mono);padding:4px 7px;border-radius:5px;border:1px solid var(--line);background:transparent;color:var(--dim);cursor:pointer;user-select:none}
.chip.on{color:var(--fg);border-color:var(--dim);background:var(--bg3)}
.chip.prompt.on{color:var(--prompt)}.chip.say.on{color:var(--say)}.chip.think.on{color:var(--think)}.chip.tool.on{color:var(--tool)}.chip.err.on{color:var(--err)}
#steps{overflow:auto;flex:1;min-height:0}
.step{display:grid;grid-template-columns:8px 1fr auto;gap:10px;padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer;align-items:start}
.step:hover{background:var(--bg3)}.step.sel{background:var(--bg3);box-shadow:inset 3px 0 0 var(--fg)}
.step .dot{width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--mute)}
.step.prompt .dot{background:var(--prompt)}.step.say .dot{background:var(--say)}.step.think .dot{background:var(--think)}.step.tool .dot{background:var(--tool)}.step.err .dot{background:var(--err)}
.step .k{font:600 11px var(--mono);color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.step .k .tn{color:var(--fg);text-transform:none;letter-spacing:0}
.step .s{font-size:12.5px;color:var(--fg);opacity:.85;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:290px}
.step .s.mono{font-family:var(--mono);font-size:11.5px}
.step .t{font:11px var(--mono);color:var(--mute);white-space:nowrap}
.step.side .k::before{content:"↳ ";color:var(--mute)}
#right{display:flex;flex-direction:column;min-height:0}
#detail{overflow:auto;padding:18px 22px;flex:1;min-height:0}
#detail h2{margin:0 0 4px;font-size:15px;font-weight:650;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#detail .meta{font:12px var(--mono);color:var(--mute);margin-bottom:14px;display:flex;gap:14px;flex-wrap:wrap}
pre{background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow:auto;font:12.5px/1.5 var(--mono);white-space:pre-wrap;word-break:break-word;margin:0 0 14px;max-height:60vh}
.prose{white-space:pre-wrap;line-height:1.6;font-size:14px;max-width:80ch}
.prose.prompt{border-left:3px solid var(--prompt);padding-left:14px}.prose.think{color:var(--dim);font-style:italic;border-left:3px solid var(--think);padding-left:14px}
.lbl{font:600 11px var(--mono);color:var(--mute);text-transform:uppercase;letter-spacing:.06em;margin:14px 0 6px}
.diff{font:12.5px/1.45 var(--mono);border:1px solid var(--line);border-radius:8px;overflow:auto;margin-bottom:14px;max-height:70vh}
.diff .ln{padding:0 12px;white-space:pre;display:block}
.diff .h{color:var(--dim);background:var(--bg3)}.diff .a{background:var(--add);color:var(--addfg)}.diff .d{background:var(--del);color:var(--delfg)}.diff .hd{color:var(--say);background:var(--bg2);font-weight:600}
.fp{font:12px var(--mono);color:var(--say)}
.err{color:var(--err)}
#files{border-top:1px solid var(--line);background:var(--bg2);max-height:38vh;overflow:auto;display:none}
#files.on{display:block}
#files table{width:100%;border-collapse:collapse;font:12px var(--mono)}
#files td{padding:5px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
#files td:first-child{width:100%;white-space:normal;word-break:break-all}
#files tr:hover{background:var(--bg3);cursor:pointer}
#files .op{color:var(--dim)}.op.edit,.op.write,.op.create{color:var(--tool)}.op.delete{color:var(--err)}
#ctrl{display:flex;gap:8px;align-items:center;padding:8px 12px;border-top:1px solid var(--line);background:var(--bg2);font:12px var(--mono);color:var(--dim)}
#ctrl button{background:var(--bg3);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:5px 10px;font:600 12px var(--mono);cursor:pointer}
#ctrl button:hover{border-color:var(--dim)}
#ctrl .sp{margin-left:auto}
.kbd{border:1px solid var(--line);border-radius:4px;padding:0 5px;font:11px var(--mono);color:var(--dim)}
#empty{padding:40px;color:var(--dim);max-width:60ch}
@media (max-width:900px){main{grid-template-columns:1fr}#right{display:none}#right.show{display:flex;position:fixed;inset:0;top:0;background:var(--bg);z-index:5}header h1{max-width:100%}.stats{margin-left:0}}
</style></head><body>
<div id="app">
<header>
 <span class="badge agent" id="agent"></span>
 <h1 id="title"></h1>
 <span class="badge" id="model"></span>
 <span class="badge" id="date"></span>
 <div class="stats" id="stats"></div>
</header>
<div id="strip" title="Timeline — click to jump"></div>
<main>
 <section id="left">
  <div id="toolbar">
   <input id="q" placeholder="Search steps  ( / )" autocomplete="off">
   <span class="chip prompt on" data-k="prompt">prompt</span>
   <span class="chip say on" data-k="say">say</span>
   <span class="chip think on" data-k="think">think</span>
   <span class="chip tool on" data-k="tool">tool</span>
   <span class="chip err" data-k="err" title="only errors">errors</span>
  </div>
  <div id="steps"></div>
  <div id="ctrl">
   <button id="play" title="space">▶ play</button>
   <button id="speed" title="cycle speed">4×</button>
   <span id="pos"></span>
   <span class="sp"></span>
   <button id="fbtn" title="f">files</button>
   <span><span class="kbd">j</span>/<span class="kbd">k</span> step</span>
  </div>
 </section>
 <section id="right">
  <div id="detail"><div id="empty">Select a step. <br><br>Keyboard: <span class="kbd">j</span> / <span class="kbd">k</span> move, <span class="kbd">space</span> play, <span class="kbd">f</span> files changed, <span class="kbd">/</span> search.</div></div>
  <div id="files"></div>
 </section>
</main>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
const S=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtInt=n=>n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e4?Math.round(n/1e3)+'k':n>=1e3?(n/1e3).toFixed(1)+'k':String(n|0);
const fmtDur=s=>{s=Math.max(0,s|0);if(s<60)return s+'s';const m=Math.floor(s/60);if(m<60)return m+'m '+String(s%60).padStart(2,'0')+'s';return Math.floor(m/60)+'h '+String(m%60).padStart(2,'0')+'m'};
const t0=S.steps.length?Date.parse(S.steps[0].t):0;const rel=t=>{const d=(Date.parse(t)-t0)/1000;return isFinite(d)?'+'+fmtDur(d):''};
const isErr=s=>s.kind==='tool'&&s.error;
// header
$('#agent').textContent=S.agent;$('#title').textContent=S.title||'(untitled)';$('#title').title=S.title||'';
$('#model').textContent=(S.models&&S.models.length?S.models.join(', '):'model ?');
$('#date').textContent=S.started?new Date(S.started).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'';
const u=S.usage||{};const tok=(u.input||0)+(u.output||0)+(u.cache_read||0)+(u.cache_write||0);
const stats=[[fmtDur(S.active_s||S.duration_s||0),'active'],[S.prompts,'prompts'],[S.tool_calls,'tool calls'],[(S.blast_radius||[]).length,'files changed'],[fmtInt(tok),'tokens'],[S.cost_usd!=null?'$'+S.cost_usd.toFixed(2):'—','est. cost']];
$('#stats').innerHTML=stats.map(([v,l])=>`<div class="stat"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join('');
// state
let filt={prompt:1,say:1,think:1,tool:1,err:0},q='',fileFilter=null,sel=-1,playing=false,timer=null,speedIdx=1;const speeds=[1,4,16,64];
const visible=()=>S.steps.filter(s=>{const k=s.kind==='note'?'say':s.kind;if(filt.err&&!isErr(s))return false;if(!filt[k]&&s.kind!=='note')return false;if(fileFilter&&!(s.files||[]).some(f=>f.path===fileFilter))return false;if(q){const hay=(s.text||'')+' '+(s.tool||'')+' '+JSON.stringify(s.input||{})+' '+(s.output||'');if(!hay.toLowerCase().includes(q))return false}return true});
function summary(s){if(s.kind==='tool'){const i=s.input||{};const fp=i.file_path||i.path||i.notebook_path;if(fp)return{mono:1,t:fp.split('/').slice(-2).join('/')};if(i.command)return{mono:1,t:i.command};if(i.cmd)return{mono:1,t:Array.isArray(i.cmd)?i.cmd.join(' '):i.cmd};if(i.pattern)return{mono:1,t:i.pattern};if(i.patch)return{mono:1,t:((s.files||[])[0]||{}).path||'patch'};if(i.description)return{t:i.description};if(i.prompt)return{t:i.prompt};if(i.query)return{t:i.query};if(i.url)return{mono:1,t:i.url};const k=Object.keys(i)[0];return{mono:1,t:k?String(i[k]).slice(0,120):''}}return{t:(s.text||'').replace(/\s+/g,' ').trim()}}
function renderStrip(){const el=$('#strip');el.innerHTML='';const n=S.steps.length;const maxSeg=1400;const step=Math.max(1,Math.ceil(n/maxSeg));for(let i=0;i<n;i+=step){const s=S.steps[i];const d=document.createElement('div');d.className='seg '+(isErr(s)?'err':s.kind)+(i<=sel?' past':'')+(i<=sel&&sel<i+step?' cur':'');d.dataset.i=i;d.title='#'+i+' '+s.kind+(s.tool?' '+s.tool:'');el.appendChild(d)}}
function renderList(){const el=$('#steps');const vis=visible();el.innerHTML=vis.map(s=>{const sm=summary(s);const k=isErr(s)?'err':s.kind;return `<div class="step ${k}${s.i===sel?' sel':''}${s.sidechain?' side':''}" data-i="${s.i}"><div class="dot"></div><div><div class="k">${s.kind==='tool'?'<span class="tn">'+esc(s.tool)+'</span>':esc(s.kind)}${s.diff?' <span title="changes a file">±</span>':''}${isErr(s)?' <span class="err">error</span>':''}</div><div class="s${sm.mono?' mono':''}">${esc(sm.t)}</div></div><div class="t">${rel(s.t)}</div></div>`}).join('');$('#pos').textContent=(sel>=0?('#'+sel+' / '+S.steps.length):S.steps.length+' steps')+(vis.length!==S.steps.length?' · '+vis.length+' shown':'')}
function diffHtml(d){return '<div class="diff">'+d.split('\n').map(l=>{let c='';if(l.startsWith('+++')||l.startsWith('---'))c='hd';else if(l.startsWith('@@'))c='h';else if(l.startsWith('+'))c='a';else if(l.startsWith('-'))c='d';return `<span class="ln ${c}">${esc(l)||' '}</span>`}).join('')+'</div>'}
function renderDetail(){const el=$('#detail');if(sel<0){return}const s=S.steps[sel];let h=`<h2><span class="badge">${esc(s.kind)}</span>${s.tool?'<span>'+esc(s.tool)+'</span>':''}${isErr(s)?'<span class="badge" style="color:var(--err);border-color:var(--err)">error</span>':''}${s.sidechain?'<span class="badge" title="ran inside a sub-agent">sub-agent</span>':''}</h2>`;
h+=`<div class="meta"><span>#${s.i}</span><span>${esc(rel(s.t))}</span>${s.duration_ms!=null?'<span>'+(s.duration_ms/1000).toFixed(1)+'s</span>':''}${s.model?'<span>'+esc(s.model)+'</span>':''}<span>${esc(new Date(s.t).toLocaleTimeString())}</span></div>`;
if(s.kind!=='tool'){h+=`<div class="prose ${esc(s.kind)}">${esc(s.text)}</div>`}
else{const i=s.input||{};const fp=i.file_path||i.path||i.notebook_path;if(fp)h+=`<div class="fp">${esc(fp)}</div>`;
 if(s.diff){h+='<div class="lbl">diff</div>'+diffHtml(s.diff)}
 const shown={...i};if(s.diff){delete shown.old_string;delete shown.new_string;delete shown.content;delete shown.patch;delete shown.edits}
 const cmd=shown.command||shown.cmd;if(cmd){h+='<div class="lbl">command</div><pre>'+esc(Array.isArray(cmd)?cmd.join(' '):cmd)+'</pre>';delete shown.command;delete shown.cmd;delete shown.description}
 if(shown.prompt&&typeof shown.prompt==='string'){h+='<div class="lbl">prompt</div><div class="prose">'+esc(shown.prompt)+'</div>';delete shown.prompt}
 const rest=Object.keys(shown).filter(k=>shown[k]!==undefined&&shown[k]!==''&&!(k==='replace_all'&&shown[k]===false)&&!(fp&&(k==='file_path'||k==='path'||k==='notebook_path')));
 if(rest.length)h+='<div class="lbl">input</div><pre>'+esc(JSON.stringify(Object.fromEntries(rest.map(k=>[k,shown[k]])),null,2))+'</pre>';
 h+='<div class="lbl">'+(s.error?'<span class="err">result (error)</span>':'result')+'</div><pre'+(s.error?' class="err"':'')+'>'+esc(s.output||'(no output recorded)')+'</pre>'}
el.innerHTML=h;el.scrollTop=0}
function renderFiles(){const el=$('#files');const files=S.files||{};const rows=Object.entries(files).sort((a,b)=>{const w=x=>(x.edit||0)+(x.write||0)+(x.create||0)+(x.delete||0);return (w(b[1])-w(a[1]))||(a[0]<b[0]?-1:1)});
el.innerHTML=`<table><tr><td style="color:var(--mute)">${rows.length} files touched · ${(S.blast_radius||[]).length} changed${fileFilter?' · filtering: '+esc(fileFilter)+' <span class="chip on" id="clearf">clear</span>':''}</td><td></td></tr>`+rows.map(([p,ops])=>`<tr data-p="${esc(p)}"><td>${esc(p)}</td><td>${Object.entries(ops).map(([o,n])=>`<span class="op ${o}">${o}×${n}</span>`).join(' ')}</td></tr>`).join('')+'</table>'}
function select(i,scroll=true){sel=Math.max(0,Math.min(S.steps.length-1,i));try{history.replaceState(null,'','#'+sel+($('#files').classList.contains('on')?',files':''))}catch(e){}renderList();renderDetail();renderStrip();if(scroll){const e=$('.step.sel');if(e)e.scrollIntoView({block:'nearest'})}if(window.innerWidth<=900)$('#right').classList.add('show')}
function stepNext(dir){const vis=visible();if(!vis.length)return;let idx=vis.findIndex(s=>s.i===sel);idx=Math.max(0,Math.min(vis.length-1,idx+dir));if(idx<0)idx=0;select(vis[idx].i)}
function play(){playing=!playing;$('#play').textContent=playing?'❚❚ pause':'▶ play';if(playing)tick();else clearTimeout(timer)}
function tick(){if(!playing)return;const vis=visible();let idx=vis.findIndex(s=>s.i===sel);if(idx>=vis.length-1){playing=false;$('#play').textContent='▶ play';return}const cur=vis[idx],nxt=vis[idx+1];select(nxt.i);const gap=cur?Math.min(4000,Math.max(250,Date.parse(nxt.t)-Date.parse(cur.t))):400;timer=setTimeout(tick,gap/speeds[speedIdx])}
// events
$('#steps').addEventListener('click',e=>{const el=e.target.closest('.step');if(el)select(+el.dataset.i,false)});
$('#strip').addEventListener('click',e=>{const el=e.target.closest('.seg');if(el)select(+el.dataset.i)});
$('#files').addEventListener('click',e=>{if(e.target.id==='clearf'){fileFilter=null;renderFiles();renderList();return}const tr=e.target.closest('tr[data-p]');if(tr){fileFilter=tr.dataset.p;renderFiles();renderList()}});
document.querySelectorAll('.chip[data-k]').forEach(c=>c.addEventListener('click',()=>{const k=c.dataset.k;filt[k]=filt[k]?0:1;c.classList.toggle('on',!!filt[k]);renderList()}));
$('#q').addEventListener('input',e=>{q=e.target.value.toLowerCase();renderList()});
$('#play').addEventListener('click',play);$('#speed').addEventListener('click',()=>{speedIdx=(speedIdx+1)%speeds.length;$('#speed').textContent=speeds[speedIdx]+'×'});
$('#fbtn').addEventListener('click',()=>{$('#files').classList.toggle('on');renderFiles()});
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'){if(e.key==='Escape')e.target.blur();return}if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();stepNext(1)}else if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();stepNext(-1)}else if(e.key===' '){e.preventDefault();play()}else if(e.key==='f'){$('#fbtn').click()}else if(e.key==='/'){e.preventDefault();$('#q').focus()}else if(e.key==='Escape'){$('#right').classList.remove('show')}});
const h=(location.hash||'').slice(1).split(',');if(h.includes('files'))$('#files').classList.add('on');renderStrip();renderList();renderFiles();if(S.steps.length)select(parseInt(h[0])||0);
})();
</script>
<div style="display:none">Recorded with agentcast __VERSION__ — https://github.com/GreenAiSolution/agentcast</div>
</body></html>
"""
TEMPLATE = TEMPLATE.replace("__VERSION__", __version__)
