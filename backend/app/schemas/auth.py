from pydantic import BaseModel


class AuthConnectRequest(BaseModel):
    telegram_id: str | None = None
    singularity_api_token: str | None = None
    timezone: str = "Europe/Moscow"


class AuthStatusResponse(BaseModel):
    connected: bool
    telegram_id: str | None = None
    telegram_webapp_url: str | None = None
    last_synced_at: str | None = None
