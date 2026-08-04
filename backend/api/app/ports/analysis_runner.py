from dataclasses import dataclass
from typing import Protocol, TypeAlias
from uuid import UUID

from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse, IdentityConfirmationResponse


@dataclass(frozen=True, slots=True)
class TargetAnalysisCompleted:
    result: AnalysisResultResponse


@dataclass(frozen=True, slots=True)
class TargetAnalysisAwaitingConfirmation:
    confirmation: IdentityConfirmationResponse


TargetAnalysisOutcome: TypeAlias = TargetAnalysisCompleted | TargetAnalysisAwaitingConfirmation


class AnalysisRunner(Protocol):
    async def detect_candidates(self, owner_id: str, job_id: UUID) -> list[DancerCandidateResponse]: ...

    async def analyze_target(
        self, owner_id: str, job_id: UUID, candidate_id: str
    ) -> TargetAnalysisOutcome: ...

    async def shutdown(self) -> None: ...
