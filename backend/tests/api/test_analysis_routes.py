def test_target_endpoint_requires_idempotency_key(client, auth_headers):
    response = client.post(
        "/v1/jobs/11111111-1111-1111-1111-111111111111/target",
        headers=auth_headers,
        json={"candidateId": "candidate-1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_identity_confirmation_endpoints_require_identity_and_valid_job_identifier(client, auth_headers):
    unauthenticated = client.get(
        "/v1/jobs/11111111-1111-1111-1111-111111111111/identity-confirmation"
    )
    malformed = client.post(
        "/v1/jobs/not-a-uuid/identity-confirmation",
        headers={**auth_headers, "Idempotency-Key": "identity-key"},
        json={"confirmationId": "confirm-1", "decision": "same"},
    )
    invalid_decision = client.post(
        "/v1/jobs/11111111-1111-1111-1111-111111111111/identity-confirmation",
        headers={**auth_headers, "Idempotency-Key": "identity-key"},
        json={"confirmationId": "confirm-1", "decision": "maybe"},
    )

    assert unauthenticated.status_code == 401
    assert malformed.status_code == 422
    assert invalid_decision.status_code == 422
