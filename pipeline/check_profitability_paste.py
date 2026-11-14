#!/usr/bin/env python3
"""Fail if analyse_results.py profitability helpers drift from the pipeline module.

TVFI checkpoint packaging cannot ``import pipeline``. Helpers are pasted into
``analyse_results.py`` and must stay byte-identical (normalized) to
``pipeline/profitability_formulas.py``.

Usage (from project root):

    python3 -m pipeline.check_profitability_paste
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "pipeline" / "profitability_formulas.py"
PASTE = ROOT / "analyse_results.py"

# Symbols that must match between module and paste.
COMPARE_FUNCS = (
    "excel_npv",
    "vonb_dollars_from_ctfs",
    "vonb_pct",
    "net_csm_pct",
    "capm_denominator",
    "capm",
    "ratio_of_sums",
    "per_cell_metrics",
    "aggregate_metrics",
    "group_by_plan_code",
    "group_individuals",
    "summarize_cuts",
    "map_result_keys",
    "build_ctfs_series_by_model_point",
)
COMPARE_CONSTS = ("RISK_DISCOUNT_RATE", "INDIVIDUAL_KEYS")


def _norm_src(src: str) -> str:
    return "".join(src.split())


def _sha(src: str) -> str:
    return hashlib.sha1(_norm_src(src).encode()).hexdigest()[:12]


def _func_bodies(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    out: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(text, node) or ""
            out[node.name] = seg
    return out


def _const_values(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    out: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in COMPARE_CONSTS:
                    seg = ast.get_source_segment(text, node) or ""
                    out[t.id] = seg
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in COMPARE_CONSTS:
                seg = ast.get_source_segment(text, node) or ""
                out[node.target.id] = seg
    return out


def compare() -> Tuple[List[str], List[str]]:
    """Return (ok_messages, error_messages)."""
    ok: List[str] = []
    err: List[str] = []
    if not MODULE.is_file():
        return ok, [f"missing module: {MODULE}"]
    if not PASTE.is_file():
        return ok, [f"missing paste target: {PASTE}"]

    mod_fns = _func_bodies(MODULE)
    paste_fns = _func_bodies(PASTE)
    mod_c = _const_values(MODULE)
    paste_c = _const_values(PASTE)

    for name in COMPARE_CONSTS:
        if name not in mod_c:
            err.append(f"module missing const {name}")
            continue
        if name not in paste_c:
            err.append(f"analyse_results.py missing const {name}")
            continue
        if _sha(mod_c[name]) != _sha(paste_c[name]):
            err.append(f"const drifted: {name}")
        else:
            ok.append(f"const ok: {name}")

    missing_mod: Set[str] = set()
    missing_paste: Set[str] = set()
    for name in COMPARE_FUNCS:
        if name not in mod_fns:
            missing_mod.add(name)
            err.append(f"module missing def {name}")
            continue
        if name not in paste_fns:
            missing_paste.add(name)
            err.append(f"analyse_results.py missing def {name}")
            continue
        if _sha(mod_fns[name]) != _sha(paste_fns[name]):
            err.append(
                f"def drifted: {name} "
                f"(module={_sha(mod_fns[name])} paste={_sha(paste_fns[name])})"
            )
        else:
            ok.append(f"def ok: {name}")

    extra = sorted(
        n
        for n in paste_fns
        if n in COMPARE_FUNCS and n not in missing_paste and n in mod_fns
    )
    _ = extra  # silence unused; ok list already covers matches
    return ok, err


def main() -> int:
    ok, err = compare()
    print("Profitability paste freeze check")
    print(f"  module: {MODULE.relative_to(ROOT)}")
    print(f"  paste:  {PASTE.relative_to(ROOT)}")
    print(f"  matched: {len(ok)}")
    if err:
        print(f"  failures: {len(err)}")
        for line in err:
            print(f"  FAIL  {line}")
        print(
            "\nRe-paste helpers from pipeline/profitability_formulas.py into "
            "analyse_results.py (do not import pipeline in the checkpoint scripts)."
        )
        return 1
    print("  all compared symbols identical (whitespace-normalized).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
