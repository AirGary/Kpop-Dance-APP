from fastapi.testclient import TestClient
import pytest

from api.app.config import Settings
from api.app.main import create_app


def test_cloud_bootstrap_health_is_public(tmp_path):
    settings = Settings(environment="cloud-bootstrap", object_storage_root=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "cloud-bootstrap"}


def test_cloud_bootstrap_rejects_development_identity(tmp_path):
    settings = Settings(environment="cloud-bootstrap", object_storage_root=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer dev-user-a"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_unknown_environment_fails_closed(tmp_path):
    settings = Settings(environment="unknown", object_storage_root=tmp_path)

    with pytest.raises(ValueError, match="Unsupported environment"):
        create_app(settings=settings)


def test_settings_reads_cloud_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENVIRONMENT", "cloud-bootstrap")
    monkeypatch.setenv("OBJECT_STORAGE_ROOT", str(tmp_path))

    settings = Settings.from_environment()

    assert settings.environment == "cloud-bootstrap"
    assert settings.object_storage_root == tmp_path
