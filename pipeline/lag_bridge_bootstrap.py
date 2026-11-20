#!/usr/bin/env python3
"""Lag remedy: predict RF with Ridge / PCA / PCA+Ridge, then IoA-bootstrap each.

For a user-chosen calendar interval (BoC publish lag window), this module:

1. Pulls Valet observations in ``[--from, --to]`` (or ``--lag-days`` from BoC rf_asof).
2. For **each** Valet date, builds three predicted annual-effective zero curves:
   - ``ridge``      — multi-output Ridge Valet → BoC zeros
   - ``pca``        — interpolate Valet anchors → dense curve, then PCA-project
                      onto the historical BoC eigenspace (PCA curve)
   - ``pca_ridge``  — PCA factors + Ridge map Valet → scores → reconstruct
3. Runs the IoA/CM1 annual-par bootstrap **separately** on each prediction
   (zeros → implied par → DF / zero / 1y forward via ``pipeline.bootstrap``).
4. Writes per-method artifacts under ``data/curves/lag_bootstrap/``.
5. Exports a multi-sheet Excel workbook with all predicted zeros + bootstrap
   curves (``lag_bootstrap_curves.xlsx`` by default).

This does **not** replace the keyed Valet shift default on ``--rebuilt``. It is
the statistical lag-remedy path that produces bootstrapped rate curves from
each nowcast model.

Usage (from the TVFI project root)::

    python3 -m pipeline.lag_bridge_bootstrap
    python3 -m pipeline.lag_bridge_bootstrap --from 2026-11-04 --to 2026-11-19
    python3 -m pipeline.lag_bridge_bootstrap --lag-days 16
    python3 -m pipeline.lag_bridge_bootstrap --methods ridge,pca,pca_ridge --build-j
    python3 -m pipeline.lag_bridge_bootstrap --xlsx-only   # rebuild Excel from existing JSON
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
CURVES_DIR = ROOT / "data" / "curves"
OUT_DIR = CURVES_DIR / "lag_bootstrap"
MODEL_DIR = ROOT / "data" / "models"

YEARS = tuple(range(1, 31))
VALET_ANCHORS = (2.0, 3.0, 5.0, 7.0, 10.0, 30.0)

METHOD_IDS = {
    "ridge": "ridge_mlr_then_bootstrap",
    "pca": "pca_curve_then_bootstrap",
    "pca_ridge": "pca_ridge_then_bootstrap",
}


def _zeros_to_vector(zeros: Mapping[int, float]) -> np.ndarray:
    return np.array([float(zeros[y]) for y in YEARS], dtype=float)


def _vector_to_zeros(v: np.ndarray) -> Dict[int, float]:
    return {int(y): float(v[i]) for i, y in enumerate(YEARS)}


def interpolate_valet_to_annual(
    obs: Mapping[str, object],
    *,
    anchors: Sequence[float] = VALET_ANCHORS,
) -> Dict[int, float]:
    """Piecewise-linear Valet benchmarks → dense annual yields 1..30 (decimal)."""
    from pipeline.lag_bridge import _lerp, _yields_decimal

    yld = _yields_decimal(obs)
    pts = sorted((float(a), float(yld[a])) for a in anchors if a in yld)
    if len(pts) < 2:
        raise RuntimeError("need ≥2 Valet anchors to interpolate a PCA input curve")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    out: Dict[int, float] = {}
    for y in YEARS:
        x = float(y)
        if x <= xs[0]:
            out[y] = ys[0]
        elif x >= xs[-1]:
            out[y] = ys[-1]
        else:
            for i in range(1, len(xs)):
                if xs[i - 1] <= x <= xs[i]:
                    out[y] = _lerp(xs[i - 1], ys[i - 1], xs[i], ys[i], x)
                    break
    return out


def pca_project_curve(
    dense_zeros: Mapping[int, float],
    pca: object,
) -> Dict[int, float]:
    """Project a dense annual curve onto the fitted BoC PCA subspace."""
    v = _zeros_to_vector(dense_zeros).reshape(1, -1)
    scores = pca.transform(v)
    recon = np.asarray(pca.inverse_transform(scores)[0], dtype=float)
    return _vector_to_zeros(recon)


def bootstrap_predicted_zeros(
    zeros: Mapping[int, float],
) -> Tuple[object, Dict[int, float]]:
    """IoA bootstrap: annual zeros → implied par → DF / zero / forward curve.

    Returns (BootstrapCurve, par_by_year).
    """
    from pipeline.bootstrap import bootstrap_annual_par, par_from_zeros

    par = par_from_zeros(zeros)
    # Ensure contiguous 1..30
    years = list(YEARS)
    missing = [y for y in years if y not in par]
    if missing:
        raise RuntimeError(f"par_from_zeros missing years {missing[:5]}")
    curve = bootstrap_annual_par(par, years=years)
    return curve, par


def _feature_row_for_date(
    valet_snapshot: Mapping[str, object],
    valet_obs: Mapping[str, object],
    boc_rf_asof: str,
    *,
    feature_mode: str,
) -> np.ndarray:
    from pipeline.lag_bridge_mlr import _valet_vector

    x_live = _valet_vector(valet_obs)
    if feature_mode == "levels":
        return x_live
    from pipeline import valet_intake

    base = valet_intake.find_observation_on_or_before(valet_snapshot, boc_rf_asof)
    if base is None:
        # Fall back to levels-only if no base print
        return x_live
    x_base = _valet_vector(base)
    return np.concatenate([x_live, x_live - x_base])


def predict_zeros_for_obs(
    *,
    method: str,
    valet_snapshot: Mapping[str, object],
    valet_obs: Mapping[str, object],
    boc_rf_asof: str,
    ridge_bundle: Optional[dict],
    pca_bundle: Optional[dict],
    feature_mode: str = "levels_delta",
) -> Dict[int, float]:
    """Predicted annual-effective zeros for one Valet observation."""
    from pipeline.lag_bridge_mlr import predict_pca, predict_ridge

    if method == "ridge":
        if ridge_bundle is None:
            raise FileNotFoundError("ridge model not loaded; run lag_bridge_mlr --train")
        x = _feature_row_for_date(
            valet_snapshot, valet_obs, boc_rf_asof, feature_mode=feature_mode
        )
        # Feature width must match training
        n_feat = int(ridge_bundle.get("report", {}).get("n_features") or 0)
        if n_feat and x.shape[0] != n_feat:
            # Retry with levels if delta features mismatch
            x = _feature_row_for_date(
                valet_snapshot, valet_obs, boc_rf_asof, feature_mode="levels"
            )
            if x.shape[0] != n_feat and feature_mode == "levels_delta":
                # Pad/truncate shouldn't happen; raise clearly
                raise RuntimeError(
                    f"ridge feature width {x.shape[0]} != trained {n_feat}"
                )
        return predict_ridge(ridge_bundle["model"], x)

    if method == "pca_ridge":
        if pca_bundle is None or pca_bundle.get("pca") is None:
            raise FileNotFoundError("pca_ridge model not loaded; run lag_bridge_mlr --train")
        x = _feature_row_for_date(
            valet_snapshot, valet_obs, boc_rf_asof, feature_mode=feature_mode
        )
        n_feat = int(pca_bundle.get("report", {}).get("n_features") or 0)
        if n_feat and x.shape[0] != n_feat:
            x = _feature_row_for_date(
                valet_snapshot, valet_obs, boc_rf_asof, feature_mode="levels"
            )
        return predict_pca(pca_bundle["pca"], pca_bundle["model"], x)

    if method == "pca":
        # PCA curve: interpolate Valet → dense, project onto BoC PCA subspace
        if pca_bundle is None or pca_bundle.get("pca") is None:
            raise FileNotFoundError(
                "pca model (for eigenspace) not loaded; run lag_bridge_mlr --train --method pca"
            )
        dense = interpolate_valet_to_annual(valet_obs)
        return pca_project_curve(dense, pca_bundle["pca"])

    raise ValueError(f"unknown method {method!r}; expected ridge|pca|pca_ridge")


def resolve_interval(
    *,
    date_from: Optional[str],
    date_to: Optional[str],
    lag_days: Optional[int],
    boc_rf_asof: str,
) -> Tuple[str, str]:
    """Return (start, end) inclusive YYYY-MM-DD for the lag window."""
    if date_from and date_to:
        if date_from > date_to:
            raise SystemExit(f"--from {date_from} is after --to {date_to}")
        return date_from, date_to

    end = date_to or date.today().isoformat()
    if lag_days is not None:
        start_d = date.fromisoformat(end) - timedelta(days=int(lag_days))
        start = start_d.isoformat()
        # Prefer starting at rf_asof when lag_days spans past it
        if boc_rf_asof and boc_rf_asof > start:
            start = boc_rf_asof
        return start, end

    # Default: from BoC rf_asof through today (the publish-lag window)
    start = date_from or boc_rf_asof
    return start, end


def valet_obs_in_range(
    valet_snapshot: Mapping[str, object],
    start: str,
    end: str,
) -> List[dict]:
    rows = []
    for obs in valet_snapshot.get("observations") or []:
        d = str(obs.get("date") or "")
        if start <= d <= end:
            rows.append(obs)
    rows.sort(key=lambda o: str(o.get("date")))
    return rows


def load_model_bundles(
    feature_mode: str = "levels_delta",
) -> Tuple[Optional[dict], Optional[dict]]:
    from pipeline.lag_bridge_mlr import load_models

    ridge_path = MODEL_DIR / f"lag_bridge_ridge_{feature_mode}.pkl"
    pca_path = MODEL_DIR / f"lag_bridge_pca_{feature_mode}.pkl"
    ridge = load_models(ridge_path) if ridge_path.is_file() else None
    pca = load_models(pca_path) if pca_path.is_file() else None
    return ridge, pca


def curve_payload(
    *,
    method: str,
    valet_date: str,
    zeros: Mapping[int, float],
    par: Mapping[int, float],
    boot_curve: object,
    boc_rf_asof: str,
    interval: Tuple[str, str],
) -> dict:
    return {
        "experimental": True,
        "lag_remedy": True,
        "method": METHOD_IDS[method],
        "method_key": method,
        "valet_asof": valet_date,
        "boc_rf_asof": boc_rf_asof,
        "interval": {"from": interval[0], "to": interval[1]},
        "note": (
            "Predicted annual-effective zeros from Valet nowcast, then IoA/CM1 "
            "annual-par bootstrap (zeros→par→DF/zero/forward). Separate artifact "
            "per model; does not replace keyed Valet shift default."
        ),
        "predicted_zeros_annual_effective": [
            {"year": y, "zero": zeros[y]} for y in YEARS
        ],
        "implied_par": [{"year": y, "par": par[y]} for y in YEARS],
        "bootstrap": boot_curve.as_rows(),
    }


def write_method_day(
    payload: dict,
    *,
    out_root: Path = OUT_DIR,
) -> Path:
    method = payload["method_key"]
    day = payload["valet_asof"]
    d = out_root / method
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{day}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Also CSV of bootstrap rows for quick inspection
    csv_path = d / f"{day}_bootstrap.csv"
    rows = payload["bootstrap"]
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for row in rows:
                w.writerow(row)
    return path


def maybe_build_column_j(
    zeros: Mapping[int, float],
    *,
    method: str,
    valet_date: str,
    prem_as_of: Optional[str] = None,
) -> Optional[dict]:
    """Optional: rebuild Slope col J using bootstrapped zeros as RF."""
    from pipeline import curve_builder

    params = curve_builder.load_static_params()
    pub_as_of, premium = curve_builder.load_held_liquidity_premium(as_of=prem_as_of)
    forwards = curve_builder.build_column_j(zeros, premium, params)
    stem = f"illiquid_col_j_lagboot_{method}_{valet_date}_h_{pub_as_of}"
    out_dir = OUT_DIR / method
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = out_dir / f"{stem}.xlsx"
    csv_p = out_dir / f"{stem}.csv"
    curve_builder.write_slope_xlsx(forwards, xlsx)
    curve_builder.write_slope_csv(forwards, csv_p)
    return {
        "xlsx": str(xlsx),
        "csv": str(csv_p),
        "premium_as_of": pub_as_of,
        "n_forwards": len(forwards),
    }


def run_interval(
    *,
    start: str,
    end: str,
    methods: Sequence[str],
    feature_mode: str = "levels_delta",
    fetch_valet: bool = True,
    build_j: bool = False,
    latest_only: bool = False,
) -> dict:
    from pipeline import boc_intake, valet_intake

    boc_path = boc_intake.find_preferred_boc_snapshot()
    if boc_path is None:
        raise RuntimeError("no BoC snapshot under data/risk_free/")
    boc = boc_intake.load_snapshot(boc_path)
    boc_rf_asof = str(boc["rf_asof"])

    if fetch_valet:
        try:
            valet, _ = valet_intake.fetch_and_store(
                recent=None,
                start_date=start,
                end_date=end,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Valet fetch failed ({exc}); using cache", file=sys.stderr)
            valet = valet_intake.load_snapshot()
    else:
        valet = valet_intake.load_snapshot()

    obs_list = valet_obs_in_range(valet, start, end)
    if not obs_list:
        raise RuntimeError(
            f"no Valet observations in [{start}, {end}]; "
            "widen the window or refresh Valet cache"
        )
    if latest_only:
        obs_list = [obs_list[-1]]

    ridge_bundle, pca_bundle = load_model_bundles(feature_mode)
    summary: dict = {
        "interval": {"from": start, "to": end},
        "boc_rf_asof": boc_rf_asof,
        "boc_snapshot": str(boc_path),
        "feature_mode": feature_mode,
        "n_valet_days": len(obs_list),
        "methods": {},
    }

    for method in methods:
        summary["methods"][method] = {"days": [], "artifacts": []}

    for obs in obs_list:
        vdate = str(obs["date"])
        print(f"\n--- Valet {vdate} ---")
        for method in methods:
            try:
                zeros = predict_zeros_for_obs(
                    method=method,
                    valet_snapshot=valet,
                    valet_obs=obs,
                    boc_rf_asof=boc_rf_asof,
                    ridge_bundle=ridge_bundle,
                    pca_bundle=pca_bundle,
                    feature_mode=feature_mode,
                )
                boot, par = bootstrap_predicted_zeros(zeros)
                payload = curve_payload(
                    method=method,
                    valet_date=vdate,
                    zeros=zeros,
                    par=par,
                    boot_curve=boot,
                    boc_rf_asof=boc_rf_asof,
                    interval=(start, end),
                )
                path = write_method_day(payload)
                entry: dict = {
                    "valet_asof": vdate,
                    "json": str(path),
                    "spot_y1_pct": zeros[1] * 100.0,
                    "spot_y10_pct": zeros[10] * 100.0,
                    "spot_y30_pct": zeros[30] * 100.0,
                    "fwd_y10_pct": boot.forwards_1y[9] * 100.0,
                }
                if build_j:
                    jinfo = maybe_build_column_j(
                        # Use bootstrapped annual-effective zeros as RF input
                        {
                            y: boot.zeros_annual_effective[i]
                            for i, y in enumerate(YEARS)
                        },
                        method=method,
                        valet_date=vdate,
                    )
                    entry["column_j"] = jinfo
                    payload["column_j"] = jinfo
                    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                summary["methods"][method]["days"].append(entry)
                summary["methods"][method]["artifacts"].append(str(path))
                print(
                    f"  {method:10s}  z1={zeros[1]*100:.3f}%  "
                    f"z10={zeros[10]*100:.3f}%  z30={zeros[30]*100:.3f}%  "
                    f"→ {path.name}"
                )
            except Exception as exc:  # noqa: BLE001
                err = {"valet_asof": vdate, "error": str(exc)}
                summary["methods"][method]["days"].append(err)
                print(f"  {method:10s}  FAIL: {exc}", file=sys.stderr)

    # Latest-day convenience copies
    for method in methods:
        days = [
            d
            for d in summary["methods"][method]["days"]
            if "json" in d
        ]
        if not days:
            continue
        latest = days[-1]
        src = Path(latest["json"])
        latest_path = OUT_DIR / method / "latest.json"
        latest_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        summary["methods"][method]["latest"] = str(latest_path)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / f"summary_{start}_to_{end}.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _load_day_payloads(
    *,
    out_root: Path = OUT_DIR,
    methods: Optional[Sequence[str]] = None,
    summary: Optional[Mapping[str, object]] = None,
) -> List[dict]:
    """Load all day JSON payloads from disk (or from summary artifact paths)."""
    methods = list(methods) if methods else list(METHOD_IDS.keys())
    payloads: List[dict] = []
    seen: set = set()

    if summary:
        for method in methods:
            block = (summary.get("methods") or {}).get(method) or {}
            for day in block.get("days") or []:
                path_s = day.get("json")
                if not path_s:
                    continue
                path = Path(path_s)
                if not path.is_file():
                    # Relative to OUT_DIR if absolute path moved
                    alt = out_root / method / path.name
                    path = alt if alt.is_file() else path
                if not path.is_file() or str(path) in seen:
                    continue
                try:
                    payloads.append(json.loads(path.read_text(encoding="utf-8")))
                    seen.add(str(path))
                except (OSError, json.JSONDecodeError):
                    continue

    # Also sweep OUT_DIR/{method}/*.json (skip latest.json duplicates by valet_asof)
    for method in methods:
        d = out_root / method
        if not d.is_dir():
            continue
        for path in sorted(d.glob("????-??-??.json")):
            if str(path) in seen:
                continue
            try:
                payloads.append(json.loads(path.read_text(encoding="utf-8")))
                seen.add(str(path))
            except (OSError, json.JSONDecodeError):
                continue

    payloads.sort(
        key=lambda p: (
            str(p.get("method_key") or ""),
            str(p.get("valet_asof") or ""),
        )
    )
    return payloads


def _sheet_name(name: str) -> str:
    """Excel sheet names: ≤31 chars, no \\ / ? * [ ]."""
    bad = '\\/?*[]'
    cleaned = "".join("_" if c in bad else c for c in name)[:31]
    return cleaned or "Sheet"


def export_lag_bootstrap_xlsx(
    *,
    out_path: Optional[Path] = None,
    out_root: Path = OUT_DIR,
    summary: Optional[Mapping[str, object]] = None,
    methods: Optional[Sequence[str]] = None,
) -> Path:
    """Write a multi-sheet workbook of all predicted + bootstrapped curves.

    Sheets
    ------
    Notes
        What the file contains / conventions.
    Summary
        Interval, BoC rf_asof, methods, day counts.
    Predicted_Zeros
        Long: method, valet_asof, year, zero, zero_pct.
    Implied_Par
        Long: method, valet_asof, year, par, par_pct.
    Bootstrap
        Long: method, valet_asof, year, par, discount_factor,
        zero_annual_effective, zero_pct, forward_1y, forward_pct.
    Spot_Wide_Latest
        Years 1–30 as columns; one row per method (latest Valet day).
    Fwd_Wide_Latest
        Same for bootstrapped 1y forwards.
    Spot_Wide_AllDays
        method + valet_asof rows × year columns (predicted zeros %).
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise SystemExit(
            "openpyxl is required for Excel export: pip install openpyxl"
        ) from exc

    methods = list(methods) if methods else list(METHOD_IDS.keys())
    if summary is None:
        # Prefer newest summary_*.json under out_root
        summaries = sorted(out_root.glob("summary_*.json"))
        if summaries:
            summary = json.loads(summaries[-1].read_text(encoding="utf-8"))

    payloads = _load_day_payloads(
        out_root=out_root, methods=methods, summary=summary
    )
    if not payloads:
        raise RuntimeError(
            f"no lag_bootstrap day JSON under {out_root}; "
            "run pipeline.lag_bridge_bootstrap first"
        )

    wb = Workbook()

    # --- Notes ---
    ws = wb.active
    ws.title = _sheet_name("Notes")
    notes = [
        "TVFI Group 5 — Lag-remedy prediction + IoA bootstrap curves",
        "",
        "Rates are annual-effective decimals unless _pct columns (×100).",
        "Predicted_Zeros: Valet → BoC annual-effective zeros from Ridge / PCA / PCA+Ridge.",
        "Implied_Par: CM1 par yields implied from those zeros (par_from_zeros).",
        "Bootstrap: IoA/CM1 annual-par strip (par, DF, zero, 1y forward).",
        "Spot_Wide_Latest / Fwd_Wide_Latest: latest Valet day only, years as columns (%).",
        "Spot_Wide_AllDays: every method × Valet day, years as columns (%).",
        "",
        "Experimental — does not replace keyed Valet shift (--rebuilt default).",
        "Primary RF remains BoC zeros; Fiera H still held between monthly pubs.",
        f"Generated from: {out_root}",
    ]
    for i, line in enumerate(notes, start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 100
    ws["A1"].font = Font(bold=True)

    # --- Summary ---
    ws = wb.create_sheet(_sheet_name("Summary"))
    interval = (summary or {}).get("interval") or {}
    meta_rows = [
        ("interval_from", interval.get("from")),
        ("interval_to", interval.get("to")),
        ("boc_rf_asof", (summary or {}).get("boc_rf_asof")),
        ("feature_mode", (summary or {}).get("feature_mode")),
        ("n_valet_days", (summary or {}).get("n_valet_days")),
        ("n_payloads_exported", len(payloads)),
        ("methods", ", ".join(methods)),
    ]
    ws.append(["key", "value"])
    for k, v in meta_rows:
        ws.append([k, v])
    ws.append([])
    ws.append(["method", "n_ok_days", "latest_valet_asof", "latest_json"])
    for method in methods:
        block = ((summary or {}).get("methods") or {}).get(method) or {}
        days_ok = [d for d in (block.get("days") or []) if d.get("json")]
        latest_asof = days_ok[-1]["valet_asof"] if days_ok else None
        ws.append(
            [
                method,
                len(days_ok),
                latest_asof,
                block.get("latest") or (days_ok[-1].get("json") if days_ok else None),
            ]
        )
    for col in range(1, 5):
        ws.column_dimensions[get_column_letter(col)].width = 28

    # --- Long sheets ---
    ws_z = wb.create_sheet(_sheet_name("Predicted_Zeros"))
    ws_z.append(["method", "valet_asof", "boc_rf_asof", "year", "zero", "zero_pct"])
    ws_p = wb.create_sheet(_sheet_name("Implied_Par"))
    ws_p.append(["method", "valet_asof", "boc_rf_asof", "year", "par", "par_pct"])
    ws_b = wb.create_sheet(_sheet_name("Bootstrap"))
    ws_b.append(
        [
            "method",
            "valet_asof",
            "boc_rf_asof",
            "year",
            "par",
            "discount_factor",
            "zero_annual_effective",
            "zero_pct",
            "forward_1y",
            "forward_pct",
        ]
    )

    # Track latest per method for wide sheets
    latest_by_method: Dict[str, dict] = {}

    for payload in payloads:
        method = str(payload.get("method_key") or "")
        valet_asof = str(payload.get("valet_asof") or "")
        boc_rf = str(payload.get("boc_rf_asof") or "")
        if method not in latest_by_method or valet_asof >= str(
            latest_by_method[method].get("valet_asof") or ""
        ):
            latest_by_method[method] = payload

        for row in payload.get("predicted_zeros_annual_effective") or []:
            z = float(row["zero"])
            ws_z.append(
                [method, valet_asof, boc_rf, int(float(row["year"])), z, z * 100.0]
            )
        for row in payload.get("implied_par") or []:
            c = float(row["par"])
            ws_p.append(
                [method, valet_asof, boc_rf, int(float(row["year"])), c, c * 100.0]
            )
        for row in payload.get("bootstrap") or []:
            z = float(row["zero_annual_effective"])
            f = float(row["forward_1y"])
            ws_b.append(
                [
                    method,
                    valet_asof,
                    boc_rf,
                    int(float(row["year"])),
                    float(row["par"]),
                    float(row["discount_factor"]),
                    z,
                    z * 100.0,
                    f,
                    f * 100.0,
                ]
            )

    for ws in (ws_z, ws_p, ws_b):
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 16

    def _wide_sheet(title: str, field: str, source: str) -> None:
        """field: 'zero' from predicted, or 'forward_1y' / 'zero_annual_effective' from bootstrap."""
        ws = wb.create_sheet(_sheet_name(title))
        header = ["method", "valet_asof", "boc_rf_asof"] + [f"y{y}" for y in YEARS]
        ws.append(header)
        for method in methods:
            payload = latest_by_method.get(method)
            if not payload:
                continue
            if source == "predicted":
                by_year = {
                    int(float(r["year"])): float(r["zero"]) * 100.0
                    for r in (payload.get("predicted_zeros_annual_effective") or [])
                }
            else:
                by_year = {
                    int(float(r["year"])): float(r[field]) * 100.0
                    for r in (payload.get("bootstrap") or [])
                }
            ws.append(
                [
                    method,
                    payload.get("valet_asof"),
                    payload.get("boc_rf_asof"),
                ]
                + [by_year.get(y) for y in YEARS]
            )
        for col in range(1, len(header) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 12

    _wide_sheet("Spot_Wide_Latest", "zero", "predicted")
    _wide_sheet("Fwd_Wide_Latest", "forward_1y", "bootstrap")

    # All days wide predicted spots
    ws_all = wb.create_sheet(_sheet_name("Spot_Wide_AllDays"))
    header = ["method", "valet_asof", "boc_rf_asof"] + [f"y{y}" for y in YEARS]
    ws_all.append(header)
    for payload in payloads:
        by_year = {
            int(float(r["year"])): float(r["zero"]) * 100.0
            for r in (payload.get("predicted_zeros_annual_effective") or [])
        }
        ws_all.append(
            [
                payload.get("method_key"),
                payload.get("valet_asof"),
                payload.get("boc_rf_asof"),
            ]
            + [by_year.get(y) for y in YEARS]
        )
    for col in range(1, len(header) + 1):
        ws_all.column_dimensions[get_column_letter(col)].width = 12

    # Stable download name + dated copy
    if out_path is None:
        interval = (summary or {}).get("interval") or {}
        stem_from = interval.get("from") or "unknown"
        stem_to = interval.get("to") or "unknown"
        out_path = out_root / f"lag_bootstrap_curves_{stem_from}_to_{stem_to}.xlsx"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)

    # Also write a stable alias for the dashboard download button
    alias = out_root / "lag_bootstrap_curves.xlsx"
    if out_path.resolve() != alias.resolve():
        alias.write_bytes(out_path.read_bytes())

    return out_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from", dest="date_from", default=None, help="Interval start YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="Interval end YYYY-MM-DD")
    p.add_argument(
        "--lag-days",
        type=int,
        default=None,
        help="If set (and --from omitted), start = end − lag-days (clamped to BoC rf_asof)",
    )
    p.add_argument(
        "--methods",
        default="ridge,pca,pca_ridge",
        help="Comma list: ridge, pca, pca_ridge (default all three)",
    )
    p.add_argument(
        "--feature-mode",
        choices=("levels", "levels_delta"),
        default="levels_delta",
    )
    p.add_argument("--no-fetch", action="store_true", help="Use cached Valet only")
    p.add_argument(
        "--latest-only",
        action="store_true",
        help="Only process the last Valet day in the interval",
    )
    p.add_argument(
        "--build-j",
        action="store_true",
        help="Also rebuild Slope col J from each bootstrapped RF curve",
    )
    p.add_argument(
        "--train-if-missing",
        action="store_true",
        help="Run lag_bridge_mlr --train if model pickles are missing",
    )
    p.add_argument(
        "--export-xlsx",
        dest="export_xlsx",
        action="store_true",
        help="Write multi-sheet Excel of all predictions + bootstrap curves (default ON)",
    )
    p.add_argument(
        "--no-export-xlsx",
        dest="export_xlsx",
        action="store_false",
        help="Skip Excel export after a predict→bootstrap run",
    )
    p.set_defaults(export_xlsx=True)
    p.add_argument(
        "--xlsx-only",
        action="store_true",
        help="Only build Excel from existing lag_bootstrap JSON (no predict/bootstrap)",
    )
    p.add_argument(
        "--xlsx-out",
        type=Path,
        default=None,
        help="Excel output path (default: data/curves/lag_bootstrap/lag_bootstrap_*.xlsx)",
    )
    args = p.parse_args(argv)

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    bad = [m for m in methods if m not in METHOD_IDS]
    if bad:
        raise SystemExit(f"unknown methods {bad}; choose from {list(METHOD_IDS)}")

    do_export = bool(args.export_xlsx)

    from pipeline import boc_intake

    boc_path = boc_intake.find_preferred_boc_snapshot()
    if boc_path is None:
        raise SystemExit("no BoC snapshot; run pipeline.boc_intake first")
    boc = boc_intake.load_snapshot(boc_path)
    boc_rf_asof = str(boc["rf_asof"])

    start, end = resolve_interval(
        date_from=args.date_from,
        date_to=args.date_to,
        lag_days=args.lag_days,
        boc_rf_asof=boc_rf_asof,
    )

    if args.xlsx_only:
        print(f"xlsx-only:  {start} → {end}")
        print(f"methods:    {methods}")
        print(f"out dir:    {OUT_DIR}")
        summary_path = OUT_DIR / f"summary_{start}_to_{end}.json"
        summary_payload: Optional[dict] = None
        if summary_path.is_file():
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        try:
            xlsx_path = export_lag_bootstrap_xlsx(
                methods=methods,
                out_path=args.xlsx_out,
                summary=summary_payload,
            )
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Excel export failed: {exc}") from exc
        print(f"wrote xlsx: {xlsx_path}")
        print(f"alias:      {OUT_DIR / 'lag_bootstrap_curves.xlsx'}")
        return 0

    ridge_b, pca_b = load_model_bundles(args.feature_mode)
    need_ridge = "ridge" in methods and ridge_b is None
    need_pca = (("pca" in methods) or ("pca_ridge" in methods)) and pca_b is None
    if (need_ridge or need_pca) and args.train_if_missing:
        print("Models missing — training via lag_bridge_mlr …")
        from pipeline import lag_bridge_mlr

        train_methods = []
        if need_ridge:
            train_methods.append("ridge")
        if need_pca:
            train_methods.append("pca")
        # Re-use CLI entry
        rc = lag_bridge_mlr.main(
            [
                "--train",
                "--method",
                "both" if len(train_methods) > 1 else train_methods[0],
                "--feature-mode",
                args.feature_mode,
                "--boc-window-days",
                "400",
            ]
        )
        if rc != 0:
            raise SystemExit(f"lag_bridge_mlr train failed rc={rc}")
        ridge_b, pca_b = load_model_bundles(args.feature_mode)
    elif need_ridge or need_pca:
        missing = []
        if need_ridge:
            missing.append(f"lag_bridge_ridge_{args.feature_mode}.pkl")
        if need_pca:
            missing.append(f"lag_bridge_pca_{args.feature_mode}.pkl")
        raise SystemExit(
            "Missing models: "
            + ", ".join(missing)
            + "\nRun: python3 -m pipeline.lag_bridge_mlr --train"
            "\nOr re-run with --train-if-missing"
        )

    print(f"interval:   {start} → {end}")
    print(f"boc rf:     {boc_rf_asof}")
    print(f"methods:    {methods}")
    print(f"out dir:    {OUT_DIR}")

    summary = run_interval(
        start=start,
        end=end,
        methods=methods,
        feature_mode=args.feature_mode,
        fetch_valet=not args.no_fetch,
        build_j=args.build_j,
        latest_only=args.latest_only,
    )
    print(f"\nwrote summary: {summary.get('summary_path')}")
    for method, block in summary["methods"].items():
        n_ok = sum(1 for d in block["days"] if "json" in d)
        n_err = sum(1 for d in block["days"] if "error" in d)
        print(f"  {method}: {n_ok} curves" + (f", {n_err} errors" if n_err else ""))
        if block.get("latest"):
            print(f"    latest → {block['latest']}")

    if do_export:
        try:
            xlsx_path = export_lag_bootstrap_xlsx(
                methods=methods,
                out_path=args.xlsx_out,
                summary=summary,
            )
            print(f"wrote xlsx: {xlsx_path}")
            print(f"alias:      {OUT_DIR / 'lag_bootstrap_curves.xlsx'}")
        except Exception as exc:  # noqa: BLE001
            print(f"Excel export failed: {exc}", file=sys.stderr)
            return 1

    print(
        "\nNOTE: three separate bootstrapped lag-remedy tracks. "
        "Keyed Valet shift remains the --rebuilt default."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
