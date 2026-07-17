import asyncio
import errno
import os
from threading import Event
from pathlib import Path
from uuid import UUID

import pytest

from api.app.adapters.storage.local_analysis_workspace import (
    LocalAnalysisWorkspace,
    UnsafeAnalysisWorkspacePathError,
)


JOB_ID = UUID("377a305d-9e09-45ba-ad1b-bbe7c6489f3f")
UPLOAD_ID = UUID("d987817a-ca47-4f19-9c17-2b8717f518a8")


@pytest.mark.asyncio
async def test_workspace_promotes_upload_by_hard_link_without_changing_source(tmp_path) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original video bytes")
    before = source.read_bytes()
    workspace = LocalAnalysisWorkspace(root)

    destination = await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID)

    assert destination == root / "owner-a" / str(JOB_ID) / "source.mp4"
    assert destination.read_bytes() == before
    assert source.read_bytes() == before
    assert destination.stat().st_ino == source.stat().st_ino


@pytest.mark.asyncio
async def test_workspace_copies_when_hard_link_is_unavailable(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original video bytes")
    workspace = LocalAnalysisWorkspace(root)
    fsync_calls: list[int] = []
    real_fsync = os.fsync
    real_link = os.link

    def unavailable_link(link_source: Path, target: Path) -> None:
        if Path(link_source) == source:
            raise OSError("cross-device link")
        real_link(link_source, target)

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unavailable_link,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.fsync",
        lambda descriptor: (fsync_calls.append(descriptor), real_fsync(descriptor))[1],
    )
    destination = await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID)

    assert destination.read_bytes() == source.read_bytes() == b"original video bytes"
    assert destination.stat().st_ino != source.stat().st_ino
    assert fsync_calls


@pytest.mark.asyncio
async def test_workspace_copies_when_filesystem_does_not_support_any_hard_links(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original video bytes")
    workspace = LocalAnalysisWorkspace(root)

    def unsupported_link(*_args, **_kwargs) -> None:
        raise OSError(errno.EOPNOTSUPP, "hard links are not supported")

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unsupported_link,
    )

    destination = await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID)

    assert destination.read_bytes() == source.read_bytes() == b"original video bytes"
    assert destination.stat().st_ino != source.stat().st_ino
    assert list(destination.parent.glob(".source.mp4.*.tmp")) == []


@pytest.mark.asyncio
async def test_workspace_instances_serialize_fallback_before_destination_is_visible(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original video bytes")
    first = LocalAnalysisWorkspace(root)
    second = LocalAnalysisWorkspace(root)
    destination = root / "owner-a" / str(JOB_ID) / "source.mp4"
    staging_started = Event()
    release_staging = Event()
    partial_destination = Event()
    release_destination = Event()
    copy_calls = 0
    destination_descriptors: set[int] = set()
    real_copyfileobj = __import__("shutil").copyfileobj
    real_open = os.open
    real_fdopen = os.fdopen

    def unsupported_link(*_args, **_kwargs) -> None:
        raise OSError(errno.EOPNOTSUPP, "hard links are not supported")

    def staged_copy(input_handle, output_handle, *args, **kwargs) -> None:
        nonlocal copy_calls
        copy_calls += 1
        if copy_calls != 1:
            return real_copyfileobj(input_handle, output_handle, *args, **kwargs)
        content = input_handle.read()
        output_handle.write(content[:1])
        output_handle.flush()
        staging_started.set()
        assert release_staging.wait(timeout=5)
        output_handle.write(content[1:])

    def tracked_open(path: Path, flags: int, mode: int = 0o777) -> int:
        descriptor = real_open(path, flags, mode)
        if Path(path) == destination:
            destination_descriptors.add(descriptor)
        return descriptor

    class PartialDestinationWriter:
        def __init__(self, handle) -> None:
            self._handle = handle
            self._partial_written = False

        def write(self, content: bytes) -> int:
            if self._partial_written:
                return self._handle.write(content)
            self._partial_written = True
            count = self._handle.write(content[:1])
            self._handle.flush()
            partial_destination.set()
            assert release_destination.wait(timeout=5)
            return count + self._handle.write(content[1:])

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args) -> None:
            self._handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self._handle, name)

    def tracked_fdopen(descriptor: int, *args, **kwargs):
        handle = real_fdopen(descriptor, *args, **kwargs)
        if descriptor in destination_descriptors:
            return PartialDestinationWriter(handle)
        return handle

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unsupported_link,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.shutil.copyfileobj",
        staged_copy,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.open",
        tracked_open,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.fdopen",
        tracked_fdopen,
    )

    first_task = asyncio.create_task(first.promote_upload("owner-a", JOB_ID, UPLOAD_ID))
    second_task = None
    try:
        assert await asyncio.to_thread(staging_started.wait, 2)
        second_task = asyncio.create_task(
            second.promote_upload("owner-a", JOB_ID, UPLOAD_ID)
        )

        assert not await asyncio.to_thread(partial_destination.wait, 0.2)
        assert not destination.exists()
        assert not second_task.done()
    finally:
        release_staging.set()
        release_destination.set()
        tasks = [first_task]
        if second_task is not None:
            tasks.append(second_task)
        results = await asyncio.gather(*tasks)

    assert results[0] == results[-1] == destination
    assert destination.read_bytes() == source.read_bytes()


@pytest.mark.asyncio
async def test_workspace_keeps_existing_destination_when_hard_link_races(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"upload source")
    workspace = LocalAnalysisWorkspace(root)
    destination = root / "owner-a" / str(JOB_ID) / "source.mp4"

    def competing_link(_source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"first publisher")
        raise FileExistsError

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        competing_link,
    )

    assert await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID) == destination
    assert destination.read_bytes() == b"first publisher"
    assert source.read_bytes() == b"upload source"


@pytest.mark.asyncio
async def test_workspace_copy_fallback_fsyncs_parent_and_cleans_temp(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"upload source")
    workspace = LocalAnalysisWorkspace(root)
    destination = root / "owner-a" / str(JOB_ID) / "source.mp4"
    parent = destination.parent
    real_open = os.open
    real_fsync = os.fsync
    opened: list[tuple[Path, int, int]] = []
    fsynced: list[int] = []

    def unavailable_link(*_args, **_kwargs) -> None:
        raise OSError("cross-device link")

    def tracked_open(path: Path, flags: int, mode: int = 0o777) -> int:
        descriptor = real_open(path, flags, mode)
        opened.append((Path(path), flags, descriptor))
        return descriptor

    def tracked_fsync(descriptor: int) -> None:
        fsynced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unavailable_link,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.open",
        tracked_open,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.fsync",
        tracked_fsync,
    )

    assert await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID) == destination
    assert destination.read_bytes() == b"upload source"
    assert source.read_bytes() == b"upload source"
    assert list(destination.parent.glob(".source.mp4.*.tmp")) == []
    directory_descriptors = [
        descriptor
        for path, flags, descriptor in opened
        if path == parent and flags & os.O_DIRECTORY
    ]
    assert directory_descriptors[0] in fsynced


def test_workspace_rejects_owner_path_traversal(tmp_path) -> None:
    workspace = LocalAnalysisWorkspace(tmp_path / "objects")

    with pytest.raises(UnsafeAnalysisWorkspacePathError):
        workspace.analysis_directory("../owner-b", JOB_ID)


def test_workspace_keeps_analysis_artifacts_below_the_owner_job_directory(tmp_path) -> None:
    workspace = LocalAnalysisWorkspace(tmp_path / "objects")
    analysis = tmp_path / "objects" / "owner-a" / str(JOB_ID) / "analysis"

    assert workspace.analysis_directory("owner-a", JOB_ID) == analysis
    assert workspace.proxy_path("owner-a", JOB_ID) == analysis / "proxy.mp4"
    assert workspace.checkpoints_directory("owner-a", JOB_ID) == analysis / "checkpoints"
    assert workspace.result_path("owner-a", JOB_ID) == analysis / "result.json"
