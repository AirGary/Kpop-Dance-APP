from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_ROOT = REPOSITORY_ROOT / "infra" / "terraform"


def terraform_source() -> str:
    expected_files = [
        "modules/api/main.tf",
        "modules/api/variables.tf",
        "modules/api/outputs.tf",
        "modules/data/main.tf",
        "modules/data/variables.tf",
        "modules/storage/main.tf",
        "modules/storage/variables.tf",
        "environments/dev/main.tf",
        "environments/dev/variables.tf",
        "environments/dev/outputs.tf",
    ]
    return "\n".join((TERRAFORM_ROOT / path).read_text() for path in expected_files)


def test_dev_infrastructure_is_private_scale_to_zero_and_expiring():
    source = terraform_source()

    assert 'resource "google_cloud_run_v2_service"' in source
    assert "min_instance_count = 0" in source
    assert 'resource "google_artifact_registry_repository"' in source
    assert 'resource "google_firestore_database"' in source
    assert source.count("uniform_bucket_level_access = true") == 2
    assert re.search(r"condition\s*\{\s*age\s*=\s*1\s*\}", source)
    assert re.search(r"condition\s*\{\s*age\s*=\s*7\s*\}", source)


def test_dev_infrastructure_uses_narrow_service_accounts():
    source = terraform_source()

    account_ids = re.findall(r'account_id\s*=\s*"([^"]+)"', source)
    assert set(account_ids) == {
        "stage-lab-api",
        "stage-lab-worker",
        "stage-lab-signer",
    }
    assert "roles/editor" not in source
    assert "roles/owner" not in source
