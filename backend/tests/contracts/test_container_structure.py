from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_is_pinned_non_root_and_port_aware():
    source = (BACKEND_ROOT / "Dockerfile").read_text()

    assert "python:3.13-slim@sha256:" in source
    assert "USER stage-lab" in source
    assert "uvicorn api.app.main:app" in source
    assert "${PORT:-8080}" in source
    assert "--host 0.0.0.0" in source


def test_docker_context_excludes_development_and_user_data():
    patterns = (BACKEND_ROOT / ".dockerignore").read_text().splitlines()

    required_patterns = [
        ".venv",
        "tests",
        "**/__pycache__",
        ".pytest_cache",
        ".git",
        "stage-lab-objects",
    ]
    for required in required_patterns:
        assert required in patterns
