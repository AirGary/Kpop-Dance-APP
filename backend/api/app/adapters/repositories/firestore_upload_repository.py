from datetime import datetime
import hashlib
from typing import Any
from uuid import UUID

from api.app.adapters.repositories.firestore_gateway import (
    FirestoreGateway,
    FirestoreTransaction,
)
from api.app.ports.upload_repository import (
    UploadIdempotencyConflictError,
    UploadSession,
)
from api.app.schemas.uploads import CreateUploadRequest


class FirestoreUploadRepository:
    def __init__(self, gateway: FirestoreGateway) -> None:
        self._gateway = gateway

    async def create(self, session: UploadSession) -> tuple[UploadSession, bool]:
        index_path = _index_path(session.owner_id, session.idempotency_key)
        upload_path = _upload_path(session.id)

        async def operation(
            transaction: FirestoreTransaction,
        ) -> tuple[UploadSession, bool]:
            index = await transaction.get(index_path)
            if index is not None:
                existing = await transaction.get(
                    _upload_path(UUID(index["uploadId"]))
                )
                if existing is None:
                    raise RuntimeError("Firestore upload idempotency index is inconsistent.")
                stored = _session_from_document(existing)
                if stored.request_digest != session.request_digest:
                    raise UploadIdempotencyConflictError
                return stored, False

            transaction.set(upload_path, _session_to_document(session))
            transaction.set(
                index_path,
                {
                    "uploadId": str(session.id),
                    "ownerId": session.owner_id,
                    "requestDigest": session.request_digest,
                },
            )
            return session, True

        return await self._gateway.run_transaction(operation)

    async def get(self, upload_id: UUID) -> UploadSession | None:
        document = await self._gateway.get(_upload_path(upload_id))
        return _session_from_document(document) if document is not None else None

    async def find_idempotent(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> UploadSession | None:
        index = await self._gateway.get(_index_path(owner_id, idempotency_key))
        if index is None:
            return None
        document = await self._gateway.get(_upload_path(UUID(index["uploadId"])))
        if document is None or document.get("ownerId") != owner_id:
            return None
        return _session_from_document(document)

    async def update_offset(
        self,
        upload_id: UUID,
        expected: int,
        new: int,
    ) -> bool:
        async def operation(transaction: FirestoreTransaction) -> bool:
            path = _upload_path(upload_id)
            document = await transaction.get(path)
            if document is None or document.get("offset") != expected:
                return False
            document["offset"] = new
            transaction.set(path, document)
            return True

        return await self._gateway.run_transaction(operation)

    async def update_token_digest(
        self,
        upload_id: UUID,
        token_digest: str,
    ) -> UploadSession:
        return await self._replace_fields(upload_id, tokenDigest=token_digest)

    async def mark_completed(
        self,
        upload_id: UUID,
        job_id: UUID,
    ) -> UploadSession:
        return await self._replace_fields(upload_id, completedJobId=str(job_id))

    async def delete(self, upload_id: UUID) -> None:
        async def operation(transaction: FirestoreTransaction) -> None:
            path = _upload_path(upload_id)
            document = await transaction.get(path)
            if document is None:
                return
            session = _session_from_document(document)
            transaction.delete(path)
            transaction.delete(_index_path(session.owner_id, session.idempotency_key))

        await self._gateway.run_transaction(operation)

    async def expired_before(self, instant: datetime) -> list[UploadSession]:
        documents = await self._gateway.query_less_than_or_equal(
            "uploads",
            "expiresAt",
            instant,
        )
        return sorted(
            (_session_from_document(document) for document in documents),
            key=lambda session: session.expires_at,
        )

    async def _replace_fields(
        self,
        upload_id: UUID,
        **updates: object,
    ) -> UploadSession:
        async def operation(transaction: FirestoreTransaction) -> UploadSession:
            path = _upload_path(upload_id)
            document = await transaction.get(path)
            if document is None:
                raise KeyError(upload_id)
            document.update(updates)
            transaction.set(path, document)
            return _session_from_document(document)

        return await self._gateway.run_transaction(operation)


def _upload_path(upload_id: UUID) -> str:
    return f"uploads/{upload_id}"


def _index_path(owner_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{owner_id}\0{idempotency_key}".encode()).hexdigest()
    return f"uploadIdempotency/{digest}"


def _session_to_document(session: UploadSession) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "ownerId": session.owner_id,
        "request": session.request.model_dump(mode="json", by_alias=True),
        "requestDigest": session.request_digest,
        "idempotencyKey": session.idempotency_key,
        "tokenDigest": session.token_digest,
        "offset": session.offset,
        "expiresAt": session.expires_at,
        "completedJobId": (
            str(session.completed_job_id)
            if session.completed_job_id is not None
            else None
        ),
    }


def _session_from_document(document: dict[str, Any]) -> UploadSession:
    completed_job_id = document.get("completedJobId")
    return UploadSession(
        id=UUID(document["id"]),
        owner_id=document["ownerId"],
        request=CreateUploadRequest.model_validate(document["request"]),
        request_digest=document["requestDigest"],
        idempotency_key=document["idempotencyKey"],
        token_digest=document["tokenDigest"],
        offset=document["offset"],
        expires_at=document["expiresAt"],
        completed_job_id=(
            UUID(completed_job_id) if completed_job_id is not None else None
        ),
    )
