def test_openapi_exposes_only_approved_operations(client):
    schema = client.get("/openapi.json").json()
    operations = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in path_item
    }

    assert operations == {
        ("GET", "/healthz"),
        ("GET", "/v1/me"),
        ("POST", "/v1/jobs"),
        ("GET", "/v1/jobs/{job_id}"),
        ("DELETE", "/v1/jobs/{job_id}"),
    }
