import re

from api.app.ports.auth import AuthenticatedUser
from api.app.schemas.errors import APIError


_DEVELOPMENT_TOKEN = re.compile(r"^dev-[A-Za-z0-9_-]{1,64}$")


class DevelopmentAuthVerifier:
    async def verify(self, token: str) -> AuthenticatedUser:
        if not _DEVELOPMENT_TOKEN.fullmatch(token):
            raise APIError(401, "unauthorized", "Authentication is required.")
        return AuthenticatedUser(user_id=token)
