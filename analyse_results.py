#!/usr/bin/env python3
"""Step 2: wait for Slope runs, load CSV exports, compute profitability metrics.

Auditors: VoNB (%) / Net CSM (%) / CaPM formulas are transcribed from
docs/memos/profitability-formula-map.md (Example Profitability Model.xlsx).
Local development copy of the same helpers lives in pipeline/profitability_formulas.py;
this script pastes them inline so the TVFI checkpoint zip needs no pipeline/ package.

    wait_for_runs()
    results = load_results()
    # results[curve] maps report name -> Path to CSV
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from slope_api import wait_for_runs, load_results

# ---------------------------------------------------------------------------
# Pasted profitability helpers (keep in sync with pipeline/profitability_formulas.py)
# ---------------------------------------------------------------------------

RISK_DISCOUNT_RATE = 0.15  # CTFS by cell!B1 / Business Mix Summary VoNB @ 15%

INDIVIDUAL_KEYS = (
    "issue_age",
    "collar_type",
    "sex",
    "deferral_period_in_months",
    "guarantee_period",
    "spousal_indicator",
    "spousal_benefit_pct",
    "salary_inflation",
    "benefit_inflation",
)

EXPECTED_SLOPE_SHEETS = (
    "Cash Flows",
    "Reserves",  # README may label this "Liabilities"; confirm on first real export
    "LICAT",
    "By Cell (Reserves)",
    "By Cell (LICAT)",
    "By Cell (CFs)",
    "Model Point Fields",
)

# Canonical field names used in workbook formulas → alternate CSV header spellings.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "Model Point Record #": (
        "Model Point Record #",
        "Model Point Record Number",
        "Model Point #",
        "Model Point ID",
        "model_point",
    ),
    "Reporting Date": ("Reporting Date", "Report Date", "Valuation Date", "Date"),
    "CTFS": ("CTFS", "Contribution to Free Surplus", "CtFS"),
    "PV (Gross Premiums)": (
        "PV (Gross Premiums)",
        "PV(Gross Premiums)",
        "PV Gross Premiums",
        "PV (Premium)",
        "PV Premium",
    ),
    "Time 0 Actuarial Liability - Net": (
        "Time 0 Actuarial Liability - Net",
        "Time 0 Actuarial Liability − Net",
        "Time 0 Actuarial Liability-Net",
        "T0 Actuarial Liability - Net",
        "Time 0 AL - Net",
    ),
    "Field Name": ("Field Name", "Name", "field_name"),
    "Field Value": ("Field Value", "Value", "field_value"),
}

MP_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "plan_code": ("Plan Code", "PlanCode", "plan_code"),
    "initial_premium": ("Initial Premium", "InitialPremium", "initial_premium"),
    "issue_age": ("Issue Age", "IssueAge", "issue_age"),
    "collar_type": ("Collar Type", "CollarType", "collar_type"),
    "sex": ("Sex", "Gender", "sex"),
    "deferral_period_in_months": (
        "Deferral Period In Months",
        "Deferral Period",
        "deferral_period_in_months",
    ),
    "guarantee_period": ("Guarantee Period", "guarantee_period"),
    "spousal_indicator": ("Spousal Indicator", "spousal_indicator"),
    "spousal_benefit_pct": (
        "Spousal Benefit %",
        "Spousal Benefit Pct",
        "spousal_benefit_pct",
    ),
    "salary_inflation": ("Salary Inflation", "salary_inflation"),
    "benefit_inflation": ("Benefit Inflation", "benefit_inflation"),
}


def excel_npv(rate: float, cashflows: Sequence[float]) -> float:
    """Match Excel NPV: first cash flow is discounted by one period."""
    total = 0.0
    for i, cf in enumerate(cashflows, start=1):
        total += float(cf) / ((1.0 + rate) ** i)
    return total


def vonb_dollars_from_ctfs(
    ctfs_by_year: Sequence[float],
    rate: float = RISK_DISCOUNT_RATE,
) -> float:
    """VoNB ($) from an ordered CTFS path (By Cell (LICAT) col CTFS → NPV@rate)."""
    return excel_npv(rate, ctfs_by_year)


def vonb_pct(vonb_dollars: float, initial_premium: float) -> float:
    """By Cell Summary!Z = Y / L."""
    return vonb_dollars / initial_premium


def net_csm_pct(t0_al_net: float, initial_premium: float) -> float:
    """By Cell Summary!AA = -W / L."""
    return -t0_al_net / initial_premium


def capm_denominator(
    initial_premium: float,
    pv_premium: float,
    plan_code: str,
    *,
    per_cell: bool = True,
) -> float:
    """
    Per-cell AB: PA1 -> -M + L/12; else -> -M + L.
    Aggregates / AB3: always L - M (== -M + L); ignore plan_code when per_cell=False.
    """
    if per_cell and plan_code == "PA1":
        return -pv_premium + initial_premium / 12.0
    return -pv_premium + initial_premium


def capm(
    vonb_dollars: float,
    initial_premium: float,
    pv_premium: float,
    plan_code: str,
    *,
    per_cell: bool = True,
) -> float:
    """By Cell Summary!AB (per_cell=True) or aggregate CaPM (per_cell=False)."""
    return vonb_dollars / capm_denominator(
        initial_premium, pv_premium, plan_code, per_cell=per_cell
    )


def ratio_of_sums(
    numerator: float,
    denominator: float,
    *,
    on_zero: Optional[float] = None,
) -> Optional[float]:
    if denominator == 0:
        return on_zero
    return numerator / denominator


def per_cell_metrics(
    *,
    vonb_dollars: float,
    initial_premium: float,
    pv_premium: float,
    t0_al_net: float,
    plan_code: str,
) -> dict[str, float]:
    """Decode By Cell Summary Y/Z/AA/AB for one model point."""
    return {
        "vonb_$": vonb_dollars,
        "vonb_pct": vonb_pct(vonb_dollars, initial_premium),
        "net_csm_pct": net_csm_pct(t0_al_net, initial_premium),
        "capm": capm(
            vonb_dollars, initial_premium, pv_premium, plan_code, per_cell=True
        ),
    }


def aggregate_metrics(
    rows: Iterable[Mapping[str, Any]],
    *,
    on_zero: Optional[float] = None,
) -> dict[str, Optional[float]]:
    """
    Ratio-of-sums for portfolio / plan / individual cuts.

    Each row needs: vonb_$, initial_premium, pv_premium, t0_al_net.
    CaPM uses (ΣL - ΣM) — no PA1 L/12 (matches AB3 / Aggregated!N).
    """
    sum_y = 0.0
    sum_l = 0.0
    sum_m = 0.0
    sum_w = 0.0
    for r in rows:
        sum_y += float(r["vonb_$"])
        sum_l += float(r["initial_premium"])
        sum_m += float(r["pv_premium"])
        sum_w += float(r["t0_al_net"])
    return {
        "vonb_$": sum_y,
        "vonb_pct": ratio_of_sums(sum_y, sum_l, on_zero=on_zero),
        "net_csm_pct": ratio_of_sums(-sum_w, sum_l, on_zero=on_zero),
        "capm": ratio_of_sums(sum_y, sum_l - sum_m, on_zero=on_zero),
    }


def group_by_plan_code(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(r.get("plan_code", ""))].append(r)
    return dict(grouped)


def group_individuals(
    rows: Iterable[Mapping[str, Any]],
    keys: Sequence[str] = INDIVIDUAL_KEYS,
) -> dict[tuple[Any, ...], list[Mapping[str, Any]]]:
    """By Cell Aggregated grain: same underwriting attributes, PA1+RI1 combined."""
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        key = tuple(r.get(k) for k in keys)
        grouped[key].append(r)
    return dict(grouped)


def summarize_cuts(
    model_point_rows: Sequence[Mapping[str, Any]],
    *,
    on_zero: Optional[float] = 0.0,
) -> dict[str, Any]:
    """Convenience: total + by plan code + by individual attribute tuple."""
    by_plan = {
        plan: aggregate_metrics(group, on_zero=on_zero)
        for plan, group in group_by_plan_code(model_point_rows).items()
    }
    by_individual = {
        key: aggregate_metrics(group, on_zero=on_zero)
        for key, group in group_individuals(model_point_rows).items()
    }
    return {
        "total": aggregate_metrics(model_point_rows, on_zero=on_zero),
        "by_plan_code": by_plan,
        "by_individual": by_individual,
    }


def map_result_keys(result_files: Mapping[str, Any]) -> dict[str, str]:
    """
    Best-effort name alignment. Call once with a real load_results()[curve] dict.
    Does not invent schemas beyond workbook sheet names.
    """
    available = {str(k): str(k) for k in result_files}
    aliases = {
        "Reserves": ("Reserves", "Liabilities"),
        "Cash Flows": ("Cash Flows",),
        "LICAT": ("LICAT",),
        "By Cell (Reserves)": ("By Cell (Reserves)",),
        "By Cell (LICAT)": ("By Cell (LICAT)",),
        "By Cell (CFs)": ("By Cell (CFs)",),
        "Model Point Fields": ("Model Point Fields",),
    }
    mapped: dict[str, str] = {}
    for canonical, options in aliases.items():
        for opt in options:
            if opt in available:
                mapped[canonical] = opt
                break
    return mapped


def build_ctfs_series_by_model_point(
    licat_by_cell_rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str = "Reporting Date",
    mp_key: str = "Model Point Record #",
    ctfs_key: str = "CTFS",
) -> dict[Any, list[float]]:
    """
    Pivot By Cell (LICAT) CTFS into ordered yearly series per model point.
    Years sorted ascending; caller pads/truncates to the horizon used in NPV.
    """
    buckets: dict[Any, list[tuple[Any, float]]] = defaultdict(list)
    for row in licat_by_cell_rows:
        buckets[row[mp_key]].append((row[date_key], float(row[ctfs_key])))
    series: dict[Any, list[float]] = {}
    for mp, pairs in buckets.items():
        pairs.sort(key=lambda x: str(x[0]))
        series[mp] = [cf for _, cf in pairs]
    return series


# ---------------------------------------------------------------------------
# CSV I/O and resilient column mapping
# ---------------------------------------------------------------------------


def _try_import_pandas():
    try:
        import pandas as pd  # type: ignore

        return pd
    except ImportError:
        return None


def _try_import_openpyxl():
    try:
        from openpyxl import Workbook  # type: ignore

        return Workbook
    except ImportError:
        return None


def resolve_header(headers: Sequence[str], canonical: str) -> Optional[str]:
    """Return the actual header string matching a canonical name, or None."""
    lookup = {h.strip(): h for h in headers if h is not None}
    lowered = {h.strip().lower(): h for h in headers if h is not None}
    for alias in HEADER_ALIASES.get(canonical, (canonical,)):
        if alias in lookup:
            return lookup[alias]
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return None


def resolve_headers(
    headers: Sequence[str], needed: Sequence[str]
) -> tuple[dict[str, str], list[str]]:
    """Map canonical -> actual header; return missing canonical names."""
    found: dict[str, str] = {}
    missing: list[str] = []
    for name in needed:
        actual = resolve_header(headers, name)
        if actual is None:
            missing.append(name)
        else:
            found[name] = actual
    return found, missing


def read_csv_dicts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return headers, rows


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return default
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return default


def pivot_model_point_fields(
    rows: Iterable[Mapping[str, str]],
    *,
    mp_col: str,
    name_col: str,
    value_col: str,
) -> dict[Any, dict[str, Any]]:
    """Long Model Point Fields → one dict per model point with known attributes."""
    # Build reverse map: workbook field label -> internal key
    label_to_key: dict[str, str] = {}
    for key, aliases in MP_FIELD_ALIASES.items():
        for alias in aliases:
            label_to_key[alias.lower()] = key

    out: dict[Any, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        mp = row.get(mp_col)
        if mp is None or str(mp).strip() == "":
            continue
        field = str(row.get(name_col, "")).strip()
        value = row.get(value_col, "")
        internal = label_to_key.get(field.lower())
        if internal is None:
            continue
        if internal == "initial_premium":
            out[mp][internal] = _to_float(value)
        else:
            out[mp][internal] = value
    return dict(out)


def t0_reserves_by_model_point(
    rows: Iterable[Mapping[str, str]],
    *,
    date_col: str,
    mp_col: str,
    pv_col: str,
    al_col: str,
) -> dict[Any, dict[str, float]]:
    """
    Attach PV(Premium) and T0 AL Net at the minimum / issue reporting month.
    Do not hard-code 2026 — use chronologically first YYYY-MM (or any date string).
    """
    by_mp: dict[Any, list[tuple[str, float, float]]] = defaultdict(list)
    for row in rows:
        mp = row.get(mp_col)
        if mp is None or str(mp).strip() == "":
            continue
        date = str(row.get(date_col, "")).strip()
        pv = _to_float(row.get(pv_col))
        al = _to_float(row.get(al_col))
        by_mp[mp].append((date, pv, al))

    out: dict[Any, dict[str, float]] = {}
    for mp, triples in by_mp.items():
        triples.sort(key=lambda t: t[0])
        date, pv, al = triples[0]
        out[mp] = {"pv_premium": pv, "t0_al_net": al, "t0_date": date}  # type: ignore[dict-item]
    return out


def build_model_point_rows(
    mp_attrs: Mapping[Any, Mapping[str, Any]],
    ctfs_series: Mapping[Any, Sequence[float]],
    reserves_t0: Mapping[Any, Mapping[str, Any]],
    *,
    messages: list[str],
) -> list[dict[str, Any]]:
    """Join attributes + VoNB($) + reserves into per-cell metric rows."""
    mps = sorted(
        set(mp_attrs) | set(ctfs_series) | set(reserves_t0),
        key=lambda x: str(x),
    )
    rows: list[dict[str, Any]] = []
    skipped = 0
    for mp in mps:
        attrs = dict(mp_attrs.get(mp, {}))
        plan_code = str(attrs.get("plan_code", "") or "")
        initial_premium = attrs.get("initial_premium")
        series = ctfs_series.get(mp)
        res = reserves_t0.get(mp)

        missing_bits = []
        if initial_premium is None:
            missing_bits.append("Initial Premium")
        if series is None:
            missing_bits.append("CTFS series")
        if res is None:
            missing_bits.append("t0 reserves (PV Premium / T0 AL Net)")
        if missing_bits:
            skipped += 1
            messages.append(
                f"  skip model point {mp}: missing {', '.join(missing_bits)}"
            )
            continue

        vonb_dollars = vonb_dollars_from_ctfs(series)
        pv_premium = float(res["pv_premium"])
        t0_al_net = float(res["t0_al_net"])
        metrics = per_cell_metrics(
            vonb_dollars=vonb_dollars,
            initial_premium=float(initial_premium),
            pv_premium=pv_premium,
            t0_al_net=t0_al_net,
            plan_code=plan_code,
        )
        row = {
            "model_point": mp,
            "plan_code": plan_code,
            "initial_premium": float(initial_premium),
            "pv_premium": pv_premium,
            "t0_al_net": t0_al_net,
            "t0_date": res.get("t0_date"),
            **{k: attrs.get(k) for k in INDIVIDUAL_KEYS},
            **metrics,
        }
        rows.append(row)

    if skipped:
        messages.append(
            f"  joined {len(rows)} model points; skipped {skipped} with incomplete inputs"
        )
    return rows


def analyse_curve_files(
    curve: str,
    files: Mapping[str, Any],
) -> tuple[Optional[dict[str, Any]], list[str]]:
    """
    Compute profitability for one curve's seven CSVs.
    Returns (payload or None, log messages). Never raises on missing columns.
    """
    messages: list[str] = []
    key_map = map_result_keys(files)
    available = sorted(str(k) for k in files)
    messages.append(f"[{curve}] available reports: {available}")
    messages.append(f"[{curve}] mapped keys: {key_map or '(none)'}")

    required = ("Model Point Fields", "By Cell (LICAT)", "By Cell (Reserves)")
    missing_sheets = [name for name in required if name not in key_map]
    if missing_sheets:
        messages.append(
            f"[{curve}] SKIP profitability: missing required reports {missing_sheets}. "
            f"Need Model Point Fields + By Cell (LICAT) + By Cell (Reserves)."
        )
        return None, messages

    # --- Model Point Fields ---
    mp_path = Path(files[key_map["Model Point Fields"]])
    mp_headers, mp_rows = read_csv_dicts(mp_path)
    mp_needed = ("Model Point Record #", "Field Name", "Field Value")
    mp_cols, mp_missing = resolve_headers(mp_headers, mp_needed)
    if mp_missing:
        messages.append(
            f"[{curve}] SKIP: Model Point Fields missing columns {mp_missing}; "
            f"have {mp_headers}"
        )
        return None, messages
    mp_attrs = pivot_model_point_fields(
        mp_rows,
        mp_col=mp_cols["Model Point Record #"],
        name_col=mp_cols["Field Name"],
        value_col=mp_cols["Field Value"],
    )
    if not mp_attrs:
        messages.append(
            f"[{curve}] SKIP: Model Point Fields had no recognised field names "
            f"(expected Plan Code / Initial Premium / …). Headers OK but values unmapped."
        )
        return None, messages

    # --- By Cell (LICAT) → CTFS series ---
    licat_path = Path(files[key_map["By Cell (LICAT)"]])
    licat_headers, licat_rows_raw = read_csv_dicts(licat_path)
    licat_needed = ("Model Point Record #", "Reporting Date", "CTFS")
    licat_cols, licat_missing = resolve_headers(licat_headers, licat_needed)
    if licat_missing:
        messages.append(
            f"[{curve}] SKIP: By Cell (LICAT) missing columns {licat_missing}; "
            f"have {licat_headers}"
        )
        return None, messages
    licat_rows = []
    for row in licat_rows_raw:
        licat_rows.append(
            {
                "Model Point Record #": row[licat_cols["Model Point Record #"]],
                "Reporting Date": row[licat_cols["Reporting Date"]],
                "CTFS": _to_float(row[licat_cols["CTFS"]]),
            }
        )
    ctfs_series = build_ctfs_series_by_model_point(licat_rows)
    if not ctfs_series:
        messages.append(f"[{curve}] SKIP: By Cell (LICAT) produced empty CTFS series")
        return None, messages

    # --- By Cell (Reserves) → t0 PV premium + T0 AL Net ---
    res_path = Path(files[key_map["By Cell (Reserves)"]])
    res_headers, res_rows_raw = read_csv_dicts(res_path)
    res_needed = (
        "Model Point Record #",
        "Reporting Date",
        "PV (Gross Premiums)",
        "Time 0 Actuarial Liability - Net",
    )
    res_cols, res_missing = resolve_headers(res_headers, res_needed)
    if res_missing:
        messages.append(
            f"[{curve}] SKIP: By Cell (Reserves) missing columns {res_missing}; "
            f"have {res_headers}"
        )
        return None, messages
    reserves_t0 = t0_reserves_by_model_point(
        res_rows_raw,
        date_col=res_cols["Reporting Date"],
        mp_col=res_cols["Model Point Record #"],
        pv_col=res_cols["PV (Gross Premiums)"],
        al_col=res_cols["Time 0 Actuarial Liability - Net"],
    )
    if not reserves_t0:
        messages.append(f"[{curve}] SKIP: By Cell (Reserves) had no usable t0 rows")
        return None, messages

    cell_rows = build_model_point_rows(
        mp_attrs, ctfs_series, reserves_t0, messages=messages
    )
    if not cell_rows:
        messages.append(
            f"[{curve}] SKIP: could not join any complete model-point rows "
            "(dry-run CSVs often lack matching headers / field names)"
        )
        return None, messages

    cuts = summarize_cuts(cell_rows, on_zero=0.0)
    messages.append(
        f"[{curve}] computed metrics for {len(cell_rows)} model points; "
        f"plan codes={sorted(cuts['by_plan_code'])}"
    )
    payload = {
        "curve": curve,
        "model_points": cell_rows,
        "cuts": cuts,
        "risk_discount_rate": RISK_DISCOUNT_RATE,
    }
    return payload, messages


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * value:8.3f}%"


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:12.4f}"


def print_summary(payload: Mapping[str, Any], *, dry_run_hint: bool = False) -> None:
    curve = payload["curve"]
    cuts = payload["cuts"]
    total = cuts["total"]
    print(f"\n=== Profitability summary: {curve} ===")
    if dry_run_hint:
        print(
            "  NOTE: if these CSVs came from a local dry run, figures are random — "
            "not findings."
        )
    print(f"  Risk discount rate: {100 * RISK_DISCOUNT_RATE:.0f}%")
    print(
        f"  TOTAL   VoNB($)={_fmt_num(total['vonb_$'])}  "
        f"VoNB%={_fmt_pct(total['vonb_pct'])}  "
        f"NetCSM%={_fmt_pct(total['net_csm_pct'])}  "
        f"CaPM={_fmt_pct(total['capm'])}"
    )
    print("  By plan code:")
    for plan, metrics in sorted(cuts["by_plan_code"].items(), key=lambda x: x[0]):
        label = plan if plan else "(blank)"
        print(
            f"    {label:<8} VoNB($)={_fmt_num(metrics['vonb_$'])}  "
            f"VoNB%={_fmt_pct(metrics['vonb_pct'])}  "
            f"NetCSM%={_fmt_pct(metrics['net_csm_pct'])}  "
            f"CaPM={_fmt_pct(metrics['capm'])}"
        )


def _output_dir() -> Path:
    for candidate in (Path("exports"), Path("results")):
        if candidate.is_dir():
            return candidate
    out = Path("exports")
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_results_workbook(
    payloads: Sequence[Mapping[str, Any]],
    path: Path,
) -> Optional[Path]:
    """Write Excel via openpyxl, else CSV summaries. Returns written path or None."""
    Workbook = _try_import_openpyxl()
    pd = _try_import_pandas()

    if Workbook is not None:
        wb = Workbook()
        # --- Summary sheet ---
        ws = wb.active
        ws.title = "Summary"
        ws.append(
            [
                "Curve",
                "Cut",
                "Key",
                "VoNB_$",
                "VoNB_pct",
                "Net_CSM_pct",
                "CaPM",
                "n_model_points",
            ]
        )
        for payload in payloads:
            curve = payload["curve"]
            cuts = payload["cuts"]
            total = cuts["total"]
            n = len(payload["model_points"])
            ws.append(
                [
                    curve,
                    "total",
                    "",
                    total["vonb_$"],
                    total["vonb_pct"],
                    total["net_csm_pct"],
                    total["capm"],
                    n,
                ]
            )
            for plan, metrics in sorted(cuts["by_plan_code"].items()):
                ws.append(
                    [
                        curve,
                        "plan_code",
                        plan,
                        metrics["vonb_$"],
                        metrics["vonb_pct"],
                        metrics["net_csm_pct"],
                        metrics["capm"],
                        None,
                    ]
                )

        # --- Per model point ---
        ws_mp = wb.create_sheet("By Model Point")
        mp_headers = [
            "curve",
            "model_point",
            "plan_code",
            "initial_premium",
            "pv_premium",
            "t0_al_net",
            "vonb_$",
            "vonb_pct",
            "net_csm_pct",
            "capm",
        ]
        ws_mp.append(mp_headers)
        for payload in payloads:
            for row in payload["model_points"]:
                ws_mp.append(
                    [
                        payload["curve"],
                        row.get("model_point"),
                        row.get("plan_code"),
                        row.get("initial_premium"),
                        row.get("pv_premium"),
                        row.get("t0_al_net"),
                        row.get("vonb_$"),
                        row.get("vonb_pct"),
                        row.get("net_csm_pct"),
                        row.get("capm"),
                    ]
                )

        # --- By individual ---
        ws_ind = wb.create_sheet("By Individual")
        ws_ind.append(
            ["curve", "individual_key", "VoNB_$", "VoNB_pct", "Net_CSM_pct", "CaPM"]
        )
        for payload in payloads:
            for key, metrics in payload["cuts"]["by_individual"].items():
                ws_ind.append(
                    [
                        payload["curve"],
                        str(key),
                        metrics["vonb_$"],
                        metrics["vonb_pct"],
                        metrics["net_csm_pct"],
                        metrics["capm"],
                    ]
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
        return path

    # Fallback: CSV summaries (stdlib or pandas)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = path.with_suffix(".summary.csv")
    mp_path = path.with_name(path.stem + "_model_points.csv")

    summary_rows = []
    mp_rows = []
    for payload in payloads:
        curve = payload["curve"]
        total = payload["cuts"]["total"]
        summary_rows.append(
            {
                "curve": curve,
                "cut": "total",
                "key": "",
                "vonb_$": total["vonb_$"],
                "vonb_pct": total["vonb_pct"],
                "net_csm_pct": total["net_csm_pct"],
                "capm": total["capm"],
            }
        )
        for plan, metrics in sorted(payload["cuts"]["by_plan_code"].items()):
            summary_rows.append(
                {
                    "curve": curve,
                    "cut": "plan_code",
                    "key": plan,
                    "vonb_$": metrics["vonb_$"],
                    "vonb_pct": metrics["vonb_pct"],
                    "net_csm_pct": metrics["net_csm_pct"],
                    "capm": metrics["capm"],
                }
            )
        for row in payload["model_points"]:
            mp_rows.append({"curve": curve, **{k: row.get(k) for k in (
                "model_point",
                "plan_code",
                "initial_premium",
                "pv_premium",
                "t0_al_net",
                "vonb_$",
                "vonb_pct",
                "net_csm_pct",
                "capm",
            )}})

    if pd is not None:
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        pd.DataFrame(mp_rows).to_csv(mp_path, index=False)
    else:
        if summary_rows:
            with summary_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
                writer.writeheader()
                writer.writerows(summary_rows)
        if mp_rows:
            with mp_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(mp_rows[0].keys()))
                writer.writeheader()
                writer.writerows(mp_rows)

    print(f"  openpyxl unavailable — wrote CSV summaries: {summary_path}, {mp_path}")
    return summary_path


def _looks_like_dry_run(results: Mapping[str, Any]) -> bool:
    """Heuristic: local dry-run artifacts often sit under exports/ with dry_run_state."""
    if Path("dry_run_state.json").exists():
        return True
    for files in results.values():
        for path in files.values():
            p = Path(path)
            if "dry" in p.as_posix().lower():
                return True
    return False


def print_inventory(curve: str, status: Any, files: Mapping[str, Any]) -> None:
    print(f"\n{curve} ({status})")
    for name, path in files.items():
        path = Path(path)
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
            ncols = len(rows[0]) if rows else 0
            nrows = max(len(rows) - 1, 0)
            print(f"  {name:<22} {nrows:>6} rows  {ncols:>3} columns  {path}")
        except OSError as exc:
            print(f"  {name:<22} (unreadable: {exc})")


def main() -> int:
    statuses = wait_for_runs()
    results = load_results()
    dry_hint = _looks_like_dry_run(results)

    payloads: list[dict[str, Any]] = []
    for curve, files in results.items():
        status = statuses.get(curve, "unknown") if isinstance(statuses, Mapping) else statuses
        print_inventory(curve, status, files)

        status_text = str(status)
        if status_text and status_text.lower() not in {
            "completed",
            "complete",
            "success",
            "ok",
            "unknown",
            "",
        }:
            # Non-completed runs: still inventory, skip metrics.
            if "complet" not in status_text.lower():
                print(f"  SKIP profitability: run status is {status_text!r}")
                continue

        payload, messages = analyse_curve_files(curve, files)
        for line in messages:
            print(f"  {line}" if not line.startswith("[") else f"  {line}")
        if payload is None:
            continue
        print_summary(payload, dry_run_hint=dry_hint)
        payloads.append(payload)

    if payloads:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = _output_dir() / f"profitability_summary_{stamp}.xlsx"
        written = write_results_workbook(payloads, out)
        if written is not None:
            print(f"\nWrote results: {written}")
    else:
        print(
            "\nNo profitability metrics written. "
            "Required columns were missing or no completed curves joined cleanly. "
            "Re-run once slope_api dry-run / real exports expose "
            "Model Point Fields, By Cell (LICAT) [CTFS], and By Cell (Reserves) "
            "[PV (Gross Premiums), Time 0 Actuarial Liability - Net]."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
