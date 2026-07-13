from dataclasses import dataclass
from pathlib import Path

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.adapters.repositories.in_memory_job_repository import (
    InMemoryJobRepository,
)
from api.app.adapters.storage.local_object_store import LocalObjectStore
from api.app.ports.auth import AuthVerifier
from api.app.services.job_service import JobService


@dataclass(frozen=True, slots=True)
class AppContainer:
    auth_verifier: AuthVerifier
    job_service: JobService

    @classmethod
    def development(cls, object_storage_root: Path) -> "AppContainer":
        repository = InMemoryJobRepository()
        object_store = LocalObjectStore(object_storage_root)
        return cls(
            auth_verifier=DevelopmentAuthVerifier(),
            job_service=JobService(repository, object_store),
        )
