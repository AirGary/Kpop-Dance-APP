from dataclasses import dataclass
from pathlib import Path

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.adapters.storage.local_upload_object_store import LocalUploadObjectStore
from api.app.ports.auth import AuthVerifier
from api.app.services.job_service import JobService
from api.app.services.upload_service import UploadService


@dataclass(frozen=True, slots=True)
class AppContainer:
    auth_verifier: AuthVerifier
    job_service: JobService
    upload_service: UploadService

    @classmethod
    def development(cls, object_storage_root: Path) -> "AppContainer":
        job_repository = InMemoryJobRepository()
        job_object_store = LocalObjectStore(object_storage_root)
        job_service = JobService(job_repository, job_object_store)
        return cls(
            auth_verifier=DevelopmentAuthVerifier(),
            job_service=job_service,
            upload_service=UploadService(
                InMemoryUploadRepository(),
                LocalUploadObjectStore(object_storage_root),
                job_service,
            ),
        )
