import hashlib
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from api.app.adapters.storage.local_upload_object_store import LocalUploadObjectStore
from api.app.ports.upload_object_store import (
    UnsafeUploadPathError,
    UploadObjectOffsetError,
)


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@pytest.mark.anyio
async def test_append_compare_hash_and_delete(tmp_path) -> None:
    store = LocalUploadObjectStore(tmp_path)
    upload_id = uuid4()

    offset = await store.append("owner-a", upload_id, 0, chunks(b"abc", b"def"))

    assert offset == 6
    assert await store.size("owner-a", upload_id) == 6
    assert await store.matches("owner-a", upload_id, 3, chunks(b"d", b"ef")) is True
    assert await store.matches("owner-a", upload_id, 3, chunks(b"deg")) is False
    assert await store.sha256("owner-a", upload_id) == hashlib.sha256(b"abcdef").hexdigest()

    await store.delete("owner-a", upload_id)

    assert await store.size("owner-a", upload_id) == 0


@pytest.mark.anyio
async def test_append_requires_actual_file_offset(tmp_path) -> None:
    store = LocalUploadObjectStore(tmp_path)
    upload_id = uuid4()
    await store.append("owner-a", upload_id, 0, chunks(b"abc"))

    with pytest.raises(UploadObjectOffsetError) as error:
        await store.append("owner-a", upload_id, 0, chunks(b"def"))

    assert error.value.actual_offset == 3
    assert await store.size("owner-a", upload_id) == 3


@pytest.mark.anyio
async def test_append_consumes_stream_incrementally(tmp_path) -> None:
    store = LocalUploadObjectStore(tmp_path)
    upload_id = uuid4()
    observations: list[int] = []

    async def observed_chunks() -> AsyncIterator[bytes]:
        yield b"abc"
        observations.append(await store.size("owner-a", upload_id))
        yield b"def"

    await store.append("owner-a", upload_id, 0, observed_chunks())

    assert observations == [3]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "owner_id",
    ["../foreign", "owner/foreign", "owner\\foreign", ".", ""],
)
async def test_owner_component_rejects_unsafe_paths(tmp_path, owner_id: str) -> None:
    store = LocalUploadObjectStore(tmp_path)

    with pytest.raises(UnsafeUploadPathError):
        await store.size(owner_id, uuid4())


@pytest.mark.anyio
async def test_delete_is_idempotent_and_removes_empty_directories(tmp_path) -> None:
    store = LocalUploadObjectStore(tmp_path)
    upload_id = uuid4()
    await store.append("owner-a", upload_id, 0, chunks(b"abc"))

    await store.delete("owner-a", upload_id)
    await store.delete("owner-a", upload_id)

    assert not (tmp_path / "owner-a" / "uploads" / str(upload_id)).exists()
