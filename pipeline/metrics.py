"""Curve-only monitoring metrics (no Slope). Units: basis points."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Liability-weight table (teammate): (first_year, last_year, weight_per_year).
# Sums to 1.0 over years 1..30. See docs/memos/trigger-calibration.md.
WEIGHT_BUCKETS: List[Tuple[int, int, float]] = [
    (1, 5, 0.01),
    (6, 10, 0.02),
    (11, 15, 0.03),
    (16, 20, 0.05),
    (21, 25, 0.05),
    (26, 30, 0.04),
]

TRIGGER_YEARS: List[int] = list(range(1, 31))


def weight_map(
    buckets: Sequence[Tuple[int, int, float]] = WEIGHT_BUCKETS,
) -> Dict[int, float]:
    """Per-year weights from bucket table."""
    out: Dict[int, float] = {}
    for first, last, w_per in buckets:
        for t in range(first, last + 1):
            out[t] = float(w_per)
    return out


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


def weighted_abs_change_bp(
    change: Sequence[Optional[float]],
    maturities: Sequence[float],
    weights: Optional[Mapping[int, float]] = None,
) -> Optional[float]:
    """T = Σ w_t · |Δr_t| (bp). Missing years are skipped (understates T)."""
    wmap = weight_map() if weights is None else weights
    total = 0.0
    used = 0.0
    for c, m in zip(change, maturities):
        if c is None:
            continue
        w = wmap.get(int(m))
        if w is None:
            continue
        total += w * abs(c)
        used += w
    if used <= 0:
        return None
    return total


def weighted_signed_change_bp(
    change: Sequence[Optional[float]],
    maturities: Sequence[float],
    weights: Optional[Mapping[int, float]] = None,
) -> Optional[float]:
    """S = Σ w_t · Δr_t (bp). Direction diagnostic; no absolute value."""
    wmap = weight_map() if weights is None else weights
    total = 0.0
    used = 0.0
    for c, m in zip(change, maturities):
        if c is None:
            continue
        w = wmap.get(int(m))
        if w is None:
            continue
        total += w * c
        used += w
    if used <= 0:
        return None
    return total


def bucket_mean_abs_bp(
    change: Sequence[Optional[float]],
    maturities: Sequence[float],
    buckets: Sequence[Tuple[int, int, float]] = WEIGHT_BUCKETS,
) -> Tuple[Optional[float], Optional[str], Dict[str, float]]:
    """Largest equal-weight mean |Δ| across weight-table buckets.

    Returns ``(max_bucket_mean_bp, bucket_label, all_bucket_means)``.
    """
    by_year: Dict[int, float] = {}
    for c, m in zip(change, maturities):
        if c is None:
            continue
        by_year[int(m)] = float(c)

    details: Dict[str, float] = {}
    best: Optional[float] = None
    best_label: Optional[str] = None
    for first, last, _w in buckets:
        vals = [abs(by_year[t]) for t in range(first, last + 1) if t in by_year]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        label = f"{first}-{last}"
        details[label] = mean
        if best is None or mean > best:
            best = mean
            best_label = label
    return best, best_label, details
