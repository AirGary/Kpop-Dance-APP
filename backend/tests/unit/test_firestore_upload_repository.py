from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from api.app.adapters.repositories.firestore_upload_repository import (
    FirestoreUploadRepository,
)
from api.app.ports.upload_repository import (
    UploadIdempotencyConflictError,
    UploadSession,
)
from api.app.schemas.uploads import CreateUploadRequest
from tests.fake_firestore import FakeFirestoreGateway


def make_session(
    *,
    owner_id: str = "owner-a",
    idempotency_key: str = "upload-key",
    request_digest: str = "request-a",
    expires_at: datetime | None = None,
) -> UploadSession:
    return UploadSession(
        id=uuid4(),
        owner_id=owner_id,
        request=CreateUploadRequest.model_validate(
            {
                "projectId": UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430"),
                "sourceFingerprint": "sha256:0123456789abcdef",
                "durationSeconds": 90,
                "byteCount": 6,
                "mimeType": "video/mp4",
                "sha256": "a" * 64,
            }
        ),
        request_digest=request_digest,
        idempotency_key=idempotency_key,
        token_digest="token-digest",
        offset=0,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=24),
    )


@pytest.mark.asyncio
async def test_firestore_upload_replays_and_rejects_changed_request() -> None:
    repository = FirestoreUploadRepository(FakeFirestoreGateway())
    original = make_session()

    stored, created = await repository.create(original)
    replay, replay_created = await repository.create(make_session())

    assert stored == original
    assert created is True
    assert replay == original
    assert replay_created is False

    with pytest.raises(UploadIdempotencyConflictError):
        await repository.create(make_session(request_digest="request-b"))


@pytest.mark.asyncio
async def test_firestore_upload_replaces_stale_idempotency_index() -> None:
    gateway = FakeFirestoreGateway()
    repository = FirestoreUploadRepository(gateway)
    original = make_session()
    await repository.create(original)
    gateway.documents.pop(f"uploads/{original.id}")
    replacement = make_session()

    stored, created = await repository.create(replacement)

    assert created is True
    assert stored == replacement
    assert await repository.find_idempotent("owner-a", "upload-key") == replacement


@pytest.mark.asyncio
async def test_firestore_upload_offset_update_is_compare_and_set() -> None:
    repository = FirestoreUploadRepository(FakeFirestoreGateway())
    session = make_session()
    await repository.create(session)

    assert await repository.update_offset(session.id, expected=0, new=5) is True
    assert await repository.update_offset(session.id, expected=0, new=6) is False
    assert (await repository.get(session.id)).offset == 5


@pytest.mark.asyncio
async def test_firestore_upload_completion_expiration_and_delete() -> None:
    repository = FirestoreUploadRepository(FakeFirestoreGateway())
    expired = make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    active = make_session(idempotency_key="active-key")
    await repository.create(expired)
    await repository.create(active)
    job_id = uuid4()

    updated = await repository.update_token_digest(active.id, "rotated")
    await repository.claim_completion(
        active.id,
        "owner-a",
        datetime.now(UTC),
        "claim-a",
    )
    completed = await repository.mark_completed(active.id, job_id, "claim-a")

    assert updated.token_digest == "rotated"
    assert completed is not None
    assert completed.completed_job_id == job_id
    assert await repository.find_completed("owner-a", job_id) == completed
    assert await repository.find_completed("owner-b", job_id) is None
    assert await repository.expired_before(datetime.now(UTC)) == [expired]

    await repository.delete(active.id)
    assert await repository.get(active.id) is None
    assert await repository.find_idempotent("owner-a", "active-key") is None
    assert await repository.find_completed("owner-a", job_id) is None


@pytest.mark.asyncio
async def test_firestore_completion_and_deletion_claims_are_mutually_exclusive() -> None:
    gateway = FakeFirestoreGateway()
    repository = FirestoreUploadRepository(gateway)
    now = datetime.now(UTC)
    active = make_session(expires_at=now + timedelta(hours=1))
    await repository.create(active)

    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] == active.expires_at

    claimed = await repository.claim_completion(
        active.id,
        "owner-a",
        now,
        "claim-a",
    )

    assert claimed is not None
    assert claimed.state == "completing"
    assert claimed.completion_claim_id == "claim-a"
    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] is None
    assert await repository.claim_completion(
        active.id,
        "owner-a",
        now,
        "claim-b",
    ) is None
    await repository.release_completion(active.id, "claim-b")
    assert (await repository.get(active.id)).state == "completing"
    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] is None
    assert await repository.claim_deletion(active.id, "owner-a") is None

    reclaimed = await repository.claim_completion(
        active.id,
        "owner-a",
        now + timedelta(minutes=6),
        "claim-b",
    )
    assert reclaimed is not None
    assert reclaimed.completion_claim_id == "claim-b"

    await repository.release_completion(active.id, "claim-b")

    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] == active.expires_at


@pytest.mark.asyncio
async def test_firestore_expiry_cleanup_waits_for_completion_lease() -> None:
    gateway = FakeFirestoreGateway()
    repository = FirestoreUploadRepository(gateway)
    now = datetime.now(UTC)
    active = make_session(expires_at=now + timedelta(minutes=1))
    await repository.create(active)
    await repository.claim_completion(active.id, "owner-a", now, "claim-a")

    assert await repository.claim_expired(active.id, now + timedelta(minutes=2)) is None

    claimed = await repository.claim_expired(active.id, now + timedelta(minutes=6))

    assert claimed is not None
    assert claimed.state == "deleting"
    assert claimed.completion_claim_id is None
    assert claimed.completion_claim_expires_at is None
    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] is None


@pytest.mark.asyncio
async def test_firestore_abandon_claim_pauses_ttl_cleanup() -> None:
    gateway = FakeFirestoreGateway()
    repository = FirestoreUploadRepository(gateway)
    active = make_session()
    await repository.create(active)

    claimed = await repository.claim_deletion(active.id, "owner-a")

    assert claimed is not None
    assert claimed.state == "deleting"
    assert gateway.documents[f"uploads/{active.id}"]["ttlExpiresAt"] is None
