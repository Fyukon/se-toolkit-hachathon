from datetime import datetime

from pydantic import BaseModel


class SummaryTaskItem(BaseModel):
    id: str
    title: str
    when: datetime | None = None
    priority: str | None = None
    status: str


class SummaryResponse(BaseModel):
    period: str
    telegram_id: str
    summary: str
    generated_from_cache: bool
    generated_at: datetime
    task_count: int
    tasks: list[SummaryTaskItem]
