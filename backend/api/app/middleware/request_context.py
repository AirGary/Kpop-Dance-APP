import json
import logging
from time import monotonic
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger("stage_lab.requests")


def _valid_request_id(value: str | None) -> bool:
    return bool(value) and len(value) <= 128 and all("!" <= char <= "~" for char in value)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = monotonic()
        supplied_id = request.headers.get("X-Request-ID")
        request_id = supplied_id if _valid_request_id(supplied_id) else uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "duration_ms": round((monotonic() - started_at) * 1000, 3),
                    "error_code": getattr(request.state, "error_code", None),
                    "method": request.method,
                    "request_id": request_id,
                    "route": getattr(route, "path", "unmatched"),
                    "status_code": response.status_code,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return response
