"""Assemble monitor_snapshot.json for the Group 5 dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import fiera_history as fh
from . import metrics
from . import trigger

ET = ZoneInfo("America/Toronto")
DASHBOARD_DIR = (
    Path(__file__).resolve().parents[1]
    / "Dashboard UI"
    / "Group5_Monitoring_Dashboard"
)
MONITOR_DIR = Path(__file__).resolve().parents[1] / "data" / "monitor"


def _history_rows(
    forwards: Dict[str, Dict[int, float]],
    maturities: List[int],
    *,
    last_n: int = 12,
) -> List[Dict[str, Any]]:
    dates = fh.sorted_as_of(forwards)
    if len(dates) < 2:
        return []
    window = dates[-(last_n + 1) :]
    rows: List[Dict[str, Any]] = []
    for prev, curr in zip(window, window[1:]):
        base = fh.to_percent(fh.pick_at_maturities(forwards[prev], maturities))
        new = fh.to_percent(fh.pick_at_maturities(forwards[curr], maturities))
        ch = metrics.changes_bp(base, new)
        mean = metrics.mean_signed_change_bp(ch)
        mean_abs = metrics.mean_abs_change_bp(ch)
        thr = trigger.CALIBRATED["parallel"]
        flagged = bool(mean_abs is not None and mean_abs >= thr)
        row: Dict[str, Any] = {
            "date": curr,
            "mean_shift_bp": None if mean is None else round(mean, 1),
            "flagged": flagged,
        }
        if flagged:
            row["note"] = f"primary parallel threshold (≥{thr:g} bp mean |Δ|)"
        rows.append(row)
    return rows


def build_snapshot(*, use_provisional_thresholds: bool = True) -> Dict[str, Any]:
    forwards = fh.load_forward_curves()
    canada = fh.load_canada_par_curves()
    maturities = list(fh.DISPLAY_MATURITIES)

    pricing_date, current_date, pricing_fwd, current_fwd = fh.latest_pair(forwards)
    # Current market risk-free from same publication as implied (Canada par).
    if current_date not in canada:
        raise RuntimeError(f"No Canada par curve for {current_date}")
    canada_curr = canada[current_date]

    pricing_pct = fh.to_percent(fh.pick_at_maturities(pricing_fwd, maturities))
    current_pct = fh.to_percent(fh.pick_at_maturities(canada_curr, maturities))
    implied_pct = fh.to_percent(fh.pick_at_maturities(current_fwd, maturities))

    # Trigger compares implied (updated Fiera col J) vs pricing basis (prior col J).
    change = metrics.changes_bp(pricing_pct, implied_pct)
    mean_abs = metrics.mean_abs_change_bp(change)
    max_ch, _ = metrics.max_abs_change_bp(change)
    twist = metrics.twist_2s10s_bp(maturities, change)

    rules = trigger.evaluate(
        mean_abs,
        max_ch,
        twist,
        use_provisional=use_provisional_thresholds,
    )
    assessment = trigger.overall(rules)

    now = datetime.now(ET)
    snap_id = f"Fiera-{current_date.replace('-', '')}-01"

    return {
        "_note": (
            "Built by pipeline/build_monitor_snapshot.py from archived Fiera monthly "
            "method workbooks. Pricing basis = prior month column J; current = Canada "
            "par; implied = latest column J. Trigger: calibrated primary mean |Δ| "
            "(see docs/memos/trigger-calibration.md)."
        ),
        "schema_version": "1.0",
        "snapshot_id": snap_id,
        "is_illustrative": False,
        "meta": {
            "observation_date": current_date,
            "latest_market_date": current_date,
            "market_session": "close",
            "pricing_basis_date": pricing_date,
            "source": "Fiera CIA IFRS 17 method workbook (Canada par + Illiquid col J)",
            "source_label": "Fiera monthly",
            "last_successful_update": now.isoformat(timespec="seconds"),
            "timezone_label": "ET",
            "data_availability": "CURRENT",
            "currency": "CAD",
            "yield_type": "nominal",
            "premium_policy": "hold_latest_publication",
            "premium_policy_note": (
                "Between Fiera publication dates, column H is held; daily BoC intake "
                "is not wired yet. This snapshot uses consecutive monthly publications."
            ),
        },
        "maturities": maturities,
        "curves": {
            "pricing_basis": {
                "label": "Pricing Basis Curve",
                "as_of": pricing_date,
                "series": "illiquid_annual_forward_column_J",
                "yields": pricing_pct,
            },
            "current_basis": {
                "label": "Current Basis Curve",
                "as_of": current_date,
                "series": "canada_par_market_curves",
                "yields": current_pct,
            },
            "implied": {
                "label": "Updated / Implied Curve",
                "as_of": current_date,
                "construction": (
                    "Fiera Illiquid_Ref_Curve_Construction column J "
                    "(annual forward rates at publication)"
                ),
                "construction_note": (
                    "Implied curve is Fiera's published annual forward rates for the "
                    "latest month. Production will rebuild column J daily from a "
                    "chosen Canada risk-free source + held/inferred liquidity premium."
                ),
                "series": "illiquid_annual_forward_column_J",
                "yields": implied_pct,
            },
        },
        "assessment": assessment,
        "triggers": [r.as_dict() for r in rules],
        "history": _history_rows(forwards, maturities, last_n=12),
        "data_quality": {
            "reference_basis": f"Fiera {current_date} · pricing {pricing_date}",
            "last_pipeline_run": now.isoformat(timespec="seconds"),
            "pipeline_run_simulated": False,
            "fiera_publications_used": 2,
            "history_publications": len(fh.sorted_as_of(forwards)),
        },
        "pipeline_runs": [
            {
                "id": snap_id,
                "started_at": now.isoformat(timespec="seconds"),
                "finished_at": now.isoformat(timespec="seconds"),
                "status": "ok",
                "steps": [
                    "load_fiera_history",
                    "select_latest_pair",
                    "compute_curve_metrics",
                    "evaluate_calibrated_triggers",
                    "write_monitor_snapshot",
                ],
            }
        ],
        "notes": {
            "chart_reading": (
                f"Pricing basis is Fiera column J as of {pricing_date}. "
                f"Current basis is Canada par as of {current_date}. "
                f"Implied is Fiera column J as of {current_date}. "
                "Yields are percent. Deltas are implied − pricing."
            ),
            "sam_feedback": (
                "Trigger is curve-only (no Slope) with one primary measure: mean "
                "|Δ| across display maturities. A breach starts a Slope profitability "
                "test (VoNB / Net CSM / CaPM). Maturity/twist are diagnostics only."
            ),
        },
        "metrics_computed": {
            "abs_mean_change_bp": None if mean_abs is None else round(mean_abs, 2),
            "max_abs_change_bp": None if max_ch is None else round(abs(max_ch), 2),
            "abs_twist_2s10s_bp": None if twist is None else round(abs(twist), 2),
            "primary_threshold_bp": trigger.CALIBRATED["parallel"],
            "thresholds_calibrated": use_provisional_thresholds,
            "thresholds_provisional": use_provisional_thresholds,  # legacy key
        },
    }


def write_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Path]:
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(snapshot, indent=2) + "\n"
    paths = {
        "monitor": MONITOR_DIR / "monitor_snapshot.json",
        "dashboard": DASHBOARD_DIR / "monitor_snapshot.json",
    }
    for path in paths.values():
        path.write_text(text, encoding="utf-8")
    return paths
