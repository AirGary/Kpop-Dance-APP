from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from api.app.ports.auth import AuthenticatedUser
from api.app.routes.identity import authenticated_user
from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse, SelectTargetRequest
from api.app.schemas.errors import APIError

router = APIRouter(prefix="/v1/jobs")


@router.get("/{job_id}/dancers", response_model=list[DancerCandidateResponse])
async def dancers(job_id: UUID, user: Annotated[AuthenticatedUser, Depends(authenticated_user)], request: Request):
    coordinator = request.app.state.container.analysis_coordinator
    if coordinator is None:
        raise APIError(503, "analysis_unavailable", "Local analysis is not enabled.")
    return await coordinator.candidates(user.user_id, job_id)


@router.post("/{job_id}/target")
async def select_target(job_id: UUID, payload: SelectTargetRequest, user: Annotated[AuthenticatedUser, Depends(authenticated_user)], request: Request):
    coordinator = request.app.state.container.analysis_coordinator
    if coordinator is None:
        raise APIError(503, "analysis_unavailable", "Local analysis is not enabled.")
    return await coordinator.select_target(user.user_id, job_id, payload.candidate_id)


@router.get("/{job_id}/result", response_model=AnalysisResultResponse)
async def result(job_id: UUID, user: Annotated[AuthenticatedUser, Depends(authenticated_user)], request: Request):
    coordinator = request.app.state.container.analysis_coordinator
    if coordinator is None:
        raise APIError(503, "analysis_unavailable", "Local analysis is not enabled.")
    try:
        return await coordinator.result(user.user_id, job_id)
    except Exception as error:
        raise APIError(404, "result_not_found", "Analysis result was not found.") from error


@router.get("/{job_id}/result/content", name="analysis_result_content")
async def result_content(job_id: UUID, user: Annotated[AuthenticatedUser, Depends(authenticated_user)], request: Request):
    coordinator = request.app.state.container.analysis_coordinator
    if coordinator is None:
        raise APIError(503, "analysis_unavailable", "Local analysis is not enabled.")
    metadata = await coordinator.result(user.user_id, job_id)
    path = coordinator.result_content_path(user.user_id, job_id, metadata.content_path)
    if not path.is_file():
        raise APIError(404, "result_not_found", "Analysis result was not found.")
    return FileResponse(path, media_type="application/zip")

