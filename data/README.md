# TVFI data

Downloaded from Fiera Capital’s CIA IFRS 17 curves page for the yield-curve monitoring project.

Source: https://www.fieracapital.com/en-ca/institutional-markets/cia-ifrs-17-curves/

## Layout

```
data/
  README.md
  curves/                  # Slope workbooks from pipeline.curve_builder (col J)
  risk_free/               # BoC zero-coupon snapshots (YYYY-MM-DD.json) + fixture sample
  fiera/
    MANIFEST.json          # download inventory
    docs/                  # implementation note PDF
    monthly_raw/           # full monthly method Excel workbooks (primary archive)
    extracted/
      latest/              # CSVs from newest workbook (2026-10-30)
      history/             # cross-month series for audit / liquidity-premium analysis
```

## What was kept vs skipped

| Asset | Kept? | Why |
|---|---|---|
| Monthly **method** `.xlsx` | Yes (all months on the page) | Contains `Illiquid_Ref_Curve_Construction`, column H liquidity premium, column J annual forwards, `Market_Curves` |
| Implementation note PDF | Yes | Explains static parameters |
| Monthly **statistics** PDFs | No | Bond-subset counts / YTMs only — not used for Slope curve construction |

## Extracted files (pipeline-ready)

### `fiera/extracted/latest/`
- `static_parameters.csv` / `.json` — top-left insurer params (leave static)
- `illiquid_construction.csv` — years 1–100: risk-free, liquidity spread, col H, spot, **col J forward**
- `slope_forwards_column_J.csv` — Slope input format (`Policy Duration`, `Forward Rate`)
- `market_curves.csv` — Canada / Province / Corp A / Corp BBB par rates
- `illiquid_reference_spot.csv`, `liquid_reference_spot.csv` — published spot checks

### `fiera/extracted/history/`
- `liquidity_premium_by_month.csv` — col H (and related) for every month × year
- `liquidity_premium_summary.csv` — compact monthly summary for “hold vs update” analysis
- `canada_par_by_month.csv` — Canada par rates from each publication
- `static_parameters_by_month.csv` — parameter drift check across publications

### `curves/`

Slope-ready outputs from `python3 -m pipeline.curve_builder` (see `pipeline/README.md`):
`illiquid_col_j_<as_of>.xlsx` / `.csv` (Fiera RF) or `illiquid_col_j_boc_rf_<rf>_h_<h>.*` (BoC RF)
with Sheet1 `Policy Duration`, `Forward Rate` (1–100).

### `risk_free/`

BoC zero-coupon CSV intake (`python3 -m pipeline.boc_intake`):

- `YYYY-MM-DD.json` — dated snapshot (`rf_asof` = observation date; ~2-week lag)
- `fixture_boc_zeros_sample.json` — real BoC observation labeled `is_fixture: true` for offline use

See `docs/memos/boc-rf-lag-freshness.md`.

## Note

Fiera files are **monthly**. Daily Canadian RF is the BoC zero CSV under `risk_free/`; on Fiera publication dates validate the builder with `--rf fiera --validate` against column J here.
