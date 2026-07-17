def test_target_endpoint_requires_idempotency_key(client, auth_headers):
    response = client.post(
        "/v1/jobs/11111111-1111-1111-1111-111111111111/target",
        headers=auth_headers,
        json={"candidateId": "candidate-1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
