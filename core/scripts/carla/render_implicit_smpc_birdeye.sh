#!/usr/bin/env bash
set -euo pipefail

# Re-run one frozen, gate-passing implicit-SMPC configuration with CARLA's
# native RGB sensor enabled, then transcode the lossless-ish MJPG capture to
# a broadly playable H.264 MP4.  This script never selects or changes a model.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_GLOB="${INIT_GLOB:-paper_intersection_50/ego_init_01.json}"
TUNING_CONFIG="${TUNING_CONFIG:?TUNING_CONFIG must identify the frozen gate-passing configuration}"
RESULTS_DIR="${RESULTS_DIR:?RESULTS_DIR must be an explicit persistent output directory}"
CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
CARLA_PORT="${CARLA_PORT:-2000}"
RISK_PROFILE="${RISK_PROFILE:-paper_eps_002}"

if [[ -e "${RESULTS_DIR}" && -n "$(find "${RESULTS_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "ERROR: refusing to overwrite non-empty video results directory: ${RESULTS_DIR}" >&2
  exit 2
fi
mkdir -p "${RESULTS_DIR}"

RESULTS_DIR="${RESULTS_DIR}" \
INIT_GLOB="${INIT_GLOB}" \
TUNING_CONFIG="${TUNING_CONFIG}" \
CARLA_HOST="${CARLA_HOST}" \
CARLA_PORT="${CARLA_PORT}" \
RISK_PROFILE="${RISK_PROFILE}" \
ENABLE_CAMERA_VIZ=1 \
"${SCRIPT_DIR}/run_implicit_smpc_safety_filter.sh"

avi_path="$(find "${RESULTS_DIR}" -mindepth 2 -maxdepth 2 -type f -name carla_sim.avi -print -quit)"
if [[ -z "${avi_path}" || ! -s "${avi_path}" ]]; then
  echo "ERROR: CARLA native camera capture was not produced." >&2
  exit 1
fi

mp4_path="${RESULTS_DIR}/implicit_smpc_birdeye.mp4"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -loglevel error -y \
    -i "${avi_path}" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart \
    "${mp4_path}"
else
  echo "WARNING: ffmpeg is unavailable; preserving the verified CARLA AVI for local transcoding." >&2
  mp4_path=""
fi

if [[ -n "${mp4_path}" ]]; then
  sha256sum "${avi_path}" "${mp4_path}" > "${RESULTS_DIR}/video_sha256.txt"
  inspect_path="${mp4_path}"
else
  sha256sum "${avi_path}" > "${RESULTS_DIR}/video_sha256.txt"
  inspect_path="${avi_path}"
fi
"${PYTHON_BIN}" -c 'import cv2, json, os, sys; p=sys.argv[1]; c=cv2.VideoCapture(p); meta={"schema_version":"carla_native_birdeye_video_v1","path":os.path.abspath(p),"frame_count":int(c.get(cv2.CAP_PROP_FRAME_COUNT)),"fps":float(c.get(cv2.CAP_PROP_FPS)),"width":int(c.get(cv2.CAP_PROP_FRAME_WIDTH)),"height":int(c.get(cv2.CAP_PROP_FRAME_HEIGHT)),"source":"CARLA sensor.camera.rgb via RunIntersectionScenario"}; c.release(); print(json.dumps(meta,indent=2))' "${inspect_path}" > "${RESULTS_DIR}/video_manifest.json"

echo "Bird's-eye capture: ${inspect_path}"
