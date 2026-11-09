#!/usr/bin/env python3
"""Build monitor_snapshot.json from archived Fiera data and sync it to the dashboard.

Usage (from the TVFI project root):

    python3 -m pipeline.build_monitor_snapshot
    python3 pipeline/build_monitor_snapshot.py

Writes:
  data/monitor/monitor_snapshot.json
  Dashboard UI/Group5_Monitoring_Dashboard/monitor_snapshot.json

Then serve the dashboard:

    cd "Dashboard UI/Group5_Monitoring_Dashboard" && python3 -m http.server 8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python3 pipeline/build_monitor_snapshot.py` from project root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.snapshot import build_snapshot, write_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-thresholds",
        action="store_true",
        help="Leave trigger thresholds null (UNASSESSED) instead of calibrated values",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the snapshot JSON to stdout",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(use_provisional_thresholds=not args.no_thresholds)
    paths = write_snapshot(snapshot)

    print(f"snapshot_id: {snapshot['snapshot_id']}")
    print(f"status:      {snapshot['assessment']['overall_status']}")
    print(f"pricing:     {snapshot['meta']['pricing_basis_date']}")
    print(f"observation: {snapshot['meta']['observation_date']}")
    for name, path in paths.items():
        print(f"wrote [{name}]: {path}")
    m = snapshot.get("metrics_computed", {})
    print(
        "metrics bp:",
        f"mean_abs={m.get('abs_mean_change_bp')}",
        f"max_abs={m.get('max_abs_change_bp')}",
        f"twist={m.get('abs_twist_2s10s_bp')}",
    )
    if args.print:
        print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
