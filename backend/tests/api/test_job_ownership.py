from tests.factories import valid_job_data


def test_foreign_owner_cannot_read_or_delete_job(client):
    owner_headers = {
        "Authorization": "Bearer dev-user-a",
        "Idempotency-Key": "owner-key",
    }
    created = client.post(
        "/v1/jobs",
        headers=owner_headers,
        json=valid_job_data(),
    )
    job_id = created.json()["id"]
    foreign_headers = {
        "Authorization": "Bearer dev-user-b",
        "X-Request-ID": "ownership-test",
    }

    read_response = client.get(
        f"/v1/jobs/{job_id}",
        headers=foreign_headers,
    )
    delete_response = client.delete(
        f"/v1/jobs/{job_id}",
        headers=foreign_headers,
    )

    assert read_response.status_code == 404
    assert delete_response.status_code == 404
    assert read_response.json() == delete_response.json()
    assert read_response.json()["error"]["code"] == "job_not_found"
    assert client.get(
        f"/v1/jobs/{job_id}",
        headers={"Authorization": "Bearer dev-user-a"},
    ).status_code == 200
