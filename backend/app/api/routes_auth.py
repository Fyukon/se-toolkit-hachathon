from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.auth import AuthStatusResponse
from app.config import settings
from app.db.session import get_db_session
from app.schemas.auth import AuthConnectRequest
from app.services.errors import SingularityAPIError
from app.services.user_service import UserService


router = APIRouter()


@router.post("/connect", response_model=AuthStatusResponse)
def connect_account(
    payload: AuthConnectRequest,
    db: Session = Depends(get_db_session),
) -> AuthStatusResponse:
    user_service = UserService(db)

    try:
        user = user_service.connect(
            telegram_id=payload.telegram_id,
            token=payload.singularity_api_token,
            timezone=payload.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SingularityAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return AuthStatusResponse(
        connected=bool(user.singularity_access_token),
        telegram_id=user.telegram_id,
        telegram_webapp_url=settings.telegram_webapp_url,
        last_synced_at=user.last_synced_at.isoformat() if user.last_synced_at else None,
    )


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(
    telegram_id: str | None = None,
    db: Session = Depends(get_db_session),
) -> AuthStatusResponse:
    user = UserService(db).get_by_telegram_id(telegram_id)
    return AuthStatusResponse(
        connected=bool(user and user.singularity_access_token),
        telegram_id=user.telegram_id if user else settings.default_telegram_user_id,
        telegram_webapp_url=settings.telegram_webapp_url,
        last_synced_at=user.last_synced_at.isoformat() if user and user.last_synced_at else None,
    )
