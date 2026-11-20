"""Assemble monitor_snapshot.json body (orchestration only).

History rows → ``snapshot_history``. Disk write → ``snapshot_io``.
Mode branching → ``snapshot_modes``. Enrichment → ``decision_hooks``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from zoneinfo import ZoneInfo

from . import fiera_history as fh
from . import interval_metrics as im
from . import snapshot_history
from . import snapshot_modes
from . import trigger
from .snapshot_modes import RfMode

ET = ZoneInfo("America/Toronto")

SnapshotMode = Literal["fixture_archive", "rebuilt"]


def _rf_freshness(
    *,
    curve_mode: str,
    observation_date: str,
    construction_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Stamp RF freshness without conflating publish lag and obs−RF gap.

    ``rf_publish_lag_days`` (from intake) = calendar_today − rf_as_of.
    ``obs_rf_calendar_gap_days`` = observation_date − rf_as_of (product gap).
    These are different; never quote publish lag as the obs−RF gap.
    """
    rf_as_of = construction_meta.get("rf_as_of")
    publish_lag = construction_meta.get("rf_publish_lag_days")
    obs_gap: Optional[int] = None
    if rf_as_of and observation_date:
        try:
            obs = datetime.fromisoformat(str(observation_date)[:10]).date()
            rf = datetime.fromisoformat(str(rf_as_of)[:10]).date()
            obs_gap = (obs - rf).days
        except ValueError:
            obs_gap = None

    data_availability = "CURRENT"
    if curve_mode == "rebuilt" and (
        (isinstance(publish_lag, (int, float)) and publish_lag > 0)
        or (obs_gap is not None and obs_gap > 0)
        or (rf_as_of and str(rf_as_of) < str(observation_date))
    ):
        data_availability = "LAGGED"

    return {
        "data_availability": data_availability,
        "obs_rf_calendar_gap_days": obs_gap,
        "lag_semantics": (
            "rf_publish_lag_days = calendar_today − rf_as_of (intake freshness); "
            "obs_rf_calendar_gap_days = observation_date − rf_as_of (curve RF age). "
            "Do not quote publish lag as the observation−RF gap."
        ),
    }


def _metrics_computed(
    pair: Dict[str, Any],
    weighted: Dict[str, Any],
    *,
    thresholds_active: bool,
) -> Dict[str, Any]:
    """Python-owned summary metrics (dashboard prefers these over JS re-derive)."""
    mean_abs = pair["mean_abs_bp"]
    max_abs = pair["max_abs_bp"]
    twist_abs = weighted.get("twist_abs_bp", pair["twist_abs_bp"])
    t_bp = weighted.get("weighted_abs_bp")
    s_bp = weighted.get("weighted_signed_bp")
    bucket = weighted.get("max_bucket_abs_bp")
    return {
        # Primary (weighted T) + diagnostics
        "weighted_abs_change_bp": None if t_bp is None else round(t_bp, 2),
        "weighted_signed_change_bp": None if s_bp is None else round(s_bp, 2),
        "max_bucket_abs_change_bp": None if bucket is None else round(bucket, 2),
        "max_bucket_label": weighted.get("max_bucket_label"),
        # Legacy equal-weight display metrics (chart nodes)
        "abs_mean_change_bp": None if mean_abs is None else round(mean_abs, 2),
        "max_abs_change_bp": None if max_abs is None else round(max_abs, 2),
        "max_maturity": pair.get("max_maturity"),
        "abs_twist_2s10s_bp": None if twist_abs is None else round(twist_abs, 2),
        "primary_threshold_bp": trigger.CALIBRATED["weighted"],
        "thresholds_active": thresholds_active,
        "thresholds_calibrated": thresholds_active,
        # Legacy alias kept False when calibrated thresholds are active so
        # readers do not think provisional == calibrated.
        "thresholds_provisional": False if thresholds_active else True,
    }


def build_snapshot(
    *,
    mode: SnapshotMode = "fixture_archive",
    use_calibrated_thresholds: bool = True,
    use_provisional_thresholds: Optional[bool] = None,
    rebuilt_as_of: Optional[str] = None,
    rf: RfMode = "auto",
    boc_snapshot: Optional[Path] = None,
    refresh_rf: bool = True,
    lag_bridge: bool = True,
    fetch_valet: bool = True,
) -> Dict[str, Any]:
    """Build a schema 1.0 monitor snapshot.

    Modes
    -----
    fixture_archive
        Implied = archived Fiera publication column J (consecutive monthly pair).
    rebuilt
        Implied = ``curve_builder`` column J (live BoC CSV pull by default when
        ``refresh_rf``; otherwise cached ``data/risk_free`` / Fiera fixture RF)
        + hold_latest H. During BoC publish lag, Valet key-rate shift bridge is
        ON by default (``lag_bridge``). Pricing basis remains the **prior
        publication** column J from history — the trigger still measures move vs
        the last locked pricing baseline, not vs a rebuilt prior.

    Thresholds
    ----------
    ``use_calibrated_thresholds`` (preferred): when True, apply calibrated
    thresholds; when False, triggers stay UNASSESSED.

    ``use_provisional_thresholds`` is a deprecated alias with the same meaning
    (True = calibrated). If passed, it wins over ``use_calibrated_thresholds``.
    """
    if mode not in ("fixture_archive", "rebuilt"):
        raise ValueError(f"Unknown snapshot mode: {mode!r}")
    if rf not in ("auto", "boc", "fiera"):
        raise ValueError(f"Unknown rf mode: {rf!r}")

    if use_provisional_thresholds is not None:
        thresholds_active = bool(use_provisional_thresholds)
    else:
        thresholds_active = bool(use_calibrated_thresholds)

    forwards = fh.load_forward_curves()
    canada = fh.load_canada_par_curves()
    maturities = list(fh.DISPLAY_MATURITIES)

    pricing_date, current_date, pricing_fwd, current_fwd = fh.latest_pair(forwards)
    if current_date not in canada:
        raise RuntimeError(f"No Canada par curve for {current_date}")
    canada_curr = canada[current_date]

    pricing_pct = fh.to_percent(fh.pick_at_maturities(pricing_fwd, maturities))
    current_pct = fh.to_percent(fh.pick_at_maturities(canada_curr, maturities))

    if mode == "rebuilt":
        parts = snapshot_modes.build_rebuilt_mode(
            maturities=maturities,
            pricing_date=pricing_date,
            canada=canada,
            rebuilt_as_of=rebuilt_as_of,
            rf=rf,
            boc_snapshot=boc_snapshot,
            refresh_rf=refresh_rf,
            lag_bridge=lag_bridge,
            fetch_valet=fetch_valet,
        )
    else:
        parts = snapshot_modes.build_fixture_mode(
            maturities=maturities,
            pricing_date=pricing_date,
            current_date=current_date,
            current_fwd=current_fwd,
            current_pct=current_pct,
        )

    # Chart nodes stay on DISPLAY_MATURITIES; trigger uses years 1..30.
    pair = im.pair_metrics(pricing_pct, parts.implied_pct, maturities)
    trigger_years = list(trigger.TRIGGER_YEARS)
    pricing_trigger_pct = fh.to_percent(
        fh.pick_at_maturities(pricing_fwd, trigger_years)
    )
    implied_trigger_pct = fh.to_percent(
        fh.pick_at_maturities(parts.implied_fwd, trigger_years)
    )
    weighted = im.weighted_pair_metrics(
        pricing_trigger_pct, implied_trigger_pct, trigger_years
    )
    rules = trigger.evaluate(
        weighted["weighted_abs_bp"],
        weighted["max_bucket_abs_bp"],
        weighted["twist_bp"],
        weighted["weighted_signed_bp"],
        max_bucket_label=weighted.get("max_bucket_label"),
        use_calibrated=thresholds_active,
    )
    assessment = trigger.overall(rules)

    now = datetime.now(ET)
    snap_id = f"Fiera-{parts.current_date.replace('-', '')}-{parts.snap_suffix}"
    history_rows = snapshot_history.build_history_rows(
        forwards, maturities, curve_mode=mode, last_n=12
    )
    hist_quality = snapshot_history.history_data_quality(curve_mode=mode)

    fresh = _rf_freshness(
        curve_mode=mode,
        observation_date=parts.current_date,
        construction_meta=parts.construction_meta,
    )

    meta: Dict[str, Any] = {
        "observation_date": parts.current_date,
        "latest_market_date": parts.current_date,
        "market_session": "close",
        "pricing_basis_date": pricing_date,
        "source": "Fiera CIA IFRS 17 method workbook (Canada par + Illiquid col J)",
        "source_label": parts.source_label,
        "last_successful_update": now.isoformat(timespec="seconds"),
        "timezone_label": "ET",
        "data_availability": fresh["data_availability"],
        "currency": "CAD",
        "yield_type": "nominal",
        "premium_policy": parts.construction_meta.get(
            "premium_policy", "hold_latest_publication"
        ),
        "premium_policy_note": parts.premium_note,
        **parts.construction_meta,
        # Named freshness fields (must not confuse publish lag with obs−RF gap).
        "obs_rf_calendar_gap_days": fresh["obs_rf_calendar_gap_days"],
        "lag_semantics": fresh["lag_semantics"],
    }

    return {
        "_note": parts.note,
        "schema_version": "1.0",
        "snapshot_id": snap_id,
        "is_illustrative": False,
        "meta": meta,
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
                "as_of": parts.canada_as_of,
                "series": "canada_par_market_curves",
                "yields": parts.current_pct,
            },
            "implied": {
                "label": "Updated / Implied Curve",
                "as_of": parts.current_date,
                "construction": parts.implied_construction,
                "construction_note": parts.implied_construction_note,
                "series": parts.implied_series,
                "yields": parts.implied_pct,
            },
        },
        "assessment": assessment,
        "triggers": [r.as_dict() for r in rules],
        "history": history_rows,
        "data_quality": {
            "reference_basis": (
                f"Fiera {parts.current_date} · pricing {pricing_date}"
            ),
            "last_pipeline_run": now.isoformat(timespec="seconds"),
            "pipeline_run_simulated": False,
            "fiera_publications_used": 2,
            "history_publications": len(fh.sorted_as_of(forwards)),
            "curve_mode": mode,
            **hist_quality,
        },
        "pipeline_runs": [
            {
                "id": snap_id,
                "started_at": now.isoformat(timespec="seconds"),
                "finished_at": now.isoformat(timespec="seconds"),
                "status": "ok",
                "steps": parts.pipeline_steps,
            }
        ],
        "notes": {
            "chart_reading": (
                f"Pricing basis is Fiera column J as of {pricing_date}. "
                f"Current basis is Canada par as of {parts.canada_as_of}. "
                f"{parts.chart_implied} "
                "Yields are percent. Deltas are implied − pricing."
            ),
            "history_reading": snapshot_history.history_reading(curve_mode=mode),
            "sam_feedback": (
                "Trigger is curve-only (no Slope) with one primary measure: "
                "liability-weighted |Δ| T over years 1–30. A breach starts a Slope "
                "profitability test (VoNB / Net CSM / CaPM). Bucket / twist / signed "
                "S are diagnostics only."
            ),
        },
        "metrics_computed": _metrics_computed(
            pair, weighted, thresholds_active=thresholds_active
        ),
    }
