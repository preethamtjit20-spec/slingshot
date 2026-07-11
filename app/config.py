"""
config.py — CENTRALIZED configuration for SLINGSHOT.

WHAT THIS FILE IS ABOUT
=======================
Every configurable item (model IDs, GCP project, region, secret/key names, NASA API,
feature flags) lives here so nothing is hard-coded or scattered. Change a model or the
project once, here, and it changes everywhere.

MODELS
======
The model IDs the app uses are centralized in `MODELS`; reference models via this dict.
"""
from __future__ import annotations
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

# ---- GCP project / region ---------------------------------------------------
PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT", "deepmind-hack26blr-4182")
LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# ---- Models used by the app -------------------------------------------------
MODELS: dict[str, str] = {
    "general":        "gemini-3.5-flash",                    # reasoning + Computer Use
    "live":           "gemini-3.1-flash-live-preview",       # real-time voice+vision (Live API)
    "live_translate": "gemini-3.5-live-translate-preview",   # live translation
    "tts":            "gemini-3.1-flash-tts-preview",         # text-to-speech
    "omni":           "gemini-omni-flash-preview",            # GenMedia: conversational video
    "nano_banana_2_lite": "gemini-3.1-flash-lite-image",      # GenMedia: fast image (<4s)
    "interactions":   "antigravity-preview-05-2026",          # iAPI / Managed Agents
}

# The realtime model the ADK Live session runs on.
LIVE_MODEL: str = os.getenv("DEMO_AGENT_MODEL", MODELS["live"])
# Standard model for non-live generateContent (tools, classification prompts, 'adk web').
FLASH_MODEL: str = MODELS["general"]

# ---- Secrets / external APIs ------------------------------------------------
# NASA NeoWs API key. Loaded from Secret Manager or env; DEMO_KEY works for light use.
NASA_API_KEY_SECRET: str = os.getenv("NASA_API_KEY_SECRET", "nasa-api-key")
GEMINI_API_KEY_SECRET: str = os.getenv("GEMINI_API_KEY_SECRET", "gemini-api-key")
NEOWS_BASE: str = "https://api.nasa.gov/neo/rest/v1"

# ---- Dataset ----------------------------------------------------------------
# Kaggle: sameepvani/nasa-nearest-earth-objects (NASA JPL/NeoWs source, public domain).
CACHED_NEO_SNAPSHOT = os.path.join(os.path.dirname(__file__), "data", "neo_snapshot.json")

# ---- Logging ----------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


def summary() -> dict:
    """Non-secret config summary for startup logs / self-test (never exposes keys)."""
    return {
        "project_id": PROJECT_ID, "location": LOCATION,
        "live_model": LIVE_MODEL, "flash_model": FLASH_MODEL,
        "models": MODELS, "neows_base": NEOWS_BASE, "log_level": LOG_LEVEL,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))
