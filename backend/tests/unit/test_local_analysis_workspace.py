from uuid import UUID

import pytest

from api.app.adapters.storage.local_analysis_workspace import (
    LocalAnalysisWorkspace,
    UnsafeAnalysisWorkspacePathError,
)


JOB_ID = UUID("377a305d-9e09-45ba-ad1b-bbe7c6489f3f")


@pytest.mark.asyncio
async def test_workspace_promotes_upload_by_hard_link_without_changing_source(tmp_path) -> None:
    source = tmp_path / "uploads" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"original video bytes")
    before = source.read_bytes()
    workspace = LocalAnalysisWorkspace(tmp_path / "objects")

    destination = await workspace.promote_upload("owner-a", JOB_ID, source)

    assert destination == tmp_path / "objects" / "owner-a" / str(JOB_ID) / "source.mp4"
    assert destination.read_bytes() == before
    assert source.read_bytes() == before
    assert destination.stat().st_ino == source.stat().st_ino


@pytest.mark.asyncio
async def test_workspace_copies_when_hard_link_is_unavailable(tmp_path, monkeypatch) -> None:
    source = tmp_path / "uploads" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"original video bytes")
    workspace = LocalAnalysisWorkspace(tmp_path / "objects")

    def unavailable_link(*_args, **_kwargs) -> None:
        raise OSError("cross-device link")

    monkeypatch.setattr(
        "api.app.adapters.storage.local_analysis_workspace.os.link",
        unavailable_link,
    )
    destination = await workspace.promote_upload("owner-a", JOB_ID, source)

    assert destination.read_bytes() == source.read_bytes() == b"original video bytes"
    assert destination.stat().st_ino != source.stat().st_ino


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
