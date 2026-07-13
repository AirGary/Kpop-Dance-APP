import asyncio
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from api.app.ports.upload_repository import (
    UploadIdempotencyConflictError,
    UploadSession,
)


class InMemoryUploadRepository:
    def __init__(self) -> None:
        self._sessions: dict[UUID, UploadSession] = {}
        self._idempotency: dict[tuple[str, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def create(self, session: UploadSession) -> tuple[UploadSession, bool]:
        key = (session.owner_id, session.idempotency_key)
        async with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                existing = self._sessions[existing_id]
                if existing.request_digest != session.request_digest:
                    raise UploadIdempotencyConflictError
                return existing, False

            self._sessions[session.id] = session
            self._idempotency[key] = session.id
            return session, True

    async def get(self, upload_id: UUID) -> UploadSession | None:
        async with self._lock:
            return self._sessions.get(upload_id)

    async def find_idempotent(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> UploadSession | None:
        async with self._lock:
            upload_id = self._idempotency.get((owner_id, idempotency_key))
            return self._sessions.get(upload_id) if upload_id is not None else None

    async def update_offset(
        self,
        upload_id: UUID,
        expected: int,
        new: int,
    ) -> bool:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None or session.offset != expected:
                return False
            self._sessions[upload_id] = replace(session, offset=new)
            return True

    async def mark_completed(
        self,
        upload_id: UUID,
        job_id: UUID,
    ) -> UploadSession:
        async with self._lock:
            session = self._sessions[upload_id]
            completed = replace(session, completed_job_id=job_id)
            self._sessions[upload_id] = completed
            return completed

    async def delete(self, upload_id: UUID) -> None:
        async with self._lock:
            session = self._sessions.pop(upload_id, None)
            if session is not None:
                self._idempotency.pop(
                    (session.owner_id, session.idempotency_key),
                    None,
                )

    async def expired_before(self, instant: datetime) -> list[UploadSession]:
        async with self._lock:
            return [
                session
                for session in self._sessions.values()
                if session.expires_at <= instant
            ]
