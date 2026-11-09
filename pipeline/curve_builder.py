#!/usr/bin/env python3
"""Fiera Illiquid column-J curve builder (local pipeline; not Slope checkpoint code).

Reproduces annual forward rates (column J) from:
  - static top-left insurer parameters
  - held liquidity premium (column H) under ``hold_latest_publication``
  - a risk-free annual curve from Fiera fixture (col E) or BoC zero-coupon CSV

Writes a Slope-ready workbook: Sheet1 with Policy Duration 1–100 and Forward Rate.

Usage (from the TVFI project root):

    python3 -m pipeline.curve_builder
    python3 -m pipeline.curve_builder --validate
    python3 -m pipeline.curve_builder --rf boc
    python3 pipeline/curve_builder.py --as-of 2026-10-30
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Allow `python3 pipeline/curve_builder.py` from project root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROOT = _ROOT
LATEST = ROOT / "data" / "fiera" / "extracted" / "latest"
HISTORY = ROOT / "data" / "fiera" / "extracted" / "history"
CURVES_DIR = ROOT / "data" / "curves"

PREMIUM_POLICY = "hold_latest_publication"
N_DURATIONS = 100


@dataclass(frozen=True)
class StaticParams:
    observable_years: int
    ultimate_risk_free: float
    ultimate_timing_years: int
    liquidity_premium_constant: float
    ultimate_liquidity_premium: float
    interpolation: str
    raw: Mapping[str, object]

    @classmethod
    def from_json(cls, path: Path) -> "StaticParams":
        payload = json.loads(path.read_text(encoding="utf-8"))
        p = payload["parameters"]
        return cls(
            observable_years=int(p["Length of Observable Period (years)"]),
            ultimate_risk_free=float(p["Ultimate Risk-Free Rate"]),
            ultimate_timing_years=int(p["Ultimate Rate Timing (years)"]),
            liquidity_premium_constant=float(p["Liquidity Premium Constant"]),
            ultimate_liquidity_premium=float(p["Ultimate Liquidity Premium"]),
            interpolation=str(p.get("Interpolation Methodology", "Linear")),
            raw=payload,
        )


def load_static_params(path: Optional[Path] = None) -> StaticParams:
    return StaticParams.from_json(path or (LATEST / "static_parameters.json"))


def _f(x: Optional[str]) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def load_held_liquidity_premium(
    *,
    as_of: Optional[str] = None,
    latest_dir: Path = LATEST,
    history_path: Path = HISTORY / "liquidity_premium_by_month.csv",
) -> Tuple[str, Dict[int, float]]:
    """Return (publication_as_of, {year: column H}) for years in the observable window.

    Policy: ``hold_latest_publication`` — use the newest Fiera extract (or a named
    ``as_of`` from history) and keep that H term structure until the next workbook.
    """
    if as_of is None:
        meta = json.loads((latest_dir / "static_parameters.json").read_text(encoding="utf-8"))
        pub = str(meta["as_of"])
        path = latest_dir / "illiquid_construction.csv"
        h: Dict[int, float] = {}
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                year = _f(row.get("year"))
                prem = _f(row.get("liquidity_premium"))
                if year is None or prem is None:
                    continue
                y = int(year)
                if y <= 30:  # observable window; extrap rebuilds beyond
                    h[y] = prem
        if not h:
            raise RuntimeError(f"No liquidity premium rows in {path}")
        return pub, h

    by_year: Dict[int, float] = {}
    with history_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("as_of") != as_of:
                continue
            year = _f(row.get("year"))
            prem = _f(row.get("liquidity_premium"))
            if year is None or prem is None:
                continue
            y = int(year)
            if y <= 30:
                by_year[y] = prem
    if not by_year:
        raise RuntimeError(f"No liquidity premium for as_of={as_of} in {history_path}")
    return as_of, by_year


def load_fixture_risk_free(
    *,
    as_of: Optional[str] = None,
    latest_dir: Path = LATEST,
    history_path: Path = HISTORY / "liquidity_premium_by_month.csv",
) -> Tuple[str, Dict[int, float]]:
    """Load Fiera construction risk-free spots (col E) for validation / fixture RF.

    Prefer years 1–observable from the construction sheet; beyond that the builder
    extrapolates with static params (matching Fiera).
    """
    if as_of is None:
        meta = json.loads((latest_dir / "static_parameters.json").read_text(encoding="utf-8"))
        pub = str(meta["as_of"])
        path = latest_dir / "illiquid_construction.csv"
        rf: Dict[int, float] = {}
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                year = _f(row.get("year"))
                rate = _f(row.get("risk_free_curve"))
                if year is None or rate is None:
                    continue
                y = int(year)
                if y <= 30:
                    rf[y] = rate
        if len(rf) < 30:
            raise RuntimeError(f"Expected RF years 1–30 in {path}, got {len(rf)}")
        return pub, rf

    by_year: Dict[int, float] = {}
    with history_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("as_of") != as_of:
                continue
            year = _f(row.get("year"))
            rate = _f(row.get("risk_free_curve"))
            if year is None or rate is None:
                continue
            y = int(year)
            if y <= 30:
                by_year[y] = rate
    if len(by_year) < 30:
        raise RuntimeError(f"Expected RF years 1–30 for as_of={as_of}, got {len(by_year)}")
    return as_of, by_year


def _require_years(curve: Mapping[int, float], years: Sequence[int], label: str) -> None:
    missing = [y for y in years if y not in curve]
    if missing:
        raise ValueError(f"{label} missing years {missing[:5]}{'…' if len(missing) > 5 else ''}")


def extrapolate_to_ultimate(
    rate_at_observable: float,
    ultimate: float,
    *,
    year: int,
    observable_years: int,
    ultimate_timing_years: int,
) -> float:
    """Linear interpolation from observable end to ultimate timing; flat after."""
    if year <= observable_years:
        raise ValueError("extrapolate_to_ultimate is for years beyond the observable window")
    if year >= ultimate_timing_years:
        return ultimate
    weight = (year - observable_years) / (ultimate_timing_years - observable_years)
    return rate_at_observable + (ultimate - rate_at_observable) * weight


def build_spot_curves(
    risk_free_1_to_obs: Mapping[int, float],
    liquidity_premium_1_to_obs: Mapping[int, float],
    params: StaticParams,
    *,
    n_durations: int = N_DURATIONS,
) -> Tuple[Dict[int, float], Dict[int, float], Dict[int, float]]:
    """Return (rf, lp, spot) for years 1..n_durations."""
    obs = params.observable_years
    _require_years(risk_free_1_to_obs, range(1, obs + 1), "risk_free")
    _require_years(liquidity_premium_1_to_obs, range(1, obs + 1), "liquidity_premium")

    rf: Dict[int, float] = {}
    lp: Dict[int, float] = {}
    spot: Dict[int, float] = {}

    rf_obs = float(risk_free_1_to_obs[obs])
    lp_obs = float(liquidity_premium_1_to_obs[obs])

    for y in range(1, n_durations + 1):
        if y <= obs:
            rf[y] = float(risk_free_1_to_obs[y])
            lp[y] = float(liquidity_premium_1_to_obs[y])
        else:
            rf[y] = extrapolate_to_ultimate(
                rf_obs,
                params.ultimate_risk_free,
                year=y,
                observable_years=obs,
                ultimate_timing_years=params.ultimate_timing_years,
            )
            lp[y] = extrapolate_to_ultimate(
                lp_obs,
                params.ultimate_liquidity_premium,
                year=y,
                observable_years=obs,
                ultimate_timing_years=params.ultimate_timing_years,
            )
        spot[y] = rf[y] + lp[y]

    return rf, lp, spot


def spots_to_annual_forwards(spots: Mapping[int, float], n_durations: int = N_DURATIONS) -> Dict[int, float]:
    """Convert annual spot rates to one-year forward rates (Fiera column J)."""
    _require_years(spots, range(1, n_durations + 1), "spots")
    fwds: Dict[int, float] = {}
    for y in range(1, n_durations + 1):
        s_y = spots[y]
        if y == 1:
            fwds[y] = s_y
        else:
            s_prev = spots[y - 1]
            fwds[y] = (1.0 + s_y) ** y / (1.0 + s_prev) ** (y - 1) - 1.0
    return fwds


def build_column_j(
    risk_free_1_to_obs: Mapping[int, float],
    liquidity_premium_1_to_obs: Mapping[int, float],
    params: StaticParams,
    *,
    n_durations: int = N_DURATIONS,
) -> Dict[int, float]:
    _, _, spots = build_spot_curves(
        risk_free_1_to_obs,
        liquidity_premium_1_to_obs,
        params,
        n_durations=n_durations,
    )
    return spots_to_annual_forwards(spots, n_durations=n_durations)


def _write_slope_xlsx_stdlib(
    forwards: Mapping[int, float],
    path: Path,
    *,
    n_durations: int = N_DURATIONS,
) -> Path:
    """Minimal .xlsx writer (stdlib only) for Slope Sheet1 layout."""
    import zipfile

    rows_xml = [
        '<row r="1">'
        '<c r="A1" t="inlineStr"><is><t>Policy Duration</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Forward Rate</t></is></c>'
        "</row>"
    ]
    for y in range(1, n_durations + 1):
        rate = format(float(forwards[y]), ".17g")
        rows_xml.append(
            f'<row r="{y + 1}">'
            f'<c r="A{y + 1}"><v>{y}</v></c>'
            f'<c r="B{y + 1}"><v>{rate}</v></c>'
            "</row>"
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(rows_xml)
        + "</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def write_slope_xlsx(
    forwards: Mapping[int, float],
    path: Path,
    *,
    n_durations: int = N_DURATIONS,
) -> Path:
    """Write Slope Sheet1 workbook: Policy Duration, Forward Rate."""
    _require_years(forwards, range(1, n_durations + 1), "forwards")
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from openpyxl import Workbook
    except ImportError:
        return _write_slope_xlsx_stdlib(forwards, path, n_durations=n_durations)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Policy Duration", "Forward Rate"])
    for y in range(1, n_durations + 1):
        ws.append([y, float(forwards[y])])
    wb.save(path)
    return path


def write_slope_csv(
    forwards: Mapping[int, float],
    path: Path,
    *,
    n_durations: int = N_DURATIONS,
) -> Path:
    _require_years(forwards, range(1, n_durations + 1), "forwards")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Policy Duration", "Forward Rate"])
        for y in range(1, n_durations + 1):
            w.writerow([y, float(forwards[y])])
    return path


def load_reference_forwards(path: Path) -> Dict[int, float]:
    out: Dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        if "Policy Duration" in fields and "Forward Rate" in fields:
            for row in reader:
                y = _f(row.get("Policy Duration"))
                r = _f(row.get("Forward Rate"))
                if y is None or r is None:
                    continue
                out[int(y)] = r
        elif "year" in fields and "annual_forward_rate" in fields:
            for row in reader:
                y = _f(row.get("year"))
                r = _f(row.get("annual_forward_rate"))
                if y is None or r is None:
                    continue
                out[int(y)] = r
        else:
            raise ValueError(f"Unrecognized forward CSV columns in {path}: {fields}")
    return out


def max_abs_error_bp(
    constructed: Mapping[int, float],
    reference: Mapping[int, float],
    years: Optional[Iterable[int]] = None,
) -> Tuple[float, int]:
    """Return (max |Δ| in basis points, year of max)."""
    ys = list(years) if years is not None else sorted(set(constructed) & set(reference))
    if not ys:
        raise ValueError("No overlapping years to compare")
    max_bp = -1.0
    max_year = ys[0]
    for y in ys:
        bp = abs(constructed[y] - reference[y]) * 10_000.0
        if bp > max_bp:
            max_bp = bp
            max_year = y
    return max_bp, max_year


def build_from_fixtures(
    *,
    as_of: Optional[str] = None,
    params_path: Optional[Path] = None,
    out_dir: Path = CURVES_DIR,
    n_durations: int = N_DURATIONS,
) -> dict:
    """Build column J from latest (or named) Fiera fixture RF + held H + static params."""
    params = load_static_params(params_path)
    prem_as_of, premium = load_held_liquidity_premium(as_of=as_of)
    rf_as_of, risk_free = load_fixture_risk_free(as_of=as_of)
    if prem_as_of != rf_as_of:
        raise RuntimeError(
            f"Premium as_of {prem_as_of} != RF as_of {rf_as_of}; "
            "fixture validation expects a single publication day"
        )

    forwards = build_column_j(risk_free, premium, params, n_durations=n_durations)
    stem = f"illiquid_col_j_{prem_as_of}"
    xlsx_path = out_dir / f"{stem}.xlsx"
    csv_path = out_dir / f"{stem}.csv"
    write_slope_xlsx(forwards, xlsx_path, n_durations=n_durations)
    write_slope_csv(forwards, csv_path, n_durations=n_durations)

    return {
        "as_of": prem_as_of,
        "premium_policy": PREMIUM_POLICY,
        "rf_source": "fiera_illiquid_construction_col_E",
        "rf_as_of": rf_as_of,
        "params_as_of": params.raw.get("as_of"),
        "forwards": forwards,
        "xlsx_path": xlsx_path,
        "csv_path": csv_path,
    }


def build_from_boc(
    *,
    as_of: Optional[str] = None,
    params_path: Optional[Path] = None,
    out_dir: Path = CURVES_DIR,
    n_durations: int = N_DURATIONS,
    boc_snapshot: Optional[Path] = None,
    try_download: bool = True,
) -> dict:
    """Build column J from BoC zeros (annual effective 1–30) + held H + static params."""
    from pipeline.boc_intake import load_risk_free_for_builder

    params = load_static_params(params_path)
    prem_as_of, premium = load_held_liquidity_premium(as_of=as_of)
    rf_as_of, risk_free, snapshot, snap_path = load_risk_free_for_builder(
        snapshot_path=boc_snapshot,
        try_download=try_download,
    )

    forwards = build_column_j(risk_free, premium, params, n_durations=n_durations)
    stem = f"illiquid_col_j_boc_rf_{rf_as_of}_h_{prem_as_of}"
    xlsx_path = out_dir / f"{stem}.xlsx"
    csv_path = out_dir / f"{stem}.csv"
    write_slope_xlsx(forwards, xlsx_path, n_durations=n_durations)
    write_slope_csv(forwards, csv_path, n_durations=n_durations)

    return {
        "as_of": prem_as_of,
        "premium_policy": PREMIUM_POLICY,
        "rf_source": "boc_zero_coupon_csv",
        "rf_as_of": rf_as_of,
        "rf_snapshot_path": snap_path,
        "rf_is_fixture": bool(snapshot.get("is_fixture")),
        "rf_publish_lag_days": (snapshot.get("gaps") or {}).get("publish_lag_days"),
        "params_as_of": params.raw.get("as_of"),
        "forwards": forwards,
        "xlsx_path": xlsx_path,
        "csv_path": csv_path,
    }


def validate_against_fiera(
    constructed: Mapping[int, float],
    *,
    reference_path: Optional[Path] = None,
) -> dict:
    ref_path = reference_path or (LATEST / "slope_forwards_column_J.csv")
    reference = load_reference_forwards(ref_path)
    max_bp, max_year = max_abs_error_bp(constructed, reference)
    return {
        "reference_path": str(ref_path),
        "max_abs_error_bp": max_bp,
        "max_abs_error_year": max_year,
        "n_compared": len(set(constructed) & set(reference)),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default=None,
        help="Fiera publication date (YYYY-MM-DD) for held col H / Fiera RF. Default: latest extract.",
    )
    parser.add_argument(
        "--rf",
        choices=("fiera", "boc"),
        default="fiera",
        help="Risk-free source: fiera construction col E (default) or BoC zero-coupon CSV snapshot",
    )
    parser.add_argument(
        "--boc-snapshot",
        type=Path,
        default=None,
        help="Optional path to data/risk_free/YYYY-MM-DD.json (implies --rf boc)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=CURVES_DIR,
        help=f"Output directory for Slope workbooks (default: {CURVES_DIR})",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Diff constructed J vs latest slope_forwards_column_J.csv and print max |Δ| bp",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="Optional reference forwards CSV for --validate",
    )
    args = parser.parse_args(argv)

    rf_mode = "boc" if args.boc_snapshot is not None else args.rf
    if rf_mode == "boc":
        result = build_from_boc(
            as_of=args.as_of,
            out_dir=args.out_dir,
            boc_snapshot=args.boc_snapshot,
        )
    else:
        result = build_from_fixtures(as_of=args.as_of, out_dir=args.out_dir)

    print(f"as_of:           {result['as_of']}")
    print(f"premium_policy:  {result['premium_policy']}")
    print(f"rf_source:       {result['rf_source']}")
    print(f"rf_as_of:        {result.get('rf_as_of')}")
    if result.get("rf_snapshot_path") is not None:
        print(f"rf_snapshot:     {result['rf_snapshot_path']}")
        print(f"rf_is_fixture:   {result.get('rf_is_fixture')}")
        print(f"rf_lag_days:     {result.get('rf_publish_lag_days')}")
    print(f"wrote xlsx:      {result['xlsx_path']}")
    print(f"wrote csv:       {result['csv_path']}")

    # Validate only the Fiera fixture path against extracted col J (BoC RF will not match).
    if rf_mode == "fiera" and (args.validate or args.as_of is None):
        report = validate_against_fiera(result["forwards"], reference_path=args.reference)
        print(f"validate ref:    {report['reference_path']}")
        print(
            f"max |Δ| bp:      {report['max_abs_error_bp']:.6g} "
            f"(year {report['max_abs_error_year']}, n={report['n_compared']})"
        )
    elif args.validate and rf_mode == "boc":
        print(
            "validate skipped: --validate compares to Fiera col J; "
            "use --rf fiera for that check"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
