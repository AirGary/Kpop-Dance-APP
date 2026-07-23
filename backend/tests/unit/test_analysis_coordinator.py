import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.repositories.file_job_repository import FileJobRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.ports.analysis_runner import AnalysisRunner
from api.app.schemas.analysis import AnalysisJobState, DancerCandidateResponse
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import JobResponse
from api.app.services.analysis_coordinator import AnalysisCoordinator
from api.app.services.job_service import JobService
from api.app.ports.job_repository import JobRecord


JOB_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


def candidate(candidate_id: str = "candidate-1") -> DancerCandidateResponse:
    return DancerCandidateResponse.model_validate({
        "candidateId": candidate_id,
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
    jobs = FileJobRepository(tmp_path)
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
    assert (await repository.load("dev-user-a", JOB_ID)).state is AnalysisJobState.AWAITING_TARGET
    await coordinator.select_target("dev-user-a", JOB_ID, "candidate-1", "selection-1")
    await coordinator._tasks[JOB_ID]
    assert runner.target_calls == 1
    assert (await service.get_job("dev-user-a", JOB_ID)).state is AnalysisJobState.FAILED_RECOVERABLE
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_duplicate_upload_completion_does_not_restart_detection(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job()
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    service = JobService(jobs, LocalObjectStore(tmp_path))
    repository = FileAnalysisRepository(tmp_path)
    runner = FakeRunner()
    coordinator = AnalysisCoordinator(service, repository, LocalAnalysisWorkspace(tmp_path), runner)
    source = tmp_path / "dev-user-a" / "uploads" / "33333333-3333-3333-3333-333333333333" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test")

    await coordinator.on_upload_completed("dev-user-a", JOB_ID, UUID(source.parent.name))
    await coordinator._tasks[JOB_ID]
    await coordinator.on_upload_completed("dev-user-a", JOB_ID, UUID(source.parent.name))
    await asyncio.sleep(0)

    assert runner.detect_calls == 1
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_resume_pending_restarts_detection_from_persisted_state(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job().model_copy(update={"state": AnalysisJobState.DETECTING, "progress": 0.05})
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, response)
    runner = FakeRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.resume_pending()
    await coordinator._tasks[JOB_ID]

    assert runner.detect_calls == 1
    assert (await jobs.get_for_owner(JOB_ID, "dev-user-a")).response.state is AnalysisJobState.AWAITING_TARGET
    assert (await repository.load("dev-user-a", JOB_ID)).state is AnalysisJobState.AWAITING_TARGET
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_target_selection_idempotency_key_cannot_change_candidate(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job().model_copy(update={"state": AnalysisJobState.AWAITING_TARGET, "progress": 0.5})
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, response)
    await repository.set_candidates("dev-user-a", JOB_ID, [candidate(), candidate("candidate-2")])
    runner = FakeRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.select_target("dev-user-a", JOB_ID, "candidate-1", "selection-1")
    await coordinator.select_target("dev-user-a", JOB_ID, "candidate-1", "selection-1")
    with pytest.raises(APIError) as error:
        await coordinator.select_target("dev-user-a", JOB_ID, "candidate-2", "selection-1")

    assert error.value.status_code == 409
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_target_selection_cannot_switch_candidate_after_first_selection(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job().model_copy(update={"state": AnalysisJobState.AWAITING_TARGET, "progress": 0.5})
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, response)
    await repository.set_candidates("dev-user-a", JOB_ID, [candidate(), candidate("candidate-2")])
    runner = FakeRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.select_target("dev-user-a", JOB_ID, "candidate-1", "selection-1")
    with pytest.raises(APIError) as error:
        await coordinator.select_target("dev-user-a", JOB_ID, "candidate-2", "selection-2")

    assert error.value.status_code == 409
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_content_path_resolves_contract_path_inside_analysis_directory(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job()
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, response)
    coordinator = AnalysisCoordinator(
        JobService(jobs, LocalObjectStore(tmp_path)),
        repository,
        LocalAnalysisWorkspace(tmp_path),
        FakeRunner(),
    )

    resolved = coordinator.result_content_path("dev-user-a", JOB_ID, "analysis/result-v1.zip")

    assert resolved == tmp_path / "dev-user-a" / str(JOB_ID) / "analysis" / "result-v1.zip"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_content_path_rejects_files_outside_the_analysis_contract(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = job()
    await jobs.create(JobRecord("dev-user-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("dev-user-a", JOB_ID, response)
    coordinator = AnalysisCoordinator(
        JobService(jobs, LocalObjectStore(tmp_path)),
        repository,
        LocalAnalysisWorkspace(tmp_path),
        FakeRunner(),
    )

    with pytest.raises(APIError) as error:
        coordinator.result_content_path("dev-user-a", JOB_ID, "source.mp4")

    assert error.value.status_code == 404
    await coordinator.shutdown()
