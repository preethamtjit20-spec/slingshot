"""
test_media.py — OFFLINE tests for the SLINGSHOT generated-media layer.

Runs with MEDIA disabled (SLINGSHOT_MEDIA off): asserts both public functions
return well-formed dicts whose `src` points at an existing local fallback file.
Requires NO network, NO API key, and NO google-genai SDK.

Run:  python test_media.py       ->  prints PASS on success.
"""
from __future__ import annotations

import os
import sys

# Ensure the media flag is OFF before importing the module (it reads the env
# at import time). Then import via package or direct path.
os.environ["SLINGSHOT_MEDIA"] = "0"

try:
    from slingshot_mission import media  # when run as part of the package
except Exception:  # pragma: no cover - allow direct `python test_media.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import media  # type: ignore


SAMPLE_NEO = {
    "id": "2099942",
    "name": "99942 Apophis",
    "est_diameter_min": 0.34,
    "est_diameter_max": 0.37,
    "relative_velocity": 7.42,
    "miss_distance": 31000.0,
    "absolute_magnitude": 19.7,
    "hazardous": True,
}

# .../app/slingshot_mission/test_media.py -> .../app
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _url_to_path(url: str) -> str:
    """Map a /static/... URL to its on-disk path under app/static."""
    assert url.startswith("/static/"), f"unexpected src url: {url}"
    return os.path.join(_APP_DIR, url.lstrip("/").replace("/", os.sep))


def test_media_disabled_flag():
    """The module default flag must be OFF (demo-safe)."""
    assert media.MEDIA_ENABLED is False, "MEDIA_ENABLED must default to False"


def test_briefing_returns_fallback():
    """Briefing returns an image dict pointing at an existing fallback SVG."""
    result = media.generate_briefing_image(SAMPLE_NEO)
    assert isinstance(result, dict), "result must be a dict"
    assert set(result.keys()) == {"kind", "src", "caption"}, result.keys()
    assert result["kind"] == "image", result["kind"]
    assert result["src"] == media.FALLBACK_BRIEFING_URL, result["src"]
    path = _url_to_path(result["src"])
    assert os.path.isfile(path), f"fallback file missing: {path}"
    assert "fallback" in result["caption"].lower(), result["caption"]


def test_video_returns_fallback():
    """Video returns an IMAGE fallback (svg can't play in <video>) that exists."""
    result = media.generate_impact_video(SAMPLE_NEO, deflected=True)
    assert isinstance(result, dict), "result must be a dict"
    assert set(result.keys()) == {"kind", "src", "caption"}, result.keys()
    # Fallback is an image because an SVG cannot play as a <video> source.
    assert result["kind"] == "image", result["kind"]
    assert result["src"] == media.FALLBACK_IMPACT_URL, result["src"]
    path = _url_to_path(result["src"])
    assert os.path.isfile(path), f"fallback file missing: {path}"
    assert "fallback" in result["caption"].lower(), result["caption"]


def test_video_not_deflected_also_ok():
    """The non-deflected branch must also return the safe fallback offline."""
    result = media.generate_impact_video(SAMPLE_NEO, deflected=False)
    assert result["kind"] == "image"
    assert os.path.isfile(_url_to_path(result["src"]))


def main() -> int:
    tests = [
        test_media_disabled_flag,
        test_briefing_returns_fallback,
        test_video_returns_fallback,
        test_video_not_deflected_also_ok,
    ]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print("PASS — media layer returns valid fallbacks offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
