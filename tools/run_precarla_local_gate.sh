#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SKIP_MATLAB=0
if [[ "${1:-}" == "--skip-matlab" ]]; then
  SKIP_MATLAB=1
fi

echo "== Python/Gymnasium pre-CARLA comprehensive gate =="
.venv-precarla/bin/python core/scripts/precarla_comprehensive_eval.py

echo
echo "== MATLAB pre-CARLA gate =="
if [[ "$SKIP_MATLAB" == "1" ]]; then
  echo "SKIP: MATLAB gate skipped by --skip-matlab."
elif command -v matlab >/dev/null 2>&1; then
  matlab -batch "addpath('core/scripts/matlab'); precarla_validate_uk_give_way_matlab"
elif command -v octave >/dev/null 2>&1; then
  octave --quiet --eval "addpath('core/scripts/matlab'); precarla_validate_uk_give_way_matlab"
else
  echo "ERROR: neither matlab nor octave is available on PATH."
  echo "Install MATLAB command-line tools or add matlab to PATH before using this full gate."
  exit 2
fi

echo
if [[ "$SKIP_MATLAB" == "1" ]]; then
  echo "Python/Gymnasium local pre-CARLA gate passed. MATLAB gate was skipped."
else
  echo "All local pre-CARLA gates passed."
fi
