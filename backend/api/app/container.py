from dataclasses import dataclass
from pathlib import Path

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.adapters.auth.unavailable_auth import UnavailableAuthVerifier
from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.adapters.storage.local_upload_object_store import LocalUploadObjectStore
from api.app.ports.auth import AuthVerifier
from api.app.config import Settings
from api.app.services.job_service import JobService
from api.app.services.upload_service import UploadService


@dataclass(frozen=True, slots=True)
class AppContainer:
    auth_verifier: AuthVerifier
    job_service: JobService
    upload_service: UploadService

    @classmethod
    def development(cls, object_storage_root: Path) -> "AppContainer":
        return cls._local(object_storage_root, DevelopmentAuthVerifier())

    @classmethod
    def cloud_bootstrap(cls, object_storage_root: Path) -> "AppContainer":
        return cls._local(object_storage_root, UnavailableAuthVerifier())

    @classmethod
    def for_settings(cls, settings: Settings) -> "AppContainer":
        if settings.environment == "development":
            return cls.development(settings.object_storage_root)
        if settings.environment == "cloud-bootstrap":
            return cls.cloud_bootstrap(settings.object_storage_root)
        raise ValueError(f"Unsupported environment: {settings.environment}")

    @classmethod
    def _local(
        cls,
        object_storage_root: Path,
        auth_verifier: AuthVerifier,
    ) -> "AppContainer":
        job_repository = InMemoryJobRepository()
        job_object_store = LocalObjectStore(object_storage_root)
        job_service = JobService(job_repository, job_object_store)
        return cls(
            auth_verifier=auth_verifier,
            job_service=job_service,
            upload_service=UploadService(
                InMemoryUploadRepository(),
                LocalUploadObjectStore(object_storage_root),
                job_service,
            ),
        )
