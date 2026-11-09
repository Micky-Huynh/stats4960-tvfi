# Project status — TVFI yield-curve monitoring

**Course:** STATS 4960 · Group 5 × Thames Valley Financial Inc.  
**Repo:** [Micky-Huynh/stats4960-tvfi](https://github.com/Micky-Huynh/stats4960-tvfi)  
**Last updated:** 2026-11-09

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
- **Calibrated trigger** (`pipeline/trigger.py`): primary rule mean |Δ| ≥ **35 bp** (~2 fires/year). Back-test: `python3 -m pipeline.backtest_trigger`

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
| `docs/memos/trigger-calibration.md` | Single primary: mean \|Δ\| ≥ **35 bp** |
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

3. **Trigger threshold** — Is mean |Δ| ≥ **35 bp** (~2 fires/year on Fiera monthly history) ops-reasonable?  
   → `docs/memos/trigger-calibration.md` + `python3 -m pipeline.backtest_trigger`

4. **Extrapolation past 30y** — When BoC zeros feed the builder, confirm how we extend to Slope durations 1–100 (builder currently mirrors Fiera ultimate behavior).

5. **Dashboard KPI contract** — Confirm Overview should stay on implied − pricing; Canada-par remains context-only. Optionally prefer snapshot `metrics_computed` over re-deriving deltas in JS.

6. **Checkpoint hygiene** — Confirm `GROUP = 5` and root `sample_curve.xlsx` before any real Slope submission. Dry runs still require TVFI’s `slope_api.py` (not in this repo).

7. **Profitability paste** — Confirm VoNB / Net CSM / CaPM transcription in `analyse_results.py` (esp. PA1 CaPM uses `L/12` per-cell) against first real Slope exports.  
   → `docs/memos/profitability-formula-map.md`

8. **Report draft** — Trim/fill before Word export (≤10 pages); numeric profitability section waits on Slope.  
   → `docs/report/TVFI_Group5_Report_Draft.md`

---

## What’s next

### Wave 5 (blocked / finalize)
1. **Slope checkpoint** — Obtain `slope_api.py` from TVFI; dry-run `run_curves.py` / `analyse_results.py`; reconcile CSV keys vs formula map; submit baseline + implied workbooks.
2. **Fill report §5** — Baseline vs implied VoNB / Net CSM / CaPM once Slope exports exist; attach profitability into snapshot (`profitability.status=available`).
3. **Word report + presentation** — Export draft to Times New Roman 12pt / 1" margins; finalize slides from `docs/report/presentation_outline.md`.

### Blocked on TVFI
- **`slope_api.py` / dummy Slope** — Required for dry runs and real profitability numbers.
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
| Col H / RF / trigger memos | Done — **needs review** |
| Col-J builder (fixture RF) | Done |
| BoC daily intake | Done (live download verified) |
| Snapshot driven by rebuilt J | Done (`--rebuilt` **defaults to BoC RF**) |
| Decision log + profitability hooks | Done (`profitability=not_run` until Slope) |
| Profitability in `analyse_results.py` | Done (paste) — **blocked** on `slope_api.py` for live run |
| Report / presentation draft | Done — finalize after Slope numbers |
| Slope dry run | **Blocked** on `slope_api.py` |
