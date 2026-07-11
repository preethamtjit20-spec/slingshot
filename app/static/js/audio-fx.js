/*
 * audio-fx.js — SLINGSHOT procedural audio (Web Audio API + SpeechSynthesis)
 * =============================================================================
 * WHAT THIS FILE IS ABOUT
 * All demo audio, generated at runtime — NO external sound files (reliability on stage,
 * zero asset-licensing concerns). Provides:
 *   - a looping ambient mission-control soundscape (deep drone + slow pad + sonar pings)
 *   - a boot/loading tone
 *   - event SFX: detection alarm, agent handoff blip, classification tri-tone, deflection
 *     impact, and a success chord
 *   - speak(text): CAPCOM/room narration via the browser SpeechSynthesis voice
 *
 * Browsers require a user gesture before audio can start, so AudioFX.start() must be
 * called from a click/tap (the INITIATE button / mic). Everything is wrapped so it can
 * never throw into the app.
 */
let ctx = null, master = null, ambient = null, pingTimer = null, started = false;

function ac() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.6;
    master.connect(ctx.destination);
  }
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

// schedule a simple tone
function tone(freq, dur, { type = 'sine', gain = 0.15, when = 0, glideTo = null } = {}) {
  const c = ac(), t0 = c.currentTime + when;
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, t0);
  if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g).connect(master);
  o.start(t0); o.stop(t0 + dur + 0.05);
}

function noise(dur, { gain = 0.2, when = 0, cutoff = 1200 } = {}) {
  const c = ac(), t0 = c.currentTime + when;
  const n = c.createBufferSource();
  const buf = c.createBuffer(1, c.sampleRate * dur, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  n.buffer = buf;
  const f = c.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = cutoff;
  const g = c.createGain();
  g.gain.setValueAtTime(gain, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  n.connect(f).connect(g).connect(master);
  n.start(t0); n.stop(t0 + dur);
}

const AudioFX = {
  start() {
    if (started) return;
    try { ac(); started = true; this.boot(); this.startAmbient(); } catch (e) {}
  },

  // ---- ambient soundscape -------------------------------------------------
  startAmbient() {
    try {
      const c = ac();
      ambient = c.createGain(); ambient.gain.value = 0.0001; ambient.connect(master);
      // deep detuned drone
      const d1 = c.createOscillator(), d2 = c.createOscillator();
      d1.type = 'sine'; d1.frequency.value = 55;
      d2.type = 'sine'; d2.frequency.value = 55.4;
      const dg = c.createGain(); dg.gain.value = 0.12;
      d1.connect(dg); d2.connect(dg); dg.connect(ambient);
      // airy pad through a slow-moving lowpass
      const p1 = c.createOscillator(), p2 = c.createOscillator();
      p1.type = 'triangle'; p1.frequency.value = 110;
      p2.type = 'triangle'; p2.frequency.value = 164.81;
      const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 500;
      const lfo = c.createOscillator(), lfoG = c.createGain();
      lfo.frequency.value = 0.06; lfoG.gain.value = 300;
      lfo.connect(lfoG).connect(lp.frequency);
      const pg = c.createGain(); pg.gain.value = 0.05;
      p1.connect(lp); p2.connect(lp); lp.connect(pg).connect(ambient);
      [d1, d2, p1, p2, lfo].forEach(o => o.start());
      ambient.gain.exponentialRampToValueAtTime(0.5, c.currentTime + 3);
      ambient._nodes = [d1, d2, p1, p2, lfo];
      // periodic sonar ping
      pingTimer = setInterval(() => tone(880, 1.4, { type: 'sine', gain: 0.05, glideTo: 660 }), 8000);
    } catch (e) {}
  },
  stopAmbient() {
    try { if (pingTimer) clearInterval(pingTimer);
      if (ambient) { ambient.gain.exponentialRampToValueAtTime(0.0001, ac().currentTime + 1.2); } } catch (e) {}
  },

  // ---- one-shots ----------------------------------------------------------
  boot() { [261.6, 329.6, 392, 523.3].forEach((f, i) => tone(f, 0.5, { type: 'triangle', gain: 0.18, when: i * 0.12 })); },
  detect() { for (let i = 0; i < 3; i++) tone(880, 0.28, { type: 'sawtooth', gain: 0.16, when: i * 0.34, glideTo: 300 }); },
  handoff() { tone(620, 0.12, { type: 'square', gain: 0.08, glideTo: 880 }); },
  classify() { [440, 554, 659].forEach((f, i) => tone(f, 0.3, { type: 'sine', gain: 0.12, when: i * 0.14 })); },
  alert() { for (let i = 0; i < 4; i++) tone(i % 2 ? 620 : 330, 0.16, { type: 'square', gain: 0.12, when: i * 0.18 }); },
  deflect() { noise(0.5, { gain: 0.35, cutoff: 2200 }); [392, 523, 659, 784].forEach((f, i) => tone(f, 0.6, { type: 'triangle', gain: 0.16, when: 0.25 + i * 0.12 })); },
  success() { [523.3, 659.3, 784, 1046.5].forEach((f, i) => tone(f, 0.7, { type: 'sine', gain: 0.14, when: i * 0.16 })); },
  impact() {  // heavy low boom + debris
    noise(0.7, { gain: 0.5, cutoff: 900 });
    tone(120, 0.95, { type: 'sine', gain: 0.5, glideTo: 40 });
    tone(80, 1.1, { type: 'triangle', gain: 0.32, glideTo: 30 });
  },
  rumble(dur = 0.75) {  // low tremolo = the shaking/vibration
    try {
      const c = ac(), t0 = c.currentTime;
      const o = c.createOscillator(), g = c.createGain(), lfo = c.createOscillator(), lg = c.createGain();
      o.type = 'sine'; o.frequency.value = 46;
      lfo.type = 'square'; lfo.frequency.value = 24; lg.gain.value = 0.2;   // vibration modulation
      lfo.connect(lg).connect(g.gain);
      g.gain.setValueAtTime(0.3, t0); g.gain.setValueAtTime(0.3, t0 + dur - 0.1);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
      o.connect(g).connect(master);
      o.start(t0); lfo.start(t0); o.stop(t0 + dur); lfo.stop(t0 + dur);
      noise(dur, { gain: 0.16, cutoff: 480 });
    } catch (e) {}
  },
  riser(dur = 2.0) {  // rising tension sweep
    try {
      const c = ac(), t0 = c.currentTime;
      const o = c.createOscillator(), g = c.createGain(), f = c.createBiquadFilter();
      o.type = 'sawtooth'; o.frequency.setValueAtTime(160, t0); o.frequency.exponentialRampToValueAtTime(900, t0 + dur);
      f.type = 'bandpass'; f.frequency.setValueAtTime(300, t0); f.frequency.exponentialRampToValueAtTime(1400, t0 + dur); f.Q.value = 6;
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.11, t0 + dur * 0.8); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(f).connect(g).connect(master); o.start(t0); o.stop(t0 + dur + 0.1);
    } catch (e) {}
  },

  warp() { try {  // hyperspace whoosh
    noise(1.1, { gain: 0.4, cutoff: 5000 });
    tone(140, 1.1, { type: 'sawtooth', gain: 0.22, glideTo: 1400 });
    tone(70, 1.3, { type: 'sine', gain: 0.32, glideTo: 240 });
  } catch (e) {} },

  // ---- narration ----------------------------------------------------------
  speak(text, { rate = 0.98, pitch = 0.8 } = {}) {   // low pitch = male mission-control voice
    try {
      const s = window.speechSynthesis; if (!s) return;
      const u = new SpeechSynthesisUtterance(text);
      u.rate = rate; u.pitch = pitch; u.volume = 1;
      const voices = s.getVoices();
      const male =
           voices.find(v => /\bmale\b|david|daniel|mark|alex|rishi|fred|george|james|guy|arthur/i.test(v.name))
        || voices.find(v => /en(-|_)?(GB|US|IN|AU)/i.test(v.lang) && !/female|zira|susan|linda|hazel|catherine|samantha|karen|tessa|moira|fiona|veena|aria/i.test(v.name))
        || voices.find(v => /^en/i.test(v.lang));
      if (male) u.voice = male;
      s.speak(u);
    } catch (e) {}
  },
  cancelSpeech() { try { window.speechSynthesis?.cancel(); } catch (e) {} },
};

export default AudioFX;
