"""
classifier.py — SLINGSHOT explainable NEO hazard classifier.
============================================================

WHAT THIS FILE IS ABOUT
-----------------------
Given a near-Earth object (NEO) in SLINGSHOT's canonical dict shape (see
``data.py``), decide whether it is potentially hazardous and produce a
Torino-scale-style severity score with a plain-English justification.

DESIGN: TRANSPARENT RULE FIRST, ML SECOND
-----------------------------------------
The PRIMARY path is a transparent, documented rule that mirrors NASA's own
"potentially hazardous asteroid" (PHA) definition:

    An object is potentially hazardous when
        absolute_magnitude H <= 22.0   (roughly diameter >= 140 m), AND
        miss_distance       <= 7,480,000 km  (0.05 AU, the MOID threshold).

We deliberately lead with this rule because it is auditable: a mission operator
can read the reason string and check the numbers themselves. From the same
inputs we derive a Torino-like 0-10 score (bigger + closer + faster => higher).

We ALSO train a small scikit-learn RandomForest on the snapshot as a secondary,
data-driven confidence signal. HONEST CAVEAT: in the bundled dataset the
``hazardous`` label is itself largely a deterministic function of size/distance
(the very rule above). That is label leakage, so the RF's apparent accuracy is
inflated and it mostly re-learns the rule. We therefore treat the RF only as a
confidence estimate, never as ground truth, and the rule remains authoritative.
If scikit-learn or the data is unavailable, we skip the ML entirely and fall
back to a rule-derived confidence — the classifier stays fast and robust.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("slingshot.classifier")

# --- NASA-aligned PHA thresholds (documented, auditable) ---------------------
H_THRESHOLD = 22.0            # absolute magnitude; <= 22 ~ diameter >= 140 m
MISS_THRESHOLD_KM = 7_480_000.0  # 0.05 AU in km — the PHA minimum-orbit threshold

# Feature order used by the RandomForest (kept in one place for train + predict).
_FEATURES = ("absolute_magnitude", "est_diameter_max", "relative_velocity", "miss_distance")

# Lazily-initialised ML model state.
#   None  -> not attempted yet
#   False -> attempted and unavailable (sklearn/data missing) — do not retry
#   model -> a fitted estimator
_RF_MODEL = None


def _score_torino(neo: dict) -> int:
    """Derive a Torino-like 0-10 severity score from size, closeness and speed.

    The score blends three normalised contributions — larger diameter, smaller
    miss distance, and higher relative velocity all push the score up — and is
    capped at 10. Non-hazardous objects always score 0 (handled by the caller).
    """
    diameter = float(neo.get("est_diameter_max", 0.0))
    miss = float(neo.get("miss_distance", MISS_THRESHOLD_KM))
    velocity = float(neo.get("relative_velocity", 0.0))

    # Size contribution: ~0 at 0.14 km (PHA floor) rising to full weight near ~1 km+.
    size_term = min(diameter / 1.0, 1.0)
    # Closeness contribution: 1.0 at Earth's surface, 0 at the 0.05 AU threshold.
    closeness_term = max(0.0, 1.0 - (miss / MISS_THRESHOLD_KM))
    # Velocity contribution: normalised against a fast ~40 km/s approach.
    velocity_term = min(velocity / 40.0, 1.0)

    # Weighted blend -> 0..10. Size and closeness dominate, velocity modulates.
    raw = (0.45 * size_term + 0.40 * closeness_term + 0.15 * velocity_term) * 10.0
    score = int(round(raw))
    return max(0, min(score, 10))


def _impact_prob_for_score(score: int) -> str:
    """Return a plausible '1 : N' impact-probability string scaled by the score.

    Higher Torino score => shorter odds (smaller N). This is an illustrative
    figure for the mission display, not a real orbital-mechanics computation.
    """
    if score <= 0:
        return "1 : 100,000,000"
    # Odds shorten roughly by an order of magnitude as the score climbs.
    denominator = max(int(2_700_000 / (score ** 2)), 12)
    return f"1 : {denominator:,}"


def _ensure_rf_model():
    """Lazily train the RandomForest on the snapshot; return the model or None.

    Wrapped in try/except so any failure (missing sklearn, unreadable data, too
    few samples) simply disables the ML path — the rule still works.
    """
    global _RF_MODEL
    if _RF_MODEL is not None:
        return _RF_MODEL if _RF_MODEL is not False else None
    try:
        from sklearn.ensemble import RandomForestClassifier

        # Local import so the classifier does not hard-depend on the data module
        # layout at import time.
        try:
            from slingshot_mission.data import load_snapshot
        except Exception:
            from data import load_snapshot  # type: ignore

        snapshot = load_snapshot()
        if not snapshot or len(snapshot) < 4:
            raise ValueError("insufficient snapshot rows for training")

        X = [[float(n[f]) for f in _FEATURES] for n in snapshot]
        y = [1 if n.get("hazardous") else 0 for n in snapshot]
        if len(set(y)) < 2:
            raise ValueError("snapshot has a single class; cannot train")

        model = RandomForestClassifier(
            n_estimators=50, class_weight="balanced", random_state=0
        )
        model.fit(X, y)
        _RF_MODEL = model
        logger.info("_ensure_rf_model(): trained RandomForest on %d NEOs", len(snapshot))
        return model
    except Exception as exc:
        logger.warning("_ensure_rf_model(): ML unavailable (%s); using rule only", exc)
        _RF_MODEL = False
        return None


def classify_neo(neo: dict) -> dict:
    """Classify a NEO's hazard level with a transparent rule (+ optional ML confidence).

    Args:
        neo: a canonical NEO dict with at least ``absolute_magnitude``,
            ``est_diameter_max``, ``relative_velocity`` and ``miss_distance``.

    Returns:
        dict with keys:
            "hazardous"   (bool): rule verdict (H <= 22 AND miss <= 0.05 AU).
            "torino"      (int) : 0-10 severity; 0 when not hazardous.
            "impact_prob" (str) : illustrative '1 : N' odds scaled by torino.
            "reason"      (str) : one-sentence explanation citing the numbers.
            "confidence"  (float): RF probability when available, else rule margin.
    """
    logger.info("classify_neo() called for %s", neo.get("name", neo.get("id", "?")))

    H = float(neo.get("absolute_magnitude", 99.0))
    miss = float(neo.get("miss_distance", MISS_THRESHOLD_KM * 10))
    diameter = float(neo.get("est_diameter_max", 0.0))
    velocity = float(neo.get("relative_velocity", 0.0))

    # --- Primary transparent rule --------------------------------------------
    big_enough = H <= H_THRESHOLD
    close_enough = miss <= MISS_THRESHOLD_KM
    hazardous = bool(big_enough and close_enough)

    torino = _score_torino(neo) if hazardous else 0
    impact_prob = _impact_prob_for_score(torino)

    if hazardous:
        reason = (
            f"Potentially hazardous: absolute magnitude H={H:.1f} (<= {H_THRESHOLD:.0f}, "
            f"~diameter up to {diameter:.2f} km) and miss distance {miss:,.0f} km "
            f"(<= {MISS_THRESHOLD_KM:,.0f} km / 0.05 AU) at {velocity:.1f} km/s -> "
            f"Torino {torino}."
        )
    else:
        why = []
        if not big_enough:
            why.append(f"too small (H={H:.1f} > {H_THRESHOLD:.0f})")
        if not close_enough:
            why.append(f"passes far away ({miss:,.0f} km > {MISS_THRESHOLD_KM:,.0f} km)")
        reason = "Not hazardous: " + " and ".join(why) + "."

    # --- Secondary ML confidence signal --------------------------------------
    # Default confidence from the rule margin: how decisively the object clears or
    # misses both thresholds (0.5 = borderline, 1.0 = far from the boundary).
    h_margin = min(abs(H - H_THRESHOLD) / H_THRESHOLD, 1.0)
    miss_margin = min(abs(miss - MISS_THRESHOLD_KM) / MISS_THRESHOLD_KM, 1.0)
    confidence = round(0.5 + 0.5 * ((h_margin + miss_margin) / 2.0), 3)

    model = _ensure_rf_model()
    if model is not None:
        try:
            X = [[H, diameter, velocity, miss]]
            proba = model.predict_proba(X)[0]
            classes = list(model.classes_)
            # Probability the model assigns to the class matching our rule verdict.
            target = 1 if hazardous else 0
            if target in classes:
                confidence = round(float(proba[classes.index(target)]), 3)
            logger.info("classify_neo(): RF confidence=%.3f", confidence)
        except Exception as exc:
            logger.warning("classify_neo(): RF predict failed (%s); using rule margin", exc)

    result = {
        "hazardous": hazardous,
        "torino": torino,
        "impact_prob": impact_prob,
        "reason": reason,
        "confidence": confidence,
    }
    logger.info("classify_neo(): -> %s", result)
    return result


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    logging.basicConfig(level=logging.INFO)
    try:
        from slingshot_mission.data import get_cached_neo
    except Exception:
        from data import get_cached_neo  # type: ignore
    print(classify_neo(get_cached_neo()))
