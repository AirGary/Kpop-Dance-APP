import hashlib
from typing import Any
from uuid import UUID

from api.app.adapters.repositories.firestore_gateway import (
    FirestoreGateway,
    FirestoreTransaction,
)
from api.app.ports.job_repository import (
    IdempotencyConflictError,
    JobNotFoundError,
    JobRecord,
)
from api.app.schemas.jobs import JobResponse


class FirestoreJobRepository:
    def __init__(self, gateway: FirestoreGateway) -> None:
        self._gateway = gateway

    async def create(self, record: JobRecord) -> tuple[JobRecord, bool]:
        index_path = _index_path(record.owner_id, record.idempotency_key)
        job_path = _job_path(record.response.id)

        async def operation(
            transaction: FirestoreTransaction,
        ) -> tuple[JobRecord, bool]:
            index = await transaction.get(index_path)
            if index is not None:
                existing = await transaction.get(_job_path(UUID(index["jobId"])))
                if existing is None:
                    raise RuntimeError("Firestore job idempotency index is inconsistent.")
                stored = _record_from_document(existing)
                if stored.request_hash != record.request_hash:
                    raise IdempotencyConflictError
                return stored, False

            transaction.set(job_path, _record_to_document(record))
            transaction.set(
                index_path,
                {
                    "jobId": str(record.response.id),
                    "ownerId": record.owner_id,
                    "requestHash": record.request_hash,
                },
            )
            return record, True

        return await self._gateway.run_transaction(operation)

    async def get_for_owner(self, job_id: UUID, owner_id: str) -> JobRecord:
        document = await self._gateway.get(_job_path(job_id))
        if document is None or document.get("ownerId") != owner_id:
            raise JobNotFoundError
        return _record_from_document(document)

    async def delete_for_owner(self, job_id: UUID, owner_id: str) -> None:
        async def operation(transaction: FirestoreTransaction) -> None:
            path = _job_path(job_id)
            document = await transaction.get(path)
            if document is None or document.get("ownerId") != owner_id:
                raise JobNotFoundError
            record = _record_from_document(document)
            transaction.delete(path)
            transaction.delete(_index_path(owner_id, record.idempotency_key))

        await self._gateway.run_transaction(operation)

    async def find_by_idempotency_key(
        self,
        owner_id: str,
        idempotency_key: str,
    ) -> JobRecord | None:
        index = await self._gateway.get(_index_path(owner_id, idempotency_key))
        if index is None:
            return None
        document = await self._gateway.get(_job_path(UUID(index["jobId"])))
        if document is None or document.get("ownerId") != owner_id:
            return None
        return _record_from_document(document)


def _job_path(job_id: UUID) -> str:
    return f"jobs/{job_id}"


def _index_path(owner_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{owner_id}\0{idempotency_key}".encode()).hexdigest()
    return f"jobIdempotency/{digest}"


def _record_to_document(record: JobRecord) -> dict[str, Any]:
    return {
        "ownerId": record.owner_id,
        "idempotencyKey": record.idempotency_key,
        "requestHash": record.request_hash,
        "response": record.response.model_dump(mode="json", by_alias=True),
    }


def _record_from_document(document: dict[str, Any]) -> JobRecord:
    return JobRecord(
        owner_id=document["ownerId"],
        idempotency_key=document["idempotencyKey"],
        request_hash=document["requestHash"],
        response=JobResponse.model_validate(document["response"]),
    )
