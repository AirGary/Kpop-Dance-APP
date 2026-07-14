def test_health_is_public(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "development"}
    assert response.headers["X-Request-ID"]
