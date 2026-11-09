"""Curve-only monitoring metrics (no Slope). Units: basis points."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


def _num(xs: Sequence[Optional[float]]) -> List[float]:
    return [float(x) for x in xs if x is not None]


def changes_bp(
    base_pct: Sequence[Optional[float]],
    new_pct: Sequence[Optional[float]],
) -> List[Optional[float]]:
    """Percent yields → bp change (new - base)."""
    out: List[Optional[float]] = []
    for a, b in zip(base_pct, new_pct):
        if a is None or b is None:
            out.append(None)
        else:
            out.append((b - a) * 100.0)
    return out


def mean_abs_change_bp(change: Sequence[Optional[float]]) -> Optional[float]:
    vals = _num(change)
    if not vals:
        return None
    return sum(abs(v) for v in vals) / len(vals)


def mean_signed_change_bp(change: Sequence[Optional[float]]) -> Optional[float]:
    vals = _num(change)
    if not vals:
        return None
    return sum(vals) / len(vals)


def max_abs_change_bp(change: Sequence[Optional[float]]) -> Tuple[Optional[float], int]:
    best = None
    idx = -1
    for i, v in enumerate(change):
        if v is None:
            continue
        if best is None or abs(v) > abs(best):
            best = v
            idx = i
    return best, idx


def twist_2s10s_bp(
    maturities: Sequence[float],
    change: Sequence[Optional[float]],
) -> Optional[float]:
    """(Δ10y - Δ2y) in bp when both nodes exist."""
    try:
        i2 = list(maturities).index(2)
        i10 = list(maturities).index(10)
    except ValueError:
        return None
    c2, c10 = change[i2], change[i10]
    if c2 is None or c10 is None:
        return None
    return c10 - c2
