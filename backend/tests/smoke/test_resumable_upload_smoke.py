import hashlib


def test_resumable_upload_creates_fetchable_draft_job(client, auth_headers) -> None:
    content = b"\x00\x00\x00\x18ftypmp42stage-lab-video-bytes"
    created = client.post(
        "/v1/uploads",
        headers={**auth_headers, "Idempotency-Key": "smoke-create"},
        json={
            "projectId": "123e4567-e89b-12d3-a456-426614174000",
            "sourceFingerprint": "smoke:video:001",
            "durationSeconds": 10,
            "byteCount": len(content),
            "mimeType": "video/mp4",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    assert created.status_code == 201
    upload_url = created.json()["uploadUrl"]
    upload_id = created.json()["uploadId"]

    split = 11
    first_range = f"bytes 0-{split - 1}/{len(content)}"
    first = client.put(
        upload_url,
        content=content[:split],
        headers={"Content-Range": first_range},
    )
    assert first.status_code == 308
    assert first.headers["Upload-Offset"] == str(split)

    replay = client.put(
        upload_url,
        content=content[:split],
        headers={"Content-Range": first_range},
    )
    assert replay.status_code == 308
    assert replay.headers["Upload-Offset"] == str(split)

    resumed = client.head(upload_url)
    assert resumed.status_code == 204
    assert resumed.headers["Upload-Offset"] == str(split)

    final = client.put(
        upload_url,
        content=content[split:],
        headers={
            "Content-Range": f"bytes {split}-{len(content) - 1}/{len(content)}"
        },
    )
    assert final.status_code == 201
    assert final.headers["Upload-Offset"] == str(len(content))

    completed = client.post(
        f"/v1/uploads/{upload_id}/complete",
        headers={**auth_headers, "Idempotency-Key": "smoke-complete"},
    )
    assert completed.status_code == 201
    assert completed.json()["state"] == "draft"

    fetched = client.get(f'/v1/jobs/{completed.json()["id"]}', headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == completed.json()
