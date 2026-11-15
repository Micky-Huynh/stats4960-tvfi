"""Archive consecutive-column-J history rows for monitor snapshots.

History always uses archived Fiera publication pairs (not the live rebuilt
BoC path). ``flagged`` marks archive months where weighted T ≥ calibrated
primary so the JSON matches the dashboard chart. In rebuilt mode those marks
are archive context only — overall live status still comes from the rebuilt
pricing→implied pair.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from . import interval_metrics as im
from . import trigger

HISTORY_BASIS = "archive_consecutive_column_j"


def history_reading(*, curve_mode: str) -> str:
    """Human-readable note for dashboard / notes.history_reading."""
    if curve_mode == "rebuilt":
        return (
            "History chart is archived Fiera column-J pairs only "
            "(publication → next publication). Live KPI T uses the rebuilt "
            "path (prior J vs BoC-rebuilt implied) and can differ from the "
            "last history point. Markers are archive T ≥ 35 bp, not live "
            "rebuilt triggers."
        )
    return (
        "History chart is consecutive archived Fiera column-J pairs "
        "(same basis as the live fixture_archive trigger). Markers are "
        "months where weighted T ≥ 35 bp."
    )


def history_data_quality(*, curve_mode: str) -> Dict[str, Any]:
    """Extra data_quality fields describing history vs live path."""
    matches = curve_mode == "fixture_archive"
    return {
        "history_basis": HISTORY_BASIS,
        "history_matches_live_path": matches,
        "history_flagging": "weighted_abs_vs_calibrated_primary",
        "history_flags_are_live_triggers": matches,
    }


def build_history_rows(
    forwards: Mapping[str, Mapping[int, float]],
    maturities: Sequence[int],
    *,
    curve_mode: str,
    last_n: int = 12,
) -> List[Dict[str, Any]]:
    """Build last-N archive consecutive-J history rows.

    ``flagged`` is True whenever archive weighted T ≥ calibrated primary so
    the snapshot JSON matches the dashboard. Rebuilt mode still notes that
    those marks are archive-only (not the live rebuilt overall_status).
    """
    thr = trigger.CALIBRATED["weighted"]
    rows: List[Dict[str, Any]] = []
    for interval in im.consecutive_interval_metrics(
        forwards, maturities, last_n=last_n
    ):
        mean = interval["mean_signed_bp"]
        t_bp = interval["weighted_abs_bp"]
        flagged = bool(t_bp is not None and t_bp >= thr)
        row: Dict[str, Any] = {
            "date": interval["curr"],
            "mean_shift_bp": None if mean is None else round(mean, 1),
            "weighted_abs_bp": None if t_bp is None else round(t_bp, 1),
            "flagged": flagged,
            "basis": HISTORY_BASIS,
        }
        if flagged:
            # Chart marker scope — never drives assessment.overall_status.
            row["flag_scope"] = (
                "archive_only" if curve_mode == "rebuilt" else "live_primary"
            )
        if flagged and curve_mode == "rebuilt":
            row["note"] = (
                f"archive marker T ≥ {thr:g} bp (Fiera consecutive months); "
                "not a live rebuilt trigger"
            )
        elif flagged:
            row["note"] = f"primary weighted T threshold (≥{thr:g} bp)"
        rows.append(row)
    return rows
