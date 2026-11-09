#!/usr/bin/env python3
"""Back-test the curve-only trigger on consecutive Fiera monthly forward curves.

Usage (from project root):

    python3 -m pipeline.backtest_trigger
    python3 pipeline/backtest_trigger.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline import fiera_history as fh  # noqa: E402
from pipeline import metrics  # noqa: E402
from pipeline import trigger  # noqa: E402


def interval_metrics(
    forwards: Dict[str, Dict[int, float]],
    maturities: List[int],
) -> List[dict]:
    dates = fh.sorted_as_of(forwards)
    rows: List[dict] = []
    for prev, curr in zip(dates, dates[1:]):
        base = fh.to_percent(fh.pick_at_maturities(forwards[prev], maturities))
        new = fh.to_percent(fh.pick_at_maturities(forwards[curr], maturities))
        ch = metrics.changes_bp(base, new)
        mean_abs = metrics.mean_abs_change_bp(ch)
        max_ch, max_idx = metrics.max_abs_change_bp(ch)
        twist = metrics.twist_2s10s_bp(maturities, ch)
        # Duration-aware alternative: maturity-weighted mean |Δ|.
        pairs = [(abs(v), m) for v, m in zip(ch, maturities) if v is not None]
        if pairs:
            dur = sum(a * m for a, m in pairs) / sum(m for _, m in pairs)
        else:
            dur = None
        rows.append(
            {
                "prev": prev,
                "curr": curr,
                "mean_abs_bp": mean_abs,
                "max_abs_bp": None if max_ch is None else abs(max_ch),
                "max_maturity": None if max_idx < 0 else maturities[max_idx],
                "twist_bp": None if twist is None else abs(twist),
                "dur_aware_bp": dur,
            }
        )
    return rows


def _pct(xs: List[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = int(round((p / 100.0) * (len(s) - 1)))
    return s[max(0, min(len(s) - 1, i))]


def fire_table(xs: List[float], thresholds: List[float], label: str) -> None:
    n = len(xs)
    years = n / 12.0
    print(f"\n{label}  (n={n} intervals ≈ {years:.1f} yrs)")
    print(f"  {'thr':>6}  {'fires':>6}  {'rate%':>7}  {'per_yr':>7}")
    for thr in thresholds:
        fires = sum(1 for x in xs if x >= thr)
        rate = fires / n if n else 0.0
        print(f"  {thr:6.0f}  {fires:6d}  {100 * rate:6.1f}%  {rate * 12:7.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Print every interval that breaches the calibrated primary threshold",
    )
    args = parser.parse_args()

    forwards = fh.load_forward_curves()
    maturities = list(fh.DISPLAY_MATURITIES)
    rows = interval_metrics(forwards, maturities)
    dates = fh.sorted_as_of(forwards)
    primary_thr = trigger.CALIBRATED["parallel"]

    print("Fiera consecutive monthly forward curves (column J)")
    print(f"  publications: {len(dates)}  ({dates[0]} → {dates[-1]})")
    print(f"  intervals:    {len(rows)}")
    print(f"  maturities:   {maturities}")
    print(f"  calibrated primary: mean |Δ| ≥ {primary_thr:g} bp")

    for key, label in [
        ("mean_abs_bp", "mean |Δ| bp (PRIMARY)"),
        ("dur_aware_bp", "duration-weighted mean |Δ| bp"),
        ("max_abs_bp", "max |Δ| bp (diagnostic)"),
        ("twist_bp", "|2s10s twist| bp (diagnostic)"),
    ]:
        xs = [r[key] for r in rows if r[key] is not None]
        print(
            f"\n{label}: min={min(xs):.1f} p50={_pct(xs,50):.1f} "
            f"p90={_pct(xs,90):.1f} max={max(xs):.1f}"
        )
        fire_table(xs, [15, 20, 25, 30, 35, 40, 50, 60, 75], label)

    fires = [r for r in rows if (r["mean_abs_bp"] or 0) >= primary_thr]
    n = len(rows)
    print(
        f"\nCalibrated primary fires: {len(fires)}/{n} "
        f"({100 * len(fires) / n:.1f}%) ≈ {12 * len(fires) / n:.2f}/year"
    )
    print("\nBreaching months (primary):")
    print(f"  {'as_of':<12} {'mean|Δ|':>8} {'max|Δ|':>8} {'twist':>8} {'node':>6}")
    for r in fires:
        print(
            f"  {r['curr']:<12} {r['mean_abs_bp']:8.1f} "
            f"{r['max_abs_bp']:8.1f} {r['twist_bp']:8.1f} "
            f"{r['max_maturity']!s:>6}"
        )
    if args.detail:
        print("\nAll intervals:")
        print(f"  {'prev':<12} {'curr':<12} {'mean|Δ|':>8} {'max|Δ|':>8} {'twist':>8}")
        for r in rows:
            print(
                f"  {r['prev']:<12} {r['curr']:<12} "
                f"{r['mean_abs_bp']:8.1f} {r['max_abs_bp']:8.1f} {r['twist_bp']:8.1f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
