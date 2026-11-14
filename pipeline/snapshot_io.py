"""Write decision log + enrich + single monitor_snapshot.json.

Single destination: ``data/monitor/monitor_snapshot.json``. The dashboard
loads that path via ``CONFIG.snapshotUrl`` (serve from the TVFI project root).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from . import decision_hooks

ROOT = Path(__file__).resolve().parents[1]
MONITOR_DIR = ROOT / "data" / "monitor"


def write_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Path]:
    """Write decision log, enrich optional sections, then write monitor JSON once."""
    decision_path = decision_hooks.write_decision_log(snapshot)
    decision_hooks.enrich_snapshot(snapshot, decision_path)

    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    monitor_path = MONITOR_DIR / "monitor_snapshot.json"
    monitor_path.write_text(
        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "decision": decision_path,
        "monitor": monitor_path,
    }
