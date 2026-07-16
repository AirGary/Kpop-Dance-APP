import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
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

    async def find_completed(
        self,
        owner_id: str,
        job_id: UUID,
    ) -> UploadSession | None:
        async with self._lock:
            return next(
                (
                    session
                    for session in self._sessions.values()
                    if session.owner_id == owner_id
                    and session.completed_job_id == job_id
                ),
                None,
            )

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

    async def update_token_digest(
        self,
        upload_id: UUID,
        token_digest: str,
    ) -> UploadSession:
        async with self._lock:
            session = self._sessions[upload_id]
            updated = replace(session, token_digest=token_digest)
            self._sessions[upload_id] = updated
            return updated

    async def mark_completed(
        self,
        upload_id: UUID,
        job_id: UUID,
        claim_id: str,
    ) -> UploadSession | None:
        async with self._lock:
            session = self._sessions[upload_id]
            if (
                session.state != "completing"
                or session.completion_claim_id != claim_id
            ):
                return None
            completed = replace(
                session,
                completed_job_id=job_id,
                state="completed",
                completion_claim_id=None,
                completion_claim_expires_at=None,
            )
            self._sessions[upload_id] = completed
            return completed

    async def claim_completion(
        self,
        upload_id: UUID,
        owner_id: str,
        instant: datetime,
        claim_id: str,
    ) -> UploadSession | None:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None or session.owner_id != owner_id:
                return None
            if session.state == "completed":
                return session
            if session.state == "completing" and session.completion_claim_id == claim_id:
                return session
            lease_active = (
                session.completion_claim_expires_at is not None
                and session.completion_claim_expires_at > instant
            )
            if session.state == "completing" and lease_active:
                return None
            if session.state not in {"active", "completing"} or session.expires_at <= instant:
                return None
            claimed = replace(
                session,
                state="completing",
                completion_claim_id=claim_id,
                completion_claim_expires_at=instant + timedelta(minutes=5),
            )
            self._sessions[upload_id] = claimed
            return claimed

    async def release_completion(self, upload_id: UUID, claim_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if (
                session is not None
                and session.state == "completing"
                and session.completion_claim_id == claim_id
            ):
                self._sessions[upload_id] = replace(
                    session,
                    state="active",
                    completion_claim_id=None,
                    completion_claim_expires_at=None,
                )

    async def claim_expired(
        self,
        upload_id: UUID,
        instant: datetime,
    ) -> UploadSession | None:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if (
                session is None
                or session.expires_at > instant
                or (
                    session.state == "completing"
                    and session.completion_claim_expires_at is not None
                    and session.completion_claim_expires_at > instant
                )
                or session.state not in {"active", "completing", "deleting"}
            ):
                return None
            claimed = replace(
                session,
                state="deleting",
                completion_claim_id=None,
                completion_claim_expires_at=None,
            )
            self._sessions[upload_id] = claimed
            return claimed

    async def claim_deletion(
        self,
        upload_id: UUID,
        owner_id: str,
    ) -> UploadSession | None:
        async with self._lock:
            session = self._sessions.get(upload_id)
            if session is None or session.owner_id != owner_id:
                return None
            if session.state == "deleting":
                return session
            if session.state != "active":
                return None
            claimed = replace(session, state="deleting")
            self._sessions[upload_id] = claimed
            return claimed

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
                and (
                    session.state in {"active", "deleting"}
                    or (
                        session.state == "completing"
                        and session.completion_claim_expires_at is not None
                        and session.completion_claim_expires_at <= instant
                    )
                )
            ]
