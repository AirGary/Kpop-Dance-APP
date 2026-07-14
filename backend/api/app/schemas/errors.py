from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request


class ErrorDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    request_id: str = Field(alias="requestId")


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    request.state.error_code = code
    payload = {
        "error": {
            "code": code,
            "message": message,
            "requestId": request.state.request_id,
        }
    }
    return JSONResponse(status_code=status_code, content=payload)
