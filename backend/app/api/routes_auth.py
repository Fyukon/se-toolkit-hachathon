from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.auth import AuthStatusResponse
from app.config import settings
from app.db.session import get_db_session
from app.schemas.auth import AuthConnectRequest
from app.services.errors import SingularityAPIError
from app.services.user_service import UserService
from app.utils.logging import get_logger


router = APIRouter()
logger = get_logger(__name__)


@router.post("/connect", response_model=AuthStatusResponse)
def connect_account(
    payload: AuthConnectRequest,
    db: Session = Depends(get_db_session),
) -> AuthStatusResponse:
    user_service = UserService(db)
    logger.info(
        "Auth connect requested telegram_id=%s timezone=%s has_inline_token=%s has_env_token=%s",
        payload.telegram_id,
        payload.timezone,
        bool(payload.singularity_api_token),
        bool(settings.singularity_api_token),
    )

    try:
        user = user_service.connect(
            telegram_id=payload.telegram_id,
            token=payload.singularity_api_token,
            timezone=payload.timezone,
        )
    except ValueError as exc:
        logger.warning("Auth connect validation failed telegram_id=%s error=%s", payload.telegram_id, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SingularityAPIError as exc:
        logger.warning("Auth connect Singularity failure telegram_id=%s error=%s", payload.telegram_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Auth connect crashed telegram_id=%s", payload.telegram_id)
        detail = str(exc) if settings.backend_debug else "Unexpected auth failure."
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc

    logger.info(
        "Auth connect completed telegram_id=%s connected=%s",
        user.telegram_id,
        bool(user.singularity_access_token),
    )

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
