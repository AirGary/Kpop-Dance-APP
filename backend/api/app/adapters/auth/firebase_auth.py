import asyncio
import threading
from collections.abc import Callable, Mapping
from typing import Any

from api.app.ports.auth import AuthenticatedUser
from api.app.schemas.errors import APIError


TokenDecoder = Callable[[str, str], Mapping[str, Any]]
_FIREBASE_APP_LOCK = threading.Lock()


class FirebaseAuthVerifier:
    def __init__(
        self,
        project_id: str,
        *,
        decoder: TokenDecoder | None = None,
    ) -> None:
        if not project_id:
            raise ValueError("Firebase project ID is required.")
        self._project_id = project_id
        self._decoder = decoder or _decode_firebase_token

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            claims = await asyncio.to_thread(
                self._decoder,
                token,
                self._project_id,
            )
            uid = claims.get("uid")
            if not isinstance(uid, str) or not uid:
                raise ValueError("Firebase token has no UID.")
        except Exception as error:
            raise APIError(
                401,
                "unauthorized",
                "Authentication is required.",
            ) from error
        return AuthenticatedUser(user_id=uid)


def _decode_firebase_token(token: str, project_id: str) -> Mapping[str, Any]:
    import firebase_admin
    from firebase_admin import auth

    app_name = f"stage-lab-{project_id}"
    with _FIREBASE_APP_LOCK:
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            app = firebase_admin.initialize_app(
                options={"projectId": project_id},
                name=app_name,
            )
    return auth.verify_id_token(token, app=app)
