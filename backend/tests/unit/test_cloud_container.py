from pathlib import Path

import pytest

import api.app.container as container_module
from api.app.config import Settings
from api.app.container import AppContainer


class FakeGateway:
    pass


class FakeDirectStore:
    pass


class FakeResultStore:
    async def delete_job_objects(self, owner_id, job_id) -> None:
        return None


def test_cloud_container_requires_all_resource_settings() -> None:
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        AppContainer.for_settings(Settings(environment="cloud"))


def test_cloud_container_selects_production_adapters(monkeypatch) -> None:
    auth = object()
    gateway = FakeGateway()
    direct_store = FakeDirectStore()
    result_store = FakeResultStore()
    monkeypatch.setattr(container_module, "FirebaseAuthVerifier", lambda _project: auth)
    monkeypatch.setattr(container_module, "GoogleFirestoreGateway", lambda _project: gateway)
    monkeypatch.setattr(
        container_module.GCSUploadObjectStore,
        "from_bucket_name",
        lambda _name: direct_store,
    )
    monkeypatch.setattr(
        container_module.GCSObjectStore,
        "from_bucket_name",
        lambda _name: result_store,
    )
    settings = Settings(
        environment="cloud",
        object_storage_root=Path("/unused"),
        google_cloud_project="stage-lab-project",
        source_bucket_name="stage-lab-source",
        result_bucket_name="stage-lab-result",
    )

    container = AppContainer.for_settings(settings)

    assert container.auth_verifier is auth
    assert container.upload_service._direct_objects is direct_store
    cloud_store = container.job_service._object_store
    assert cloud_store._results is result_store
    assert cloud_store._sources is direct_store
    assert cloud_store._uploads is container.upload_service._repository
