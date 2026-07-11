/*
 * panels.js — SLINGSHOT HUD rendering (mission-control overlay)
 * =============================================================================
 * WHAT THIS FILE IS ABOUT
 * Pure view layer. Given plain data it paints the glassmorphic panels over the 3D
 * scene: the mission-control agent roster (who's active), the animated threat
 * assessment card (Torino ring + telemetry count-ups), the flight log, the comms
 * ticker, the generated-intel frame (NB2/Omni output), the full-screen hazard
 * alert, and the top status bar. GSAP animates numbers and transitions so the
 * console feels alive. No network, no model calls here — app.js calls these.
 *
 * The AGENTS roster is the multi-agent "mission control room"; app.js / the backend
 * light up whichever agent is currently working via setActiveAgent().
 */
import gsap from 'gsap';

const $ = (id) => document.getElementById(id);

// Minimal monoline SVG icons (stroke = currentColor) — mission-grade, not emoji.
const _svg = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICON = {
  CAPCOM: _svg('<circle cx="12" cy="12" r="2.2"/><path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 7.5a6.4 6.4 0 0 1 0 9M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>'),
  SENTRY: _svg('<circle cx="12" cy="12" r="8"/><path d="M12 12l6-3.5"/><path d="M12 4v1.5M12 18.5V20"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>'),
  GNC:    _svg('<circle cx="12" cy="12" r="7"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>'),
  ASSESS: _svg('<path d="M3 17l4-6 3 3 4-8 4 6 3-4"/><path d="M3 21h18" opacity=".5"/>'),
  FIDO:   _svg('<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.3"/><path d="M12 1.5V5M22.5 12H19"/>'),
  INTEL:  _svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-4 4 3 3-2 6 4"/><circle cx="8.5" cy="9.5" r="1.4"/>'),
};
// The mission-control room. IDs match the backend agent names (author field).
export const AGENTS = [
  { id:'CAPCOM', icon:ICON.CAPCOM, label:'Commander interface · routes the room' },
  { id:'SENTRY', icon:ICON.SENTRY, label:'Detection & tracking · NeoWs feed' },
  { id:'GNC',    icon:ICON.GNC,    label:'Guidance, Nav & Control · trajectory' },
  { id:'ASSESS', icon:ICON.ASSESS, label:'Hazard classification · ML on NEO data' },
  { id:'FIDO',   icon:ICON.FIDO,   label:'Flight dynamics · deflection burn' },
  { id:'INTEL',  icon:ICON.INTEL,  label:'Visual intelligence · briefing & sim' },
];

const Panels = {
  // ---- agent roster -------------------------------------------------------
  initAgents(){
    $('agent-list').innerHTML = AGENTS.map(a => `
      <div class="agent" data-id="${a.id}">
        <div class="ic">${a.icon}</div>
        <div class="meta"><div class="nm">${a.id}</div><div class="rl">${a.label}</div></div>
        <div class="st">standby</div>
      </div>`).join('');
  },
  setActiveAgent(id){
    document.querySelectorAll('.agent').forEach(el => {
      const on = el.dataset.id === id;
      el.classList.toggle('active', on);
      el.querySelector('.st').textContent = on ? 'active' : 'standby';
    });
    if(id){ const a = AGENTS.find(x=>x.id===id); this.dock(id, a?`${a.label}`:''); }
  },

  // ---- flight log ---------------------------------------------------------
  log(text, kind='ev'){
    const body = $('log-body');
    const row = document.createElement('div');
    row.className = 'ev';
    const t = new Date().toLocaleTimeString('en-GB',{hour12:false});
    row.innerHTML = `<span class="t">${t}</span><span class="b">›</span><span>${text}</span>`;
    body.appendChild(row); body.scrollTop = body.scrollHeight;
    gsap.from(row,{opacity:0,x:-8,duration:.35});
    while(body.children.length>60) body.removeChild(body.firstChild);
  },

  ticker(text){
    const el = $('ticker'); el.textContent = text;
    gsap.fromTo(el,{opacity:0},{opacity:1,duration:.4});
    clearTimeout(el._t); el._t = setTimeout(()=>gsap.to(el,{opacity:0,duration:.6}), 4200);
  },

  dock(who, line){ $('dock-who').textContent = who; if(line!==undefined) $('dock-line').textContent = line; },
  status(text, color){ const s=$('status'); s.textContent = text; if(color) s.style.color=color; },
  neoCount(n){ this._count($('neo-count'), n, {int:true}); },

  // ---- threat assessment card --------------------------------------------
  threat(d){
    if(d.name) $('th-name').textContent = d.name;
    if(d.torino!=null){
      const ring=$('th-ring');
      gsap.to(ring,{'--v':d.torino,duration:1.1,onUpdate:()=>{
        const v=gsap.getProperty(ring,'--v'); ring.textContent=Math.round(v);
      }});
      $('th-class').textContent = d.torinoLabel || torinoLabel(d.torino);
    }
    if(d.diameter!=null) $('th-dia').textContent = d.diameter;
    if(d.velocity!=null) $('th-vel').textContent = d.velocity;
    if(d.miss!=null) $('th-miss').textContent = d.miss;
    if(d.prob!=null){ const e=$('th-prob'); e.textContent=d.prob; e.className='val hot'; }
    if(d.hazardous!=null){
      const e=$('th-haz'); e.textContent = d.hazardous ? 'POTENTIALLY HAZARDOUS' : 'Not hazardous';
      e.className = 'val ' + (d.hazardous ? 'hot' : 'ok');
    }
  },

  // ---- generated intel (NB2 image / Omni video / placeholder) -------------
  media({kind, src, caption}){
    const frame=$('media-frame'), cap=$('media-cap');
    frame.querySelectorAll('img,video,.ph,.media-ov').forEach(n=>n.remove());
    if(kind==='image'){
      const img=new Image(); img.src=src; frame.appendChild(img); gsap.from(img,{opacity:0,scale:1.06,duration:.6});
      // crisp, accurate data overlay (AI image text isn't reliable) — read live values from the threat panel
      const g=(id)=>($(id)?.textContent||'—').trim();
      const name=g('th-name'), dia=g('th-dia'), vel=g('th-vel'), tor=g('th-ring');
      if(name && name!=='— no active target —'){
        const ov=document.createElement('div'); ov.className='media-ov';
        ov.innerHTML=`<div class="mo-t">THREAT BRIEFING · ${name}</div>`+
          `<div class="mo-g"><span>DIA <b>${dia}</b></span><span>VEL <b>${vel}</b></span><span>TORINO <b>${tor}</b></span></div>`;
        frame.appendChild(ov); gsap.from(ov,{opacity:0,y:8,duration:.5,delay:.2});
      }
    }
    else if(kind==='video'){ const v=document.createElement('video'); v.src=src; v.autoplay=v.loop=v.muted=v.playsInline=true; frame.appendChild(v); gsap.from(v,{opacity:0,duration:.6}); }
    else { const ph=document.createElement('span'); ph.className='ph'; ph.textContent=src||'standby'; frame.appendChild(ph); }
    if(caption) cap.textContent = caption;
  },

  // ---- top status / defcon ------------------------------------------------
  defcon(level){ // 'nominal' | 'warn' | 'crit'
    const el=$('defcon'); el.className='';
    if(level==='warn'){ el.classList.add('warn'); el.textContent='STATUS · ELEVATED'; }
    else if(level==='crit'){ el.classList.add('crit'); el.textContent='STATUS · IMPACT THREAT'; }
    else el.textContent='STATUS · NOMINAL';
  },

  // ---- full-screen hazard alert ------------------------------------------
  alert(big, sub, show=true){
    const a=$('alert');
    if(show){ $('alert-big').textContent=big; $('alert-sub').textContent=sub||''; a.classList.add('show');
      clearTimeout(a._t); a._t=setTimeout(()=>a.classList.remove('show'), 2600); }
    else a.classList.remove('show');
  },

  // ---- mission clock ------------------------------------------------------
  startClock(){
    const el=$('clock'); const t0=Date.now();
    clearInterval(this._clk); this._clk=setInterval(()=>{
      const s=Math.floor((Date.now()-t0)/1000);
      const hh=String(Math.floor(s/3600)).padStart(2,'0');
      const mm=String(Math.floor(s/60)%60).padStart(2,'0');
      const ss=String(s%60).padStart(2,'0');
      el.textContent=`T+${hh}:${mm}:${ss}`;
    },1000);
  },

  // ---- helper: animated count-up -----------------------------------------
  _count(el, to, {int=false}={}){
    const obj={v: parseFloat(el.textContent)||0};
    gsap.to(obj,{v:to,duration:1,ease:'power2.out',onUpdate:()=>{ el.textContent = int?Math.round(obj.v):obj.v.toFixed(1); }});
  },
};

// Torino scale 0-10 label bands (CNEOS)
function torinoLabel(v){
  if(v<=0) return 'No hazard (0)';
  if(v<=1) return 'Normal (1)';
  if(v<=4) return 'Meriting attention';
  if(v<=7) return 'Threatening';
  return 'Certain collision';
}

export default Panels;
