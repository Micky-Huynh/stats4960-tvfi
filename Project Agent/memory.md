# TVFI project memory

Working notes for the STATS 4960 yield-curve monitoring project. This file is not a deliverable and should be ignored when packaging work for TVFI.

Last updated: 2026-11-08.

## 1. What needs to be built and implemented

TVFI is launching **Secured Retirement**: guaranteed lifetime income bought in small pieces with each contribution. The **benefit rate** is the income starting at age 65 that one dollar of contribution buys. Past purchases stay locked in. Only future rates can change.

The interest-rate assumption drives those rates and can move daily. We need an operational process that sources rates, builds the curve Slope uses, decides whether the move is large enough to reprice, and shows the profitability impact. The process has to be something OSFI could review.

### Curve that Slope receives

The file Slope imports is the **annual forward rate** (column J on Fiera’s `Illiquid_Ref_Curve_Construction` sheet). It is built from:

- A **Canadian public (risk-free) yield curve**, updated daily. We source this.
- A **Fiera liquidity premium (column H)**, published monthly. This is the open piece: hold the latest publication through the month, or justify a more frequent update via the liquidity spread. Sam’s feedback says leaving column H monthly-only without analysis is not acceptable.
- **Insurer-specific parameters** in the top left of that sheet. Use the values Fiera already chose. Treat them as static. Sam confirmed these do **not** need updating; column H is the thing that might.

The daily risk-free curve should always update the annual forward rate, even when the liquidity premium is left unchanged.

Each curve sent to Slope is its own `.xlsx`: sheet `Sheet1`, columns `Policy Duration` and `Forward Rate`, durations 1 through 100, rates as annual decimals (`0.0523` for 5.23%). The filename is the curve name, and each name can be sent only once.

### Pieces to deliver

1. **Data pipeline.** Compare candidate daily Canadian yield-curve sources (coverage and methodology). **Make an explicit recommendation** (Sam’s feedback: researching many sources is not enough; pick one). Students are not expected to pay for data. Recommendations for paid/blocked sources were due Oct 9. Pull, clean, and store the chosen curve historically and going forward. Store historical monthly Fiera snapshots for back-testing and audit.
2. **Implied curve.** On any day, combine the latest risk-free curve, the Fiera liquidity premium (latest or inferred — with a defended policy for column H), and the static parameters into the annual forward curve.
3. **Change trigger.** Define “moved enough to start a profitability test.” The trigger must be a **cheap, curve-only** measure that does **not** require a Slope run. Sam rejected PV-of-liability triggers because computing PV of liability cash flows is effectively what Slope’s profitability test already does. One trigger is enough; a second “black swan / severe” level is probably unnecessary because a large move already fires the same profitability check. Back-test fire frequency and recommend one measure with trade-offs.
4. **Monitoring dashboard.** Python backend with an HTML, JavaScript, and/or CSS front end. No paid tools such as Power BI. Show the pricing curve and the current curve, the pricing and implied interest-rate curves, actuarial deltas (for example parallel shift and twist), and a status such as TRIGGERED. Sam liked the mock-up; keep that direction. The UI prototype can later sit behind a Cloudflare Worker. It is not part of the Slope scripts TVFI reruns.
5. **Slope integration and profitability.** `run_curves.py` sends the baseline curve and the new implied curve. `analyse_results.py` waits, loads the exports, and computes profitability in Python. All of our code has to live in those two scripts. Extra `.py` files of our own will not be present when TVFI reruns them. Installed libraries such as pandas are fine. Do not edit `slope_api.py`.
6. **Report and presentation.** Times New Roman 12 pt, single-spaced, 1-inch margins, at most 10 pages of body text (exhibits count; appendices do not). The report must contain a memo justifying the trigger, a profitability comparison of current benefit rates under the baseline curves versus the new or implied curves, and an operational process document. Then present the recommendation to TVFI.

### Profitability metrics

Primary metrics (Sam confirmed; columns Z–AB on `By Cell Summary` in `Example Profitability Model.xlsx`):

- VoNB (%)
- Net CSM (%)
- Capital-adjusted Profitability Margin (CaPM)

Show them for each model point, aggregated by individual (`By Cell Aggregated`), aggregated by plan code, and in total. A reasonable output is an Excel workbook with that detail, plus a short command-line summary (everything together, and by plan code).

Profitability is from the **insurer’s** perspective (not the MGA’s). Commissions appear as outflows in the sample model for that reason. Cash-flow assumptions should start from the example profitability workbook; further detail can wait for a meeting with TVFI.

Slope exports used by the existing workbook include Cash Flows, Reserves, LICAT, and the by-cell versions of those, plus Model Point Fields / CTFS by cell.

### How a checkpoint run works

```bash
python run_curves.py
python analyse_results.py
```

A local run uses dummy Slope results. Both scripts must finish without errors before we send `run_curves.py`, `analyse_results.py`, and the curve files. TVFI runs them on the real model and returns the folder. After that, `analyse_results.py` can be rerun against the reports already saved.

`run_curves.py` calls `run_slope_curve(curve_file, GROUP)` and does not wait. `GROUP` must be our group number, 1 to 5. `analyse_results.py` calls `wait_for_runs()` and `load_results()`. Only a run marked `Completed` worked. Each completed curve returns seven CSV reports.

Local artifacts, deleted to start over: `runs.csv`, `exports/`, `dry_run_state.json`.

Questions go to Sam Guan (sam.guan@tvfi.ca) and Nathan Phelps (nathan.phelps@tvfi.ca).

## 2. Industry partner feedback (progress update)

Source: `Project Progress Update Evaluation Group 5.docx`. Score: **87/100** (Work completed 52/60, Plan 26/30, Questions 9/10). Grade band: Excellent.

### What Sam liked
- Dashboard mock-up looks really good — keep that direction.
- Overall progress and plan quality were strong enough for the Excellent band.

### What Sam wants changed

1. **Liquidity premium (column H) — analyze, don’t ignore.** Holding the premium monthly-only without justification is not well supported. He wants analysis on whether monthly is enough or something more frequent is needed via the liquidity spread. Clarification: top-left Fiera parameters stay static; **column H** is the open question. (He noted terminology confusion from earlier email about “alterations to the Fiera curve” may have contributed.)
2. **Recommend a daily data source.** Lots of research is fine; he wanted an **active recommendation**. Paid/inaccessible sources were supposed to be recommended by Oct 9.
3. **Rewrite the trigger — no Slope inside the trigger.** The threshold exists to decide when to **run a Slope profitability test**. It must not itself require Slope (and must not be PV of liability cash flows, since that is how profitability/PV would be computed anyway).
4. **Drop the second “black swan” trigger.** One trigger that initiates the profitability test is enough; a severe-move second level is probably redundant.
5. **Primary profitability metrics are VoNB, Net CSM, and CaPM.** Align reporting and scripts to those three.

### Answers Sam gave to our questions
- **ML / black box:** ML is okay, but he is unsure this is the best application. If used, layer a simple fallback (e.g. if the model does not fire but the curve moved by X points, fire anyway).
- **Simplify / de-black-box:** Mostly the same guidance as above.
- **Slope vs hyperparameter tuning:** Needs a clearer explanation of what we want to do before he can answer.
- **Meeting with Nathan / developers on codebase organisation:** Yes, absolutely.
- **Equity and liability cash-flow assumptions:** Start from the example profitability workbook; more in a meeting.
- **How profitability is calculated / insurer vs MGA:** TVFI focuses on **insurer** profitability metrics.

### Feedback → open work (must address)
| Feedback item | Required response |
|---|---|
| Column H ignored | Back-test month-to-month liquidity premium / spread moves; defend hold-latest or a more frequent policy with evidence |
| No source pick | Commit to one daily Canada risk-free recommendation (ranked alternative OK) |
| PV-liability / Slope-in-trigger | Replace with a curve-only measure (parallel shift, duration-weighted forwards, shape/twist, or combo) |
| Second trigger | Remove or demote; one profitability-test trigger |
| Metrics | VoNB %, Net CSM %, CaPM only as the primary set |

## 3. What is our idea and model

Group 5: Allison Shen, Ethan Stewart, Micky Huynh, Peter (Zhiyuan) Li, Sawyer Cobham. Progress update evaluated; feedback above is binding for the plan going forward.

The monitoring UI prototype already exists under `Dashboard UI/Group5_Monitoring_Dashboard/` (static HTML/JS/CSS reading `monitor_snapshot.json`). Sam liked it. A Cloudflare Worker can host the same snapshot later. The page does not compute curves, triggers, or profitability.

### Curve model (from TVFI, not a design choice)

On the Fiera sheet `Illiquid_Ref_Curve_Construction`:

1. Start from the daily risk-free curve (Canada par / market inputs).
2. Apply Fiera’s liquidity premium (**column H**, fed by liquidity spread in column F and the additional premium in column G) to get a spot curve. Column H is the monthly input that needs a defended hold-or-update policy.
3. Keep Fiera’s parameter values in the top left of the sheet (static).
4. Export column J, Annual Forward Rate, as the Slope curve (durations 1–100).

The brief’s earlier wording treated a whole “Fiera curve” as monthly. The update corrects that: only the liquidity premium is monthly. The forward curve itself must move with the daily risk-free curve.

Fiera monthly method workbooks (Oct 2019 → Oct 2026) and extracted CSVs now live under `data/fiera/`. Use `extracted/history/liquidity_premium_*.csv` for the column H analysis Sam asked for.

### What the group is doing

Update only the Canadian risk-free inputs. On Fiera’s `Market_Curves` sheet those are annual par rates for maturities 1 to 30 (plus any short tenor Fiera uses for mid-year discounting). They feed `Illiquid_Ref_Curve_Construction`. Column J, Annual Forward Rate, is what Slope receives after we extend it from the market maturities out to policy durations 1–100.

Leave the corporate spread curve method, ultimate risk-free rate, its timing, liquidity spread **ratios**, liquidity **parameters** (top-left), and interpolation method unchanged unless TVFI says otherwise. A change in column J on a non-publication day should come from new risk-free market data (and, if we adopt a non-hold premium policy, from the defended column H update).

Daily data is the starting point. More frequent updates only if a source actually supports them. Publication lag matters as much as the label “daily.” On dates where both exist, compare our constructed curve with Fiera’s published curve.

Candidate sources — **must pick one recommendation**:

- **Bank of Canada.** Leading free candidate. Benchmark yields at selected maturities and a zero-coupon curve with wider coverage. Zero-curve schedule / lag may be too slow for true daily pricing; still credible for history and a first pipeline.
- **FXMacroData.** Daily API, sourced from the Bank of Canada. Convenient, not an independent check, and it does not by itself solve latency.
- **Trading Economics.** Possibly more frequent. API access, maturity coverage, latency, licence, and cost are not confirmed; paid/blocked path should already have been flagged by Oct 9.

If the source only has benchmark yields, do not paste them in as a full par curve. Two methods are still open: a parametric fit such as Nelson–Siegel, or a bootstrap from bond prices and cash flows when that data exists. Extrapolation past 30 years has to be named. Slope’s 100 durations are model periods, not 100 years of market data.

Pipeline once the source and the fit are chosen: retrieve, check timestamps and coverage, build par rates 1–30, apply Fiera construction with the chosen column H policy, extract column J, write the Slope workbook, and keep the inputs, timestamps, parameters, method, and checks.

### Trigger (revised after feedback)

**Rejected (do not use):** percent change in PV of liability cash flows, or any trigger that needs a Slope run.

**Direction:** one curve-only decision that answers “did the implied annual-forward curve move enough to justify a Slope profitability test?” Candidate measures to back-test:

- Parallel shift on the forward or spot curve
- Duration-weighted move across forwards 1–100 (or 1–30 + ultimate)
- Shape / twist indicator (e.g. short vs long differential)
- Combination, optionally with a simple ML layer **plus** a hard fallback threshold if ML is used

The trigger starts a review / Slope profitability run. It does not reprice by itself. TVFI’s actuary or data scientist approves a benefit-rate change.

**Do not keep a separate second “black swan” trigger** unless we have a strong new reason; Sam said it is probably unnecessary.

Calibration plan: historical curves (BoC and/or Fiera publication days), reset the reference when TVFI reprices, try several thresholds, walk-forward and synthetic parallel/shape moves, and stress 2008 and COVID. State limits clearly in the trigger memo.

### Dashboard

Static prototype exists at `Dashboard UI/Group5_Monitoring_Dashboard/`. It loads `monitor_snapshot.json`, derives display metrics, and renders Overview / Maturity views. It does **not** evaluate triggers or build curves. Sam liked the mock — keep the visual direction; later wire real pipeline output (and optionally a Cloudflare Worker URL) into `snapshotUrl`.

### Profitability

Extend `run_curves.py` to submit the baseline and the updated forward curve, durations 1–100. Extend `analyse_results.py` to compare them. Hold model points, business mix, and every assumption except the interest curve. Keep the 15% risk discount rate fixed where the workbook uses it for VoNB.

**Primary metrics (locked by feedback):** VoNB (%), Net CSM (%), Capital-adjusted Profitability Margin. Report by model point, by individual, by plan code, and total. CTFS and reserve detail can support explanation but are not the primary headline set.

Explain moves with best-estimate reserve items where useful: PV of lifetime income, future premiums, commissions, expenses, longevity-swap premiums. Split PA1 (regular premium) and RI1 (roll-in). RI1 has no future-premium offset in the sample. Profitability is insurer-view.

Dummy Slope runs only prove the scripts finish. Reconcile formulas to `Example Profitability Model.xlsx`. Read profitability off real Slope results when TVFI returns them.

### Questions still open with TVFI
- Clearer write-up of any Slope / calibration interaction if we still want that answered.
- Meeting with Nathan (approved) on docs expectations and codebase limits.
- Remaining cash-flow / reserve questions after we dig through the example profitability workbook.

### Choices still open

- **Daily source.** Must become a firm recommendation soon (BoC is the default free lead).
- **Column H policy.** Hold-latest vs more frequent update via liquidity spread — needs the analysis Sam asked for; history CSVs are ready under `data/fiera/extracted/history/`.
- **How to fill maturities 1–30** when the source is only benchmarks, and how to extrapolate to duration 100.
- **Single trigger measure and threshold.** Curve-only; numbers not chosen; second severe trigger dropped unless newly justified.
- **Group number in the script.** We are group 5. `GROUP` in `run_curves.py` is set to 5. Dry runs still need TVFI’s `slope_api.py` (not invented locally).

## 4. What is built and implemented

| Path | State |
|---|---|
| `README.md` | Slope workflow: curve file format, the three API calls, dry-run check, checkpoint rules. |
| `run_curves.py` | Starter path fixed: `sample_curve.xlsx` at project root, `GROUP = 5`. Dry runs still need TVFI’s `slope_api.py`. |
| `analyse_results.py` | Starter only. Waits, loads results, and prints row and column counts. No profitability math yet. |
| `sample_curve.xlsx` | Valid example curve at project root. Sheet `Sheet1`, durations 1–100, forwards from about 3.26% to 5.15% (matches Fiera ultimate forward level). |
| `Example Profitability Model.xlsx` | TVFI’s Excel process. Formulas for VoNB / Net CSM / CaPM decoded; primary metrics confirmed by Sam. |
| `TVFI Yield Curve Monitoring Project Brief.docx` | Original brief. |
| `Updated Project Information.docx` | Corrections: liquidity premium is the monthly piece, dashboard must be free and web-based, profitability cuts listed above. |
| `Project Progress Update Evaluation Group 5.docx` | Sam’s scored feedback (87/100) — see §2. |
| `slope_api.py` | Not in the folder. Both scripts import it, so they cannot run until it is added. Do not modify it once it is here. |
| `pipeline/` | **Built (local).** Fiera history → curve metrics → provisional trigger → `monitor_snapshot.json` for the dashboard. |
| `data/monitor/monitor_snapshot.json` | Latest dashboard snapshot (also copied into the dashboard folder). |
| `data/fiera/` | **Built.** 85 monthly method workbooks (2019-10 → 2026-10), implementation note PDF, extracted latest CSVs, and cross-month liquidity-premium / Canada-par / parameter history. See `data/README.md`. |
| Data pipeline (daily risk-free intake) | Not started. |
| Curve builder (reproduce column J) | Not started. |
| Trigger (curve-only, post-feedback) | Not started — prior PV-liability idea is withdrawn. |
| Profitability script | Not started. |
| `Dashboard UI/Group5_Monitoring_Dashboard/` | **Built.** Prototype + live snapshot from `python3 -m pipeline.build_monitor_snapshot` (Fiera monthly → `monitor_snapshot.json`). |
| `Project Architect/architecture.md` | Working architecture notes. Not a deliverable. Align trigger section with Sam’s feedback when next edited. |
| `Software Architecture/data-flow.md` | Mermaid diagram of the one-day monitor flow. Not a deliverable. |

Remaining blocker before a dry run:

- `slope_api.py` is missing, so `from slope_api import ...` fails. Do not invent it; wait for TVFI’s file. `run_curves.py` already uses root `sample_curve.xlsx` and `GROUP = 5`.

### Suggested next build order (post-feedback)

1. Analyze column H history and write the liquidity-premium policy recommendation.
2. Recommend one daily risk-free source.
3. Implement curve builder against a Fiera publication day (diff column J).
4. Implement one curve-only trigger + historical fire-rate back-test.
5. Obtain `slope_api.py` (sample path / `GROUP` already fixed), wire profitability (VoNB / Net CSM / CaPM) into `analyse_results.py`.
6. Emit real `monitor_snapshot.json` into the existing dashboard; package report and presentation.
