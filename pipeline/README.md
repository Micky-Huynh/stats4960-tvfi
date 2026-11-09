# Monitoring pipeline → dashboard

Local Python package that turns archived Fiera monthly curves into the dashboard’s `monitor_snapshot.json`.

**Not** part of the Slope checkpoint zip (`run_curves.py` / `analyse_results.py` stay separate).

## What it does

1. Loads Fiera history from `data/fiera/extracted/history/`
2. Sets:
   - **Pricing basis** = prior month Illiquid column J (annual forwards)
   - **Current basis** = latest Canada par (`Market_Curves`)
   - **Implied** = latest Illiquid column J
3. Computes curve-only metrics (mean |Δ|, max |Δ|, 2s10s twist) in bp
4. Evaluates **provisional** thresholds (no Slope) — replace after back-test
5. Writes:
   - `data/monitor/monitor_snapshot.json`
   - `Dashboard UI/Group5_Monitoring_Dashboard/monitor_snapshot.json`

## Run

From the TVFI project root:

```bash
python3 -m pipeline.build_monitor_snapshot
```

Serve the dashboard:

```bash
cd "Dashboard UI/Group5_Monitoring_Dashboard"
python3 -m http.server 8000
```

Open http://localhost:8000 — footer should say `Loaded snapshot: monitor_snapshot.json`.

## Curve builder (Illiquid column J)

`pipeline/curve_builder.py` rebuilds Fiera annual forwards (column J) from static params + held column H + a risk-free input, then writes a Slope workbook under `data/curves/`.

It is **separate** from the snapshot assembler and is **not** imported by `run_curves.py`.

```bash
# Latest Fiera publication day (fixture RF + hold_latest H); validates vs extracted col J
python3 -m pipeline.curve_builder

# Named publication from history (add --validate to diff vs latest reference CSV)
python3 -m pipeline.curve_builder --as-of 2026-10-30 --validate
```

Output: `data/curves/illiquid_col_j_<as_of>.xlsx` (`Sheet1`: Policy Duration, Forward Rate) plus a matching `.csv`.

Today the RF input is the Fiera construction fixture (col E). Daily BoC zero-curve intake is not wired yet — see `docs/memos/daily-risk-free-source.md`.

## Notes

- Yields in the snapshot are **percent** (dashboard contract).
- Daily BoC intake is not wired yet; this uses consecutive Fiera publications as the fixture loop.
- Dry runs still need TVFI’s `slope_api.py`; `GROUP` is now 5 in `run_curves.py` for real submissions.
- Column H policy for the builder is **`hold_latest_publication`** (see `docs/memos/column-h-liquidity-premium.md`).
