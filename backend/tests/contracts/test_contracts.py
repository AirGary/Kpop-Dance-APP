import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.app.schemas.analysis import (
    AnalysisJobState,
    AnalysisResultResponse,
    DancerCandidateResponse,
    SelectTargetRequest,
)
from api.app.schemas.errors import ErrorEnvelope
from api.app.schemas.identity import IdentityResponse
from api.app.schemas.jobs import JobResponse
from api.app.schemas.uploads import UploadSessionResponse


FIXTURES = Path(__file__).parents[2] / "contracts" / "fixtures"


def assert_fixture_round_trips(name, model_type):
    payload = json.loads((FIXTURES / name).read_text())
    model = model_type.model_validate(payload)

    assert model.model_dump(mode="json", by_alias=True) == payload


def test_identity_fixture_round_trips():
    assert_fixture_round_trips("identity.json", IdentityResponse)


def test_job_fixture_round_trips():
    assert_fixture_round_trips("job.json", JobResponse)


def test_error_fixture_round_trips():
    assert_fixture_round_trips("error.json", ErrorEnvelope)


def test_upload_session_fixture_round_trips():
    assert_fixture_round_trips("upload-session.json", UploadSessionResponse)


def test_dancers_fixture_round_trips():
    payload = json.loads((FIXTURES / "dancers.json").read_text())
    dancers = [DancerCandidateResponse.model_validate(item) for item in payload]

    assert [dancer.model_dump(mode="json", by_alias=True) for dancer in dancers] == payload


def test_analysis_result_fixture_round_trips():
    assert_fixture_round_trips("analysis-result.json", AnalysisResultResponse)


def test_analysis_contract_uses_all_swift_state_raw_values_and_aliases():
    assert {state.value for state in AnalysisJobState} == {
        "draft",
        "preparing",
        "uploading",
        "uploaded",
        "detecting",
        "awaitingTarget",
        "queued",
        "analyzing",
        "awaitingConfirmation",
        "resultReady",
        "importing",
        "completed",
        "failedRecoverable",
        "failedTerminal",
        "cancelling",
        "deleted",
    }
    assert SelectTargetRequest.model_validate(
        {"candidateId": "candidate-1"}
    ).model_dump(by_alias=True) == {"candidateId": "candidate-1"}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "candidateId": "candidate-1",
            "representativeImagePaths": ["one", "two"],
            "appearanceIntervals": [{"startSeconds": 1, "endSeconds": 2}],
            "boxSummary": {"x": 0, "y": 0, "width": 1, "height": 1},
            "confidence": 0.5,
        },
        {
            "candidateId": "candidate-1",
            "representativeImagePaths": ["one", "two", "three"],
            "appearanceIntervals": [{"startSeconds": 2, "endSeconds": 1}],
            "boxSummary": {"x": 0, "y": 0, "width": 1, "height": 1},
            "confidence": 0.5,
        },
        {
            "candidateId": "candidate-1",
            "representativeImagePaths": ["one", "two", "three"],
            "appearanceIntervals": [{"startSeconds": 1, "endSeconds": 2}],
            "boxSummary": {"x": 0.9, "y": 0, "width": 0.2, "height": 1},
            "confidence": 0.5,
        },
        {
            "candidateId": "candidate-1",
            "representativeImagePaths": ["one", "two", "three"],
            "appearanceIntervals": [{"startSeconds": 1, "endSeconds": 2}],
            "boxSummary": {"x": 0, "y": 0, "width": 1, "height": 1},
            "confidence": 1.01,
        },
    ],
)
def test_dancer_candidate_rejects_invalid_boundaries(payload):
    with pytest.raises(ValidationError):
        DancerCandidateResponse.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"schemaVersion": 2, "sha256": "a" * 64, "byteCount": 1, "contentPath": "analysis/result.json"},
        {"schemaVersion": 1, "sha256": "A" * 64, "byteCount": 1, "contentPath": "analysis/result.json"},
        {"schemaVersion": 1, "sha256": "a" * 64, "byteCount": 0, "contentPath": "analysis/result.json"},
        {"schemaVersion": 1, "sha256": "a" * 64, "byteCount": 1, "contentPath": "/tmp/result.json"},
        {"schemaVersion": 1, "sha256": "a" * 64, "byteCount": 1, "contentPath": "../result.json"},
    ],
)
def test_analysis_result_rejects_invalid_metadata_boundaries(payload):
    with pytest.raises(ValidationError):
        AnalysisResultResponse.model_validate(payload)
