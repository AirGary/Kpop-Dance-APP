from dataclasses import dataclass

from api.app.adapters.auth.development_auth import DevelopmentAuthVerifier
from api.app.ports.auth import AuthVerifier


@dataclass(frozen=True, slots=True)
class AppContainer:
    auth_verifier: AuthVerifier

    @classmethod
    def development(cls) -> "AppContainer":
        return cls(auth_verifier=DevelopmentAuthVerifier())
