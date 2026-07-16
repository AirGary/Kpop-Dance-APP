from pathlib import Path
import os
import subprocess


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "cloud-bootstrap.sh"


def run_sourced_script(command: str, payload: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                "budget_display_name='Stage Lab Dev Monthly Guardrail'; eval \"$(awk "
                "'/^project_budget_is_valid\\(\\)/,/^}/ {print} "
                "/^bucket_configuration_is_valid\\(\\)/,/^}/ {print}' "
                f'\"{SCRIPT}\")\"; {command}'
            ),
        ],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cloud_script_has_guarded_commands():
    source = SCRIPT.read_text()

    assert "stage-lab-dev-gary-202607" in source
    assert "asia-southeast1" in source
    assert "--platform linux/amd64" in source
    assert 'readonly system_git="/usr/bin/git"' in source
    assert "image_summary.digest" in source
    assert "stage5b.tfplan" in source
    assert "stage-lab-dev-gary-202607-source" in source
    assert "stage-lab-dev-gary-202607-results" in source
    assert '$api_url/health"' in source
    assert "/healthz" not in source
    assert "/v1/me" in source
    assert "source_bucket_name" in source
    assert "result_bucket_name" in source
    assert "preflight" in source
    assert source.count("preflight >&2") >= 5
    assert "-auto-approve" not in source


def test_test_environment_cannot_disable_a_direct_deployment_command():
    environment = os.environ.copy()
    environment["STAGE_LAB_SOURCE_ONLY"] = "1"
    result = subprocess.run(
        [str(SCRIPT), "apply"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode != 0


def test_cloud_script_cannot_change_billing_or_start_cloud_builds():
    source = SCRIPT.read_text()

    assert "billing projects link" not in source
    assert "billing budgets update" not in source
    assert "billing budgets list" in source
    assert "gcloud builds" not in source


def test_deployment_requires_primary_state_and_project_scoped_budget():
    source = SCRIPT.read_text()

    assert "terraform.tfstate" in source
    assert "rev-parse --git-dir" in source
    assert "rev-parse --git-common-dir" in source
    assert "Stage Lab Dev Monthly Guardrail" in source
    assert '"projects/$project_number"' in source
    assert "thresholdPercent" in source
    assert "disableDefaultIamRecipients" in source
    assert "projectNumber" in source
    assert "budgetFilter" in source
    assert "status --porcelain=v1 --untracked-files=all" in source


def test_budget_validation_accepts_only_exact_monthly_project_scope():
    valid_budget = """[
      {
        "displayName": "Stage Lab Dev Monthly Guardrail",
        "amount": {"specifiedAmount": {"currencyCode": "JPY", "units": "1000"}},
        "budgetFilter": {
          "calendarPeriod": "MONTH",
          "creditTypesTreatment": "INCLUDE_ALL_CREDITS",
          "projects": ["projects/724772255298"]
        },
        "notificationsRule": {},
        "thresholdRules": [
          {"spendBasis": "CURRENT_SPEND", "thresholdPercent": 0.1},
          {"spendBasis": "CURRENT_SPEND", "thresholdPercent": 0.5},
          {"spendBasis": "CURRENT_SPEND", "thresholdPercent": 0.8},
          {"spendBasis": "CURRENT_SPEND", "thresholdPercent": 1.0}
        ]
      }
    ]"""
    accepted = run_sourced_script(
        'project_budget_is_valid "$(cat)" "724772255298"', valid_budget
    )
    assert accepted.returncode == 0, accepted.stderr

    extra_filter = valid_budget.replace(
        '"projects": ["projects/724772255298"]',
        '"projects": ["projects/724772255298"], "services": ["services/123"]',
    )
    rejected = run_sourced_script(
        'project_budget_is_valid "$(cat)" "724772255298"', extra_filter
    )
    assert rejected.returncode != 0


def test_saved_plan_must_use_image_built_from_current_head():
    source = SCRIPT.read_text()

    assert "verify_image_matches_head" in source
    assert "gcloud artifacts docker images list" in source
    assert "--include-tags" in source
    assert 'terraform_dev show -json "$plan_file"' in source
    assert "planned_image" in source
    assert "verify_saved_plan" in source
    assert 'index("delete")' in source


def test_foundation_requires_a_saved_reviewed_plan_before_apply():
    source = SCRIPT.read_text()

    assert "stage5b-foundation.tfplan" in source
    assert "foundation-plan" in source
    assert "foundation-apply" in source
    assert "terraform_dev apply \\\n    -target=" not in source
    assert 'verify_plan_has_no_deletes "$foundation_plan_file"' in source


def test_smoke_requires_two_identities_and_checks_cloud_boundaries():
    source = SCRIPT.read_text()

    assert "STAGE_LAB_TEST_ID_TOKEN_A" in source
    assert "STAGE_LAB_TEST_ID_TOKEN_B" in source
    assert '"$api_url/v1/jobs"' in source
    assert '"$api_url/v1/jobs/$job_id"' in source
    assert "cross-owner" in source
    assert "gcloud storage buckets describe" in source
    assert "public_access_prevention" in source
    assert "uniform_bucket_level_access" in source
    assert "soft_delete_policy" in source
    assert "lifecycle_config" in source
    assert "trap smoke_cleanup EXIT" in source
    assert source.count("delete_and_verify_smoke_job") >= 3
    assert "Smoke cleanup verification failed" in source
    assert "autoscaling.knative.dev/minScale" in source
    assert "autoscaling.knative.dev/maxScale" in source


def test_bucket_validation_uses_gcloud_storage_output_schema():
    valid_bucket = """{
      "public_access_prevention": "enforced",
      "uniform_bucket_level_access": true,
      "lifecycle_config": {
        "rule": [{"action": {"type": "Delete"}, "condition": {"age": 1}}]
      },
      "soft_delete_policy": {"retentionDurationSeconds": "0"}
    }"""
    accepted = run_sourced_script('bucket_configuration_is_valid "$(cat)" 1', valid_bucket)
    assert accepted.returncode == 0, accepted.stderr

    wrong_age = run_sourced_script('bucket_configuration_is_valid "$(cat)" 7', valid_bucket)
    assert wrong_age.returncode != 0
