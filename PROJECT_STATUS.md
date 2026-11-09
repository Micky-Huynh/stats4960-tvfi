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

### Monitoring pipeline (`pipeline/`)
- Fiera history → curve metrics → trigger → `monitor_snapshot.json`
- Writes canonical snapshot to `data/monitor/` and copies into the dashboard folder
- Latest fixture run: `Fiera-20261030-01`, status **`NO_TRIGGER`**, mean |Δ| ≈ **15.5 bp** (implied − pricing)
- **Column J builder** (`pipeline/curve_builder.py`): fixture RF + hold-latest H + static params; validates vs Fiera published J (~0 bp error). Output: `data/curves/illiquid_col_j_2026-10-30.xlsx`
- **Calibrated trigger** (`pipeline/trigger.py`): primary rule mean |Δ| ≥ **35 bp** (~2 fires/year historically). Back-test CLI: `python3 -m pipeline.backtest_trigger`

### Dashboard
- Static prototype: `Dashboard UI/Group5_Monitoring_Dashboard/`
- Overview KPIs use **implied − pricing** (aligned with pipeline trigger)
- Canada-par series kept as labeled **market context** only

### Checkpoint starters
- `run_curves.py`: **`GROUP = 5`**, path → root `sample_curve.xlsx`
- README sample-path corrected

### Decisions documented (memos)
| Memo | Decision |
|---|---|
| `docs/memos/column-h-liquidity-premium.md` | **`hold_latest_publication`** for col H |
| `docs/memos/daily-risk-free-source.md` | **BoC zero-coupon CSV** as primary RF source (own ~2-week lag) |
| `docs/memos/trigger-calibration.md` | Single primary: mean \|Δ\| ≥ **35 bp** |
| `docs/memos/profitability-formula-map.md` | VoNB % / Net CSM % / CaPM formulas + `pipeline/profitability_formulas.py` stubs |

### Sam / TVFI feedback absorbed
Progress update **87/100**. Binding: defend col H, pick one RF source, curve-only trigger (no Slope / no PV-liability), one trigger level, metrics VoNB / Net CSM / CaPM.

---

## What needs review

Team / industry partner should explicitly review and sign off on:

1. **Column H policy** — Is `hold_latest_publication` acceptable given the MoM analysis (~4–6 bp typical |ΔH|; RF dominates between pubs)?  
   → `docs/memos/column-h-liquidity-premium.md`

2. **Daily RF source** — Is BoC zero-coupon CSV the right primary despite ~2-week lag? (Valet benchmarks only as freshness overlay.)  
   → `docs/memos/daily-risk-free-source.md`

3. **Trigger threshold** — Is mean |Δ| ≥ **35 bp** (~2 fires/year on Fiera monthly history) ops-reasonable?  
   → `docs/memos/trigger-calibration.md` + `python3 -m pipeline.backtest_trigger`

4. **Extrapolation past 30y** — When BoC zeros feed the builder, confirm how we extend to Slope durations 1–100 (builder currently mirrors Fiera ultimate behavior on fixture days).

5. **Dashboard KPI contract** — Confirm Overview should stay on implied − pricing; Canada-par remains context-only. Optionally prefer snapshot `metrics_computed` over re-deriving deltas in JS.

6. **Checkpoint hygiene** — Confirm `GROUP = 5` and root `sample_curve.xlsx` before any real Slope submission. Dry runs still require TVFI’s `slope_api.py` (not in this repo).

7. **Profitability formula map** — Confirm VoNB / Net CSM / CaPM transcription (esp. PA1 CaPM uses `L/12` per-cell) before pasting into `analyse_results.py`.  
   → `docs/memos/profitability-formula-map.md`

---

## What’s next

### Wave 3 (build)
1. **BoC intake** — Parse zero-coupon CSV → annual RF 1–30 → feed `curve_builder` with hold-latest H; write dated construction records + Slope workbooks.
2. **Wire snapshot to builder** — Rebuilt (daily/fixture) column J drives implied curve + trigger; stop relying only on archived publication-J pairs.
3. **Slope checkpoint** — Obtain `slope_api.py` from TVFI; paste VoNB / Net CSM / CaPM into `analyse_results.py` (do **not** import `pipeline/` in the checkpoint zip); submit baseline + implied workbooks.
4. **Richer snapshot** — Include decision log + profitability summary when Slope has run.

### Deliverables (course / TVFI)
5. **Written report** — Trigger memo, profitability comparison (baseline vs implied), operational process doc (≤10 pages body).
6. **Final presentation** — Recommendation to TVFI.

### Blocked on TVFI
- **`slope_api.py` / dummy Slope** — Required for dry runs and real profitability numbers.
- Meeting with Nathan (approved) on codebase / docs expectations if still needed.

---

## Quick commands

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.curve_builder --validate
python3 -m pipeline.backtest_trigger
python3 -m pipeline.build_monitor_snapshot
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
| BoC daily intake | Next |
| Snapshot driven by rebuilt J | Next |
| Slope dry run + profitability in scripts | Blocked on `slope_api.py` |
| Report / presentation | Not started |
