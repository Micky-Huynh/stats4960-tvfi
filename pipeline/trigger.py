"""Curve-only trigger (Sam: no Slope inside the trigger; one primary measure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
# Primary: mean |Δ| across DISPLAY_MATURITIES ≥ 35 bp → start Slope profitability test.
# See docs/memos/trigger-calibration.md.
CALIBRATED = {
    "parallel": 35.0,  # primary: |mean Δ| bp
    # Diagnostics only (do not drive overall_status):
    "maturity": 75.0,  # max |Δ| bp — single-node / long-end noise filter
    "twist": 40.0,  # |Δ 2s10s| bp — shape diagnostic
}

# Back-compat alias used by snapshot history flagging.
PROVISIONAL = CALIBRATED

PRIMARY_RULE_ID = "parallel"


def evaluate(
    mean_abs_bp: Optional[float],
    max_abs_bp: Optional[float],
    twist_bp: Optional[float],
    *,
    use_provisional: bool = True,
) -> List[TriggerRule]:
    """Evaluate primary + diagnostic rules.

    ``use_provisional`` kept for CLI flag compatibility; when False, thresholds
    are null (UNASSESSED). When True, use calibrated thresholds.
    """
    thr = CALIBRATED if use_provisional else {k: None for k in CALIBRATED}
    rules = [
        TriggerRule(
            "parallel",
            "Parallel movement (primary)",
            "abs_mean_change_bp",
            thr["parallel"],
            mean_abs_bp,
            role="primary",
        ),
        TriggerRule(
            "maturity",
            "Maturity-level movement (diagnostic)",
            "max_abs_change_bp",
            thr["maturity"],
            None if max_abs_bp is None else abs(max_abs_bp),
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
            "note": "Threshold missing or mean-abs metric unavailable.",
            "outcome": "No trigger conclusion.",
        }
    if primary.status == "BREACH":
        return {
            "overall_status": "TRIGGERED",
            "detail": (
                f"Primary threshold breach: {primary.label} "
                f"(|mean Δ| ≥ {primary.threshold_bp:g} bp)"
            ),
            "note": (
                "Calibrated curve-only trigger (mean absolute change across display "
                "maturities). A breach means: run a Slope profitability test "
                "(VoNB / Net CSM / CaPM). Maturity/twist rules are diagnostics only."
            ),
            "outcome": f"Triggered on: {primary.label}",
        }
    return {
        "overall_status": "NO_TRIGGER",
        "detail": (
            f"Primary rule passed (|mean Δ| < {primary.threshold_bp:g} bp)"
        ),
        "note": (
            "Calibrated curve-only trigger. Diagnostics (max |Δ|, 2s10s twist) "
            "do not fire the Slope profitability test on their own."
        ),
        "outcome": "No Slope profitability test required under calibrated primary rule.",
    }
