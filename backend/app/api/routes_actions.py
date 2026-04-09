from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.action import ActionDecisionRequest, ActionParseRequest, ActionResponse, ActionSelectCandidateRequest
from app.services.action_parser_service import ActionParserService
from app.services.apply_changes_service import ApplyChangesService
from app.services.errors import ActionError, SingularityAPIError
from app.services.user_service import UserService


router = APIRouter()


@router.post("/parse", response_model=ActionResponse)
def parse_action(
    payload: ActionParseRequest,
    db: Session = Depends(get_db_session),
) -> ActionResponse:
    user_service = UserService(db)

    try:
        user = user_service.get_required(payload.telegram_id)
        change_request = ActionParserService(db).create_draft(user, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ActionResponse(**ActionParserService(db).to_response_payload(change_request))


@router.get("/{change_request_id}", response_model=ActionResponse)
def get_action(
    change_request_id: int,
    telegram_id: str | None = None,
    db: Session = Depends(get_db_session),
) -> ActionResponse:
    user_service = UserService(db)

    try:
        user = user_service.get_required(telegram_id)
        change_request = ActionParserService(db).get_required(user, change_request_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ActionResponse(**ActionParserService(db).to_response_payload(change_request))


@router.post("/{change_request_id}/confirm", response_model=ActionResponse)
def confirm_action(
    change_request_id: int,
    payload: ActionDecisionRequest,
    db: Session = Depends(get_db_session),
) -> ActionResponse:
    user_service = UserService(db)
    parser_service = ActionParserService(db)

    try:
        user = user_service.get_required(payload.telegram_id)
        change_request = parser_service.get_required(user, change_request_id)
        ApplyChangesService(db).apply(user, change_request)
        db.refresh(change_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except SingularityAPIError as exc:
        upstream_status = exc.status_code or status.HTTP_502_BAD_GATEWAY
        mapped_status = status.HTTP_400_BAD_REQUEST if upstream_status in (401, 403) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=mapped_status, detail=str(exc)) from exc

    return ActionResponse(**parser_service.to_response_payload(change_request))


@router.post("/{change_request_id}/select-candidate", response_model=ActionResponse)
def select_candidate(
    change_request_id: int,
    payload: ActionSelectCandidateRequest,
    db: Session = Depends(get_db_session),
) -> ActionResponse:
    user_service = UserService(db)
    parser_service = ActionParserService(db)

    try:
        user = user_service.get_required(payload.telegram_id)
        change_request = parser_service.get_required(user, change_request_id)
        change_request = parser_service.select_candidate(user, change_request, payload.candidate_index)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ActionResponse(**parser_service.to_response_payload(change_request))


@router.post("/{change_request_id}/cancel", response_model=ActionResponse)
def cancel_action(
    change_request_id: int,
    payload: ActionDecisionRequest,
    db: Session = Depends(get_db_session),
) -> ActionResponse:
    user_service = UserService(db)
    parser_service = ActionParserService(db)

    try:
        user = user_service.get_required(payload.telegram_id)
        change_request = parser_service.get_required(user, change_request_id)
        change_request = parser_service.cancel(change_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ActionResponse(**parser_service.to_response_payload(change_request))
