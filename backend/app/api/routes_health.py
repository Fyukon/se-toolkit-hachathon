from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db_session


router = APIRouter()


@router.get("/health")
def healthcheck(db: Session = Depends(get_db_session)) -> dict[str, str]:
    if settings.database_url.startswith("sqlite"):
        return {"status": "ok", "database": "ok"}
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
