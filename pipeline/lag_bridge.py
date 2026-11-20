#!/usr/bin/env python3
"""Valet lag bridge: shift held BoC zeros by benchmark moves since rf_asof.

EXPERIMENTAL → production default during lag (2026-11-20):
  Primary RF remains BoC zero-coupon CSV (shape + level at rf_asof).
  While publish_lag_days >= 1 and Valet has a newer observation than rf_asof,
  apply an additive shift interpolated from Valet Δ at 2/3/5/7/10/30(Long).

This is *not* inventing a new zero curve from sparse pars — it carries forward
the official BoC shape with a market-timed level/key-rate adjustment.

Usage (from the TVFI project root):

    python3 -m pipeline.lag_bridge
    python3 -m pipeline.lag_bridge --no-fetch
    python3 -m pipeline.lag_bridge --disable   # report only; no shift
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
CURVES_DIR = ROOT / "data" / "curves"

METHOD_ID = "valet_keyed_shift_v1"
METHOD_NOTE = (
    "Hold BoC zeros at rf_asof; add piecewise-linear key-rate shifts from Valet "
    "benchmark Δ (live − on/before rf_asof) at 2/3/5/7/10/30y. Soft-fails to "
    "unshifted BoC if Valet unavailable."
)


def _lerp(x0: float, y0: float, x1: float, y1: float, x: float) -> float:
    if x1 == x0:
        return y0
    w = (x - x0) / (x1 - x0)
    return y0 + w * (y1 - y0)


def interpolate_shifts(
    anchor_delta: Mapping[float, float],
    *,
    years: Sequence[int] = range(1, 31),
) -> Dict[int, float]:
    """Piecewise-linear Δ(year); flat outside the anchor span."""
    anchors = sorted((float(k), float(v)) for k, v in anchor_delta.items())
    if not anchors:
        return {int(y): 0.0 for y in years}
    xs = [a[0] for a in anchors]
    ys = [a[1] for a in anchors]
    out: Dict[int, float] = {}
    for y in years:
        x = float(y)
        if x <= xs[0]:
            out[int(y)] = ys[0]
            continue
        if x >= xs[-1]:
            out[int(y)] = ys[-1]
            continue
        for i in range(1, len(xs)):
            if xs[i - 1] <= x <= xs[i]:
                out[int(y)] = _lerp(xs[i - 1], ys[i - 1], xs[i], ys[i], x)
                break
    return out


def _yields_decimal(obs: Mapping[str, object]) -> Dict[float, float]:
    """Prefer yields_decimal; fall back from yields_pct."""
    dec = obs.get("yields_decimal")
    if isinstance(dec, dict) and dec:
        return {float(k): float(v) for k, v in dec.items()}
    pct = obs.get("yields_pct") or {}
    return {float(k): float(v) / 100.0 for k, v in pct.items()}


def compute_anchor_deltas(
    base_obs: Mapping[str, object],
    live_obs: Mapping[str, object],
) -> Dict[float, float]:
    """Δ = live − base at common Valet tenors (decimal rates)."""
    base = _yields_decimal(base_obs)
    live = _yields_decimal(live_obs)
    common = sorted(set(base) & set(live))
    if not common:
        raise RuntimeError("no overlapping Valet tenors between base and live")
    return {t: live[t] - base[t] for t in common}


def apply_shift_to_annual_zeros(
    annual_zeros: Mapping[int, float],
    shifts: Mapping[int, float],
) -> Dict[int, float]:
    """Additive shift on annual-effective spot rates (decimal)."""
    out: Dict[int, float] = {}
    for y, z in annual_zeros.items():
        out[int(y)] = float(z) + float(shifts.get(int(y), 0.0))
    return out


def should_bridge(
    *,
    publish_lag_days: Optional[int],
    rf_asof: str,
    valet_live_asof: str,
    min_lag_days: int = 1,
) -> Tuple[bool, str]:
    if publish_lag_days is None:
        try:
            publish_lag_days = (date.today() - date.fromisoformat(rf_asof)).days
        except ValueError:
            return False, "cannot parse rf_asof for lag"
    if publish_lag_days < min_lag_days:
        return False, f"publish_lag_days={publish_lag_days} < {min_lag_days}; no bridge"
    if valet_live_asof <= rf_asof:
        return (
            False,
            f"Valet live {valet_live_asof} not newer than rf_asof {rf_asof}",
        )
    return True, "lag present and Valet newer than rf_asof"


def bridge_boc_snapshot(
    boc_snapshot: Mapping[str, object],
    valet_snapshot: Mapping[str, object],
    *,
    min_lag_days: int = 1,
    enabled: bool = True,
) -> Tuple[Dict[int, float], dict]:
    """Return (annual_eff_1_30, bridge_meta).

    Always returns a usable annual RF dict. When the bridge does not apply,
    returns the original BoC annual zeros with ``applied=False`` meta.
    """
    from pipeline.boc_intake import annual_effective_rf_from_snapshot

    base_rf = annual_effective_rf_from_snapshot(boc_snapshot)
    rf_asof = str(boc_snapshot.get("rf_asof") or "")
    gaps = boc_snapshot.get("gaps") or {}
    publish_lag = gaps.get("publish_lag_days")
    if publish_lag is not None:
        publish_lag = int(publish_lag)

    meta: dict = {
        "method": METHOD_ID,
        "method_note": METHOD_NOTE,
        "applied": False,
        "enabled": enabled,
        "rf_asof": rf_asof,
        "publish_lag_days": publish_lag,
        "primary_rf_source": boc_snapshot.get("rf_source"),
    }

    if not enabled:
        meta["reason"] = "bridge disabled"
        return dict(base_rf), meta

    from pipeline import valet_intake

    live = valet_intake.latest_observation(valet_snapshot)
    if live is None:
        meta["reason"] = "no Valet observations"
        return dict(base_rf), meta

    live_asof = str(live["date"])
    meta["valet_live_asof"] = live_asof
    meta["valet_source_url"] = valet_snapshot.get("source_url")

    ok, reason = should_bridge(
        publish_lag_days=publish_lag,
        rf_asof=rf_asof,
        valet_live_asof=live_asof,
        min_lag_days=min_lag_days,
    )
    if not ok:
        meta["reason"] = reason
        return dict(base_rf), meta

    base_obs = valet_intake.find_observation_on_or_before(valet_snapshot, rf_asof)
    if base_obs is None:
        meta["reason"] = f"no Valet observation on/before rf_asof {rf_asof}"
        return dict(base_rf), meta

    base_asof = str(base_obs["date"])
    meta["valet_base_asof"] = base_asof
    try:
        anchors = compute_anchor_deltas(base_obs, live)
    except RuntimeError as exc:
        meta["reason"] = str(exc)
        return dict(base_rf), meta

    shifts = interpolate_shifts(anchors, years=range(1, 31))
    bridged = apply_shift_to_annual_zeros(base_rf, shifts)

    meta.update(
        {
            "applied": True,
            "reason": reason,
            "anchor_delta_bp": {str(int(k) if k == int(k) else k): v * 1e4 for k, v in sorted(anchors.items())},
            "shift_bp_sample": {
                str(y): shifts[y] * 1e4 for y in (1, 2, 5, 10, 20, 30) if y in shifts
            },
            "mean_abs_shift_bp": sum(abs(v) for v in shifts.values()) / len(shifts) * 1e4,
            "max_abs_shift_bp": max(abs(v) for v in shifts.values()) * 1e4,
        }
    )
    return bridged, meta


def bridge_from_disk(
    *,
    boc_snapshot_path: Optional[Path] = None,
    valet_snapshot_path: Optional[Path] = None,
    fetch_valet: bool = True,
    enabled: bool = True,
    min_lag_days: int = 1,
) -> Tuple[Dict[int, float], dict, dict, dict]:
    """Load BoC + Valet, optionally refresh Valet, apply bridge.

    Returns (annual_rf, bridge_meta, boc_snapshot, valet_snapshot).
    """
    from pipeline import boc_intake, valet_intake

    if boc_snapshot_path is None:
        boc_snapshot_path = boc_intake.find_preferred_boc_snapshot()
    if boc_snapshot_path is None:
        raise RuntimeError("no BoC snapshot under data/risk_free/")
    boc = boc_intake.load_snapshot(boc_snapshot_path)

    valet: Optional[dict] = None
    if fetch_valet:
        try:
            valet, _ = valet_intake.fetch_and_store(recent=60)
        except Exception as exc:  # noqa: BLE001
            print(f"Valet live download unavailable ({exc}); using cache", file=sys.stderr)

    if valet is None:
        try:
            valet = valet_intake.load_snapshot(valet_snapshot_path)
        except Exception as exc:  # noqa: BLE001
            # Soft-fail: return unshifted BoC
            rf = boc_intake.annual_effective_rf_from_snapshot(boc)
            meta = {
                "method": METHOD_ID,
                "applied": False,
                "enabled": enabled,
                "reason": f"Valet unavailable: {exc}",
                "rf_asof": boc.get("rf_asof"),
                "primary_rf_source": boc.get("rf_source"),
            }
            return rf, meta, boc, {}

    rf, meta = bridge_boc_snapshot(
        boc, valet, min_lag_days=min_lag_days, enabled=enabled
    )
    meta["boc_snapshot_path"] = str(boc_snapshot_path)
    return rf, meta, boc, valet


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-fetch", action="store_true", help="Skip live Valet download")
    p.add_argument("--disable", action="store_true", help="Force bridge off (report only)")
    p.add_argument("--min-lag-days", type=int, default=1)
    p.add_argument(
        "--boc-snapshot",
        type=Path,
        default=None,
        help="Pin a BoC JSON under data/risk_free/",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write bridge diagnostic JSON (default under data/curves/)",
    )
    args = p.parse_args(argv)

    rf, meta, boc, _valet = bridge_from_disk(
        boc_snapshot_path=args.boc_snapshot,
        fetch_valet=not args.no_fetch,
        enabled=not args.disable,
        min_lag_days=args.min_lag_days,
    )

    print(f"method:     {METHOD_ID}")
    print(f"rf_asof:    {meta.get('rf_asof')}")
    print(f"lag days:   {meta.get('publish_lag_days')}")
    print(f"applied:    {meta.get('applied')}")
    print(f"reason:     {meta.get('reason')}")
    if meta.get("applied"):
        print(f"valet base: {meta.get('valet_base_asof')}")
        print(f"valet live: {meta.get('valet_live_asof')}")
        print(f"max|Δ|:     {meta.get('max_abs_shift_bp'):.2f} bp")
        print(f"mean|Δ|:    {meta.get('mean_abs_shift_bp'):.2f} bp")
        print(f"anchors bp: {meta.get('anchor_delta_bp')}")
        print(f"sample bp:  {meta.get('shift_bp_sample')}")
    print(f"RF y1/y10/y30 %: {rf[1]*100:.4f} / {rf[10]*100:.4f} / {rf[30]*100:.4f}")

    out = args.out
    if out is None:
        CURVES_DIR.mkdir(parents=True, exist_ok=True)
        tag = "applied" if meta.get("applied") else "skipped"
        out = CURVES_DIR / f"lag_bridge_{meta.get('rf_asof', 'unknown')}_{tag}.json"
    payload = {
        "bridge": meta,
        "annual_zeros_1_30": [rf[y] for y in range(1, 31)],
        "boc_rf_asof": boc.get("rf_asof"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote:      {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
