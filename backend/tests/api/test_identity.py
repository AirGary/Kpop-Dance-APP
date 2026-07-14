def test_me_returns_development_identity(client):
    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer dev-user-a"},
    )

    assert response.status_code == 200
    assert response.json() == {"userId": "dev-user-a"}


def test_me_rejects_missing_token(client):
    response = client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_rejects_non_development_token(client):
    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer production-user"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
