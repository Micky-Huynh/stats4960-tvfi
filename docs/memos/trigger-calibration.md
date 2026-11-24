# Memo: Curve-Only Trigger Calibration (weighted revision)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Subject:** PV-basis liability weights + T ≥ 25 bp primary; bucket ≥ 40 bp diagnostic  
**Inputs:** `data/fiera/extracted/history/liquidity_premium_by_month.csv` (85 Fiera months, 2019-10 → 2026-10); post-Nathan / Ethan weight flip (2026-11-20)  
**Supersedes:** memo of 2026-11-20 morning (long-end weights; T ≥ 25 bp; bucket 40 bp)

---

## 1. Decision

**Primary rule (drives `overall_status`):** start a Slope profitability test when

```
T = Σ_{t=1..30} w_t · |r_t(Current) − r_t(Pricing)|  ≥  25 bp
```

where `r_t` is the column-J annual forward rate at year `t` and `w_t` is the per-year weight below.

| Years | Total weight | Per year | Relative importance |
|-------|--------------|----------|---------------------|
| 1–5 | **30%** | 6% | High |
| 6–10 | **25%** | 5% | High |
| 11–15 | **20%** | 4% | Medium–High |
| 16–20 | **15%** | 3% | Medium |
| 21–25 | **5%** | 1% | Low |
| 26–30 | **5%** | 1% | Low |

Present-value / short-end basis (Sawyer suggestion; Ethan agreed post-Nathan). Years 1–10 carry **55%** of T; years 21–30 only **10%**.

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

On the full archive (84 intervals) with **PV weights**, T ≥ 25 bp fires **27** times (~**3.9 / year**). (Under the prior long-end weight table the same 25 bp bar fired 23 times ≈ 3.3 / year.)

---

## 3. Why weighted — PV / short-end basis (2026-11-20)

Post-Nathan team sync flipped the liability weights from a long-end / pension-heavy table (years 16–30 ≈ 70%) to a **present-value basis**: short tenors dominate the monitoring trigger because near-term cash flows and discounting sensitivity matter more for the insurer metrics Nathan cares about. Equal-weight mean over nine display maturities still over-weights or under-weights arbitrarily; the PV table is explicit judgment (1–5 High … 26–30 Low) and sums to 100%.

---

## 4. Historical distribution (84 intervals) — PV weights

| Measure | min | p50 | p90 | max |
|---------|-----|-----|-----|-----|
| T (weighted \|Δ\|) bp | 3.4 | 20.1 | 43.8 | 70.5 |
| Largest bucket mean \|Δ\| bp | 7.8 | 35.1 | 74.6 | 141.4 |
| Equal-weight mean \|Δ\| bp | 4.1 | 19.0 | 43.2 | 67.8 |

| X (bp) | Fires / 84 | ≈ / year |
|--------|------------|----------|
| **25 (chosen)** | **27** | **3.86** |
| 30 | 16 | 2.29 |
| 35 | 12 | 1.71 |
| 40 | 10 | 1.43 |
| 50 | 4 | 0.57 |
| 60 | 3 | 0.43 |

### Primary fires at X = 25 (27) — re-run 2026-11-24 (PV weights)

| as_of | T | S (signed) | Largest bucket mean \|Δ\| | Bucket |
|-------|---|------------|---------------------------|--------|
| 2020-01-31 | 43.8 | −43.8 | 54.3 | 6–10 |
| 2020-03-31 | 70.5 | +70.5 | 120.1 | 21–25 |
| 2020-04-30 | 60.7 | −60.7 | 141.4 | 26–30 |
| 2020-06-30 | 27.6 | −27.6 | 50.6 | 21–25 |
| 2021-02-26 | 35.4 | +32.4 | 99.6 | 26–30 |
| 2021-03-31 | 28.8 | +27.0 | 40.6 | 16–20 |
| 2021-06-30 | 25.2 | −20.1 | 40.2 | 11–15 |
| 2021-10-29 | 25.9 | +4.8 | 48.8 | 26–30 |
| 2022-01-31 | 49.3 | +49.3 | 56.3 | 16–20 |
| 2022-03-31 | 31.3 | +25.0 | 76.4 | 1–5 |
| 2022-04-29 | 61.0 | +61.0 | 95.0 | 26–30 |
| 2022-06-30 | 27.6 | +27.6 | 41.9 | 1–5 |
| 2022-07-29 | 48.1 | −48.1 | 74.6 | 6–10 |
| 2022-08-31 | 27.4 | +23.3 | 57.7 | 1–5 |
| 2022-10-31 | 27.3 | +24.1 | 48.5 | 16–20 |
| 2022-11-30 | 47.4 | −47.4 | 79.2 | 26–30 |
| 2022-12-30 | 28.8 | +28.8 | 42.0 | 6–10 |
| 2023-01-31 | 38.2 | −37.7 | 52.7 | 1–5 |
| 2023-02-28 | 28.4 | +28.4 | 57.7 | 26–30 |
| 2023-09-29 | 47.0 | +47.0 | 103.0 | 26–30 |
| 2023-11-30 | 59.6 | −59.6 | 66.2 | 11–15 |
| 2023-12-29 | 41.4 | −41.4 | 55.2 | 1–5 |
| 2024-01-31 | 26.7 | +26.2 | 47.6 | 11–15 |
| 2024-04-30 | 32.3 | +31.9 | 38.7 | 16–20 |
| 2024-11-29 | 26.3 | −25.0 | 37.8 | 16–20 |
| 2026-03-31 | 31.9 | +31.9 | 45.8 | 1–5 |
| 2026-07-31 | 32.0 | +32.0 | 41.3 | 21–25 |

Bucket ≥ 40 with T < 25 (diagnostic-only, does **not** fire): **10** months — see `docs/partner-review/2026-11-20/artifacts/backtest_trigger_25bp.txt`.

---

## 5. Trade-offs and caveats

- T uses absolute values, so opposite moves do not cancel, but T has no direction. The signed sum S is shown beside it for that reason.
- The weights are the team's PV-basis judgment (post-Nathan / Ethan). A sensitivity run vs Slope model-derived weights is still planned if cash-flow exposures differ materially.
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
