def test_openapi_exposes_only_approved_operations(client):
    schema = client.get("/openapi.json").json()
    operations = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in path_item
    }

    assert operations == {
        ("GET", "/health"),
        ("GET", "/v1/me"),
        ("POST", "/v1/jobs"),
        ("GET", "/v1/jobs/{job_id}"),
        ("DELETE", "/v1/jobs/{job_id}"),
        ("POST", "/v1/uploads"),
        ("DELETE", "/v1/uploads/{upload_id}"),
        ("HEAD", "/v1/uploads/{upload_id}/content"),
        ("PUT", "/v1/uploads/{upload_id}/content"),
        ("POST", "/v1/uploads/{upload_id}/complete"),
    }
