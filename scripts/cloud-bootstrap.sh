#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly backend_root="$repository_root/backend"
readonly terraform_root="$repository_root/infra/terraform/environments/dev"
readonly plan_file="$terraform_root/stage5b.tfplan"
readonly project_id="stage-lab-dev-gary-202607"
readonly region="asia-southeast1"
readonly repository="stage-lab-api"
readonly image_name="api"
readonly registry_host="$region-docker.pkg.dev"
readonly image_base="$registry_host/$project_id/$repository/$image_name"
readonly source_bucket_name="stage-lab-dev-gary-202607-source"
readonly result_bucket_name="stage-lab-dev-gary-202607-results"
readonly bootstrap_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000"
readonly system_git="/usr/bin/git"

usage() {
  printf '%s\n' "Usage: $0 {foundation|image|plan IMAGE_DIGEST_URI|apply|smoke}" >&2
}

require_tools() {
  local tool
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      printf 'Required command is unavailable: %s\n' "$tool" >&2
      exit 1
    fi
  done
}

terraform_dev() {
  terraform -chdir="$terraform_root" "$@"
}

foundation() {
  require_tools gcloud terraform
  gcloud projects describe "$project_id" --format='value(projectId)' >/dev/null
  terraform_dev init
  terraform_dev apply \
    -target='google_project_service.required' \
    -target='google_artifact_registry_repository.api' \
    -var="project_id=$project_id" \
    -var="container_image=$image_base@$bootstrap_digest" \
    -var="source_bucket_name=$source_bucket_name" \
    -var="result_bucket_name=$result_bucket_name"
}

build_image() {
  require_tools docker gcloud
  if [[ ! -x "$system_git" ]]; then
    printf 'Required command is unavailable: %s\n' "$system_git" >&2
    exit 1
  fi
  gcloud auth configure-docker "$registry_host" --quiet >&2

  local git_sha image_tag digest
  git_sha="$("$system_git" -C "$repository_root" rev-parse --short=12 HEAD)"
  image_tag="$image_base:$git_sha"
  docker buildx build \
    --platform linux/amd64 \
    --push \
    --tag "$image_tag" \
    "$backend_root" >&2
  digest="$(
    gcloud artifacts docker images describe "$image_tag" \
      --project="$project_id" \
      --format='value(image_summary.digest)'
  )"

  if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf 'Artifact Registry returned an invalid digest: %s\n' "$digest" >&2
    exit 1
  fi
  printf '%s@%s\n' "$image_base" "$digest"
}

create_plan() {
  require_tools terraform
  local image_uri="${1:-}"
  if [[ ! "$image_uri" =~ @sha256:[0-9a-f]{64}$ ]]; then
    printf '%s\n' "plan requires an immutable Artifact Registry image URI." >&2
    exit 1
  fi

  terraform_dev init
  terraform_dev plan \
    -out="$plan_file" \
    -var="project_id=$project_id" \
    -var="container_image=$image_uri" \
    -var="source_bucket_name=$source_bucket_name" \
    -var="result_bucket_name=$result_bucket_name"
  printf 'Saved reviewed plan candidate: %s\n' "$plan_file"
}

apply_plan() {
  require_tools terraform
  if [[ ! -f "$plan_file" ]]; then
    printf 'Saved Terraform plan is missing: %s\n' "$plan_file" >&2
    exit 1
  fi
  terraform_dev apply "$plan_file"
}

smoke_test() {
  require_tools curl terraform
  local api_url health protected_body protected_status
  api_url="$(terraform_dev output -raw api_url)"
  health="$(curl --fail --silent --show-error "$api_url/health")"
  if [[ "$health" != *'"status":"ok"'* || "$health" != *'"environment":"cloud"'* ]]; then
    printf 'Unexpected health response: %s\n' "$health" >&2
    exit 1
  fi

  protected_body="$(mktemp)"
  protected_status="$(
    curl --silent --show-error \
      --output "$protected_body" \
      --write-out '%{http_code}' \
      --header 'Authorization: Bearer dev-user-a' \
      "$api_url/v1/me"
  )"
  if [[ "$protected_status" != "401" ]]; then
    printf 'Protected endpoint returned %s: ' "$protected_status" >&2
    cat "$protected_body" >&2
    rm -f "$protected_body"
    exit 1
  fi
  rm -f "$protected_body"
  printf 'health=%s\nprotected_status=%s\napi_url=%s\n' "$health" "$protected_status" "$api_url"
}

case "${1:-}" in
  foundation)
    foundation
    ;;
  image)
    build_image
    ;;
  plan)
    create_plan "${2:-}"
    ;;
  apply)
    apply_plan
    ;;
  smoke)
    smoke_test
    ;;
  *)
    usage
    exit 2
    ;;
esac
