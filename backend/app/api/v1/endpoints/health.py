from fastapi import APIRouter

from app.core.config import settings
from app.db.session import check_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    db_ok = await check_db()
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": db_ok,
        "app_env": settings.app_env,
        "project": "JURAS",
        "pilot": "Purani Mandi",
        "data_label": settings.data_label,
    }
