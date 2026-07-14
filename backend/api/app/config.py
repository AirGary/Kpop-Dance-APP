import os
from pathlib import Path
import tempfile

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: str = "development"
    object_storage_root: Path = Path(tempfile.gettempdir()) / "stage-lab-objects"

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
        )
