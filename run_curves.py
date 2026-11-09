#!/usr/bin/env python3
"""Step 1: start a SLOPE run for each of your curves.

    run_slope_curve(curve_file, GROUP)

runs one curve on SLOPE. The curve file must be an .xlsx with one sheet named Sheet1 and two
columns, headers in row 1:
    Policy Duration   1, 2, 3, ... 100   (fixed: exactly these, in this order)
    Forward Rate      0.0326, ...        (a decimal, not a percent)
100 data rows, one per duration.

A curve file name that has already been run is not run again: to run a changed curve, save it
under a new name.
"""
from pathlib import Path

from slope_api import run_slope_curve

GROUP = 5                                       # your group number, 1 to 5


def main():
    curve_file = Path("sample_curve.xlsx")
    run_slope_curve(curve_file, GROUP)


if __name__ == "__main__":
    main()
