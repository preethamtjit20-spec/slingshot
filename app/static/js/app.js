/*
 * app.js — SLINGSHOT console orchestration
 * =============================================================================
 * WHAT THIS FILE IS ABOUT
 * Boots the scene + HUD, then runs in one of two modes:
 *
 *  • MOCK MODE (default, or ?mock=1, or when no backend answers) — a fully scripted
 *    "planetary defense" mission plays out on its own so the visuals can be shown and
 *    rehearsed with ZERO dependencies. Every number is grounded in the real research
 *    (NeoWs-style features, Torino scale, DART's ~32-min deflection). This is the
 *    reliability net for the 500-person, one-shot judging.
 *
 *  • LIVE MODE (?live=1) — opens the WebSocket to the ADK backend, streams mic audio +
 *    video frames up, and dispatches each tool's render_command to Scene + Panels.
 *    The live agents drive exactly the same visual API the mock scenario uses.
 *
 * RENDER_COMMAND CONTRACT (backend tools must emit these; see dispatch() below):
 *   {layer:'scene',  action:'spawn_asteroid'|'set_threat'|'focus_threat'|'focus_earth'|'deflect'|'impact'|'reset', ...}
 *   {layer:'threat', ...fields}            {layer:'agent',  id}
 *   {layer:'log',    text}                 {layer:'ticker', text}
 *   {layer:'media',  kind, src, caption}   {layer:'alert',  big, sub}
 *   {layer:'defcon', level}                {layer:'status', neo_count}
 */
import Scene from './scene.js';
import Panels from './panels.js';
import AudioFX from './audio-fx.js';

const params = new URLSearchParams(location.search);
let live = params.has('live');

// narrate + caption a line (speaks aloud only in the no-mic watch mode)
const say = (text, who = 'CAPCOM') => { Panels.dock(who, text); Panels.ticker(text); if (!live) AudioFX.speak(text); };

// ---- cinematic drama helpers -------------------------------------------------
const screenShake = (ms = 700) => {
  ['scene', 'hud'].forEach(id => { const el = document.getElementById(id); if (!el) return;
    el.classList.remove('shake'); void el.offsetWidth; el.classList.add('shake'); setTimeout(() => el.classList.remove('shake'), ms); });
};
const flashScreen = () => { const f = document.getElementById('flash'); if (!f) return;
  f.style.transition = 'none'; f.style.opacity = '0.9';
  requestAnimationFrame(() => { f.style.transition = 'opacity .7s ease-out'; f.style.opacity = '0'; }); };
const redAlert = (on) => { const r = document.getElementById('redalert'); if (r) r.classList.toggle('on', !!on); };
const bigHit = () => { AudioFX.impact(); AudioFX.rumble && AudioFX.rumble(); flashScreen(); screenShake(); Scene.shake && Scene.shake(0.7); };

// ---- live mission telemetry (evolving readouts for a real-ops feel) ----------
let telemTimer = null;
function startTelemetry(){
  if (telemTimer) return;
  const el = document.getElementById('telem'); if (!el) return;
  let cpa = 21 * 60 + 40;                                   // ~T-21:40 to closest approach
  let i = 0;
  const tick = () => {
    cpa = Math.max(0, cpa - Math.round(2 + Math.random() * 2));
    const mm = String(Math.floor(cpa / 60)).padStart(2, '0'), ss = String(cpa % 60).padStart(2, '0');
    const r = [
      `TRACK CONF ${(94 + Math.random() * 4).toFixed(0)}%`,
      `Δv ${(3.0 + Math.random() * 0.9).toFixed(1)} mm/s`,
      `CPA T-${mm}:${ss}`,
      `ISTRAC BENGALURU · LOCK`,
      `LINK ${(95 + Math.random() * 4).toFixed(0)}%`,
      `NETRA · TRACKING`,
      `SIGNAL ${(-118 - Math.random() * 6).toFixed(0)} dBm`,
    ];
    el.textContent = r[i % r.length]; i++;
  };
  tick(); telemTimer = setInterval(tick, 2200);
}

// ---------------------------------------------------------------------- boot
window.addEventListener('DOMContentLoaded', () => {
  Scene.init(document.getElementById('scene'));
  Panels.initAgents();
  Panels.startClock();
  Panels.neoCount(2473);              // ~known PHAs (CNEOS)
  Panels.setActiveAgent('CAPCOM');
  Panels.status('● STANDBY', 'var(--ink-dim)');
  setTimeout(() => document.getElementById('boot')?.classList.add('hide'), 1900);  // loader → briefing

  const enter = (goLive) => {
    AudioFX.start();                             // boot tone + ambient (needs a user gesture)
    AudioFX.warp && AudioFX.warp();              // hyperspace whoosh
    const b = document.getElementById('briefing');
    b.classList.add('warp');                     // zoom + fade the briefing (dragged into space)
    document.getElementById('tunnel')?.classList.add('go');   // tunnel warp overlay
    Scene.warp && Scene.warp();                  // camera rush + star-streak
    flashScreen();
    startTelemetry();
    setTimeout(() => {
      b.classList.add('hide');
      if (goLive) { live = true; toggleLive(); } else { runDemo(); }
    }, 1050);
  };
  document.getElementById('btn-live').addEventListener('click', () => enter(true));
  document.getElementById('btn-watch').addEventListener('click', () => enter(false));

  const mic = document.getElementById('mic');
  mic.addEventListener('click', () => { if (live) toggleLive(); else if (!demoRunning) runDemo(); });
});

// ============================================================ MOCK SCENARIO ==
// A grounded, cinematic run. Times are ms offsets; each beat drives Scene + HUD.
let demoRunning = false;
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const DEMO_NEO = { name:'(2026 PDC)', est_diameter_min:0.34, est_diameter_max:0.76,
  relative_velocity:19.4, miss_distance:71900, absolute_magnitude:21.3, hazardous:true };

async function runDemo(){
  if (demoRunning) return;
  demoRunning = true;
  const mic = document.getElementById('mic'); mic.classList.add('live');
  Panels.status('● SCENARIO LIVE', 'var(--green)');

  // ── STORYTELLING INTRO (video / first-time viewers) ──
  say("This is SLINGSHOT — real-time AI mission control for planetary defense.", 'MISSION BRIEF');
  Panels.log('MISSION BRIEF · SLINGSHOT online');
  await wait(4800);
  say("Thousands of asteroids pass near Earth, and we've deflected exactly one. SLINGSHOT is a room of AI agents that detect, classify, and deflect an incoming threat — live, and by voice.", 'MISSION BRIEF');
  await wait(9800);
  say("Let's run an intercept.", 'MISSION BRIEF');
  await wait(2800);

  // CAPCOM opens
  Panels.setActiveAgent('CAPCOM');
  say("Hey Flight, CAPCOM here. All systems green — let's see what's out there.", 'CAPCOM');
  Panels.log('CAPCOM online · mission status nominal');
  await wait(2800);

  // SENTRY — detect (fetching real data feed)
  Panels.setActiveAgent('SENTRY'); AudioFX.handoff();
  Panels.log('SENTRY → querying NASA NeoWs close-approach feed…');
  await wait(1500);
  AudioFX.detect(); Panels.defcon('warn');
  Panels.alert('OBJECT DETECTED', 'Unclassified NEO on Earth-approach vector');
  Scene.spawnAsteroid({ threat: 0.85 }); Scene.focusThreat();
  say("Got a contact — object 2026 PDC, inbound. Passing it to GNC.", 'SENTRY');
  Panels.log('SENTRY acquired (2026 PDC) from NeoWs · handing off');
  await wait(2600);

  // GNC — trajectory
  Panels.setActiveAgent('GNC'); AudioFX.handoff();
  Panels.threat({ name:'(2026 PDC)', diameter:'0.34 – 0.76 km', velocity:'19.4 km/s', miss:'71,900 km' });
  say("Trajectory's locked in — we've got an intercept window.", 'GNC');
  Panels.log('GNC plotted approach from orbital elements');
  await wait(2400);

  // ASSESS — ML hazard classification
  Panels.setActiveAgent('ASSESS'); AudioFX.handoff();
  Panels.log('ASSESS → running hazard model on size, velocity, miss distance…');
  AudioFX.riser(1.6);                                   // rising tension
  await wait(1600);
  AudioFX.classify();
  Panels.threat({ torino:7, hazardous:true, prob:'1 : 2,700' });
  Panels.defcon('crit'); Scene.setThreat(0.95); AudioFX.alert();
  Scene.punchIn(); redAlert(true);                      // dramatic push + red-alert vignette
  Panels.alert('POTENTIALLY HAZARDOUS', 'Torino 7 · impact corridor intersects Earth');
  say("Okay, this one's serious — potentially hazardous, Torino seven.", 'ASSESS');
  Panels.log('CLASSIFICATION: POTENTIALLY HAZARDOUS · Torino 7');
  await wait(2900);

  // INTEL — REAL Nano Banana 2 Lite generation
  Panels.setActiveAgent('INTEL'); AudioFX.handoff();
  say("Pulling up a visual briefing for you now.", 'INTEL');
  await generateBriefingLive(DEMO_NEO);
  await wait(1400);

  // FIDO — deflection
  Panels.setActiveAgent('FIDO'); AudioFX.handoff();
  say("I'd recommend a kinetic impactor. Your call, Flight.", 'CAPCOM');
  await wait(1800);
  Panels.log('▶ KINETIC IMPACTOR — GO for intercept');
  AudioFX.deflect(); Scene.deflect();
  await wait(520);
  bigHit();                                             // the impact: boom + flash + screen-shake
  await wait(1100);

  // resolution
  AudioFX.success(); redAlert(false);
  Panels.threat({ torino:0, hazardous:false, prob:'< 1 : 10⁶' });
  Panels.defcon('nominal');
  Panels.alert('THREAT NEUTRALIZED', 'Orbit shifted — Earth clears by a safe margin');
  Panels.log('DEFLECTION CONFIRMED · orbital period changed −32 min (cf. DART 2022)');
  say("Deflection confirmed — Earth is clear. Beautiful work, everyone.", 'CAPCOM');
  Scene.focusEarth(); Panels.setActiveAgent('CAPCOM');
  await wait(2600);
  // closing thank-you card
  document.getElementById('closing')?.classList.add('show');
  say("That's SLINGSHOT — planetary defense, in real time, by voice. Huge thanks to Google DeepMind and Cerebral Valley.", 'CAPCOM');
  Panels.status('● SCENARIO COMPLETE — tap mic to replay', 'var(--cyan)');
  mic.classList.remove('live');
  await wait(800);
  demoRunning = false;
}

// Call the backend to generate a REAL threat-briefing image (NB2 Lite) and show it,
// with a live "generating…" spinner + timing. Falls back gracefully.
async function generateBriefingLive(neo){
  const frame = document.getElementById('media-frame');
  Panels.media({ kind:'placeholder', src:'Rendering intel…', caption:'Live visual intelligence' });
  frame.classList.add('gen');
  Panels.log('INTEL → rendering threat briefing…');
  const t0 = performance.now();
  try {
    const r = await fetch('/api/briefing', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(neo) });
    const d = await r.json();
    frame.classList.remove('gen');
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    Panels.media({ kind: d.kind || 'image', src: d.src, caption: `Threat briefing · rendered in ${secs}s` });
    Panels.log(`Threat briefing rendered in ${secs}s`);
  } catch (e) {
    frame.classList.remove('gen');
    Panels.media({ kind:'image', src:'/static/assets/fallback/briefing.svg', caption:'Threat briefing' });
    Panels.log('INTEL briefing — fallback card');
  }
}

// =============================================================== LIVE MODE ===
// Opens the ADK WebSocket, streams mic/video up, dispatches render_command down.
let ws = null, audioPlayerNode = null, recorderStop = null, videoTimer = null;

async function toggleLive(){
  if (ws) { stopLive(); return; }
  const mic = document.getElementById('mic'); mic.classList.add('live');
  Panels.status('● LINK OPEN', 'var(--green)');
  Panels.dock('CAPCOM', 'Link open — say: “Scan for an incoming asteroid, then assess it.”');
  Panels.log('Live link opening to Mission Control…');

  const uid = 'flight', sid = 'm' + Date.now();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${uid}/${sid}`);
  ws.onmessage = (e) => handleServerEvent(e.data);
  ws.onclose = () => stopLive();
  ws.onerror = () => { Panels.log('Link error — falling back to demo'); stopLive(); };

  // lazy-load the ADK audio streaming plumbing only when going live
  const [{ startAudioPlayerWorklet }, { startAudioRecorderWorklet }] = await Promise.all([
    import('./audio-player.js'), import('./audio-recorder.js'),
  ]).catch(() => [{}, {}]);
  try {
    if (startAudioPlayerWorklet) [audioPlayerNode] = await startAudioPlayerWorklet();
    if (startAudioRecorderWorklet) [, , recorderStop] = await startAudioRecorderWorklet(pcm => {
      if (ws && ws.readyState === 1) ws.send(pcm);
    });
    startVideo();
  } catch (err) { Panels.log('Media init failed: ' + err.message); }
}

function stopLive(){
  if (ws) { try { ws.close(); } catch {} ws = null; }
  if (recorderStop) { try { recorderStop(); } catch {} recorderStop = null; }
  if (audioPlayerNode) { try { audioPlayerNode.disconnect(); } catch {} audioPlayerNode = null; }
  if (videoTimer) { clearInterval(videoTimer); videoTimer = null; }
  document.getElementById('mic').classList.remove('live');
  Panels.status('● OFFLINE', 'var(--ink-dim)');
}

function startVideo(){
  navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'environment' } }).then(stream => {
    const v = document.createElement('video'); v.srcObject = stream; v.play();
    const c = document.createElement('canvas'); c.width = 640; c.height = 480;
    videoTimer = setInterval(() => {
      if (!ws || ws.readyState !== 1) return;
      c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
      ws.send(JSON.stringify({ type: 'image_frame', data: c.toDataURL('image/jpeg', 0.6) }));
    }, 1000);
  }).catch(() => Panels.log('Camera unavailable — audio only'));
}

function handleServerEvent(raw){
  let ev; try { ev = JSON.parse(raw); } catch { return; }
  // transcript
  const out = ev.outputTranscription?.text || ev.output_transcription?.text;
  if (out) Panels.dock(ev.author || 'CAPCOM', out);
  // audio playback
  for (const part of ev.content?.parts || []) {
    const inl = part.inlineData || part.inline_data;
    if (inl && (inl.mimeType || inl.mime_type || '').startsWith('audio/pcm') && audioPlayerNode)
      audioPlayerNode.port.postMessage(b64ToArray(inl.data));
    const fr = part.functionResponse || part.function_response;
    const rc = fr?.response?.render_command;
    if (Array.isArray(rc)) rc.forEach(dispatch);      // tools may emit several commands
    else if (rc) dispatch(rc);
  }
  if (ev.author) Panels.setActiveAgent(ev.author);
}

// The single mapping from backend render_command → visual state.
function dispatch(cmd){
  switch (cmd.layer) {
    case 'scene':
      if (cmd.action === 'spawn_asteroid') { Scene.spawnAsteroid(cmd); AudioFX.detect(); }
      else if (cmd.action === 'set_threat') Scene.setThreat(cmd.value);
      else if (cmd.action === 'focus_threat') Scene.focusThreat();
      else if (cmd.action === 'focus_earth') Scene.focusEarth();
      else if (cmd.action === 'deflect') { Scene.deflect(); setTimeout(bigHit, 520); }
      else if (cmd.action === 'impact') { Scene.impact(); bigHit(); }
      else if (cmd.action === 'reset') { Scene.reset(); redAlert(false); }
      break;
    case 'threat': Panels.threat(cmd); break;
    case 'agent':  Panels.setActiveAgent(cmd.id); AudioFX.handoff(); break;
    case 'log':    Panels.log(cmd.text); break;
    case 'ticker': Panels.ticker(cmd.text); break;
    case 'media':  Panels.media(cmd); break;
    case 'alert':  Panels.alert(cmd.big, cmd.sub); AudioFX.alert(); break;
    case 'defcon': Panels.defcon(cmd.level);
      if (cmd.level === 'crit') { redAlert(true); Scene.punchIn(); }
      else if (cmd.level === 'nominal') redAlert(false);
      break;
    case 'status': if (cmd.neo_count != null) Panels.neoCount(cmd.neo_count); break;
  }
}

function b64ToArray(b64){ const s = atob(b64); const a = new Uint8Array(s.length); for (let i=0;i<s.length;i++) a[i]=s.charCodeAt(i); return a.buffer; }
