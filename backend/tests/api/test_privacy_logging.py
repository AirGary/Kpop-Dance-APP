import logging
import hashlib


def test_request_logs_do_not_contain_authorization_token(client, caplog):
    secret = "dev-private-token"
    caplog.set_level(logging.INFO, logger="stage_lab.requests")

    response = client.get(
        "/v1/me",
        headers={
            "Authorization": f"Bearer {secret}",
            "X-Request-ID": "privacy-log-test",
        },
    )

    assert response.status_code == 200
    assert secret not in caplog.text
    assert "Authorization" not in caplog.text
    assert "privacy-log-test" in caplog.text


def test_request_logs_do_not_contain_upload_token_or_query(client, caplog):
    caplog.set_level(logging.INFO, logger="stage_lab.requests")
    content = b"abc"
    created = client.post(
        "/v1/uploads",
        json={
            "projectId": "5dc6cb17-9df3-4f99-9f32-dd51e69f4430",
            "sourceFingerprint": "sha256:0123456789abcdef",
            "durationSeconds": 90,
            "byteCount": len(content),
            "mimeType": "video/mp4",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        headers={
            "Authorization": "Bearer dev-user-a",
            "Idempotency-Key": "privacy-create",
        },
    )
    upload_url = created.json()["uploadUrl"]
    token = upload_url.partition("token=")[2]

    client.head(upload_url)

    assert token not in caplog.text
    assert "?token=" not in caplog.text
    assert "sourceFingerprint" not in caplog.text
    assert hashlib.sha256(content).hexdigest() not in caplog.text
