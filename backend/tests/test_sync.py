from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.task import Task
from app.models.user import User
from app.services.sync_service import SyncService


def create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def test_sync_service_upserts_tasks(monkeypatch) -> None:
    session = create_session()
    user = User(telegram_id="123", singularity_access_token="token", timezone="Europe/Moscow")
    session.add(user)
    session.commit()
    session.refresh(user)

    payload = [
        {
            "id": "task-1",
            "title": "Prepare seminar",
            "note": "Slides",
            "startDate": "2026-04-07T10:00:00Z",
            "priority": 0,
            "completed": False,
        }
    ]

    monkeypatch.setattr("app.services.singularity_client.SingularityClient.fetch_tasks", lambda self, **_: payload)

    result = SyncService(session).sync(user)

    stored = session.query(Task).all()
    assert result["tasks"] == 1
    assert len(stored) == 1
    assert stored[0].external_id == "task-1"
    assert stored[0].title == "Prepare seminar"
    assert stored[0].priority == "high"
    assert stored[0].status == "open"


def test_parse_datetime_handles_date_and_timestamp() -> None:
    assert SyncService._parse_datetime("2026-04-07").date().isoformat() == "2026-04-07"
    assert SyncService._parse_datetime("2026-04-07T10:00:00Z") == datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
