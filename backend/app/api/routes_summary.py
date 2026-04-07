from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.summary import SummaryResponse
from app.services.summary_service import SummaryService
from app.services.user_service import UserService


router = APIRouter()


@router.get("/day", response_model=SummaryResponse)
def get_day_summary(
    telegram_id: str | None = None,
    db: Session = Depends(get_db_session),
) -> SummaryResponse:
    try:
        user = UserService(db).get_required(telegram_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SummaryResponse.model_validate(SummaryService(db).generate_day_summary(user))


@router.get("/week", response_model=SummaryResponse)
def get_week_summary(
    telegram_id: str | None = None,
    db: Session = Depends(get_db_session),
) -> SummaryResponse:
    try:
        user = UserService(db).get_required(telegram_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SummaryResponse.model_validate(SummaryService(db).generate_week_summary(user))
