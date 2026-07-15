import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from api.app.ports.upload_object_store import UploadObjectStore
from api.app.ports.direct_upload_object_store import DirectUploadObjectStore
from api.app.ports.upload_repository import (
    UploadIdempotencyConflictError,
    UploadRepository,
    UploadSession,
)
from api.app.schemas.jobs import CreateJobRequest, JobResponse
from api.app.schemas.uploads import CreateUploadRequest
from api.app.services.job_service import JobService


class UploadServiceError(Exception):
    code = "upload_error"


class UploadNotFoundError(UploadServiceError):
    code = "upload_not_found"


class UploadRangeError(UploadServiceError):
    def __init__(self, code: str = "invalid_upload_range") -> None:
        super().__init__(code)
        self.code = code


class UploadOffsetConflictError(UploadServiceError):
    code = "upload_offset_conflict"

    def __init__(self, expected_offset: int) -> None:
        super().__init__(f"Expected upload offset {expected_offset}.")
        self.expected_offset = expected_offset


class UploadIncompleteError(UploadServiceError):
    code = "upload_incomplete"


class ChecksumMismatchError(UploadServiceError):
    code = "checksum_mismatch"


@dataclass(frozen=True, slots=True)
class CreatedUpload:
    session: UploadSession
    token: str
    created: bool
    upload_url: str | None = None


@dataclass(frozen=True, slots=True)
class ChunkResult:
    offset: int
    complete: bool


@dataclass(frozen=True, slots=True)
class CompletedUpload:
    job: JobResponse
    created: bool


class UploadService:
    CHUNK_SIZE = 5_242_880
    LIFETIME = timedelta(hours=24)

    def __init__(
        self,
        repository: UploadRepository,
        object_store: UploadObjectStore | DirectUploadObjectStore,
        job_service: JobService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._objects = object_store
        self._jobs = job_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._upload_locks: dict[UUID, asyncio.Lock] = {}
        self._session_creation_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._direct_objects: DirectUploadObjectStore | None = None

    @classmethod
    def direct(
        cls,
        repository: UploadRepository,
        object_store: DirectUploadObjectStore,
        job_service: JobService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> "UploadService":
        service = cls(repository, object_store, job_service, clock=clock)
        service._direct_objects = object_store
        return service

    async def create_session(
        self,
        owner_id: str,
        idempotency_key: str,
        request: CreateUploadRequest,
    ) -> CreatedUpload:
        key = (owner_id, idempotency_key)
        lock = self._session_creation_locks.setdefault(key, asyncio.Lock())
        async with lock:
            return await self._create_session(owner_id, idempotency_key, request)

    async def _create_session(
        self,
        owner_id: str,
        idempotency_key: str,
        request: CreateUploadRequest,
    ) -> CreatedUpload:
        await self.cleanup_expired()
        token = secrets.token_urlsafe(32)
        session = UploadSession(
            id=uuid4(),
            owner_id=owner_id,
            request=request,
            request_digest=self._request_digest(request),
            idempotency_key=idempotency_key,
            token_digest=self._token_digest(token),
            offset=0,
            expires_at=self._clock() + self.LIFETIME,
        )
        if self._direct_objects is not None:
            existing = await self._repository.find_idempotent(
                owner_id,
                idempotency_key,
            )
            if existing is not None:
                if existing.request_digest != session.request_digest:
                    raise UploadRangeError("idempotency_conflict")
                return CreatedUpload(
                    session=existing,
                    token="",
                    created=False,
                    upload_url=existing.upload_url,
                )
            upload_url = await self._direct_objects.create_resumable_session(
                owner_id,
                session.id,
                request,
            )
            session = replace(session, upload_url=upload_url)
        try:
            stored, created = await self._repository.create(session)
        except UploadIdempotencyConflictError as error:
            raise UploadRangeError("idempotency_conflict") from error

        if self._direct_objects is not None:
            return CreatedUpload(
                session=stored,
                token="",
                created=created,
                upload_url=stored.upload_url,
            )

        if not created:
            stored = await self._repository.update_token_digest(
                stored.id,
                self._token_digest(token),
            )
        return CreatedUpload(session=stored, token=token, created=created)

    async def head(self, upload_id: UUID, token: str) -> UploadSession:
        if self._direct_objects is not None:
            raise UploadNotFoundError
        await self.cleanup_expired()
        return await self._valid_token_session(upload_id, token)

    async def append_chunk(
        self,
        upload_id: UUID,
        token: str,
        start: int,
        end: int,
        total: int,
        chunks: AsyncIterator[bytes],
    ) -> ChunkResult:
        if self._direct_objects is not None:
            raise UploadNotFoundError
        await self.cleanup_expired()
        lock = self._upload_locks.setdefault(upload_id, asyncio.Lock())
        async with lock:
            session = await self._valid_token_session(upload_id, token)
            expected_length = self._validate_range(session, start, end, total)
            content = await self._read_exact_body(chunks, expected_length)
            session = await self._reconcile_offset(session)

            if start == session.offset:
                new_offset = await self._objects.append(
                    session.owner_id,
                    upload_id,
                    start,
                    self._single_chunk(content),
                )
                if not await self._repository.update_offset(
                    upload_id,
                    expected=session.offset,
                    new=new_offset,
                ):
                    raise UploadOffsetConflictError(session.offset)
                return ChunkResult(
                    offset=new_offset,
                    complete=new_offset == session.request.byte_count,
                )

            if end + 1 == session.offset and await self._objects.matches(
                session.owner_id,
                upload_id,
                start,
                self._single_chunk(content),
            ):
                return ChunkResult(
                    offset=session.offset,
                    complete=session.offset == session.request.byte_count,
                )

            raise UploadOffsetConflictError(session.offset)

    async def complete(
        self,
        owner_id: str,
        upload_id: UUID,
        _idempotency_key: str,
    ) -> CompletedUpload:
        await self.cleanup_expired()
        lock = self._upload_locks.setdefault(upload_id, asyncio.Lock())
        async with lock:
            session = await self._repository.get(upload_id)
            if session is None or session.owner_id != owner_id:
                raise UploadNotFoundError
            if session.completed_job_id is not None:
                job = await self._jobs.get_job(owner_id, session.completed_job_id)
                return CompletedUpload(job=job, created=False)

            actual_size = await self._objects.size(owner_id, upload_id)
            if actual_size != session.request.byte_count:
                raise UploadIncompleteError
            if (
                self._direct_objects is None
                and await self._objects.sha256(owner_id, upload_id)
                != session.request.sha256
            ):
                await self._objects.delete(owner_id, upload_id)
                await self._repository.update_offset(upload_id, session.offset, 0)
                raise ChecksumMismatchError

            job_request = CreateJobRequest.model_validate(
                {
                    "projectId": session.request.project_id,
                    "sourceFingerprint": session.request.source_fingerprint,
                    "durationSeconds": session.request.duration_seconds,
                    "byteCount": session.request.byte_count,
                    "mimeType": session.request.mime_type,
                }
            )
            job, created = await self._jobs.create_job(
                owner_id,
                f"upload-complete:{upload_id}",
                job_request,
            )
            await self._repository.mark_completed(upload_id, job.id)
            return CompletedUpload(job=job, created=created)

    async def cleanup_expired(self) -> int:
        expired = await self._repository.expired_before(self._clock())
        for session in expired:
            await self._objects.delete(session.owner_id, session.id)
            await self._repository.delete(session.id)
            self._upload_locks.pop(session.id, None)
        return len(expired)

    async def _valid_token_session(
        self,
        upload_id: UUID,
        token: str,
    ) -> UploadSession:
        session = await self._repository.get(upload_id)
        if session is None or not hmac.compare_digest(
            session.token_digest,
            self._token_digest(token),
        ):
            raise UploadNotFoundError
        return session

    async def _reconcile_offset(self, session: UploadSession) -> UploadSession:
        actual = await self._objects.size(session.owner_id, session.id)
        if actual == session.offset:
            return session
        if actual > session.request.byte_count:
            raise UploadRangeError
        await self._repository.update_offset(session.id, session.offset, actual)
        reconciled = await self._repository.get(session.id)
        if reconciled is None:
            raise UploadNotFoundError
        return reconciled

    @classmethod
    def _validate_range(
        cls,
        session: UploadSession,
        start: int,
        end: int,
        total: int,
    ) -> int:
        if total != session.request.byte_count or start < 0 or end < start or end >= total:
            raise UploadRangeError
        length = end - start + 1
        if length > cls.CHUNK_SIZE:
            raise UploadRangeError
        return length

    @staticmethod
    async def _read_exact_body(chunks: AsyncIterator[bytes], expected: int) -> bytes:
        content = bytearray()
        async for chunk in chunks:
            content.extend(chunk)
            if len(content) > expected:
                raise UploadRangeError
        if len(content) != expected:
            raise UploadRangeError
        return bytes(content)

    @staticmethod
    async def _single_chunk(content: bytes) -> AsyncIterator[bytes]:
        yield content

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _request_digest(request: CreateUploadRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
