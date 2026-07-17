from datetime import UTC, datetime
from uuid import UUID

import pytest

from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.repositories.in_memory_job_repository import InMemoryJobRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.ports.analysis_runner import AnalysisRunner
from api.app.schemas.analysis import AnalysisJobState, DancerCandidateResponse
from api.app.schemas.jobs import JobResponse
from api.app.services.analysis_coordinator import AnalysisCoordinator
from api.app.services.job_service import JobService
from api.app.ports.job_repository import JobRecord


JOB_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


def candidate() -> DancerCandidateResponse:
    return DancerCandidateResponse.model_validate({
        "candidateId": "candidate-1",
        "representativeImagePaths": ["analysis/candidates/1-1.jpg", "analysis/candidates/1-2.jpg", "analysis/candidates/1-3.jpg"],
        "appearanceIntervals": [{"startSeconds": 0, "endSeconds": 2}],
        "boxSummary": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.6},
        "confidence": 0.9,
    })


class FakeRunner(AnalysisRunner):
    def __init__(self):
        self.detect_calls = 0
        self.target_calls = 0

    async def detect_candidates(self, owner_id, job_id):
        self.detect_calls += 1
        return [candidate()]

    async def analyze_target(self, owner_id, job_id, candidate_id):
        self.target_calls += 1
        raise RuntimeError("not part of Task 5")

    async def shutdown(self):
        return None


def job() -> JobResponse:
    now = datetime.now(UTC)
    return JobResponse(id=JOB_ID, project_id=PROJECT_ID, created_at=now, updated_at=now)


@pytest.mark.asyncio
async def test_upload_completion_runs_detection_and_target_selection_is_idempotent(tmp_path):
    jobs = InMemoryJobRepository()
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", job()))
    service = JobService(jobs, LocalObjectStore(tmp_path))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, job())
    runner = FakeRunner()
    coordinator = AnalysisCoordinator(service, repository, LocalAnalysisWorkspace(tmp_path), runner)

    source = tmp_path / "dev-user-a" / "uploads" / "33333333-3333-3333-3333-333333333333" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test")
    await coordinator.on_upload_completed("dev-user-a", JOB_ID, UUID(source.parent.name))
    await coordinator._tasks[JOB_ID]

    assert runner.detect_calls == 1
    assert (await service.get_job("dev-user-a", JOB_ID)).state is AnalysisJobState.AWAITING_TARGET
    await coordinator.select_target("dev-user-a", JOB_ID, "candidate-1")
    await coordinator._tasks[JOB_ID]
    assert runner.target_calls == 1
    assert (await service.get_job("dev-user-a", JOB_ID)).state is AnalysisJobState.FAILED_RECOVERABLE
    await coordinator.shutdown()

