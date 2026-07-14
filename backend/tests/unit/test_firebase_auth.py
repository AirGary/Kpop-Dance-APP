import pytest

from api.app.adapters.auth.firebase_auth import FirebaseAuthVerifier
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
