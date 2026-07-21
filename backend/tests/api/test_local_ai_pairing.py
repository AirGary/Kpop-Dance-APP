from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app


def test_local_ai_requires_pairing_header(tmp_path):
    settings = Settings(
        environment="local-ai",
        object_storage_root=tmp_path,
        local_ai_model_root=tmp_path / "models",
        pairing_token="temporary-pairing-token",
    )

    with TestClient(create_app(settings=settings)) as client:
        missing = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer dev-user-a"},
        )
        valid = client.get(
            "/v1/me",
            headers={
                "Authorization": "Bearer dev-user-a",
                "X-Stage-Lab-Pairing-Token": "temporary-pairing-token",
            },
        )

    assert missing.status_code == 401
    assert valid.status_code == 200


def test_development_does_not_require_pairing_header(tmp_path):
    settings = Settings(environment="development", object_storage_root=tmp_path)

    with TestClient(create_app(settings=settings)) as client:
        response = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer dev-user-a"},
        )

    assert response.status_code == 200
