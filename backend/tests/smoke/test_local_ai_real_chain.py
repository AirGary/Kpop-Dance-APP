import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app


VIDEO = os.environ.get("STAGE_LAB_ACCEPTANCE_VIDEO")
pytestmark = pytest.mark.skipif(
    not VIDEO,
    reason="Set STAGE_LAB_ACCEPTANCE_VIDEO to run the local real-AI chain.",
)


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _upload(client: TestClient, path: Path, headers: dict[str, str]) -> str:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    created = client.post(
        "/v1/uploads",
        headers={**headers, "Idempotency-Key": "real-chain-create"},
        json={
            "projectId": "123e4567-e89b-12d3-a456-426614174000",
            "sourceFingerprint": f"sha256:{digest}",
            "durationSeconds": _duration(path),
            "byteCount": len(content),
            "mimeType": "video/mp4",
            "sha256": digest,
        },
    )
    assert created.status_code == 201
    upload_url = created.json()["uploadUrl"]
    upload_id = created.json()["uploadId"]
    chunk_size = 5_242_880
    for start in range(0, len(content), chunk_size):
        end = min(len(content), start + chunk_size)
        response = client.put(
            upload_url,
            content=content[start:end],
            headers={"Content-Range": f"bytes {start}-{end - 1}/{len(content)}"},
        )
        assert response.status_code == (201 if end == len(content) else 308)
    completed = client.post(
        f"/v1/uploads/{upload_id}/complete",
        headers={**headers, "Idempotency-Key": "real-chain-complete"},
    )
    assert completed.status_code == 201
    return completed.json()["id"]


def test_real_video_upload_candidates_restart_and_target_selection(tmp_path):
    path = Path(VIDEO).expanduser().resolve()
    model_root = Path(os.environ.get("LOCAL_AI_MODEL_ROOT", ".local-ai/models"))
    settings = Settings(
        environment="local-ai",
        object_storage_root=tmp_path,
        local_ai_model_root=model_root,
    )
    headers = {"Authorization": "Bearer dev-user-a"}

    with TestClient(create_app(settings=settings)) as client:
        job_id = _upload(client, path, headers)
        candidates = []
        for _ in range(420):
            response = client.get(f"/v1/jobs/{job_id}/dancers", headers=headers)
            assert response.status_code == 200
            candidates = response.json()
            if candidates:
                break
            client.get(f"/v1/jobs/{job_id}", headers=headers)
            import time
            time.sleep(1)
        assert len(candidates) >= 3
        assert all(len(item["representativeImagePaths"]) == 3 for item in candidates)

    with TestClient(create_app(settings=settings)) as restarted:
        recovered = restarted.get(f"/v1/jobs/{job_id}/dancers", headers=headers)
        assert recovered.status_code == 200
        assert recovered.json() == candidates
        selected = restarted.post(
            f"/v1/jobs/{job_id}/target",
            headers={**headers, "Idempotency-Key": "real-chain-target"},
            json={"candidateId": candidates[0]["candidateId"]},
        )
        assert selected.status_code == 200
        assert selected.json()["state"] in {"queued", "analyzing", "failedRecoverable"}
