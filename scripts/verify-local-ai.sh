#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly worker_root="$repository_root/backend/workers/analysis"
readonly local_root="$repository_root/.local-ai"
readonly python="$local_root/venv/bin/python"
readonly matplotlib_root="$local_root/matplotlib"
readonly capabilities="$local_root/runtime-capabilities.json"

rm -f "$capabilities"

if [[ ! -x "$python" ]]; then
  printf '%s\n' 'Local AI environment is missing. Run ./scripts/bootstrap-local-ai.sh first.' >&2
  exit 1
fi

mkdir -p "$matplotlib_root"
export MPLCONFIGDIR="$matplotlib_root"

ffmpeg -version | sed -n '1p'
ffprobe -version | sed -n '1p'
"$python" -m pytest "$worker_root/tests" -q
"$python" -m stage_lab_analysis.runtime_probe probe \
  --manifest "$worker_root/model-manifest.json" \
  --model-root "$local_root/models" \
  --output "$capabilities"
