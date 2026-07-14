from uuid import UUID


PROJECT_ID = UUID("5dc6cb17-9df3-4f99-9f32-dd51e69f4430")


def valid_job_data(**overrides):
    data = {
        "projectId": str(PROJECT_ID),
        "sourceFingerprint": "sha256:0123456789abcdef",
        "durationSeconds": 180.5,
        "byteCount": 104_857_600,
        "mimeType": "video/mp4",
    }
    data.update(overrides)
    return data
