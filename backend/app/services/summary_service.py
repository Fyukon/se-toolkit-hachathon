from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.schemas.summary import SummaryTaskItem
from app.utils.logging import get_logger


logger = get_logger(__name__)


class SummaryService:
    """Builds a deterministic Version 1 summary from synced tasks."""

    def __init__(self, db: Session):
        self.db = db

    def generate_day_summary(self, user: User, today: date | None = None) -> dict:
        tz = self._user_timezone(user)
        target_day = today or datetime.now(tz).date()
        window_start_local = datetime.combine(target_day, time.min, tzinfo=tz)
        window_end_local = datetime.combine(target_day, time.max, tzinfo=tz)
        window_start = window_start_local.astimezone(UTC)
        window_end = window_end_local.astimezone(UTC)
        tasks = self._tasks_in_window(user, window_start, window_end)
        self._log_window_diagnostics(user, "day", window_start, window_end, tz, tasks)
        return self._build_summary_payload(user, "day", tasks, window_start, window_end, tz)

    def generate_week_summary(self, user: User, today: date | None = None) -> dict:
        tz = self._user_timezone(user)
        target_day = today or datetime.now(tz).date()
        week_start = target_day - timedelta(days=target_day.weekday())
        week_end = week_start + timedelta(days=6)
        window_start_local = datetime.combine(week_start, time.min, tzinfo=tz)
        window_end_local = datetime.combine(week_end, time.max, tzinfo=tz)
        window_start = window_start_local.astimezone(UTC)
        window_end = window_end_local.astimezone(UTC)
        tasks = self._tasks_in_window(user, window_start, window_end)
        self._log_window_diagnostics(user, "week", window_start, window_end, tz, tasks)
        return self._build_summary_payload(user, "week", tasks, window_start, window_end, tz)

    def _tasks_in_window(self, user: User, window_start: datetime, window_end: datetime) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.due_at.is_not(None),
                Task.due_at >= window_start,
                Task.due_at <= window_end,
            )
            .order_by(Task.due_at.asc(), Task.priority.asc().nullslast(), Task.title.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def _upcoming_tasks(self, user: User, limit: int = 5) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.due_at.is_not(None),
                Task.status != "completed",
                Task.due_at >= datetime.now(UTC),
            )
            .order_by(Task.due_at.asc(), Task.title.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def _build_summary_payload(
        self,
        user: User,
        period: str,
        tasks: list[Task],
        window_start: datetime,
        window_end: datetime,
        tz: ZoneInfo,
    ) -> dict:
        completed_count = sum(task.status == "completed" for task in tasks)
        high_priority_count = sum(task.priority == "high" for task in tasks)
        upcoming = [task for task in tasks if task.status != "completed"]
        display_tasks = tasks

        if not tasks:
            if period == "day":
                summary = "На сегодня задач не найдено."
            else:
                fallback_tasks = self._upcoming_tasks(user)
                display_tasks = fallback_tasks

                if fallback_tasks:
                    first = fallback_tasks[0]
                    when = self._format_dt(first.due_at, tz) if first.due_at else "без времени"
                    summary = (
                        "На этой неделе задач не найдено. "
                        f"Ближайшая следующая задача: {first.title} ({when})."
                    )
                else:
                    summary = (
                        "В SingularityApp нет задач с датой. "
                        "После синхронизации и планирования здесь появится краткая сводка."
                    )
        else:
            pieces = [f"Найдено задач: {len(tasks)}."]
            if high_priority_count:
                pieces.append(f"Из них с высоким приоритетом: {high_priority_count}.")
            if completed_count:
                pieces.append(f"Уже выполнено: {completed_count}.")
            if upcoming:
                first = upcoming[0]
                when = self._format_dt(first.due_at, tz) if first.due_at else "без времени"
                pieces.append(f"Ближайшая активная задача: {first.title} ({when}).")
            summary = " ".join(pieces)

        items = [
            SummaryTaskItem(
                id=task.external_id,
                title=task.title,
                when=task.due_at,
                priority=task.priority,
                status=task.status,
            )
            for task in display_tasks
        ]

        return {
            "period": period,
            "telegram_id": user.telegram_id or "",
            "summary": summary,
            "generated_from_cache": False,
            "generated_at": datetime.now(UTC),
            "task_count": len(display_tasks),
            "tasks": items,
            "window_start": window_start,
            "window_end": window_end,
        }

    @staticmethod
    def _format_dt(value: datetime, tz: ZoneInfo) -> str:
        return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _user_timezone(user: User) -> ZoneInfo:
        try:
            return ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def _log_window_diagnostics(
        self,
        user: User,
        period: str,
        window_start: datetime,
        window_end: datetime,
        tz: ZoneInfo,
        tasks: list[Task],
    ) -> None:
        logger.info(
            "Summary window telegram_id=%s period=%s tz=%s utc_start=%s utc_end=%s matched=%s",
            user.telegram_id,
            period,
            getattr(tz, "key", str(tz)),
            window_start.isoformat(),
            window_end.isoformat(),
            len(tasks),
        )

        nearby_stmt = (
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.due_at.is_not(None),
                Task.due_at >= window_start - timedelta(days=1),
                Task.due_at <= window_end + timedelta(days=2),
            )
            .order_by(Task.due_at.asc())
        )
        nearby = list(self.db.execute(nearby_stmt).scalars().all())
        for task in nearby:
            logger.info(
                "Nearby task telegram_id=%s external_id=%s due_at_utc=%s due_at_local=%s status=%s priority=%s title=%r",
                user.telegram_id,
                task.external_id,
                task.due_at.isoformat() if task.due_at else None,
                self._format_dt(task.due_at, tz) if task.due_at else None,
                task.status,
                task.priority,
                task.title[:120],
            )
