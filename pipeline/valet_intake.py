#!/usr/bin/env python3
"""BoC Valet benchmark bond yields intake (lag-bridge feed).

Free, keyless, business-daily. Sparse tenors only (2/3/5/7/10/Long).
Used to *shift* held BoC zeros during the zero-curve publication lag —
not as a second primary RF curve.

    GET https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=N

Usage (from the TVFI project root):

    python3 -m pipeline.valet_intake
    python3 -m pipeline.valet_intake --recent 60
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
VALET_DIR = ROOT / "data" / "risk_free" / "valet"
VALET_URL = (
    "https://www.bankofcanada.ca/valet/observations/group/"
    "bond_yields_benchmark/json"
)
USER_AGENT = "TVFI-Group5-student-pipeline/1.0 (+STATS4960)"

# Valet series → maturity year used for the shift grid.
# Long-term benchmark mapped to 30y (end of BoC zero grid).
SERIES_TO_YEAR: Dict[str, float] = {
    "BD.CDN.2YR.DQ.YLD": 2.0,
    "BD.CDN.3YR.DQ.YLD": 3.0,
    "BD.CDN.5YR.DQ.YLD": 5.0,
    "BD.CDN.7YR.DQ.YLD": 7.0,
    "BD.CDN.10YR.DQ.YLD": 10.0,
    "BD.CDN.LONG.DQ.YLD": 30.0,
}
# Ignore RRB (real return) for nominal RF bridge.
IGNORE_SERIES = {"BD.CDN.RRB.DQ.YLD"}


def fetch_valet_json(
    *,
    recent: Optional[int] = 45,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeout: float = 30.0,
) -> Tuple[str, dict]:
    """Download Valet group JSON. Returns (url, payload).

    Prefer ``recent=N`` *or* ``start_date``/``end_date`` (YYYY-MM-DD). Valet
    rejects combining recent_* with an explicit date range.
    """
    if start_date or end_date:
        q = []
        if start_date:
            q.append(f"start_date={start_date}")
        if end_date:
            q.append(f"end_date={end_date}")
        url = f"{VALET_URL}?{'&'.join(q)}"
    else:
        url = f"{VALET_URL}?recent={int(recent or 45)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Valet download failed: {exc}") from exc
    if "json" not in ctype and "javascript" not in ctype:
        # Valet sometimes omits charset; still try parse if body looks like JSON.
        text_head = raw[:32].lstrip()
        if not text_head.startswith(b"{"):
            raise RuntimeError(f"Valet returned unexpected content-type {ctype!r}")
    payload = json.loads(raw.decode("utf-8"))
    if "observations" not in payload:
        raise RuntimeError("Valet JSON missing observations[]")
    return url, payload


def _obs_yields_pct(obs: Mapping[str, object]) -> Dict[float, float]:
    """Parse one observation into {tenor_years: yield_percent}."""
    out: Dict[float, float] = {}
    for series, year in SERIES_TO_YEAR.items():
        cell = obs.get(series)
        if not isinstance(cell, dict):
            continue
        raw = cell.get("v")
        if raw is None or raw == "":
            continue
        try:
            out[year] = float(raw)  # Valet unit = percent
        except (TypeError, ValueError):
            continue
    return out


def parse_observations(payload: Mapping[str, object]) -> List[dict]:
    """Return chronological list of {date, yields_pct, yields_decimal}."""
    rows: List[dict] = []
    for obs in payload.get("observations") or []:
        if not isinstance(obs, dict):
            continue
        d = obs.get("d")
        if not d:
            continue
        yld_pct = _obs_yields_pct(obs)
        if len(yld_pct) < 3:
            continue
        rows.append(
            {
                "date": str(d),
                "yields_pct": {str(int(k) if k == int(k) else k): v for k, v in sorted(yld_pct.items())},
                "yields_decimal": {
                    str(int(k) if k == int(k) else k): v / 100.0
                    for k, v in sorted(yld_pct.items())
                },
            }
        )
    rows.sort(key=lambda r: r["date"])
    return rows


def build_snapshot(
    *,
    observations: Sequence[Mapping[str, object]],
    source_url: str,
    fetched_at: Optional[str] = None,
) -> dict:
    fetched = fetched_at or datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )
    if not observations:
        raise RuntimeError("no Valet observations to store")
    latest = observations[-1]
    return {
        "overlay_source": "valet_bond_yields_benchmark",
        "fetched_at": fetched,
        "source_url": source_url,
        "quote_unit": "percent",
        "series_map": {k: v for k, v in SERIES_TO_YEAR.items()},
        "ignore_series": sorted(IGNORE_SERIES),
        "latest_asof": latest["date"],
        "latest_yields_pct": latest["yields_pct"],
        "observations": list(observations),
        "note": (
            "Business-daily GoC benchmark bond yields. Sparse tenors only. "
            "Used by pipeline.lag_bridge to shift held BoC zeros during publication lag."
        ),
    }


def write_snapshot(snapshot: Mapping[str, object], out_dir: Path = VALET_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "benchmarks_latest.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    # Also keep a dated copy of the latest observation day for audit.
    dated = out_dir / f"benchmarks_{snapshot['latest_asof']}.json"
    dated.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return path


def load_snapshot(path: Optional[Path] = None) -> dict:
    p = path or (VALET_DIR / "benchmarks_latest.json")
    return json.loads(p.read_text(encoding="utf-8"))


def find_observation_on_or_before(
    snapshot: Mapping[str, object],
    as_of: str,
) -> Optional[dict]:
    """Nearest Valet row with date <= as_of."""
    best: Optional[dict] = None
    for obs in snapshot.get("observations") or []:
        d = str(obs.get("date") or "")
        if d and d <= as_of:
            best = obs
    return best


def latest_observation(snapshot: Mapping[str, object]) -> Optional[dict]:
    rows = snapshot.get("observations") or []
    return rows[-1] if rows else None


def fetch_and_store(
    *,
    recent: Optional[int] = 45,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[dict, Path]:
    url, payload = fetch_valet_json(
        recent=recent, start_date=start_date, end_date=end_date
    )
    observations = parse_observations(payload)
    snap = build_snapshot(observations=observations, source_url=url)
    path = write_snapshot(snap)
    return snap, path


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recent", type=int, default=45, help="Valet recent=N observations")
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD (disables --recent)")
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD (disables --recent)")
    p.add_argument(
        "--from-json",
        type=Path,
        default=None,
        help="Parse a saved Valet JSON file instead of downloading",
    )
    args = p.parse_args(argv)

    if args.from_json is not None:
        payload = json.loads(args.from_json.read_text(encoding="utf-8"))
        url = str(args.from_json)
        observations = parse_observations(payload)
        snap = build_snapshot(observations=observations, source_url=url)
        path = write_snapshot(snap)
    else:
        if args.start_date or args.end_date:
            snap, path = fetch_and_store(
                recent=None, start_date=args.start_date, end_date=args.end_date
            )
        else:
            snap, path = fetch_and_store(recent=args.recent)

    latest = snap["latest_yields_pct"]
    print(f"valet asof:  {snap['latest_asof']}")
    print(f"wrote:       {path}")
    print(
        "yields %:   "
        + "  ".join(f"{k}y={float(v):.2f}" for k, v in sorted(latest.items(), key=lambda kv: float(kv[0])))
    )
    print(f"n obs:       {len(snap['observations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
