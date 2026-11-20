# BoC risk-free lag & freshness

**Project:** STATS 4960 Group 5 / TVFI  
**Date:** 2026-11-09  
**Related:** `docs/memos/daily-risk-free-source.md`, `pipeline/boc_intake.py`

## Source

Primary RF input is the Bank of Canada **zero-coupon bond yield curve CSV** (not Valet benchmarks).

```text
GET https://www.bankofcanada.ca/stats/results/csv?lookupPage=lookup_yield_curve.php&dFrom={YYYY-MM-DD}&dTo={YYYY-MM-DD}
```

Use a rolling ~30–45 calendar-day window so the Thursday refresh still returns the newest lagged observation.

## Lag (product property)

| Property | Value |
| --- | --- |
| Refresh cadence | Typically **Thursday ~16:30 ET** |
| Structural lag | **~2 weeks** (observation date behind calendar) |
| Verified example | On 2026-11-09, latest CSV row was **2026-10-21** (~19 calendar days) |

Hold the last published zero curve as `rf_asof`. Do not invent fills for missing calendar days; BoC marks holidays `na` — drop those rows.

## Snapshot contract

Dated JSON under `data/risk_free/YYYY-MM-DD.json` (filename = observation `rf_asof`):

- `rf_source`, `fetched_at`, `source_url`, `is_fixture`
- `tenors_years` / `zeros` — full 0.25y grid, **continuous** decimals
- `annual_zeros_1_30` — years 1–30 converted to **annual-effective** spots for `curve_builder` (`s = exp(z) - 1`)
- `gaps.publish_lag_days`, `lag_note`

Offline: `data/risk_free/fixture_boc_zeros_sample.json` is a **real** BoC observation labeled `is_fixture: true` (not synthetic).

## How to run

```bash
# Refresh BoC snapshot (+ fixture sample)
python3 -m pipeline.boc_intake

# Slope workbook: BoC RF + hold_latest col H
python3 -m pipeline.curve_builder --rf boc

# Unchanged Fiera fixture validation path
python3 -m pipeline.curve_builder --rf fiera --validate
```
