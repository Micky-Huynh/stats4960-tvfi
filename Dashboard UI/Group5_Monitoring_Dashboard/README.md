# Yield Curve Monitoring Dashboard — Group 5

Local prototype of the TVFI Secured Retirement yield curve monitoring dashboard. It reads `monitor_snapshot.json` (from the pipeline or a local file) and renders Overview + Maturity Analysis.

When served from the TVFI project root, it loads the **pipeline** snapshot at `../../data/monitor/monitor_snapshot.json`, optional Ridge/PCA nowcast results, lag-remedy curves from `../../data/curves/lag_bootstrap/`, and walk-forward MoE from `../../data/curves/lag_error_report.json`. Overview includes feeds + a **Lag RF rates + MoE** panel: Valet-timed daily predict → IoA bootstrap (not clock-hourly); last known BoC through `rf_asof`; Ridge / PCA / PCA+Ridge fan out; per-maturity SE / RMSE / P90|e| table; ±P90 MoE band on the maturity chart (MoE method select); hover shows SE. **Export Excel** downloads `lag_bootstrap_curves.xlsx`. Regenerate curves with `python3 -m pipeline.lag_bridge_bootstrap --xlsx-only`; MoE with `python3 -m pipeline.lag_error_report --methods ridge,pca_ridge`. See `docs/memos/trigger-calibration.md`, `valet-lag-bridge.md`, `lag-bridge-ridge-pca.md`, `lag-bridge-bootstrap.md`. Opening `index.html` from disk falls back to an embedded placeholder only.

## What's in the folder

| File | Purpose |
|---|---|
| `index.html` | The dashboard page |
| `styles.css` | Styling |
| `dashboard.js` | Loads the snapshot, calculates display metrics, draws the charts |
| `monitor_snapshot.json` | Local copy / placeholder format example |
| `README.md` | This file |

Keep all files in the same folder.

## Running it

### Option A — double-click (quickest, placeholder only)

Open `index.html` in Chrome, Edge, Firefox or Safari.

Browsers block a page opened from disk from reading other files, so in this mode the dashboard shows a built-in copy of the placeholder data instead of reading `monitor_snapshot.json`. Everything else works. You can still load a JSON file with the **Load JSON** button.

### Option B — local server (reads pipeline snapshot)

You need Python 3, nothing else to install. The pipeline writes **once** to `data/monitor/monitor_snapshot.json`; the dashboard loads that path via `CONFIG.snapshotUrl`.

1. Open a terminal in the **TVFI project root** (parent of `Dashboard UI/` and `data/`).
2. Start the server:
   - **Windows:** `py -m http.server 8000`
     (use `py`, not `python` — on many Windows machines `python` just opens the Microsoft Store)
   - **Mac / Linux:** `python3 -m http.server 8000`
3. Go to **http://127.0.0.1:8000/Dashboard%20UI/Group5_Monitoring_Dashboard/** in your browser.
4. Stop the server with **Ctrl + C** in the terminal.

To check it's reading the file, scroll to the footer: it should say `Loaded snapshot: ../../data/monitor/monitor_snapshot.json`. If it says `embedded placeholder`, you're in Option A mode (or the server cwd is wrong).

After editing `monitor_snapshot.json`, refresh the browser.

**Port already in use?** Use another number, e.g. `py -m http.server 8080`, then go to http://localhost:8080.

### Option C — VS Code

Install the **Live Server** extension, right-click `index.html` → *Open with Live Server*. Works the same as Option B.

## Using the dashboard

- **Load JSON:** pick any snapshot file from your computer; the whole dashboard redraws. A file with missing curves or mismatched lengths is rejected with a message.
- **Curve / Maturity range** dropdowns filter the charts and the table.
- **Click** a point on the curve chart, a bar, or a table row to select that maturity everywhere.
- **Export snapshot** downloads the current JSON; **Export CSV** (Maturity Analysis tab) downloads the table.
- **View history** shows the historical observations and pipeline runs.
- Add `#maturity` to the URL to open straight to the Maturity Analysis tab.

## The JSON format

See `monitor_snapshot.json` for a full example. The main parts:

| Field | What it holds |
|---|---|
| `snapshot_id`, `schema_version` | Identifiers shown in the audit trail |
| `is_illustrative` | `true` shows the "Illustrative data" banner and demo labels; set `false` for real data |
| `meta` | Observation/market/pricing dates, source, RF as-of / publish lag, Col H policy, optional `lag_bridge` (Valet keyed shift), currency |
| `decision` / `profitability` | Primary T decision + Slope profitability hook (`not_run` until exports) |
| `maturities` | Display maturity nodes in years (e.g. 9 nodes for charts/table) |
| `curves.pricing_basis` / `current_basis` / `implied` | Each has `label`, `as_of` and `yields` (in %, same length as `maturities`; use `null` for a missing value) |
| `assessment` | `overall_status`: `UNASSESSED`, `NO_TRIGGER` or `TRIGGERED`, plus explanatory text |
| `triggers` | Primary `weighted` (T), diagnostics `bucket` / `twist` / `signed` (S has no threshold) |
| `history` | Archive rows: `date`, `weighted_abs_bp`, `flagged`, optional `flag_scope` (`archive_only` / `live_primary`), `note` |
| `metrics_computed` | Pipeline-owned T / S / bucket / `primary_threshold_bp` / display mean \|Δ\| |
| `meta.obs_rf_calendar_gap_days` | observation_date − rf_as_of (not the same as `rf_publish_lag_days`) |
| `data_quality`, `pipeline_runs`, `notes` | Audit trail details and chart captions |

The dashboard **displays** pipeline trigger statuses and prefers snapshot `history[].flagged` for markers. Threshold line uses `metrics_computed.primary_threshold_bp`. It does not own calibration.

### Delta convention (must match the pipeline trigger)

| Measure | Formula | Where used |
|---|---|---|
| **Primary T** | Σ w_t · \|Δr_t\| over years 1–30 (bp) | Overview KPI, trigger panel, history chart |
| **Trigger delta (display)** | **implied − pricing** (bp) at display nodes | Maturity bars / table |
| Market context | current − pricing (Canada par vs pricing) | Curve chart series, maturity table “market” column — **not** KPIs |
| Construction uplift | implied − current | Formula card / construction note when present |

This matches `pipeline/snapshot.py`. Do not use Canada-par current − pricing for Overview KPIs.

## Good to know

- The placeholder data exists in two places: `monitor_snapshot.json` and a copy inside `dashboard.js` (used for Option A). If you change one, change the other.
- Fonts load from Google Fonts. Offline, the page falls back to system fonts.

## Future: Cloudflare

This version runs locally only. Later, `monitor_snapshot.json` will be served by a Cloudflare Worker. The only code change needed is `CONFIG.snapshotUrl` at the top of `dashboard.js`.
