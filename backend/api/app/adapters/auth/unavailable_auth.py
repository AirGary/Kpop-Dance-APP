from api.app.ports.auth import AuthenticatedUser
from api.app.schemas.errors import APIError


class UnavailableAuthVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        raise APIError(401, "unauthorized", "Authentication is required.")
