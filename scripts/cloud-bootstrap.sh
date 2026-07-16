#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly backend_root="$repository_root/backend"
readonly terraform_root="$repository_root/infra/terraform/environments/dev"
readonly plan_file="$terraform_root/stage5b.tfplan"
readonly foundation_plan_file="$terraform_root/stage5b-foundation.tfplan"
readonly state_file="$terraform_root/terraform.tfstate"
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
readonly budget_display_name="Stage Lab Dev Monthly Guardrail"

usage() {
  printf '%s\n' "Usage: $0 {preflight|foundation-plan|foundation-apply|image|plan IMAGE_DIGEST_URI|apply|smoke}" >&2
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

require_primary_state() {
  if [[ ! -x "$system_git" ]]; then
    printf 'Required command is unavailable: %s\n' "$system_git" >&2
    exit 1
  fi

  local git_dir git_common branch dirty
  git_dir="$(cd "$repository_root" && "$system_git" rev-parse --git-dir)"
  git_common="$(cd "$repository_root" && "$system_git" rev-parse --git-common-dir)"
  branch="$($system_git -C "$repository_root" branch --show-current)"
  if [[ "$git_dir" != "$git_common" || "$branch" != "main" ]]; then
    printf '%s\n' "Deployment requires the primary checkout on main, not a linked worktree." >&2
    exit 1
  fi
  if [[ ! -f "$state_file" ]]; then
    printf 'Canonical Terraform state is missing: %s\n' "$state_file" >&2
    exit 1
  fi
  dirty="$($system_git -C "$repository_root" status --porcelain=v1 --untracked-files=all)"
  if [[ -n "$dirty" ]]; then
    printf '%s\n' "Deployment requires a clean main checkout with no unreviewed files." >&2
    exit 1
  fi
}

project_budget_is_valid() {
  local budgets="$1" project_number="$2"
  jq -e \
    --arg name "$budget_display_name" \
    --arg project "projects/$project_number" \
    '[.[]
      | select(.displayName == $name)
      | select(.budgetFilter.projects == [$project])
      | select(
          (.budgetFilter | keys | sort)
          == ["calendarPeriod", "creditTypesTreatment", "projects"]
        )
      | select(.budgetFilter.calendarPeriod == "MONTH")
      | select(.budgetFilter.creditTypesTreatment == "INCLUDE_ALL_CREDITS")
      | select(.amount.specifiedAmount.currencyCode == "JPY")
      | select((.amount.specifiedAmount.units | tonumber) == 1000)
      | select((.notificationsRule.disableDefaultIamRecipients // false) == false)
      | select(
          ([.thresholdRules[]
            | select(.spendBasis == "CURRENT_SPEND")
            | .thresholdPercent] | sort) == [0.1, 0.5, 0.8, 1]
        )
    ] | length == 1' <<<"$budgets" >/dev/null
}

verify_project_budget() {
  local billing_account budgets project_number
  billing_account="$(
    gcloud billing projects describe "$project_id" \
      --format='value(billingAccountName)'
  )"
  if [[ ! "$billing_account" =~ ^billingAccounts/(.+)$ ]]; then
    printf '%s\n' "The Stage Lab project has no valid billing account." >&2
    exit 1
  fi

  budgets="$(
    gcloud billing budgets list \
      --billing-account="${BASH_REMATCH[1]}" \
      --format=json
  )"
  project_number="$(
    gcloud projects describe "$project_id" --format='value(projectNumber)'
  )"
  if [[ ! "$project_number" =~ ^[0-9]+$ ]] \
    || ! project_budget_is_valid "$budgets" "$project_number"; then
    printf '%s\n' \
      "Budget must be monthly JPY 1,000, scoped only to the Stage Lab project, with 10/50/80/100%% current-spend alerts." >&2
    exit 1
  fi
}

preflight() {
  require_tools gcloud jq terraform
  require_primary_state
  gcloud projects describe "$project_id" --format='value(projectId)' >/dev/null
  verify_project_budget
  terraform_dev validate >/dev/null
  printf 'preflight=ok\nproject=%s\nstate=%s\n' \
    "$project_id" \
    "$state_file"
}

verify_image_matches_head() {
  local image_uri="$1" digest git_sha metadata
  if [[ "$image_uri" != "$image_base"@sha256:* ]] \
    || [[ ! "${image_uri#"$image_base"@}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    printf '%s\n' "Image must be an immutable digest from the Stage Lab repository." >&2
    exit 1
  fi
  digest="${image_uri##*@}"
  git_sha="$($system_git -C "$repository_root" rev-parse --short=12 HEAD)"
  metadata="$(
    gcloud artifacts docker images list "$image_base" \
      --include-tags \
      --project="$project_id" \
      --format=json
  )"
  if ! jq -e \
    --arg digest "$digest" \
    --arg tag "$git_sha" \
    '[.[] | select(.version == $digest) | .tags[]?] | index($tag) != null' \
    <<<"$metadata" >/dev/null; then
    printf 'Image digest is not tagged for current HEAD %s.\n' "$git_sha" >&2
    exit 1
  fi
}

verify_plan_has_no_deletes() {
  local saved_plan="$1" destructive_changes
  destructive_changes="$(
    terraform_dev show -json "$saved_plan" \
      | jq '[.resource_changes[]?
        | select(.change.actions | index("delete"))] | length'
  )"
  if [[ "$destructive_changes" != "0" ]]; then
    printf 'Saved Terraform plan contains %s destructive change(s).\n' "$destructive_changes" >&2
    exit 1
  fi
}

verify_saved_plan() {
  local planned_image
  verify_plan_has_no_deletes "$plan_file"
  planned_image="$(
    terraform_dev show -json "$plan_file" \
      | jq -r '[.resource_changes[]?
        | select(.address == "module.api.google_cloud_run_v2_service.api")
        | .change.after.template[0].containers[0].image]
        | if length == 1 then .[0] else empty end'
  )"
  if [[ -z "$planned_image" ]]; then
    printf '%s\n' "Saved Terraform plan must contain exactly one Cloud Run API image." >&2
    exit 1
  fi
  verify_image_matches_head "$planned_image"
}

foundation_plan() {
  preflight >&2
  terraform_dev init
  terraform_dev plan \
    -out="$foundation_plan_file" \
    -target='google_project_service.required' \
    -target='google_artifact_registry_repository.api' \
    -var="project_id=$project_id" \
    -var="container_image=$image_base@$bootstrap_digest" \
    -var="source_bucket_name=$source_bucket_name" \
    -var="result_bucket_name=$result_bucket_name"
  verify_plan_has_no_deletes "$foundation_plan_file"
  printf 'Saved foundation plan candidate: %s\n' "$foundation_plan_file"
}

foundation_apply() {
  preflight >&2
  if [[ ! -f "$foundation_plan_file" ]]; then
    printf 'Saved Terraform foundation plan is missing: %s\n' "$foundation_plan_file" >&2
    exit 1
  fi
  verify_plan_has_no_deletes "$foundation_plan_file"
  terraform_dev apply "$foundation_plan_file"
}

build_image() {
  preflight >&2
  require_tools docker
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
  preflight >&2
  local image_uri="${1:-}"
  if [[ ! "$image_uri" =~ @sha256:[0-9a-f]{64}$ ]]; then
    printf '%s\n' "plan requires an immutable Artifact Registry image URI." >&2
    exit 1
  fi
  verify_image_matches_head "$image_uri"

  terraform_dev init
  terraform_dev plan \
    -out="$plan_file" \
    -var="project_id=$project_id" \
    -var="container_image=$image_uri" \
    -var="source_bucket_name=$source_bucket_name" \
    -var="result_bucket_name=$result_bucket_name"
  verify_saved_plan
  printf 'Saved reviewed plan candidate: %s\n' "$plan_file"
}

apply_plan() {
  preflight >&2
  if [[ ! -f "$plan_file" ]]; then
    printf 'Saved Terraform plan is missing: %s\n' "$plan_file" >&2
    exit 1
  fi
  verify_saved_plan
  terraform_dev apply "$plan_file"
}

bucket_configuration_is_valid() {
  local description="$1" expected_age="$2"
  jq -e \
    --argjson age "$expected_age" \
    '.public_access_prevention == "enforced"
      and .uniform_bucket_level_access == true
      and any(.lifecycle_config.rule[]?;
        .action.type == "Delete" and .condition.age == $age)
      and (.soft_delete_policy.retentionDurationSeconds | tonumber) == 0' \
    <<<"$description" >/dev/null
}

verify_bucket() {
  local bucket="$1" expected_age="$2" description
  description="$(
    gcloud storage buckets describe "gs://$bucket" \
      --project="$project_id" \
      --format=json
  )"
  if ! bucket_configuration_is_valid "$description" "$expected_age"; then
    printf 'Bucket security or lifecycle verification failed: %s\n' "$bucket" >&2
    exit 1
  fi
}

smoke_temp_dir=""
smoke_api_url=""
smoke_job_id=""
smoke_token_a=""

delete_and_verify_smoke_job() {
  local delete_status get_status
  delete_status="$(
    curl --silent --show-error \
      --output /dev/null \
      --write-out '%{http_code}' \
      --request DELETE \
      --header "Authorization: Bearer $smoke_token_a" \
      "$smoke_api_url/v1/jobs/$smoke_job_id"
  )"
  if [[ "$delete_status" != "204" && "$delete_status" != "404" ]]; then
    return 1
  fi
  get_status="$(
    curl --silent --show-error \
      --output /dev/null \
      --write-out '%{http_code}' \
      --header "Authorization: Bearer $smoke_token_a" \
      "$smoke_api_url/v1/jobs/$smoke_job_id"
  )"
  [[ "$get_status" == "404" ]]
}

smoke_cleanup() {
  local original_status="$?"
  trap - EXIT
  set +e
  if [[ -n "$smoke_job_id" && -n "$smoke_api_url" && -n "$smoke_token_a" ]]; then
    if ! delete_and_verify_smoke_job; then
      printf '%s\n' "Smoke cleanup verification failed during failure handling." >&2
    fi
  fi
  if [[ -n "$smoke_temp_dir" ]]; then
    rm -rf "$smoke_temp_dir"
  fi
  exit "$original_status"
}

smoke_test() {
  preflight >&2
  require_tools curl uuidgen
  local api_url health protected_body protected_status token_a token_b
  local temp_dir status uid_a uid_b job_id project_uuid idempotency_key run_service
  token_a="${STAGE_LAB_TEST_ID_TOKEN_A:-}"
  token_b="${STAGE_LAB_TEST_ID_TOKEN_B:-}"
  if [[ -z "$token_a" || -z "$token_b" ]]; then
    printf '%s\n' "Smoke requires STAGE_LAB_TEST_ID_TOKEN_A and STAGE_LAB_TEST_ID_TOKEN_B." >&2
    exit 1
  fi

  api_url="$(terraform_dev output -raw api_url)"
  smoke_api_url="$api_url"
  smoke_token_a="$token_a"
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

  temp_dir="$(mktemp -d)"
  smoke_temp_dir="$temp_dir"
  trap smoke_cleanup EXIT
  status="$(
    curl --silent --show-error \
      --output "$temp_dir/me-a.json" \
      --write-out '%{http_code}' \
      --header "Authorization: Bearer $token_a" \
      "$api_url/v1/me"
  )"
  [[ "$status" == "200" ]] || { printf 'Identity A failed: %s\n' "$status" >&2; exit 1; }
  status="$(
    curl --silent --show-error \
      --output "$temp_dir/me-b.json" \
      --write-out '%{http_code}' \
      --header "Authorization: Bearer $token_b" \
      "$api_url/v1/me"
  )"
  [[ "$status" == "200" ]] || { printf 'Identity B failed: %s\n' "$status" >&2; exit 1; }
  uid_a="$(jq -r '.userId // empty' "$temp_dir/me-a.json")"
  uid_b="$(jq -r '.userId // empty' "$temp_dir/me-b.json")"
  if [[ -z "$uid_a" || -z "$uid_b" || "$uid_a" == "$uid_b" ]]; then
    printf '%s\n' "Smoke identities must resolve to two different Firebase users." >&2
    exit 1
  fi

  project_uuid="$(uuidgen | tr '[:upper:]' '[:lower:]')"
  idempotency_key="smoke-$(date +%s)-$RANDOM"
  jq -n \
    --arg project "$project_uuid" \
    '{projectId:$project,sourceFingerprint:"sha256:smoke",durationSeconds:1,byteCount:1,mimeType:"video/mp4"}' \
    >"$temp_dir/job-request.json"
  status="$(
    curl --silent --show-error \
      --output "$temp_dir/job.json" \
      --write-out '%{http_code}' \
      --request POST \
      --header "Authorization: Bearer $token_a" \
      --header "Idempotency-Key: $idempotency_key" \
      --header 'Content-Type: application/json' \
      --data-binary "@$temp_dir/job-request.json" \
      "$api_url/v1/jobs"
  )"
  [[ "$status" == "201" ]] || { printf 'Smoke job creation failed: %s\n' "$status" >&2; exit 1; }
  job_id="$(jq -r '.id // empty' "$temp_dir/job.json")"
  [[ -n "$job_id" ]] || { printf '%s\n' "Smoke job response has no ID." >&2; exit 1; }
  smoke_job_id="$job_id"

  status="$(
    curl --silent --show-error \
      --output "$temp_dir/cross-owner.json" \
      --write-out '%{http_code}' \
      --header "Authorization: Bearer $token_b" \
      "$api_url/v1/jobs/$job_id"
  )"
  if [[ "$status" != "404" ]]; then
    printf 'cross-owner isolation failed: %s\n' "$status" >&2
    exit 1
  fi
  if ! delete_and_verify_smoke_job; then
    printf '%s\n' "Smoke cleanup verification failed." >&2
    exit 1
  fi
  smoke_job_id=""

  verify_bucket "$source_bucket_name" 1
  verify_bucket "$result_bucket_name" 7
  run_service="$(
    gcloud run services describe stage-lab-api \
      --project="$project_id" \
      --region="$region" \
      --format=json
  )"
  if ! jq -e \
    '.spec.template.metadata.annotations["autoscaling.knative.dev/minScale"] == "0"
      and .spec.template.metadata.annotations["autoscaling.knative.dev/maxScale"] == "1"
      and .spec.template.spec.containers[0].resources.limits.cpu == "1"
      and .spec.template.spec.containers[0].resources.limits.memory == "512Mi"
      and any(.spec.template.spec.containers[0].env[]?;
        .name == "APP_ENVIRONMENT" and .value == "cloud")' \
    <<<"$run_service" >/dev/null; then
    printf '%s\n' "Cloud Run cost controls or cloud environment verification failed." >&2
    exit 1
  fi
  rm -rf "$temp_dir"
  smoke_temp_dir=""
  trap - EXIT
  printf 'health=%s\nprotected_status=%s\nidentity_isolation=ok\nbuckets=private\napi_url=%s\n' \
    "$health" \
    "$protected_status" \
    "$api_url"
}

case "${1:-}" in
  preflight)
    preflight
    ;;
  foundation-plan)
    foundation_plan
    ;;
  foundation-apply)
    foundation_apply
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
