from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.task import Task
from app.models.user import User
from app.services.summary_service import SummaryService


def create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def test_day_summary_returns_tasks_and_text() -> None:
    session = create_session()
    user = User(telegram_id="123", singularity_access_token="token", timezone="Europe/Moscow")
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add_all(
        [
            Task(
                user_id=user.id,
                external_id="task-1",
                title="Write lab report",
                due_at=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
                priority="high",
                status="open",
            ),
            Task(
                user_id=user.id,
                external_id="task-2",
                title="Review notes",
                due_at=datetime(2026, 4, 7, 18, 0, tzinfo=UTC),
                priority="normal",
                status="completed",
            ),
        ]
    )
    session.commit()

    payload = SummaryService(session).generate_day_summary(user, today=datetime(2026, 4, 7, tzinfo=UTC).date())

    assert payload["period"] == "day"
    assert payload["task_count"] == 2
    assert "Найдено задач: 2." in payload["summary"]
    assert payload["tasks"][0].title == "Write lab report"
