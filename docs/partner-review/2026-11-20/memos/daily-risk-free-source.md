# Daily Canada risk-free yield source — recommendation

**Project:** STATS 4960 Group 5 / TVFI Secured Retirement monitoring  
**Author:** Researcher C  
**Date:** 2026-11-09  
**Audience:** Pipeline + dashboard owners (Sam feedback: stop shopping; pick one)

## Verdict

**Recommend one primary source: Bank of Canada zero-coupon bond yield curve (CSV).**

Use it as the sole risk-free input to Fiera-style construction (annual forwards → Slope col J path). Do not treat Valet benchmarks, FXMacroData, or Trading Economics as competing primaries.

---

## 1. Ranked comparison

| Rank | Source | Cost / access | Cadence & lag | Maturity coverage | Format / parseability | Fit for Fiera → Slope |
| ---: | --- | --- | --- | --- | --- | --- |
| **1 (pick)** | **BoC zero-coupon yield curve** | Free; no key | Daily curves; file typically updated **Thu ~16:30 ET** with **~2-week lag** | **0.25y–30.00y** on a **0.25y grid (120 tenors)** | CSV via stats form/`stats/results/csv?lookupPage=lookup_yield_curve.php&…` (not on Valet) | Best free match: already zeros; dense 1–30 market piece; interpolate annually then extend beyond 30 for Slope 1–100 |
| 2 | BoC Valet **benchmark** bond yields | Free; no key | **Business-daily**; bond yields published ~**09:30–10:00 ET** | Sparse: **2, 3, 5, 7, 10, Long** (+ RRB long); no 1y / no full 15–25 grid | Valet JSON/CSV/XML group `bond_yields_benchmark` | Timely market check only; par yields need bootstrap + heavy fill before annual forwards |
| 3 | BoC Valet T-bills / CORRA (short end) | Free; no key | Daily (T-bills ~10:30–11:30 ET) | Money-market / overnight only | Valet series/groups | Useful short-end context; **not** a 1–30 / 1–100 curve |
| — | CanDeal DNA (direct) | Commercial | N/A for students | Full dealer pricing | Vendor | Upstream of BoC benchmarks; **not** a free student API |
| — | FXMacroData CAD gov yields | API key / paid unlock for full use | Daily wrapper | Sparse gov tenors (e.g. 2y, 10y pages) | REST + key | Non-primary; re-packages official data |
| — | Trading Economics | No free API; Standard ~$199/mo | Vendor quotes | Bond markets via paid API | REST + key | Non-primary; blocked for free student pipeline |

**Verification note (2026-11-09):** Zero-curve CSV latest observation date was **2026-10-21** (~2–3 weeks behind calendar), consistent with BoC’s stated Thursday / two-week lag. Valet benchmarks were current through **2026-11-05**.

---

## 2. Final recommendation (one source)

**Primary: Bank of Canada “Yield curves for zero-coupon bonds” (CSV).**

**Why this one (and not Valet benchmarks):**

1. **Construction-ready zeros** — Continuous-compounding zeros in decimal form (e.g. `0.0500` = 5%), so the pipeline does not invent a bootstrap just to reach annual forwards.
2. **Coverage for the market piece** — Uniform **0.25–30y** grid covers ~1–30y durations with native points every quarter-year; Valet only gives six nominal benchmarks.
3. **Credible methodology** — Fitted from GoC bonds + T-bills; documented in Bolder, Johnson, and Metzler (2004) (linked from the BoC page).
4. **Free and student-safe** — Public CSV; no registration; no paid subscription.
5. **Sam constraint** — One recommended RF source for monitoring. Benchmarks remain an optional *staleness / market-move overlay*, not a second primary curve shop.

Accept the publication lag as an explicit product property of this source (document it on the dashboard freshness badge), rather than switching vendors.

---

## 3. Known gaps and fill / extrapolation approach (high-level)

| Gap | Detail | Proposed fill |
| --- | --- | --- |
| **Publication lag** | Weekly file refresh; ~2-week structural lag (verified ~19 calendar days as of memo date) | Hold **last published zero curve** as `rf_asof`; stamp `source_publish_lag_days`. Optional: show Valet benchmark Δ vs last common date as *market drift since RF as-of* (context only; do not replace zeros). |
| **Holidays / missing rows** | BoC marks missing days `na` | Drop `na` rows; do not interpolate across holidays into the official series. |
| **No Valet endpoint** | Zeros are CSV-only (stats lookup), not `/valet/observations/...` | One dedicated CSV fetcher with content-type / header validation; cache last good file on HTML/maintenance responses. |
| **Maturity holes inside 1–30** | Grid is quarterly; Fiera/Slope want **annual** forwards | Interpolate zeros on **integer years 1…30** from neighboring `ZC{nnnn}YR` columns (linear in maturity on continuously compounded zeros is acceptable v1). |
| **Beyond 30 → Slope 1–100** | Official curve stops at **30.00y** | High-level v1: hold the **30y zero flat** for years 31–100 *or* apply a **constant long forward** equal to the 29→30 implied one-year forward. Flag extrapolated tenors in the snapshot (`extrapolated: true` for t>30). Prefer matching whatever Fiera workbook rule the team locks in col J QA. |
| **If someone used benchmarks only** | Missing 1y, 4y, 6y, 8–9y, 11–29y continuum | (Not our primary path.) Map 2/3/5/7/10/Long → spline or piecewise-linear log-DF bootstrap, then same annual + >30 extension. Higher error vs BoC zeros; avoid unless zeros unavailable. |

---

## 4. Concrete intake sketch

### A. Primary pull (recommended)

```text
GET https://www.bankofcanada.ca/stats/results/csv?lookupPage=lookup_yield_curve.php&dFrom={YYYY-MM-DD}&dTo={YYYY-MM-DD}
```

- Use a rolling window (e.g. last **30 calendar days**) so each Thursday refresh still returns the newest lagged row.
- Parse CSV: column `Date`, then `ZC025YR` … `ZC3000YR` (tenor years = integer suffix / 100).
- Values are **decimals**; convert to percent or keep as rate consistently with Fiera inputs.
- Select latest non-`na` row → build snapshot below.

### B. Optional overlay (not primary)

```text
GET https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=5
# or .../csv?recent=5
```

Series: `BD.CDN.{2,3,5,7,10}YR.DQ.YLD`, `BD.CDN.LONG.DQ.YLD` (ignore RRB for nominal RF).

### C. Snapshot shape (pipeline contract sketch)

```json
{
  "rf_source": "boc_zero_coupon_csv",
  "rf_asof": "2026-10-21",
  "fetched_at": "2026-11-09T16:45:00-05:00",
  "quote_convention": "continuous_zero_decimal",
  "methodology": "Bolder-Johnson-Metzler-2004",
  "tenors_years": [0.25, 0.5, "...", 30.0],
  "zeros": [0.02385, 0.02578, "...", 0.04342],
  "annual_zeros_1_30": [0.02885, 0.03269, "..."],
  "annual_forwards_1_100": ["/* after Fiera construction + >30 policy */"],
  "gaps": {
    "official_max_maturity_years": 30,
    "extrapolation_policy": "flat_30y_zero_or_const_long_fwd",
    "publish_lag_days": 19
  },
  "market_overlay_optional": {
    "source": "valet_bond_yields_benchmark",
    "asof": "2026-11-05",
    "par_yields_pct": {"2": 3.17, "3": 3.26, "5": 3.39, "7": 3.48, "10": 3.67, "long": 4.02}
  }
}
```

Wire this into `pipeline/` as the daily RF intake feeding held liquidity premium (col H policy) → reconstructed illiquid col J → `monitor_snapshot.json`.

---

## 5. Non-primary vendors (do not adopt)

- **FXMacroData** — documents CAD gov bond endpoints with `X-API-Key`; useful dashboards, but not free/primary and ultimately cites BoC-class official yields.
- **Trading Economics** — no free API; Standard tier is paid (~$199/mo listed); unsuitable for a student monitoring pipeline.

---

## Citations (URLs used)

1. https://www.bankofcanada.ca/rates/interest-rates/bond-yield-curves/  
2. https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/  
3. https://www.bankofcanada.ca/rates/  
4. https://www.bankofcanada.ca/valet/static/swagger/api-en.yml  
5. https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json  
6. https://www.bankofcanada.ca/valet-api-how-to/  
7. https://www.bankofcanada.ca/stats/results/csv?lookupPage=lookup_yield_curve.php&dFrom=2026-09-01&dTo=2026-11-09 (live CSV check)  
8. https://carrycurve.com/methodology/cad (secondary confirmation: zeros not on Valet; Thu / 2-week lag)  
9. https://fxmacrodata.com/canada/gov-bond-10y  
10. https://tradingeconomics.com/api/pricing.aspx  
11. https://www.candeal.com/en/news/bank-canada-selects-candeal-data-analytics-dna-reference-pricing-service-its-pricing-source  
