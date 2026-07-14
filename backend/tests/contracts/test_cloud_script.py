from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "cloud-bootstrap.sh"


def test_cloud_script_has_guarded_commands():
    source = SCRIPT.read_text()

    assert "stage-lab-dev-gary-202607" in source
    assert "asia-southeast1" in source
    assert "--platform linux/amd64" in source
    assert "image_summary.digest" in source
    assert "stage5a.tfplan" in source
    assert "/healthz" in source
    assert "/v1/me" in source
    assert "-auto-approve" not in source


def test_cloud_script_cannot_change_billing_or_start_cloud_builds():
    source = SCRIPT.read_text()

    assert "billing projects link" not in source
    assert "billing budgets" not in source
    assert "gcloud builds" not in source
    assert "firebase" not in source.lower()
