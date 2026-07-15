from dataclasses import dataclass
from pathlib import Path

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.adapters.auth.firebase_auth import FirebaseAuthVerifier
from api.app.adapters.auth.unavailable_auth import UnavailableAuthVerifier
from api.app.adapters.repositories.firestore_gateway import GoogleFirestoreGateway
from api.app.adapters.repositories.firestore_job_repository import (
    FirestoreJobRepository,
)
from api.app.adapters.repositories.firestore_upload_repository import (
    FirestoreUploadRepository,
)
from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.adapters.repositories.in_memory_upload_repository import (
    InMemoryUploadRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.adapters.storage.local_upload_object_store import LocalUploadObjectStore
from api.app.adapters.storage.cloud_job_object_store import CloudJobObjectStore
from api.app.adapters.storage.gcs_object_store import GCSObjectStore
from api.app.adapters.storage.gcs_upload_object_store import GCSUploadObjectStore
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
    def cloud(cls, settings: Settings) -> "AppContainer":
        project_id = _required_setting(
            "GOOGLE_CLOUD_PROJECT",
            settings.google_cloud_project,
        )
        source_bucket = _required_setting(
            "SOURCE_BUCKET_NAME",
            settings.source_bucket_name,
        )
        result_bucket = _required_setting(
            "RESULT_BUCKET_NAME",
            settings.result_bucket_name,
        )
        gateway = GoogleFirestoreGateway(project_id)
        upload_repository = FirestoreUploadRepository(gateway)
        source_store = GCSUploadObjectStore.from_bucket_name(source_bucket)
        job_service = JobService(
            FirestoreJobRepository(gateway),
            CloudJobObjectStore(
                GCSObjectStore.from_bucket_name(result_bucket),
                upload_repository,
                source_store,
            ),
        )
        return cls(
            auth_verifier=FirebaseAuthVerifier(project_id),
            job_service=job_service,
            upload_service=UploadService.direct(
                upload_repository,
                source_store,
                job_service,
            ),
        )

    @classmethod
    def for_settings(cls, settings: Settings) -> "AppContainer":
        if settings.environment == "development":
            return cls.development(settings.object_storage_root)
        if settings.environment == "cloud-bootstrap":
            return cls.cloud_bootstrap(settings.object_storage_root)
        if settings.environment == "cloud":
            return cls.cloud(settings)
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


def _required_setting(name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required in cloud environment.")
    return value
