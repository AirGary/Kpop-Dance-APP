import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest

from api.app.adapters.repositories.file_analysis_repository import (
    AnalysisNotFoundError,
    FileAnalysisRepository,
    UnsafeAnalysisPathError,
)
from api.app.adapters.repositories.in_memory_job_repository import InMemoryJobRepository
from api.app.ports.job_repository import JobRecord, JobStateConflictError
from api.app.schemas.analysis import (
    AnalysisJobState,
    AnalysisResultResponse,
    DancerCandidateResponse,
)
from api.app.schemas.jobs import JobResponse


JOB_ID = UUID("377a305d-9e09-45ba-ad1b-bbe7c6489f3f")


def analysis_response(state: AnalysisJobState = AnalysisJobState.UPLOADED) -> JobResponse:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    return JobResponse(
        id=JOB_ID,
        projectId=UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430"),
        state=state,
        createdAt=now,
        updatedAt=now,
    )


def candidate() -> DancerCandidateResponse:
    return DancerCandidateResponse.model_validate(
        {
            "candidateId": "candidate-1",
            "representativeImagePaths": [
                "analysis/candidates/candidate-1-1.jpg",
                "analysis/candidates/candidate-1-2.jpg",
                "analysis/candidates/candidate-1-3.jpg",
            ],
            "appearanceIntervals": [{"startSeconds": 1.5, "endSeconds": 4.0}],
            "boxSummary": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            "confidence": 0.91,
        }
    )


@pytest.mark.asyncio
async def test_file_repository_persists_state_with_atomic_replace(tmp_path, monkeypatch) -> None:
    repository = FileAnalysisRepository(tmp_path)
    replaces: list[tuple[Path, Path]] = []
    real_replace = __import__("os").replace

    def record_replace(source: Path, destination: Path) -> None:
        replaces.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(
        "api.app.adapters.repositories.file_analysis_repository.os.replace",
        record_replace,
    )

    stored = await repository.update("owner-a", JOB_ID, analysis_response())

    assert stored.state is AnalysisJobState.UPLOADED
    assert len(replaces) == 1
    temporary, destination = replaces[0]
    assert temporary.parent == tmp_path / "owner-a" / str(JOB_ID) / "analysis"
    assert temporary.name.startswith(".analysis-state.json.")
    assert temporary.name.endswith(".tmp")
    assert destination == tmp_path / "owner-a" / str(JOB_ID) / "analysis" / "analysis-state.json"
    assert not replaces[0][0].exists()


@pytest.mark.asyncio
async def test_file_repository_uses_unique_temps_for_concurrent_writes_and_keeps_valid_json(tmp_path, monkeypatch) -> None:
    repository = FileAnalysisRepository(tmp_path)
    replaces: list[Path] = []
    barrier = Barrier(2)
    real_replace = os.replace

    def synchronized_replace(source: Path, destination: Path) -> None:
        replaces.append(source)
        barrier.wait(timeout=5)
        real_replace(source, destination)

    monkeypatch.setattr(
        "api.app.adapters.repositories.file_analysis_repository.os.replace",
        synchronized_replace,
    )

    await asyncio.gather(
        repository.update("owner-a", JOB_ID, analysis_response(AnalysisJobState.UPLOADED)),
        repository.update("owner-a", JOB_ID, analysis_response(AnalysisJobState.DETECTING)),
    )

    assert len(set(replaces)) == 2
    payload = json.loads(
        (tmp_path / "owner-a" / str(JOB_ID) / "analysis" / "analysis-state.json").read_text()
    )
    assert payload["state"] in {"uploaded", "detecting"}


@pytest.mark.asyncio
async def test_file_repository_fsyncs_parent_directory_after_replace(tmp_path, monkeypatch) -> None:
    repository = FileAnalysisRepository(tmp_path)
    opened: list[tuple[Path, int, int]] = []
    fsynced: list[int] = []
    real_open = os.open
    real_fsync = os.fsync

    def record_open(path: Path, flags: int, mode: int = 0o777) -> int:
        descriptor = real_open(path, flags, mode)
        opened.append((Path(path), flags, descriptor))
        return descriptor

    def record_fsync(descriptor: int) -> None:
        fsynced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(
        "api.app.adapters.repositories.file_analysis_repository.os.open",
        record_open,
    )
    monkeypatch.setattr(
        "api.app.adapters.repositories.file_analysis_repository.os.fsync",
        record_fsync,
    )

    await repository.update("owner-a", JOB_ID, analysis_response())

    parent = tmp_path / "owner-a" / str(JOB_ID) / "analysis"
    directory_descriptors = [
        descriptor
        for path, flags, descriptor in opened
        if path == parent and flags & os.O_DIRECTORY
    ]
    assert directory_descriptors
    assert directory_descriptors[0] in fsynced


@pytest.mark.asyncio
async def test_file_repository_removes_unique_temp_when_replace_fails(tmp_path, monkeypatch) -> None:
    repository = FileAnalysisRepository(tmp_path)

    monkeypatch.setattr(
        "api.app.adapters.repositories.file_analysis_repository.os.replace",
        lambda _source, _destination: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        await repository.update("owner-a", JOB_ID, analysis_response())

    directory = tmp_path / "owner-a" / str(JOB_ID) / "analysis"
    assert list(directory.glob(".analysis-state.json.*.tmp")) == []


@pytest.mark.asyncio
async def test_file_repository_recovers_state_and_related_data_after_restart(tmp_path) -> None:
    first = FileAnalysisRepository(tmp_path)
    await first.update("owner-a", JOB_ID, analysis_response(AnalysisJobState.DETECTING))
    await first.set_candidates("owner-a", JOB_ID, [candidate()])
    result = AnalysisResultResponse.model_validate(
        {
            "schemaVersion": 1,
            "sha256": "a" * 64,
            "byteCount": 2048,
            "contentPath": "analysis/result.json",
        }
    )
    await first.set_result("owner-a", JOB_ID, result)

    second = FileAnalysisRepository(tmp_path)

    assert (await second.load("owner-a", JOB_ID)).state is AnalysisJobState.DETECTING
    assert await second.candidates("owner-a", JOB_ID) == [candidate()]
    assert await second.result("owner-a", JOB_ID) == result


@pytest.mark.asyncio
async def test_file_repository_hides_foreign_and_missing_jobs_with_one_error(tmp_path) -> None:
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, analysis_response())

    with pytest.raises(AnalysisNotFoundError) as foreign:
        await repository.load("owner-b", JOB_ID)
    with pytest.raises(AnalysisNotFoundError) as missing:
        await repository.load("owner-a", UUID("00000000-0000-0000-0000-000000000000"))

    assert type(foreign.value) is type(missing.value)


@pytest.mark.asyncio
async def test_file_repository_rejects_owner_path_traversal(tmp_path) -> None:
    repository = FileAnalysisRepository(tmp_path)

    with pytest.raises(UnsafeAnalysisPathError):
        await repository.update("../owner-b", JOB_ID, analysis_response())


@pytest.mark.asyncio
async def test_in_memory_job_updates_response_only_when_expected_state_matches() -> None:
    repository = InMemoryJobRepository()
    original = analysis_response(AnalysisJobState.DRAFT)
    await repository.create(
        JobRecord("owner-a", "key", "request", original)
    )
    updated = original.model_copy(update={"state": AnalysisJobState.UPLOADED})

    stored = await repository.update_response(AnalysisJobState.DRAFT, updated)

    assert stored.response == updated
    with pytest.raises(JobStateConflictError):
        await repository.update_response(AnalysisJobState.DRAFT, updated)
