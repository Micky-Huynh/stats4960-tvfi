# Memo: Curve-Only Trigger Calibration (weighted revision)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-14  
**Subject:** Replace the equal-weight primary with a liability-weighted primary; keep one trigger  
**Inputs:** `data/fiera/extracted/history/liquidity_premium_by_month.csv` (85 Fiera months, 2019-10 → 2026-10)  
**Supersedes:** memo of 2026-11-09 (mean |Δ| ≥ 35 bp over display maturities)

---

## 1. Decision

**Primary rule (drives `overall_status`):** start a Slope profitability test when

```
T = Σ_{t=1..30} w_t · |r_t(Current) − r_t(Pricing)|  ≥  35 bp
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
| Largest per-bucket mean \|Δ\| | 75 bp | Flags a move concentrated in one part of the curve |
| \|2s10s twist\| | 40 bp | Shape context |
| Signed sum S = Σ w_t · Δr_t | none | Direction of the move |

Sam's constraint is unchanged: one trigger starts a Slope profitability test.

---

## 2. Why change the primary

Secured Retirement pays income decades out, so its benefit rates depend mostly on rates at 16–30 years. The equal-weight mean over nine display maturities gave the 1, 2 and 3 year points a third of the vote. The weighted measure gives years 16–30 70% of the weight and years 1–5 5%.

---

## 3. Historical distribution (84 intervals)

| Measure | min | p50 | p90 | max |
|---------|-----|-----|-----|-----|
| T (weighted \|Δ\|) bp | 4.6 | 19.5 | 37.9 | 98.2 |
| Largest bucket mean \|Δ\| bp | 7.8 | 35.1 | 74.6 | 141.4 |
| Old mean \|Δ\| bp | 4.2 | 19.0 | 43.2 | 67.8 |

| X (bp) | Fires / 84 | ≈ / year |
|--------|------------|----------|
| 25 | 23 | 3.29 |
| 30 | 18 | 2.57 |
| **35 (chosen)** | **12** | **1.71** |
| 40–50 | 7 | 1.00 |
| 60 | 3 | 0.43 |

At 35 bp the rule fires in 2020 (5), 2021 (1), 2022 (3), 2023 (2) and 2026 (1), and never in 2024–2025.

### Primary fires at X = 35 (12)

| as_of | T | S (signed) | Largest bucket mean \|Δ\| | Bucket |
|-------|---|------------|---------------------------|--------|
| 2020-01-31 | 37.6 | −37.6 | 54.3 | 6–10 |
| 2020-03-31 | 98.2 | +98.2 | 120.1 | 21–25 |
| 2020-04-30 | 86.2 | −86.2 | 141.4 | 26–30 |
| 2020-06-30 | 39.0 | −39.0 | 50.6 | 21–25 |
| 2020-10-30 | 35.9 | +35.9 | 86.1 | 26–30 |
| 2021-02-26 | 37.9 | +33.5 | 99.6 | 26–30 |
| 2022-01-31 | 50.6 | +50.6 | 56.3 | 16–20 |
| 2022-04-29 | 65.7 | +65.7 | 95.0 | 26–30 |
| 2022-11-30 | 55.1 | −55.1 | 79.2 | 26–30 |
| 2023-09-29 | 55.7 | +55.7 | 103.0 | 26–30 |
| 2023-11-30 | 56.1 | −56.1 | 66.2 | 11–15 |
| 2026-07-31 | 36.2 | +36.2 | 41.3 | 21–25 |

---

## 4. Change from the previous rule

Nine months fire under both rules. Five months no longer fire (2022-03, 2022-07, 2022-08, 2023-01, 2023-12); these were short- and mid-curve moves. Three months now fire (2020-06, 2020-10, 2026-07); these were long-end moves the equal-weight mean diluted.

---

## 5. Trade-offs and caveats

- T uses absolute values, so opposite moves do not cancel, but T has no direction. The signed sum S is shown beside it for that reason.
- The weights are the team's judgment. An earlier look at the Example Profitability Model cash flows suggests the long end (30 years and beyond) carries more of the sensitivity than the table gives it. A sensitivity run with model-derived weights is planned.
- T ignores rates beyond year 30, where the curve is extrapolated.
- The bucket check stays a diagnostic. Letting it fire on its own would add one month on this history (2022-03, a short-end move), and would break the one-trigger rule.
- Calibrated on monthly publications over a period dominated by COVID and the 2022–23 hikes; re-calibrate when daily curves are available.

---

## 6. Implementation

| File | Change |
|------|--------|
| `pipeline/metrics.py` | Weight table + T / S / bucket helpers |
| `pipeline/trigger.py` | Primary = weighted T @ 35 bp; bucket + twist + signed diagnostics |
| `pipeline/interval_metrics.py` | Weighted pair metrics over years 1..30 |
| `pipeline/backtest_trigger.py` | Prints T / Layer-2 fire tables |
| `docs/memos/trigger-calibration.md` | This memo |

Reproduce:

```bash
python3 -m pipeline.backtest_trigger
python3 -m pipeline.build_monitor_snapshot
```
