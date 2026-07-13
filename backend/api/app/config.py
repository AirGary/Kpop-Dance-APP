from pathlib import Path
import tempfile

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: str = "development"
    object_storage_root: Path = Path(tempfile.gettempdir()) / "stage-lab-objects"
