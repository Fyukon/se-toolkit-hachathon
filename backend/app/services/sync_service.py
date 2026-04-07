import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.services.errors import SingularityAPIError
from app.services.singularity_client import SingularityClient
from app.utils.logging import get_logger


logger = get_logger(__name__)


class SyncService:
    """Synchronizes SingularityApp tasks into the local database."""

    def __init__(self, db: Session):
        self.db = db

    def sync(self, user: User) -> dict[str, int | datetime]:
        if not user.singularity_access_token:
            raise ValueError("SingularityApp API token is not configured for this user.")

        client = SingularityClient(user.singularity_access_token)
        tz = self._user_timezone(user)
        now_local = datetime.now(tz)
        today_local = now_local.date()

        # Combine a broad task pull with a focused date-range pull around "today" to catch recurring instances.
        all_tasks_payload = self._fetch_all_tasks(client)
        try:
            window_start_local = datetime.combine(today_local, datetime.min.time(), tzinfo=tz)
            window_end_local = datetime.combine(today_local + timedelta(days=1), datetime.min.time(), tzinfo=tz)
            raw_today_payload = client.fetch_tasks_payload(
                start_date_from=window_start_local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                start_date_to=window_end_local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                max_count=1000,
            )
            today_window_debug = client.payload_debug_info(raw_today_payload)
        except SingularityAPIError as exc:
            logger.warning(
                "Focused today-window sync failed for telegram_id=%s: %s",
                user.telegram_id,
                exc,
            )
            raw_today_payload = {"tasks": []}
            today_window_debug = {
                "payload_type": "error",
                "payload_size": 0,
                "selected_collection_key": None,
                "sample_keys": [],
                "error": str(exc),
            }
        tasks_payload = self._merge_payloads(
            all_tasks_payload,
            client.extract_tasks(raw_today_payload),
        )
        debug = {
            "payload_type": "list",
            "payload_size": len(all_tasks_payload),
            "selected_collection_key": "merged_pages",
            "sample_keys": list(all_tasks_payload[0].keys())[:20] if all_tasks_payload else [],
        }
        debug["today_window"] = {
            "from": window_start_local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "to": window_end_local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "payload_size": today_window_debug.get("payload_size"),
            "selected_collection_key": today_window_debug.get("selected_collection_key"),
            "error": today_window_debug.get("error"),
        }
        logger.info(
            "Sync started for telegram_id=%s payload_type=%s payload_size=%s collection_key=%s today_window=%s",
            user.telegram_id,
            debug.get("payload_type"),
            debug.get("payload_size"),
            debug.get("selected_collection_key"),
            debug.get("today_window"),
        )

        try:
            self._upsert_tasks(user=user, payloads=tasks_payload)
            user.last_synced_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(user)
        except SQLAlchemyError:
            self.db.rollback()
            raise

        logger.info(
            "Sync completed for telegram_id=%s tasks_synced=%s with_due_at=%s completed=%s high_priority=%s",
            user.telegram_id,
            len(tasks_payload),
            sum(task.due_at is not None for task in self._recent_tasks(user.id, limit=200)),
            sum(task.status == "completed" for task in self._recent_tasks(user.id, limit=200)),
            sum(task.priority == "high" for task in self._recent_tasks(user.id, limit=200)),
        )
        self._log_recent_samples(user.id)

        return {
            "events": 0,
            "tasks": len(tasks_payload),
            "synced_at": user.last_synced_at,
            "debug": debug,
        }

    def _upsert_tasks(self, user: User, payloads: list[dict]) -> None:
        external_ids = [self._extract_external_id(payload) for payload in payloads if self._extract_external_id(payload)]
        existing_by_external_id: dict[str, Task] = {}
        tz = self._user_timezone(user)
        today_local = datetime.now(tz).date()
        interesting_dates = {today_local, today_local + timedelta(days=1)}
        interesting_tokens = {
            today_local.isoformat(),
            (today_local + timedelta(days=1)).isoformat(),
            today_local.strftime("%Y%m%d"),
            (today_local + timedelta(days=1)).strftime("%Y%m%d"),
        }
        logged_interesting = 0
        logged_raw_interesting = 0
        raw_state_counter: Counter[str] = Counter()
        raw_priority_counter: Counter[str] = Counter()

        if external_ids:
            stmt = select(Task).where(Task.user_id == user.id, Task.external_id.in_(external_ids))
            existing_tasks = self.db.execute(stmt).scalars().all()
            existing_by_external_id = {task.external_id: task for task in existing_tasks}

        now = datetime.now(UTC)
        for index, payload in enumerate(payloads):
            external_id = self._extract_external_id(payload)
            if not external_id:
                continue

            raw_state_counter.update([repr(payload.get("state"))])
            raw_priority_counter.update([repr(payload.get("priority"))])

            task = existing_by_external_id.get(external_id)
            if task is None:
                task = Task(user_id=user.id, external_id=external_id, title="Untitled task")
                self.db.add(task)
                existing_by_external_id[external_id] = task

            task.title = self._extract_title(payload)
            task.description = self._extract_description(payload)
            task.due_at = self._extract_datetime(payload)
            task.priority = self._extract_priority(payload)
            task.status = self._extract_status(payload)
            task.raw_payload = json.dumps(payload, ensure_ascii=False)
            task.synced_at = now

            if index < 8:
                logger.info(
                    "Parsed task sample telegram_id=%s external_id=%s title=%r raw_priority=%r raw_state=%r due_at=%s parsed_priority=%s parsed_status=%s candidate_keys=%s",
                    user.telegram_id,
                    external_id,
                    task.title[:120],
                    payload.get("priority"),
                    payload.get("state"),
                    task.due_at.isoformat() if task.due_at else None,
                    task.priority,
                    task.status,
                    self._date_candidate_snapshot(payload),
                )

            if logged_interesting < 20 and task.due_at is not None:
                local_date = task.due_at.astimezone(tz).date()
                if local_date in interesting_dates:
                    logger.info(
                        "Interesting task telegram_id=%s local_date=%s external_id=%s title=%r due_at_utc=%s due_at_local=%s raw_priority=%r parsed_priority=%s raw_state=%r parsed_status=%s raw_date_fields=%s",
                        user.telegram_id,
                        local_date.isoformat(),
                        external_id,
                        task.title[:120],
                        task.due_at.isoformat(),
                        task.due_at.astimezone(tz).isoformat(),
                        payload.get("priority"),
                        task.priority,
                        payload.get("state"),
                        task.status,
                        self._date_candidate_snapshot(payload),
                    )
                    logged_interesting += 1

            if logged_raw_interesting < 20 and self._payload_has_interesting_date_hint(payload, interesting_tokens):
                logger.info(
                    "Raw date candidate telegram_id=%s external_id=%s title=%r parsed_due_at=%s raw_priority=%r raw_state=%r raw_date_fields=%s",
                    user.telegram_id,
                    external_id,
                    task.title[:120],
                    task.due_at.isoformat() if task.due_at else None,
                    payload.get("priority"),
                    payload.get("state"),
                    self._date_candidate_snapshot(payload),
                )
                logged_raw_interesting += 1

            # Flush each record separately to avoid opaque batched insert errors from heterogeneous payloads.
            self.db.flush()

        logger.info(
            "Raw distributions telegram_id=%s state_counts=%s priority_counts=%s",
            user.telegram_id,
            dict(raw_state_counter),
            dict(raw_priority_counter),
        )

    @staticmethod
    def _merge_payloads(*task_groups: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for group in task_groups:
            for payload in group:
                external_id = SyncService._extract_external_id(payload)
                if not external_id:
                    continue
                merged[external_id] = payload
        return list(merged.values())

    def _fetch_all_tasks(self, client: SingularityClient, page_size: int = 500, max_pages: int = 20) -> list[dict]:
        merged: dict[str, dict] = {}

        for page_index in range(max_pages):
            offset = page_index * page_size
            payload = client.fetch_tasks(
                max_count=page_size,
                offset=offset,
            )
            logger.info(
                "Fetched task page offset=%s page_size=%s returned=%s",
                offset,
                page_size,
                len(payload),
            )

            for item in payload:
                external_id = self._extract_external_id(item)
                if external_id:
                    merged[external_id] = item

            if len(payload) < page_size:
                break

        return list(merged.values())

    @staticmethod
    def _extract_external_id(payload: dict) -> str | None:
        for key in ("id", "_id", "taskId"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _extract_title(payload: dict) -> str:
        for key in ("title", "name", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Untitled task"

    @staticmethod
    def _extract_description(payload: dict) -> str | None:
        for key in ("note", "description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_priority(payload: dict) -> str | None:
        value = payload.get("priority")
        mapping = {0: "high", 1: "normal", 2: "low"}
        if isinstance(value, int):
            return mapping.get(value, str(value))
        if isinstance(value, str) and value:
            normalized = value.strip().lower()
            if normalized.isdigit():
                return mapping.get(int(normalized), normalized)
            if normalized in {"high", "normal", "low"}:
                return normalized
            return normalized

        for key in ("importance", "priorityLabel", "importanceLevel"):
            fallback = payload.get(key)
            if isinstance(fallback, int):
                return mapping.get(fallback, str(fallback))
            if isinstance(fallback, str) and fallback.strip():
                normalized = fallback.strip().lower()
                if normalized.isdigit():
                    return mapping.get(int(normalized), normalized)
                return normalized
        return None

    @staticmethod
    def _extract_status(payload: dict) -> str:
        for key in ("status",):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value

        # According to SingularityApp Swagger:
        # - state is pin/unpin state, not completion
        # - complete and checked carry completion semantics
        if payload.get("completed") is True:
            return "completed"
        if payload.get("complete") not in (None, 0, False):
            return "completed"
        if payload.get("checked") in (1, True):
            return "completed"
        return "open"

    @staticmethod
    def _extract_datetime(payload: dict) -> datetime | None:
        recurrence = payload.get("recurrence")
        recurrence_time = recurrence.get("time") if isinstance(recurrence, dict) else None

        # journalDate/deadline often reflect the actual dated instance better than the series-level start.
        for key in (
            "journalDate",
            "date",
            "deadline",
            "deadlineDate",
            "deadlineTime",
            "scheduledDate",
            "taskDate",
        ):
            raw = payload.get(key)
            parsed = SyncService._parse_date_and_time(raw, recurrence_time)
            if parsed is not None:
                return parsed

        for key in (
            "start",
            "startDate",
            "startTime",
            "dueAt",
        ):
            raw = payload.get(key)
            parsed = SyncService._parse_datetime(raw)
            if parsed is not None:
                return parsed

        if isinstance(recurrence, dict):
            for key in ("date", "startDate", "nextDate", "nextStartDate"):
                parsed = SyncService._parse_datetime(recurrence.get(key))
                if parsed is not None:
                    return parsed

            for date_key in ("date", "nextDate", "startDate", "nextStartDate"):
                date_raw = recurrence.get(date_key)
                parsed = SyncService._parse_date_and_time(date_raw, recurrence_time)
                if parsed is not None:
                    return parsed

        external_id = payload.get("id")
        if isinstance(external_id, str):
            parsed = SyncService._parse_date_from_external_id(external_id)
            if parsed is not None:
                return parsed

        return None

    @staticmethod
    def _parse_datetime(raw: object) -> datetime | None:
        if not isinstance(raw, str) or not raw.strip():
            return None

        value = raw.strip().replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(f"{value}T00:00:00")
            except ValueError:
                return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse_date_and_time(date_raw: object, time_raw: object) -> datetime | None:
        if not isinstance(date_raw, str) or not date_raw.strip():
            return None
        if not isinstance(time_raw, str) or not time_raw.strip():
            return SyncService._parse_datetime(date_raw)

        normalized_date = date_raw.strip().split("T")[0]
        normalized_time = time_raw.strip()
        candidate = f"{normalized_date}T{normalized_time}"
        return SyncService._parse_datetime(candidate)

    @staticmethod
    def _parse_date_from_external_id(external_id: str) -> datetime | None:
        parts = external_id.split("-")
        suffix = parts[-1]
        if len(suffix) == 8 and suffix.isdigit():
            candidate = f"{suffix[0:4]}-{suffix[4:6]}-{suffix[6:8]}"
            return SyncService._parse_datetime(candidate)
        return None

    def _recent_tasks(self, user_id: int, limit: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(Task.synced_at.desc(), Task.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def _log_recent_samples(self, user_id: int) -> None:
        tasks = self._recent_tasks(user_id, limit=12)
        for task in tasks:
            logger.info(
                "Stored task sample user_id=%s external_id=%s due_at=%s priority=%s status=%s title=%r",
                user_id,
                task.external_id,
                task.due_at.isoformat() if task.due_at else None,
                task.priority,
                task.status,
                task.title[:120],
            )

    @staticmethod
    def _date_candidate_snapshot(payload: dict) -> dict[str, object]:
        recurrence = payload.get("recurrence") if isinstance(payload.get("recurrence"), dict) else {}
        return {
            "journalDate": payload.get("journalDate"),
            "start": payload.get("start"),
            "startDate": payload.get("startDate"),
            "date": payload.get("date"),
            "deadline": payload.get("deadline"),
            "deadlineDate": payload.get("deadlineDate"),
            "dueAt": payload.get("dueAt"),
            "scheduledDate": payload.get("scheduledDate"),
            "complete": payload.get("complete"),
            "checked": payload.get("checked"),
            "recurrence.date": recurrence.get("date"),
            "recurrence.startDate": recurrence.get("startDate"),
            "recurrence.nextDate": recurrence.get("nextDate"),
            "recurrence.time": recurrence.get("time"),
            "id": payload.get("id"),
        }

    @staticmethod
    def _payload_has_interesting_date_hint(payload: dict, tokens: set[str]) -> bool:
        snapshot = SyncService._date_candidate_snapshot(payload)
        for value in snapshot.values():
            if isinstance(value, str):
                if any(token in value for token in tokens):
                    return True
        return False

    @staticmethod
    def _user_timezone(user: User) -> ZoneInfo:
        try:
            return ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")
