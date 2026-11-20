# Memo: Experimental annual par bootstrap (IoA / CM1)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Status:** **EXPERIMENTAL** — not the production RF path  
**Code:** `pipeline/bootstrap.py`

---

## 1. What this is / is not

| | |
|--|--|
| **Is** | A textbook **annual par → discount factor → zero → 1y forward** bootstrap for experimentation and pedagogy |
| **Is not** | A fix for the BoC **~2-week publication lag** (we still **hold last published zeros** there) |
| **Does not replace** | Primary RF = BoC zero-coupon CSV (`docs/memos/daily-risk-free-source.md`) |

Template math (cleaned to annual par):  
[QuantAndFinancial yield_curve_bootstrapping notebook](https://github.com/omartinsky/QuantAndFinancial/blob/master/yield_curve_bootstrapping/bootstrapping.ipynb)

Actuarial framing: Institute of Actuaries / IFoA **CM1** (formerly CT1) term-structure bootstrapping from **par yields**.

---

## 2. Method (basic, annual coupons)

For a unit-notional annual-pay bond priced at **par** with coupon = par yield \(c_n\):

\[
1 = c_n \sum_{k=1}^{n-1} DF_k + (1 + c_n)\, DF_n
\]

\[
DF_n = \frac{1 - c_n \sum_{k=1}^{n-1} DF_k}{1 + c_n},
\quad
z_n = DF_n^{-1/n} - 1,
\quad
f_n = \frac{DF_{n-1}}{DF_n} - 1
\]

(\(z_1 = c_1\), \(f_1 = z_1\).)

Same recursion as the notebook’s spot loop after yields are on annual nodes; we skip gilt accrued-interest / semi-annual calendar detail on purpose (keep it CM1-basic).

---

## 3. Inputs in this repo

Default experiment input: **Fiera Canada par** from `data/fiera/extracted/latest/market_curves.csv` (years 1–30), or a named month from `canada_par_by_month.csv`.

Optional comparison targets (not used inside the bootstrap):

- `liquid_reference_spot.csv` — Fiera liquid annual-effective spots  
- `illiquid_construction.csv` col E — construction risk-free used in col-J rebuild  

---

## 4. How to run

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.bootstrap --self-test
python3 -m pipeline.bootstrap --series canada_par --compare
python3 -m pipeline.bootstrap --as-of 2026-10-30 --compare
```

Artifacts (gitignored only if under experimental paths you choose; defaults write under `data/curves/`):

- `data/curves/experimental_bootstrap_canada_par.json`
- `data/curves/experimental_bootstrap_canada_par.csv`

---

## 5. Empirical check (2026-10-30 Fiera extract)

On latest Canada par → bootstrap zeros vs Fiera extracts:

| Reference | Result |
|-----------|--------|
| Illiquid construction **col E** (risk-free) | **0 bp** max \|Δ\| — Fiera’s construction RF **is** this annual-par bootstrap |
| Liquid reference spot | ~60–90 bp higher on the long end (different curve; not expected to match) |

So the experiment also **documents** how Fiera builds the RF piece we already use in `curve_builder --rf fiera`.

## 6. Relation to monitoring design

- **Lag gap:** production fill is the **Valet key-rate shift bridge** (`docs/memos/valet-lag-bridge.md`) — not this bootstrap.  
- **This module:** pedagogy + sensitivity; documents that Canada par → zeros ≡ Fiera construction RF.  
- **Production col J:** `curve_builder` (BoC RF ± Valet lag bridge + held H + static θ).
