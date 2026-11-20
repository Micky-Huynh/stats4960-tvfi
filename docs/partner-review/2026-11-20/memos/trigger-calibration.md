# Memo: Curve-Only Trigger Calibration (weighted revision)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Subject:** Team-adjusted thresholds — weighted T ≥ 25 bp primary; bucket ≥ 40 bp diagnostic  
**Inputs:** `data/fiera/extracted/history/liquidity_premium_by_month.csv` (85 Fiera months, 2019-10 → 2026-10); team review vs past ~2 years  
**Supersedes:** memo of 2026-11-14 (weighted T ≥ 35 bp; bucket diagnostic 75 bp)

---

## 1. Decision

**Primary rule (drives `overall_status`):** start a Slope profitability test when

```
T = Σ_{t=1..30} w_t · |r_t(Current) − r_t(Pricing)|  ≥  25 bp
```

where `r_t` is the column-J annual forward rate at year `t` and `w_t` is the per-year weight below.

| Years | Total weight | Per year |
|-------|--------------|----------|
| 1–5 | 5% | 1% |
| 6–10 | 10% | 2% |
| 11–15 | 15% | 3% |
| 16–20 | 25% | 5% |
| 21–25 | 25% | 5% |
| 26–30 | 20% | 4% |

**Diagnostics (reported, do not drive overall status):**

| Measure | Threshold | Role |
|---------|-----------|------|
| Largest per-bucket mean \|Δ\| | **40 bp** | Flags a move concentrated in one part of the curve |
| \|2s10s twist\| | 40 bp | Shape context |
| Signed sum S = Σ w_t · Δr_t | none | Direction of the move |

Sam's constraint is unchanged: **one** trigger (weighted T) starts a Slope profitability test. Bucket stays diagnostic even at the tighter 40 bp level.

---

## 2. Why these levels (team 2026-11-20)

Team compared candidate thresholds against the past ~2 years of data and landed on:

- **25 bp** for the weighted-average primary  
- **40 bp** for individual bucket movements (diagnostic)

They noted the 2-year window produced only **~24 comparisons**, which is thin relative to the full 84-interval Fiera archive back-test. Treat the 2-year check as an ops sanity sample, not a replacement for the full-history fire table below.

On the full archive (84 intervals), T ≥ 25 bp fires **23** times (~**3.3 / year**), vs 12 fires (~1.7 / year) at the prior 35 bp choice.

---

## 3. Why weighted (unchanged rationale)

Secured Retirement pays income decades out, so its benefit rates depend mostly on rates at 16–30 years. The equal-weight mean over nine display maturities gave the 1, 2 and 3 year points a third of the vote. The weighted measure gives years 16–30 70% of the weight and years 1–5 5%.

---

## 4. Historical distribution (84 intervals)

| Measure | min | p50 | p90 | max |
|---------|-----|-----|-----|-----|
| T (weighted \|Δ\|) bp | 4.6 | 19.5 | 37.9 | 98.2 |
| Largest bucket mean \|Δ\| bp | 7.8 | 35.1 | 74.6 | 141.4 |
| Old mean \|Δ\| bp | 4.2 | 19.0 | 43.2 | 67.8 |

| X (bp) | Fires / 84 | ≈ / year |
|--------|------------|----------|
| **25 (chosen)** | **23** | **3.29** |
| 30 | 18 | 2.57 |
| 35 (prior) | 12 | 1.71 |
| 40–50 | 7 | 1.00 |
| 60 | 3 | 0.43 |

### Primary fires at X = 25 (23) — re-run 2026-11-20

| as_of | T | S (signed) | Largest bucket mean \|Δ\| | Bucket |
|-------|---|------------|---------------------------|--------|
| 2020-01-31 | 37.5 | −37.5 | 54.3 | 6–10 |
| 2020-03-31 | 98.2 | +98.2 | 120.1 | 21–25 |
| 2020-04-30 | 86.2 | −86.2 | 141.4 | 26–30 |
| 2020-06-30 | 39.0 | −39.0 | 50.6 | 21–25 |
| 2020-10-30 | 35.9 | +35.9 | 86.1 | 26–30 |
| 2021-02-26 | 37.9 | +33.5 | 99.6 | 26–30 |
| 2021-03-31 | 28.5 | +24.4 | 40.6 | 16–20 |
| 2021-06-30 | 27.0 | −26.2 | 40.2 | 11–15 |
| 2021-10-29 | 25.3 | +2.6 | 48.8 | 26–30 |
| 2022-01-31 | 50.6 | +50.6 | 56.3 | 16–20 |
| 2022-04-29 | 65.7 | +65.7 | 95.0 | 26–30 |
| 2022-07-29 | 32.5 | −32.5 | 74.6 | 6–10 |
| 2022-10-31 | 33.4 | +20.6 | 48.5 | 16–20 |
| 2022-11-30 | 55.1 | −55.1 | 79.2 | 26–30 |
| 2023-01-31 | 33.8 | −31.6 | 52.7 | 1–5 |
| 2023-02-28 | 30.9 | +30.9 | 57.7 | 26–30 |
| 2023-09-29 | 55.7 | +55.7 | 103.0 | 26–30 |
| 2023-11-30 | 56.1 | −56.1 | 66.2 | 11–15 |
| 2023-12-29 | 30.2 | −30.2 | 55.2 | 1–5 |
| 2024-04-30 | 28.7 | +27.1 | 38.7 | 16–20 |
| 2024-11-29 | 26.2 | −20.9 | 37.8 | 16–20 |
| 2026-03-31 | 30.3 | +30.3 | 45.8 | 1–5 |
| 2026-07-31 | 36.2 | +36.2 | 41.3 | 21–25 |

Bucket ≥ 40 with T < 25 (diagnostic-only, does **not** fire): **14** months — see `docs/partner-review/2026-11-20/artifacts/backtest_trigger_25bp.txt`.

---

## 5. Trade-offs and caveats

- T uses absolute values, so opposite moves do not cancel, but T has no direction. The signed sum S is shown beside it for that reason.
- The weights are the team's judgment. An earlier look at the Example Profitability Model cash flows suggests the long end (30 years and beyond) carries more of the sensitivity than the table gives it. A sensitivity run with model-derived weights is planned.
- T ignores rates beyond year 30, where the curve is extrapolated.
- The bucket check stays a diagnostic. Letting it fire on its own would break the one-trigger rule.
- 2-year ops check (~24 pairs) is sparse; re-calibrate when daily curves are available.
- Calibrated on monthly publications over a period dominated by COVID and the 2022–23 hikes.

---

## 6. Model testing note

When testing against the **actual** Slope / profitability model (not just the curve-only trigger), use the **Fiera curve workbooks** under `data/fiera/` as the curve inputs (same archive used for construction / col-J history).

---

## 7. Implementation

| File | Change |
|------|--------|
| `pipeline/metrics.py` | Weight table + T / S / bucket helpers |
| `pipeline/trigger.py` | Primary = weighted T @ **25 bp**; bucket diagnostic @ **40 bp**; twist + signed diagnostics |
| `pipeline/interval_metrics.py` | Weighted pair metrics over years 1..30 |
| `pipeline/backtest_trigger.py` | Prints T / Layer-2 fire tables |
| `docs/memos/trigger-calibration.md` | This memo |

Reproduce:

```bash
python3 -m pipeline.backtest_trigger
python3 -m pipeline.build_monitor_snapshot --rebuilt
```
