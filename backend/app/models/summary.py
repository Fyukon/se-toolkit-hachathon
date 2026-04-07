from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period_type: Mapped[str] = mapped_column(String(16))
    source_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_snapshot: Mapped[str | None] = mapped_column(Text(), nullable=True)
    summary_text: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
