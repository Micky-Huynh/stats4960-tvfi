# TVFI Yield-Curve Monitoring — Course Report Draft (Group 5)

**Course:** STATS 4960 · Group 5 × Thames Valley Financial Inc.  
**Document status:** Structured draft skeleton (Wave 4 C) — **not** the final ≤10-page Word deliverable  
**Date:** 2026-11-09  
**Repo:** [Micky-Huynh/stats4960-tvfi](https://github.com/Micky-Huynh/stats4960-tvfi)

### Formatting notes (for later Word export)

- Body font: **Times New Roman**, 12 pt; headings 14 pt bold; title 16 pt bold.
- Margins: 1" all sides; line spacing 1.15 or single; page numbers bottom-center.
- Target body length: **≤ 10 pages** (exclude title page / appendix if used).
- Cite supporting memos under `docs/memos/` rather than pasting full tables into the body.
- Replace `[PLACEHOLDER]` markers before export; **do not invent** VoNB / Net CSM / CaPM values.

**Source memos:**  
`column-h-liquidity-premium.md` · `daily-risk-free-source.md` · `boc-rf-lag-freshness.md` · `trigger-calibration.md` · `profitability-formula-map.md`  
**Constraints:** Sam / TVFI progress update **87/100** (Excellent band; see `Project Agent/memory.md` + evaluation docx) and `PROJECT_STATUS.md`.

---

## 1. Executive summary and recommendation

### Recommendation (draft)

Adopt a **curve-only daily monitoring process** that:

1. Pulls the **Bank of Canada zero-coupon CSV** as the sole primary Canadian risk-free (RF) input (accept ~2-week publication lag; label freshness on the dashboard).
2. **Holds the latest Fiera-published liquidity premium (column H)** and static top-left insurer parameters between monthly Fiera publications.
3. Rebuilds **annual forward rates (column J)** for Slope from daily RF + held H + Fiera θ.
4. Fires a **single primary trigger** — mean absolute change across display maturities **≥ 35 bp** — to start a Slope profitability test (diagnostics for max |Δ| and twist only).
5. On trigger (or checkpoint), runs Slope baseline vs implied curves and reports **insurer** metrics **VoNB (%)**, **Net CSM (%)**, and **CaPM** — formulas transcribed; **live numbers blocked** until TVFI provides `slope_api.py` / exports.

Sam liked the dashboard mock-up direction; keep Overview on implied − pricing and Canada-par as market context only.

### Why this package (Sam binding → design)

| Constraint (Sam) | How addressed |
|---|---|
| Defend column H (don’t leave monthly without analysis); θ static | MoM analysis: typical \|ΔH\| ~4–6 bp; RF dominates J between pubs → `hold_latest_publication`; θ = latest Fiera block |
| Pick **one** daily RF source (active recommendation) | BoC zeros CSV only; Valet benchmarks = freshness overlay, not a second primary |
| Rewrite trigger: curve-only; no Slope / no PV-liability inside trigger | Primary = mean \|Δ\| ≥ **35 bp** (~2 fires/year on Fiera monthly history) |
| Drop second “black swan” trigger | Multi-rule OR logic retired; max/twist remain diagnostic only |
| Primary metrics = VoNB / Net CSM / CaPM (insurer view) | Formula map locked; checkpoint paste in `analyse_results.py` |

### Current monitoring snapshot (pipeline, not profitability)

- Latest rebuilt monitor example: `Fiera-20261030-R01`, **`NO_TRIGGER`**, mean \|Δ\| ≈ **15.5 bp** (pricing = prior publication J; implied = rebuilt J).
- BoC live intake verified; latest observation example **2026-10-21** (~2-week lag as of early Nov 2026).

### Still pending for the final report

- [ ] Partner sign-off on Col H, RF source, 35 bp threshold, >30y extrapolation, dashboard KPI contract.
- [ ] Slope dry-run / real exports → fill §5 comparison tables (**no fabricated numbers**).
- [ ] Default `--rebuilt` snapshot path to BoC RF when a fresh `data/risk_free/` file exists.

---

## 2. Operational process

End-to-end daily / monthly ops path the report should document for TVFI.

```text
Daily BoC RF intake
    → Hold latest Fiera column H (+ static θ)
    → Build column J (annual forwards)
    → Curve-only trigger (mean |Δ| ≥ 35 bp)
    → If FIRE: Slope profitability (baseline vs implied)
    → Dashboard via monitor_snapshot.json
```

### 2.1 Daily risk-free intake

| Step | Action | Artifact / command |
|---|---|---|
| Pull | BoC zero-coupon CSV (rolling ~30–45 day window) | `python3 -m pipeline.boc_intake` |
| Persist | Dated JSON; filename = observation `rf_asof` | `data/risk_free/YYYY-MM-DD.json` |
| Label | Stamp `gaps.publish_lag_days` / lag note | Dashboard freshness badge |
| Optional overlay | Valet benchmark par yields | Context only — do **not** replace zeros |

**Product property:** Thursday ~16:30 ET refresh; structural lag **~2 weeks**. Hold last published zeros; drop BoC `na` holiday rows (no invented fills).

### 2.2 Hold column H (and static parameters)

- On each new Fiera CIA IFRS 17 method workbook: adopt published **H** and top-left **θ**.
- Between publications: **`hold_latest_publication`** for H; do not retune ultimate RF, liquidity ratios, G (50 bp add-on), or ultimate LP.
- Daily RF still refreshes **J** = *f*(RFₜ, H_last pub, θ_Fiera).

### 2.3 Build column J

| Mode | Command | Role |
|---|---|---|
| Fiera fixture QA | `python3 -m pipeline.curve_builder --rf fiera --validate` | Validate vs published J (~0 bp error on fixture) |
| BoC production path | `python3 -m pipeline.curve_builder --rf boc` | Daily RF + held H → Slope-ready curve under `data/curves/` |
| Monitor snapshot | `python3 -m pipeline.build_monitor_snapshot --rebuilt` | Pricing = prior pub J; implied = rebuilt J → `monitor_snapshot.json` |

**Open ops item:** `--rebuilt` still defaults to Fiera col E for RF today; prefer BoC when a fresh `data/risk_free/` snapshot exists.

### 2.4 Trigger evaluation

- Display maturities: `{1, 2, 3, 5, 7, 10, 15, 20, 30}`.
- **Primary:** mean \|Δ\| bp ≥ **35** → `overall_status` = fire / start Slope test.
- **Diagnostics only:** max \|Δ\| ≥ 75 bp; \|2s10s twist\| ≥ 40 bp.
- Back-test: `python3 -m pipeline.backtest_trigger`.

### 2.5 Slope profitability (when trigger fires or on checkpoint)

1. Submit **baseline** (pricing) and **implied** (rebuilt J) workbooks via TVFI `slope_api.py` (`run_curves.py`, `GROUP = 5`, root `sample_curve.xlsx`).
2. Ingest seven CSV reports per curve; compute VoNB / Net CSM / CaPM per formula map (`analyse_results.py`).
3. Write `exports/profitability_summary_*.xlsx` when CSVs exist.
4. Fold summary into richer snapshot / dashboard (future wave).

**Blocked:** `slope_api.py` / dummy Slope not in this repo — no live profitability numbers yet.

### 2.6 Dashboard

- Static prototype: `Dashboard UI/Group5_Monitoring_Dashboard/`.
- Overview KPIs: **implied − pricing** (aligned with pipeline trigger).
- Canada-par series: labeled **market context** only.
- Serve locally: `cd "Dashboard UI/Group5_Monitoring_Dashboard" && python3 -m http.server 8000`.

---

## 3. Trigger memo (curve-only calibration)

*Condensed from `docs/memos/trigger-calibration.md`. Full fire tables stay in the memo / appendix if needed.*

### 3.1 Decision

**Primary rule (drives `overall_status`):**

> Fire / start a Slope profitability test when the **mean absolute change** across display maturities  
> \|Δ\| averaged over `{1, 2, 3, 5, 7, 10, 15, 20, 30}` ≥ **35 bp**  
> between consecutive monthly Fiera column-J curves (or pricing basis vs next implied).

Sam constraint: **one** trigger that starts Slope; drop redundant multi-rule / “second black-swan” OR logic.

### 3.2 Evidence (84 consecutive Fiera intervals, 2019-10 → 2026-10)

| Measure | min | p50 | p90 | max |
|---------|-----|-----|-----|-----|
| mean \|Δ\| bp | 4.2 | 19.0 | 43.2 | 67.8 |
| max \|Δ\| bp | 8.7 | 39.2 | 85.6 | 151.8 |
| \|2s10s twist\| bp | 0.2 | 14.3 | 40.5 | 92.2 |

**Fire-rate trade-off (mean \|Δ\|):**

| Threshold (bp) | Fires / 84 | ≈ / year |
|----------------|------------|----------|
| 25 (old provisional) | 29 | 4.1 |
| 30 | 21 | 3.0 |
| **35 (chosen)** | **14** | **2.0** |
| 40 | 12 | 1.7 |

Old OR-of-three rule fired **45/84 (≈6.4/yr)** — too chatty for an ops trigger that launches Slope.

**Why mean \|Δ\| @ 35 bp:** already on the monitor path; balances the curve (max alone is node-noisy); duration-weighted does not clearly beat equal-weight; twist kept diagnostic. Fires concentrate in COVID (2020) and the hiking cycle (2022–23); **zero** fires in calm 2024–2025 under this rule.

### 3.3 Caveats (carry into final report)

- Misses isolated long-end spikes with small mean moves (accepted under one-primary rule).
- Calibration is on **monthly** Fiera J history; **re-calibrate** when daily BoC rebuild distributions are available.
- Sample is rate-cycle heavy; if TVFI wants more dry-runs in calm markets, consider 30 bp (~3/yr).

---

## 4. Column H and risk-free source decisions

### 4.1 Column H — `hold_latest_publication`

*From `docs/memos/column-h-liquidity-premium.md`.*

**Decision:** Adopt latest Fiera-published H on each publication date and **hold constant** until the next workbook. Update Canadian RF daily so J still moves with market rates. Keep top-left θ = latest Fiera static block (do not retune).

**Defense (short):**

- H = liquidity spread (F) + additional premium (G); **G ≡ 50 bp** every month in the archive → MoM ΔH = ΔF only.
- Typical MoM \|Δ mean H (1–30)\| ≈ **4–5 bp** (median ~4.5); P95 ~14 bp; COVID Mar 2020 jump ~91 bp arrives with the official publication anyway.
- Last ~36 months: mean \|ΔH\| ~4.2 bp; **no** MoM mean move ≥ 10 bp.
- corr(ΔH, ΔRF) ≈ 0; median \|ΔH\| / median \|ΔRF\| ≈ **0.26** → **RF dominates** between pubs.
- Homemade intra-month H from a non-Fiera spread proxy is weaker for an OSFI-style audit trail than published H + daily RF.

**Would change the recommendation:** Fiera-aligned daily F series; back-test showing held H misses material mid-month profitability events; repeated non-pub liquidity shocks ≳15–25 bp; or Fiera itself moves to weekly/daily H.

### 4.2 Daily RF — BoC zero-coupon CSV (primary)

*From `docs/memos/daily-risk-free-source.md` and `boc-rf-lag-freshness.md`.*

**Decision:** **One primary** — Bank of Canada “Yield curves for zero-coupon bonds” CSV (not Valet as primary; not FXMacroData / Trading Economics).

| Why BoC zeros | Detail |
|---|---|
| Construction-ready | Continuous-compounding zeros; no invented bootstrap to reach annual forwards |
| Coverage | 0.25y–30y on 0.25y grid (120 tenors) |
| Method | Bolder, Johnson, Metzler (2004) |
| Access | Free public CSV; student-safe |
| Lag | ~2 weeks — **document as product property**, do not vendor-shop around it |

**Gaps / fill (high-level):** interpolate annual zeros 1…30 from quarterly grid; beyond 30 → Slope 1–100 via flat 30y zero **or** constant long forward matching Fiera ultimate behavior (**partner confirm**); Valet benchmarks optional staleness overlay only.

**Intake:** `GET …/stats/results/csv?lookupPage=lookup_yield_curve.php&dFrom=…&dTo=…` → `pipeline/boc_intake.py`.

---

## 5. Profitability comparison — baseline vs implied

*From `docs/memos/profitability-formula-map.md`. Formulas ready; **numbers pending Slope exports**.*

### 5.1 Locked metrics (insurer view; risk discount **15%**)

| Metric | Definition (English) | Per-cell shape |
|---|---|---|
| VoNB ($) | NPV@15% of model-point CTFS path (Excel NPV convention) | From `By Cell (LICAT)` CTFS by year |
| VoNB (%) | VoNB ($) / Initial Premium | `Y / L` |
| Net CSM (%) | −(Time 0 Actuarial Liability − Net) / Initial Premium | `−W / L` |
| CaPM | VoNB ($) / capital-adjusted premium denominator | **PA1:** `Y / (−M + L/12)`; **else (e.g. RI1):** `Y / (−M + L)` |

**Portfolio / plan aggregates:** VoNB% = ΣY/ΣL; Net CSM% = −ΣW/ΣL; CaPM = ΣY/(ΣL−ΣM) — aggregates **do not** apply PA1 `L/12` (that split is per-cell AB only).

**Cuts required:** model point · individual (issue attributes ex plan code) · plan code · total.

### 5.2 Comparison table template (fill after Slope)

Compare **pricing / baseline** curve vs **implied / rebuilt J** on the same model-point set. Leave cells blank until real exports exist.

| Cut | Metric | Baseline | Implied | Δ (Implied − Baseline) |
|---|---|---:|---:|---:|
| Total | VoNB ($) | *[pending Slope]* | *[pending Slope]* | — |
| Total | VoNB (%) | *[pending Slope]* | *[pending Slope]* | — |
| Total | Net CSM (%) | *[pending Slope]* | *[pending Slope]* | — |
| Total | CaPM | *[pending Slope]* | *[pending Slope]* | — |
| Plan PA1 | VoNB (%) / Net CSM (%) / CaPM | *[pending]* | *[pending]* | — |
| Plan RI1 | VoNB (%) / Net CSM (%) / CaPM | *[pending]* | *[pending]* | — |

**Do not invent** VoNB / Net CSM / CaPM figures for the draft or presentation.

### 5.3 Implementation status

| Item | State |
|---|---|
| Formula transcription + local stubs | Done (`docs/memos/profitability-formula-map.md`, `pipeline/profitability_formulas.py`) |
| Checkpoint `analyse_results.py` paste | Done (self-contained; no `pipeline/` import) |
| Live Slope / CSV keys / sign reconciliation | **Blocked** on TVFI `slope_api.py` |
| Report numeric fill | **Placeholder** until exports |

### 5.4 Still unknown without real exports

Exact `load_results()` string keys; CSV header character match; reporting-date formats; CTFS vs portfolio cash-flow identity; full plan-code universe; t0 month rule; dry-run sign conventions.

---

## 6. Open review items and risks

Team / industry partner should explicitly review and sign off (`PROJECT_STATUS.md` § What needs review):

| # | Item | Risk if unresolved | Pointer |
|---|---|---|---|
| 1 | **Column H policy** — is `hold_latest_publication` acceptable? | Mid-month liquidity shocks not in J until next Fiera pub | `column-h-liquidity-premium.md` |
| 2 | **Daily RF source** — BoC zeros despite ~2-week lag? | Stale RF vs calendar; ops must trust lag badge | `daily-risk-free-source.md`, `boc-rf-lag-freshness.md` |
| 3 | **Trigger 35 bp** — ops-reasonable (~2/yr)? | Too quiet in calm regimes / too chatty if lowered blindly | `trigger-calibration.md`, `pipeline.backtest_trigger` |
| 4 | **Extrapolation past 30y** — BoC → Slope 1–100 | Mismatch vs Fiera ultimate / benefit-rate sensitivity | Builder currently mirrors Fiera ultimate behavior |
| 5 | **Dashboard KPI contract** | JS re-derives deltas inconsistently vs snapshot | Prefer `metrics_computed`; Canada-par = context only |
| 6 | **Checkpoint hygiene** | Wrong GROUP / curve path on real submission | Confirm `GROUP = 5`, root `sample_curve.xlsx` |
| 7 | **Profitability paste** | PA1 CaPM `L/12` wrong vs first real exports | Reconcile vs Slope CSVs |
| 8 | **`slope_api.py`** | No dry-run; report §5 stays empty | Blocked on TVFI |
| 9 | **BoC as default rebuilt RF** | Snapshot still Fiera RF by default | Wave 4 remaining build |

### Risks to call out in the final narrative

- **BoC lag** is structural — monitoring is “as of last published zeros,” not same-day cash markets.
- **Extrapolation** beyond 30y is a modeling choice, not an official BoC point.
- **Trigger re-calibration** needed once daily BoC→J history accumulates.
- **No Slope numbers yet** — recommendation for the *monitoring design* can stand; profitability *impact* claims cannot until exports exist.

---

## Appendix A — Quick commands

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.boc_intake
python3 -m pipeline.curve_builder --rf fiera --validate
python3 -m pipeline.curve_builder --rf boc
python3 -m pipeline.backtest_trigger
python3 -m pipeline.build_monitor_snapshot --rebuilt
cd "Dashboard UI/Group5_Monitoring_Dashboard" && python3 -m http.server 8000
# open http://127.0.0.1:8000/ in Brave
```

## Appendix B — Document map

| Deliverable piece | Draft section | Source of truth |
|---|---|---|
| Operational process doc | §2 | `PROJECT_STATUS.md` + RF / H / builder memos |
| Trigger memo | §3 | `trigger-calibration.md` |
| Col H + RF decisions | §4 | `column-h-liquidity-premium.md`, `daily-risk-free-source.md`, `boc-rf-lag-freshness.md` |
| Profitability baseline vs implied | §5 | `profitability-formula-map.md` (+ future Slope exports) |
| Presentation outline | `docs/report/presentation_outline.md` | This draft |

---

*End of Wave 4 C draft skeleton.*
