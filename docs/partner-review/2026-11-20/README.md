# TVFI partner review pack — 2026-11-20

**From:** STATS 4960 Group 5  
**To:** Sam Guan / Nathan Phelps (TVFI)  
**Repo:** https://github.com/Micky-Huynh/stats4960-tvfi  
**Local:** `/Users/mickle/Desktop/STATS4960/TVFI`

Please review and **explicitly sign off** (or request changes) on the three decisions below. Everything else in this folder is supporting evidence and Slope-ready curve inputs.

---

## Sign-off checklist

| # | Decision | Ask | Memo |
|---|----------|-----|------|
| 1 | **Column H** | Is `hold_latest_publication` acceptable between monthly Fiera pubs? | `memos/column-h-liquidity-premium.md` |
| 2 | **Daily RF** | Is BoC zero-coupon CSV the sole primary RF despite ~2-week lag? | `memos/daily-risk-free-source.md` · `memos/boc-rf-lag-freshness.md` |
| 3 | **Trigger** | Confirm weighted **T ≥ 25 bp** primary; bucket **40 bp** diagnostic only (does not fire Slope alone) | `memos/trigger-calibration.md` · `artifacts/backtest_trigger_25bp.txt` |

Also confirm when convenient (not blockers for memo pack):

4. Extrapolation past 30y for Slope durations 1–100 (builder mirrors Fiera ultimate today)  
5. Dashboard KPIs stay on implied − pricing (Canada-par = context only)  
6. Checkpoint: `GROUP = 5`; unique `.xlsx` curve names; formulas in `analyse_results.py`

Reply with approve / change for items 1–3.

---

## What’s in this folder

```
memos/           Decision memos (H, RF, lag, trigger)
artifacts/       Back-test at 25 bp + latest snapshot / decision / construction record
slope_inputs/    Slope-ready Sheet1 workbooks (Policy Duration + Forward Rate, 1–100)
```

### Latest monitor result (25 bp rule)

- Snapshot: `Fiera-20261030-R01` / **TRIGGERED**
- Pricing: 2026-09-29 → observation 2026-10-30  
- Metrics: **T ≈ 25.24 bp**, S ≈ −24.5, bucket ≈ 43.5 (diagnostic), twist ≈ 14.7  
- RF: BoC zeros (`rf_as_of` 2026-11-04), H held from Fiera 2026-10-30

### Back-test (Fiera archive, 84 intervals)

- Primary T ≥ **25 bp**: **23 / 84** fires ≈ **3.29 / year**  
- Full table: `artifacts/backtest_trigger_25bp.txt`

---

## Slope inputs (ready when you run the model)

Built from the **Fiera archive / construction path** (not invented curves):

| File | Role |
|------|------|
| `slope_inputs/G5_baseline_Fiera_J_2026-10-30.xlsx` | Baseline col J from Fiera construction (validated ≈ 0 bp vs published J) |
| `slope_inputs/G5_implied_BoC_rf_2026-11-04_H_2026-10-30.xlsx` | Implied col J: BoC RF + held H (2026-10-30) |
| Matching `.csv` copies | Same rates for inspection |

**Layout:** `Sheet1` · `Policy Duration` 1–100 · `Forward Rate` as annual decimals.  
**Names are unique** so Slope will accept both in one checkpoint.  
Source Fiera monthlies live under `data/fiera/monthly_raw/` (85 months).

**Still needed from TVFI for live profitability numbers:** confirm we may use the local `slope_api.py` path / real model run. Group scripts: `run_curves.py` then `analyse_results.py` (`GROUP = 5`).

---

## Reproduce locally

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.backtest_trigger
python3 -m pipeline.curve_builder --rf fiera --validate
python3 -m pipeline.curve_builder --rf boc
python3 -m pipeline.build_monitor_snapshot --rebuilt
python3 -m pipeline.pre_submit
```

Pack path (shareable / for GitHub): `docs/partner-review/2026-11-20/`
