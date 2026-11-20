#!/usr/bin/env python3
"""Honest backtest: Valet → predict zeros → IoA bootstrap → vs later BoC.

Walk-forward on aligned BoC↔Valet dates:

1. Train Ridge / PCA+Ridge on history before date t (no peeking).
2. Predict annual-effective zeros at t from Valet.
3. IoA/CM1 bootstrap the prediction (zeros → par → DF / zero / 1y forward).
4. Score bootstrapped zeros vs actual BoC zeros at t.
5. Score bootstrapped 1y forwards vs forwards from bootstrapping actual BoC.
6. Baselines: hold prior BoC; bootstrap round-trip of truth (should be ~0).

Also scores the PCA-curve track (Valet interpolate → PCA project; PCA fit on
past BoC only).

Freshness note: Valet is **business-daily**, not clock-hourly. This backtest
measures whether the predict→bootstrap strip tracks eventual BoC well enough
to use as a lag RF during the publish gap (~2 weeks). Pass bar is relative to
the 25 bp trigger diagnostic (errors ≪ 25 bp ⇒ usable; else report fail).

Usage (from TVFI project root)::

    python3 -m pipeline.lag_bootstrap_backtest
    python3 -m pipeline.lag_bootstrap_backtest --min-train 40 --window-days 400
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
CURVES_DIR = ROOT / "data" / "curves"
OUT_PATH = CURVES_DIR / "lag_bootstrap_backtest_results.json"

YEARS = tuple(range(1, 31))
TRIGGER_BP = 25.0  # insurer diagnostic; not a hard pass/fail statute


@dataclass
class DayScore:
    asof: str
    method: str
    pred_zero_rmse_bp: float
    boot_zero_rmse_bp: float
    boot_fwd_rmse_bp: float
    hold_zero_rmse_bp: float
    roundtrip_zero_rmse_bp: float
    max_abs_boot_zero_bp: float
    beats_hold: bool


def _metrics_bp(pred: Mapping[int, float], actual: Mapping[int, float]) -> Tuple[float, float, float]:
    diffs = np.array([(float(pred[y]) - float(actual[y])) * 1e4 for y in YEARS])
    rmse = float(np.sqrt(np.mean(diffs**2)))
    max_abs = float(np.max(np.abs(diffs)))
    mean_abs = float(np.mean(np.abs(diffs)))
    return rmse, max_abs, mean_abs


def _fwd_from_curve(curve: object) -> Dict[int, float]:
    return {int(y): float(f) for y, f in zip(curve.years, curve.forwards_1y)}


def _zeros_from_curve(curve: object) -> Dict[int, float]:
    return {int(y): float(z) for y, z in zip(curve.years, curve.zeros_annual_effective)}


def _dict_from_row(Y_row: np.ndarray) -> Dict[int, float]:
    return {int(y): float(Y_row[i]) for i, y in enumerate(YEARS)}


def _summarize(rows: Sequence[DayScore]) -> dict:
    if not rows:
        return {"n": 0}
    boot_z = [r.boot_zero_rmse_bp for r in rows]
    boot_f = [r.boot_fwd_rmse_bp for r in rows]
    hold = [r.hold_zero_rmse_bp for r in rows]
    pred_z = [r.pred_zero_rmse_bp for r in rows]
    rt = [r.roundtrip_zero_rmse_bp for r in rows]
    maxes = [r.max_abs_boot_zero_bp for r in rows]
    n_beat = sum(1 for r in rows if r.beats_hold)
    mean_boot = float(np.mean(boot_z))
    mean_hold = float(np.mean(hold))
    # Pass if mean boot RMSE well below trigger and beats hold on average
    usable_vs_trigger = mean_boot < TRIGGER_BP * 0.2  # <5 bp mean
    beats_hold_avg = mean_boot < mean_hold
    verdict = (
        "PASS — predict→bootstrap tracks BoC; usable lag RF strip"
        if usable_vs_trigger and beats_hold_avg
        else (
            "MIXED — below trigger but does not beat hold"
            if usable_vs_trigger and not beats_hold_avg
            else (
                "FAIL — beats hold but error not small vs 25 bp trigger"
                if beats_hold_avg and not usable_vs_trigger
                else "FAIL — predict→bootstrap does not track BoC usefully"
            )
        )
    )
    return {
        "n": len(rows),
        "mean_pred_zero_rmse_bp": float(np.mean(pred_z)),
        "median_pred_zero_rmse_bp": float(np.median(pred_z)),
        "mean_boot_zero_rmse_bp": mean_boot,
        "median_boot_zero_rmse_bp": float(np.median(boot_z)),
        "mean_boot_fwd_rmse_bp": float(np.mean(boot_f)),
        "median_boot_fwd_rmse_bp": float(np.median(boot_f)),
        "mean_hold_zero_rmse_bp": mean_hold,
        "median_hold_zero_rmse_bp": float(np.median(hold)),
        "mean_roundtrip_zero_rmse_bp": float(np.mean(rt)),
        "peak_max_abs_boot_zero_bp": float(np.max(maxes)),
        "pct_days_beats_hold": float(100.0 * n_beat / len(rows)),
        "trigger_bp": TRIGGER_BP,
        "usable_vs_trigger": usable_vs_trigger,
        "beats_hold_on_mean": beats_hold_avg,
        "verdict": verdict,
    }


def walk_forward_bootstrap_backtest(
    X: np.ndarray,
    Y: np.ndarray,
    dates: Sequence[str],
    X_delta: np.ndarray,
    *,
    feature_mode: str = "levels_delta",
    alpha: float = 1.0,
    n_components: int = 3,
    min_train: int = 20,
    methods: Sequence[str] = ("ridge", "pca_ridge", "pca"),
) -> Dict[str, List[DayScore]]:
    """Expanding-window predict → bootstrap → score vs BoC truth + hold."""
    from pipeline.lag_bridge import _lerp
    from pipeline.lag_bridge_bootstrap import bootstrap_predicted_zeros, pca_project_curve
    from pipeline.lag_bridge_mlr import _make_features, fit_pca_ridge, fit_ridge
    from sklearn.decomposition import PCA

    out: Dict[str, List[DayScore]] = {m: [] for m in methods}
    anchors = (2.0, 3.0, 5.0, 7.0, 10.0, 30.0)

    for t in range(min_train, len(dates)):
        X_tr = _make_features(X[:t], X_delta[:t], feature_mode=feature_mode)
        Y_tr = Y[:t]
        X_te = _make_features(X[t : t + 1], X_delta[t : t + 1], feature_mode=feature_mode)
        actual = _dict_from_row(Y[t])
        hold = _dict_from_row(Y[t - 1])
        hold_rmse, _, _ = _metrics_bp(hold, actual)

        # Truth bootstrap (for forward comparison + round-trip sanity)
        truth_curve, _ = bootstrap_predicted_zeros(actual)
        truth_boot_z = _zeros_from_curve(truth_curve)
        truth_fwd = _fwd_from_curve(truth_curve)
        rt_rmse, _, _ = _metrics_bp(truth_boot_z, actual)

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
            # PCA eigenspace on past BoC; Valet levels → dense → project
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
            pred_rmse, _, _ = _metrics_bp(pred_z, actual)
            boot_curve, _ = bootstrap_predicted_zeros(pred_z)
            boot_z = _zeros_from_curve(boot_curve)
            boot_f = _fwd_from_curve(boot_curve)
            boot_z_rmse, boot_z_max, _ = _metrics_bp(boot_z, actual)
            boot_f_rmse, _, _ = _metrics_bp(boot_f, truth_fwd)
            out[method].append(
                DayScore(
                    asof=dates[t],
                    method=method,
                    pred_zero_rmse_bp=pred_rmse,
                    boot_zero_rmse_bp=boot_z_rmse,
                    boot_fwd_rmse_bp=boot_f_rmse,
                    hold_zero_rmse_bp=hold_rmse,
                    roundtrip_zero_rmse_bp=rt_rmse,
                    max_abs_boot_zero_bp=boot_z_max,
                    beats_hold=boot_z_rmse < hold_rmse,
                )
            )

    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window-days", type=int, default=400)
    p.add_argument("--min-train", type=int, default=20)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--n-components", type=int, default=3)
    p.add_argument("--feature-mode", default="levels_delta", choices=("levels", "levels_delta"))
    p.add_argument(
        "--methods",
        default="ridge,pca_ridge,pca",
        help="Comma list: ridge,pca_ridge,pca",
    )
    p.add_argument("--out", type=Path, default=OUT_PATH)
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
        f"walk-forward predict→bootstrap  methods={methods}  "
        f"min_train={args.min_train}  feature_mode={args.feature_mode}"
    )
    print(
        "NOTE: Valet freshness is business-daily (not clock-hourly). "
        "Score = bootstrapped predicted strip vs later-published BoC."
    )

    by_method = walk_forward_bootstrap_backtest(
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

    summary = {m: _summarize(rows) for m, rows in by_method.items()}
    # Overall: best mean boot zero RMSE among methods
    ranked = sorted(
        ((m, s) for m, s in summary.items() if s.get("n")),
        key=lambda kv: kv[1]["mean_boot_zero_rmse_bp"],
    )
    best_method = ranked[0][0] if ranked else None
    best_summary = ranked[0][1] if ranked else {}
    overall_verdict = best_summary.get("verdict", "FAIL — no rows")

    print()
    for m, s in summary.items():
        if not s.get("n"):
            print(f"=== {m} ===  (no rows)")
            continue
        print(f"=== {m} ===")
        print(
            f"  n={s['n']}  boot-zero mean RMSE={s['mean_boot_zero_rmse_bp']:.2f} bp  "
            f"median={s['median_boot_zero_rmse_bp']:.2f} bp  "
            f"peak max|Δ|={s['peak_max_abs_boot_zero_bp']:.2f} bp"
        )
        print(
            f"  pred-zero mean RMSE={s['mean_pred_zero_rmse_bp']:.2f} bp  "
            f"(bootstrap round-trip of truth={s['mean_roundtrip_zero_rmse_bp']:.4f} bp)"
        )
        print(
            f"  boot-fwd mean RMSE={s['mean_boot_fwd_rmse_bp']:.2f} bp  |  "
            f"hold baseline mean RMSE={s['mean_hold_zero_rmse_bp']:.2f} bp  |  "
            f"beats hold on {s['pct_days_beats_hold']:.0f}% of days"
        )
        print(f"  verdict: {s['verdict']}")
        print()

    print(f"BEST METHOD: {best_method}")
    print(f"OVERALL: {overall_verdict}")
    print(
        f"Freshness claim: Valet-timed (business-daily) — not true hourly. "
        f"Trigger diagnostic={TRIGGER_BP:.0f} bp."
    )

    payload = {
        "experimental": True,
        "freshness": "valet_business_daily_not_clock_hourly",
        "trigger_bp": TRIGGER_BP,
        "feature_mode": args.feature_mode,
        "min_train": args.min_train,
        "window_days": args.window_days,
        "n_aligned": len(dates),
        "date_from": dates[0],
        "date_to": dates[-1],
        "best_method": best_method,
        "overall_verdict": overall_verdict,
        "summary": summary,
        "tail": {
            m: [asdict(r) for r in rows[-5:]] for m, rows in by_method.items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
