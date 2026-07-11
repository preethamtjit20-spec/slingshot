# SLINGSHOT — Factual Research Backbone

The data + citations grounding the build. Everything the on-stage narrator says traces here.

## Primary dataset (Kaggle → NASA source)
- **NASA - Nearest Earth Objects** — `sameepvani/nasa-nearest-earth-objects` (~90,836 rows × 10 cols; ~87% not-hazardous / 13% hazardous). Sourced from NASA JPL / NeoWs → public-domain data.
- Columns: `id, name, est_diameter_min, est_diameter_max, relative_velocity (km/s), miss_distance (km), orbiting_body, sentry_object, absolute_magnitude (H), hazardous(TARGET)`.
- Richer backup (real orbital elements for the 3D viz): `shrutimehta/nasa-asteroids-classification` (~4,687×40).
- Population/pivot: `sakhawat18/asteroid-dataset` (JPL SBDB, ~950k). Exoplanet pivot: `nasa/kepler-exoplanet-search-results`.

## Live API — NASA NeoWs (no Kaggle needed)
- Base: `https://api.nasa.gov/neo/rest/v1/`
- `GET /feed?start_date&end_date&api_key=` (≤7-day window) · `GET /neo/{id}` · `GET /neo/browse`
- Field → dataset mapping: `absolute_magnitude_h→absolute_magnitude`, `estimated_diameter.kilometers.*`, `is_potentially_hazardous_asteroid→hazardous`, `close_approach_data[].relative_velocity.kilometers_per_second`, `.miss_distance.kilometers`, `orbital_data→3D orbit`.
- `DEMO_KEY`: 30 req/hr, 50/day. Free key at api.nasa.gov: 1,000 req/hr. **Load key from env / Secret Manager — never hardcode.**

## ML approach
- `RandomForestClassifier` (scikit-learn) is the literature's top performer (~94–99.5% reported).
- **Honesty caveat:** the PHA label is partly deterministic from size (H ≤ 22 ≈ ≥140 m) + MOID ≤ 0.05 AU, so accuracy is inflated / partial label leakage. Report precision/recall/F1/ROC-AUC, use `class_weight='balanced'`, stratified split. A transparent rule (`H ≤ 22 AND miss_distance within 0.05 AU / 7.48M km`) reproduces most of the boundary — good for an *explainable* demo.

## Research anchors
| Claim | Evidence |
|---|---|
| ML classifies PHAs; RF best | "Machine learning techniques for classifying dangerous asteroids," MethodsX/PMC 2023 (PMC10480302); GNN variant arXiv:2504.18605 (2025) |
| Impact-risk scale (Torino) | Binzel (2000), *Planetary and Space Science* 48(4):297–303; CNEOS torino_scale |
| Kinetic-impactor deflection (DART) | Thomas et al. (2023), *Nature* 616:448 — Dimorphos orbit −33.0±1.0 min |
| DART momentum enhancement (ejecta) | Cheng et al. (2023), *Nature* 616:457 — β ≈ 2.2–4.9 |
| Autonomous/multi-agent space ops | "LLMSat," arXiv:2405.01392 (2024); LLM Multi-Agent survey, IJCAI 2024 |

## On-stage facts (each sourced)
1. **DART worked** — 26 Sep 2022, first-ever asteroid deflection test (hit Dimorphos). NASA.
2. **−32 min** orbital-period change (NASA initial); **−33.0±1.0 min** refined (*Nature* 2023).
3. Beat the 73-second success bar by **>25×**. JPL.
4. **Ejecta** did most of the work (β≈2.2–4.9). Cheng et al. 2023.
5. **~2,473 known PHAs** (Jan 2025), ~154 larger than 1 km. CNEOS.
6. **PHA definition:** ≥140 m (H≤22) AND passes within 0.05 AU (~7.48M km). CNEOS.
7. **Torino scale 0–10** (IAU 1999). CNEOS.
8. **Live data one call away** — NeoWs streams real close approaches; DEMO_KEY = 30/hr.

## Recent context (2024–2026) — why this is timely
- **2024 YR4:** record **3.1%** Earth-impact probability (18 Feb 2025), Torino **3** (2nd-highest ever, after Apophis); **first object ever** to trigger IAWN notification + SMPAG mission-planning. Earth ruled out ~23 Feb 2025; a residual ~4% *lunar*-impact chance was cleared by JWST in Feb 2026. ~60 m. (Scientific American; Wikipedia/JWST; IAWN 2025-01-29.)
- **Apophis · 13 Apr 2029:** ~340 m, passes inside geostationary altitude (~31,600 km geocentric). Active 2026 science: Ďurech, Vokrouhlický, Pravec, et al., *"The spin state of asteroid Apophis and a prediction of its change during the 2029 close encounter with Earth,"* **arXiv:2604.24566** (submitted 27 Apr 2026) — models how Earth's gravity alters Apophis's spin. NASA **OSIRIS-APEX** rendezvous is being prepared now.
- **ESA Hera:** launched 7 Oct 2024; **arrives Nov 2026** at Didymos/Dimorphos to measure DART's momentum transfer (β) — the still-unconfirmed result of humanity's only deflection.
- **NEO Surveyor:** first IR planetary-defense telescope; launch **no earlier than 2027**; will find ⅔ of NEOs > 140 m — an open detection gap today.

_Verify flags: Kaggle blocks headless fetch (schema corroborated via notebooks — glance at the page before pitch); use "~32 min" (NASA) or "33 min" (Nature) consistently._
