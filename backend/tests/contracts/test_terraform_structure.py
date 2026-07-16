from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_ROOT = REPOSITORY_ROOT / "infra" / "terraform"


def terraform_source(*paths: str) -> str:
    return "\n".join((TERRAFORM_ROOT / path).read_text() for path in paths)


def test_stage_5b_environment_enables_private_data_modules():
    source = terraform_source(
        "environments/dev/main.tf",
        "environments/dev/variables.tf",
        "environments/dev/outputs.tf",
    )

    assert '"artifactregistry.googleapis.com"' in source
    assert '"firestore.googleapis.com"' in source
    assert '"iam.googleapis.com"' in source
    assert '"run.googleapis.com"' in source
    assert '"storage.googleapis.com"' in source
    assert 'source = "../../modules/data"' in source
    assert 'source = "../../modules/storage"' in source
    assert "source_bucket_name" in source
    assert "result_bucket_name" in source


def test_storage_is_private_and_expires_temporary_objects():
    source = terraform_source(
        "modules/storage/main.tf",
        "modules/storage/variables.tf",
    )

    assert source.count("uniform_bucket_level_access = true") == 2
    assert source.count('public_access_prevention    = "enforced"') == 2
    assert source.count("retention_duration_seconds = 0") == 2
    assert "force_destroy               = false" in source
    assert "age = 1" in source
    assert "age = 7" in source
    assert "roles/storage.objectUser" in source
    assert "allUsers" not in source
    assert "allAuthenticatedUsers" not in source


def test_firestore_is_native_and_api_access_is_least_privilege():
    source = terraform_source(
        "modules/data/main.tf",
        "modules/data/variables.tf",
    )

    assert 'type                        = "FIRESTORE_NATIVE"' in source
    assert 'deletion_policy             = "ABANDON"' in source
    assert 'resource "google_firebase_project" "default"' in source
    assert 'resource "google_firestore_field" "upload_expiration"' in source
    assert 'field      = "ttlExpiresAt"' in source
    assert 'field      = "expiresAt"' not in source
    assert "ttl_config {}" in source
    assert "roles/datastore.user" in source
    assert "roles/editor" not in source
    assert "roles/owner" not in source


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
    assert 'value = "cloud"' in source
    assert 'path = "/health"' in source
    assert "/healthz" not in source
    assert 'resource "google_cloud_run_service_iam_member" "public"' in source
    assert 'role     = "roles/run.invoker"' in source
    assert 'member   = "allUsers"' in source
    assert re.search(r'timeout\s*=\s*"30s"', source)
    assert "cpu_idle          = true" in source
    assert "startup_cpu_boost = false" in source
    assert "ignore_changes = [scaling]" in source


def test_artifact_registry_bounds_tagged_and_untagged_image_retention():
    source = terraform_source("environments/dev/main.tf")

    assert 'tag_state  = "ANY"' in source
    assert 'older_than = "604800s"' in source
    assert 'action = "KEEP"' in source
    assert "keep_count = 5" in source


def test_stage_5b_uses_one_narrow_runtime_service_account_and_no_gpu():
    source = terraform_source(
        "environments/dev/main.tf",
        "modules/api/main.tf",
    )

    assert source.count('account_id   = "stage-lab-api"') == 1
    assert 'value = "cloud"' in source
    assert 'name  = "SOURCE_BUCKET_NAME"' in source
    assert 'name  = "RESULT_BUCKET_NAME"' in source
    assert 'name  = "GOOGLE_CLOUD_PROJECT"' in source
    assert "roles/editor" not in source
    assert "roles/owner" not in source
    assert "gpu" not in source.lower()


def test_cloud_run_waits_for_private_data_and_runtime_iam():
    source = terraform_source(
        "environments/dev/main.tf",
        "modules/api/main.tf",
        "modules/api/variables.tf",
    )

    assert 'resource "google_service_account" "api"' in source
    assert "api_service_account_email = google_service_account.api.email" in source
    assert re.search(
        r'module "api".*?depends_on\s*=\s*\[module\.storage, module\.data\]',
        source,
        re.DOTALL,
    )
    assert re.search(
        r"service_account\s*=\s*var\.api_service_account_email",
        source,
    )


def test_refactored_foundation_resources_keep_their_terraform_identity():
    source = terraform_source("environments/dev/main.tf")

    assert "from = module.api.google_artifact_registry_repository.api" in source
    assert "to   = google_artifact_registry_repository.api" in source
    assert "from = module.api.google_service_account.api" in source
    assert "to   = google_service_account.api" in source
