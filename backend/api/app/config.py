import os
from pathlib import Path
import tempfile

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: str = "development"
    object_storage_root: Path = Path(tempfile.gettempdir()) / "stage-lab-objects"
    google_cloud_project: str | None = None
    source_bucket_name: str | None = None
    result_bucket_name: str | None = None
    local_ai_model_root: Path | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        storage_root = os.environ.get("OBJECT_STORAGE_ROOT")
        return cls(
            environment=os.environ.get("APP_ENVIRONMENT", "development"),
            object_storage_root=(
                Path(storage_root)
                if storage_root
                else Path(tempfile.gettempdir()) / "stage-lab-objects"
            ),
            google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            source_bucket_name=os.environ.get("SOURCE_BUCKET_NAME"),
            result_bucket_name=os.environ.get("RESULT_BUCKET_NAME"),
            local_ai_model_root=(Path(os.environ["LOCAL_AI_MODEL_ROOT"]) if os.environ.get("LOCAL_AI_MODEL_ROOT") else None),
        )
