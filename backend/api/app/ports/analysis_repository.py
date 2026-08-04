from typing import Protocol
from uuid import UUID

from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse, IdentityConfirmationResponse, IdentityDecisionValue
from api.app.schemas.jobs import JobResponse


class AnalysisNotFoundError(Exception):
    pass


class UnsafeAnalysisPathError(ValueError):
    pass


class AnalysisRepository(Protocol):
    async def list_states(self) -> list[tuple[str, JobResponse]]: ...

    async def load(self, owner_id: str, job_id: UUID) -> JobResponse: ...

    async def update(
        self,
        owner_id: str,
        job_id: UUID,
        response: JobResponse,
    ) -> JobResponse: ...

    async def candidates(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> list[DancerCandidateResponse]: ...

    async def set_candidates(
        self,
        owner_id: str,
        job_id: UUID,
        candidates: list[DancerCandidateResponse],
    ) -> None: ...

    async def set_target_selection(
        self,
        owner_id: str,
        job_id: UUID,
        candidate_id: str,
        idempotency_key: str,
    ) -> None: ...

    async def target_selection(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> tuple[str, str] | None: ...

    async def result(self, owner_id: str, job_id: UUID) -> AnalysisResultResponse: ...

    async def set_result(
        self,
        owner_id: str,
        job_id: UUID,
        result: AnalysisResultResponse,
    ) -> None: ...

    async def set_identity_confirmation(self, owner_id: str, job_id: UUID, confirmation: IdentityConfirmationResponse | None) -> None: ...

    async def identity_confirmation(self, owner_id: str, job_id: UUID) -> IdentityConfirmationResponse: ...

    async def set_identity_decision(self, owner_id: str, job_id: UUID, confirmation_id: str, decision: IdentityDecisionValue, idempotency_key: str) -> None: ...

    async def identity_decision(self, owner_id: str, job_id: UUID, confirmation_id: str | None = None) -> tuple[str, IdentityDecisionValue, str] | None: ...
