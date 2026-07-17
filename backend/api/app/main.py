from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.app.config import Settings
from api.app.container import AppContainer
from api.app.middleware.request_context import RequestContextMiddleware
from api.app.routes.health import router as health_router
from api.app.routes.identity import router as identity_router
from api.app.routes.jobs import router as jobs_router
from api.app.routes.uploads import router as uploads_router
from api.app.routes.analysis import router as analysis_router
from api.app.schemas.errors import APIError, error_response


def create_app(
    settings: Settings | None = None,
    container: AppContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    resolved_container = container or AppContainer.for_settings(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await resolved_container.upload_service.cleanup_expired()
        coordinator = getattr(resolved_container, "analysis_coordinator", None)
        if coordinator is not None:
            await coordinator.resume_pending()
        yield
        if coordinator is not None:
            await coordinator.shutdown()

    app = FastAPI(title="Stage Lab API", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.container = resolved_container
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(jobs_router)
    app.include_router(uploads_router)
    app.include_router(analysis_router)

    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, error: APIError):
        return error_response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _: RequestValidationError):
        return error_response(
            request,
            status_code=422,
            code="validation_error",
            message="Request validation failed.",
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException):
        if error.status_code == 404:
            return error_response(
                request,
                status_code=404,
                code="not_found",
                message="Resource was not found.",
            )
        return error_response(
            request,
            status_code=error.status_code,
            code="http_error",
            message="Request failed.",
        )

    @app.exception_handler(Exception)
    async def handle_internal_error(request: Request, _: Exception):
        return error_response(
            request,
            status_code=500,
            code="internal_error",
            message="An internal error occurred.",
        )

    return app


app = create_app()
