from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.task import Task
from app.models.user import User
from app.services.action_parser_service import ActionParserService


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)()


def test_action_parser_creates_move_draft_for_matching_task() -> None:
    db = make_session()
    user = User(telegram_id="local-dev", timezone="Europe/Moscow", singularity_access_token="token")
    db.add(user)
    db.commit()
    db.refresh(user)

    task = Task(
        user_id=user.id,
        external_id="task-1",
        title="Лаба DSA",
        due_at=datetime(2026, 4, 13, 9, 40, tzinfo=UTC),
        priority="normal",
        status="open",
    )
    db.add(task)
    db.commit()

    change_request = ActionParserService(db).create_draft(user, "перенеси лабу DSA на завтра 15:00")
    payload = ActionParserService(db).to_response_payload(change_request)

    assert payload["status"] == "draft"
    assert payload["intent"] == "move_task"
    assert payload["parsed_action"]["target_task_id"] == "task-1"
    assert payload["parsed_action"]["payload"]["journalDate"]
    assert payload["parsed_action"]["payload"]["start"].endswith("Z")
