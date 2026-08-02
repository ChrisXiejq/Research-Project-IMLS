#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
DAY6_RESULTS="${DAY6_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day6/formal/day6_formal_v2_200}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1}"
DAY9_RESULTS="${DAY9_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day9/day9_smoke_v1}"
DAY10_RESULTS="${DAY10_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day10/day10_formal_v1}"
DAY11_RESULTS="${DAY11_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day11/day11_timing_shift_v1}"
DAY12_RESULTS="${DAY12_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day12/day12_evidence_freeze_v1}"

mkdir -p "$DAY12_RESULTS"
exec > >(tee -a "$DAY12_RESULTS/day12_runner.log") 2>&1

echo "[$(date -Iseconds)] Day12 collision-window attribution"
python "$REPO_ROOT/core/scripts/models/audit_day6_collision_windows.py" \
  --day6-results "$DAY6_RESULTS" \
  --output-dir "$DAY12_RESULTS/collision_attribution"

echo "[$(date -Iseconds)] Day10 init-cluster analysis v3"
python "$REPO_ROOT/core/scripts/models/analyze_day10_closed_loop.py" \
  --results-dir "$DAY10_RESULTS" \
  --output-dir "$DAY12_RESULTS/day10_analysis_v3"

echo "[$(date -Iseconds)] Day10+Day11 timing synthesis"
python "$REPO_ROOT/core/scripts/models/analyze_day12_timing_synthesis.py" \
  --day10-results "$DAY10_RESULTS" \
  --day11-results "$DAY11_RESULTS" \
  --output-dir "$DAY12_RESULTS/timing_synthesis"

echo "[$(date -Iseconds)] Critical asset bundles"
python "$REPO_ROOT/core/scripts/models/package_day12_critical_assets.py" \
  --day6-results "$DAY6_RESULTS" \
  --day7-results "$DAY7_RESULTS" \
  --day8-results "$DAY8_RESULTS" \
  --selection-freeze "$DAY8_RESULTS/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  --day9-preflight "$DAY9_RESULTS/day9_deployment_preflight.json" \
  --b0-model "$REPO_ROOT/core/scripts/models/l5kit_multipath_10" \
  --anchors "$REPO_ROOT/core/scripts/models/l5kit_clusters_16.npy" \
  --day10-results "$DAY10_RESULTS" \
  --day11-results "$DAY11_RESULTS" \
  --day10-snapshot "$DAY10_RESULTS/day10_formal_snapshot.tar.gz" \
  --day11-snapshot "$DAY11_RESULTS/day11_timing_shift_snapshot.tar.gz" \
  --output-dir "$DAY12_RESULTS/asset_backup"

echo "[$(date -Iseconds)] Day12 server stage complete"
cat "$DAY12_RESULTS/collision_attribution/DAY12_COLLISION_ATTRIBUTION_COMPLETE.json"
cat "$DAY12_RESULTS/timing_synthesis/DAY12_TIMING_SYNTHESIS_COMPLETE.json"
cat "$DAY12_RESULTS/asset_backup/DAY12_ASSET_BACKUP_SERVER_STAGE_COMPLETE.json"
