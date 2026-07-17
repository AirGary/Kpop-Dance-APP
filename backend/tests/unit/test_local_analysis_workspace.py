import errno
import os
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
async def test_workspace_copy_race_preserves_first_publisher_and_cleans_temp(tmp_path, monkeypatch) -> None:
    root = tmp_path / "objects"
    source = root / "owner-a" / "uploads" / str(UPLOAD_ID) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"upload source")
    workspace = LocalAnalysisWorkspace(root)
    destination = root / "owner-a" / str(JOB_ID) / "source.mp4"
    real_open = os.open

    def unavailable_link(*_args, **_kwargs) -> None:
        raise OSError("cross-device link")

    def competing_open(path: Path, flags: int, mode: int = 0o777) -> int:
        if Path(path) == destination and flags & os.O_EXCL:
            destination.write_bytes(b"first publisher")
            raise FileExistsError
        return real_open(path, flags, mode)

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unavailable_link,
    )
    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.open",
        competing_open,
    )

    assert await workspace.promote_upload("owner-a", JOB_ID, UPLOAD_ID) == destination
    assert destination.read_bytes() == b"first publisher"
    assert source.read_bytes() == b"upload source"
    assert list(destination.parent.glob(".source.mp4.*.tmp")) == []


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
