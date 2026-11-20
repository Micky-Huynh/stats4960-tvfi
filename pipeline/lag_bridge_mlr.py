#!/usr/bin/env python3
"""Valet → BoC lag bridge via multi-output Ridge and PCA+Ridge.

Statistical nowcast of dense BoC annual-effective zeros from sparse daily
Valet benchmarks (2/3/5/7/10/Long→30). Complements the keyed-shift bridge in
``pipeline.lag_bridge`` (fixed 1:1 Δ) with a *learned* mapping.

Methods
-------
ridge
    Multi-output Ridge: Valet yields (and optional Δ vs prior BoC date) → zeros 1..30.
pca
    PCA (default 3 components) on BoC zero panels; Ridge maps Valet → PC scores;
    reconstruct annual zeros = mean + scores @ components.

Usage (from the TVFI project root)::

    python3 -m pipeline.lag_bridge_mlr --train --backtest
    python3 -m pipeline.lag_bridge_mlr --method ridge --predict
    python3 -m pipeline.lag_bridge_mlr --method pca --n-components 3 --predict
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
CURVES_DIR = ROOT / "data" / "curves"
MODEL_DIR = ROOT / "data" / "models"
VALET_ANCHORS = (2.0, 3.0, 5.0, 7.0, 10.0, 30.0)
YEARS = tuple(range(1, 31))

METHOD_RIDGE = "valet_ridge_mlr_v1"
METHOD_PCA = "valet_pca_ridge_v1"


@dataclass
class FitReport:
    method: str
    n_train: int
    n_features: int
    alpha: float
    n_components: Optional[int]
    train_rmse_bp: float
    train_max_abs_bp: float
    feature_mode: str  # "levels" | "levels_delta"


@dataclass
class BacktestRow:
    asof: str
    method: str
    rmse_bp: float
    max_abs_bp: float
    mean_abs_bp: float


def _valet_vector(obs: Mapping[str, object], anchors: Sequence[float] = VALET_ANCHORS) -> np.ndarray:
    from pipeline.lag_bridge import _yields_decimal

    yld = _yields_decimal(obs)
    missing = [a for a in anchors if a not in yld]
    if missing:
        raise KeyError(f"Valet obs missing anchors {missing}")
    return np.array([yld[a] for a in anchors], dtype=float)


def _zeros_vector(annual: Mapping[int, float]) -> np.ndarray:
    return np.array([float(annual[y]) for y in YEARS], dtype=float)


def fetch_boc_panel(
    *,
    window_days: int = 400,
    as_of_calendar: Optional[date] = None,
) -> List[Tuple[str, Dict[int, float]]]:
    """Download a long BoC CSV window and return (date, annual_eff_1_30) rows."""
    from pipeline import boc_intake

    end = as_of_calendar or date.today()
    start = end - timedelta(days=window_days)
    url = boc_intake.boc_csv_url(d_from=start, d_to=end)
    _, text = boc_intake.fetch_boc_csv(window_days=window_days, as_of_calendar=end)
    rows_raw = boc_intake.parse_boc_csv_all_rows(text)
    out: List[Tuple[str, Dict[int, float]]] = []
    for obs_date, cont_grid in rows_raw:
        annual_cont = boc_intake.interpolate_annual_tenors(
            cont_grid, years=YEARS, also_half=False
        )
        annual_eff = {
            y: boc_intake.continuous_to_annual_effective(float(annual_cont[float(y)]))
            for y in YEARS
        }
        out.append((obs_date, annual_eff))
    # de-dupe by date (keep last)
    by_date = {d: z for d, z in out}
    return sorted(by_date.items(), key=lambda kv: kv[0])


def fetch_valet_panel(*, recent: int = 250, start_date: Optional[str] = None) -> dict:
    from pipeline import valet_intake

    if start_date:
        snap, path = valet_intake.fetch_and_store(
            recent=None, start_date=start_date, end_date=date.today().isoformat()
        )
    else:
        snap, path = valet_intake.fetch_and_store(recent=recent)
    print(f"valet panel: {snap['latest_asof']}  n={len(snap['observations'])}  ({path})")
    return snap


def align_panel(
    boc_rows: Sequence[Tuple[str, Dict[int, float]]],
    valet_snapshot: Mapping[str, object],
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray]:
    """Align BoC dates to Valet on/before each date.

    Returns X_levels (n×6), Y (n×30), dates, X_delta (n×6) where delta is vs
    prior aligned row's Valet (first row delta = 0).
    """
    from pipeline import valet_intake

    X_list: List[np.ndarray] = []
    Y_list: List[np.ndarray] = []
    dates: List[str] = []
    prev_v: Optional[np.ndarray] = None
    deltas: List[np.ndarray] = []

    for boc_date, annual in boc_rows:
        obs = valet_intake.find_observation_on_or_before(valet_snapshot, boc_date)
        if obs is None:
            continue
        try:
            xv = _valet_vector(obs)
        except KeyError:
            continue
        X_list.append(xv)
        Y_list.append(_zeros_vector(annual))
        dates.append(boc_date)
        if prev_v is None:
            deltas.append(np.zeros_like(xv))
        else:
            deltas.append(xv - prev_v)
        prev_v = xv

    if len(X_list) < 8:
        raise RuntimeError(
            f"need ≥8 aligned BoC↔Valet rows for training; got {len(X_list)}. "
            "Fetch a longer BoC window / more Valet history."
        )
    return (
        np.vstack(X_list),
        np.vstack(Y_list),
        dates,
        np.vstack(deltas),
    )


def _make_features(
    X_levels: np.ndarray,
    X_delta: np.ndarray,
    *,
    feature_mode: str,
) -> np.ndarray:
    if feature_mode == "levels":
        return X_levels
    if feature_mode == "levels_delta":
        return np.hstack([X_levels, X_delta])
    raise ValueError(f"unknown feature_mode {feature_mode!r}")


def fit_ridge(
    X: np.ndarray,
    Y: np.ndarray,
    *,
    alpha: float = 1.0,
) -> Tuple[object, FitReport]:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(X, Y)
    pred = model.predict(X)
    err_bp = (pred - Y) * 1e4
    report = FitReport(
        method=METHOD_RIDGE,
        n_train=int(X.shape[0]),
        n_features=int(X.shape[1]),
        alpha=alpha,
        n_components=None,
        train_rmse_bp=float(np.sqrt(np.mean(err_bp**2))),
        train_max_abs_bp=float(np.max(np.abs(err_bp))),
        feature_mode="",  # filled by caller
    )
    return model, report


def fit_pca_ridge(
    X: np.ndarray,
    Y: np.ndarray,
    *,
    n_components: int = 3,
    alpha: float = 1.0,
) -> Tuple[object, object, FitReport]:
    """PCA on Y (BoC curves); Ridge maps Valet features → PC scores."""
    from sklearn.decomposition import PCA
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pca = PCA(n_components=n_components)
    scores = pca.fit_transform(Y)  # n × k
    ridge = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    ridge.fit(X, scores)
    scores_hat = ridge.predict(X)
    Y_hat = pca.inverse_transform(scores_hat)
    err_bp = (Y_hat - Y) * 1e4
    report = FitReport(
        method=METHOD_PCA,
        n_train=int(X.shape[0]),
        n_features=int(X.shape[1]),
        alpha=alpha,
        n_components=n_components,
        train_rmse_bp=float(np.sqrt(np.mean(err_bp**2))),
        train_max_abs_bp=float(np.max(np.abs(err_bp))),
        feature_mode="",
    )
    return pca, ridge, report


def predict_ridge(model: object, x_row: np.ndarray) -> Dict[int, float]:
    y = np.asarray(model.predict(x_row.reshape(1, -1))[0], dtype=float)
    return {int(year): float(y[i]) for i, year in enumerate(YEARS)}


def predict_pca(pca: object, ridge: object, x_row: np.ndarray) -> Dict[int, float]:
    scores = ridge.predict(x_row.reshape(1, -1))
    y = np.asarray(pca.inverse_transform(scores)[0], dtype=float)
    return {int(year): float(y[i]) for i, year in enumerate(YEARS)}


def _metrics_bp(pred: Mapping[int, float], actual: Mapping[int, float]) -> Tuple[float, float, float]:
    diffs = np.array([(pred[y] - actual[y]) * 1e4 for y in YEARS])
    rmse = float(np.sqrt(np.mean(diffs**2)))
    max_abs = float(np.max(np.abs(diffs)))
    mean_abs = float(np.mean(np.abs(diffs)))
    return rmse, max_abs, mean_abs


def walk_forward_backtest(
    X: np.ndarray,
    Y: np.ndarray,
    dates: Sequence[str],
    *,
    method: str,
    feature_mode: str,
    X_delta: np.ndarray,
    alpha: float = 1.0,
    n_components: int = 3,
    min_train: int = 20,
) -> List[BacktestRow]:
    """Expanding-window: train on 0..t-1, predict date t."""
    rows: List[BacktestRow] = []
    for t in range(min_train, len(dates)):
        X_tr = _make_features(X[:t], X_delta[:t], feature_mode=feature_mode)
        Y_tr = Y[:t]
        X_te = _make_features(X[t : t + 1], X_delta[t : t + 1], feature_mode=feature_mode)
        if method == "ridge":
            model, _ = fit_ridge(X_tr, Y_tr, alpha=alpha)
            pred_v = model.predict(X_te)[0]
        elif method == "pca":
            pca, ridge, _ = fit_pca_ridge(
                X_tr, Y_tr, n_components=n_components, alpha=alpha
            )
            scores = ridge.predict(X_te)
            pred_v = pca.inverse_transform(scores)[0]
        else:
            raise ValueError(method)
        pred = {y: float(pred_v[i]) for i, y in enumerate(YEARS)}
        actual = {y: float(Y[t, i]) for i, y in enumerate(YEARS)}
        rmse, max_abs, mean_abs = _metrics_bp(pred, actual)
        rows.append(
            BacktestRow(
                asof=dates[t],
                method=f"{method}:{feature_mode}",
                rmse_bp=rmse,
                max_abs_bp=max_abs,
                mean_abs_bp=mean_abs,
            )
        )
    return rows


def compare_to_shift_bridge(
    boc_snapshot: Mapping[str, object],
    valet_snapshot: Mapping[str, object],
    predicted: Mapping[int, float],
) -> dict:
    """Compare ridge/PCA prediction vs keyed-shift and vs hold."""
    from pipeline import boc_intake, lag_bridge

    held = boc_intake.annual_effective_rf_from_snapshot(boc_snapshot)
    shifted, shift_meta = lag_bridge.bridge_boc_snapshot(
        boc_snapshot, valet_snapshot, enabled=True
    )
    # No actual "today BoC" — compare prediction vs shift/hold as diagnostic only
    pred_vs_hold = _metrics_bp(predicted, held)
    shift_vs_hold = _metrics_bp(shifted, held) if shift_meta.get("applied") else None
    pred_vs_shift = (
        _metrics_bp(predicted, shifted) if shift_meta.get("applied") else None
    )
    return {
        "shift_applied": bool(shift_meta.get("applied")),
        "shift_meta": {
            k: shift_meta.get(k)
            for k in (
                "valet_base_asof",
                "valet_live_asof",
                "max_abs_shift_bp",
                "mean_abs_shift_bp",
                "reason",
            )
        },
        "pred_vs_hold_bp": {
            "rmse": pred_vs_hold[0],
            "max_abs": pred_vs_hold[1],
            "mean_abs": pred_vs_hold[2],
        },
        "shift_vs_hold_bp": (
            {
                "rmse": shift_vs_hold[0],
                "max_abs": shift_vs_hold[1],
                "mean_abs": shift_vs_hold[2],
            }
            if shift_vs_hold
            else None
        ),
        "pred_vs_shift_bp": (
            {
                "rmse": pred_vs_shift[0],
                "max_abs": pred_vs_shift[1],
                "mean_abs": pred_vs_shift[2],
            }
            if pred_vs_shift
            else None
        ),
    }


def save_models(
    *,
    method: str,
    feature_mode: str,
    ridge_or_bundle: object,
    report: FitReport,
    pca: Optional[object] = None,
    out_dir: Path = MODEL_DIR,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lag_bridge_{method}_{feature_mode}.pkl"
    payload = {
        "method": method,
        "feature_mode": feature_mode,
        "report": asdict(report),
        "model": ridge_or_bundle,
        "pca": pca,
        "anchors": list(VALET_ANCHORS),
        "years": list(YEARS),
    }
    path.write_bytes(pickle.dumps(payload))
    meta = out_dir / f"lag_bridge_{method}_{feature_mode}_report.json"
    meta.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    return path


def load_models(path: Path) -> dict:
    return pickle.loads(path.read_bytes())


def _feature_row_for_live(
    valet_snapshot: Mapping[str, object],
    boc_rf_asof: str,
    *,
    feature_mode: str,
) -> np.ndarray:
    from pipeline import valet_intake

    live = valet_intake.latest_observation(valet_snapshot)
    if live is None:
        raise RuntimeError("no Valet live observation")
    x_live = _valet_vector(live)
    if feature_mode == "levels":
        return x_live
    base = valet_intake.find_observation_on_or_before(valet_snapshot, boc_rf_asof)
    if base is None:
        raise RuntimeError(f"no Valet base on/before {boc_rf_asof}")
    x_base = _valet_vector(base)
    return np.concatenate([x_live, x_live - x_base])


def predict_live(
    *,
    method: str,
    feature_mode: str,
    model_path: Optional[Path] = None,
    fetch_valet: bool = True,
    fetch_boc_panel_days: int = 0,
) -> Tuple[Dict[int, float], dict]:
    """Predict annual RF using saved model + live Valet; compare to shift bridge."""
    from pipeline import boc_intake, valet_intake

    if model_path is None:
        model_path = MODEL_DIR / f"lag_bridge_{method}_{feature_mode}.pkl"
    if not model_path.is_file():
        raise FileNotFoundError(
            f"missing model {model_path}; run with --train first"
        )
    bundle = load_models(model_path)

    if fetch_valet:
        try:
            valet, _ = valet_intake.fetch_and_store(recent=120)
        except Exception as exc:  # noqa: BLE001
            print(f"Valet fetch failed ({exc}); using cache", file=sys.stderr)
            valet = valet_intake.load_snapshot()
    else:
        valet = valet_intake.load_snapshot()

    boc_path = boc_intake.find_preferred_boc_snapshot()
    if boc_path is None:
        raise RuntimeError("no BoC snapshot")
    boc = boc_intake.load_snapshot(boc_path)
    rf_asof = str(boc["rf_asof"])

    x_row = _feature_row_for_live(valet, rf_asof, feature_mode=feature_mode)
    if method == "ridge":
        pred = predict_ridge(bundle["model"], x_row)
        method_id = METHOD_RIDGE
    elif method == "pca":
        pred = predict_pca(bundle["pca"], bundle["model"], x_row)
        method_id = METHOD_PCA
    else:
        raise ValueError(method)

    cmp_ = compare_to_shift_bridge(boc, valet, pred)
    meta = {
        "method": method_id,
        "feature_mode": feature_mode,
        "model_path": str(model_path),
        "boc_rf_asof": rf_asof,
        "valet_live_asof": valet.get("latest_asof"),
        "fit_report": bundle.get("report"),
        "comparison": cmp_,
        "predicted_sample_pct": {
            str(y): pred[y] * 100.0 for y in (1, 2, 5, 10, 20, 30)
        },
    }
    _ = fetch_boc_panel_days  # reserved for online retrain hooks
    return pred, meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--method",
        choices=("ridge", "pca", "both"),
        default="both",
        help="ridge MLR, PCA+Ridge, or both (default both)",
    )
    p.add_argument(
        "--feature-mode",
        choices=("levels", "levels_delta"),
        default="levels_delta",
        help="Valet levels only, or levels + Δ vs prior row / rf_asof",
    )
    p.add_argument("--alpha", type=float, default=1.0, help="Ridge L2 strength")
    p.add_argument("--n-components", type=int, default=3, help="PCA components")
    p.add_argument("--boc-window-days", type=int, default=400)
    p.add_argument("--valet-recent", type=int, default=250)
    p.add_argument(
        "--valet-start",
        default=None,
        help="Optional Valet start_date YYYY-MM-DD (uses date range instead of recent=)",
    )
    p.add_argument("--train", action="store_true", help="Fit and save model(s)")
    p.add_argument("--backtest", action="store_true", help="Walk-forward back-test")
    p.add_argument("--predict", action="store_true", help="Predict live RF with saved model")
    p.add_argument("--no-fetch", action="store_true", help="Skip live Valet/BoC downloads")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write prediction / backtest JSON",
    )
    args = p.parse_args(argv)

    if not (args.train or args.backtest or args.predict):
        args.train = True
        args.backtest = True
        args.predict = True

    methods = ["ridge", "pca"] if args.method == "both" else [args.method]

    boc_rows = None
    valet = None
    X = Y = X_delta = None
    dates: List[str] = []

    need_panel = args.train or args.backtest
    if need_panel:
        print("Fetching BoC panel…")
        if args.no_fetch:
            # Fall back to dated snapshots only (thin)
            from pipeline import boc_intake

            boc_rows = []
            for path in sorted((ROOT / "data" / "risk_free").glob("????-??-??.json")):
                snap = boc_intake.load_snapshot(path)
                if snap.get("is_fixture"):
                    continue
                boc_rows.append(
                    (snap["rf_asof"], boc_intake.annual_effective_rf_from_snapshot(snap))
                )
            if len(boc_rows) < 8:
                raise SystemExit(
                    "cached BoC snapshots too few for --no-fetch training; "
                    "omit --no-fetch to download a long CSV panel"
                )
        else:
            boc_rows = fetch_boc_panel(window_days=args.boc_window_days)
        print(f"BoC panel rows: {len(boc_rows)}  ({boc_rows[0][0]} → {boc_rows[-1][0]})")

        if args.no_fetch:
            from pipeline import valet_intake

            valet = valet_intake.load_snapshot()
        else:
            valet_start = args.valet_start
            if valet_start is None and not args.no_fetch:
                # Match BoC window so alignment has enough Valet history
                valet_start = (
                    date.today() - timedelta(days=args.boc_window_days)
                ).isoformat()
            valet = fetch_valet_panel(
                recent=args.valet_recent, start_date=valet_start
            )

        X, Y, dates, X_delta = align_panel(boc_rows, valet)
        print(f"aligned rows:   {len(dates)}  ({dates[0]} → {dates[-1]})")

    results: dict = {"feature_mode": args.feature_mode, "methods": {}}

    for method in methods:
        print(f"\n=== {method} / {args.feature_mode} ===")
        if need_panel:
            Xf = _make_features(X, X_delta, feature_mode=args.feature_mode)
            if method == "ridge":
                model, report = fit_ridge(Xf, Y, alpha=args.alpha)
                report.feature_mode = args.feature_mode
                pca = None
                bundle_model = model
            else:
                pca, ridge, report = fit_pca_ridge(
                    Xf, Y, n_components=args.n_components, alpha=args.alpha
                )
                report.feature_mode = args.feature_mode
                bundle_model = ridge

            print(
                f"train n={report.n_train}  feats={report.n_features}  "
                f"RMSE={report.train_rmse_bp:.2f} bp  "
                f"max|Δ|={report.train_max_abs_bp:.2f} bp"
            )
            if args.train:
                path = save_models(
                    method=method,
                    feature_mode=args.feature_mode,
                    ridge_or_bundle=bundle_model,
                    report=report,
                    pca=pca,
                )
                print(f"wrote model: {path}")

            bt_rows: List[BacktestRow] = []
            if args.backtest:
                bt_rows = walk_forward_backtest(
                    X,
                    Y,
                    dates,
                    method=method,
                    feature_mode=args.feature_mode,
                    X_delta=X_delta,
                    alpha=args.alpha,
                    n_components=args.n_components,
                )
                if bt_rows:
                    rmses = [r.rmse_bp for r in bt_rows]
                    print(
                        f"walk-forward n={len(bt_rows)}  "
                        f"mean RMSE={np.mean(rmses):.2f} bp  "
                        f"median={np.median(rmses):.2f} bp  "
                        f"max|Δ| peak={max(r.max_abs_bp for r in bt_rows):.2f} bp"
                    )
                    # Hold baseline: Y[t-1] as forecast of Y[t] (same walk-forward windows)
                    hold_for_bt = [
                        _metrics_bp(
                            {y: float(Y[t - 1, i]) for i, y in enumerate(YEARS)},
                            {y: float(Y[t, i]) for i, y in enumerate(YEARS)},
                        )[0]
                        for t in range(20, len(dates))
                    ]
                    if hold_for_bt:
                        print(
                            f"hold baseline    mean RMSE={np.mean(hold_for_bt):.2f} bp  "
                            f"(same windows)"
                        )

            results["methods"][method] = {
                "fit": asdict(report) if need_panel else None,
                "backtest": [asdict(r) for r in bt_rows] if bt_rows else [],
                "backtest_summary": (
                    {
                        "n": len(bt_rows),
                        "mean_rmse_bp": float(np.mean([r.rmse_bp for r in bt_rows])),
                        "median_rmse_bp": float(np.median([r.rmse_bp for r in bt_rows])),
                        "hold_mean_rmse_bp": (
                            float(np.mean(hold_for_bt)) if bt_rows else None
                        ),
                    }
                    if bt_rows
                    else None
                ),
            }

        if args.predict:
            try:
                pred, meta = predict_live(
                    method=method,
                    feature_mode=args.feature_mode,
                    fetch_valet=not args.no_fetch,
                )
            except FileNotFoundError as exc:
                print(f"predict skipped: {exc}")
                continue
            print(
                f"predict live: valet={meta.get('valet_live_asof')}  "
                f"boc_asof={meta.get('boc_rf_asof')}"
            )
            print(f"  sample %: {meta.get('predicted_sample_pct')}")
            cmp_ = meta.get("comparison") or {}
            print(f"  vs hold:  {cmp_.get('pred_vs_hold_bp')}")
            print(f"  vs shift: {cmp_.get('pred_vs_shift_bp')}")
            print(f"  shift:    {cmp_.get('shift_meta')}")
            results["methods"].setdefault(method, {})["live_predict"] = {
                "meta": meta,
                "annual_zeros_1_30": [pred[y] for y in YEARS],
            }

    out = args.out or (
        CURVES_DIR / f"lag_bridge_mlr_{args.feature_mode}_results.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    # Drop huge backtest detail if enormous — keep summary + last 5
    for m in results["methods"].values():
        bt = m.get("backtest") or []
        if len(bt) > 10:
            m["backtest_tail"] = bt[-5:]
            m["backtest"] = bt[:3]
            m["backtest_note"] = f"truncated; full n={m['backtest_summary']['n']}"
    out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nwrote: {out}")
    print(
        "NOTE: Ridge/PCA nowcast the RF grid from Valet; "
        "keyed shift remains the simple baseline. Hold Fiera H unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
