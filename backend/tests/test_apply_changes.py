import json
from types import SimpleNamespace

from app.models.change_request import ChangeRequest
from app.models.user import User
from app.services.apply_changes_service import ApplyChangesService


class FakeDb:
    def commit(self) -> None:
        return None

    def refresh(self, _: object) -> None:
        return None


def test_apply_changes_updates_task(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, token: str):
            calls["token"] = token

        def update_task(self, task_id: str, payload: dict) -> dict:
            calls["task_id"] = task_id
            calls["payload"] = payload
            return {"id": task_id}

    class FakeSyncService:
        def __init__(self, db):
            self.db = db

        def sync(self, user):
            calls["synced_user"] = user.telegram_id
            return {"events": 0, "tasks": 0, "synced_at": None}

    monkeypatch.setattr("app.services.apply_changes_service.SingularityClient", FakeClient)
    monkeypatch.setattr("app.services.apply_changes_service.SyncService", FakeSyncService)

    user = User(telegram_id="local-dev", timezone="Europe/Moscow", singularity_access_token="secret")
    change_request = ChangeRequest(
        id=42,
        user_id=1,
        user_command="перенеси лабу",
        parsed_actions=json.dumps(
            {
                "intent": "move_task",
                "target_task_id": "task-42",
                "payload": {"start": "2026-04-09T12:00:00Z", "journalDate": "2026-04-09", "useTime": True},
            }
        ),
        status="draft",
    )

    result = ApplyChangesService(FakeDb()).apply(user, change_request)

    assert result["status"] == "applied"
    assert result["change_request_id"] == "42"
    assert calls["task_id"] == "task-42"
    assert calls["payload"] == {"start": "2026-04-09T12:00:00Z", "journalDate": "2026-04-09", "useTime": True}
    assert calls["synced_user"] == "local-dev"
    assert change_request.status == "applied"
