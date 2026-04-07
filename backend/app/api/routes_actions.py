from fastapi import APIRouter

from app.schemas.action import ActionParseRequest, ActionParseResponse


router = APIRouter()


@router.post("/parse", response_model=ActionParseResponse)
def parse_action(payload: ActionParseRequest) -> ActionParseResponse:
    return ActionParseResponse(
        original_text=payload.text,
        status="draft",
        message="Action parsing is not implemented yet.",
    )
