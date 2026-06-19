#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: tools/run_postcarla_trajectory_gate.sh core/results/<timestamp> [extra args...]"
  exit 2
fi

RESULTS_DIR="$1"
shift

echo "== Post-CARLA trajectory safety gate =="
.venv-precarla/bin/python core/scripts/postcarla_trajectory_gate.py "$RESULTS_DIR" "$@"
