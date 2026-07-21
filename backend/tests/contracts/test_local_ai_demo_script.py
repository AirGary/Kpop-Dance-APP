from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "run-local-ai-demo.sh"


def test_local_ai_demo_script_has_safe_startup_contract():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'default_bind="127.0.0.1"' in source
    assert 'APP_ENVIRONMENT="local-ai"' in source
    assert 'api_python="$backend_root/.venv/bin/python"' in source
    assert 'worker_python="$local_root/venv/bin/python"' in source
    assert "X-Stage-Lab-Pairing-Token" not in source
    assert "openssl rand -hex" in source
    assert "trap cleanup EXIT INT TERM" in source
    assert "private IPv4" in source


def test_local_ai_demo_script_does_not_commit_runtime_configuration():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "mktemp -d" in source
    assert "chmod 600" in source
    assert "STAGE_LAB_PAIRING_ENV_FILE" in source
    assert "git" not in source
