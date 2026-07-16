#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly worker_root="$repository_root/backend/workers/analysis"
readonly local_root="$repository_root/.local-ai"
readonly virtual_environment="$local_root/venv"
readonly model_root="$local_root/models"
readonly manifest="$worker_root/model-manifest.json"
readonly constraints="$worker_root/constraints-macos-arm64.txt"
readonly artifact_lock="$worker_root/requirements-macos-arm64.lock"
readonly license_manifest="$worker_root/dependency-licenses.json"
readonly package_root="$local_root/packages"

missing=()
for tool in python3.11 ffmpeg ffprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing+=("$tool")
  fi
done

if (( ${#missing[@]} > 0 )); then
  printf 'Missing local AI prerequisites: %s\n' "${missing[*]}" >&2
  printf '%s\n' 'Install only after approval with: brew install python@3.11 ffmpeg' >&2
  exit 1
fi

PYTHONPATH="$worker_root" python3.11 -c \
  'from pathlib import Path; import sys; from stage_lab_analysis.runtime_probe import load_model_manifest; load_model_manifest(Path(sys.argv[1]))' \
  "$manifest"
PYTHONPATH="$worker_root" python3.11 -m stage_lab_analysis.supply_chain \
  --lock "$artifact_lock" \
  --licenses "$license_manifest"

if [[ ! -x "$virtual_environment/bin/python" ]]; then
  python3.11 -m venv "$virtual_environment"
fi

export PATH="$virtual_environment/bin:$PATH"

mkdir -p "$package_root"
find "$package_root" -type f -delete
"$virtual_environment/bin/python" -m pip download --no-build-isolation --require-hashes \
  -r "$artifact_lock" \
  --dest "$package_root"

offline=(--no-index --find-links "$package_root" -c "$constraints")

"$virtual_environment/bin/python" -m pip install "${offline[@]}" \
  pip==26.1.2 setuptools==80.10.2 wheel==0.47.0 ninja==1.13.0
"$virtual_environment/bin/python" -m pip install "${offline[@]}" \
  torch==2.13.0 torchvision==0.28.0
"$virtual_environment/bin/python" -m pip install "${offline[@]}" \
  --no-build-isolation chumpy==0.70
"$virtual_environment/bin/python" -m pip install "${offline[@]}" \
  --no-build-isolation mmcv==2.1.0 --no-cache-dir
"$virtual_environment/bin/python" -m pip install "${offline[@]}" \
  mmengine==0.10.7 mmdet==3.3.0 mmpose==1.3.2 \
  opencv-python-headless==4.11.0.86 numpy==1.26.4 pydantic==2.13.4 pytest==9.1.1
"$virtual_environment/bin/python" -m pip install --no-build-isolation --no-deps -e "$worker_root"
"$virtual_environment/bin/python" -m pip check
"$virtual_environment/bin/python" -m stage_lab_analysis.runtime_probe download \
  --manifest "$manifest" \
  --model-root "$model_root"
"$virtual_environment/bin/python" -m pip freeze --exclude-editable > "$local_root/requirements.lock"

printf 'local_ai_environment=%s\nmodel_root=%s\n' \
  "$virtual_environment" \
  "$model_root"
