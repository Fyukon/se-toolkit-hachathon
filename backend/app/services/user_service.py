from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
class UserService:
    """Fetches and upserts the single-user or Telegram-bound user profile."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_telegram_id(self, telegram_id: str | None) -> str:
        return telegram_id or settings.default_telegram_user_id

    def get_by_telegram_id(self, telegram_id: str | None) -> User | None:
        resolved_id = self.resolve_telegram_id(telegram_id)
        stmt = select(User).where(User.telegram_id == resolved_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_required(self, telegram_id: str | None) -> User:
        user = self.get_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError("User is not connected to SingularityApp yet.")
        return user

    def connect(self, telegram_id: str | None, token: str | None, timezone: str) -> User:
        resolved_id = self.resolve_telegram_id(telegram_id)
        user = self.get_by_telegram_id(resolved_id)
        resolved_token = token or (user.singularity_access_token if user else None) or settings.singularity_api_token

        if not resolved_token:
            raise ValueError("SingularityApp API token is required for Version 1.")

        if user is None:
            user = User(telegram_id=resolved_id, timezone=timezone)
            self.db.add(user)

        user.singularity_access_token = resolved_token

        user.timezone = timezone

        self.db.commit()
        self.db.refresh(user)
        return user
