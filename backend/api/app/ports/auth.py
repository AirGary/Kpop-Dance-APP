from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str


class AuthVerifier(Protocol):
    async def verify(self, token: str) -> AuthenticatedUser: ...
