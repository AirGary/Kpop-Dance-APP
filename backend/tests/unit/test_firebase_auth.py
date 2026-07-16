import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from api.app.adapters.auth.firebase_auth import (
    FirebaseAuthVerifier,
    _decode_firebase_token,
)
from api.app.schemas.errors import APIError


@pytest.mark.asyncio
async def test_firebase_auth_returns_authenticated_uid() -> None:
    calls: list[tuple[str, str]] = []

    def decode(token: str, project_id: str) -> dict[str, object]:
        calls.append((token, project_id))
        return {"uid": "firebase-user-123"}

    verifier = FirebaseAuthVerifier("stage-lab-project", decoder=decode)

    user = await verifier.verify("firebase-token")

    assert user.user_id == "firebase-user-123"
    assert calls == [("firebase-token", "stage-lab-project")]


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [{}, {"uid": ""}, {"uid": 123}])
async def test_firebase_auth_rejects_missing_or_invalid_uid(
    claims: dict[str, object],
) -> None:
    verifier = FirebaseAuthVerifier(
        "stage-lab-project",
        decoder=lambda _token, _project_id: claims,
    )

    with pytest.raises(APIError) as caught:
        await verifier.verify("firebase-token")

    assert caught.value.status_code == 401
    assert caught.value.code == "unauthorized"
    assert caught.value.message == "Authentication is required."


@pytest.mark.asyncio
async def test_firebase_auth_hides_decoder_failure() -> None:
    def decode(_token: str, _project_id: str) -> dict[str, object]:
        raise ValueError("sensitive provider detail")

    verifier = FirebaseAuthVerifier("stage-lab-project", decoder=decode)

    with pytest.raises(APIError) as caught:
        await verifier.verify("bad-token")

    assert caught.value.code == "unauthorized"
    assert "sensitive" not in caught.value.message


def test_firebase_app_initialization_is_thread_safe(monkeypatch) -> None:
    apps: dict[str, object] = {}
    initialize_calls = 0

    def get_app(name: str) -> object:
        if name in apps:
            return apps[name]
        time.sleep(0.02)
        raise ValueError("app does not exist")

    def initialize_app(*, options: dict[str, str], name: str) -> object:
        nonlocal initialize_calls
        initialize_calls += 1
        if name in apps:
            raise ValueError("app already exists")
        app = {"name": name, "options": options}
        apps[name] = app
        return app

    auth = SimpleNamespace(
        verify_id_token=lambda token, *, app: {"uid": f"{token}:{app['name']}"}
    )
    firebase_admin = SimpleNamespace(
        auth=auth,
        get_app=get_app,
        initialize_app=initialize_app,
    )
    monkeypatch.setitem(sys.modules, "firebase_admin", firebase_admin)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", auth)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda token: _decode_firebase_token(token, "stage-lab-project"),
                ["token-a", "token-b"],
            )
        )

    assert initialize_calls == 1
    assert [result["uid"] for result in results] == [
        "token-a:stage-lab-stage-lab-project",
        "token-b:stage-lab-stage-lab-project",
    ]
