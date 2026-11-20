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
from pipeline import interval_metrics as im  # noqa: E402
from pipeline import trigger  # noqa: E402


def interval_metrics(
    forwards: Dict[str, Dict[int, float]],
    maturities: List[int],
) -> List[dict]:
    """Back-test rows; twist_bp is absolute to match historical printouts."""
    rows: List[dict] = []
    for interval in im.consecutive_interval_metrics(forwards, maturities):
        rows.append(
            {
                "prev": interval["prev"],
                "curr": interval["curr"],
                "mean_abs_bp": interval["mean_abs_bp"],
                "max_abs_bp": interval["max_abs_bp"],
                "max_maturity": interval["max_maturity"],
                "twist_bp": interval["twist_abs_bp"],
                "dur_aware_bp": interval["dur_aware_bp"],
                "weighted_abs_bp": interval["weighted_abs_bp"],
                "weighted_signed_bp": interval["weighted_signed_bp"],
                "max_bucket_abs_bp": interval["max_bucket_abs_bp"],
                "max_bucket_label": interval["max_bucket_label"],
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
    primary_thr = trigger.CALIBRATED["weighted"]
    bucket_thr = trigger.CALIBRATED["bucket"]

    print("Fiera consecutive monthly forward curves (column J)")
    print(f"  publications: {len(dates)}  ({dates[0]} → {dates[-1]})")
    print(f"  intervals:    {len(rows)}")
    print(f"  display mats: {maturities}")
    print(f"  trigger years: 1..30 (weighted T)")
    print(f"  calibrated primary: weighted |Δ| T ≥ {primary_thr:g} bp")
    print(f"  bucket diagnostic: max bucket mean |Δ| ≥ {bucket_thr:g} bp")

    for key, label in [
        ("weighted_abs_bp", "weighted |Δ| T bp (PRIMARY)"),
        ("mean_abs_bp", "equal-weight mean |Δ| bp (legacy comparison)"),
        ("max_bucket_abs_bp", "max bucket mean |Δ| bp (Layer 2 diagnostic)"),
        ("max_abs_bp", "max |Δ| bp (legacy single-node)"),
        ("twist_bp", "|2s10s twist| bp (diagnostic)"),
    ]:
        xs = [r[key] for r in rows if r[key] is not None]
        print(
            f"\n{label}: min={min(xs):.1f} p50={_pct(xs,50):.1f} "
            f"p90={_pct(xs,90):.1f} max={max(xs):.1f}"
        )
        fire_table(xs, [15, 20, 25, 30, 35, 40, 50, 60, 75], label)

    fires = [r for r in rows if (r["weighted_abs_bp"] or 0) >= primary_thr]
    layer2_only = [
        r
        for r in rows
        if (r["max_bucket_abs_bp"] or 0) >= bucket_thr
        and (r["weighted_abs_bp"] or 0) < primary_thr
    ]
    n = len(rows)
    print(
        f"\nCalibrated primary fires: {len(fires)}/{n} "
        f"({100 * len(fires) / n:.1f}%) ≈ {12 * len(fires) / n:.2f}/year"
    )
    print("\nBreaching months (primary T ≥ 25):")
    print(
        f"  {'as_of':<12} {'T':>8} {'S':>8} {'bucket':>8} {'which':>8} {'mean|Δ|':>8}"
    )
    for r in fires:
        print(
            f"  {r['curr']:<12} {r['weighted_abs_bp']:8.1f} "
            f"{r['weighted_signed_bp']:8.1f} "
            f"{r['max_bucket_abs_bp']:8.1f} "
            f"{str(r['max_bucket_label'] or ''):>8} "
            f"{r['mean_abs_bp']:8.1f}"
        )
    print(
        f"\nLayer-2-only months (bucket ≥ {bucket_thr:g}, T < {primary_thr:g}): "
        f"{len(layer2_only)}"
    )
    for r in layer2_only:
        print(
            f"  {r['curr']:<12} T={r['weighted_abs_bp']:5.1f} "
            f"bucket={r['max_bucket_abs_bp']:5.1f} ({r['max_bucket_label']})"
        )
    if args.detail:
        print("\nAll intervals:")
        print(
            f"  {'prev':<12} {'curr':<12} {'T':>8} {'S':>8} "
            f"{'bucket':>8} {'mean|Δ|':>8}"
        )
        for r in rows:
            print(
                f"  {r['prev']:<12} {r['curr']:<12} "
                f"{r['weighted_abs_bp']:8.1f} {r['weighted_signed_bp']:8.1f} "
                f"{r['max_bucket_abs_bp']:8.1f} {r['mean_abs_bp']:8.1f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
