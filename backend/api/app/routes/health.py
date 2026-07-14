from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "environment": request.app.state.settings.environment,
    }
