import re
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from api.app.ports.auth import AuthenticatedUser
from api.app.routes.identity import authenticated_user
from api.app.routes.jobs import idempotency_key
from api.app.schemas.errors import APIError
from api.app.schemas.jobs import JobResponse
from api.app.schemas.uploads import CreateUploadRequest, UploadSessionResponse
from api.app.services.upload_service import (
    ChecksumMismatchError,
    UploadCompletionInProgressError,
    UploadIncompleteError,
    UploadNotFoundError,
    UploadOffsetConflictError,
    UploadRangeError,
)


router = APIRouter(prefix="/v1/uploads")
_CONTENT_RANGE = re.compile(r"^bytes ([0-9]+)-([0-9]+)/([0-9]+)$")


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int
    total: int


def parse_content_range(request: Request) -> ByteRange:
    values = request.headers.getlist("Content-Range")
    if len(values) != 1:
        raise APIError(422, "validation_error", "Request validation failed.")
    match = _CONTENT_RANGE.fullmatch(values[0])
    if match is None:
        raise APIError(422, "validation_error", "Request validation failed.")
    return ByteRange(*(int(value) for value in match.groups()))


def map_upload_error(error: Exception) -> APIError:
    if isinstance(error, UploadNotFoundError):
        return APIError(404, "upload_not_found", "Upload was not found.")
    if isinstance(error, UploadOffsetConflictError):
        return APIError(409, error.code, "Upload offset does not match.")
    if isinstance(error, UploadIncompleteError):
        return APIError(409, error.code, "Upload is incomplete.")
    if isinstance(error, UploadCompletionInProgressError):
        return APIError(409, error.code, "Upload completion is already in progress.")
    if isinstance(error, ChecksumMismatchError):
        return APIError(422, error.code, "Upload validation failed.")
    if isinstance(error, UploadRangeError):
        status = 409 if error.code == "idempotency_conflict" else 422
        message = (
            "Idempotency key was already used for a different request."
            if status == 409
            else "Request validation failed."
        )
        return APIError(status, error.code, message)
    if isinstance(error, OSError):
        return APIError(503, "storage_unavailable", "Temporary storage is unavailable.")
    raise error


@router.post("", response_model=UploadSessionResponse, status_code=201)
async def create_upload(
    payload: CreateUploadRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    key: Annotated[str, Depends(idempotency_key)],
    request: Request,
) -> UploadSessionResponse:
    try:
        result = await request.app.state.container.upload_service.create_session(
            user.user_id,
            key,
            payload,
        )
    except (UploadRangeError, OSError) as error:
        raise map_upload_error(error) from error

    if result.upload_url is None:
        content_url = request.url_for(
            "put_upload_content",
            upload_id=str(result.session.id),
        )
        upload_url = str(content_url.include_query_params(token=result.token))
        upload_protocol = "stage-lab"
    else:
        upload_url = result.upload_url
        upload_protocol = "gcs-resumable"
    response.status_code = 201 if result.created else 200
    return UploadSessionResponse(
        upload_id=result.session.id,
        upload_url=upload_url,
        expires_at=result.session.expires_at,
        chunk_size=request.app.state.container.upload_service.CHUNK_SIZE,
        offset=result.session.offset,
        upload_protocol=upload_protocol,
    )


@router.head("/{upload_id}/content", status_code=204, name="head_upload_content")
async def head_upload_content(
    upload_id: UUID,
    request: Request,
    token: Annotated[str, Query(min_length=1, max_length=256)],
) -> Response:
    try:
        session = await request.app.state.container.upload_service.head(upload_id, token)
    except (UploadNotFoundError, OSError) as error:
        raise map_upload_error(error) from error
    return Response(
        status_code=204,
        headers={
            "Upload-Offset": str(session.offset),
            "Upload-Length": str(session.request.byte_count),
            "Upload-Expires": session.expires_at.isoformat().replace("+00:00", "Z"),
        },
    )


@router.put("/{upload_id}/content", name="put_upload_content")
async def put_upload_content(
    upload_id: UUID,
    request: Request,
    token: Annotated[str, Query(min_length=1, max_length=256)],
) -> Response:
    byte_range = parse_content_range(request)
    try:
        result = await request.app.state.container.upload_service.append_chunk(
            upload_id,
            token,
            byte_range.start,
            byte_range.end,
            byte_range.total,
            request.stream(),
        )
    except (
        UploadNotFoundError,
        UploadOffsetConflictError,
        UploadRangeError,
        OSError,
    ) as error:
        raise map_upload_error(error) from error
    return Response(
        status_code=201 if result.complete else 308,
        headers={"Upload-Offset": str(result.offset)},
    )


@router.post("/{upload_id}/complete", response_model=JobResponse, status_code=201)
async def complete_upload(
    upload_id: UUID,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    key: Annotated[str, Depends(idempotency_key)],
    request: Request,
) -> JobResponse:
    try:
        result = await request.app.state.container.upload_service.complete(
            user.user_id,
            upload_id,
            key,
        )
    except (
        UploadNotFoundError,
        UploadIncompleteError,
        UploadCompletionInProgressError,
        ChecksumMismatchError,
        OSError,
    ) as error:
        raise map_upload_error(error) from error
    response.status_code = 201 if result.created else 200
    return result.job


@router.delete("/{upload_id}", status_code=204)
async def abandon_upload(
    upload_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
    request: Request,
) -> Response:
    try:
        await request.app.state.container.upload_service.abandon(
            user.user_id,
            upload_id,
        )
    except (UploadNotFoundError, OSError) as error:
        raise map_upload_error(error) from error
    return Response(status_code=204)
