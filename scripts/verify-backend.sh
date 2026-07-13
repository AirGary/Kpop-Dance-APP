#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly backend_root="$repository_root/backend"
readonly virtual_environment="$backend_root/.venv"

if [[ ! -x "$virtual_environment/bin/python" ]]; then
  python3 -m venv "$virtual_environment"
fi

"$virtual_environment/bin/python" -m pip install -e "$backend_root[dev]"
(
  cd "$backend_root"
  .venv/bin/python -m pytest -q
  .venv/bin/python -c 'from api.app.main import create_app; create_app()'
)

if command -v terraform >/dev/null 2>&1; then
  terraform -chdir="$repository_root/infra/terraform" fmt -check -recursive
else
  printf '%s\n' "Terraform is not installed; formatting check skipped (no deployment attempted)."
fi
