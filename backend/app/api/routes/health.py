from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health_check() -> dict[str, str]:
    """
    Minimal health check endpoint for scaffold verification.
    """
    return {"status": "ok"}
