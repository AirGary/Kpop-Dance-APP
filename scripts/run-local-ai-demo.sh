#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly backend_root="$repository_root/backend"
readonly local_root="$repository_root/.local-ai"
readonly api_python="$backend_root/.venv/bin/python"
readonly worker_python="$local_root/venv/bin/python"
readonly default_bind="127.0.0.1"

bind="$default_bind"
port="8000"
frame_stride="${LOCAL_AI_FRAME_STRIDE:-30}"
server_pid=""
runtime_dir=""

usage() {
  printf '%s\n' "Usage: $0 [--bind 127.0.0.1|PRIVATE_IPV4] [--port 8000] [--frame-stride 30]"
}

private_ipv4() {
  local address="$1"
  local first second third fourth
  IFS=. read -r first second third fourth <<< "$address"
  [[ "$address" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  (( first <= 255 && second <= 255 && third <= 255 && fourth <= 255 )) || return 1
  (( first == 10 )) && return 0
  (( first == 172 && second >= 16 && second <= 31 )) && return 0
  (( first == 192 && second == 168 )) && return 0
  return 1
}

while (($# > 0)); do
  case "$1" in
    --bind)
      bind="${2:?--bind requires an address}"
      shift 2
      ;;
    --port)
      port="${2:?--port requires a number}"
      shift 2
      ;;
    --frame-stride)
      frame_stride="${2:?--frame-stride requires a positive integer}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$bind" != "$default_bind" && "$bind" != "localhost" && "$bind" != "::1" ]] && ! private_ipv4 "$bind"; then
  printf '%s\n' 'Refusing non-private IPv4 bind address.' >&2
  exit 2
fi
if [[ ! -x "$api_python" ]]; then
  printf '%s\n' 'Backend environment is missing. Run ./scripts/verify-backend.sh first.' >&2
  exit 1
fi
if [[ ! -x "$worker_python" ]]; then
  printf '%s\n' 'Local AI environment is missing. Run ./scripts/bootstrap-local-ai.sh first.' >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  printf '%s\n' 'openssl is required to create a short-lived pairing token.' >&2
  exit 1
fi

runtime_dir="$(mktemp -d "${TMPDIR:-/tmp}/stage-lab-local-ai.XXXXXX")"
pairing_token="$(openssl rand -hex 24)"
pairing_env_file="$runtime_dir/stage-lab.env"
cat > "$pairing_env_file" <<EOF
export STAGE_LAB_ENVIRONMENT=local-ai
export STAGE_LAB_API_BASE_URL=http://$bind:$port
export STAGE_LAB_PAIRING_TOKEN=$pairing_token
EOF
chmod 600 "$pairing_env_file"

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "$runtime_dir" ]]; then
    rm -rf "$runtime_dir"
  fi
}
trap cleanup EXIT INT TERM

export APP_ENVIRONMENT="local-ai"
export OBJECT_STORAGE_ROOT="$runtime_dir/objects"
export LOCAL_AI_MODEL_ROOT="$local_root/models"
export LOCAL_AI_FRAME_STRIDE="$frame_stride"
export STAGE_LAB_PAIRING_TOKEN="$pairing_token"

(
  cd "$backend_root"
  exec "$api_python" -m uvicorn api.app.main:app --host "$bind" --port "$port"
) &
server_pid=$!

for _ in {1..30}; do
  if curl --silent --fail "http://$bind:$port/health" >/dev/null 2>&1; then
    printf 'STAGE_LAB_ENVIRONMENT=local-ai\n'
    printf 'STAGE_LAB_API_BASE_URL=http://%s:%s\n' "$bind" "$port"
    printf 'STAGE_LAB_PAIRING_ENV_FILE=%s\n' "$pairing_env_file"
    printf 'Local AI is running. Source the env file before launching the Debug app.\n'
    wait "$server_pid"
    exit $?
  fi
  sleep 1
done

printf '%s\n' 'Local AI API did not become healthy.' >&2
exit 1
