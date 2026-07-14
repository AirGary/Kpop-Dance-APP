import hashlib
from uuid import UUID


PROJECT_ID = UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430")


def upload_body(content: bytes, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "projectId": str(PROJECT_ID),
        "sourceFingerprint": "sha256:0123456789abcdef",
        "durationSeconds": 90,
        "byteCount": len(content),
        "mimeType": "video/mp4",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    body.update(overrides)
    return body


def create_upload(client, auth_headers, content: bytes = b"abcdef"):
    return client.post(
        "/v1/uploads",
        json=upload_body(content),
        headers={**auth_headers, "Idempotency-Key": "create-key"},
    )


def test_upload_resume_and_complete(client, auth_headers) -> None:
    created = create_upload(client, auth_headers)

    assert created.status_code == 201
    payload = created.json()
    assert payload["chunkSize"] == 5_242_880
    assert payload["offset"] == 0
    upload_url = payload["uploadUrl"]

    first = client.put(
        upload_url,
        content=b"abc",
        headers={"Content-Range": "bytes 0-2/6"},
    )
    assert first.status_code == 308
    assert first.headers["Upload-Offset"] == "3"

    offset = client.head(upload_url)
    assert offset.status_code == 204
    assert offset.headers["Upload-Offset"] == "3"
    assert offset.headers["Upload-Length"] == "6"
    assert offset.headers["Upload-Expires"] == payload["expiresAt"]

    final = client.put(
        upload_url,
        content=b"def",
        headers={"Content-Range": "bytes 3-5/6"},
    )
    assert final.status_code == 201
    assert final.headers["Upload-Offset"] == "6"

    completed = client.post(
        f'/v1/uploads/{payload["uploadId"]}/complete',
        headers={**auth_headers, "Idempotency-Key": "complete-key"},
    )
    assert completed.status_code == 201
    assert completed.json()["state"] == "draft"

    fetched = client.get(
        f'/v1/jobs/{completed.json()["id"]}',
        headers=auth_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json() == completed.json()


def test_create_session_replay_rotates_signed_token(client, auth_headers) -> None:
    first = create_upload(client, auth_headers)
    second = create_upload(client, auth_headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["uploadId"] == second.json()["uploadId"]
    assert first.json()["uploadUrl"] != second.json()["uploadUrl"]
    assert client.head(first.json()["uploadUrl"]).status_code == 404
    assert client.head(second.json()["uploadUrl"]).status_code == 204


def test_changed_create_idempotency_body_conflicts(client, auth_headers) -> None:
    assert create_upload(client, auth_headers).status_code == 201

    changed = client.post(
        "/v1/uploads",
        json=upload_body(b"different"),
        headers={**auth_headers, "Idempotency-Key": "create-key"},
    )

    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"


def test_create_and_complete_require_authentication(client, auth_headers) -> None:
    unauthenticated = client.post(
        "/v1/uploads",
        json=upload_body(b"abc"),
        headers={"Idempotency-Key": "key"},
    )
    assert unauthenticated.status_code == 401

    created = create_upload(client, auth_headers, b"abc")
    completion = client.post(
        f'/v1/uploads/{created.json()["uploadId"]}/complete',
        headers={"Idempotency-Key": "complete"},
    )
    assert completion.status_code == 401


def test_invalid_token_and_unknown_upload_share_safe_error(client, auth_headers) -> None:
    created = create_upload(client, auth_headers, b"abc")
    invalid_url = created.json()["uploadUrl"].replace("token=", "token=wrong-")

    invalid = client.head(invalid_url)
    unknown = client.head(
        "http://testserver/v1/uploads/00000000-0000-0000-0000-000000000000/content?token=wrong"
    )

    assert invalid.status_code == unknown.status_code == 404

    invalid_put = client.put(
        invalid_url,
        content=b"abc",
        headers={"Content-Range": "bytes 0-2/3"},
    )
    assert invalid_put.status_code == 404
    assert invalid_put.json()["error"]["code"] == "upload_not_found"


def test_foreign_owner_cannot_complete_upload(client, auth_headers) -> None:
    created = create_upload(client, auth_headers, b"abc")
    client.put(
        created.json()["uploadUrl"],
        content=b"abc",
        headers={"Content-Range": "bytes 0-2/3"},
    )

    response = client.post(
        f'/v1/uploads/{created.json()["uploadId"]}/complete',
        headers={
            "Authorization": "Bearer dev-user-b",
            "Idempotency-Key": "complete",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "upload_not_found"


def test_chunk_rejects_bad_range_and_incomplete_completion(client, auth_headers) -> None:
    created = create_upload(client, auth_headers)
    upload_url = created.json()["uploadUrl"]

    bad_range = client.put(
        upload_url,
        content=b"abc",
        headers={"Content-Range": "invalid"},
    )
    assert bad_range.status_code == 422
    assert bad_range.json()["error"]["code"] == "validation_error"

    incomplete = client.post(
        f'/v1/uploads/{created.json()["uploadId"]}/complete',
        headers={**auth_headers, "Idempotency-Key": "complete"},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["error"]["code"] == "upload_incomplete"


def test_checksum_mismatch_returns_422(client, auth_headers) -> None:
    body = upload_body(b"abc", sha256="0" * 64)
    created = client.post(
        "/v1/uploads",
        json=body,
        headers={**auth_headers, "Idempotency-Key": "create"},
    )
    client.put(
        created.json()["uploadUrl"],
        content=b"abc",
        headers={"Content-Range": "bytes 0-2/3"},
    )

    completed = client.post(
        f'/v1/uploads/{created.json()["uploadId"]}/complete',
        headers={**auth_headers, "Idempotency-Key": "complete"},
    )

    assert completed.status_code == 422
    assert completed.json()["error"]["code"] == "checksum_mismatch"
