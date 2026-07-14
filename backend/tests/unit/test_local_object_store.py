from uuid import uuid4

import pytest

from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.ports.object_store import UnsafeObjectPathError


@pytest.mark.parametrize("component", ["", ".", "..", "/tmp/outside", "a/b"])
@pytest.mark.asyncio
async def test_invalid_owner_components_are_rejected(tmp_path, component):
    store = LocalObjectStore(tmp_path)

    with pytest.raises(UnsafeObjectPathError):
        await store.delete_job_objects(component, uuid4())


@pytest.mark.asyncio
async def test_job_directory_is_deleted_inside_root(tmp_path):
    store = LocalObjectStore(tmp_path)
    job_id = uuid4()
    job_directory = tmp_path / "dev-user-a" / str(job_id)
    job_directory.mkdir(parents=True)
    (job_directory / "source.mp4").write_bytes(b"video")

    await store.delete_job_objects("dev-user-a", job_id)

    assert not job_directory.exists()
    assert tmp_path.exists()


@pytest.mark.asyncio
async def test_missing_job_directory_is_a_success(tmp_path):
    store = LocalObjectStore(tmp_path)

    await store.delete_job_objects("dev-user-a", uuid4())
