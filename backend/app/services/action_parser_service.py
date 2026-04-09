from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change_request import ChangeRequest
from app.models.task import Task
from app.models.user import User
from app.schemas.action import ActionTaskCandidate
from app.services.errors import ActionError
from app.services.llm_service import LLMService
from app.utils.logging import get_logger


logger = get_logger(__name__)


class ActionParserService:
    """Converts natural language into structured change drafts."""

    def __init__(self, db: Session):
        self.db = db

    def create_draft(self, user: User, text: str) -> ChangeRequest:
        cleaned = text.strip()
        if not cleaned:
            raise ActionError("Action text is required.")

        parsed = self._parse_with_fallback(user, cleaned)
        logger.info(
            "Create draft prepared user_id=%s status=%s intent=%s",
            user.id,
            parsed["status"],
            (parsed.get("parsed_action") or {}).get("intent"),
        )
        change_request = ChangeRequest(
            user_id=user.id,
            user_command=cleaned,
            parsed_actions=json.dumps(parsed["parsed_action"], ensure_ascii=False) if parsed["parsed_action"] else None,
            status=parsed["status"],
            validation_errors=json.dumps(parsed["validation_errors"], ensure_ascii=False)
            if parsed["validation_errors"]
            else None,
        )
        self.db.add(change_request)
        logger.info("Create draft commit started user_id=%s", user.id)
        self.db.commit()
        logger.info("Create draft commit completed user_id=%s change_request_id=%s", user.id, change_request.id)
        self.db.refresh(change_request)
        return change_request

    def _parse_with_fallback(self, user: User, text: str) -> dict:
        logger.info("Action parse started user_id=%s text=%r", user.id, text)
        try:
            llm_result = self._parse_with_llm_with_timeout(user, text)
            if llm_result is not None:
                logger.info("Action parse used llm path user_id=%s", user.id)
                return llm_result
        except ActionError as exc:
            logger.warning("Action parse llm fallback user_id=%s reason=%s", user.id, exc)
        except Exception:
            logger.exception("Action parse llm path crashed user_id=%s", user.id)

        logger.info("Action parse switching to deterministic fallback user_id=%s", user.id)
        return self._parse(user, text)

    def _parse_with_llm_with_timeout(self, user: User, text: str, timeout_seconds: float = 6.0) -> dict | None:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._parse_with_llm, user, text)
        try:
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise ActionError("LLM parse timed out.") from exc
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        executor.shutdown(wait=False, cancel_futures=True)
        return result

    def get_required(self, user: User, change_request_id: int) -> ChangeRequest:
        stmt = select(ChangeRequest).where(
            ChangeRequest.id == change_request_id,
            ChangeRequest.user_id == user.id,
        )
        change_request = self.db.execute(stmt).scalar_one_or_none()
        if change_request is None:
            raise ActionError("Change request not found.", status_code=404)
        return change_request

    def cancel(self, change_request: ChangeRequest) -> ChangeRequest:
        if change_request.status == "applied":
            raise ActionError("Applied change request cannot be cancelled.", status_code=409)
        change_request.status = "cancelled"
        self.db.commit()
        self.db.refresh(change_request)
        return change_request

    def select_candidate(self, user: User, change_request: ChangeRequest, candidate_index: int) -> ChangeRequest:
        if change_request.status != "clarification_required":
            raise ActionError("This change request does not need clarification.", status_code=409)
        if not change_request.parsed_actions:
            raise ActionError("Change request does not contain clarification candidates.", status_code=400)

        parsed_action = json.loads(change_request.parsed_actions)
        candidates = parsed_action.get("candidates") or []
        if candidate_index < 0 or candidate_index >= len(candidates):
            raise ActionError("Candidate index is out of range.", status_code=400)

        selected_candidate = candidates[candidate_index]
        selected_task = self._get_task_by_external_id(user, selected_candidate.get("external_id"))
        if selected_task is None:
            raise ActionError("Selected candidate is no longer available.", status_code=404)

        resolved_action = self._resolve_clarification_choice(user, parsed_action, selected_task)
        change_request.parsed_actions = json.dumps(resolved_action, ensure_ascii=False)
        change_request.status = "draft"
        change_request.validation_errors = None
        self.db.commit()
        self.db.refresh(change_request)
        return change_request

    def to_response_payload(self, change_request: ChangeRequest) -> dict:
        parsed_action = json.loads(change_request.parsed_actions) if change_request.parsed_actions else None
        validation_errors = json.loads(change_request.validation_errors) if change_request.validation_errors else []
        candidates = [
            ActionTaskCandidate(**candidate)
            for candidate in (parsed_action or {}).get("candidates", [])
        ]

        message = self._message_for_status(change_request.status, parsed_action, validation_errors)

        return {
            "id": change_request.id,
            "original_text": change_request.user_command,
            "status": change_request.status,
            "message": message,
            "intent": (parsed_action or {}).get("intent"),
            "requires_confirmation": change_request.status == "draft",
            "requires_clarification": change_request.status == "clarification_required",
            "parsed_action": parsed_action,
            "validation_errors": validation_errors,
            "candidates": candidates,
            "created_at": change_request.created_at,
            "updated_at": change_request.updated_at,
        }

    def _parse(self, user: User, text: str) -> dict:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ("перенеси", "сдвинь", "move", "reschedule")):
            return self._parse_move_task(user, text)
        if any(keyword in lowered for keyword in ("добавь", "создай", "add", "create", "make")):
            return self._parse_create_task(user, text)
        if any(keyword in lowered for keyword in ("заверши", "заверши", "отметь", "complete", "done", "выполни")):
            return self._parse_complete_task(user, text)

        raise ActionError(
            "Unsupported action. Version 2 currently supports move, create, and complete task commands."
        )

    def _parse_with_llm(self, user: User, text: str) -> dict | None:
        logger.info("Action parse llm request started user_id=%s", user.id)
        llm_payload = LLMService().parse_action_command(
            text=text,
            today=datetime.now(self._user_timezone(user)).date(),
            timezone=user.timezone,
            candidate_tasks=self._candidate_context(user),
        )
        logger.info("Action parse llm request completed user_id=%s payload=%s", user.id, llm_payload)
        if llm_payload is None:
            return None

        intent = llm_payload.get("intent")
        if intent == "move_task":
            return self._build_move_task_from_hints(
                user=user,
                target_hint=llm_payload.get("target_hint"),
                date_hint=llm_payload.get("date_hint"),
                time_hint=llm_payload.get("time_hint"),
                llm_reason=llm_payload.get("reason"),
            )
        if intent == "create_task":
            return self._build_create_task_from_hints(
                user=user,
                title=llm_payload.get("title") or llm_payload.get("target_hint"),
                date_hint=llm_payload.get("date_hint"),
                time_hint=llm_payload.get("time_hint"),
                llm_reason=llm_payload.get("reason"),
            )
        if intent == "complete_task":
            return self._build_complete_task_from_hints(
                user=user,
                target_hint=llm_payload.get("target_hint"),
                llm_reason=llm_payload.get("reason"),
            )
        return None

    def _build_move_task_from_hints(
        self,
        *,
        user: User,
        target_hint: str | None,
        date_hint: str | None,
        time_hint: str | None,
        llm_reason: str | None,
    ) -> dict:
        if not target_hint:
            return self._error_result("validation_failed", ["LLM не смог определить, какую задачу переносить."], intent="move_task")

        due_at = self._resolve_datetime_from_hints(user, date_hint, time_hint)
        if due_at is None:
            return self._error_result("validation_failed", ["LLM не смог определить новую дату или время."], intent="move_task")

        candidates = self._resolve_candidates(user, target_hint, include_completed=False)
        if not candidates:
            return self._error_result("validation_failed", [f"Не нашёл задачу, похожую на '{target_hint}'."], intent="move_task")

        if len(candidates) > 1 and not self._is_clear_match(candidates, target_hint):
            result = self._clarification_result(
                intent="move_task",
                target_hint=target_hint,
                candidates=candidates,
                extra={"new_when": due_at.isoformat(), "llm_reason": llm_reason},
            )
            return result

        task = candidates[0]
        local_dt = due_at.astimezone(self._user_timezone(user))
        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": {
                "intent": "move_task",
                "target_hint": target_hint,
                "target_task_id": task.external_id,
                "target_title": task.title,
                "current_when": task.due_at.isoformat() if task.due_at else None,
                "new_when": due_at.isoformat(),
                "llm_reason": llm_reason,
                "payload": {
                    "start": due_at.isoformat().replace("+00:00", "Z"),
                    "journalDate": local_dt.date().isoformat(),
                    "useTime": True,
                },
                "candidates": [self._candidate_to_dict(item) for item in candidates[:5]],
            },
        }

    def _build_create_task_from_hints(
        self,
        *,
        user: User,
        title: str | None,
        date_hint: str | None,
        time_hint: str | None,
        llm_reason: str | None,
    ) -> dict:
        if not title:
            return self._error_result("validation_failed", ["LLM не смог определить название новой задачи."], intent="create_task")

        due_at = self._resolve_datetime_from_hints(user, date_hint, time_hint)
        payload: dict[str, object] = {"title": title}
        if due_at is not None:
            local_dt = due_at.astimezone(self._user_timezone(user))
            payload.update(
                {
                    "start": due_at.isoformat().replace("+00:00", "Z"),
                    "journalDate": local_dt.date().isoformat(),
                    "useTime": True,
                }
            )
        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": {
                "intent": "create_task",
                "title": title,
                "new_when": due_at.isoformat() if due_at else None,
                "llm_reason": llm_reason,
                "payload": payload,
                "candidates": [],
            },
        }

    def _build_complete_task_from_hints(self, *, user: User, target_hint: str | None, llm_reason: str | None) -> dict:
        if not target_hint:
            return self._error_result("validation_failed", ["LLM не смог определить, какую задачу завершить."], intent="complete_task")

        candidates = self._resolve_candidates(user, target_hint, include_completed=False)
        if not candidates:
            return self._error_result("validation_failed", [f"Не нашёл задачу, похожую на '{target_hint}'."], intent="complete_task")

        if len(candidates) > 1 and not self._is_clear_match(candidates, target_hint):
            return self._clarification_result(
                intent="complete_task",
                target_hint=target_hint,
                candidates=candidates,
                extra={"llm_reason": llm_reason},
            )

        task = candidates[0]
        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": {
                "intent": "complete_task",
                "target_hint": target_hint,
                "target_task_id": task.external_id,
                "target_title": task.title,
                "llm_reason": llm_reason,
                "payload": {"complete": 1, "checked": 1},
                "candidates": [self._candidate_to_dict(item) for item in candidates[:5]],
            },
        }

    def _parse_move_task(self, user: User, text: str) -> dict:
        due_at, normalized_text, date_hint = self._extract_target_datetime(user, text)
        if due_at is None:
            return self._error_result(
                "validation_failed",
                ["Не удалось определить новую дату или время. Пример: 'перенеси лабу DSA на завтра 15:00'."],
            )

        target_hint = self._extract_target_hint(
            normalized_text,
            verbs=("перенеси", "сдвинь", "move", "reschedule"),
            prepositions=("на", "to"),
        )
        if not target_hint:
            return self._error_result("validation_failed", ["Не удалось определить, какую задачу нужно перенести."])

        candidates = self._resolve_candidates(user, target_hint, include_completed=False)
        if not candidates:
            return self._error_result("validation_failed", [f"Не нашёл задачу, похожую на '{target_hint}'."], intent="move_task")

        if len(candidates) > 1 and not self._is_clear_match(candidates, target_hint):
            return self._clarification_result(
                intent="move_task",
                target_hint=target_hint,
                candidates=candidates,
                extra={"new_when": due_at.isoformat(), "date_hint": date_hint},
            )

        task = candidates[0]
        local_dt = due_at.astimezone(self._user_timezone(user))
        parsed_action = {
            "intent": "move_task",
            "target_hint": target_hint,
            "target_task_id": task.external_id,
            "target_title": task.title,
            "current_when": task.due_at.isoformat() if task.due_at else None,
            "new_when": due_at.isoformat(),
            "date_hint": date_hint,
            "payload": {
                "start": due_at.isoformat().replace("+00:00", "Z"),
                "journalDate": local_dt.date().isoformat(),
                "useTime": True,
            },
            "candidates": [self._candidate_to_dict(item) for item in candidates[:5]],
        }
        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": parsed_action,
        }

    def _parse_create_task(self, user: User, text: str) -> dict:
        due_at, normalized_text, date_hint = self._extract_target_datetime(user, text)
        title = self._extract_create_title(normalized_text)
        if not title:
            return self._error_result("validation_failed", ["Не удалось определить название новой задачи."], intent="create_task")

        payload: dict[str, object] = {"title": title}
        if due_at is not None:
            local_dt = due_at.astimezone(self._user_timezone(user))
            payload.update(
                {
                    "start": due_at.isoformat().replace("+00:00", "Z"),
                    "journalDate": local_dt.date().isoformat(),
                    "useTime": True,
                }
            )

        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": {
                "intent": "create_task",
                "title": title,
                "new_when": due_at.isoformat() if due_at else None,
                "date_hint": date_hint,
                "payload": payload,
                "candidates": [],
            },
        }

    def _parse_complete_task(self, user: User, text: str) -> dict:
        target_hint = self._extract_target_hint(
            text,
            verbs=("заверши", "заверши", "отметь", "complete", "done", "выполни"),
            prepositions=("как", "как выполненную"),
        )
        if not target_hint:
            return self._error_result("validation_failed", ["Не удалось определить, какую задачу нужно завершить."], intent="complete_task")

        candidates = self._resolve_candidates(user, target_hint, include_completed=False)
        if not candidates:
            return self._error_result("validation_failed", [f"Не нашёл задачу, похожую на '{target_hint}'."], intent="complete_task")

        if len(candidates) > 1 and not self._is_clear_match(candidates, target_hint):
            return self._clarification_result(
                intent="complete_task",
                target_hint=target_hint,
                candidates=candidates,
            )

        task = candidates[0]
        return {
            "status": "draft",
            "validation_errors": [],
            "parsed_action": {
                "intent": "complete_task",
                "target_hint": target_hint,
                "target_task_id": task.external_id,
                "target_title": task.title,
                "payload": {
                    "complete": 1,
                    "checked": 1,
                },
                "candidates": [self._candidate_to_dict(item) for item in candidates[:5]],
            },
        }

    def _resolve_candidates(self, user: User, target_hint: str, *, include_completed: bool) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user.id)
        if not include_completed:
            stmt = stmt.where(Task.status != "completed")

        tasks = list(self.db.execute(stmt).scalars().all())
        tokens = self._normalize_tokens(target_hint)
        if not tokens:
            return []

        scored: list[tuple[int, Task]] = []
        phrase = " ".join(tokens)
        for task in tasks:
            title_tokens = self._normalize_tokens(task.title)
            title_normalized = " ".join(title_tokens)
            score = 0
            if phrase and phrase in title_normalized:
                score += 20
            score += sum(3 for token in tokens if token in title_tokens)
            if task.due_at:
                score += 1
            if score > 0:
                scored.append((score, task))

        scored.sort(key=lambda item: (-item[0], item[1].due_at or datetime.max.replace(tzinfo=UTC), item[1].title))
        return [task for _, task in scored[:5]]

    def _get_task_by_external_id(self, user: User, external_id: str | None) -> Task | None:
        if not external_id:
            return None

        stmt = select(Task).where(Task.user_id == user.id, Task.external_id == external_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def _resolve_clarification_choice(self, user: User, parsed_action: dict, selected_task: Task) -> dict:
        intent = parsed_action.get("intent")
        if intent == "move_task":
            new_when_raw = parsed_action.get("new_when")
            if not new_when_raw:
                raise ActionError("Clarification draft is missing the new datetime.", status_code=400)

            due_at = self._parse_iso_datetime(new_when_raw)
            local_dt = due_at.astimezone(self._user_timezone(user))
            return {
                "intent": "move_task",
                "target_hint": parsed_action.get("target_hint"),
                "target_task_id": selected_task.external_id,
                "target_title": selected_task.title,
                "current_when": selected_task.due_at.isoformat() if selected_task.due_at else None,
                "new_when": due_at.isoformat(),
                "llm_reason": parsed_action.get("llm_reason"),
                "date_hint": parsed_action.get("date_hint"),
                "payload": {
                    "start": due_at.isoformat().replace("+00:00", "Z"),
                    "journalDate": local_dt.date().isoformat(),
                    "useTime": True,
                },
                "candidates": [],
            }

        if intent == "complete_task":
            return {
                "intent": "complete_task",
                "target_hint": parsed_action.get("target_hint"),
                "target_task_id": selected_task.external_id,
                "target_title": selected_task.title,
                "llm_reason": parsed_action.get("llm_reason"),
                "payload": {
                    "complete": 1,
                    "checked": 1,
                },
                "candidates": [],
            }

        raise ActionError("Candidate selection is not supported for this action type.", status_code=400)

    @staticmethod
    def _is_clear_match(candidates: list[Task], target_hint: str) -> bool:
        if len(candidates) == 1:
            return True

        normalized_hint = " ".join(ActionParserService._normalize_tokens(target_hint))
        normalized_first = " ".join(ActionParserService._normalize_tokens(candidates[0].title))
        normalized_second = " ".join(ActionParserService._normalize_tokens(candidates[1].title))
        return normalized_hint == normalized_first and normalized_first != normalized_second

    @staticmethod
    def _error_result(status: str, errors: list[str], *, intent: str | None = None) -> dict:
        return {
            "status": status,
            "validation_errors": errors,
            "parsed_action": {"intent": intent, "candidates": []} if intent else None,
        }

    def _clarification_result(
        self,
        *,
        intent: str,
        target_hint: str,
        candidates: list[Task],
        extra: dict | None = None,
    ) -> dict:
        parsed_action = {
            "intent": intent,
            "target_hint": target_hint,
            "candidates": [self._candidate_to_dict(item) for item in candidates],
        }
        if extra:
            parsed_action.update(extra)

        return {
            "status": "clarification_required",
            "validation_errors": ["Команда неоднозначна. Выбери одну из найденных задач."],
            "parsed_action": parsed_action,
        }

    def _extract_target_datetime(self, user: User, text: str) -> tuple[datetime | None, str, str | None]:
        tz = self._user_timezone(user)
        now_local = datetime.now(tz)
        normalized = text

        date_value, date_hint, normalized = self._parse_date_hint(normalized, now_local.date())
        time_value, normalized = self._parse_time_hint(normalized)

        if date_value is None and time_value is None:
            return None, normalized, None

        if date_value is None:
            date_value = now_local.date()
        if time_value is None:
            time_value = time(9, 0)

        local_dt = datetime.combine(date_value, time_value, tzinfo=tz)
        return local_dt.astimezone(UTC), normalized, date_hint

    def _resolve_datetime_from_hints(self, user: User, date_hint: str | None, time_hint: str | None) -> datetime | None:
        tz = self._user_timezone(user)
        today = datetime.now(tz).date()
        combined = " ".join(part for part in (date_hint, time_hint) if part)
        if not combined:
            return None

        date_value, _, _ = self._parse_date_hint(combined, today)
        time_value, _ = self._parse_time_hint(combined)
        if date_value is None and time_value is None:
            return None
        if date_value is None:
            date_value = today
        if time_value is None:
            time_value = time(9, 0)
        return datetime.combine(date_value, time_value, tzinfo=tz).astimezone(UTC)

    @staticmethod
    def _parse_date_hint(text: str, today: date) -> tuple[date | None, str | None, str]:
        lowered = text.lower()
        replacements = {
            "сегодня": today,
            "today": today,
            "завтра": today + timedelta(days=1),
            "tomorrow": today + timedelta(days=1),
            "послезавтра": today + timedelta(days=2),
        }
        for token, resolved in replacements.items():
            if token in lowered:
                return resolved, token, re.sub(token, " ", text, flags=re.IGNORECASE)

        weekday_map = {
            "понедельник": 0,
            "вторник": 1,
            "среду": 2,
            "среда": 2,
            "четверг": 3,
            "пятницу": 4,
            "пятница": 4,
            "субботу": 5,
            "суббота": 5,
            "воскресенье": 6,
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for token, weekday in weekday_map.items():
            if token in lowered:
                days_ahead = (weekday - today.weekday()) % 7
                days_ahead = 7 if days_ahead == 0 else days_ahead
                return today + timedelta(days=days_ahead), token, re.sub(token, " ", text, flags=re.IGNORECASE)

        explicit = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if explicit:
            resolved = datetime.fromisoformat(explicit.group(1)).date()
            return resolved, explicit.group(1), text.replace(explicit.group(1), " ")

        dotted = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", text)
        if dotted:
            day_value = int(dotted.group(1))
            month_value = int(dotted.group(2))
            year_value = int(dotted.group(3) or today.year)
            resolved = date(year_value, month_value, day_value)
            return resolved, dotted.group(0), text.replace(dotted.group(0), " ")

        return None, None, text

    @staticmethod
    def _parse_time_hint(text: str) -> tuple[time | None, str]:
        clock_match = re.search(r"(\d{1,2})[:.](\d{2})", text)
        if clock_match:
            hour = int(clock_match.group(1))
            minute = int(clock_match.group(2))
            return time(hour, minute), text.replace(clock_match.group(0), " ")

        am_pm_match = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text, flags=re.IGNORECASE)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            marker = am_pm_match.group(2).lower()
            if marker == "pm" and hour < 12:
                hour += 12
            if marker == "am" and hour == 12:
                hour = 0
            return time(hour, 0), text.replace(am_pm_match.group(0), " ")

        return None, text

    @staticmethod
    def _extract_target_hint(text: str, *, verbs: tuple[str, ...], prepositions: tuple[str, ...]) -> str:
        lowered = text.lower()
        for verb in verbs:
            lowered = re.sub(rf"\b{re.escape(verb)}\b", " ", lowered)
        for prep in prepositions:
            lowered = re.sub(rf"\b{re.escape(prep)}\b.*$", " ", lowered)

        lowered = re.sub(r"\s+", " ", lowered).strip(" ,.")
        return lowered

    @staticmethod
    def _extract_create_title(text: str) -> str:
        normalized = text.lower()
        normalized = re.sub(r"\b(добавь|создай|add|create|make)\b", " ", normalized)
        normalized = re.sub(r"\b(me|мне)\b", " ", normalized)
        normalized = re.sub(r"\b(a|an|new|новую|новую задачу|задачу|task)\b", " ", normalized)
        normalized = re.sub(r"\b(for|на|to)\b.*$", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip(" ,.")
        return normalized

    @staticmethod
    def _normalize_tokens(text: str) -> list[str]:
        return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+]+", text.lower())

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _candidate_context(self, user: User) -> list[dict]:
        stmt = (
            select(Task)
            .where(Task.user_id == user.id)
            .order_by(Task.due_at.asc().nullslast(), Task.title.asc())
            .limit(30)
        )
        tasks = list(self.db.execute(stmt).scalars().all())
        return [
            {
                "external_id": task.external_id,
                "title": task.title,
                "when": task.due_at.isoformat() if task.due_at else None,
                "priority": task.priority,
                "status": task.status,
            }
            for task in tasks
        ]

    @staticmethod
    def _candidate_to_dict(task: Task) -> dict:
        return {
            "external_id": task.external_id,
            "title": task.title,
            "when": task.due_at.isoformat() if task.due_at else None,
            "priority": task.priority,
            "status": task.status,
        }

    @staticmethod
    def _message_for_status(status: str, parsed_action: dict | None, validation_errors: list[str]) -> str:
        if status == "draft" and parsed_action:
            intent = parsed_action.get("intent")
            if intent == "move_task":
                return (
                    f"Черновик готов: перенести '{parsed_action.get('target_title')}' "
                    f"на {parsed_action.get('new_when')}."
                )
            if intent == "create_task":
                return f"Черновик готов: создать задачу '{parsed_action.get('title')}'."
            if intent == "complete_task":
                return f"Черновик готов: завершить '{parsed_action.get('target_title')}'."
        if status == "clarification_required":
            return "Команда неоднозначна. Нужно уточнение."
        if status == "cancelled":
            return "Черновик отменён."
        if status == "applied":
            return "Изменение применено."
        if status == "failed":
            return "Применение не удалось."
        if validation_errors:
            return validation_errors[0]
        return "Черновик обработан."

    @staticmethod
    def _user_timezone(user: User) -> ZoneInfo:
        try:
            return ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")
