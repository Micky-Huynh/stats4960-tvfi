#!/usr/bin/env python3
"""Per-maturity margin of error for Valet → predict → IoA bootstrap nowcast.

Walk-forward (same design as ``lag_bootstrap_backtest``): for each test day *t*,
train only on dates before *t*, predict zeros, IoA-bootstrap, residual vs later
BoC zeros at each maturity year 1…30.

For each tenor reports (bp)::

    bias   = mean(pred − actual)
    sd     = sample std of residuals
    se     = sd / sqrt(n)          ← standard error of the mean residual
    rmse   = sqrt(mean(residual²))
    mae    = mean(|residual|)
    p50/p90 |e|  = quantiles of absolute residual (conformal-style half-width)

Also bins SE/RMSE by days-since-previous BoC date (lag-horizon stress).

This is **daily lag-bridge MoE**, not clock-hourly accuracy. Valet is
business-daily; free CAD data has no hourly ground truth.

Usage (from TVFI project root)::

    python3 -m pipeline.lag_error_report
    python3 -m pipeline.lag_error_report --methods ridge,pca_ridge
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
CURVES_DIR = ROOT / "data" / "curves"
OUT_JSON = CURVES_DIR / "lag_error_report.json"
OUT_CSV = CURVES_DIR / "lag_error_report_by_maturity.csv"

YEARS = tuple(range(1, 31))
KEY_TENORS = (1, 2, 5, 7, 10, 15, 20, 30)


def _dict_from_row(Y_row: np.ndarray) -> Dict[int, float]:
    return {int(y): float(Y_row[i]) for i, y in enumerate(YEARS)}


def _zeros_from_curve(curve: object) -> Dict[int, float]:
    return {int(y): float(z) for y, z in zip(curve.years, curve.zeros_annual_effective)}


def _residual_bp(pred: Mapping[int, float], actual: Mapping[int, float]) -> np.ndarray:
    """(pred − actual) × 1e4 for years 1…30."""
    return np.array(
        [(float(pred[y]) - float(actual[y])) * 1e4 for y in YEARS], dtype=float
    )


def _tenor_stats(err_panel: np.ndarray) -> List[dict]:
    """err_panel shape (n_days, 30). Returns one row per maturity year."""
    n = int(err_panel.shape[0])
    rows: List[dict] = []
    for i, y in enumerate(YEARS):
        e = err_panel[:, i]
        abs_e = np.abs(e)
        sd = float(np.std(e, ddof=1)) if n > 1 else 0.0
        se = sd / np.sqrt(n) if n > 0 else float("nan")
        rows.append(
            {
                "year": int(y),
                "n": n,
                "bias_bp": float(np.mean(e)),
                "sd_bp": sd,
                "se_bp": float(se),
                "rmse_bp": float(np.sqrt(np.mean(e**2))),
                "mae_bp": float(np.mean(abs_e)),
                "p50_abs_bp": float(np.median(abs_e)),
                "p90_abs_bp": float(np.quantile(abs_e, 0.90)),
                "max_abs_bp": float(np.max(abs_e)),
            }
        )
    return rows


def walk_forward_error_panels(
    X: np.ndarray,
    Y: np.ndarray,
    dates: Sequence[str],
    X_delta: np.ndarray,
    *,
    feature_mode: str = "levels_delta",
    alpha: float = 1.0,
    n_components: int = 3,
    min_train: int = 20,
    methods: Sequence[str] = ("ridge", "pca_ridge"),
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], List[str], np.ndarray]:
    """Return (pred_err, boot_err, test_dates, lag_days).

    pred_err / boot_err: method → (n_test, 30) residual bp panels.
    lag_days: calendar days since previous aligned BoC date (proxy for freshness).
    """
    from datetime import date as date_cls

    from pipeline.lag_bridge import _lerp
    from pipeline.lag_bridge_bootstrap import bootstrap_predicted_zeros, pca_project_curve
    from pipeline.lag_bridge_mlr import _make_features, fit_pca_ridge, fit_ridge
    from sklearn.decomposition import PCA

    anchors = (2.0, 3.0, 5.0, 7.0, 10.0, 30.0)
    pred_bufs: Dict[str, List[np.ndarray]] = {m: [] for m in methods}
    boot_bufs: Dict[str, List[np.ndarray]] = {m: [] for m in methods}
    test_dates: List[str] = []
    lag_days: List[float] = []

    for t in range(min_train, len(dates)):
        X_tr = _make_features(X[:t], X_delta[:t], feature_mode=feature_mode)
        Y_tr = Y[:t]
        X_te = _make_features(X[t : t + 1], X_delta[t : t + 1], feature_mode=feature_mode)
        actual = _dict_from_row(Y[t])

        d0 = date_cls.fromisoformat(dates[t - 1])
        d1 = date_cls.fromisoformat(dates[t])
        lag_days.append(float((d1 - d0).days))
        test_dates.append(dates[t])

        preds: Dict[str, Dict[int, float]] = {}

        if "ridge" in methods:
            model, _ = fit_ridge(X_tr, Y_tr, alpha=alpha)
            pred_v = model.predict(X_te)[0]
            preds["ridge"] = {y: float(pred_v[i]) for i, y in enumerate(YEARS)}

        if "pca_ridge" in methods:
            pca, ridge, _ = fit_pca_ridge(
                X_tr, Y_tr, n_components=n_components, alpha=alpha
            )
            scores = ridge.predict(X_te)
            pred_v = pca.inverse_transform(scores)[0]
            preds["pca_ridge"] = {y: float(pred_v[i]) for i, y in enumerate(YEARS)}

        if "pca" in methods:
            pca_fit = PCA(n_components=n_components)
            pca_fit.fit(Y_tr)
            pts = [(float(a), float(X[t, i])) for i, a in enumerate(anchors)]
            dense: Dict[int, float] = {}
            for y in YEARS:
                if y <= pts[0][0]:
                    dense[y] = pts[0][1]
                elif y >= pts[-1][0]:
                    dense[y] = pts[-1][1]
                else:
                    for j in range(len(pts) - 1):
                        if pts[j][0] <= y <= pts[j + 1][0]:
                            dense[y] = _lerp(
                                pts[j][0],
                                pts[j][1],
                                pts[j + 1][0],
                                pts[j + 1][1],
                                float(y),
                            )
                            break
            preds["pca"] = pca_project_curve(dense, pca_fit)

        for method, pred_z in preds.items():
            pred_bufs[method].append(_residual_bp(pred_z, actual))
            boot_curve, _ = bootstrap_predicted_zeros(pred_z)
            boot_z = _zeros_from_curve(boot_curve)
            boot_bufs[method].append(_residual_bp(boot_z, actual))

    pred_err = {m: np.vstack(v) for m, v in pred_bufs.items() if v}
    boot_err = {m: np.vstack(v) for m, v in boot_bufs.items() if v}
    return pred_err, boot_err, test_dates, np.asarray(lag_days, dtype=float)


def lag_horizon_bins(
    err_panel: np.ndarray,
    lag_days: np.ndarray,
    *,
    edges: Sequence[float] = (1, 3, 5, 8, 12, 20),
) -> List[dict]:
    """RMSE / mean |e| by calendar gap since previous BoC date."""
    abs_curve = np.mean(np.abs(err_panel), axis=1)  # mean |e| across tenors that day
    rmse_curve = np.sqrt(np.mean(err_panel**2, axis=1))
    bins: List[dict] = []
    lo = 0.0
    for hi in edges:
        mask = (lag_days > lo) & (lag_days <= hi)
        n = int(np.sum(mask))
        if n == 0:
            bins.append(
                {
                    "lag_days_lo": lo,
                    "lag_days_hi": float(hi),
                    "n": 0,
                    "mean_abs_bp": None,
                    "rmse_bp": None,
                }
            )
        else:
            bins.append(
                {
                    "lag_days_lo": lo,
                    "lag_days_hi": float(hi),
                    "n": n,
                    "mean_abs_bp": float(np.mean(abs_curve[mask])),
                    "rmse_bp": float(np.sqrt(np.mean(rmse_curve[mask] ** 2))),
                }
            )
        lo = float(hi)
    mask = lag_days > lo
    n = int(np.sum(mask))
    bins.append(
        {
            "lag_days_lo": lo,
            "lag_days_hi": None,
            "n": n,
            "mean_abs_bp": float(np.mean(abs_curve[mask])) if n else None,
            "rmse_bp": float(np.sqrt(np.mean(rmse_curve[mask] ** 2))) if n else None,
        }
    )
    return bins


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window-days", type=int, default=400)
    p.add_argument("--min-train", type=int, default=20)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--n-components", type=int, default=3)
    p.add_argument(
        "--feature-mode", default="levels_delta", choices=("levels", "levels_delta")
    )
    p.add_argument(
        "--methods",
        default="ridge,pca_ridge",
        help="Comma list (default ridge,pca_ridge — skip failing bare pca)",
    )
    p.add_argument("--out-json", type=Path, default=OUT_JSON)
    p.add_argument("--out-csv", type=Path, default=OUT_CSV)
    args = p.parse_args(list(argv) if argv is not None else None)

    from pipeline.lag_bridge_mlr import align_panel, fetch_boc_panel, fetch_valet_panel

    methods = tuple(m.strip() for m in args.methods.split(",") if m.strip())
    print("Fetching BoC panel…")
    boc_rows = fetch_boc_panel(window_days=args.window_days)
    print(f"BoC panel rows: {len(boc_rows)}  ({boc_rows[0][0]} → {boc_rows[-1][0]})")
    valet = fetch_valet_panel(recent=max(250, args.window_days // 2 + 50))
    X, Y, dates, X_delta = align_panel(boc_rows, valet)
    print(f"aligned rows:   {len(dates)}  ({dates[0]} → {dates[-1]})")
    print(
        f"walk-forward per-maturity MoE  methods={methods}  "
        f"min_train={args.min_train}  feature_mode={args.feature_mode}"
    )
    print(
        "NOTE: daily lag-bridge MoE (Valet business-daily). "
        "se_bp = sd(residuals)/sqrt(n) per tenor — not clock-hourly."
    )

    pred_err, boot_err, test_dates, lag_days = walk_forward_error_panels(
        X,
        Y,
        dates,
        X_delta,
        feature_mode=args.feature_mode,
        alpha=args.alpha,
        n_components=args.n_components,
        min_train=args.min_train,
        methods=methods,
    )

    report: dict = {
        "experimental": True,
        "label": "daily_lag_bridge_margin_of_error_not_clock_hourly",
        "feature_mode": args.feature_mode,
        "min_train": args.min_train,
        "window_days": args.window_days,
        "n_test": len(test_dates),
        "date_from": test_dates[0] if test_dates else None,
        "date_to": test_dates[-1] if test_dates else None,
        "definitions": {
            "bias_bp": "mean(pred − actual) × 1e4",
            "sd_bp": "sample std of residuals across walk-forward days",
            "se_bp": "sd_bp / sqrt(n) — standard error of mean residual at that tenor",
            "rmse_bp": "sqrt(mean(residual²))",
            "p90_abs_bp": "90th percentile of |residual| (approx 90% conformal half-width)",
        },
        "methods": {},
    }

    csv_rows: List[dict] = []

    for method in methods:
        if method not in boot_err:
            continue
        # Prefer boot residuals (post IoA); also store pred for reference
        boot_stats = _tenor_stats(boot_err[method])
        pred_stats = _tenor_stats(pred_err[method])
        lag_bins = lag_horizon_bins(boot_err[method], lag_days)

        # Curve-level summary
        all_e = boot_err[method].ravel()
        n_days = boot_err[method].shape[0]
        curve_rmse = float(np.sqrt(np.mean(boot_err[method] ** 2)))
        mean_se = float(np.mean([r["se_bp"] for r in boot_stats]))

        report["methods"][method] = {
            "n_days": n_days,
            "curve_rmse_bp": curve_rmse,
            "mean_tenor_se_bp": mean_se,
            "mean_tenor_rmse_bp": float(np.mean([r["rmse_bp"] for r in boot_stats])),
            "max_tenor_se_bp": float(np.max([r["se_bp"] for r in boot_stats])),
            "max_tenor_rmse_bp": float(np.max([r["rmse_bp"] for r in boot_stats])),
            "p90_abs_curve_bp": float(np.quantile(np.abs(all_e), 0.90)),
            "by_maturity_boot": boot_stats,
            "by_maturity_pred": pred_stats,
            "lag_horizon": lag_bins,
        }

        for row in boot_stats:
            csv_rows.append(
                {
                    "method": method,
                    "source": "boot_zero",
                    **row,
                }
            )

        print()
        print(f"=== {method} ===  n_days={n_days}  curve RMSE={curve_rmse:.2f} bp")
        print(
            f"{'y':>3}  {'bias':>7}  {'sd':>7}  {'SE':>7}  {'RMSE':>7}  "
            f"{'MAE':>7}  {'P90|e|':>7}"
        )
        for row in boot_stats:
            if row["year"] not in KEY_TENORS and row["year"] % 5 != 0:
                continue
            print(
                f"{row['year']:3d}  {row['bias_bp']:7.2f}  {row['sd_bp']:7.2f}  "
                f"{row['se_bp']:7.3f}  {row['rmse_bp']:7.2f}  {row['mae_bp']:7.2f}  "
                f"{row['p90_abs_bp']:7.2f}"
            )
        print(
            f"  mean SE across tenors = {mean_se:.3f} bp  |  "
            f"P90 |e| (pooled) = {report['methods'][method]['p90_abs_curve_bp']:.2f} bp"
        )
        print("  lag-horizon (mean |e| across curve that day):")
        for b in lag_bins:
            if not b["n"]:
                continue
            hi = b["lag_days_hi"]
            label = f"{b['lag_days_lo']:.0f}<Δd≤{hi:.0f}" if hi else f"Δd>{b['lag_days_lo']:.0f}"
            print(
                f"    {label:14s}  n={b['n']:3d}  "
                f"mean|e|={b['mean_abs_bp']:.2f} bp  rmse={b['rmse_bp']:.2f} bp"
            )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if csv_rows:
        with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            for row in csv_rows:
                w.writerow(row)

    print()
    print(f"wrote: {args.out_json}")
    print(f"wrote: {args.out_csv}")
    print(
        "SE = standard error of mean residual at each maturity (bp). "
        "Use ±1.96·SE for approx 95% CI on mean bias; use P90|e| as MoE band."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
