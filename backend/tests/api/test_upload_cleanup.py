from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app


def test_app_startup_cleans_expired_uploads(tmp_path) -> None:
    cleanup = AsyncMock(return_value=2)
    container = SimpleNamespace(upload_service=SimpleNamespace(cleanup_expired=cleanup))

    with TestClient(
        create_app(
            settings=Settings(object_storage_root=tmp_path),
            container=container,
        )
    ):
        pass

    cleanup.assert_awaited_once_with()
