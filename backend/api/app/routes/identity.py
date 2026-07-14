from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.app.ports.auth import AuthenticatedUser
from api.app.schemas.errors import APIError
from api.app.schemas.identity import IdentityResponse


router = APIRouter(prefix="/v1")


async def authenticated_user(request: Request) -> AuthenticatedUser:
    values = request.headers.getlist("Authorization")
    if len(values) != 1:
        raise APIError(401, "unauthorized", "Authentication is required.")

    scheme, separator, token = values[0].partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token or " " in token:
        raise APIError(401, "unauthorized", "Authentication is required.")

    return await request.app.state.container.auth_verifier.verify(token)


@router.get("/me", response_model=IdentityResponse)
async def me(
    user: Annotated[AuthenticatedUser, Depends(authenticated_user)],
) -> IdentityResponse:
    return IdentityResponse(user_id=user.user_id)
