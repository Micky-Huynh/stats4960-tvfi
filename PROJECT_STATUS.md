# Project status — TVFI yield-curve monitoring

**Course:** STATS 4960 · Group 5 × Thames Valley Financial Inc.  
**Repo:** [Micky-Huynh/stats4960-tvfi](https://github.com/Micky-Huynh/stats4960-tvfi)  
**Last updated:** 2026-11-20

**Goal (one line):** Daily Canadian risk-free + Fiera construction → Slope annual forwards (column J) → cheap no-Slope trigger → insurer VoNB / Net CSM / CaPM → dashboard via `monitor_snapshot.json`.

---

## What’s done

### Data & archive
- Fiera CIA IFRS 17 monthly **method** workbooks archived (85 months, 2019-10 → 2026-10) under `data/fiera/monthly_raw/`
- Extracted CSVs under `data/fiera/extracted/` (construction, col H history, Canada par, static params)
- Slope-ready sample curve at repo root: `sample_curve.xlsx`
- **BoC zeros:** live intake at `pipeline/boc_intake.py` → `data/risk_free/YYYY-MM-DD.json` (latest live: `2026-10-21`, ~2-week lag)

### Monitoring pipeline (`pipeline/`)
- Fiera history → curve metrics → trigger → `monitor_snapshot.json`
- Writes canonical snapshot to `data/monitor/` and copies into the dashboard folder
- **Column J builder** (`pipeline/curve_builder.py`): `--rf fiera|boc`; Fiera fixture validates vs published J (~0 bp error). Outputs under `data/curves/`
- **Rebuilt snapshot (Wave 4):** `python3 -m pipeline.build_monitor_snapshot --rebuilt` **auto-prefers BoC RF** when `data/risk_free/` has a snapshot (`--rf auto|boc|fiera`). Latest: `Fiera-20261030-R01`, **`NO_TRIGGER`**, `rf_source=boc_zero_coupon_csv`, mean |Δ| ≈ **16.9 bp**
- **Decision log:** each build writes `data/decisions/YYYY-MM-DD.json`; snapshot carries `decision` + `profitability` hooks (`profitability.status=not_run` until Slope exports exist)
- **Calibrated trigger** (`pipeline/trigger.py`): primary rule liability-weighted |Δ| **T ≥ 25 bp** (~3.3 fires/year over years 1–30; team 2026-11-20). Diagnostics: max bucket mean |Δ| **40 bp**, |2s10s| 40 bp, signed S (no threshold). Bucket does **not** fire alone. Back-test: `python3 -m pipeline.backtest_trigger`

### Dashboard
- Static prototype: `Dashboard UI/Group5_Monitoring_Dashboard/`
- Overview KPIs use **implied − pricing** (aligned with pipeline trigger)
- Canada-par series kept as labeled **market context** only

### Checkpoint starters
- `run_curves.py`: **`GROUP = 5`**, path → root `sample_curve.xlsx`
- `analyse_results.py`: **self-contained** VoNB ($) / VoNB % / Net CSM % / CaPM (pasted helpers; no `pipeline/` import). Prints TOTAL + by plan code; writes `exports/profitability_summary_*.xlsx` when Slope CSVs exist. Still needs TVFI `slope_api.py` to run live.

### Report draft (Wave 4)
- `docs/report/TVFI_Group5_Report_Draft.md` — exec summary, ops process, trigger/col H/RF decisions, profitability formulas (numeric cells pending Slope)
- `docs/report/presentation_outline.md` — ~8-slide outline

### Decisions documented (memos)
| Memo | Decision |
|---|---|
| `docs/memos/column-h-liquidity-premium.md` | **`hold_latest_publication`** for col H |
| `docs/memos/daily-risk-free-source.md` | **BoC zero-coupon CSV** as primary RF source (own ~2-week lag) |
| `docs/memos/boc-rf-lag-freshness.md` | BoC URL, lag labeling, intake commands |
| `docs/memos/trigger-calibration.md` | Single primary: weighted \|Δ\| T ≥ **25 bp** (years 1–30); bucket diagnostic 40 bp |
| `docs/memos/profitability-formula-map.md` | VoNB % / Net CSM % / CaPM formulas (+ local `pipeline/profitability_formulas.py`) |

### Sam / TVFI feedback absorbed
Progress update **87/100**. Binding: defend col H, pick one RF source, curve-only trigger (no Slope / no PV-liability), one trigger level, metrics VoNB / Net CSM / CaPM.

---

## What needs review

Team / industry partner should explicitly review and sign off on:

1. **Column H policy** — Is `hold_latest_publication` acceptable given the MoM analysis (~4–6 bp typical |ΔH|; RF dominates between pubs)?  
   → `docs/memos/column-h-liquidity-premium.md`

2. **Daily RF source** — Is BoC zero-coupon CSV the right primary despite ~2-week lag? (Valet benchmarks only as freshness overlay.)  
   → `docs/memos/daily-risk-free-source.md` · `docs/memos/boc-rf-lag-freshness.md`

3. **Trigger threshold** — Team set weighted |Δ| T ≥ **25 bp** + bucket diagnostic **40 bp** (2-year sample ~24 comparisons; full archive ~3.3 fires/year at 25 bp). Confirm ops-reasonable with TVFI.  
   → `docs/memos/trigger-calibration.md` + `python3 -m pipeline.backtest_trigger`

4. **Extrapolation past 30y** — When BoC zeros feed the builder, confirm how we extend to Slope durations 1–100 (builder currently mirrors Fiera ultimate behavior).

5. **Dashboard KPI contract** — Confirm Overview should stay on implied − pricing; Canada-par remains context-only. Optionally prefer snapshot `metrics_computed` over re-deriving deltas in JS.

6. **Checkpoint hygiene** — Confirm `GROUP = 5` and root `sample_curve.xlsx` before any real Slope submission. Dry runs still require TVFI’s `slope_api.py` (not in this repo).

7. **Profitability paste** — Confirm VoNB / Net CSM / CaPM transcription in `analyse_results.py` (esp. PA1 CaPM uses `L/12` per-cell) against first real Slope exports.  
   → `docs/memos/profitability-formula-map.md`

8. **Report draft** — Trim/fill before Word export (≤10 pages); numeric profitability section waits on Slope.  
   → `docs/report/TVFI_Group5_Report_Draft.md`

---

## Valet lag bridge (2026-11-20) — default during BoC lag

Live overlay for the ~2-week BoC zero publication lag (does **not** replace BoC as primary):

- Intake: `pipeline/valet_intake.py` → `data/risk_free/valet/`
- Bridge: `pipeline/lag_bridge.py` — keyed shift of held BoC annual zeros by Valet Δ
- Wired into `--rebuilt` by default; disable with `--no-lag-bridge`
- Memo: `docs/memos/valet-lag-bridge.md`

### Experimental: Ridge / PCA nowcast (2026-11-20)

Statistical horse-race vs keyed shift — **not** default yet:

- Code: `pipeline/lag_bridge_mlr.py` (`--train --backtest --predict`)
- Memo: `docs/memos/lag-bridge-ridge-pca.md`
- First back-test (~1y BoC panel, walk-forward): Ridge mean RMSE **~1.0 bp** vs hold **~3.4 bp**; PCA nearly identical (~1.05 bp). Live prediction ≈ keyed shift (~2.4 bp RMSE vs shift).

## Experimental: IoA annual par bootstrap (2026-11-20)

Pedagogy / Fiera RF check — **not** the lag fill (use Valet bridge above).

- Code: `pipeline/bootstrap.py` (`python3 -m pipeline.bootstrap --compare`)
- Memo: `docs/memos/experimental-par-bootstrap.md`
- Finding: bootstrapping Fiera **Canada par** recovers construction **col E** exactly (0 bp)

## Partner review pack (2026-11-20)

Ready to send: `docs/partner-review/2026-11-20/`

- Sign-off checklist (H / RF / trigger 25+40) in that folder’s `README.md`
- Memos copied under `memos/`
- Back-test at 25 bp: `artifacts/backtest_trigger_25bp.txt` (23/84 ≈ 3.29/yr)
- Slope-ready baseline + implied workbooks under `slope_inputs/` (unique names; Fiera-validated J ≈ 0 bp)
- Latest rebuilt snapshot in pack: **TRIGGERED** (T ≈ 25.24 bp)

## What’s next

### Wave 5 (blocked / finalize)
1. **TVFI sign-off** on review pack items 1–3 (H / RF / trigger).
2. **Slope checkpoint** — Run baseline + implied from `docs/handoff/.../slope_inputs/` via `run_curves.py` / `analyse_results.py` once TVFI confirms model path; reconcile CSV keys vs formula map.
3. **Fill report §5** — Baseline vs implied VoNB / Net CSM / CaPM once Slope exports exist; attach path into snapshot (`profitability.status=export_found`), then parse metrics to flip `available`.
4. **Word report + presentation** — After Slope numbers (deferred for now).

### Blocked on TVFI
- Explicit memo sign-off (H / RF / 25 bp trigger).
- Real Slope model run / confirmation of `slope_api.py` path for profitability numbers.
- Meeting with Nathan (approved) on codebase / docs expectations if still needed.

---

## Quick commands

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.boc_intake
python3 -m pipeline.curve_builder --rf fiera --validate
python3 -m pipeline.curve_builder --rf boc
python3 -m pipeline.backtest_trigger
python3 -m pipeline.build_monitor_snapshot --rebuilt          # auto-prefers BoC RF
python3 -m pipeline.build_monitor_snapshot --rebuilt --rf fiera  # force fixture RF
cd "Dashboard UI/Group5_Monitoring_Dashboard" && python3 -m http.server 8000
# open http://127.0.0.1:8000/ in Brave
```

---

## Status snapshot

| Area | State |
|---|---|
| Fiera archive + extracts | Done |
| Dashboard + snapshot handoff | Done |
| Col H / RF / trigger memos | Done — **review pack ready** (`docs/partner-review/2026-11-20/`) |
| Col-J builder (fixture RF) | Done |
| BoC daily intake | Done (live download verified) |
| Snapshot driven by rebuilt J | Done (`--rebuilt` **defaults to BoC RF**) |
| Decision log + profitability hooks | Done (`profitability=not_run` until Slope) |
| Profitability in `analyse_results.py` | Done (paste) — **blocked** on `slope_api.py` for live run |
| Report / presentation draft | Done — finalize after Slope numbers |
| Slope dry run | **Blocked** on `slope_api.py` |
