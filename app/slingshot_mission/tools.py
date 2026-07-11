"""
SLINGSHOT tool layer — tools.py
===============================
The "layer of tools" the mission-control agents call. IMPORTANT: docstrings in this
file are instructions to Gemini (when/how to call each tool), not human docs.

Every tool returns:
  { 'status': 'success'|'error', ...domain fields,
    'render_command': <cmd> | [<cmd>, ...] }
where each <cmd> is {'layer': ..., 'action'/fields...} consumed by the frontend
(js/app.js dispatch → js/scene.js + js/panels.js). Tools may return a LIST of commands
to drive several HUD layers at once.

Layers: scene (3D), threat (assessment card), agent, log, ticker, media, alert, defcon,
status. This tool layer is what makes the multi-agent reasoning VISIBLE on the console.

Data + ML + media are delegated to sibling modules (data.py, classifier.py, media.py),
imported lazily so importing tools.py never hard-fails if an optional dep is missing.
"""
from __future__ import annotations
import datetime
import logging

log = logging.getLogger("slingshot.tools")

# --------------------------------------------------------------- session state
_SESSION_LOG: list[dict] = []
_current_neo: dict | None = None
_deflected: bool = False


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _fmt_neo(neo: dict) -> dict:
    """Human-readable telemetry strings for the threat card."""
    dmin, dmax = neo.get("est_diameter_min", 0), neo.get("est_diameter_max", 0)
    return {
        "name": neo.get("name", "unknown"),
        "diameter": f"{dmin:.2f} – {dmax:.2f} km",
        "velocity": f"{neo.get('relative_velocity', 0):.1f} km/s",
        "miss": f"{neo.get('miss_distance', 0):,.0f} km",
    }


# =============================================================== SENTRY tool ==
def track_asteroid(source: str = "cached") -> dict:
    """
    Use this FIRST when a new object appears or the operator says "scan", "track",
    "what's incoming", "pull an asteroid". It acquires a near-Earth object from the
    NASA feed and puts it on the 3D scene with initial telemetry.

    source — "live" to pull a real current NEO from NASA NeoWs, or "cached" (default)
             to use the bundled demo object. Use "cached" unless the operator asks for
             a live/real asteroid.
    """
    global _current_neo, _deflected
    log.info("call track_asteroid source=%s", source)
    try:
        from . import data
        neo = data.get_live_neo() if source == "live" else data.get_cached_neo()
    except Exception as exc:  # never fail the demo
        log.warning("track_asteroid data error: %s", exc)
        neo = {"id": "demo", "name": "(2026 PDC)", "est_diameter_min": 0.34,
               "est_diameter_max": 0.76, "relative_velocity": 19.4,
               "miss_distance": 71900, "absolute_magnitude": 21.3, "hazardous": True}
    _current_neo, _deflected = neo, False
    f = _fmt_neo(neo)
    _SESSION_LOG.append({"type": "detect", "note": f["name"], "timestamp": _now()})
    return {
        "status": "success", "neo": {k: neo.get(k) for k in
            ("name", "est_diameter_max", "relative_velocity", "miss_distance", "absolute_magnitude")},
        "render_command": [
            {"layer": "agent", "id": "SENTRY"},
            {"layer": "alert", "big": "OBJECT DETECTED", "sub": "Unclassified NEO on Earth-approach vector"},
            {"layer": "scene", "action": "spawn_asteroid", "threat": 0.85},
            {"layer": "scene", "action": "focus_threat"},
            {"layer": "threat", **f},
            {"layer": "defcon", "level": "warn"},
            {"layer": "log", "text": f"SENTRY acquired {f['name']} on approach vector"},
        ],
    }


# ================================================================= GNC tool ===
def plot_trajectory() -> dict:
    """
    Use this after an object is acquired to compute and display its approach
    trajectory. Call when the operator says "plot it", "show the trajectory",
    "where's it going".
    """
    log.info("call plot_trajectory")
    if not _current_neo:
        return {"status": "error", "message": "No object acquired yet. Call track_asteroid first."}
    return {
        "status": "success",
        "render_command": [
            {"layer": "agent", "id": "GNC"},
            {"layer": "scene", "action": "focus_threat"},
            {"layer": "log", "text": "GNC plotted approach trajectory from orbital elements"},
            {"layer": "ticker", "text": "GNC: Trajectory locked. Intercept window open."},
        ],
    }


# ============================================================== ASSESS tool ===
def classify_hazard() -> dict:
    """
    Use this to run the hazard-classification model on the acquired object and show
    the verdict (Torino score, hazardous or not, impact probability). Call when the
    operator says "assess", "is it dangerous", "classify", "run the model".
    """
    global _current_neo
    log.info("call classify_hazard")
    if not _current_neo:
        return {"status": "error", "message": "No object acquired yet. Call track_asteroid first."}
    try:
        from . import classifier
        result = classifier.classify_neo(_current_neo)
    except Exception as exc:
        log.warning("classify_hazard error: %s", exc)
        result = {"hazardous": True, "torino": 7, "impact_prob": "1 : 2,700",
                  "reason": "Large diameter and close miss distance.", "confidence": 0.9}
    haz = bool(result.get("hazardous"))
    torino = int(result.get("torino", 0))
    cmds = [
        {"layer": "agent", "id": "ASSESS"},
        {"layer": "threat", "torino": torino, "hazardous": haz, "prob": result.get("impact_prob", "—")},
        {"layer": "scene", "action": "set_threat", "value": min(1.0, torino / 10)},
        {"layer": "defcon", "level": "crit" if haz else "nominal"},
        {"layer": "log", "text": f"ASSESS: {'POTENTIALLY HAZARDOUS' if haz else 'Not hazardous'} · Torino {torino}"},
    ]
    if haz:
        cmds.append({"layer": "alert", "big": "POTENTIALLY HAZARDOUS",
                     "sub": f"Torino {torino} · {result.get('reason', '')}"})
    return {"status": "success", "classification": result, "render_command": cmds}


# ============================================================== INTEL tools ===
def generate_briefing() -> dict:
    """
    Use this to generate a visual threat-briefing card for the
    acquired object. Call when the operator says "brief me", "make the card",
    "show intel".
    """
    log.info("call generate_briefing")
    neo = _current_neo or {"id": "demo", "name": "(2026 PDC)"}
    try:
        from . import media
        m = media.generate_briefing_image(neo)
    except Exception as exc:
        log.warning("generate_briefing error: %s", exc)
        m = {"kind": "image", "src": "/static/assets/fallback/briefing.svg",
             "caption": "Threat briefing"}
    return {
        "status": "success",
        "render_command": [
            {"layer": "agent", "id": "INTEL"},
            {"layer": "media", **m},
            {"layer": "log", "text": "INTEL rendered threat briefing"},
        ],
    }


def generate_impact_sim(deflected: bool = False) -> dict:
    """
    Use this to generate a short impact/deflection simulation video (Omni Flash).
    deflected — True to show the successful kinetic-impactor deflection; False for the
    un-mitigated approach. Call when the operator says "show the sim", "simulate the
    impact", "show the deflection".
    """
    log.info("call generate_impact_sim deflected=%s", deflected)
    neo = _current_neo or {"id": "demo", "name": "(2026 PDC)"}
    try:
        from . import media
        m = media.generate_impact_video(neo, deflected=deflected)
    except Exception as exc:
        log.warning("generate_impact_sim error: %s", exc)
        m = {"kind": "image", "src": "/static/assets/fallback/impact.svg", "caption": "Impact simulation"}
    return {
        "status": "success",
        "render_command": [
            {"layer": "agent", "id": "INTEL"},
            {"layer": "media", **m},
            {"layer": "log", "text": f"INTEL rendered {'deflection' if deflected else 'impact'} simulation"},
        ],
    }


# ================================================================ FIDO tool ===
def deflect_asteroid() -> dict:
    """
    Use this to execute the kinetic-impactor deflection (DART-style) once the operator
    gives the GO. Call when the operator says "deflect", "fire the impactor", "GO for
    intercept", "execute". This bends the trajectory to a safe miss and neutralizes
    the threat.
    """
    global _deflected
    log.info("call deflect_asteroid")
    if not _current_neo:
        return {"status": "error", "message": "No object acquired to deflect."}
    _deflected = True
    _SESSION_LOG.append({"type": "deflect", "note": "kinetic impactor", "timestamp": _now()})
    return {
        "status": "success",
        "render_command": [
            {"layer": "agent", "id": "FIDO"},
            {"layer": "scene", "action": "deflect"},
            {"layer": "threat", "torino": 0, "hazardous": False, "prob": "< 1 : 10⁶"},
            {"layer": "defcon", "level": "nominal"},
            {"layer": "alert", "big": "THREAT NEUTRALIZED", "sub": "Orbit shifted — Earth clears by a safe margin"},
            {"layer": "log", "text": "DEFLECTION CONFIRMED · orbital period changed −32 min (cf. DART 2022)"},
        ],
    }


# ============================================================= shared tools ===
def set_mission_status(level: str) -> dict:
    """
    Use this to set the top-bar mission status. level — "nominal", "elevated", or
    "threat". Call "nominal" at the start and after a threat is resolved.
    """
    log.info("call set_mission_status level=%s", level)
    lvl = {"nominal": "nominal", "elevated": "warn", "threat": "crit"}.get(level.lower().strip(), "nominal")
    return {"status": "success", "render_command": {"layer": "defcon", "level": lvl}}


def log_event(text: str) -> dict:
    """Use this to add a line to the flight log. text — a short mission-log note."""
    log.info("call log_event text=%s", text)
    _SESSION_LOG.append({"type": "note", "note": text, "timestamp": _now()})
    return {"status": "success", "render_command": {"layer": "log", "text": text}}


def reset_console() -> dict:
    """Use this to clear the scene and start a fresh scenario. Call when the operator
    says "reset", "clear", "start over"."""
    global _current_neo, _deflected
    log.info("call reset_console")
    _current_neo, _deflected = None, False
    return {"status": "success", "render_command": [
        {"layer": "scene", "action": "reset"},
        {"layer": "defcon", "level": "nominal"},
        {"layer": "threat", "torino": 0, "hazardous": False},
        {"layer": "log", "text": "Console reset — standing by."},
    ]}


# ------- server-side helper (NOT an agent tool) — used by main.py on turnComplete
def log_ai_interaction(flight_said: str, capcom_said: str) -> dict | None:
    """Record one voice exchange for the transparency log. Called by main.py."""
    flight_said = (flight_said or "").strip()
    capcom_said = (capcom_said or "").strip()
    if not flight_said and not capcom_said:
        return None
    return {"flight": flight_said, "capcom": capcom_said, "timestamp": _now()}
