"""
media.py — SLINGSHOT GENERATED-MEDIA layer (Nano Banana 2 Lite + Omni Flash)
============================================================================

WHAT THIS MODULE IS ABOUT
-------------------------
This is the *generated media* layer for SLINGSHOT, the NASA planetary-defense
mission-control app. Given a NEO (near-Earth object) record it produces two
demo artifacts:

  * a THREAT BRIEFING card image  -> via NB2 Lite ("gemini-3.1-flash-lite-image")
  * a DEFLECTION SIM video        -> via Omni Flash ("gemini-omni-flash-preview")

DESIGN GOALS (in priority order)
--------------------------------
1. NEVER crash the app, and NEVER block the demo. Preview GenMedia models are
   slow and 503 often, so generation is *opt-in* and *off by default*. When it
   is off (or anything fails), we instantly return a hand-crafted local SVG
   fallback that the frontend can drop straight into an <img>.
2. Zero import cost. The google-genai SDK is imported *lazily* inside the
   functions, so `import media` works with no SDK, no network and no key.
3. The two model IDs above are the generative-media models this module calls.

FEATURE FLAG
------------
    SLINGSHOT_MEDIA=1   -> enable live generation (calls the preview models)
    (unset / "0")       -> disabled; functions return fallbacks immediately

AUTH (never hardcode keys)
--------------------------
The google-genai client picks auth up from the environment automatically:
    * AI Studio:  GOOGLE_API_KEY=<key>
    * Vertex AI:  GOOGLE_GENAI_USE_VERTEXAI=1  + GOOGLE_CLOUD_PROJECT / ADC
We only ever call genai.Client(); we read nothing secret ourselves.

PUBLIC INTERFACE
----------------
    generate_briefing_image(neo: dict) -> {"kind":"image","src":str,"caption":str}
    generate_impact_video(neo: dict, deflected: bool = True)
                                    -> {"kind":"video"|"image","src":str,"caption":str}

A NEO dict looks like:
    {"id","name","est_diameter_min","est_diameter_max","relative_velocity",
     "miss_distance","absolute_magnitude","hazardous"}
"""
from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger("slingshot.media")

# --- Generative-media model IDs ----------------------------------------------
NB2_LITE_MODEL = "gemini-3.1-flash-lite-image"      # fast image (<4s)
OMNI_FLASH_MODEL = "gemini-omni-flash-preview"      # conversational video

# --- Feature flag: OFF by default so the demo never blocks on preview latency -
MEDIA_ENABLED = os.getenv("SLINGSHOT_MEDIA", "0") == "1"

# --- Filesystem layout --------------------------------------------------------
# .../app/slingshot_mission/media.py  ->  .../app
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GEN_DIR = os.path.join(_APP_DIR, "static", "assets", "gen")
_FALLBACK_DIR = os.path.join(_APP_DIR, "static", "assets", "fallback")

# Web (URL) paths served by FastAPI's /static mount.
FALLBACK_BRIEFING_URL = "/static/assets/fallback/briefing.svg"
FALLBACK_IMPACT_URL = "/static/assets/fallback/impact.svg"

# Retry policy for flaky preview models.
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5  # seconds; exponential: base * 2**attempt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_id(neo: dict) -> str:
    """Return a filesystem-safe id token for a NEO (never empty)."""
    raw = str(neo.get("id") or neo.get("name") or "unknown")
    token = re.sub(r"[^A-Za-z0-9_-]", "_", raw).strip("_")
    return token or "unknown"


def _designation(neo: dict) -> str:
    """Human designation for prompts/captions."""
    return str(neo.get("name") or neo.get("id") or "Unknown NEO")


def _diameter_km(neo: dict) -> float:
    """Mean estimated diameter (km) from min/max, best-effort."""
    try:
        lo = float(neo.get("est_diameter_min") or 0.0)
        hi = float(neo.get("est_diameter_max") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if lo and hi:
        return (lo + hi) / 2.0
    return hi or lo


def _fnum(value, default: float = 0.0) -> float:
    """Coerce a value to float, tolerating None / bad strings."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_gen_dir() -> None:
    """Create the generated-assets output directory if needed."""
    os.makedirs(_GEN_DIR, exist_ok=True)


def _truncate_for_log(text: str, limit: int = 240) -> str:
    """Shorten prompt text for INFO logs (prompts can be long)."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def _strip_inline_data(obj):
    """
    Return a log-safe copy of an SDK config/response with large inline blobs
    (image/video bytes, base64) replaced by a short placeholder, so we never
    dump megabytes of media into the logs.
    """
    try:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in ("data", "inline_data", "bytes", "image_bytes", "video_bytes"):
                    out[k] = f"<{len(v) if hasattr(v, '__len__') else '?'} bytes>"
                else:
                    out[k] = _strip_inline_data(v)
            return out
        if isinstance(obj, (list, tuple)):
            return [_strip_inline_data(v) for v in obj]
        if isinstance(obj, (bytes, bytearray)):
            return f"<{len(obj)} bytes>"
        return obj
    except Exception:  # pragma: no cover - logging must never raise
        return "<unloggable>"


def _briefing_prompt(neo: dict) -> str:
    """Build the NB2 Lite image prompt from NEO fields."""
    designation = _designation(neo)
    diameter = _diameter_km(neo)
    velocity = _fnum(neo.get("relative_velocity"))
    hazardous = bool(neo.get("hazardous"))
    threat = "POTENTIALLY HAZARDOUS" if hazardous else "monitored, non-hazardous"
    return (
        "Render a high-fidelity 1K 'THREAT BRIEFING' card for a NASA planetary-defense "
        "mission-control console. Dark navy background, cyan HUD accents, monospace "
        "telemetry typography, corner registration ticks, subtle grid. Feature a "
        "photorealistic rocky asteroid glyph with a dashed approach trajectory. "
        "Display crisp, correctly-spelled text fields: "
        f"DESIGNATION: {designation}; "
        f"DIAMETER: {diameter:.3f} km; "
        f"VELOCITY: {velocity:.1f} km/s; "
        f"STATUS: {threat}. "
        "Aesthetic: cinematic, authoritative, cyan-on-navy mission-control. "
        "High-fidelity, legible text; no watermark."
    )


def _impact_prompt(neo: dict, deflected: bool) -> str:
    """Build the Omni Flash video prompt from NEO fields."""
    designation = _designation(neo)
    diameter = _diameter_km(neo)
    velocity = _fnum(neo.get("relative_velocity"))
    if deflected:
        outcome = (
            "A kinetic-impactor spacecraft strikes the asteroid, imparting a small "
            "delta-v; the trajectory bends and the asteroid sweeps past Earth to a "
            "safe miss. End on the safe-miss vector."
        )
    else:
        outcome = (
            "No deflection is applied; show the asteroid continuing on its original "
            "approach corridor toward Earth (no impact frame, sim ends on approach)."
        )
    return (
        "Short cinematic space simulation, ~6 seconds, for a planetary-defense console. "
        f"An asteroid designated {designation} (~{diameter:.3f} km across, "
        f"~{velocity:.1f} km/s) approaches Earth from deep space. "
        "Photoreal Earth with correct day/night terminator and rim lighting; realistic "
        "starfield; physically-plausible motion and lighting. "
        f"{outcome} "
        "Camera: slow cinematic push-in. No text overlays, no watermark."
    )


# ---------------------------------------------------------------------------
# NB2 Lite — threat briefing image
# ---------------------------------------------------------------------------
def generate_briefing_image(neo: dict) -> dict:
    """
    Generate a THREAT BRIEFING card image for a NEO.

    Returns {"kind": "image", "src": <url>, "caption": <str>}.

    * If MEDIA_ENABLED, calls NB2 Lite ("gemini-3.1-flash-lite-image") to render
      a 1K mission-control briefing card, saves the PNG to
      app/static/assets/gen/briefing_<id>.png, and returns that /static URL.
      Wrapped in try/except with retry-on-503 (max 3, exponential backoff).
    * If disabled or anything fails, returns the local SVG fallback URL
      immediately so the caller never blocks or crashes.
    """
    designation = _designation(neo)
    logger.info("generate_briefing_image(neo=%s, enabled=%s)", designation, MEDIA_ENABLED)

    if not MEDIA_ENABLED:
        return {
            "kind": "image",
            "src": FALLBACK_BRIEFING_URL,
            "caption": "Threat briefing",
        }

    prompt = _briefing_prompt(neo)
    neo_id = _safe_id(neo)
    started = time.time()

    for attempt in range(_MAX_RETRIES):
        try:
            # Lazy import so importing this module never requires the SDK.
            from google import genai
            from google.genai import types

            client = genai.Client()
            logger.info(
                "genai.generate_content(IMAGE) model=%s prompt=%r attempt=%d",
                NB2_LITE_MODEL, _truncate_for_log(prompt), attempt + 1,
            )

            image_bytes = _call_nb2_lite(client, types, prompt)
            if not image_bytes:
                raise RuntimeError("NB2 Lite returned no image bytes")

            _ensure_gen_dir()
            out_path = os.path.join(_GEN_DIR, f"briefing_{neo_id}.png")
            with open(out_path, "wb") as fh:
                fh.write(image_bytes)

            elapsed = time.time() - started
            logger.info("Saved briefing image (%d bytes) -> %s in %.1fs",
                        len(image_bytes), out_path, elapsed)
            return {
                "kind": "image",
                "src": f"/static/assets/gen/briefing_{neo_id}.png",
                "caption": f"Threat briefing · generated in {elapsed:.1f}s",
            }

        except Exception as exc:  # noqa: BLE001 - media must never propagate
            if _is_503(exc) and attempt < _MAX_RETRIES - 1:
                backoff = _BACKOFF_BASE * (2 ** attempt)
                logger.warning("NB2 Lite 503 (attempt %d/%d); retrying in %.1fs: %s",
                               attempt + 1, _MAX_RETRIES, backoff, exc)
                time.sleep(backoff)
                continue
            logger.warning("NB2 Lite generation failed (%s); using fallback.", exc)
            break

    return {
        "kind": "image",
        "src": FALLBACK_BRIEFING_URL,
        "caption": "Threat briefing",
    }


def _call_nb2_lite(client, types, prompt: str) -> bytes | None:
    """
    Invoke NB2 Lite and return the first image's raw bytes (or None).

    gemini-3.1-flash-lite-image is an image-capable generateContent model (NOT the
    Imagen predict/generate_images API), so we request an IMAGE modality and read the
    inline image part from the response.
    """
    resp = client.models.generate_content(
        model=NB2_LITE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                return bytes(inline.data)
    return None


# ---------------------------------------------------------------------------
# Omni Flash — deflection sim video
# ---------------------------------------------------------------------------
def generate_impact_video(neo: dict, deflected: bool = True) -> dict:
    """
    Generate a short DEFLECTION SIM video for a NEO.

    Returns {"kind": "video", "src": <url>, "caption": <str>} on success.

    * If MEDIA_ENABLED, calls Omni Flash ("gemini-omni-flash-preview") to render
      a short cinematic approach + (optional) kinetic-impactor deflection, saves
      the MP4 to app/static/assets/gen/impact_<id>.mp4, and returns that URL.
      Wrapped in try/except with retry-on-503 (max 3, exponential backoff).
    * If disabled or anything fails, returns an IMAGE fallback pointing at the
      DEFLECTION SIM SVG (a <video> src to an SVG won't play), i.e.
      {"kind":"image","src":FALLBACK_IMPACT_URL,"caption":"Impact simulation"}.
    """
    designation = _designation(neo)
    logger.info("generate_impact_video(neo=%s, deflected=%s, enabled=%s)",
                designation, deflected, MEDIA_ENABLED)

    fallback = {
        "kind": "image",
        "src": FALLBACK_IMPACT_URL,
        "caption": "Impact simulation",
    }
    if not MEDIA_ENABLED:
        return fallback

    prompt = _impact_prompt(neo, deflected)
    neo_id = _safe_id(neo)
    started = time.time()

    for attempt in range(_MAX_RETRIES):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client()
            logger.info(
                "genai.generate_videos model=%s prompt=%r deflected=%s attempt=%d",
                OMNI_FLASH_MODEL, _truncate_for_log(prompt), deflected, attempt + 1,
            )

            video_bytes = _call_omni_flash(client, types, prompt)
            if not video_bytes:
                raise RuntimeError("Omni Flash returned no video bytes")

            _ensure_gen_dir()
            out_path = os.path.join(_GEN_DIR, f"impact_{neo_id}.mp4")
            with open(out_path, "wb") as fh:
                fh.write(video_bytes)

            elapsed = time.time() - started
            logger.info("Saved impact video (%d bytes) -> %s in %.1fs",
                        len(video_bytes), out_path, elapsed)
            return {
                "kind": "video",
                "src": f"/static/assets/gen/impact_{neo_id}.mp4",
                "caption": f"Impact simulation · generated in {elapsed:.1f}s",
            }

        except Exception as exc:  # noqa: BLE001 - media must never propagate
            if _is_503(exc) and attempt < _MAX_RETRIES - 1:
                backoff = _BACKOFF_BASE * (2 ** attempt)
                logger.warning("Omni Flash 503 (attempt %d/%d); retrying in %.1fs: %s",
                               attempt + 1, _MAX_RETRIES, backoff, exc)
                time.sleep(backoff)
                continue
            logger.warning("Omni Flash generation failed (%s); using fallback.", exc)
            break

    return fallback


def _call_omni_flash(client, types, prompt: str) -> bytes | None:
    """
    Invoke Omni Flash and return the generated video's raw bytes (or None).

    Video generation is long-running; poll the operation to completion, then
    download the resulting file's bytes via the SDK. Isolated here so the SDK
    surface is easy to adapt.
    """
    operation = client.models.generate_videos(
        model=OMNI_FLASH_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(number_of_videos=1),
    )
    # Poll until the long-running operation completes.
    waited = 0.0
    while not getattr(operation, "done", False) and waited < 180.0:
        time.sleep(5.0)
        waited += 5.0
        operation = client.operations.get(operation)
    logger.info("Omni Flash operation done=%s after %.0fs",
                getattr(operation, "done", False), waited)

    response = getattr(operation, "response", None) or getattr(operation, "result", None)
    videos = getattr(response, "generated_videos", None) or []
    if not videos:
        return None

    video = getattr(videos[0], "video", videos[0])
    data = getattr(video, "video_bytes", None) or getattr(video, "data", None)
    if data:
        return bytes(data)
    # Some SDK builds require an explicit download of the file handle.
    try:
        client.files.download(file=video)
        data = getattr(video, "video_bytes", None)
        if data:
            return bytes(data)
    except Exception:  # pragma: no cover
        pass
    return None


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------
def _is_503(exc: Exception) -> bool:
    """Best-effort detection of a 503 / UNAVAILABLE / overloaded error."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 503:
        return True
    text = f"{getattr(exc, 'status', '')} {exc}".lower()
    return any(tok in text for tok in ("503", "unavailable", "overloaded", "try again"))


def _summarize(resp) -> dict:
    """Small dict describing an SDK response for logging (no inline media)."""
    try:
        return {"type": type(resp).__name__,
                "attrs": [a for a in dir(resp) if not a.startswith("_")][:12]}
    except Exception:  # pragma: no cover
        return {"type": "unknown"}


# ---------------------------------------------------------------------------
# Self-test (must work with NO network and NO key)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    # Force the disabled path regardless of the ambient environment.
    MEDIA_ENABLED = False

    sample = {
        "id": "2099942",
        "name": "99942 Apophis",
        "est_diameter_min": 0.34,
        "est_diameter_max": 0.37,
        "relative_velocity": 7.42,
        "miss_distance": 31000.0,
        "absolute_magnitude": 19.7,
        "hazardous": True,
    }

    print("MEDIA_ENABLED =", MEDIA_ENABLED)
    print("briefing ->", generate_briefing_image(sample))
    print("video    ->", generate_impact_video(sample, deflected=True))
    print("video(no deflect) ->", generate_impact_video(sample, deflected=False))
