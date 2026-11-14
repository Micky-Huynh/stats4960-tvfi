"""Curve-only trigger (Sam: no Slope inside the trigger; one primary measure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import metrics as curve_metrics

# Re-export weight table for callers / back-tests.
WEIGHT_BUCKETS = curve_metrics.WEIGHT_BUCKETS
TRIGGER_YEARS = curve_metrics.TRIGGER_YEARS


@dataclass
class TriggerRule:
    id: str
    label: str
    metric: str
    threshold_bp: Optional[float]
    value_bp: Optional[float]
    role: str = "diagnostic"  # "primary" | "diagnostic"

    @property
    def status(self) -> str:
        if self.threshold_bp is None or self.value_bp is None:
            return "NOT_EVALUATED"
        return "BREACH" if abs(self.value_bp) >= self.threshold_bp else "PASS"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "metric": self.metric,
            "threshold_bp": self.threshold_bp,
            "value_bp": None if self.value_bp is None else round(self.value_bp, 2),
            "status": self.status,
            "role": self.role,
        }


# Calibrated on Fiera consecutive monthly col-J curves (2019-10 → 2026-10).
# Primary: liability-weighted T = Σ w_t·|Δr_t| over years 1..30 ≥ 35 bp.
# See docs/memos/trigger-calibration.md.
CALIBRATED = {
    "weighted": 35.0,  # primary: T bp
    # Diagnostics only (do not drive overall_status):
    "bucket": 75.0,  # max per-bucket mean |Δ| bp
    "twist": 40.0,  # |Δ 2s10s| bp — shape diagnostic
    # Legacy aliases (equal-weight era keys):
    "parallel": 35.0,
    "maturity": 75.0,
}

# Back-compat alias used by snapshot history flagging.
PROVISIONAL = CALIBRATED

PRIMARY_RULE_ID = "weighted"


def evaluate(
    weighted_abs_bp: Optional[float],
    max_bucket_abs_bp: Optional[float],
    twist_bp: Optional[float],
    signed_bp: Optional[float] = None,
    *,
    max_bucket_label: Optional[str] = None,
    use_calibrated: bool = True,
    use_provisional: Optional[bool] = None,
) -> List[TriggerRule]:
    """Evaluate primary + diagnostic rules. Primary measure is weighted T."""
    active = use_calibrated if use_provisional is None else bool(use_provisional)
    thr = CALIBRATED if active else {k: None for k in ("weighted", "bucket", "twist")}
    bucket_label = (
        f"Largest bucket mean |Δ| ({max_bucket_label})"
        if max_bucket_label
        else "Largest bucket mean |Δ| (diagnostic)"
    )
    rules = [
        TriggerRule(
            "weighted",
            "Weighted |Δ| T (primary)",
            "weighted_abs_change_bp",
            thr["weighted"],
            weighted_abs_bp,
            role="primary",
        ),
        TriggerRule(
            "bucket",
            bucket_label,
            "max_bucket_abs_change_bp",
            thr["bucket"],
            None if max_bucket_abs_bp is None else abs(max_bucket_abs_bp),
            role="diagnostic",
        ),
        TriggerRule(
            "twist",
            "Curve shape / twist (diagnostic)",
            "abs_twist_2s10s_bp",
            thr["twist"],
            None if twist_bp is None else abs(twist_bp),
            role="diagnostic",
        ),
        TriggerRule(
            "signed",
            "Signed weighted Δ S (direction)",
            "weighted_signed_change_bp",
            None,  # no threshold — display only
            signed_bp,
            role="diagnostic",
        ),
    ]
    return rules


def overall(rules: List[TriggerRule]) -> Dict[str, str]:
    """Overall status follows the single primary rule only."""
    primary = next((r for r in rules if r.role == "primary"), None)
    if primary is None:
        primary = next((r for r in rules if r.id == PRIMARY_RULE_ID), None)
    if primary is None:
        return {
            "overall_status": "UNASSESSED",
            "detail": "Primary rule missing",
            "note": "No primary trigger rule configured.",
            "outcome": "No trigger conclusion.",
        }
    if primary.status == "NOT_EVALUATED":
        return {
            "overall_status": "UNASSESSED",
            "detail": "Primary rule not evaluated",
            "note": "Threshold missing or weighted-T metric unavailable.",
            "outcome": "No trigger conclusion.",
        }
    if primary.status == "BREACH":
        return {
            "overall_status": "TRIGGERED",
            "detail": (
                f"Primary threshold breach: {primary.label} "
                f"(T ≥ {primary.threshold_bp:g} bp)"
            ),
            "note": (
                "Calibrated curve-only trigger (liability-weighted absolute change "
                "T over years 1–30). A breach means: run a Slope profitability test "
                "(VoNB / Net CSM / CaPM). Bucket/twist/signed rules are diagnostics only."
            ),
            "outcome": f"Triggered on: {primary.label}",
        }
    return {
        "overall_status": "NO_TRIGGER",
        "detail": (
            f"Primary rule passed (T < {primary.threshold_bp:g} bp)"
        ),
        "note": (
            "Calibrated curve-only trigger. Diagnostics (bucket mean |Δ|, 2s10s twist, "
            "signed S) do not fire the Slope profitability test on their own."
        ),
        "outcome": "No Slope profitability test required under calibrated primary rule.",
    }
