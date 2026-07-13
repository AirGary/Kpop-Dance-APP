from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def _valid_request_id(value: str | None) -> bool:
    return bool(value) and len(value) <= 128 and all("!" <= char <= "~" for char in value)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied_id = request.headers.get("X-Request-ID")
        request_id = supplied_id if _valid_request_id(supplied_id) else uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
