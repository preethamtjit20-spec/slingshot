"""
test_integration.py — end-to-end tool-chain sanity check (offline, no LLM/network).
Runs the mission the agents would drive (SENTRY→GNC→ASSESS→INTEL→FIDO) by calling the
tools directly, and asserts every tool returns a well-formed render_command for the
frontend. No API key, no model call, no data mutation beyond in-memory session state.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # put app/ on path

# Import the tools module directly (avoid importing the package __init__ -> google.adk,
# so this test runs even without the heavy ADK dependency).
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "sl_tools", os.path.join(os.path.dirname(__file__), "tools.py"))
t = importlib.util.module_from_spec(_spec)
sys.modules["sl_tools"] = t
# tools.py uses `from . import data/classifier/media` lazily; give it a package context.
t.__package__ = "slingshot_mission"
import slingshot_mission  # noqa  (namespace only; light)
_spec.loader.exec_module(t)


def _cmds(resp):
    rc = resp.get("render_command")
    return rc if isinstance(rc, list) else [rc]


def _valid(resp):
    assert resp["status"] == "success", resp
    for c in _cmds(resp):
        assert isinstance(c, dict) and "layer" in c, c


def main():
    r = t.track_asteroid("cached"); _valid(r)
    layers = {c["layer"] for c in _cmds(r)}
    assert {"scene", "threat", "alert"} <= layers, layers
    print(f"PASS track_asteroid -> {r['neo']['name'] if 'neo' in r else '?'} · layers={sorted(layers)}")

    _valid(t.plot_trajectory()); print("PASS plot_trajectory")

    r = t.classify_hazard(); _valid(r)
    cls = r["classification"]
    assert "hazardous" in cls and "torino" in cls
    print(f"PASS classify_hazard -> hazardous={cls['hazardous']} torino={cls['torino']}")

    r = t.generate_briefing(); _valid(r)
    media_cmd = [c for c in _cmds(r) if c["layer"] == "media"][0]
    assert media_cmd["src"], media_cmd
    print(f"PASS generate_briefing -> media src={media_cmd['src']}")

    r = t.generate_impact_sim(deflected=True); _valid(r); print("PASS generate_impact_sim")

    r = t.deflect_asteroid(); _valid(r)
    assert any(c["layer"] == "scene" and c.get("action") == "deflect" for c in _cmds(r))
    print("PASS deflect_asteroid -> scene deflect emitted")

    _valid(t.reset_console()); print("PASS reset_console")
    print("\nALL INTEGRATION TESTS PASSED (tool chain -> render_commands well-formed).")


if __name__ == "__main__":
    main()
