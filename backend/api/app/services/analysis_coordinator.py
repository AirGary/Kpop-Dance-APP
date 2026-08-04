import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.ports.analysis_runner import AnalysisRunner, TargetAnalysisAwaitingConfirmation
from api.app.schemas.analysis import (
    AnalysisJobState,
    DancerCandidateResponse,
    IdentityConfirmationResponse,
    IdentityDecisionValue,
)
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
        self._pending_analyses: dict[UUID, tuple[str, str]] = {}
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
            if previous_candidate != candidate_id:
                raise APIError(409, "target_already_selected", "A different target dancer is already selected.")
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

    async def identity_confirmation(
        self, owner_id: str, job_id: UUID
    ) -> IdentityConfirmationResponse:
        await self._require_owner(owner_id, job_id)
        try:
            return await self._repository.identity_confirmation(owner_id, job_id)
        except Exception as error:
            raise APIError(404, "identity_confirmation_not_found", "Identity confirmation was not found.") from error

    async def submit_identity_confirmation(
        self,
        owner_id: str,
        job_id: UUID,
        confirmation_id: str,
        decision: IdentityDecisionValue,
        idempotency_key: str,
    ) -> JobResponse:
        current = await self._require_owner(owner_id, job_id)
        existing = await self._repository.identity_decision(owner_id, job_id, confirmation_id)
        if existing is not None:
            prior_confirmation, prior_decision, prior_key = existing
            if (prior_confirmation, prior_decision, prior_key) == (confirmation_id, decision, idempotency_key):
                try:
                    pending = await self._repository.identity_confirmation(owner_id, job_id)
                except Exception:
                    pending = None
                if pending is None or pending.confirmation_id != confirmation_id:
                    return current
                if current.state is AnalysisJobState.AWAITING_CONFIRMATION:
                    return await self._advance_after_identity_decision(owner_id, job_id, current)
                return current
            if prior_key == idempotency_key:
                raise APIError(409, "idempotency_conflict", "Idempotency key was already used for another identity decision.")
            raise APIError(409, "identity_decision_final", "The identity confirmation has already been decided.")
        if current.state is not AnalysisJobState.AWAITING_CONFIRMATION:
            raise APIError(409, "invalid_analysis_state", "Analysis is not awaiting identity confirmation.")
        try:
            pending = await self._repository.identity_confirmation(owner_id, job_id)
        except Exception as error:
            raise APIError(409, "stale_identity_confirmation", "Identity confirmation is no longer current.") from error
        if pending.confirmation_id != confirmation_id:
            raise APIError(409, "stale_identity_confirmation", "Identity confirmation is no longer current.")
        try:
            await self._repository.set_identity_decision(owner_id, job_id, confirmation_id, decision, idempotency_key)
        except ValueError as error:
            raise APIError(409, "idempotency_conflict", "Identity decision conflicts with a prior request.") from error
        return await self._advance_after_identity_decision(owner_id, job_id, current)

    async def _advance_after_identity_decision(
        self, owner_id: str, job_id: UUID, current: JobResponse
    ) -> JobResponse:
        """Finish a persisted decision, including an exact replay after a process crash."""
        await self._repository.set_identity_confirmation(owner_id, job_id, None)
        selection = await self._repository.target_selection(owner_id, job_id)
        if selection is None:
            raise APIError(409, "target_not_selected", "Target dancer is not selected.")
        queued = await self._set_state(owner_id, job_id, AnalysisJobState.QUEUED, current.progress)
        await self._schedule_analysis(owner_id, job_id, selection[0])
        return queued

    async def content_path(self, owner_id: str, job_id: UUID, relative_path: str) -> Path:
        await self._require_owner(owner_id, job_id)
        return self.result_content_path(owner_id, job_id, relative_path)

    def result_content_path(self, owner_id: str, job_id: UUID, relative_path: str):
        from pathlib import PurePosixPath

        candidate = PurePosixPath(relative_path)
        if (
            candidate.is_absolute()
            or len(candidate.parts) < 2
            or candidate.parts[0] != "analysis"
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise APIError(404, "result_not_found", "Analysis result was not found.")
        analysis_directory = self._workspace.analysis_directory(owner_id, job_id).resolve()
        path = (analysis_directory / Path(*candidate.parts[1:])).resolve()
        if not path.is_relative_to(analysis_directory):
            raise APIError(404, "result_not_found", "Analysis result was not found.")
        return path

    async def resume_pending(self) -> None:
        for owner_id, persisted in await self._repository.list_states():
            current = await self._jobs.get_job(owner_id, persisted.id)
            terminal_states = {
                AnalysisJobState.RESULT_READY,
                AnalysisJobState.COMPLETED,
                AnalysisJobState.FAILED_TERMINAL,
                AnalysisJobState.DELETED,
            }
            if current.state in terminal_states:
                await self._repository.update(owner_id, persisted.id, current)
                continue
            if persisted.state in terminal_states:
                await self._converge_state(owner_id, persisted.id, current, persisted.state)
                continue
            if persisted.state is AnalysisJobState.DETECTING:
                await self._schedule_detection(owner_id, persisted.id)
                continue
            try:
                pending = await self._repository.identity_confirmation(owner_id, persisted.id)
            except Exception:
                pending = None
            decision = await self._repository.identity_decision(
                owner_id,
                persisted.id,
                pending.confirmation_id if pending is not None else None,
            )
            resumable_states = {
                AnalysisJobState.QUEUED,
                AnalysisJobState.ANALYZING,
                AnalysisJobState.AWAITING_CONFIRMATION,
            }
            if {current.state, persisted.state} - resumable_states:
                # A history entry alone must never revive failed, importing, or cancelling work.
                continue
            if pending is not None and decision is None:
                await self._converge_state(owner_id, persisted.id, current, AnalysisJobState.AWAITING_CONFIRMATION)
                continue
            if pending is not None and decision is not None:
                # The decision is durable; discard its old prompt before another worker can run.
                await self._repository.set_identity_confirmation(owner_id, persisted.id, None)
            await self._converge_state(owner_id, persisted.id, current, AnalysisJobState.QUEUED)
            selection = await self._repository.target_selection(owner_id, persisted.id)
            if selection is not None:
                await self._schedule_analysis(owner_id, persisted.id, selection[0])

    async def _converge_state(
        self,
        owner_id: str,
        job_id: UUID,
        current: JobResponse,
        state: AnalysisJobState,
    ) -> JobResponse:
        """Repair either side of a crash-interrupted durable state transition."""
        if current.state is not state:
            updated = current.model_copy(update={
                "state": state,
                "updated_at": datetime.now(UTC),
            })
            current = await self._jobs.update_response(current.state, updated)
        await self._repository.update(owner_id, job_id, current)
        return current

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._pending_analyses.clear()
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
                return
            self._pending_analyses[job_id] = (owner_id, candidate_id)
            task.add_done_callback(
                lambda finished, identifier=job_id: asyncio.create_task(
                    self._launch_pending_analysis(identifier, finished)
                )
            )

    async def _launch_pending_analysis(self, job_id: UUID, finished: asyncio.Task[None]) -> None:
        async with self._lock:
            if self._tasks.get(job_id) is not finished:
                return
            pending = self._pending_analyses.pop(job_id, None)
            if pending is not None:
                owner_id, candidate_id = pending
                self._tasks[job_id] = asyncio.create_task(
                    self._analyze(owner_id, job_id, candidate_id)
                )

    async def _analyze(self, owner_id: str, job_id: UUID, candidate_id: str) -> None:
        try:
            await self._set_state(owner_id, job_id, AnalysisJobState.ANALYZING, 0.6)
            outcome = await self._runner.analyze_target(owner_id, job_id, candidate_id)
            if isinstance(outcome, TargetAnalysisAwaitingConfirmation):
                await self._repository.set_identity_confirmation(owner_id, job_id, outcome.confirmation)
                await self._set_state(owner_id, job_id, AnalysisJobState.AWAITING_CONFIRMATION, 0.6)
                return
            await self._repository.set_result(owner_id, job_id, outcome.result)
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
