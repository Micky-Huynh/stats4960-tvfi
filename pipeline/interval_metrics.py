"""Consecutive-publication curve metrics shared by snapshot history and back-test."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import fiera_history as fh
from . import metrics


def pair_metrics(
    base_pct: Sequence[Optional[float]],
    new_pct: Sequence[Optional[float]],
    maturities: Sequence[float],
) -> Dict[str, Any]:
    """Equal-weight display metrics (legacy / chart nodes)."""
    ch = metrics.changes_bp(base_pct, new_pct)
    mean_abs = metrics.mean_abs_change_bp(ch)
    mean_signed = metrics.mean_signed_change_bp(ch)
    max_ch, max_idx = metrics.max_abs_change_bp(ch)
    twist = metrics.twist_2s10s_bp(maturities, ch)
    pairs = [(abs(v), float(m)) for v, m in zip(ch, maturities) if v is not None]
    if pairs:
        dur = sum(a * m for a, m in pairs) / sum(m for _, m in pairs)
    else:
        dur = None
    return {
        "change_bp": ch,
        "mean_abs_bp": mean_abs,
        "mean_signed_bp": mean_signed,
        "max_abs_bp": None if max_ch is None else abs(max_ch),
        "max_signed_bp": max_ch,
        "max_idx": max_idx,
        "max_maturity": None if max_idx < 0 else maturities[max_idx],
        "twist_bp": twist,
        "twist_abs_bp": None if twist is None else abs(twist),
        "dur_aware_bp": dur,
    }


def weighted_pair_metrics(
    base_pct: Sequence[Optional[float]],
    new_pct: Sequence[Optional[float]],
    maturities: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Liability-weighted primary T, signed S, and Layer-2 bucket max."""
    years = list(metrics.TRIGGER_YEARS if maturities is None else maturities)
    ch = metrics.changes_bp(base_pct, new_pct)
    weights = metrics.weight_map()
    t_bp = metrics.weighted_abs_change_bp(ch, years, weights)
    s_bp = metrics.weighted_signed_change_bp(ch, years, weights)
    bucket_max, bucket_label, bucket_means = metrics.bucket_mean_abs_bp(ch, years)
    twist = metrics.twist_2s10s_bp(years, ch)
    return {
        "trigger_change_bp": ch,
        "weighted_abs_bp": t_bp,
        "weighted_signed_bp": s_bp,
        "max_bucket_abs_bp": bucket_max,
        "max_bucket_label": bucket_label,
        "bucket_means_bp": bucket_means,
        "twist_bp": twist,
        "twist_abs_bp": None if twist is None else abs(twist),
    }


def consecutive_interval_metrics(
    forwards: Mapping[str, Mapping[int, float]],
    maturities: Sequence[int],
    *,
    last_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Walk consecutive as-of dates and return per-interval metrics.

    ``maturities`` are the equal-weight / chart nodes (usually DISPLAY_MATURITIES).
    Weighted trigger metrics always use years 1..30.

    When ``last_n`` is set, only the last ``last_n`` intervals are returned
    (needs ``last_n + 1`` publications).
    """
    dates = fh.sorted_as_of(forwards)
    if len(dates) < 2:
        return []
    if last_n is not None:
        dates = dates[-(last_n + 1) :]
    trigger_years = list(metrics.TRIGGER_YEARS)
    rows: List[Dict[str, Any]] = []
    for prev, curr in zip(dates, dates[1:]):
        base = fh.to_percent(fh.pick_at_maturities(forwards[prev], list(maturities)))
        new = fh.to_percent(fh.pick_at_maturities(forwards[curr], list(maturities)))
        m = pair_metrics(base, new, maturities)
        base_t = fh.to_percent(fh.pick_at_maturities(forwards[prev], trigger_years))
        new_t = fh.to_percent(fh.pick_at_maturities(forwards[curr], trigger_years))
        wt = weighted_pair_metrics(base_t, new_t, trigger_years)
        # Prefer twist from the denser 1..30 series when available.
        rows.append(
            {
                "prev": prev,
                "curr": curr,
                **m,
                "weighted_abs_bp": wt["weighted_abs_bp"],
                "weighted_signed_bp": wt["weighted_signed_bp"],
                "max_bucket_abs_bp": wt["max_bucket_abs_bp"],
                "max_bucket_label": wt["max_bucket_label"],
                "bucket_means_bp": wt["bucket_means_bp"],
                "twist_bp": wt["twist_bp"] if wt["twist_bp"] is not None else m["twist_bp"],
                "twist_abs_bp": (
                    wt["twist_abs_bp"]
                    if wt["twist_abs_bp"] is not None
                    else m["twist_abs_bp"]
                ),
            }
        )
    return rows
