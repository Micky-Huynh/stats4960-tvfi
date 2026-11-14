"""Mode-specific implied-curve assembly for monitor snapshots.

Keeps ``snapshot.build_snapshot`` focused on loading bases, computing metrics,
and assembling the JSON body — rebuilt vs fixture branching lives here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from . import curve_builder
from . import fiera_history as fh

ROOT = Path(__file__).resolve().parents[1]
CURVES_DIR = ROOT / "data" / "curves"

RfMode = Literal["auto", "boc", "fiera"]


@dataclass(frozen=True)
class ModeParts:
    """Pieces that differ between fixture_archive and rebuilt modes."""

    implied_pct: List[Optional[float]]
    implied_fwd: Dict[int, float]
    current_date: str
    canada_as_of: str
    current_pct: List[Optional[float]]
    construction_meta: Dict[str, Any]
    pipeline_steps: List[str]
    note: str
    chart_implied: str
    source_label: str
    premium_note: str
    snap_suffix: str
    implied_construction: str
    implied_construction_note: str
    implied_series: str


def write_construction_record(built: Dict[str, Any]) -> Path:
    """Persist a small construction pointer next to Slope curve outputs."""
    CURVES_DIR.mkdir(parents=True, exist_ok=True)
    as_of = str(built["as_of"])
    path = CURVES_DIR / f"construction_record_{as_of}.json"
    record = {
        "as_of": as_of,
        "rf_source": built["rf_source"],
        "rf_as_of": built.get("rf_as_of", as_of),
        "premium_policy": built["premium_policy"],
        "premium_as_of": as_of,
        "params_as_of": built.get("params_as_of"),
        "lag_note": built.get("lag_note"),
        "xlsx_path": str(built["xlsx_path"]),
        "csv_path": str(built["csv_path"]),
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def select_rebuilt_build(
    *,
    rebuilt_as_of: Optional[str],
    rf: RfMode,
    boc_snapshot: Optional[Path],
) -> tuple[Dict[str, Any], Optional[str]]:
    """Build rebuilt column J, preferring BoC RF when available.

    Returns ``(built, rf_fallback_note)``. ``rf_fallback_note`` is set when
    ``rf="auto"`` falls back to Fiera fixture RF because no BoC snapshot exists.
    """
    from . import boc_intake

    force_boc = rf == "boc" or boc_snapshot is not None
    force_fiera = rf == "fiera"

    if force_fiera:
        return curve_builder.build_from_fixtures(as_of=rebuilt_as_of), None

    snap_path = boc_snapshot
    if snap_path is None and (force_boc or rf == "auto"):
        snap_path = boc_intake.find_preferred_boc_snapshot()

    if snap_path is not None:
        built = curve_builder.build_from_boc(
            as_of=rebuilt_as_of,
            boc_snapshot=snap_path,
            try_download=False,
        )
        return built, None

    if force_boc:
        built = curve_builder.build_from_boc(
            as_of=rebuilt_as_of,
            boc_snapshot=None,
            try_download=True,
        )
        return built, None

    built = curve_builder.build_from_fixtures(as_of=rebuilt_as_of)
    note = (
        "No BoC snapshot under data/risk_free/; fell back to Fiera construction "
        "col E fixture RF. Refresh with: python3 -m pipeline.boc_intake"
    )
    return built, note


def build_fixture_mode(
    *,
    maturities: List[int],
    pricing_date: str,
    current_date: str,
    current_fwd: Dict[int, float],
    current_pct: List[Optional[float]],
) -> ModeParts:
    """Implied = archived latest Fiera column J."""
    implied_pct = fh.to_percent(fh.pick_at_maturities(current_fwd, maturities))
    return ModeParts(
        implied_pct=implied_pct,
        implied_fwd=dict(current_fwd),
        current_date=current_date,
        canada_as_of=current_date,
        current_pct=current_pct,
        construction_meta={
            "curve_mode": "fixture_archive",
            "rf_source": "fiera_publication_archive",
            "premium_policy": "hold_latest_publication",
        },
        pipeline_steps=[
            "load_fiera_history",
            "select_latest_pair",
            "compute_curve_metrics",
            "evaluate_calibrated_triggers",
            "write_decision_log",
            "write_monitor_snapshot",
        ],
        note=(
            "Built by pipeline/build_monitor_snapshot.py from archived Fiera monthly "
            "method workbooks. Pricing basis = prior month column J; current = Canada "
            "par; implied = latest column J. Trigger: calibrated weighted |Δ| T "
            "(see docs/memos/trigger-calibration.md)."
        ),
        chart_implied=f"Implied is Fiera column J as of {current_date}.",
        source_label="Fiera monthly",
        premium_note=(
            "Between Fiera publication dates, column H is held; daily BoC intake "
            "is not wired yet. This snapshot uses consecutive monthly publications."
        ),
        snap_suffix="01",
        implied_construction=(
            "Fiera Illiquid_Ref_Curve_Construction column J "
            "(annual forward rates at publication)"
        ),
        implied_construction_note=(
            "Implied curve is Fiera's published annual forward rates for the "
            "latest month. Production will rebuild column J daily from a "
            "chosen Canada risk-free source + held/inferred liquidity premium."
        ),
        implied_series="illiquid_annual_forward_column_J",
    )


def build_rebuilt_mode(
    *,
    maturities: List[int],
    pricing_date: str,
    canada: Dict[str, Dict[int, float]],
    rebuilt_as_of: Optional[str],
    rf: RfMode,
    boc_snapshot: Optional[Path],
) -> ModeParts:
    """Implied = curve_builder column J (BoC RF preferred)."""
    built, rf_fallback_note = select_rebuilt_build(
        rebuilt_as_of=rebuilt_as_of,
        rf=rf,
        boc_snapshot=boc_snapshot,
    )
    record_path = write_construction_record(built)
    implied_fwd = built["forwards"]
    implied_pct = fh.to_percent(fh.pick_at_maturities(implied_fwd, maturities))
    current_date = str(built["as_of"])
    rf_as_of = str(built.get("rf_as_of") or current_date)

    if current_date not in canada:
        canada_dates = fh.sorted_as_of(canada)
        if not canada_dates:
            raise RuntimeError("No Canada par curves available")
        canada_curr = canada[canada_dates[-1]]
        current_pct = fh.to_percent(fh.pick_at_maturities(canada_curr, maturities))
        canada_as_of = canada_dates[-1]
    else:
        canada_curr = canada[current_date]
        current_pct = fh.to_percent(fh.pick_at_maturities(canada_curr, maturities))
        canada_as_of = current_date

    using_boc = str(built["rf_source"]).startswith("boc_")
    if using_boc:
        implied_construction = (
            "Rebuilt Illiquid column J via pipeline.curve_builder "
            f"(rf_source={built['rf_source']}, premium_policy={built['premium_policy']})"
        )
        implied_construction_note = (
            "Implied curve is reconstructed annual forwards (column J) from BoC "
            f"zero-coupon RF (rf_as_of={rf_as_of}) + held liquidity premium "
            f"(column H as of {current_date}). Pricing basis stays prior Fiera "
            f"publication column J ({pricing_date})."
        )
        rebuild_step = "rebuild_column_j_boc_rf"
        rf_label = f"BoC RF as of {rf_as_of}"
        premium_note = (
            "Column H held under hold_latest_publication; implied J rebuilt from "
            f"BoC zero-coupon CSV RF (rf_as_of={rf_as_of})."
        )
    else:
        implied_construction = (
            "Rebuilt Illiquid column J via pipeline.curve_builder "
            f"(rf_source={built['rf_source']}, premium_policy={built['premium_policy']})"
        )
        implied_construction_note = (
            "Implied curve is reconstructed annual forwards (column J) from fixture "
            "risk-free spots + held liquidity premium (column H). Pricing basis stays "
            f"prior Fiera publication column J ({pricing_date})."
        )
        if rf_fallback_note:
            implied_construction_note += f" {rf_fallback_note}"
        rebuild_step = "rebuild_column_j_fixture_rf"
        rf_label = "fixture RF (Fiera construction col E)"
        premium_note = (
            "Column H held under hold_latest_publication; implied J rebuilt from "
            "fixture RF (Fiera construction col E)."
        )
        if rf_fallback_note:
            premium_note = f"{premium_note} {rf_fallback_note}"

    construction_meta: Dict[str, Any] = {
        "curve_mode": "rebuilt",
        "rf_source": built["rf_source"],
        "rf_as_of": rf_as_of,
        "premium_policy": built["premium_policy"],
        "premium_as_of": current_date,
        "params_as_of": built.get("params_as_of"),
        "construction_record": str(record_path.relative_to(ROOT)),
        "construction_xlsx": str(Path(built["xlsx_path"]).relative_to(ROOT)),
        "construction_csv": str(Path(built["csv_path"]).relative_to(ROOT)),
    }
    lag_note = built.get("lag_note")
    if lag_note:
        construction_meta["lag_note"] = lag_note
    elif using_boc:
        from .boc_intake import LAG_NOTE

        construction_meta["lag_note"] = LAG_NOTE
    if rf_fallback_note:
        construction_meta["rf_fallback_note"] = rf_fallback_note
    if built.get("rf_publish_lag_days") is not None:
        construction_meta["rf_publish_lag_days"] = built["rf_publish_lag_days"]

    return ModeParts(
        implied_pct=implied_pct,
        implied_fwd=dict(implied_fwd),
        current_date=current_date,
        canada_as_of=canada_as_of,
        current_pct=current_pct,
        construction_meta=construction_meta,
        pipeline_steps=[
            "load_fiera_history",
            "select_pricing_baseline_prior_publication_J",
            rebuild_step,
            "write_construction_record",
            "compute_curve_metrics",
            "evaluate_calibrated_triggers",
            "write_decision_log",
            "write_monitor_snapshot",
        ],
        note=(
            "Built by pipeline/build_monitor_snapshot.py --rebuilt. "
            "Pricing basis = prior month archived column J; current = Canada par; "
            f"implied = curve_builder rebuilt column J ({rf_label}). "
            "Trigger: calibrated weighted |Δ| T (see docs/memos/trigger-calibration.md)."
        ),
        chart_implied=(
            f"Implied is rebuilt column J as of {current_date} "
            f"(rf_source={built['rf_source']}, rf_as_of={rf_as_of})."
        ),
        source_label="Fiera monthly + rebuilt J",
        premium_note=premium_note,
        snap_suffix="R01",
        implied_construction=implied_construction,
        implied_construction_note=implied_construction_note,
        implied_series="illiquid_annual_forward_column_J_rebuilt",
    )
