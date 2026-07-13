from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/healthz")
async def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "environment": request.app.state.settings.environment,
    }
