#!/usr/bin/env bash
# Option 1: keep TVFI agent sessions named and stable.
# Does not attach; safe to run from either pane or outside tmux.

set -euo pipefail

ensure_session() {
  local name="$1"
  if tmux has-session -t "$name" 2>/dev/null; then
    echo "ok: session '$name' exists"
  else
    tmux new-session -ds "$name"
    echo "created: session '$name'"
  fi
}

ensure_session "pi-TVFI"
ensure_session "cc-STATS-Consulting"

echo
tmux list-sessions -F '#{session_name} attached=#{session_attached} windows=#{session_windows}'
