# Monitoring pipeline → dashboard

Local Python package that turns archived Fiera monthly curves into the dashboard’s `monitor_snapshot.json`.

**Not** part of the Slope checkpoint zip (`run_curves.py` / `analyse_results.py` stay separate).

## What it does

1. Loads Fiera history from `data/fiera/extracted/history/`
2. Sets:
   - **Pricing basis** = prior month Illiquid column J (annual forwards) — locked baseline
   - **Current basis** = latest Canada par (`Market_Curves`)
   - **Implied** = either archived latest column J (`fixture_archive`) or **rebuilt** column J from `curve_builder` (`rebuilt`)
3. Computes curve-only metrics (mean |Δ|, max |Δ|, 2s10s twist) in bp
4. Evaluates **calibrated** thresholds (no Slope) — see `docs/memos/trigger-calibration.md`
5. Writes:
   - `data/monitor/monitor_snapshot.json`
   - `Dashboard UI/Group5_Monitoring_Dashboard/monitor_snapshot.json`

## Run

From the TVFI project root:

```bash
# Default: consecutive archived Fiera publication pair (implied = published col J)
python3 -m pipeline.build_monitor_snapshot

# Rebuilt: implied = curve_builder col J (fixture RF + hold_latest H);
# pricing basis still prior publication J
python3 -m pipeline.build_monitor_snapshot --rebuilt
python3 -m pipeline.build_monitor_snapshot --rebuilt --as-of 2026-10-30
```

Serve the dashboard:

```bash
cd "Dashboard UI/Group5_Monitoring_Dashboard"
python3 -m http.server 8000
```

Open http://localhost:8000 — footer should say `Loaded snapshot: monitor_snapshot.json`.

### Snapshot modes

| Mode | Flag | Pricing basis | Implied |
|------|------|---------------|---------|
| `fixture_archive` | (default) | prior publication col J | archived latest col J |
| `rebuilt` | `--rebuilt` | prior publication col J | `curve_builder` rebuilt col J |

In **rebuilt** mode, `meta` carries `curve_mode`, `rf_source`, `premium_policy`, RF/premium `as_of` dates, and a `construction_record` pointer under `data/curves/`. Schema stays `1.0`.

## Curve builder (Illiquid column J)

`pipeline/curve_builder.py` rebuilds Fiera annual forwards (column J) from static params + held column H + a risk-free input, then writes a Slope workbook under `data/curves/`. Snapshot `--rebuilt` calls this path; it is **not** imported by `run_curves.py`.

```bash
# Latest Fiera publication day (fixture RF + hold_latest H); validates vs extracted col J
python3 -m pipeline.curve_builder
python3 -m pipeline.curve_builder --rf fiera --validate

# Named publication from history (add --validate to diff vs latest reference CSV)
python3 -m pipeline.curve_builder --as-of 2026-10-30 --validate

# Refresh BoC zero snapshot, then build Slope workbook (BoC RF + hold_latest H)
python3 -m pipeline.boc_intake
python3 -m pipeline.curve_builder --rf boc
```

Output: `data/curves/illiquid_col_j_<as_of>.xlsx` (Fiera RF) or `illiquid_col_j_boc_rf_<rf>_h_<h>.*` (BoC RF), plus matching `.csv`. Snapshot `--rebuilt` still uses the Fiera fixture RF path by default and writes `construction_record_<as_of>.json`.

RF sources: `--rf fiera` (default, col E fixture; required for `--validate`) or `--rf boc` (dated JSON under `data/risk_free/`). Lag/freshness: `docs/memos/boc-rf-lag-freshness.md`.

## Notes

- Yields in the snapshot are **percent** (dashboard contract).
- BoC intake is live via `pipeline/boc_intake.py`; archive monitor mode still uses consecutive Fiera publications; rebuilt mode defaults to fixture RF.
- Dry runs still need TVFI’s `slope_api.py`; `GROUP` is now 5 in `run_curves.py` for real submissions.
- Column H policy for the builder is **`hold_latest_publication`** (see `docs/memos/column-h-liquidity-premium.md`).
