from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_ROOT = REPOSITORY_ROOT / "infra" / "terraform"


def terraform_source(*paths: str) -> str:
    return "\n".join((TERRAFORM_ROOT / path).read_text() for path in paths)


def test_stage_5a_environment_enables_only_bootstrap_modules():
    source = terraform_source(
        "environments/dev/main.tf",
        "environments/dev/variables.tf",
        "environments/dev/outputs.tf",
    )

    assert '"artifactregistry.googleapis.com"' in source
    assert '"iam.googleapis.com"' in source
    assert '"run.googleapis.com"' in source
    assert 'source = "../../modules/data"' not in source
    assert 'source = "../../modules/storage"' not in source
    assert "source_bucket_name" not in source
    assert "result_bucket_name" not in source


def test_cloud_run_is_public_scale_to_zero_and_bounded():
    source = terraform_source(
        "modules/api/main.tf",
        "modules/api/variables.tf",
        "modules/api/outputs.tf",
    )

    assert "min_instance_count = 0" in source
    assert "max_instance_count = 1" in source
    assert 'cpu    = "1"' in source
    assert 'memory = "512Mi"' in source
    assert 'name  = "APP_ENVIRONMENT"' in source
    assert 'value = "cloud-bootstrap"' in source
    assert 'path = "/health"' in source
    assert "/healthz" not in source
    assert 'resource "google_cloud_run_service_iam_member" "public"' in source
    assert 'role     = "roles/run.invoker"' in source
    assert 'member   = "allUsers"' in source
    assert re.search(r'timeout\s*=\s*"30s"', source)
    assert "cpu_idle          = true" in source
    assert "startup_cpu_boost = false" in source


def test_artifact_registry_deletes_old_untagged_images():
    source = terraform_source("modules/api/main.tf")

    assert 'tag_state  = "UNTAGGED"' in source
    assert 'older_than = "604800s"' in source


def test_stage_5a_uses_one_narrow_runtime_service_account():
    source = terraform_source(
        "environments/dev/main.tf",
        "modules/api/main.tf",
    )

    assert source.count('account_id   = "stage-lab-api"') == 1
    assert "roles/editor" not in source
    assert "roles/owner" not in source
    assert "gpu" not in source.lower()
