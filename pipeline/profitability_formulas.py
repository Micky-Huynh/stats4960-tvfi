"""Pure profitability helpers transcribed from Example Profitability Model.xlsx.

Local source of truth only. Slope checkpoint packaging must NOT import this module;
paste the needed functions into analyse_results.py before a TVFI dry run.

See docs/memos/profitability-formula-map.md for Excel references (Y/Z/AA/AB).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence

RISK_DISCOUNT_RATE = 0.15  # CTFS by cell!B1 / Business Mix Summary VoNB @ 15%

# Attribute keys used by By Cell Aggregated (individual cut), excluding Plan Code.
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


# --- CSV wiring stubs (fill after load_results() keys/headers are known) ---

EXPECTED_SLOPE_SHEETS = (
    "Cash Flows",
    "Reserves",  # README may label this "Liabilities"; confirm on first real export
    "LICAT",
    "By Cell (Reserves)",
    "By Cell (LICAT)",
    "By Cell (CFs)",
    "Model Point Fields",
)


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
