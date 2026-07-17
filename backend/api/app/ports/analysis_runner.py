from typing import Protocol
from uuid import UUID

from api.app.schemas.analysis import DancerCandidateResponse, AnalysisResultResponse


class AnalysisRunner(Protocol):
    async def detect_candidates(self, owner_id: str, job_id: UUID) -> list[DancerCandidateResponse]: ...

    async def analyze_target(
        self, owner_id: str, job_id: UUID, candidate_id: str
    ) -> AnalysisResultResponse: ...

    async def shutdown(self) -> None: ...

