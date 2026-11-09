#!/usr/bin/env python3
"""Step 2: wait for the runs that run_curves.py started, get their results, and analyse them.

    wait_for_runs()                              # waits until every run has finished
    results = load_results()
    path = results["base"]["Cash Flows"]         # the Cash Flows CSV of the run of base.xlsx
"""
import csv

from slope_api import wait_for_runs, load_results


def main():
    statuses = wait_for_runs()
    results = load_results()

    for curve, files in results.items():
        print(f"\n{curve} ({statuses[curve]})")
        for name, path in files.items():
            with path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
            print(f"  {name:<22} {len(rows) - 1:>6} rows  {len(rows[0]):>3} columns")


if __name__ == "__main__":
    main()
