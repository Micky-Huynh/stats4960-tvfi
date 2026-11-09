"""Load archived Fiera monthly curves from extracted history CSVs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "fiera" / "extracted" / "history"
LATEST = ROOT / "data" / "fiera" / "extracted" / "latest"

DISPLAY_MATURITIES = [1, 2, 3, 5, 7, 10, 15, 20, 30]


def _f(x: str) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def load_forward_curves() -> Dict[str, Dict[int, float]]:
    """as_of -> {year: annual_forward_rate (decimal)}."""
    path = HISTORY / "liquidity_premium_by_month.csv"
    out: Dict[str, Dict[int, float]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            as_of = row["as_of"]
            year = _f(row["year"])
            fwd = _f(row["annual_forward_rate"])
            if year is None or fwd is None:
                continue
            y = int(year)
            out.setdefault(as_of, {})[y] = fwd
    return out


def load_canada_par_curves() -> Dict[str, Dict[int, float]]:
    """as_of -> {term_years: canada_par (decimal)}."""
    path = HISTORY / "canada_par_by_month.csv"
    out: Dict[str, Dict[int, float]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            as_of = row["as_of"]
            term = _f(row["term_years"])
            rate = _f(row["canada_par"])
            if term is None or rate is None:
                continue
            # Keep integer years only for dashboard nodes.
            if abs(term - round(term)) > 1e-9:
                continue
            out.setdefault(as_of, {})[int(round(term))] = rate
    return out


def sorted_as_of(curves: Dict[str, dict]) -> List[str]:
    return sorted(curves.keys())


def pick_at_maturities(
    curve: Dict[int, float], maturities: List[int]
) -> List[Optional[float]]:
    return [curve.get(m) for m in maturities]


def to_percent(rates: List[Optional[float]]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for r in rates:
        out.append(None if r is None else round(r * 100.0, 4))
    return out


def latest_pair(
    curves: Dict[str, Dict[int, float]],
) -> Tuple[str, str, Dict[int, float], Dict[int, float]]:
    dates = sorted_as_of(curves)
    if len(dates) < 2:
        raise RuntimeError("Need at least two monthly Fiera publications")
    prev, curr = dates[-2], dates[-1]
    return prev, curr, curves[prev], curves[curr]
