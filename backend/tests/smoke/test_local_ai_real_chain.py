import hashlib
import io
import json
import os
import subprocess
import asyncio
import zipfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app
from api.app.ports.analysis_runner import TargetAnalysisAwaitingConfirmation, TargetAnalysisCompleted
from api.app.schemas.analysis import AnalysisResultResponse, DancerCandidateResponse, IdentityConfirmationResponse
from api.app.ports.job_repository import JobRecord
from api.app.schemas.analysis import AnalysisJobState
from api.app.schemas.jobs import JobResponse


VIDEO = os.environ.get("STAGE_LAB_ACCEPTANCE_VIDEO")
EXPECTED_PACKAGE_MEMBERS = (
    "confidence.json",
    "manifest.json",
    "pose-track.json",
    "spotlight-track.json",
    "timeline.json",
)


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _acceptance_metrics(
    analysis_directory: Path,
    candidate_id: str,
    package: Path,
    *,
    elapsed_seconds: float,
) -> dict[str, int | float | list[str]]:
    clusters = json.loads((analysis_directory / "identity-clusters.json").read_text(encoding="utf-8"))
    plan = json.loads((analysis_directory / "target-work-plan.json").read_text(encoding="utf-8"))
    fragments = {
        item["fragmentId"]: item
        for item in clusters["fragments"]
        if isinstance(item, dict) and isinstance(item.get("fragmentId"), int)
    }
    selected = clusters["candidateClusters"][candidate_id]
    accepted = plan["acceptedFragmentIds"]
    rejected = plan["excludedFragmentIds"]
    visible_duration = sum(
        float(fragments[fragment_id]["endSeconds"]) - float(fragments[fragment_id]["startSeconds"])
        for fragment_id in selected
    )
    accepted_duration = sum(
        float(fragments[fragment_id]["endSeconds"]) - float(fragments[fragment_id]["startSeconds"])
        for fragment_id in selected
        if fragment_id in accepted
    )
    awaiting = {
        decision["laterFragmentId"]
        for decision in clusters["decisions"]
        if isinstance(decision, dict)
        and decision.get("kind") == "awaiting_confirmation"
        and isinstance(decision.get("laterFragmentId"), int)
    }
    with zipfile.ZipFile(package) as archive:
        members = sorted(archive.namelist())
    assert tuple(members) == EXPECTED_PACKAGE_MEMBERS
    return {
        "elapsedSeconds": round(elapsed_seconds, 3),
        "candidateClusterCount": len(clusters["candidateClusters"]),
        "selectedCandidateVisibleDurationSeconds": round(visible_duration, 3),
        "acceptedFragmentCount": len(accepted),
        "rejectedFragmentCount": len(rejected),
        "awaitingConfirmationFragmentCount": len(awaiting),
        "packageMembers": members,
        "finalPoseCoverage": round(accepted_duration / visible_duration, 3) if visible_duration else 0.0,
    }


def _analysis_directory(root: Path, job_id: str) -> Path:
    return root / "dev-user-a" / job_id / "analysis"


def _assert_ambiguous_boundary_is_paused(analysis_directory: Path) -> None:
    clusters = json.loads((analysis_directory / "identity-clusters.json").read_text(encoding="utf-8"))
    plan = json.loads((analysis_directory / "target-work-plan.json").read_text(encoding="utf-8"))
    pending_fragment = plan["pendingFragmentId"]
    assert any(
        decision.get("kind") == "awaiting_confirmation"
        and decision.get("laterFragmentId") == pending_fragment
        for decision in clusters["decisions"]
        if isinstance(decision, dict)
    )
    checkpoints = analysis_directory / "target-checkpoints"
    checkpoint_ids = [path.stem for path in checkpoints.glob("*.json")] if checkpoints.exists() else []
    assert all(fragment_id.isdigit() and int(fragment_id) < pending_fragment for fragment_id in checkpoint_ids)
    assert not (analysis_directory / "result-v1.zip").exists()


def test_ambiguous_boundary_rejects_pending_or_later_pose_checkpoint(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "identity-clusters.json").write_text(json.dumps({
        "decisions": [{
            "kind": "awaiting_confirmation",
            "earlierFragmentId": 1,
            "laterFragmentId": 2,
        }],
    }), encoding="utf-8")
    (analysis / "target-work-plan.json").write_text(json.dumps({
        "pendingFragmentId": 2,
    }), encoding="utf-8")
    checkpoints = analysis / "target-checkpoints"
    checkpoints.mkdir()
    (checkpoints / "2.json").write_text("{}", encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_ambiguous_boundary_is_paused(analysis)


def _wait_for_result_with_same_decisions(
    client: TestClient,
    job_id: str,
    headers: dict[str, str],
    storage_root: Path,
) -> int:
    confirmations = 0
    for _ in range(600):
        state = client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert state.status_code == 200
        if state.json()["state"] == "resultReady":
            return confirmations
        if state.json()["state"] == "failedRecoverable":
            pytest.fail(f"target analysis failed: {state.json()}")
        if state.json()["state"] == "awaitingConfirmation":
            analysis_directory = _analysis_directory(storage_root, job_id)
            _assert_ambiguous_boundary_is_paused(analysis_directory)
            confirmation = client.get(f"/v1/jobs/{job_id}/identity-confirmation", headers=headers)
            assert confirmation.status_code == 200
            submitted = client.post(
                f"/v1/jobs/{job_id}/identity-confirmation",
                headers={**headers, "Idempotency-Key": f"real-chain-same-{confirmations}"},
                json={"confirmationId": confirmation.json()["confirmationId"], "decision": "same"},
            )
            assert submitted.status_code == 200
            confirmations += 1
        time.sleep(1)
    pytest.fail("target analysis did not reach resultReady")


def _write_scripted_v1_package(destination: Path) -> tuple[str, int]:
    payloads = {
        "confidence.json": [{"confidence": 0.9, "endSeconds": 1.0, "startSeconds": 0.0}],
        "pose-track.json": [{"confidence": 0.9, "keypoints": [], "timeSeconds": 0.0}],
        "spotlight-track.json": [{"confidence": 0.9, "height": 0.5, "timeSeconds": 0.0, "width": 0.3, "x": 0.2, "y": 0.1}],
        "timeline.json": [{"difficulty": "easy", "endSeconds": 1.0, "reasons": [], "startSeconds": 0.0}],
    }
    encoded = {
        member: (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        for member, value in payloads.items()
    }
    manifest = {
        "schemaVersion": 1,
        "memberHashes": {member: hashlib.sha256(encoded[member]).hexdigest() for member in encoded},
    }
    encoded["manifest.json"] = (json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for member in EXPECTED_PACKAGE_MEMBERS:
            archive.writestr(member, encoded[member])
    data = destination.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _assert_valid_v1_package(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert tuple(sorted(archive.namelist())) == EXPECTED_PACKAGE_MEMBERS
        manifest = json.loads(archive.read("manifest.json"))
        for member in EXPECTED_PACKAGE_MEMBERS:
            if member != "manifest.json":
                assert hashlib.sha256(archive.read(member)).hexdigest() == manifest["memberHashes"][member]


def test_acceptance_metrics_report_only_reproducible_aggregate_values(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "identity-clusters.json").write_text(json.dumps({
        "fragments": [
            {"fragmentId": 1, "startSeconds": 1, "endSeconds": 5},
            {"fragmentId": 2, "startSeconds": 5, "endSeconds": 6},
            {"fragmentId": 3, "startSeconds": 6, "endSeconds": 8},
        ],
        "candidateClusters": {"candidate-1": [1, 2], "candidate-2": [3]},
        "decisions": [{
            "kind": "awaiting_confirmation",
            "earlierFragmentId": 1,
            "laterFragmentId": 2,
        }],
    }), encoding="utf-8")
    (analysis / "target-work-plan.json").write_text(json.dumps({
        "acceptedFragmentIds": [1],
        "excludedFragmentIds": [3],
        "pendingFragmentId": 2,
    }), encoding="utf-8")
    package = analysis / "result-v1.zip"
    with zipfile.ZipFile(package, "w") as archive:
        for member in (
            "manifest.json", "pose-track.json", "spotlight-track.json",
            "timeline.json", "confidence.json",
        ):
            archive.writestr(member, "{}")

    metrics = _acceptance_metrics(analysis, "candidate-1", package, elapsed_seconds=12.5)

    assert metrics == {
        "elapsedSeconds": 12.5,
        "candidateClusterCount": 2,
        "selectedCandidateVisibleDurationSeconds": 5.0,
        "acceptedFragmentCount": 1,
        "rejectedFragmentCount": 1,
        "awaitingConfirmationFragmentCount": 1,
        "packageMembers": [
            "confidence.json", "manifest.json", "pose-track.json",
            "spotlight-track.json", "timeline.json",
        ],
        "finalPoseCoverage": 0.8,
    }


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


@pytest.mark.skipif(
    not VIDEO,
    reason="Set STAGE_LAB_ACCEPTANCE_VIDEO to run the local real-AI chain.",
)
def test_real_video_upload_candidates_restart_and_target_selection(tmp_path):
    started = time.monotonic()
    path = Path(VIDEO).expanduser().resolve()
    model_root = Path(os.environ.get("LOCAL_AI_MODEL_ROOT", ".local-ai/models"))
    settings = Settings(
        environment="local-ai",
        object_storage_root=tmp_path,
        local_ai_model_root=model_root,
        local_ai_frame_stride=int(os.environ.get("LOCAL_AI_FRAME_STRIDE", "6")),
        pairing_token="smoke-pairing-token",
    )
    headers = {
        "Authorization": "Bearer dev-user-a",
        "X-Stage-Lab-Pairing-Token": "smoke-pairing-token",
    }

    with TestClient(create_app(settings=settings)) as client:
        job_id = _upload(client, path, headers)
        candidates = []
        for _ in range(420):
            response = client.get(f"/v1/jobs/{job_id}/dancers", headers=headers)
            assert response.status_code == 200
            candidates = response.json()
            if candidates:
                break
            state = client.get(f"/v1/jobs/{job_id}", headers=headers)
            assert state.status_code == 200
            if state.json()["state"] == "failedRecoverable":
                pytest.fail(f"candidate detection failed: {state.json()}")
            time.sleep(1)
        assert 1 <= len(candidates) <= 8
        assert all(len(item["representativeImagePaths"]) == 3 for item in candidates)
        candidate_image_path = candidates[0]["representativeImagePaths"][0]
        candidate_image = client.get(
            f"/v1/jobs/{job_id}/content/{candidate_image_path}",
            headers=headers,
        )
        assert candidate_image.status_code == 200
        assert candidate_image.headers["content-type"].startswith("image/jpeg")

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
        assert selected.json()["state"] in {"queued", "analyzing", "resultReady", "failedRecoverable"}
        if selected.json()["state"] == "failedRecoverable":
            pytest.fail(f"target analysis failed: {selected.json()}")
        _wait_for_result_with_same_decisions(restarted, job_id, headers, tmp_path)
        result = restarted.get(f"/v1/jobs/{job_id}/result", headers=headers)
        assert result.status_code == 200
        assert result.json()["contentPath"] == "analysis/result-v1.zip"
        content = restarted.get(f"/v1/jobs/{job_id}/result/content", headers=headers)
        assert content.status_code == 200
        assert content.content[:2] == b"PK"
        analysis_directory = _analysis_directory(tmp_path, job_id)
        metrics = _acceptance_metrics(
            analysis_directory,
            candidates[0]["candidateId"],
            analysis_directory / "result-v1.zip",
            elapsed_seconds=time.monotonic() - started,
        )
        assert metrics["candidateClusterCount"] == len(candidates)
        assert metrics["candidateClusterCount"] <= 8
        assert metrics["finalPoseCoverage"] >= 0.8
        assert metrics["packageMembers"] == list(EXPECTED_PACKAGE_MEMBERS)
        print(json.dumps(metrics, sort_keys=True))


def test_synthetic_confirmation_fixture_contains_no_media(tmp_path):
    """Exercise owner-scoped confirmation GET/POST without video bytes or real models."""
    confirmation = IdentityConfirmationResponse.model_validate({
        "confirmationId": "synthetic-confirmation",
        "previousImagePath": "analysis/candidates/candidate-1-3.jpg",
        "candidateImagePath": "analysis/candidates/candidate-2-1.jpg",
        "previousInterval": {"startSeconds": 1, "endSeconds": 2},
        "candidateInterval": {"startSeconds": 2, "endSeconds": 3},
        "candidateClusterId": "candidate-2",
    })
    outcome = TargetAnalysisAwaitingConfirmation(confirmation)
    settings = Settings(
        environment="local-ai",
        object_storage_root=tmp_path,
        local_ai_model_root=tmp_path / "models",
        pairing_token="synthetic-pairing-token",
    )
    app = create_app(settings=settings)
    coordinator = app.state.container.analysis_coordinator
    assert coordinator is not None

    class SyntheticRunner:
        async def detect_candidates(self, owner_id, job_id):
            return []

        async def analyze_target(self, owner_id, job_id, candidate_id):
            return outcome

        async def shutdown(self):
            return None

    coordinator._runner = SyntheticRunner()
    job_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    now = datetime.now(UTC)
    response = JobResponse(
        id=job_id,
        projectId=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        state=AnalysisJobState.AWAITING_CONFIRMATION,
        progress=0.6,
        createdAt=now,
        updatedAt=now,
    )

    async def seed() -> None:
        await coordinator._jobs._repository.create(JobRecord("dev-user-a", "upload", "hash", response))
        await coordinator._repository.update("dev-user-a", job_id, response)
        await coordinator._repository.set_target_selection("dev-user-a", job_id, "candidate-1", "target-key")
        await coordinator._repository.set_identity_confirmation("dev-user-a", job_id, confirmation)

    asyncio.run(seed())
    headers = {
        "Authorization": "Bearer dev-user-a",
        "X-Stage-Lab-Pairing-Token": "synthetic-pairing-token",
    }
    with TestClient(app) as client:
        fetched = client.get(f"/v1/jobs/{job_id}/identity-confirmation", headers=headers)
        foreign = client.get(
            f"/v1/jobs/{job_id}/identity-confirmation",
            headers={**headers, "Authorization": "Bearer dev-user-b"},
        )
        submitted = client.post(
            f"/v1/jobs/{job_id}/identity-confirmation",
            headers={**headers, "Idempotency-Key": "synthetic-decision"},
            json={"confirmationId": "synthetic-confirmation", "decision": "same"},
        )

    assert fetched.status_code == 200
    assert fetched.json()["candidateClusterId"] == "candidate-2"
    assert foreign.status_code == 404
    assert submitted.status_code == 200
    assert submitted.json()["state"] == "queued"
    assert not list(tmp_path.rglob("*.mp4"))


@pytest.mark.parametrize("decision", ("same", "different"))
def test_scripted_identity_decision_reaches_valid_v1_package(tmp_path, decision):
    """Drive both decisions through the protected API without video or model bytes."""
    settings = Settings(
        environment="local-ai",
        object_storage_root=tmp_path,
        local_ai_model_root=tmp_path / "models",
        pairing_token="scripted-pairing-token",
    )
    app = create_app(settings=settings)
    coordinator = app.state.container.analysis_coordinator
    assert coordinator is not None
    job_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    confirmation = IdentityConfirmationResponse.model_validate({
        "confirmationId": "scripted-confirmation",
        "previousImagePath": "analysis/candidates/candidate-1-1.jpg",
        "candidateImagePath": "analysis/candidates/candidate-2-1.jpg",
        "previousInterval": {"startSeconds": 1, "endSeconds": 2},
        "candidateInterval": {"startSeconds": 2, "endSeconds": 3},
        "candidateClusterId": "candidate-2",
    })

    class ScriptedRunner:
        def __init__(self) -> None:
            self.calls = 0

        async def detect_candidates(self, owner_id, identifier):
            return []

        async def analyze_target(self, owner_id, identifier, candidate_id):
            self.calls += 1
            if self.calls == 1:
                return TargetAnalysisAwaitingConfirmation(confirmation)
            decision_payload = json.loads(
                (tmp_path / owner_id / str(identifier) / "analysis" / "identity-decision.json").read_text(encoding="utf-8")
            )
            assert decision_payload["decisions"][-1]["decision"] == decision
            package = tmp_path / owner_id / str(identifier) / "analysis" / "result-v1.zip"
            digest, byte_count = _write_scripted_v1_package(package)
            return TargetAnalysisCompleted(AnalysisResultResponse.model_validate({
                "schemaVersion": 1,
                "sha256": digest,
                "byteCount": byte_count,
                "contentPath": "analysis/result-v1.zip",
            }))

        async def shutdown(self):
            return None

    coordinator._runner = ScriptedRunner()
    now = datetime.now(UTC)
    response = JobResponse(
        id=job_id,
        projectId=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        state=AnalysisJobState.AWAITING_TARGET,
        progress=0.5,
        createdAt=now,
        updatedAt=now,
    )
    candidate = DancerCandidateResponse.model_validate({
        "candidateId": "candidate-1",
        "representativeImagePaths": [
            "analysis/candidates/candidate-1-1.jpg",
            "analysis/candidates/candidate-1-2.jpg",
            "analysis/candidates/candidate-1-3.jpg",
        ],
        "appearanceIntervals": [{"startSeconds": 1, "endSeconds": 3}],
        "boxSummary": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.6},
        "confidence": 0.9,
    })

    async def seed() -> None:
        await coordinator._jobs._repository.create(JobRecord("dev-user-a", "upload", "hash", response))
        await coordinator._repository.update("dev-user-a", job_id, response)
        await coordinator._repository.set_candidates("dev-user-a", job_id, [candidate])

    asyncio.run(seed())
    headers = {
        "Authorization": "Bearer dev-user-a",
        "X-Stage-Lab-Pairing-Token": "scripted-pairing-token",
    }
    with TestClient(app) as client:
        selected = client.post(
            f"/v1/jobs/{job_id}/target",
            headers={**headers, "Idempotency-Key": f"scripted-target-{decision}"},
            json={"candidateId": "candidate-1"},
        )
        assert selected.status_code == 200
        for _ in range(100):
            state = client.get(f"/v1/jobs/{job_id}", headers=headers)
            if state.json()["state"] == "awaitingConfirmation":
                break
            time.sleep(0.01)
        assert state.json()["state"] == "awaitingConfirmation"
        package = tmp_path / "dev-user-a" / str(job_id) / "analysis" / "result-v1.zip"
        assert not package.exists()
        submitted = client.post(
            f"/v1/jobs/{job_id}/identity-confirmation",
            headers={**headers, "Idempotency-Key": f"scripted-decision-{decision}"},
            json={"confirmationId": "scripted-confirmation", "decision": decision},
        )
        assert submitted.status_code == 200
        for _ in range(100):
            state = client.get(f"/v1/jobs/{job_id}", headers=headers)
            if state.json()["state"] == "resultReady":
                break
            time.sleep(0.01)
        assert state.json()["state"] == "resultReady"
        content = client.get(f"/v1/jobs/{job_id}/result/content", headers=headers)

    assert content.status_code == 200
    _assert_valid_v1_package(content.content)
    assert not list(tmp_path.rglob("*.mp4"))
