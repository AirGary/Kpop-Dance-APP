import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.ports.analysis_runner import AnalysisRunner
from api.app.schemas.analysis import AnalysisJobState, DancerCandidateResponse
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import JobResponse
from api.app.services.job_service import JobService


class AnalysisCoordinator:
    def __init__(
        self,
        job_service: JobService,
        repository: FileAnalysisRepository,
        workspace: LocalAnalysisWorkspace,
        runner: AnalysisRunner,
    ) -> None:
        self._jobs = job_service
        self._repository = repository
        self._workspace = workspace
        self._runner = runner
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def on_upload_completed(self, owner_id: str, job_id: UUID, upload_id: UUID) -> None:
        current = await self._jobs.get_job(owner_id, job_id)
        if current.state not in {
            AnalysisJobState.DRAFT,
            AnalysisJobState.UPLOADED,
            AnalysisJobState.FAILED_RECOVERABLE,
        }:
            return
        await self._repository.update(owner_id, job_id, current)
        try:
            await self._workspace.promote_upload(owner_id, job_id, upload_id)
            await self._set_state(owner_id, job_id, AnalysisJobState.DETECTING, 0.05)
        except Exception:
            await self._set_state(owner_id, job_id, AnalysisJobState.FAILED_RECOVERABLE, 0, "media_preflight_failed")
            return
        await self._schedule_detection(owner_id, job_id)

    async def candidates(self, owner_id: str, job_id: UUID) -> list[DancerCandidateResponse]:
        await self._require_owner(owner_id, job_id)
        return await self._repository.candidates(owner_id, job_id)

    async def select_target(
        self,
        owner_id: str,
        job_id: UUID,
        candidate_id: str,
        idempotency_key: str,
    ) -> JobResponse:
        await self._require_owner(owner_id, job_id)
        candidates = await self._repository.candidates(owner_id, job_id)
        if not any(candidate.candidate_id == candidate_id for candidate in candidates):
            raise APIError(422, "invalid_candidate", "Candidate was not found.")
        previous = await self._repository.target_selection(owner_id, job_id)
        if previous is not None:
            previous_candidate, previous_key = previous
            if previous_key == idempotency_key and previous_candidate == candidate_id:
                return await self._jobs.get_job(owner_id, job_id)
            if previous_key == idempotency_key:
                raise APIError(409, "idempotency_conflict", "Idempotency key was already used for a different candidate.")
        current = await self._jobs.get_job(owner_id, job_id)
        if current.state not in {AnalysisJobState.AWAITING_TARGET, AnalysisJobState.QUEUED, AnalysisJobState.ANALYZING, AnalysisJobState.RESULT_READY}:
            raise APIError(409, "invalid_analysis_state", "Analysis is not ready for target selection.")
        if current.state is AnalysisJobState.AWAITING_TARGET:
            await self._repository.set_target_selection(owner_id, job_id, candidate_id, idempotency_key)
            await self._set_state(owner_id, job_id, AnalysisJobState.QUEUED, 0.55)
            await self._schedule_analysis(owner_id, job_id, candidate_id)
        return await self._jobs.get_job(owner_id, job_id)

    async def result(self, owner_id: str, job_id: UUID):
        await self._require_owner(owner_id, job_id)
        return await self._repository.result(owner_id, job_id)

    def result_content_path(self, owner_id: str, job_id: UUID, relative_path: str):
        from pathlib import PurePosixPath

        candidate = PurePosixPath(relative_path)
        if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise APIError(404, "result_not_found", "Analysis result was not found.")
        path = (self._workspace.analysis_directory(owner_id, job_id).parent / Path(*candidate.parts)).resolve()
        if not path.is_relative_to(self._workspace.analysis_directory(owner_id, job_id).parent.resolve()):
            raise APIError(404, "result_not_found", "Analysis result was not found.")
        return path

    async def resume_pending(self) -> None:
        for owner_id, response in await self._repository.list_states():
            if response.state is AnalysisJobState.DETECTING:
                await self._schedule_detection(owner_id, response.id)
            elif response.state in {AnalysisJobState.QUEUED, AnalysisJobState.ANALYZING}:
                selection = await self._repository.target_selection(owner_id, response.id)
                if selection is not None:
                    await self._schedule_analysis(owner_id, response.id, selection[0])

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._runner.shutdown()

    async def _detect(self, owner_id: str, job_id: UUID) -> None:
        try:
            candidates = await self._runner.detect_candidates(owner_id, job_id)
            await self._repository.set_candidates(owner_id, job_id, candidates)
            await self._set_state(owner_id, job_id, AnalysisJobState.AWAITING_TARGET, 0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._set_state(owner_id, job_id, AnalysisJobState.FAILED_RECOVERABLE, 0, "analysis_runner_failed")

    async def _schedule_detection(self, owner_id: str, job_id: UUID) -> None:
        async with self._lock:
            task = self._tasks.get(job_id)
            if task is None or task.done():
                self._tasks[job_id] = asyncio.create_task(self._detect(owner_id, job_id))

    async def _schedule_analysis(self, owner_id: str, job_id: UUID, candidate_id: str) -> None:
        async with self._lock:
            task = self._tasks.get(job_id)
            if task is None or task.done():
                self._tasks[job_id] = asyncio.create_task(self._analyze(owner_id, job_id, candidate_id))

    async def _analyze(self, owner_id: str, job_id: UUID, candidate_id: str) -> None:
        try:
            await self._set_state(owner_id, job_id, AnalysisJobState.ANALYZING, 0.6)
            result = await self._runner.analyze_target(owner_id, job_id, candidate_id)
            await self._repository.set_result(owner_id, job_id, result)
            await self._set_state(owner_id, job_id, AnalysisJobState.RESULT_READY, 1.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._set_state(owner_id, job_id, AnalysisJobState.FAILED_RECOVERABLE, 0, "analysis_runner_failed")

    async def _require_owner(self, owner_id: str, job_id: UUID) -> JobResponse:
        try:
            return await self._jobs.get_job(owner_id, job_id)
        except APIError:
            raise

    async def _set_state(self, owner_id: str, job_id: UUID, state: AnalysisJobState, progress: float, error_code: str | None = None) -> JobResponse:
        current = await self._jobs.get_job(owner_id, job_id)
        updated = current.model_copy(update={"state": state, "progress": progress, "error_code": error_code, "updated_at": datetime.now(UTC)})
        stored = await self._jobs.update_response(current.state, updated)
        await self._repository.update(owner_id, job_id, stored)
        return stored
