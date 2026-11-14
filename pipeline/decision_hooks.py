"""Decision log + profitability attach hooks for monitor snapshots.

Kept separate from ``snapshot.build_snapshot`` so the assembler owns curve/trigger
assembly and this module owns post-build enrichment + disk side effects.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from . import trigger

ET = ZoneInfo("America/Toronto")
ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = ROOT / "data" / "decisions"
EXPORTS_DIR = ROOT / "exports"

PRIMARY_MEASURE = "weighted_abs_change_bp"


def _primary_trigger(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Return the primary trigger rule dict from a snapshot."""
    for rule in snapshot.get("triggers") or []:
        if rule.get("role") == "primary" or rule.get("id") == trigger.PRIMARY_RULE_ID:
            return rule
    return {}


def _decision_path_for(as_of: str) -> Path:
    return DECISIONS_DIR / f"{as_of}.json"


def build_decision_log(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Build a daily decision log payload from a monitor snapshot."""
    meta = snapshot.get("meta") or {}
    assessment = snapshot.get("assessment") or {}
    metrics_computed = snapshot.get("metrics_computed") or {}
    curves = snapshot.get("curves") or {}
    primary = _primary_trigger(snapshot)
    as_of = str(meta.get("observation_date") or "unknown")
    now = datetime.now(ET)

    measure = primary.get("metric") or PRIMARY_MEASURE
    threshold_bp = primary.get("threshold_bp")
    value_bp = primary.get("value_bp")
    if value_bp is None:
        value_bp = metrics_computed.get(measure)
    overall_status = assessment.get("overall_status", "UNASSESSED")

    # Single metrics blob (no duplicate values/metrics copies).
    metrics = {
        "weighted_abs_change_bp": metrics_computed.get("weighted_abs_change_bp"),
        "weighted_signed_change_bp": metrics_computed.get(
            "weighted_signed_change_bp"
        ),
        "max_bucket_abs_change_bp": metrics_computed.get(
            "max_bucket_abs_change_bp"
        ),
        "max_bucket_label": metrics_computed.get("max_bucket_label"),
        "abs_mean_change_bp": metrics_computed.get("abs_mean_change_bp"),
        "max_abs_change_bp": metrics_computed.get("max_abs_change_bp"),
        "max_maturity": metrics_computed.get("max_maturity"),
        "abs_twist_2s10s_bp": metrics_computed.get("abs_twist_2s10s_bp"),
        "thresholds_active": metrics_computed.get("thresholds_active"),
        "thresholds_calibrated": metrics_computed.get("thresholds_calibrated"),
        "thresholds_provisional": metrics_computed.get("thresholds_provisional"),
    }

    return {
        "decision_id": snapshot.get("snapshot_id"),
        "as_of": as_of,
        "pricing_basis_date": meta.get("pricing_basis_date"),
        "measure": measure,
        "threshold_bp": threshold_bp,
        "value_bp": value_bp,
        "metrics": metrics,
        "triggers": snapshot.get("triggers") or [],
        "assessment": assessment,
        "overall_status": overall_status,
        "inputs": {
            "rf_source": meta.get("rf_source"),
            "premium_policy": meta.get("premium_policy"),
            "construction_record": meta.get("construction_record"),
            "pricing_series": (curves.get("pricing_basis") or {}).get("series"),
            "implied_series": (curves.get("implied") or {}).get("series"),
            "current_series": (curves.get("current_basis") or {}).get("series"),
            "curve_mode": meta.get("curve_mode"),
            "source": meta.get("source"),
        },
        "notes": (
            "Generated with pipeline.build_monitor_snapshot; "
            "primary measure is calibrated weighted |Δ| T (curve-only)."
        ),
        "written_at": now.isoformat(timespec="seconds"),
    }


def write_decision_log(snapshot: Dict[str, Any]) -> Path:
    """Write/update data/decisions/YYYY-MM-DD.json for the snapshot as-of date."""
    meta = snapshot.get("meta") or {}
    as_of = str(meta.get("observation_date") or "unknown")
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _decision_path_for(as_of)
    payload = build_decision_log(snapshot)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def profitability_section(*, exports_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Optional profitability hook for the snapshot.

    Status values:
      - ``not_run`` — no export workbook yet
      - ``export_found`` — workbook on disk, metrics not parsed yet
      - ``available`` — reserved for when ``summary.metrics`` is filled
    """
    root_exports = exports_dir if exports_dir is not None else EXPORTS_DIR
    exports = (
        sorted(root_exports.glob("profitability_summary_*.xlsx"))
        if root_exports.is_dir()
        else []
    )
    if not exports:
        return {
            "status": "not_run",
            "note": (
                "No exports/profitability_summary_*.xlsx yet. After "
                "analyse_results.py writes an export (needs slope_api.py), "
                "re-run pipeline.build_monitor_snapshot to attach the path here."
            ),
            "summary": None,
        }

    latest = exports[-1]
    try:
        rel = str(latest.relative_to(ROOT))
    except ValueError:
        rel = str(latest)
    return {
        "status": "export_found",
        "note": (
            "Found profitability export path only. VoNB / Net CSM / CaPM are not "
            "parsed into summary.metrics yet — status stays export_found until "
            "workbook parse is wired (then status becomes available)."
        ),
        "summary": {
            "export_path": rel,
            "export_name": latest.name,
            "metrics": None,
        },
    }


def enrich_snapshot(snapshot: Dict[str, Any], decision_path: Path) -> Dict[str, Any]:
    """Attach optional decision + profitability sections (schema 1.0-safe)."""
    primary = _primary_trigger(snapshot)
    metrics_computed = snapshot.get("metrics_computed") or {}
    assessment = snapshot.get("assessment") or {}
    measure = primary.get("metric") or PRIMARY_MEASURE
    value_bp = primary.get("value_bp")
    if value_bp is None:
        value_bp = metrics_computed.get(measure)

    try:
        rel_decision = str(decision_path.relative_to(ROOT))
    except ValueError:
        rel_decision = str(decision_path)

    snapshot["decision"] = {
        "measure": measure,
        "threshold_bp": primary.get("threshold_bp"),
        "value_bp": value_bp,
        "status": assessment.get("overall_status", "UNASSESSED"),
        "decision_path": rel_decision,
    }
    snapshot["profitability"] = profitability_section()
    return snapshot
