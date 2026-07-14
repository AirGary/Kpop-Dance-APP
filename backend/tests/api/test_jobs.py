from tests.factories import valid_job_data


def create_job(client, auth_headers, key="job-key", **overrides):
    return client.post(
        "/v1/jobs",
        headers={**auth_headers, "Idempotency-Key": key},
        json=valid_job_data(**overrides),
    )


def test_create_replay_and_conflict(client, auth_headers):
    created = create_job(client, auth_headers)
    replay = create_job(client, auth_headers)
    conflict = create_job(
        client,
        auth_headers,
        durationSeconds=120,
    )

    assert created.status_code == 201
    assert created.json()["state"] == "draft"
    assert created.json()["progress"] == 0
    assert replay.status_code == 200
    assert replay.json() == created.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_owner_can_read_and_delete_a_job(client, auth_headers):
    created = create_job(client, auth_headers)
    job_id = created.json()["id"]

    fetched = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    deleted = client.delete(f"/v1/jobs/{job_id}", headers=auth_headers)
    fetched_after_delete = client.get(
        f"/v1/jobs/{job_id}",
        headers=auth_headers,
    )

    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    assert deleted.status_code == 204
    assert not deleted.content
    assert fetched_after_delete.status_code == 404


def test_missing_idempotency_key_uses_validation_error(client, auth_headers):
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        json=valid_job_data(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
