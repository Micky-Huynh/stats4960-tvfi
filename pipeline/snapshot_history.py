"""Archive consecutive-column-J history rows for monitor snapshots.

History always uses archived Fiera publication pairs (not the live rebuilt
BoC path). In rebuilt mode, rows stay for chart context but are never flagged
as live-trigger events.
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
            "(publication → next publication). It is not the live rebuilt "
            "path (prior J vs BoC-rebuilt implied). Red flags are omitted "
            "in rebuilt mode so archive moves are not read as live triggers."
        )
    return (
        "History chart is consecutive archived Fiera column-J pairs "
        "(same basis as the live fixture_archive trigger)."
    )


def history_data_quality(*, curve_mode: str) -> Dict[str, Any]:
    """Extra data_quality fields describing history vs live path."""
    matches = curve_mode == "fixture_archive"
    return {
        "history_basis": HISTORY_BASIS,
        "history_matches_live_path": matches,
        "history_flagging": (
            "disabled_in_rebuilt"
            if curve_mode == "rebuilt"
            else "weighted_abs_vs_calibrated_primary"
        ),
    }


def build_history_rows(
    forwards: Mapping[str, Mapping[int, float]],
    maturities: Sequence[int],
    *,
    curve_mode: str,
    last_n: int = 12,
) -> List[Dict[str, Any]]:
    """Build last-N archive consecutive-J history rows.

    When ``curve_mode == "rebuilt"``, ``flagged`` is always False (no fake
    live-trigger events). Fixture mode flags when weighted T ≥ calibrated primary.
    """
    thr = trigger.CALIBRATED["weighted"]
    allow_flags = curve_mode == "fixture_archive"
    rows: List[Dict[str, Any]] = []
    for interval in im.consecutive_interval_metrics(
        forwards, maturities, last_n=last_n
    ):
        # Chart still uses signed equal-weight mean for the history series.
        mean = interval["mean_signed_bp"]
        t_bp = interval["weighted_abs_bp"]
        would_flag = bool(t_bp is not None and t_bp >= thr)
        flagged = bool(allow_flags and would_flag)
        row: Dict[str, Any] = {
            "date": interval["curr"],
            "mean_shift_bp": None if mean is None else round(mean, 1),
            "weighted_abs_bp": None if t_bp is None else round(t_bp, 1),
            "flagged": flagged,
            "basis": HISTORY_BASIS,
        }
        if flagged:
            row["note"] = f"primary weighted T threshold (≥{thr:g} bp)"
        elif curve_mode == "rebuilt" and would_flag:
            row["note"] = (
                f"archive-only context (≥{thr:g} bp weighted T); "
                "not a live rebuilt trigger"
            )
        rows.append(row)
    return rows
