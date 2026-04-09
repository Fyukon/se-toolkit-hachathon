from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionParseRequest(BaseModel):
    telegram_id: str | None = None
    text: str


class ActionDecisionRequest(BaseModel):
    telegram_id: str | None = None


class ActionSelectCandidateRequest(ActionDecisionRequest):
    candidate_index: int


class ActionTaskCandidate(BaseModel):
    external_id: str
    title: str
    when: datetime | None = None
    priority: str | None = None
    status: str


class ActionResponse(BaseModel):
    id: int
    original_text: str
    status: str
    message: str
    intent: str | None = None
    requires_confirmation: bool = False
    requires_clarification: bool = False
    parsed_action: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    candidates: list[ActionTaskCandidate] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
