# Memo: Curve-Only Trigger Calibration

**To:** TVFI / Group 5 project file  
**From:** Wave 2 E (STATS 4960 Group 5)  
**Date:** 2026-11-09  
**Subject:** Calibrate a single primary curve-only trigger (no Slope inside the trigger)  
**Inputs:** `data/fiera/extracted/history/liquidity_premium_by_month.csv` (85 Fiera months, 2019-10 → 2026-10); `pipeline/metrics.py`; `pipeline/fiera_history.DISPLAY_MATURITIES`

---

## 1. Decision

**Primary rule (drives `overall_status`):**

> Fire / start a Slope profitability test when the **mean absolute change** across display maturities  
> `|Δ|` averaged over `{1, 2, 3, 5, 7, 10, 15, 20, 30}` ≥ **35 bp** between consecutive monthly Fiera column-J curves (or pricing basis vs next implied).

**Diagnostics (reported, do not drive overall status):**

| Measure | Diagnostic threshold | Role |
|---------|----------------------|------|
| max \|Δ\| bp | 75 bp | Flags single-node / long-end spikes |
| \|2s10s twist\| bp | 40 bp | Shape / twist context |

Sam constraint: **one** trigger that starts a Slope profitability test; drop the redundant multi-rule / “second black-swan” OR logic.

---

## 2. Methodology

1. Load archived monthly **annual forward rates** (column J) from `liquidity_premium_by_month.csv`.
2. For each consecutive pair of publication dates, pick yields at `DISPLAY_MATURITIES`, convert to percent, and compute bp changes via `metrics.changes_bp`.
3. For each interval compute:
   - **mean \|Δ\| bp** — equal-weight average of absolute changes (primary candidate)
   - **duration-weighted mean \|Δ\| bp** — weights by maturity years (sensitivity check)
   - **max \|Δ\| bp** — largest absolute node move
   - **\|2s10s twist\| bp** — `|Δ10y − Δ2y|`
4. Tabulate fire rates across candidate thresholds; pick an ops-reasonable rate (few times per year in calm markets; denser in crises).

Reproduce with:

```bash
python3 -m pipeline.backtest_trigger
```

---

## 3. Historical distribution (84 intervals)

| Measure | min | p50 | p90 | max |
|---------|-----|-----|-----|-----|
| mean \|Δ\| bp | 4.2 | 19.0 | 43.2 | 67.8 |
| duration-weighted mean \|Δ\| | 5.5 | 20.8 | 44.3 | 89.9 |
| max \|Δ\| bp | 8.7 | 39.2 | 85.6 | 151.8 |
| \|2s10s twist\| bp | 0.2 | 14.3 | 40.5 | 92.2 |

### Fire-rate trade-off — primary candidate (mean \|Δ\|)

| Threshold (bp) | Fires / 84 | Rate | ≈ / year |
|----------------|------------|------|----------|
| 25 (old provisional) | 29 | 34.5% | 4.1 |
| 30 | 21 | 25.0% | 3.0 |
| **35 (chosen)** | **14** | **16.7%** | **2.0** |
| 40 | 12 | 14.3% | 1.7 |
| 50 | 5 | 6.0% | 0.7 |

Old provisional **OR of three** (parallel≥25 **or** max≥50 **or** twist≥30) fired **45/84 (53.6%, ≈6.4/yr)** — far too chatty for an ops trigger that launches Slope.

---

## 4. Why mean \|Δ\| @ 35 bp (not duration-weighted / max / twist)

1. **Already in the monitor path** (`abs_mean_change_bp`) and matches “parallel movement” language on the dashboard.
2. **Balances the curve** without letting a single noisy long end (often 20y/30y) dominate — max \|Δ\| alone fires ~4×/yr even at 50 bp and often reflects one node.
3. **Duration-weighted** tracks mean \|Δ\| closely (same ~1.7/yr at 40 bp) but needs a new metric and slightly overweight long maturities; data does not strongly favor it over equal-weight mean.
4. **Twist** is useful context but can fire without a broad curve move (and vice versa); keeping it diagnostic avoids a second black-swan path.
5. **35 bp** lands near ~2 fires/year over 2019–2026, concentrated in COVID (2020) and the hiking cycle (2022–23), with **zero** fires in calm 2024–2025 under this rule.

### Primary fires at 35 bp (14 months)

| as_of | mean \|Δ\| | max \|Δ\| | twist |
|-------|------------|-----------|-------|
| 2020-01-31 | 43.2 | 61.4 | 9.6 |
| 2020-03-31 | 62.9 | 121.9 | 29.2 |
| 2020-04-30 | 67.8 | 151.8 | 19.4 |
| 2021-02-26 | 43.1 | 132.7 | 8.4 |
| 2022-01-31 | 48.2 | 62.6 | 3.0 |
| 2022-03-31 | 42.2 | 92.7 | 92.2 |
| 2022-04-29 | 63.5 | 112.3 | 21.7 |
| 2022-07-29 | 46.2 | 78.6 | 32.0 |
| 2022-08-31 | 38.2 | 70.5 | 53.9 |
| 2022-11-30 | 46.9 | 85.6 | 16.4 |
| 2023-01-31 | 39.5 | 68.1 | 27.8 |
| 2023-09-29 | 50.7 | 127.4 | 16.6 |
| 2023-11-30 | 58.9 | 66.4 | 8.0 |
| 2023-12-29 | 41.2 | 74.8 | 25.7 |

---

## 5. Trade-offs / caveats

- **Misses isolated long-end spikes** with small mean moves (e.g. 2020-10 mean 21 / max 104; 2024-03 mean 15 / max 86). Accepted: Sam asked for one broad-curve primary, not a second black-swan node rule.
- **Monthly publication cadence** only — daily RF rebuild may produce different intra-month distributions; re-calibrate when daily BoC intake is wired.
- **Sample is rate-cycle heavy** (COVID + hiking). In a long calm regime, 35 bp may fire rarely (good); if the team wants more Slope dry-runs, lower toward 30 bp (~3/yr).
- Diagnostics remain in the snapshot JSON so ops can see max/twist without promoting them to overall status.

---

## 6. Implementation

| File | Change |
|------|--------|
| `pipeline/trigger.py` | `CALIBRATED` primary 35 bp; `overall()` follows primary only |
| `pipeline/snapshot.py` | History flagging + notes use calibrated primary |
| `pipeline/backtest_trigger.py` | Prints distribution / fire tables |
| `docs/memos/trigger-calibration.md` | This memo |

Rebuild:

```bash
python3 -m pipeline.build_monitor_snapshot
```
