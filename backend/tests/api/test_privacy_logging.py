import logging


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
