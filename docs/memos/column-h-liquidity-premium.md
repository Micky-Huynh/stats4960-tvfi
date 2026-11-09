# Memo: Column H Liquidity Premium — Hold Latest vs Intra-Month Update

**To:** TVFI / Group 5 project file  
**From:** Researcher B (STATS 4960 Group 5)  
**Date:** 2026-11-09  
**Subject:** Defended policy for Fiera liquidity premium (column H) between monthly publications  
**Inputs:** `data/fiera/extracted/history/liquidity_premium_*.csv`, `static_parameters_by_month.csv` (85 Fiera months, 2019-10 → 2026-10)

---

## 1. Question and constraint

Slope receives the **annual forward rate** (column J). That curve is rebuilt from:

1. A **daily Canadian risk-free curve** (we update), and  
2. Fiera’s **liquidity premium (column H)**, published monthly, and  
3. **Top-left insurer parameters** on the Fiera sheet.

Sam’s feedback: top-left parameters stay **static** (use Fiera’s values; do not redesign them). Column H is the open question — leaving it monthly-only **without analysis** is not acceptable. The daily RF path must still refresh column J even when H is held.

**Decision:** Should we hold the latest published H through the month (`hold_latest_publication`), or infer H more often from the liquidity-spread path?

---

## 2. What column H is in the archive

On `Illiquid_Ref_Curve_Construction`, for observable years 1–30:

\[
H = \text{liquidity spread (F)} + \text{additional liquidity premium (G)}
\]

Across all 85 months × years 1–30 in the extracted history:

- **Additional premium (G) is always 0.005** (50 bp). It never moves.  
- Therefore **every month-to-month change in H is a change in the liquidity spread (F)**.  
- Mean H over years 1–30 averages **~167 bp** (min 129 bp, max 251 bp in Mar 2020), of which ~70% is spread and 50 bp is the constant add-on.

Holding H is equivalent to holding Fiera’s published liquidity-spread term structure until the next Fiera workbook.

Supporting extracts:

- `liquidity_premium_summary.csv` — monthly y1 / y10 / y30 / mean(1–30) H and selected forwards  
- `liquidity_premium_mom_moves.csv` — month-to-month deltas (bp)  
- `liquidity_premium_policy_stats.csv` — sample statistics for the policy choice  

---

## 3. Month-to-month moves in column H

Absolute MoM changes (84 intervals), **basis points**:

| Tenor / aggregate | Median \|Δ\| | Mean \|Δ\| | P90 \|Δ\| | P95 \|Δ\| | Max \|Δ\| |
|---|---:|---:|---:|---:|---:|
| H year 1 | 4.0 | 7.6 | 12.8 | 23.9 | **127.8** |
| H year 10 | 4.1 | 6.2 | 11.4 | 12.7 | 91.1 |
| H year 30 | 5.7 | 8.4 | 15.2 | 21.7 | 88.2 |
| H mean years 1–30 | **4.5** | 6.3 | 10.9 | 14.1 | **91.0** |

How often does mean(1–30) H move by a material amount?

| Threshold | Share of months |
|---|---:|
| \|Δ\| ≥ 10 bp | 10.7% (9 / 84) |
| \|Δ\| ≥ 15 bp | 4.8% (4 / 84) |
| \|Δ\| ≥ 25 bp | 2.4% (2 / 84) |
| \|Δ\| ≥ 50 bp | 1.2% (1 / 84) |

**Typical months are quiet.** Outside Mar–Jun 2020, median \|Δ mean H\| is still ~4.4 bp, P90 ~9.4 bp, and the **largest** MoM move is only **16.4 bp**. In the **last ~36 months**, mean \|Δ H\| is **4.2 bp**, median **4.2 bp**, and **no** MoM \|Δ mean H\| reached 10 bp.

### Crisis / stress months

| Month | Δ mean H (bp) | Notes |
|---|---:|---|
| **2020-03** | **+91.0** | COVID liquidity spike; y1 +128 bp, y10 +91, y30 +88 |
| 2020-04 | −37.2 | Partial unwind |
| 2020-06 | −20.0 | Further normalization |
| 2022-04 | +14.4 | Largest non-COVID up-move in sample |
| 2022-09 / 2023-03 | ~+12.3 | Modest stress / banking-stress window |

The COVID publication already embeds the crisis level in the next Fiera workbook. A hold-latest policy does **not** ignore that move; it adopts it on publication day. What it cannot do is invent an **intra-month** path between Feb-26 and Mar-31 publications — and neither does an unverified “update via spread” without a Fiera-aligned daily spread source.

---

## 4. H vs risk-free vs forward moves

Using mean years 1–30 risk-free spots from the same workbooks, and a simple forward proxy (average of fwd y1/y10/y30):

| Comparison (MoM changes) | Result |
|---|---|
| corr(Δ H, Δ RF) | **−0.05** (≈ uncorrelated) |
| corr(Δ RF, Δ Fwd) | **0.75** |
| corr(Δ H, Δ Fwd) | 0.41 (full sample; **0.19** ex COVID Mar–Jun 2020) |
| Median \|Δ H\| / median \|Δ RF\| | **0.26** (~4.5 bp vs ~16.5 bp) |
| Mean \|Δ H\| / mean \|Δ RF\| | **0.36** (~6.3 vs ~17.7 bp) |

**Interpretation for monitoring:** between publications, the dominant driver of column J is the **risk-free curve**, not H. Updating daily RF while holding H still lets the pricing/forward curve move with market rates. Month-to-month H innovations are mostly **independent** of RF and, outside crises, an order of magnitude smaller than RF moves over the same window.

Also: corr(Δ H, Δ liquidity spread) = **1.00** by construction (G fixed). Any “update H via the liquidity spread” policy is only as good as a **non-Fiera daily spread estimator** that reproduces Fiera’s F. The archive does not give us that daily series — only month-end Fiera publications.

---

## 5. Static top-left parameters (confirm; do not change for TVFI)

Sam: keep insurer parameters static. Archive check (85 months):

| Regime | Dates | Ultimate RF | Liquidity spread ratio | Other |
|---|---|---|---|---|
| A | 2019-10 → 2019-12 (3 mo) | 4.00% | single 0.75 | G=50 bp, ult LP=150 bp, obs=30, timing=70, linear |
| B | 2020-01 → 2025-09 (69 mo) | **3.65%** | single **0.70** | same constants |
| C | 2025-10 → 2026-10 (13 mo) | 3.65% | **tiered** 0.80 / 0.75 / 0.70 (yrs 1–3 / 4 / 5+) | same constants |

Parameters are **not** drifting every month. They change only when Fiera revises the method workbook (two rare methodology updates in seven years). For TVFI operations:

- Treat the **latest Fiera parameter block as static** between Fiera publications.  
- **Do not** recommend TVFI retune ultimate RF, ratios, G, or ultimate LP.  
- Column H remains the only open update-frequency question.

---

## 6. OSFI-defensible monitoring argument

What an auditor can defend:

1. **Published CIA / Fiera method workbook** as the liquidity-premium authority.  
2. **Daily Canada RF** as the market input that is allowed to move continuously.  
3. Column J rebuilt each day as \(f(\text{RF}_t,\ H_{\text{last pub}},\ \theta_{\text{Fiera}})\).

What is harder to defend without new evidence:

- A homemade **intra-month H** scaled from some credit/illiquid proxy that is **not** the Fiera F column.  
- Claiming that mid-month H inference is required for prudence when, outside one COVID month, MoM H moves are typically **~4–5 bp** while RF moves **~16–18 bp** over the same publication spacing.  
- Changing top-left θ when Sam has already locked them as static.

**Hold-latest lag risk (honest bound):** until the next Fiera file, the unobserved H error is on the order of the next MoM ΔH. Historically that is **median ~4.5 bp** (mean 1–30), **P95 ~14 bp**, and **~91 bp** only in the COVID publication jump — which arrives with the official workbook anyway. Daily RF updates already absorb the larger market-rate risk into column J.

Intra-month inference would only be OSFI-stronger if we had a **documented, Fiera-consistent** daily spread feed and a back-test showing that mid-month H errors systematically bias benefit-rate or profitability decisions beyond what the curve trigger + Slope profitability test already catch. We do not have that feed in the current archive.

---

## 7. Alternatives considered (and why not primary)

| Policy | Pros | Cons |
|---|---|---|
| **A. `hold_latest_publication`** | Matches Fiera authority; simple audit trail; RF still moves J daily; MoM H usually small | Mid-month liquidity shocks not reflected until next pub |
| B. Scale H by a daily corporate-spread index | Could react faster in stress | Needs validated mapping to Fiera F; invents method between pubs; weak OSFI story without Fiera endorsement |
| C. Linear interpolate between last two pubs | Smooth path | Forward-looking between pubs is fictional; does not add real information |
| D. Hold H but add a “liquidity stress override” if some spread index jumps | Acknowledges COVID-type risk | Still needs an approved index/threshold; second process Sam did not ask for; better as a future enhancement if TVFI wants it |

Primary recommendation is **A**. Optional future work (not required to close Sam’s feedback): monitor a public Canada credit/illiquid proxy **as a diagnostic**, not as a silent rewrite of H, and escalate only if mid-month moves would have exceeded a pre-agreed bp threshold.

---

## Recommendation

**`hold_latest_publication`**

Adopt the latest Fiera-published column H (and its liquidity-spread term structure) on each publication date and **hold it constant** until the next Fiera workbook. Continue to **update the Canadian risk-free inputs daily** so column J moves with market rates. Keep top-left insurer parameters equal to the **latest Fiera static block** and do not retune them.

**Evidence that would change this recommendation**

1. TVFI (or Fiera) provides a **daily liquidity-spread series** that is the same construction as column F, with a written method note — then a more frequent H update becomes defensible.  
2. A back-test shows that **holding H** causes the curve-only trigger or Slope profitability metrics (VoNB / Net CSM / CaPM) to **miss** material mid-month events that a Fiera-aligned spread update would have caught, at a rate TVFI finds unacceptable.  
3. Repeated **non-publication** liquidity shocks where a validated proxy implies **≳15–25 bp** mean(1–30) H move inside a month (ex post vs next Fiera file) become common — historically that is rare outside COVID.  
4. Fiera itself moves to **weekly/daily** liquidity-premium publication — then match their cadence.

Until one of those holds, inventing an intra-month H path is weaker for OSFI review than using Fiera’s published H and letting daily RF drive column J.

---

*Supporting tables: `data/fiera/extracted/history/liquidity_premium_mom_moves.csv`, `liquidity_premium_policy_stats.csv`.*
