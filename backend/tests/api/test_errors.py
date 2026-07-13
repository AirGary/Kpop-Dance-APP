def test_unknown_route_uses_error_envelope(client):
    response = client.get(
        "/missing",
        headers={"X-Request-ID": "request-test"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Resource was not found.",
            "requestId": "request-test",
        }
    }
    assert response.headers["X-Request-ID"] == "request-test"
