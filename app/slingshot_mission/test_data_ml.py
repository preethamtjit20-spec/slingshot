"""
test_data_ml.py — offline smoke test for SLINGSHOT's data + ML layer.
=====================================================================

Runs with NO network and NO API key. Verifies:
  * the offline snapshot loads and is non-empty,
  * ``get_cached_neo()`` returns a fully-formed canonical NEO dict,
  * ``classify_neo()`` flags the dramatic hazardous NEO as hazardous with a
    meaningful Torino score (>= 5),
  * ``classify_neo()`` flags a tiny distant NEO as not hazardous with Torino 0.

Run:  python slingshot_mission/test_data_ml.py    (from the app/ directory)
or:   python app/slingshot_mission/test_data_ml.py (from the repo root)
"""
from __future__ import annotations

import os
import sys

# --- sys.path bootstrap so `import data` / `import classifier` work regardless
# of the current working directory when this file is run directly. --------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from data import load_snapshot, get_cached_neo  # noqa: E402
from classifier import classify_neo  # noqa: E402

REQUIRED_KEYS = (
    "id", "name", "est_diameter_min", "est_diameter_max",
    "relative_velocity", "miss_distance", "absolute_magnitude", "hazardous",
)


def test_snapshot_non_empty() -> None:
    """load_snapshot() returns a non-empty list of NEOs."""
    snapshot = load_snapshot()
    assert isinstance(snapshot, list), "snapshot must be a list"
    assert len(snapshot) > 0, "snapshot must be non-empty"
    print(f"PASS: load_snapshot() returned {len(snapshot)} NEOs")


def test_cached_neo_shape() -> None:
    """get_cached_neo() returns a dict containing every required key."""
    neo = get_cached_neo()
    for key in REQUIRED_KEYS:
        assert key in neo, f"cached NEO missing key: {key}"
    print(f"PASS: get_cached_neo() has all required keys ({neo['name']})")


def test_hazardous_classification() -> None:
    """The dramatic hazardous NEO classifies as hazardous with Torino >= 5."""
    neo = get_cached_neo(prefer_hazardous=True)
    result = classify_neo(neo)
    assert result["hazardous"] is True, "dramatic NEO should be hazardous"
    assert result["torino"] >= 5, f"expected Torino >= 5, got {result['torino']}"
    print(
        f"PASS: classify_neo() flags {neo['name']} hazardous "
        f"(torino={result['torino']}, conf={result['confidence']})"
    )


def test_non_hazardous_classification() -> None:
    """A tiny, distant NEO classifies as not hazardous with Torino 0."""
    tiny = {
        "id": "test-tiny",
        "name": "(tiny harmless)",
        "est_diameter_min": 0.003,
        "est_diameter_max": 0.007,
        "relative_velocity": 5.0,
        "miss_distance": 40_000_000.0,
        "absolute_magnitude": 28.5,
        "hazardous": False,
    }
    result = classify_neo(tiny)
    assert result["hazardous"] is False, "tiny distant NEO should be not hazardous"
    assert result["torino"] == 0, f"expected Torino 0, got {result['torino']}"
    print(
        f"PASS: classify_neo() flags {tiny['name']} not hazardous "
        f"(torino={result['torino']})"
    )


def main() -> int:
    """Run every offline check; return process exit code (0 = all passed)."""
    tests = [
        test_snapshot_non_empty,
        test_cached_neo_shape,
        test_hazardous_classification,
        test_non_hazardous_classification,
    ]
    for test in tests:
        test()
    print(f"\nALL {len(tests)} TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
