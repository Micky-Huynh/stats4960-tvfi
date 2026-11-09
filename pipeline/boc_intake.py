#!/usr/bin/env python3
"""Bank of Canada zero-coupon yield curve CSV intake.

Primary RF source for TVFI monitoring (see docs/memos/daily-risk-free-source.md).

BoC publishes continuously compounded zeros on a 0.25y grid (0.25–30y). The file
is typically refreshed Thursday ~16:30 ET with an ~2-week structural lag.

Usage (from the TVFI project root):

    python3 -m pipeline.boc_intake
    python3 -m pipeline.boc_intake --window-days 45
    python3 -m pipeline.boc_intake --from-csv /path/to/boc.csv
    python3 -m pipeline.boc_intake --fixture-only   # write offline sample from cache/fixture
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
RISK_FREE_DIR = ROOT / "data" / "risk_free"

BOC_CSV_BASE = (
    "https://www.bankofcanada.ca/stats/results/csv"
    "?lookupPage=lookup_yield_curve.php"
)
DEFAULT_WINDOW_DAYS = 45
USER_AGENT = "TVFI-Group5-student-pipeline/1.0 (+STATS4960)"
LAG_NOTE = (
    "BoC zero-coupon CSV typically refreshes Thursday ~16:30 ET with ~2-week "
    "publication lag; hold last published curve as rf_asof."
)


def boc_csv_url(*, d_from: date, d_to: date) -> str:
    return f"{BOC_CSV_BASE}&dFrom={d_from.isoformat()}&dTo={d_to.isoformat()}"


def _zc_column(tenor_years: float) -> str:
    """BoC header for tenor years, e.g. 1.0 -> ZC100YR, 0.25 -> ZC025YR."""
    hundredths = int(round(tenor_years * 100))
    return f"ZC{hundredths:04d}YR"


def continuous_to_annual_effective(z: float) -> float:
    """Convert continuously compounded zero to annually compounded spot.

    DF = exp(-z t) = (1+s)^{-t}  ⇒  s = exp(z) - 1.
    Matches Fiera construction / curve_builder (1+s)^n forwards.
    """
    return math.exp(z) - 1.0


def fetch_boc_csv(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    as_of_calendar: Optional[date] = None,
    timeout: float = 30.0,
) -> Tuple[str, str]:
    """Download BoC zero-curve CSV. Returns (url, csv_text)."""
    end = as_of_calendar or date.today()
    start = end - timedelta(days=window_days)
    url = boc_csv_url(d_from=start, d_to=end)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"BoC CSV download failed: {exc}") from exc

    if "html" in ctype and "csv" not in ctype:
        raise RuntimeError(
            f"BoC returned non-CSV content-type {ctype!r}; likely maintenance HTML"
        )
    text = raw.decode("utf-8-sig")
    if not text.lstrip().startswith("Date"):
        raise RuntimeError(
            "BoC response did not start with Date header; refusing to parse as curve CSV"
        )
    return url, text


def _parse_rate(cell: str) -> Optional[float]:
    s = cell.strip()
    if not s or s.lower() == "na":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_boc_csv(text: str) -> Tuple[str, Dict[float, float]]:
    """Parse BoC CSV; return (latest_observation_date, {tenor_years: continuous_zero})."""
    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration as exc:
        raise RuntimeError("BoC CSV is empty") from exc

    headers = [h.strip() for h in header_row]
    if not headers or headers[0] != "Date":
        raise RuntimeError(f"Unexpected BoC CSV header: {headers[:5]!r}")

    # Map ZC###YR -> tenor years
    tenor_cols: List[Tuple[int, float]] = []
    for i, name in enumerate(headers):
        if not name.startswith("ZC") or not name.endswith("YR"):
            continue
        body = name[2:-2]
        if not body.isdigit():
            continue
        tenor_cols.append((i, int(body) / 100.0))

    if not tenor_cols:
        raise RuntimeError("No ZC*YR columns found in BoC CSV")

    latest_date: Optional[str] = None
    latest_rates: Dict[float, float] = {}

    for row in reader:
        if not row or not row[0].strip():
            continue
        obs = row[0].strip()
        rates: Dict[float, float] = {}
        ok = True
        for idx, tenor in tenor_cols:
            if idx >= len(row):
                ok = False
                break
            val = _parse_rate(row[idx])
            if val is None:
                ok = False
                break
            rates[tenor] = val
        if not ok or not rates:
            continue
        latest_date = obs
        latest_rates = rates

    if latest_date is None or not latest_rates:
        raise RuntimeError("No complete non-na BoC zero-curve row in CSV window")
    return latest_date, latest_rates


def interpolate_annual_tenors(
    grid: Mapping[float, float],
    *,
    years: Sequence[int] = range(1, 31),
    also_half: bool = True,
) -> Dict[float, float]:
    """Linear interpolate continuous zeros onto integer years (and optional 0.5)."""
    knots = sorted(grid.items())
    xs = [t for t, _ in knots]
    ys = [z for _, z in knots]

    def lerp(t: float) -> float:
        if t in grid:
            return float(grid[t])
        if t < xs[0] or t > xs[-1]:
            raise ValueError(f"tenor {t} outside BoC grid [{xs[0]}, {xs[-1]}]")
        # binary search neighbors
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= t:
                lo = mid
            else:
                hi = mid
        x0, x1 = xs[lo], xs[hi]
        y0, y1 = ys[lo], ys[hi]
        w = (t - x0) / (x1 - x0)
        return y0 + (y1 - y0) * w

    out: Dict[float, float] = {}
    if also_half and 0.5 in grid:
        out[0.5] = float(grid[0.5])
    elif also_half:
        out[0.5] = lerp(0.5)
    for y in years:
        out[float(y)] = lerp(float(y))
    return out


def build_snapshot(
    *,
    rf_asof: str,
    continuous_grid: Mapping[float, float],
    source_url: str,
    fetched_at: Optional[str] = None,
    is_fixture: bool = False,
    calendar_today: Optional[date] = None,
) -> dict:
    """Build pipeline snapshot JSON (continuous grid + annual effective 1–30)."""
    fetched = fetched_at or datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )
    today = calendar_today or date.today()
    asof_d = date.fromisoformat(rf_asof)
    publish_lag_days = (today - asof_d).days

    annual_cont = interpolate_annual_tenors(continuous_grid, years=range(1, 31), also_half=True)
    tenors_sorted = sorted(continuous_grid.keys())
    zeros_sorted = [float(continuous_grid[t]) for t in tenors_sorted]

    annual_years = list(range(1, 31))
    annual_cont_1_30 = [float(annual_cont[float(y)]) for y in annual_years]
    annual_eff_1_30 = [continuous_to_annual_effective(z) for z in annual_cont_1_30]

    return {
        "rf_source": "boc_zero_coupon_csv",
        "rf_asof": rf_asof,
        "fetched_at": fetched,
        "source_url": source_url,
        "is_fixture": is_fixture,
        "quote_convention": "continuous_zero_decimal",
        "builder_quote_convention": "annual_effective_spot_decimal",
        "methodology": "Bolder-Johnson-Metzler-2004",
        "lag_note": LAG_NOTE,
        "tenors_years": tenors_sorted,
        "zeros": zeros_sorted,
        "annual_tenors_years": annual_years,
        "annual_zeros_continuous_1_30": annual_cont_1_30,
        "annual_zeros_1_30": annual_eff_1_30,
        "half_year_continuous": float(annual_cont[0.5]) if 0.5 in annual_cont else None,
        "gaps": {
            "official_max_maturity_years": 30,
            "extrapolation_policy": "curve_builder_uses_static_ultimate_beyond_obs",
            "publish_lag_days": publish_lag_days,
        },
    }


def write_snapshot(snapshot: Mapping[str, object], out_dir: Path = RISK_FREE_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{snapshot['rf_asof']}.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return path


def write_fixture_sample(
    snapshot: Mapping[str, object],
    out_dir: Path = RISK_FREE_DIR,
) -> Path:
    """Compact offline sample (real BoC observation, labeled is_fixture)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep a thin grid: 0.25, 0.5, then annual 1–30 continuous zeros from snapshot
    thin_tenors = [0.25, 0.5] + list(range(1, 31))
    tenors = snapshot["tenors_years"]
    zeros = snapshot["zeros"]
    by_t = {float(t): float(z) for t, z in zip(tenors, zeros)}
    sample_tenors = []
    sample_zeros = []
    for t in thin_tenors:
        ft = float(t)
        if ft in by_t:
            sample_tenors.append(ft)
            sample_zeros.append(by_t[ft])
        elif abs(ft - int(ft)) < 1e-9:
            # annual already in annual_zeros_continuous
            idx = int(ft) - 1
            cont = snapshot["annual_zeros_continuous_1_30"][idx]
            sample_tenors.append(ft)
            sample_zeros.append(float(cont))

    fixture = {
        **dict(snapshot),
        "is_fixture": True,
        "fixture_note": (
            "Offline sample derived from a real BoC CSV observation "
            f"(rf_asof={snapshot['rf_asof']}); not synthetic rates. "
            "Use when live download is unavailable."
        ),
        "tenors_years": sample_tenors,
        "zeros": sample_zeros,
    }
    path = out_dir / "fixture_boc_zeros_sample.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return path


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def annual_effective_rf_from_snapshot(snapshot: Mapping[str, object]) -> Dict[int, float]:
    """Years 1–30 annual-effective spots for curve_builder."""
    rates = snapshot.get("annual_zeros_1_30")
    years = snapshot.get("annual_tenors_years") or list(range(1, 31))
    if rates is None:
        raise ValueError(f"snapshot missing annual_zeros_1_30: {path_hint(snapshot)}")
    if len(rates) < 30:
        raise ValueError(f"expected 30 annual zeros, got {len(rates)}")
    return {int(y): float(r) for y, r in zip(years, rates)}


def path_hint(snapshot: Mapping[str, object]) -> str:
    return str(snapshot.get("rf_asof", "<unknown>"))


def find_latest_snapshot(out_dir: Path = RISK_FREE_DIR) -> Optional[Path]:
    if not out_dir.is_dir():
        return None
    dated = sorted(
        (p for p in out_dir.glob("????-??-??.json") if p.is_file()),
        key=lambda p: p.stem,
    )
    return dated[-1] if dated else None


def load_risk_free_for_builder(
    *,
    snapshot_path: Optional[Path] = None,
    out_dir: Path = RISK_FREE_DIR,
    try_download: bool = True,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Tuple[str, Dict[int, float], dict, Path]:
    """Return (rf_asof, {1..30: annual_eff}, snapshot, path_used).

    Prefers live download; falls back to latest dated snapshot, then fixture sample.
    """
    snapshot: Optional[dict] = None
    path_used: Optional[Path] = None
    source_url = ""

    if snapshot_path is not None:
        snapshot = load_snapshot(snapshot_path)
        path_used = snapshot_path
    elif try_download:
        try:
            source_url, text = fetch_boc_csv(window_days=window_days)
            rf_asof, grid = parse_boc_csv(text)
            snapshot = build_snapshot(
                rf_asof=rf_asof,
                continuous_grid=grid,
                source_url=source_url,
                is_fixture=False,
            )
            path_used = write_snapshot(snapshot, out_dir)
            write_fixture_sample(snapshot, out_dir)
        except Exception as exc:  # noqa: BLE001 — intentional soft fallback
            print(f"BoC live download unavailable ({exc}); falling back to cached snapshot", file=sys.stderr)

    if snapshot is None:
        path_used = find_latest_snapshot(out_dir)
        if path_used is None:
            fixture = out_dir / "fixture_boc_zeros_sample.json"
            if fixture.is_file():
                path_used = fixture
        if path_used is None:
            raise RuntimeError(
                f"No BoC snapshot available under {out_dir}. "
                f"Download with: python3 -m pipeline.boc_intake "
                f"(URL pattern: {BOC_CSV_BASE}&dFrom=YYYY-MM-DD&dTo=YYYY-MM-DD)"
            )
        snapshot = load_snapshot(path_used)

    rf_asof = str(snapshot["rf_asof"])
    rf = annual_effective_rf_from_snapshot(snapshot)
    return rf_asof, rf, snapshot, path_used


def ingest(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    csv_path: Optional[Path] = None,
    out_dir: Path = RISK_FREE_DIR,
    write_fixture: bool = True,
) -> Tuple[dict, Path]:
    if csv_path is not None:
        text = csv_path.read_text(encoding="utf-8-sig")
        source_url = f"file://{csv_path.resolve()}"
    else:
        source_url, text = fetch_boc_csv(window_days=window_days)
    rf_asof, grid = parse_boc_csv(text)
    snapshot = build_snapshot(
        rf_asof=rf_asof,
        continuous_grid=grid,
        source_url=source_url,
        is_fixture=False,
    )
    path = write_snapshot(snapshot, out_dir)
    if write_fixture:
        write_fixture_sample(snapshot, out_dir)
    return snapshot, path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Rolling calendar window ending today (default {DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=None,
        help="Parse a local BoC CSV instead of downloading",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=RISK_FREE_DIR,
        help=f"Snapshot output directory (default: {RISK_FREE_DIR})",
    )
    parser.add_argument(
        "--no-fixture",
        action="store_true",
        help="Do not refresh fixture_boc_zeros_sample.json",
    )
    args = parser.parse_args(argv)

    snapshot, path = ingest(
        window_days=args.window_days,
        csv_path=args.from_csv,
        out_dir=args.out_dir,
        write_fixture=not args.no_fixture,
    )
    print(f"rf_asof:          {snapshot['rf_asof']}")
    print(f"fetched_at:       {snapshot['fetched_at']}")
    print(f"is_fixture:       {snapshot['is_fixture']}")
    print(f"publish_lag_days: {snapshot['gaps']['publish_lag_days']}")
    print(f"lag_note:         {snapshot['lag_note']}")
    print(f"source_url:       {snapshot['source_url']}")
    print(f"wrote snapshot:   {path}")
    if not args.no_fixture:
        print(f"wrote fixture:    {args.out_dir / 'fixture_boc_zeros_sample.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
