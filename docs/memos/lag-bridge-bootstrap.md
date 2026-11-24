# Memo: Predict → IoA bootstrap lag remedy (three tracks)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Status:** **Experimental lag remedy** — parallel tracks; keyed Valet shift remains `--rebuilt` default  
**Code:** `pipeline/lag_bridge_bootstrap.py`

---

## 1. What this does

For any calendar interval (typically the BoC zero publish-lag window), run **three separate** pipelines:

| Track | Predicted zeros | Then |
|-------|-----------------|------|
| **ridge** | Multi-output Ridge Valet → BoC annual zeros | IoA/CM1 bootstrap (zeros → par → DF / zero / 1y forward) |
| **pca** | Interpolate Valet anchors → dense curve, **PCA-project** onto historical BoC eigenspace | Same bootstrap |
| **pca_ridge** | PCA factors + Ridge (Valet → scores → reconstruct) | Same bootstrap |

Each track writes its own artifacts. Interval is user-chosen (`--from` / `--to` or `--lag-days`).

---

## 2. Why bootstrap after predict

The nowcast models output **annual-effective zeros**. The IoA annual-par bootstrap turns those into a full **par / DF / forward** strip consistent with CM1 identities — useful for inspection, Slope-adjacent RF packaging (`--build-j`), and documenting a complete rate curve during the lag — without claiming a CIA-approved Fiera-day forecast.

---

## 3. Run

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
# Train nowcast models if needed
python3 -m pipeline.lag_bridge_mlr --train

# Full lag window from BoC rf_asof → today (default)
python3 -m pipeline.lag_bridge_bootstrap

# Explicit interval
python3 -m pipeline.lag_bridge_bootstrap --from 2026-11-04 --to 2026-11-19

# Last N calendar days (clamped to rf_asof)
python3 -m pipeline.lag_bridge_bootstrap --lag-days 16

# Only latest Valet day + rebuild Slope col J from each bootstrapped RF
python3 -m pipeline.lag_bridge_bootstrap --latest-only --build-j

# Multi-sheet Excel of all predicted zeros + IoA bootstrap curves
python3 -m pipeline.lag_bridge_bootstrap --xlsx-only --from 2026-11-04 --to 2026-11-19
```

Outputs under `data/curves/lag_bootstrap/`:

```
lag_bootstrap/
  ridge/{YYYY-MM-DD}.json + _bootstrap.csv + latest.json
  pca/...
  pca_ridge/...
  summary_{from}_to_{to}.json
  lag_bootstrap_curves_{from}_to_{to}.xlsx   # dated workbook
  lag_bootstrap_curves.xlsx                  # stable alias (dashboard download)
```

Excel sheets: `Notes`, `Summary`, `Predicted_Zeros`, `Implied_Par`, `Bootstrap`,
`Spot_Wide_Latest`, `Fwd_Wide_Latest`, `Spot_Wide_AllDays`. Dashboard **Export Excel**
downloads the stable alias when served from the TVFI project root.

---

## 4. Relation to other layers

| Layer | Role |
|-------|------|
| BoC zeros | Primary RF at `rf_asof` |
| Keyed Valet **shift** | Production default during lag (`--rebuilt`) |
| Ridge / PCA nowcast | Predict dense zeros from live Valet |
| **This module** | Bootstrap each prediction into a full rate curve over a chosen interval |
| Fiera H | Still held between monthly pubs |

---

## 5. Backtest (predict → IoA bootstrap vs later BoC)

```bash
python3 -m pipeline.lag_bootstrap_backtest
# → data/curves/lag_bootstrap_backtest_results.json
```

Walk-forward (train only on dates before *t*; score day *t* vs published BoC).  
Freshness is **Valet business-daily**, not clock-hourly.

| Track | Boot-zero mean RMSE | Hold baseline | Beats hold | Verdict |
|-------|---------------------|---------------|------------|---------|
| **ridge** | **0.95 bp** | 3.41 bp | 86% of days | **PASS** |
| **pca_ridge** | **0.99 bp** | 3.41 bp | 87% of days | **PASS** |
| **pca** (interp→project) | 16.80 bp | 3.41 bp | 0% | **FAIL** |

- Bootstrap round-trip of truth zeros ≈ 0 bp (identity check).  
- Peak max|Δ| ridge ≈ 9 bp ≪ 25 bp trigger diagnostic.  
- Present **ridge** (or pca_ridge) as the witchcraft; do **not** sell the bare PCA-curve track.

### Per-maturity standard error (MoE)

```bash
python3 -m pipeline.lag_error_report --methods ridge,pca_ridge
# → data/curves/lag_error_report.json
# → data/curves/lag_error_report_by_maturity.csv
```

Walk-forward residuals at each tenor year 1…30 (n≈216 days).  
**SE** = sample sd of (boot − BoC) / √n — standard error of the **mean** residual at that point.  
**P90|e|** ≈ 90% conformal half-width (pointwise MoE band). Daily lag-bridge MoE — not clock-hourly.

**Ridge (key tenors, bp):**

| Year | Bias | SD | SE | RMSE | P90\|e\| |
|-----:|-----:|---:|---:|-----:|-------:|
| 1 | −0.78 | 2.51 | 0.171 | 2.62 | 4.02 |
| 2 | −0.07 | 1.39 | 0.095 | 1.39 | 2.38 |
| 5 | −0.48 | 0.86 | 0.059 | 0.99 | 1.47 |
| 10 | 0.33 | 1.01 | 0.069 | 1.06 | 1.73 |
| 20 | −0.08 | 0.92 | 0.063 | 0.92 | 1.56 |
| 30 | −0.19 | 0.88 | 0.060 | 0.90 | 1.34 |

Mean SE across all 30 tenors ≈ **0.06 bp**. Pooled P90|e| ≈ **1.5 bp**. Front end (1y) is noisiest; belly/long ≈ 0.05–0.07 SE.

---

## 6. Caveats

- Requires trained pickles from `lag_bridge_mlr` (`data/models/`, gitignored).  
- PCA-only track uses Valet **interpolation** then eigenspace projection — not the same as pca_ridge. **Fails** the backtest.  
- Bootstrapped forwards are RF-side; illiquid col J still needs held H (`--build-j`).  
- Not wired as `--rebuilt` default until partner sign-off.
