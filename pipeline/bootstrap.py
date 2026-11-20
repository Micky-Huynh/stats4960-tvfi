#!/usr/bin/env python3
"""Experimental annual par → zero / forward bootstrap (IoA / CM1 textbook style).

EXPERIMENTAL ONLY — does **not** replace the locked primary RF path
(BoC zeros + hold last published for the ~2-week lag).

Method (Institute of Actuaries CM1 / ACT “bootstrapping” from annual par yields):
  A unit-notional annual-pay bond priced at par with coupon = par yield c_n satisfies

      1 = c_n · Σ_{k=1..n−1} DF_k  +  (1 + c_n) · DF_n

  so

      DF_n = (1 − c_n · Σ_{k=1..n−1} DF_k) / (1 + c_n)
      z_n  = DF_n^(−1/n) − 1          (annual effective spot)
      f_n  = DF_{n−1}/DF_n − 1        (one-year forward; f_1 = z_1)

This is the same recursion as the QuantAndFinancial gilt notebook template
(https://github.com/omartinsky/QuantAndFinancial/blob/master/yield_curve_bootstrapping/bootstrapping.ipynb),
simplified to the basic annual-par case taught in CM1 (no gilt accrued-interest /
semi-annual coupon calendar).

Usage (from the TVFI project root):

    python3 -m pipeline.bootstrap
    python3 -m pipeline.bootstrap --self-test
    python3 -m pipeline.bootstrap --series canada_par --compare
    python3 -m pipeline.bootstrap --as-of 2026-10-30 --out data/curves/experimental_bootstrap_canada_par.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
LATEST = ROOT / "data" / "fiera" / "extracted" / "latest"
HISTORY = ROOT / "data" / "fiera" / "extracted" / "history"
CURVES_DIR = ROOT / "data" / "curves"

METHOD_ID = "ioa_cm1_annual_par_bootstrap"
METHOD_NOTE = (
    "Experimental IoA/CM1 annual-par bootstrap (par → DF → annual-effective zero → "
    "1y forward). Does not fill BoC publication lag; primary RF remains BoC zeros + hold."
)

# ACT / treasurers-wiki textbook check (periodic rates treated as annual here).
_TEXTBOOK_PAR = {1: 0.02, 2: 0.029803}
_TEXTBOOK_Z2 = 0.029951


@dataclass(frozen=True)
class BootstrapCurve:
    """Bootstrapped term structure on integer years 1..N."""

    years: Tuple[int, ...]
    par: Tuple[float, ...]
    discount_factors: Tuple[float, ...]
    zeros_annual_effective: Tuple[float, ...]
    forwards_1y: Tuple[float, ...]

    def as_rows(self) -> List[Dict[str, float]]:
        rows: List[Dict[str, float]] = []
        for i, y in enumerate(self.years):
            rows.append(
                {
                    "year": float(y),
                    "par": self.par[i],
                    "discount_factor": self.discount_factors[i],
                    "zero_annual_effective": self.zeros_annual_effective[i],
                    "forward_1y": self.forwards_1y[i],
                }
            )
        return rows


def bootstrap_annual_par(
    par_by_year: Mapping[int, float],
    *,
    years: Optional[Sequence[int]] = None,
) -> BootstrapCurve:
    """Bootstrap annual-effective zeros / 1y forwards from annual par yields.

    ``par_by_year`` maps integer maturity (years) → decimal par yield.
    Years must be contiguous from 1 upward (missing intermediate years raise).
    """
    if years is None:
        years = sorted(int(y) for y in par_by_year.keys() if int(y) >= 1)
    else:
        years = [int(y) for y in years]

    if not years:
        raise ValueError("no par years to bootstrap")
    if years[0] != 1:
        raise ValueError(f"bootstrap requires year 1; got first year {years[0]}")
    for i, y in enumerate(years):
        if y != i + 1:
            raise ValueError(
                f"par years must be contiguous 1..N; gap before year {y} "
                f"(have {years[: i + 1]})"
            )
        if y not in par_by_year:
            raise ValueError(f"missing par yield for year {y}")

    dfs: List[float] = []
    zeros: List[float] = []
    fwds: List[float] = []
    pars: List[float] = []

    for n in years:
        c = float(par_by_year[n])
        if c <= -1.0:
            raise ValueError(f"par yield at year {n} is <= -100%: {c}")
        pars.append(c)
        sum_prior = sum(dfs)  # DF_1 + … + DF_{n-1}
        # DF_n = (1 − c · Σ DF_k) / (1 + c)
        numer = 1.0 - c * sum_prior
        denom = 1.0 + c
        if denom == 0.0:
            raise ValueError(f"invalid par yield at year {n}: {c}")
        df_n = numer / denom
        if df_n <= 0.0:
            raise ValueError(
                f"non-positive discount factor at year {n} "
                f"(DF={df_n}; check par inputs / continuity)"
            )
        # Equivalent closed form used in the QuantAndFinancial notebook:
        #   z_n = ((1+c) / (1 − c·ΣDF))^(1/n) − 1
        z_n = df_n ** (-1.0 / n) - 1.0
        if n == 1:
            f_n = z_n
        else:
            f_n = dfs[-1] / df_n - 1.0
        dfs.append(df_n)
        zeros.append(z_n)
        fwds.append(f_n)

    return BootstrapCurve(
        years=tuple(years),
        par=tuple(pars),
        discount_factors=tuple(dfs),
        zeros_annual_effective=tuple(zeros),
        forwards_1y=tuple(fwds),
    )


def par_from_zeros(zeros_by_year: Mapping[int, float]) -> Dict[int, float]:
    """Invert: annual-effective zeros → annual par yields (CM1 identity)."""
    years = sorted(int(y) for y in zeros_by_year.keys() if int(y) >= 1)
    dfs = []
    out: Dict[int, float] = {}
    for n in years:
        z = float(zeros_by_year[n])
        df = (1.0 + z) ** (-n)
        dfs.append(df)
        out[n] = (1.0 - df) / sum(dfs)
    return out


def load_latest_market_par(
    *,
    series: str = "canada_par",
    path: Optional[Path] = None,
    max_year: int = 30,
) -> Tuple[str, Dict[int, float]]:
    """Load integer-year par curve from latest ``market_curves.csv``.

    Returns (source_label, {year: par}).
    """
    csv_path = path or (LATEST / "market_curves.csv")
    if series not in {
        "canada_par",
        "province_par",
        "corporate_a_par",
        "corporate_bbb_par",
    }:
        raise ValueError(f"unknown series {series!r}")

    out: Dict[int, float] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            term_raw = (row.get("term_years") or "").strip()
            if not term_raw:
                continue
            try:
                term = float(term_raw)
            except ValueError:
                # Trailing mid-year / commentary rows in Fiera extract.
                break
            if abs(term - round(term)) > 1e-9:
                continue
            y = int(round(term))
            if y < 1 or y > max_year:
                continue
            rate_raw = (row.get(series) or "").strip()
            if not rate_raw:
                continue
            out[y] = float(rate_raw)

    if 1 not in out:
        raise RuntimeError(f"no year-1 {series} in {csv_path}")
    return f"fiera_latest:{csv_path.name}:{series}", out


def load_history_canada_par(as_of: str, *, max_year: int = 30) -> Dict[int, float]:
    """Load Canada par for one Fiera publication from history CSV."""
    path = HISTORY / "canada_par_by_month.csv"
    out: Dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("as_of") != as_of:
                continue
            term = (row.get("term_years") or "").strip()
            rate = (row.get("canada_par") or "").strip()
            if not term or not rate:
                continue
            try:
                t = float(term)
                c = float(rate)
            except ValueError:
                # Fiera extract sometimes appends commentary / mid-year header rows.
                continue
            if abs(t - round(t)) > 1e-9:
                continue
            y = int(round(t))
            if 1 <= y <= max_year:
                out[y] = c
    if 1 not in out:
        raise RuntimeError(f"no Canada par for as_of={as_of} in {path}")
    return out


def load_fiera_liquid_zeros(*, max_year: int = 30) -> Dict[int, float]:
    """Latest Fiera liquid reference annual-effective spots (comparison only)."""
    path = LATEST / "liquid_reference_spot.csv"
    out: Dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = float(row["term_years"])
            if abs(t - round(t)) > 1e-9:
                continue
            y = int(round(t))
            if 1 <= y <= max_year:
                out[y] = float(row["annual_effective_spot_rate"])
    return out


def load_fiera_construction_rf(*, max_year: int = 30) -> Dict[int, float]:
    """Latest Fiera illiquid construction col-E risk-free (comparison only)."""
    path = LATEST / "illiquid_construction.csv"
    out: Dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            y = int(float(row["year"]))
            if 1 <= y <= max_year:
                out[y] = float(row["risk_free_curve"])
    return out


def compare_zeros(
    boot: BootstrapCurve,
    reference: Mapping[int, float],
    *,
    label: str,
) -> List[Dict[str, object]]:
    """bp diffs: bootstrapped zero − reference zero."""
    rows: List[Dict[str, object]] = []
    for i, y in enumerate(boot.years):
        ref = reference.get(y)
        if ref is None:
            continue
        z = boot.zeros_annual_effective[i]
        rows.append(
            {
                "year": y,
                "bootstrap_zero": z,
                "reference_zero": ref,
                "reference": label,
                "diff_bp": (z - ref) * 1e4,
            }
        )
    return rows


def self_test() -> None:
    """ACT wiki 2-period example + round-trip par ↔ zero."""
    curve = bootstrap_annual_par(_TEXTBOOK_PAR)
    z2 = curve.zeros_annual_effective[1]
    if abs(z2 - _TEXTBOOK_Z2) > 5e-7:
        raise AssertionError(
            f"textbook z2 expected ≈ {_TEXTBOOK_Z2}, got {z2}"
        )
    # Round-trip: zeros → par should recover inputs.
    recovered = par_from_zeros(
        {y: curve.zeros_annual_effective[i] for i, y in enumerate(curve.years)}
    )
    for y, c in _TEXTBOOK_PAR.items():
        if abs(recovered[y] - c) > 1e-12:
            raise AssertionError(
                f"round-trip par year {y}: expected {c}, got {recovered[y]}"
            )
    # Notebook-equivalent closed form on year 2.
    df1 = curve.discount_factors[0]
    c2 = _TEXTBOOK_PAR[2]
    z2_nb = ((1.0 + c2) / (1.0 - c2 * df1)) ** 0.5 - 1.0
    if abs(z2_nb - z2) > 1e-15:
        raise AssertionError("notebook closed form drifted from DF form")
    print("self-test OK")
    print(f"  textbook z1={curve.zeros_annual_effective[0]:.6f} z2={z2:.6f}")
    print(f"  round-trip max |Δpar| < 1e-12")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Experimental IoA/CM1 annual par bootstrap "
            "(does not change primary BoC RF path)."
        )
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Run textbook identity checks and exit",
    )
    p.add_argument(
        "--series",
        default="canada_par",
        choices=(
            "canada_par",
            "province_par",
            "corporate_a_par",
            "corporate_bbb_par",
        ),
        help="Par column from latest market_curves.csv (ignored with --as-of)",
    )
    p.add_argument(
        "--as-of",
        default=None,
        help="Fiera publication date for Canada par history (YYYY-MM-DD)",
    )
    p.add_argument(
        "--max-year",
        type=int,
        default=30,
        help="Bootstrap through this integer year (default 30)",
    )
    p.add_argument(
        "--compare",
        action="store_true",
        help="Print bp diffs vs Fiera liquid spots and construction RF",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON curve under this path",
    )
    p.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Write CSV rows under this path",
    )
    args = p.parse_args(argv)

    if args.self_test:
        self_test()
        return 0

    if args.as_of:
        source = f"fiera_history:canada_par:{args.as_of}"
        par = load_history_canada_par(args.as_of, max_year=args.max_year)
    else:
        source, par = load_latest_market_par(
            series=args.series, max_year=args.max_year
        )

    # Contiguous 1..max available
    years = list(range(1, args.max_year + 1))
    missing = [y for y in years if y not in par]
    if missing:
        raise SystemExit(
            f"par curve missing years {missing[:5]}{'…' if len(missing) > 5 else ''}"
        )

    curve = bootstrap_annual_par(par, years=years)
    payload = {
        "experimental": True,
        "method": METHOD_ID,
        "method_note": METHOD_NOTE,
        "template": (
            "https://github.com/omartinsky/QuantAndFinancial/blob/master/"
            "yield_curve_bootstrapping/bootstrapping.ipynb"
        ),
        "source": source,
        "max_year": args.max_year,
        "curve": curve.as_rows(),
    }

    print(f"method:  {METHOD_ID}")
    print(f"source:  {source}")
    print(f"years:   1..{args.max_year}")
    print(
        f"spot %:  y1={curve.zeros_annual_effective[0]*100:.4f}  "
        f"y10={curve.zeros_annual_effective[9]*100:.4f}  "
        f"y30={curve.zeros_annual_effective[29]*100:.4f}"
    )
    print(
        f"fwd %:   f1={curve.forwards_1y[0]*100:.4f}  "
        f"f10={curve.forwards_1y[9]*100:.4f}  "
        f"f30={curve.forwards_1y[29]*100:.4f}"
    )

    if args.compare:
        liquid = load_fiera_liquid_zeros(max_year=args.max_year)
        constr = load_fiera_construction_rf(max_year=args.max_year)
        for label, ref in (
            ("fiera_liquid_reference_spot", liquid),
            ("fiera_illiquid_construction_rf_col_E", constr),
        ):
            diffs = compare_zeros(curve, ref, label=label)
            if not diffs:
                print(f"compare {label}: no overlapping years")
                continue
            abs_bp = [abs(float(d["diff_bp"])) for d in diffs]
            print(
                f"compare {label}: "
                f"max|Δ|={max(abs_bp):.2f} bp  "
                f"mean|Δ|={sum(abs_bp)/len(abs_bp):.2f} bp  "
                f"(n={len(diffs)})"
            )
            # Show a few display maturities
            show = {1, 2, 5, 10, 20, 30}
            for d in diffs:
                if int(d["year"]) in show:
                    print(
                        f"  y{int(d['year']):>2}  "
                        f"boot={float(d['bootstrap_zero'])*100:7.4f}%  "
                        f"ref={float(d['reference_zero'])*100:7.4f}%  "
                        f"Δ={float(d['diff_bp']):+7.2f} bp"
                    )
            payload.setdefault("comparisons", {})[label] = diffs

    out_json = args.out
    out_csv = args.csv_out
    if out_json is None and out_csv is None:
        # Default experimental artifact location
        stem = "experimental_bootstrap"
        if args.as_of:
            stem += f"_canada_par_{args.as_of}"
        else:
            stem += f"_{args.series}"
        out_json = CURVES_DIR / f"{stem}.json"
        out_csv = CURVES_DIR / f"{stem}.csv"

    if out_json is not None:
        _write_json(out_json, payload)
        print(f"wrote json: {out_json}")
    if out_csv is not None:
        _write_csv(out_csv, curve.as_rows())
        print(f"wrote csv:  {out_csv}")

    print("NOTE: experimental only — primary RF path unchanged (BoC zeros + hold).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
