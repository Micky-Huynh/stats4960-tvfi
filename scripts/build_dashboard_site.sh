#!/usr/bin/env bash
# Assemble the static dashboard bundle for Cloudflare (wrangler.jsonc -> dist/dashboard-site).
# Layout mirrors the project so dashboard.js's relative '../../data/...' URLs resolve:
#   /dashboard/ui/index.html  ->  ../../data/...  ->  /data/...
# Only the data files the dashboard fetches are copied (no raw Fiera workbooks).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/dashboard-site"
UI_SRC="$ROOT/Dashboard UI/Group5_Monitoring_Dashboard"

DATA_FILES=(
  data/monitor/monitor_snapshot.json
  data/curves/lag_bridge_mlr_levels_delta_results.json
  data/curves/lag_error_report.json
  data/curves/lag_bridge_2026-11-04_applied.json
  data/curves/lag_bootstrap/lag_bootstrap_curves.xlsx
  data/curves/lag_bootstrap/summary_2026-11-04_to_2026-11-19.json
  data/risk_free/2026-10-21.json
  data/risk_free/2026-10-28.json
  data/risk_free/2026-11-04.json
)
LAG_METHOD_DIRS=(ridge pca pca_ridge)

rm -rf "$OUT"
mkdir -p "$OUT/dashboard/ui"

for f in index.html styles.css dashboard.js monitor_snapshot.json; do
  cp "$UI_SRC/$f" "$OUT/dashboard/ui/$f"
done

for f in "${DATA_FILES[@]}"; do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "ERROR: missing required data file: $f" >&2
    exit 1
  fi
  mkdir -p "$OUT/$(dirname "$f")"
  cp "$ROOT/$f" "$OUT/$f"
done

for m in "${LAG_METHOD_DIRS[@]}"; do
  src="$ROOT/data/curves/lag_bootstrap/$m"
  if [[ ! -d "$src" ]]; then
    echo "ERROR: missing lag bootstrap dir: $src" >&2
    exit 1
  fi
  mkdir -p "$OUT/data/curves/lag_bootstrap/$m"
  cp "$src"/*.json "$OUT/data/curves/lag_bootstrap/$m/"
done

# Root -> dashboard
printf '/  /dashboard/ui/  302\n' > "$OUT/_redirects"

echo "Built $OUT ($(find "$OUT" -type f | wc -l | tr -d ' ') files, $(du -sh "$OUT" | cut -f1))"
