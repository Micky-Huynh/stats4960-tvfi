#!/usr/bin/env python3
"""Local pre-submit checks for TVFI packaging / push hygiene.

Currently gates profitability paste freeze (checkpoint scripts cannot import
pipeline). Add more checks here as needed — there is no CI workflow yet.

Usage (from project root):

    python3 -m pipeline.pre_submit
"""

from __future__ import annotations

import sys

from pipeline import check_profitability_paste


def main() -> int:
    print("== pre_submit: profitability paste freeze ==")
    code = check_profitability_paste.main()
    if code != 0:
        print("pre_submit FAILED")
        return code
    print("pre_submit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
