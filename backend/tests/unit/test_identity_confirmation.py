import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.repositories.file_job_repository import FileJobRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.ports.analysis_runner import AnalysisRunner, TargetAnalysisAwaitingConfirmation, TargetAnalysisCompleted
from api.app.ports.job_repository import JobRecord
from api.app.schemas.analysis import (
    AnalysisJobState,
    IdentityConfirmationResponse,
    SubmitIdentityConfirmationRequest,
    AnalysisResultResponse,
)
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import JobResponse
from api.app.services.analysis_coordinator import AnalysisCoordinator
from api.app.services.job_service import JobService


JOB_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROJECT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def pending_confirmation() -> IdentityConfirmationResponse:
    return IdentityConfirmationResponse.model_validate(
        {
            "confirmationId": "confirm-7-8",
            "previousImagePath": "analysis/candidates/candidate-1-3.jpg",
            "candidateImagePath": "analysis/candidates/candidate-2-1.jpg",
            "previousInterval": {"startSeconds": 1, "endSeconds": 2},
            "candidateInterval": {"startSeconds": 3, "endSeconds": 4},
            "candidateClusterId": "candidate-1",
        }
    )


def newer_pending_confirmation() -> IdentityConfirmationResponse:
    return pending_confirmation().model_copy(update={"confirmation_id": "confirm-9-10"})


def awaiting_job() -> JobResponse:
    now = datetime.now(UTC)
    return JobResponse(
        id=JOB_ID,
        projectId=PROJECT_ID,
        state=AnalysisJobState.AWAITING_CONFIRMATION,
        progress=0.6,
        createdAt=now,
        updatedAt=now,
    )


class AwaitingRunner(AnalysisRunner):
    def __init__(self) -> None:
        self.target_calls = 0

    async def detect_candidates(self, owner_id: str, job_id: UUID):
        return []

    async def analyze_target(self, owner_id: str, job_id: UUID, candidate_id: str):
        self.target_calls += 1
        return TargetAnalysisAwaitingConfirmation(pending_confirmation())

    async def shutdown(self) -> None:
        return None


class CompletedRunner(AnalysisRunner):
    def __init__(self) -> None:
        self.target_calls = 0

    async def detect_candidates(self, owner_id: str, job_id: UUID):
        return []

    async def analyze_target(self, owner_id: str, job_id: UUID, candidate_id: str):
        self.target_calls += 1
        return TargetAnalysisCompleted(AnalysisResultResponse.model_validate({
            "schemaVersion": 1,
            "sha256": "a" * 64,
            "byteCount": 1,
            "contentPath": "analysis/result-v1.zip",
        }))

    async def shutdown(self) -> None:
        return None


class RaceCoordinator(AnalysisCoordinator):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.awaiting_stored = asyncio.Event()
        self.release_old_analysis = asyncio.Event()

    async def _set_state(self, owner_id, job_id, state, progress, error_code=None):
        stored = await super()._set_state(owner_id, job_id, state, progress, error_code)
        if state is AnalysisJobState.AWAITING_CONFIRMATION:
            self.awaiting_stored.set()
            await self.release_old_analysis.wait()
        return stored


@pytest.mark.asyncio
async def test_pending_confirmation_is_owner_scoped_and_decision_is_exactly_idempotent(tmp_path):
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job())
    await repository.set_identity_confirmation("owner-a", JOB_ID, pending_confirmation())

    assert await repository.identity_confirmation("owner-a", JOB_ID) == pending_confirmation()
    with pytest.raises(Exception) as foreign:
        await repository.identity_confirmation("owner-b", JOB_ID)

    request = SubmitIdentityConfirmationRequest(confirmationId="confirm-7-8", decision="same")
    await repository.set_identity_decision("owner-a", JOB_ID, request.confirmation_id, request.decision, "decision-key")
    await repository.set_identity_decision("owner-a", JOB_ID, request.confirmation_id, request.decision, "decision-key")
    assert await repository.identity_decision("owner-a", JOB_ID) == ("confirm-7-8", "same", "decision-key")
    with pytest.raises(ValueError):
        await repository.set_identity_decision("owner-a", JOB_ID, request.confirmation_id, "different", "decision-key")
    assert type(foreign.value).__name__ == "AnalysisNotFoundError"


@pytest.mark.asyncio
async def test_pending_runner_pauses_job_and_decision_requeues_without_resume_pending_wakeup(tmp_path):
    jobs = FileJobRepository(tmp_path)
    response = awaiting_job().model_copy(update={"state": AnalysisJobState.QUEUED})
    await jobs.create(JobRecord("owner-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, response)
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    runner = AwaitingRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator._analyze("owner-a", JOB_ID, "candidate-1")

    assert (await coordinator._jobs.get_job("owner-a", JOB_ID)).state is AnalysisJobState.AWAITING_CONFIRMATION
    assert await repository.identity_confirmation("owner-a", JOB_ID) == pending_confirmation()
    with pytest.raises(Exception):
        await repository.result("owner-a", JOB_ID)
    calls_before_restart = runner.target_calls
    await coordinator.resume_pending()
    await asyncio.sleep(0)
    assert runner.target_calls == calls_before_restart

    queued = await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "same", "decision-key")
    assert queued.state in {AnalysisJobState.QUEUED, AnalysisJobState.ANALYZING, AnalysisJobState.AWAITING_CONFIRMATION}
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stale_or_reused_confirmation_decision_is_conflict(tmp_path):
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", awaiting_job()))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job())
    await repository.set_identity_confirmation("owner-a", JOB_ID, pending_confirmation())
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), AwaitingRunner())

    with pytest.raises(APIError) as stale:
        await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "old-confirmation", "same", "key")
    assert stale.value.status_code == 409
    await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "same", "key")
    with pytest.raises(APIError) as reused:
        await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "different", "key")
    assert reused.value.status_code == 409
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_exact_replay_recovers_after_crash_between_decision_and_requeue(tmp_path):
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", awaiting_job()))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job())
    await repository.set_identity_confirmation("owner-a", JOB_ID, pending_confirmation())
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "decision-key")
    runner = AwaitingRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    replayed = await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "same", "decision-key")

    assert replayed.state in {AnalysisJobState.QUEUED, AnalysisJobState.ANALYZING, AnalysisJobState.AWAITING_CONFIRMATION}
    assert (await coordinator._jobs.get_job("owner-a", JOB_ID)).state is not AnalysisJobState.AWAITING_CONFIRMATION
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_confirmation_schedule_is_not_lost_while_old_analysis_task_finishes(tmp_path):
    jobs = FileJobRepository(tmp_path)
    queued = awaiting_job().model_copy(update={"state": AnalysisJobState.QUEUED})
    await jobs.create(JobRecord("owner-a", "upload", "hash", queued))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, queued)
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    runner = AwaitingRunner()
    coordinator = RaceCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)
    old_task = asyncio.create_task(coordinator._analyze("owner-a", JOB_ID, "candidate-1"))
    coordinator._tasks[JOB_ID] = old_task
    await coordinator.awaiting_stored.wait()

    await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "same", "decision-key")
    coordinator.release_old_analysis.set()
    await old_task
    for _ in range(20):
        if runner.target_calls >= 2:
            break
        await asyncio.sleep(0.01)

    assert runner.target_calls >= 2
    await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_state", "analysis_state"),
    [
        (AnalysisJobState.QUEUED, AnalysisJobState.AWAITING_CONFIRMATION),
        (AnalysisJobState.AWAITING_CONFIRMATION, AnalysisJobState.QUEUED),
    ],
)
async def test_resume_converges_split_persisted_state_after_identity_decision(tmp_path, job_state, analysis_state):
    jobs = FileJobRepository(tmp_path)
    response = awaiting_job().model_copy(update={"state": job_state})
    await jobs.create(JobRecord("owner-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job().model_copy(update={"state": analysis_state}))
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "decision-key")
    runner = AwaitingRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.resume_pending()
    for _ in range(20):
        if runner.target_calls:
            break
        await asyncio.sleep(0.01)

    assert runner.target_calls == 1
    assert (await coordinator._jobs.get_job("owner-a", JOB_ID)).state is AnalysisJobState.AWAITING_CONFIRMATION
    assert (await repository.load("owner-a", JOB_ID)).state is AnalysisJobState.AWAITING_CONFIRMATION
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_repository_finds_an_older_exact_decision_for_idempotent_replay(tmp_path):
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job())
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-1", "same", "key-1")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-2", "different", "key-2")

    assert await repository.identity_decision("owner-a", JOB_ID, "confirm-1") == ("confirm-1", "same", "key-1")


@pytest.mark.asyncio
async def test_coordinator_replays_any_historical_exact_decision(tmp_path):
    jobs = FileJobRepository(tmp_path)
    ready = awaiting_job().model_copy(update={"state": AnalysisJobState.RESULT_READY})
    await jobs.create(JobRecord("owner-a", "upload", "hash", ready))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, ready)
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-1", "same", "key-1")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-2", "different", "key-2")
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), AwaitingRunner())

    replayed = await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-1", "same", "key-1")

    assert replayed.state is AnalysisJobState.RESULT_READY
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_historical_replay_succeeds_without_disturbing_newer_pending_confirmation(tmp_path):
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", awaiting_job()))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job())
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "key-1")
    await repository.set_identity_confirmation("owner-a", JOB_ID, newer_pending_confirmation())
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), AwaitingRunner())

    replayed = await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "same", "key-1")

    assert replayed.state is AnalysisJobState.AWAITING_CONFIRMATION
    assert await repository.identity_confirmation("owner-a", JOB_ID) == newer_pending_confirmation()
    with pytest.raises(APIError) as conflict:
        await coordinator.submit_identity_confirmation("owner-a", JOB_ID, "confirm-7-8", "different", "key-1")
    assert conflict.value.status_code == 409
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_resume_does_not_reschedule_terminal_result_ready_job_with_history(tmp_path):
    ready = awaiting_job().model_copy(update={"state": AnalysisJobState.RESULT_READY})
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", ready))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, ready)
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "key-1")
    runner = CompletedRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.resume_pending()
    await asyncio.sleep(0)

    assert runner.target_calls == 0
    assert (await repository.load("owner-a", JOB_ID)).state is AnalysisJobState.RESULT_READY
    await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [AnalysisJobState.FAILED_RECOVERABLE, AnalysisJobState.IMPORTING],
)
async def test_resume_does_not_reschedule_non_running_job_with_history(tmp_path, state):
    response = awaiting_job().model_copy(update={"state": state})
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", response))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, response)
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "key-1")
    runner = CompletedRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.resume_pending()
    await asyncio.sleep(0)

    assert runner.target_calls == 0
    assert (await coordinator._jobs.get_job("owner-a", JOB_ID)).state is state
    assert (await repository.load("owner-a", JOB_ID)).state is state
    await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_state", "analysis_state"),
    [
        (AnalysisJobState.QUEUED, AnalysisJobState.AWAITING_CONFIRMATION),
        (AnalysisJobState.AWAITING_CONFIRMATION, AnalysisJobState.QUEUED),
    ],
)
async def test_resume_clears_decided_pending_confirmation_before_resuming(tmp_path, job_state, analysis_state):
    jobs = FileJobRepository(tmp_path)
    await jobs.create(JobRecord("owner-a", "upload", "hash", awaiting_job().model_copy(update={"state": job_state})))
    repository = FileAnalysisRepository(tmp_path)
    await repository.update("owner-a", JOB_ID, awaiting_job().model_copy(update={"state": analysis_state}))
    await repository.set_target_selection("owner-a", JOB_ID, "candidate-1", "target-key")
    await repository.set_identity_confirmation("owner-a", JOB_ID, pending_confirmation())
    await repository.set_identity_decision("owner-a", JOB_ID, "confirm-7-8", "same", "key-1")
    runner = CompletedRunner()
    coordinator = AnalysisCoordinator(JobService(jobs, LocalObjectStore(tmp_path)), repository, LocalAnalysisWorkspace(tmp_path), runner)

    await coordinator.resume_pending()
    for _ in range(20):
        if runner.target_calls:
            break
        await asyncio.sleep(0.01)

    assert runner.target_calls == 1
    with pytest.raises(Exception):
        await repository.identity_confirmation("owner-a", JOB_ID)
    assert (await repository.load("owner-a", JOB_ID)).state is AnalysisJobState.RESULT_READY
    await coordinator.shutdown()
