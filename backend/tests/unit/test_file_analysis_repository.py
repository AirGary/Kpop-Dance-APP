from datetime import UTC, datetime
from pathlib import Path
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
    assert replaces == [
        (
            tmp_path / "owner-a" / str(JOB_ID) / "analysis" / "analysis-state.json.tmp",
            tmp_path / "owner-a" / str(JOB_ID) / "analysis" / "analysis-state.json",
        )
    ]
    assert not replaces[0][0].exists()


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
