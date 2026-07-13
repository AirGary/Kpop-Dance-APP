from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from api.app.ports.auth import AuthenticatedUser
from api.app.routes.identity import authenticated_user
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import CreateJobRequest, JobResponse


router = APIRouter(prefix="/v1/jobs")


async def idempotency_key(request: Request) -> str:
    values = request.headers.getlist("Idempotency-Key")
    if len(values) != 1:
        raise APIError(422, "validation_error", "Request validation failed.")

    value = values[0]
    if not 1 <= len(value) <= 128 or any(
        ord(character) < 33 or ord(character) > 126 for character in value
    ):
        raise APIError(422, "validation_error", "Request validation failed.")
    return value


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    payload: CreateJobRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    key: Annotated[str, Depends(idempotency_key)],
    request: Request,
) -> JobResponse:
    job, created = await request.app.state.container.job_service.create_job(
        user.user_id,
        key,
        payload,
    )
    response.status_code = 201 if created else 200
    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    request: Request,
) -> JobResponse:
    return await request.app.state.container.job_service.get_job(
        user.user_id,
        job_id,
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    request: Request,
) -> Response:
    await request.app.state.container.job_service.delete_job(user.user_id, job_id)
    return Response(status_code=204)
