# Profitability formula map (Example Profitability Model.xlsx)

**Audience:** paste into `analyse_results.py` later (no runtime dependency on this workbook or on `slope_api` existing today).  
**Perspective:** insurer (commissions / expenses are outflows).  
**Primary metrics (Sam-locked):** VoNB (%), Net CSM (%), Capital-adjusted Profitability Margin (CaPM).  
**Intermediate:** VoNB ($).  
**Risk discount rate:** **15%** fixed (`CTFS by cell!B1` and `Business Mix Summary` profit measures).

Source of truth while developing: optional local stubs in `pipeline/profitability_formulas.py` (not imported by Slope checkpoint scripts).

---

## 1. Headline columns on `By Cell Summary` (Y / Z / AA / AB)

Header row is **row 4**. One row per **Model Point Record #** (col A), data from row 5.

| Col | Label | Excel (per cell row `r`) | English |
|---|---|---|---|
| **Y** | VoNB | `=XLOOKUP(Ar,'CTFS by cell'!$C$5:$NV$5,'CTFS by cell'!$C$2:$NV$2,0,0)` | VoNB **dollars** = NPV@15% of that model point’s annual CTFS path (precomputed on `CTFS by cell` row 2). |
| **Z** | VoNB (%) | `=Yr/Lr` | VoNB ($) / **Initial Premium**. |
| **AA** | Net CSM (%) | `=-Wr/Lr` | −(Time 0 Actuarial Liability − Net) / Initial Premium. |
| **AB** | Capital-adjusted Profitability Margin | `=IF(Br="PA1",Yr/(-Mr+Lr/12),Yr/(-Mr+Lr))` | VoNB ($) / capital-adjusted premium denominator (plan-code dependent). |

### Inputs on the same row (needed for Z / AA / AB)

| Col | Label | Source |
|---|---|---|
| B | Plan Code | `Model Point Fields` via `XLOOKUP(Ar & "Plan Code", …)` |
| L | Initial Premium | `Model Point Fields` (`Initial Premium`) |
| M | PV(Premium) | `SUMIFS('By Cell (Reserves)'!G:G, A:A, "2026-01", B:B, Ar)` → sheet header **PV (Gross Premiums)** at first reporting month |
| W | Time 0 Actuarial Liability − Net | `SUMIFS('By Cell (Reserves)'!V:V, A:A, "2026-01", B:B, Ar)` |

In the example file, t0 filter is the literal `"2026-01"`. In code, treat this as **minimum / issue reporting month** for the export (do not hard-code 2026 when Slope returns another valuation year).

### Portfolio totals on row 3 (same sheet)

| Col | Formula | Meaning |
|---|---|---|
| Y3 | `=SUM(Y5:Y388)` | Total VoNB ($) |
| Z3 | `=Y3/L3` | Portfolio VoNB (%) = Σ VoNB / Σ Initial Premium |
| AA3 | `=-W3/L3` | Portfolio Net CSM (%) = −Σ T0 AL Net / Σ Initial Premium |
| AB3 | `=SUM(Y5:Y389)/(SUM(L5:L389)-SUM(M5:M389))` | Portfolio CaPM = Σ VoNB / (Σ Initial Premium − Σ PV(Premium)) |

**Important:** portfolio / slice CaPM (**AB3**, Regular/Roll-in AE3/AG3, and `By Cell Aggregated` N) uses **(L − M)** and does **not** apply the PA1 `L/12` rule. The `L/12` split is **per-cell AB only**.

### Plan-type slices on the same sheet (example layout)

Example workbook partitions model points as Regular Premium (PA1) vs Roll-in (RI1) by row blocks (here ~5–53 vs ~54–90):

- Net CSM (%), Regular: `=-SUM(W5:W53)/SUM(L5:L53)`
- CaPM, Regular: `=SUM(Y5:Y53)/(SUM(L5:L53)-SUM(M5:M53))`
- Net CSM (%), Roll-in: `=-SUM(W54:W90)/SUM(L54:L90)`
- CaPM, Roll-in: `=SUM(Y54:Y90)/(SUM(L54:L90)-SUM(M54:M90))`

Prefer grouping by **Plan Code** from Model Point Fields rather than hard-coded row ranges.

---

## 2. How VoNB ($) is built (CTFS → NPV@15%)

`CTFS by cell` is an **Excel-derived** sheet (not one of the seven Slope CSVs).

1. **Rate:** `B1 = 0.15`.
2. **Columns C…:** each column is one model point (`C5`, `D5`, … = model point #); last column may be `Total`.
3. **Rows 6…95:** policy/calendar years (`B6=2026` … `B95=2115`, index in col A = 1…90).
4. **In-year CTFS:**  
   `=SUMIFS('By Cell (LICAT)'!$Q:$Q, $A:$A, $Byear, $B:$B, model_point)`  
   where col **Q** header is **`CTFS`**.
5. **VoNB ($):** `=NPV($B$1, C6:C95)` for that column (Excel `NPV` discounts the first cash flow by one period).

So:

```text
VoNB_$(mp) = NPV_excel(0.15, CTFS_year1..CTFS_year90 for mp)
```

`By Cell Summary!Y` simply XLOOKUPs that row-2 NPV by model point.

### Portfolio VoNB on `Business Mix Summary` (related, not identical path)

Profit measures (cols A–B):

| Cell | Label | Formula |
|---|---|---|
| B2 | VoNB $ (@ 15%) | `=NPV(15%, BC8:BC97)` |
| B3 | VoNB % (@ 15%) | `=NPV(15%, BC8:BC97)/G8` |
| B5 | t0 % Direct Net CSM | `=-Reserves!AM2/G8` |

`BC` = Contribution to Free Surplus **(with expense)** ← `Cash Flows!AF`.  
`G8` = t0 premiums ← `Cash Flows!F2`.

Per-cell Sam metrics use **By Cell (LICAT)!CTFS** NPV’d; portfolio BMS uses **Cash Flows!AF**. Reconcile once real exports are available; do not assume they are bitwise identical without checking.

Commissions appear on `Cash Flows` as outflows (`Best Estimate Commissions (on assets|on CF)`), consistent with insurer view.

---

## 3. PA1 vs RI1 CaPM denominator

Per-cell (`By Cell Summary!AB`):

| Plan Code | Denominator | Formula shape |
|---|---|---|
| **PA1** (regular premium) | `-PV(Premium) + InitialPremium/12` | `Y / (-M + L/12)` |
| **else** (example: **RI1** roll-in) | `-PV(Premium) + InitialPremium` | `Y / (-M + L)` |

Algebra note: with PV(Premium) stored **negative** in the example (`M < 0`), `L - M` equals `-M + L`. Same identity used in aggregates: `ΣY / (ΣL − ΣM)`.

**Interpretation (from structure, not TVFI prose):** PA1 compares VoNB to one month of written premium plus the PV-premium capital term; RI1 uses the full initial premium. Aggregates intentionally drop the `/12` and use `ΣL − ΣM` only.

---

## 4. Aggregation cuts required

| Cut | Workbook analogue | How ratios are formed |
|---|---|---|
| **Model point** | `By Cell Summary` rows | Z, AA, AB as in §1 |
| **Individual** | `By Cell Aggregated` | Group by issue attributes **excluding** plan code: Issue Age, Collar Type, Sex, Deferral Period, Guarantee Period, Spousal Indicator, Spousal Benefit %, Salary Inflation, Benefit Inflation. Sum L / M / W / Y across PA1+RI1 sharing those keys; then `VoNB%=ΣY/ΣL`, `NetCSM%=-ΣW/ΣL`, `CaPM=ΣY/(ΣL−ΣM)`. |
| **Plan code** | PA1 / RI1 slices; Plan Code field | Same ratio-of-sums pattern; for CaPM at plan total use `ΣY/(ΣL−ΣM)` (workbook slice formulas), not average of per-cell AB |
| **Total** | Row 3 / BMS B2–B5 | Ratio of portfolio sums |

`By Cell Aggregated` supporting columns:

- J / K = Initial Premium for PA1 / RI1 only (filter Plan Code).
- P / Q / R / S = Total Initial Premium, PV(Premium), T0 AL Net, VoNB across both plans.
- L / M / N = `S/P`, `-R/P`, `S/(P-Q)` with `IFERROR(...,0)`.

---

## 5. Slope export CSV mapping (best notes until `load_results()` is seen)

README: each completed curve yields **seven** CSV reports. Workbook sheet names ↔ likely keys:

| # | Workbook sheet | Likely `load_results()[curve]` key | Role for primary metrics |
|---|---|---|---|
| 1 | `Cash Flows` | `"Cash Flows"` (README example) | Portfolio CTFS-with-expense (`AF`), premiums; BMS path. Not required for per-cell Z/AA/AB if LICAT-by-cell CTFS is present. |
| 2 | `Reserves` | Possibly `"Liabilities"` (README) or `"Reserves"` | Portfolio T0 AL Net (`AM`); BMS Net CSM. Align key after first real dict. |
| 3 | `LICAT` | `"LICAT"` | Portfolio capital / assets; not needed for Z/AA/AB per cell. |
| 4 | `By Cell (Reserves)` | likely `"By Cell (Reserves)"` | **Required:** PV Gross Premiums (G), T0 AL Net (V) at t0 month. |
| 5 | `By Cell (LICAT)` | likely `"By Cell (LICAT)"` | **Required:** CTFS (Q) by year × model point → VoNB ($). |
| 6 | `By Cell (CFs)` | likely `"By Cell (CFs)"` | **Not referenced** by Summary / CTFS / Aggregated formulas for Y–AB. Keep for diagnostics only. |
| 7 | `Model Point Fields` | likely `"Model Point Fields"` | **Required:** Plan Code, Initial Premium, attribute fields for joins / individual cuts. |

**Not a Slope CSV:** `CTFS by cell`, `By Cell Summary`, `By Cell Aggregated`, `Business Mix Summary` — rebuild in Python.

### Column contracts implied by formulas (do not invent beyond these)

**Model Point Fields** (long): `Model Point Record #`, `Field Name`, `Field Value`, `Product Name`, (+ Excel `Lookup`). Fields used for Summary: Plan Code, Issue Age, Collar Type, Sex, Deferral Period In Months, Guarantee Period, Spousal Indicator, Spousal Benefit %, Salary Inflation, Benefit Inflation, Initial Premium.

**By Cell (LICAT):** `Reporting Date` (calendar year string e.g. `2026`), `Model Point Record #`, `CTFS` (col Q).

**By Cell (Reserves):** `Reporting Date` (month `YYYY-MM`), `Model Point Record #`, `PV (Gross Premiums)`, `Time 0 Actuarial Liability - Net` (and related PVs if explaining CTFS).

---

## 6. Pseudocode / paste stubs

```python
RISK_DISCOUNT_RATE = 0.15  # locked with workbook


def excel_npv(rate, cashflows):
    """Excel NPV: sum_{t=1..n} cf[t-1] / (1+rate)**t  (first CF discounted one period)."""
    total = 0.0
    for i, cf in enumerate(cashflows, start=1):
        total += cf / ((1.0 + rate) ** i)
    return total


def vonb_dollars_from_ctfs(ctfs_by_year, rate=RISK_DISCOUNT_RATE):
    """ctfs_by_year: ordered list for years 1..N (missing years -> 0)."""
    return excel_npv(rate, list(ctfs_by_year))


def vonb_pct(vonb_dollars, initial_premium):
    return vonb_dollars / initial_premium


def net_csm_pct(t0_al_net, initial_premium):
    return -t0_al_net / initial_premium


def capm(vonb_dollars, initial_premium, pv_premium, plan_code, *, per_cell=True):
    """
    per_cell=True  -> PA1 uses L/12; else uses full L  (By Cell Summary!AB)
    per_cell=False -> always (L - pv_premium)         (aggregates / AB3)
    """
    if per_cell and plan_code == "PA1":
        denom = -pv_premium + initial_premium / 12.0
    else:
        denom = -pv_premium + initial_premium  # == initial_premium - pv_premium
    return vonb_dollars / denom


def ratio_of_sums(numerator_sum, denominator_sum):
    if denominator_sum == 0:
        return None  # or 0 to mirror IFERROR(...,0) on Aggregated
    return numerator_sum / denominator_sum


def aggregate_metrics(rows):
    """rows: iterable of dicts with vonb_$, initial_premium, pv_premium, t0_al_net."""
    sum_y = sum(r["vonb_$"] for r in rows)
    sum_l = sum(r["initial_premium"] for r in rows)
    sum_m = sum(r["pv_premium"] for r in rows)
    sum_w = sum(r["t0_al_net"] for r in rows)
    return {
        "vonb_$": sum_y,
        "vonb_pct": ratio_of_sums(sum_y, sum_l),
        "net_csm_pct": ratio_of_sums(-sum_w, sum_l),
        "capm": ratio_of_sums(sum_y, sum_l - sum_m),  # no PA1 /12
    }
```

Suggested pipeline once CSVs exist:

1. Pivot `Model Point Fields` → one row per model point.  
2. From `By Cell (LICAT)`, build CTFS series per model point (order by reporting year); `vonb_$ = excel_npv(0.15, series)`.  
3. From `By Cell (Reserves)` at t0 month, attach `pv_premium` (G) and `t0_al_net` (V).  
4. Compute per-cell Z / AA / AB.  
5. Aggregate to individual / plan / total via `aggregate_metrics`.

---

## 7. Still unknown without real Slope exports

- Exact **string keys** in `load_results()` (especially Reserves vs `"Liabilities"`).
- Whether CSV headers match workbook headers character-for-character (spacing, dashes).
- Reporting-date formats in dry-run / live exports (year vs `YYYY-MM` vs timestamps).
- Whether CTFS in `By Cell (LICAT)!Q` equals portfolio `Cash Flows!AF` when summed.
- Full model-point universe size and whether PA1/RI1 are the only plan codes.
- Whether t0 is always the chronologically first reserves month or a named valuation date.
- Sign conventions on dry-run random CSVs (formulas assume example signs: `pv_premium` negative, `t0_al_net` negative in sample totals).
- `By Cell (CFs)` usefulness beyond unused-by-YAB status.

---

## 8. What not to do yet

- Do not import a local package from `analyse_results.py` for the TVFI checkpoint zip.  
- Do not edit `run_curves.py` / `analyse_results.py` for this transcription step.  
- Do not invent columns that never appear in the workbook formulas.
