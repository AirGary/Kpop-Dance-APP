from dataclasses import dataclass
from pathlib import Path

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.adapters.auth.firebase_auth import FirebaseAuthVerifier
from api.app.adapters.auth.unavailable_auth import UnavailableAuthVerifier
from api.app.adapters.analysis.local_analysis_runner import LocalAnalysisRunner
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
from api.app.adapters.repositories.file_analysis_repository import FileAnalysisRepository
from api.app.adapters.storage.local_analysis_workspace import LocalAnalysisWorkspace
from api.app.services.analysis_coordinator import AnalysisCoordinator


@dataclass(frozen=True, slots=True)
class AppContainer:
    auth_verifier: AuthVerifier
    job_service: JobService
    upload_service: UploadService
    analysis_coordinator: AnalysisCoordinator | None = None

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
        if settings.environment == "local-ai":
            return cls.local_ai(settings)
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

    @classmethod
    def local_ai(cls, settings: Settings) -> "AppContainer":
        auth = DevelopmentAuthVerifier()
        job_repository = InMemoryJobRepository()
        object_store = LocalObjectStore(settings.object_storage_root)
        job_service = JobService(job_repository, object_store)
        workspace = LocalAnalysisWorkspace(settings.object_storage_root)
        analysis_repository = FileAnalysisRepository(settings.object_storage_root)
        model_root = settings.local_ai_model_root or (Path(__file__).resolve().parents[3] / ".local-ai" / "models")
        repository_root = Path(__file__).resolve().parents[3]
        runner = LocalAnalysisRunner(
            settings.object_storage_root,
            repository_root / "backend" / "workers" / "analysis",
            model_root,
            repository_root / ".local-ai" / "venv" / "bin" / "python",
        )
        coordinator = AnalysisCoordinator(job_service, analysis_repository, workspace, runner)
        upload_service = UploadService(
            InMemoryUploadRepository(),
            LocalUploadObjectStore(settings.object_storage_root),
            job_service,
            on_completed=coordinator.on_upload_completed,
        )
        return cls(auth, job_service, upload_service, coordinator)


def _required_setting(name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required in cloud environment.")
    return value
