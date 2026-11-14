# Monitoring pipeline → dashboard

Local Python package that turns archived Fiera monthly curves into the dashboard’s `monitor_snapshot.json`.

**Not** part of the Slope checkpoint zip (`run_curves.py` / `analyse_results.py` stay separate).

## What it does

1. Loads Fiera history from `data/fiera/extracted/history/`
2. Sets:
   - **Pricing basis** = prior month Illiquid column J (annual forwards) — locked baseline
   - **Current basis** = latest Canada par (`Market_Curves`)
   - **Implied** = either archived latest column J (`fixture_archive`) or **rebuilt** column J from `curve_builder` (`rebuilt`)
3. Computes curve-only metrics (weighted |Δ| T, signed S, bucket mean |Δ|, 2s10s twist) in bp
4. Evaluates **calibrated** thresholds (no Slope) — see `docs/memos/trigger-calibration.md`
5. Writes:
   - `data/decisions/YYYY-MM-DD.json` — decision log (measure, threshold, values, overall_status, inputs)
   - `data/monitor/monitor_snapshot.json` (single write; dashboard loads this path)

Optional schema 1.0 sections (dashboard `validate`/`derive` ignore unknown keys safely):

| Key | Shape |
|-----|--------|
| `decision` | `{measure, threshold_bp, value_bp, status, decision_path}` |
| `profitability` | `{status: "not_run"\|"export_found"\|"available", note, summary}` |

**Profitability attach:** when `analyse_results.py` writes `exports/profitability_summary_*.xlsx` (needs TVFI `slope_api.py`), re-run this builder; `profitability.status` becomes `export_found` with `summary.export_path` (metrics still null). Status becomes `available` only once workbook parse fills `summary.metrics`. Until an export exists, status stays `not_run`.

## Run

From the TVFI project root:

```bash
# Default: consecutive archived Fiera publication pair (implied = published col J)
python3 -m pipeline.build_monitor_snapshot

# Rebuilt: implied = curve_builder col J (BoC RF when data/risk_free has a
# dated snapshot; else Fiera fixture) + hold_latest H; pricing basis still
# prior publication J
python3 -m pipeline.build_monitor_snapshot --rebuilt
python3 -m pipeline.build_monitor_snapshot --rebuilt --as-of 2026-10-30
python3 -m pipeline.build_monitor_snapshot --rebuilt --rf fiera   # force fixture RF
python3 -m pipeline.build_monitor_snapshot --rebuilt --rf boc     # force BoC RF
```

Serve the dashboard from the **TVFI project root** (relative `../../data/monitor/...` URL):

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m http.server 8000
# open http://127.0.0.1:8000/Dashboard%20UI/Group5_Monitoring_Dashboard/
```

Footer should say `Loaded snapshot: ../../data/monitor/monitor_snapshot.json`.

### Snapshot modes

| Mode | Flag | Pricing basis | Implied |
|------|------|---------------|---------|
| `fixture_archive` | (default) | prior publication col J | archived latest col J |
| `rebuilt` | `--rebuilt` | prior publication col J | `curve_builder` rebuilt col J |

In **rebuilt** mode, `meta` carries `curve_mode`, `rf_source`, `rf_as_of`, `lag_note` (when BoC), `premium_policy`, premium `as_of`, and a `construction_record` pointer under `data/curves/`. Default RF is **auto**: prefer latest dated `data/risk_free/YYYY-MM-DD.json` (skip `fixture_boc_zeros_sample.json` unless it is the only file); fall back to Fiera fixture RF with `rf_fallback_note` if none exist. Override with `--rf boc|fiera` or `--boc-snapshot`. Schema stays `1.0`.

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

Output: `data/curves/illiquid_col_j_<as_of>.xlsx` (Fiera RF) or `illiquid_col_j_boc_rf_<rf>_h_<h>.*` (BoC RF), plus matching `.csv`. Snapshot `--rebuilt` prefers BoC RF by default and writes `construction_record_<as_of>.json`.

RF sources for `curve_builder`: `--rf fiera` (default there, col E fixture; required for `--validate`) or `--rf boc` (dated JSON under `data/risk_free/`). Monitor `--rebuilt` defaults to `--rf auto` (BoC when available). Lag/freshness: `docs/memos/boc-rf-lag-freshness.md`.

## Module split (keep thin)

| Module | Owns |
|--------|------|
| `metrics.py` | Pure bp helpers |
| `interval_metrics.py` | Live-pair + consecutive-interval metrics (snapshot / history / back-test) |
| `trigger.py` | Calibrated rules / overall status (`use_calibrated`; `use_provisional` deprecated alias) |
| `curve_builder.py` | Column J rebuild |
| `boc_intake.py` | BoC download + dated RF JSON |
| `snapshot_modes.py` | Fixture vs rebuilt implied-curve branching |
| `snapshot_history.py` | Archive consecutive-J history rows + rebuilt labeling (no flags in rebuilt) |
| `snapshot.py` | Assemble `monitor_snapshot.json` body only |
| `snapshot_io.py` | Decision log + enrich + single write to `data/monitor/` |
| `decision_hooks.py` | Decision log + profitability attach (`not_run` / `export_found` / reserved `available`) |
| `profitability_formulas.py` | Local source of truth for VoNB / Net CSM / CaPM helpers |
| `check_profitability_paste.py` | Freeze check vs paste in `analyse_results.py` |
| `pre_submit.py` | Local gate before packaging / push (runs paste freeze) |

```bash
# Before packaging analyse_results.py or pushing pipeline formula edits:
python3 -m pipeline.pre_submit
# (same as: python3 -m pipeline.check_profitability_paste)
```

## Notes

- Yields in the snapshot are **percent** (dashboard contract).
- Dashboard KPIs prefer `metrics_computed` / `decision` from this pipeline (see `Dashboard UI/.../dashboard.js`); charts still derive per-maturity deltas in JS.
- History panel is always **archived Fiera consecutive column J**; in `--rebuilt` mode those dots are labeled archive-only and are **not** red-flagged (live KPI is prior J vs rebuilt implied).
- BoC intake is live via `pipeline/boc_intake.py`; archive monitor mode still uses consecutive Fiera publications; rebuilt mode prefers BoC RF when a snapshot exists.
- Dry runs still need TVFI’s `slope_api.py`; `GROUP` is now 5 in `run_curves.py` for real submissions.
- Column H policy for the builder is **`hold_latest_publication`** (see `docs/memos/column-h-liquidity-premium.md`).
