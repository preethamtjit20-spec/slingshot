"""
data.py — SLINGSHOT NEO data access layer (offline snapshot + live NASA NeoWs).
================================================================================

WHAT THIS FILE IS ABOUT
-----------------------
This module is the single source of near-Earth-object (NEO) data for the whole
SLINGSHOT app. Everything downstream (the hazard classifier, the mission agents,
the UI) consumes NEOs in ONE canonical dict shape:

    {
      "id":                 str,      # NASA object reference id
      "name":               str,      # human-readable designation
      "est_diameter_min":   float,    # estimated diameter, kilometers (low)
      "est_diameter_max":   float,    # estimated diameter, kilometers (high)
      "relative_velocity":  float,    # close-approach relative velocity, km/s
      "miss_distance":      float,    # close-approach miss distance, km
      "absolute_magnitude": float,    # absolute magnitude H
      "hazardous":          bool,     # NASA "potentially hazardous" flag
    }

TWO DATA PATHS
--------------
1. OFFLINE SNAPSHOT (`load_snapshot` / `get_cached_neo`): reads a bundled JSON
   file of ~12 realistic NEOs. This guarantees the demo runs with NO network and
   NO API key — critical for a reliable live hackathon demo.

2. LIVE FEED (`get_live_neo`): calls the NASA NeoWs "feed" endpoint for today,
   flattens the response into our canonical shape, and returns the most notable
   object. It is defensive by design: on ANY failure (no network, blocked egress,
   rate limit, malformed payload, empty result) it logs a warning and transparently
   falls back to the offline snapshot. It NEVER raises to the caller.

SECRETS
-------
The NASA API key is resolved from (in priority order): the `api_key` argument,
the `NASA_API_KEY` environment variable, then the public `DEMO_KEY`. No key is
ever hard-coded in this file.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date

logger = logging.getLogger("slingshot.data")

# Path to the offline snapshot, resolved relative to THIS file so it works no
# matter what the process working directory is.
_SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "neo_snapshot.json")

# NASA NeoWs "feed" endpoint (documented public planetary-data API).
_NEOWS_FEED_URL = "https://api.nasa.gov/neo/rest/v1/feed"

# The keys every canonical NEO dict must contain.
REQUIRED_KEYS = (
    "id", "name", "est_diameter_min", "est_diameter_max",
    "relative_velocity", "miss_distance", "absolute_magnitude", "hazardous",
)

# Module-level cache so we read the JSON file from disk at most once per process.
_SNAPSHOT_CACHE: list[dict] | None = None


def load_snapshot() -> list[dict]:
    """Load the bundled offline NEO snapshot as a list of canonical NEO dicts.

    Reads ``../data/neo_snapshot.json`` (relative to this file) exactly once and
    caches the parsed list in a module global for all subsequent calls.

    Returns:
        list[dict]: the parsed NEO objects. Returns an empty list only if the
        file is missing or unreadable (which is logged as an error).
    """
    global _SNAPSHOT_CACHE
    logger.info("load_snapshot() called")
    if _SNAPSHOT_CACHE is not None:
        logger.info("load_snapshot(): returning %d cached NEOs", len(_SNAPSHOT_CACHE))
        return _SNAPSHOT_CACHE
    try:
        with open(_SNAPSHOT_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("snapshot JSON root is not a list")
        _SNAPSHOT_CACHE = data
        logger.info("load_snapshot(): loaded %d NEOs from %s", len(data), _SNAPSHOT_PATH)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("load_snapshot(): failed to read %s: %s", _SNAPSHOT_PATH, exc)
        _SNAPSHOT_CACHE = []
    return _SNAPSHOT_CACHE


def get_cached_neo(prefer_hazardous: bool = True) -> dict:
    """Return one representative NEO from the offline snapshot.

    Args:
        prefer_hazardous: when True (default), prefer a hazardous object, and
            among those the largest by maximum estimated diameter — this surfaces
            the "dramatic" demo asteroid. When False, just return the first NEO.

    Returns:
        dict: a single canonical NEO dict. Falls back to a hard-coded minimal
        object only in the pathological case of an empty/absent snapshot, so
        callers can always rely on a valid dict.
    """
    logger.info("get_cached_neo(prefer_hazardous=%s) called", prefer_hazardous)
    snapshot = load_snapshot()
    if not snapshot:
        logger.warning("get_cached_neo(): snapshot empty, returning safe default NEO")
        return {
            "id": "0", "name": "(fallback)", "est_diameter_min": 0.34,
            "est_diameter_max": 0.76, "relative_velocity": 19.4,
            "miss_distance": 71900.0, "absolute_magnitude": 21.3, "hazardous": True,
        }
    if prefer_hazardous:
        hazardous = [n for n in snapshot if n.get("hazardous")]
        if hazardous:
            chosen = max(hazardous, key=lambda n: n.get("est_diameter_max", 0.0))
            logger.info("get_cached_neo(): chose hazardous NEO %s", chosen.get("name"))
            return chosen
    logger.info("get_cached_neo(): returning first snapshot NEO %s", snapshot[0].get("name"))
    return snapshot[0]


def _map_neows_object(raw: dict) -> dict | None:
    """Map a single raw NASA NeoWs object to our canonical NEO dict.

    Returns None if the object is missing the close-approach data we need, so the
    caller can skip it rather than crash on a partial record.
    """
    try:
        cad = raw.get("close_approach_data") or []
        if not cad:
            return None
        first = cad[0]
        diameter = raw["estimated_diameter"]["kilometers"]
        return {
            "id": str(raw.get("id", "")),
            "name": str(raw.get("name", "")).strip(),
            "est_diameter_min": float(diameter["estimated_diameter_min"]),
            "est_diameter_max": float(diameter["estimated_diameter_max"]),
            "relative_velocity": float(first["relative_velocity"]["kilometers_per_second"]),
            "miss_distance": float(first["miss_distance"]["kilometers"]),
            "absolute_magnitude": float(raw["absolute_magnitude_h"]),
            "hazardous": bool(raw.get("is_potentially_hazardous_asteroid", False)),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("_map_neows_object(): skipping malformed object: %s", exc)
        return None


def get_live_neo(api_key: str | None = None, prefer_hazardous: bool = True) -> dict:
    """Fetch the most notable NEO from NASA's live NeoWs feed for today.

    Calls ``GET https://api.nasa.gov/neo/rest/v1/feed`` with today's date as both
    start and end date, flattens the date->list ``near_earth_objects`` map, maps
    each object to our canonical shape, and picks the most notable one.

    "Most notable" means: prefer potentially-hazardous objects (when
    ``prefer_hazardous`` is True), then break ties by the largest maximum
    estimated diameter.

    This function is deliberately crash-proof: on ANY exception, a missing key,
    an empty feed, or a network/timeout error, it logs a warning and returns
    :func:`get_cached_neo`. It NEVER raises to the caller.

    Args:
        api_key: NASA API key. If None, falls back to the ``NASA_API_KEY`` env
            var, then to the public ``DEMO_KEY``.
        prefer_hazardous: prefer hazardous objects when selecting the notable NEO.

    Returns:
        dict: a single canonical NEO dict (live if possible, cached otherwise).
    """
    key = api_key or os.getenv("NASA_API_KEY") or "DEMO_KEY"
    today = date.today().isoformat()
    logger.info("get_live_neo(prefer_hazardous=%s) called for date=%s", prefer_hazardous, today)
    try:
        import requests  # imported lazily so the offline path has no hard dependency

        resp = requests.get(
            _NEOWS_FEED_URL,
            params={"start_date": today, "end_date": today, "api_key": key},
            timeout=6,
        )
        resp.raise_for_status()
        payload = resp.json()

        by_date = payload.get("near_earth_objects", {}) or {}
        flat: list[dict] = []
        for objects in by_date.values():
            for raw in objects or []:
                mapped = _map_neows_object(raw)
                if mapped is not None:
                    flat.append(mapped)

        if not flat:
            logger.warning("get_live_neo(): live feed returned no usable objects; using snapshot")
            return get_cached_neo(prefer_hazardous)

        if prefer_hazardous:
            hazardous = [n for n in flat if n["hazardous"]]
            pool = hazardous if hazardous else flat
        else:
            pool = flat
        chosen = max(pool, key=lambda n: n["est_diameter_max"])
        logger.info(
            "get_live_neo(): selected %s (hazardous=%s) from %d live NEOs",
            chosen["name"], chosen["hazardous"], len(flat),
        )
        return chosen
    except Exception as exc:
        logger.warning("get_live_neo(): live fetch failed (%s); falling back to snapshot", exc)
        return get_cached_neo(prefer_hazardous)


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    logging.basicConfig(level=logging.INFO)
    print("cached:", get_cached_neo()["name"])
    print("live:  ", get_live_neo()["name"])
