# Yield Curve Monitoring Dashboard — Group 5

A local prototype of the TVFI Secured Retirement yield curve monitoring dashboard. It reads a single `monitor_snapshot.json` file and renders the Overview and Maturity Analysis views.

**All data is placeholder.** Nothing here is real TVFI data, and no trigger rules are evaluated.

## What's in the folder

| File | Purpose |
|---|---|
| `index.html` | The dashboard page |
| `styles.css` | Styling |
| `dashboard.js` | Loads the snapshot, calculates metrics, draws the charts |
| `monitor_snapshot.json` | Placeholder data — this is the format our pipeline needs to produce |
| `README.md` | This file |

Keep all files in the same folder.

## Running it

### Option A — double-click (quickest, placeholder only)

Open `index.html` in Chrome, Edge, Firefox or Safari.

Browsers block a page opened from disk from reading other files, so in this mode the dashboard shows a built-in copy of the placeholder data instead of reading `monitor_snapshot.json`. Everything else works. You can still load a JSON file with the **Load JSON** button.

### Option B — local server (reads `monitor_snapshot.json`)

You need Python 3, nothing else to install.

1. Open a terminal in the unzipped folder.
   - **Windows:** open the folder in File Explorer, click the address bar, type `powershell`, press Enter.
   - **Mac:** right-click the folder in Finder → *New Terminal at Folder* (or `cd` into it).
2. Start the server:
   - **Windows:** `py -m http.server 8000`
     (use `py`, not `python` — on many Windows machines `python` just opens the Microsoft Store)
   - **Mac / Linux:** `python3 -m http.server 8000`
3. Go to **http://localhost:8000** in your browser.
4. Stop the server with **Ctrl + C** in the terminal.

To check it's reading the file, scroll to the footer: it should say `Loaded snapshot: monitor_snapshot.json`. If it says `embedded placeholder`, you're in Option A mode.

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
| `meta` | Observation/market/pricing dates, source, last update time, data availability, currency |
| `maturities` | Maturity nodes in years, ascending, e.g. `[0.5, 1, 2, …, 30]` |
| `curves.pricing_basis` / `current_basis` / `implied` | Each has `label`, `as_of` and `yields` (in %, same length as `maturities`; use `null` for a missing value) |
| `assessment` | `overall_status`: `UNASSESSED`, `NO_TRIGGER` or `TRIGGERED`, plus explanatory text |
| `triggers` | Each rule's `label`, `metric`, `threshold_bp` (`null` = to be calibrated) and `status`: `NOT_EVALUATED`, `PASS` or `BREACH` |
| `history` | Daily `date`, `mean_shift_bp`, `flagged` and optional `note` |
| `data_quality`, `pipeline_runs`, `notes` | Audit trail details and chart captions |

The dashboard **calculates** the mean shift, largest move, 2s10s twist and validation checks from the curves. It **does not** evaluate triggers. Trigger statuses come from the Decision log step and are displayed as given.

### Delta convention (must match the pipeline trigger)

| Measure | Formula | Where used |
|---|---|---|
| **Trigger delta** | **implied − pricing** (bp) | Overview KPIs, maturity-level bars, twist, trigger metric display, history mean shift, CSV `implied_minus_pricing_bp` |
| Market context | current − pricing (Canada par vs pricing) | Curve chart series, maturity table “market” column, tooltip secondary row — **not** KPIs |
| Construction uplift | implied − current | Formula card / construction note when present |

This matches `pipeline/snapshot.py`, which compares Fiera column J (implied) to the prior column J (pricing). Do not use Canada-par current − pricing for Overview KPIs.

## Good to know

- The placeholder data exists in two places: `monitor_snapshot.json` and a copy inside `dashboard.js` (used for Option A). If you change one, change the other.
- Fonts load from Google Fonts. Offline, the page falls back to system fonts.

## Future: Cloudflare

This version runs locally only. Later, `monitor_snapshot.json` will be served by a Cloudflare Worker (see the "later prototype" box in the data flow diagram). The only code change needed is `CONFIG.snapshotUrl` at the top of `dashboard.js`, which will point to the Worker URL.
