from fastapi.testclient import TestClient
import pytest

from api.app.config import Settings
from api.app.main import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(object_storage_root=tmp_path)
    with TestClient(create_app(settings=settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-user-a"}
