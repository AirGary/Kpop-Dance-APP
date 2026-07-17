from typing import Protocol
from uuid import UUID

from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse
from api.app.schemas.jobs import JobResponse


class AnalysisNotFoundError(Exception):
    pass


class UnsafeAnalysisPathError(ValueError):
    pass


class AnalysisRepository(Protocol):
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

    async def result(self, owner_id: str, job_id: UUID) -> AnalysisResultResponse: ...

    async def set_result(
        self,
        owner_id: str,
        job_id: UUID,
        result: AnalysisResultResponse,
    ) -> None: ...
