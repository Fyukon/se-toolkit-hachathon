from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db_session
from app.schemas.sync import SyncRequest, SyncResponse
from app.services.errors import SingularityAPIError
from app.services.sync_service import SyncService
from app.services.user_service import UserService


router = APIRouter()


@router.post("/full", response_model=SyncResponse)
def sync_full(
    payload: SyncRequest,
    db: Session = Depends(get_db_session),
) -> SyncResponse:
    user_service = UserService(db)

    try:
        user = user_service.get_required(payload.telegram_id)
        if payload.timezone:
            user.timezone = payload.timezone
            db.commit()
            db.refresh(user)

        result = SyncService(db).sync(user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SingularityAPIError as exc:
        upstream_status = exc.status_code or status.HTTP_502_BAD_GATEWAY
        mapped_status = status.HTTP_400_BAD_REQUEST if upstream_status in (401, 403) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=mapped_status, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc) if settings.backend_debug else "Unexpected sync failure."
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc

    return SyncResponse(
        telegram_id=user.telegram_id or "",
        synced_at=result["synced_at"],
        events_synced=int(result["events"]),
        tasks_synced=int(result["tasks"]),
        debug=result.get("debug"),
    )
