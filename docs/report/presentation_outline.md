# Presentation outline — TVFI recommendation (Group 5)

**Companion to:** `docs/report/TVFI_Group5_Report_Draft.md`  
**Length target:** ~1 page / ~6–8 slides  
**Audience:** TVFI + course checkpoint  
**Rule:** Do **not** show invented VoNB / Net CSM / CaPM numbers — use “pending Slope” or omit numeric impact until exports exist.

---

## Slide 1 — Title / ask

- STATS 4960 Group 5 × Thames Valley Financial Inc.
- Ask: Approve the monitoring design (RF + Col H + 35 bp trigger) and unlock Slope dry-run (`slope_api.py`).

## Slide 2 — Recommendation in one breath

- Daily **BoC zeros** → hold Fiera **H** → rebuild **J** → **mean \|Δ\| ≥ 35 bp** → Slope → VoNB / Net CSM / CaPM on dashboard.
- Curve-only trigger; one RF source; H held between pubs.

## Slide 3 — Ops process (flowchart)

- Intake → hold H → build J → trigger → Slope (on fire) → `monitor_snapshot.json` → dashboard.
- Call out BoC ~2-week lag as a labeled product property.

## Slide 4 — Trigger calibration

- Primary: mean \|Δ\| ≥ **35 bp** (~2 fires/year; 14/84 months).
- Old multi-rule OR ≈6.4/yr — too chatty.
- Diagnostics only: max \|Δ\|, 2s10s twist.
- Caveat: monthly Fiera history; re-calibrate on daily BoC path.

## Slide 5 — Col H + RF decisions

- **H:** `hold_latest_publication` — typical MoM ~4–6 bp; RF drives J between pubs.
- **RF:** BoC zero CSV only; Valet = freshness overlay.
- Static Fiera θ — do not retune.

## Slide 6 — Profitability (formulas, not numbers)

- Locked metrics @ 15% discount: VoNB (%), Net CSM (%), CaPM (PA1 uses L/12 per cell).
- Table shell: baseline vs implied — **numbers pending Slope exports**.
- Blocker: TVFI `slope_api.py`.

## Slide 7 — Open reviews / risks

- Partner sign-off: H, RF lag, 35 bp, >30y extrapolation, dashboard KPIs.
- Risks: BoC lag, extrapolation, trigger re-cal on daily data, no live profitability yet.

## Slide 8 — Next steps / ask

1. Sign off § review list in report draft.
2. Provide `slope_api.py` / dummy Slope for dry-run.
3. Fill profitability comparison; finalize ≤10-page Word report + deck.

---

*Optional speaker note:* Progress update absorbed (~87/100); design choices map 1:1 to Sam’s binding constraints.
