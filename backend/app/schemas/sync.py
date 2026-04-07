from datetime import datetime

from pydantic import BaseModel


class SyncRequest(BaseModel):
    telegram_id: str | None = None
    timezone: str | None = None


class SyncDebugInfo(BaseModel):
    payload_type: str
    payload_size: int
    selected_collection_key: str | None = None
    sample_keys: list[str]


class SyncResponse(BaseModel):
    telegram_id: str
    synced_at: datetime
    events_synced: int
    tasks_synced: int
    debug: SyncDebugInfo | None = None
