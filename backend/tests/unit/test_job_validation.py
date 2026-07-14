import pytest
from pydantic import ValidationError

from api.app.schemas.jobs import CreateJobRequest
from tests.factories import valid_job_data


@pytest.mark.parametrize("duration", [0, -1, 360.0001])
def test_duration_outside_supported_range_is_rejected(duration):
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(
            valid_job_data(durationSeconds=duration)
        )


@pytest.mark.parametrize("duration", [0.001, 360])
def test_duration_boundary_is_accepted(duration):
    request = CreateJobRequest.model_validate(
        valid_job_data(durationSeconds=duration)
    )

    assert request.duration_seconds == duration


@pytest.mark.parametrize("byte_count", [0, -1, 2_147_483_649])
def test_file_size_outside_supported_range_is_rejected(byte_count):
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(valid_job_data(byteCount=byte_count))


@pytest.mark.parametrize("mime_type", ["video/mp4", "video/quicktime"])
def test_supported_video_mime_types_are_accepted(mime_type):
    request = CreateJobRequest.model_validate(valid_job_data(mimeType=mime_type))

    assert request.mime_type == mime_type


def test_unsupported_mime_type_is_rejected():
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(valid_job_data(mimeType="text/plain"))


def test_invalid_fingerprint_is_rejected():
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(valid_job_data(sourceFingerprint="../bad"))
