import asyncio
import logging
import os
from datetime import datetime
from html import escape
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


BACKEND_URL = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL", "http://localhost:5173")
DISPLAY_TZ = ZoneInfo("Europe/Moscow")
TELEGRAM_MESSAGE_LIMIT = 3500


def is_https_webapp_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def build_keyboard() -> ReplyKeyboardMarkup | None:
    if not is_https_webapp_url(WEBAPP_URL):
        return None

    return ReplyKeyboardMarkup(
        [[KeyboardButton(text="Open Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
    )


def build_help_text() -> str:
    lines = [
        "Команды бота:",
        "/start - короткое приветствие",
        "/help - показать эту инструкцию",
        "/connect <singularity_api_token> - сохранить API token SingularityApp",
        "/sync - синхронизировать задачи из SingularityApp",
        "/day - показать summary на день",
        "/week - показать summary на неделю",
        "/action <команда> - создать draft изменения",
        "/confirm <id> - подтвердить draft и применить изменение",
        "/cancel_action <id> - отменить draft",
        "",
        "Рекомендуемый порядок:",
        "1. /connect <token>",
        "2. /sync",
        "3. /day или /week",
        "4. /action ...",
        "5. /confirm <id>",
    ]

    if not is_https_webapp_url(WEBAPP_URL):
        lines.extend(
            [
                "",
                "Mini App кнопка сейчас отключена, потому что Telegram принимает только https URL.",
                f"Локально Mini App можно открыть в браузере: {WEBAPP_URL}",
            ]
        )

    return "\n".join(lines)


def backend_candidates() -> list[str]:
    candidates = [
        BACKEND_URL,
        "http://backend:8000",
        "http://host.docker.internal:8000",
    ]
    unique_candidates: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.rstrip("/")
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_candidates.append(normalized)
    return unique_candidates


def create_backend_client(base_url: str, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        trust_env=False,
    )


def build_action_keyboard(payload: dict) -> InlineKeyboardMarkup | None:
    action_id = payload.get("id")
    if not action_id:
        return None

    status = payload.get("status")
    candidates = payload.get("candidates") or []

    if status == "clarification_required" and candidates:
        rows = []
        for index, candidate in enumerate(candidates[:5]):
            title = (candidate.get("title") or f"Вариант {index + 1}").strip()
            if len(title) > 48:
                title = f"{title[:45]}..."
            rows.append(
                [InlineKeyboardButton(text=title, callback_data=f"pick:{action_id}:{index}")]
            )
        rows.append([InlineKeyboardButton(text="Отменить", callback_data=f"cancel:{action_id}")])
        return InlineKeyboardMarkup(rows)

    if status == "draft":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm:{action_id}"),
                    InlineKeyboardButton(text="Отменить", callback_data=f"cancel:{action_id}"),
                ]
            ]
        )

    return None


async def backend_get(path: str, telegram_id: str) -> dict:
    last_transport_error: httpx.TransportError | None = None
    for base_url in backend_candidates():
        logger.info("Bot backend GET url=%s path=%s telegram_id=%s", base_url, path, telegram_id)
        async with create_backend_client(base_url=base_url, timeout=20.0) as client:
            try:
                response = await client.get(path, params={"telegram_id": telegram_id})
            except httpx.TransportError as exc:
                last_transport_error = exc
                logger.exception(
                    "Bot backend GET transport failure url=%s path=%s telegram_id=%s",
                    base_url,
                    path,
                    telegram_id,
                )
                continue

            response.raise_for_status()
            logger.info("Bot backend GET completed url=%s path=%s status=%s", base_url, path, response.status_code)
            return response.json()

    if last_transport_error is not None:
        raise last_transport_error

    async with create_backend_client(base_url=BACKEND_URL, timeout=20.0) as client:
        try:
            response = await client.get(path, params={"telegram_id": telegram_id})
        except httpx.HTTPError:
            logger.exception(
                "Bot backend GET transport failure url=%s path=%s telegram_id=%s",
                BACKEND_URL,
                path,
                telegram_id,
            )
            raise
        response.raise_for_status()
        logger.info("Bot backend GET completed path=%s status=%s", path, response.status_code)
        return response.json()


async def backend_post(path: str, payload: dict) -> dict:
    safe_payload = {key: ("***" if "token" in key.lower() else value) for key, value in payload.items()}
    last_transport_error: httpx.TransportError | None = None
    for base_url in backend_candidates():
        logger.info("Bot backend POST url=%s path=%s payload=%s", base_url, path, safe_payload)
        async with create_backend_client(base_url=base_url, timeout=30.0) as client:
            try:
                response = await client.post(path, json=payload)
            except httpx.TransportError as exc:
                last_transport_error = exc
                logger.exception(
                    "Bot backend POST transport failure url=%s path=%s payload=%s",
                    base_url,
                    path,
                    safe_payload,
                )
                continue

            response.raise_for_status()
            logger.info("Bot backend POST completed url=%s path=%s status=%s", base_url, path, response.status_code)
            return response.json()

    if last_transport_error is not None:
        raise last_transport_error

    async with create_backend_client(base_url=BACKEND_URL, timeout=30.0) as client:
        try:
            response = await client.post(path, json=payload)
        except httpx.HTTPError:
            logger.exception(
                "Bot backend POST transport failure url=%s path=%s payload=%s",
                BACKEND_URL,
                path,
                safe_payload,
            )
            raise
        response.raise_for_status()
        logger.info("Bot backend POST completed path=%s status=%s", path, response.status_code)
        return response.json()


def format_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            payload = exc.response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])

    return str(exc)


def format_priority(priority: str | None) -> str:
    mapping = {
        "high": "высокий",
        "normal": "обычный",
        "low": "низкий",
    }
    return mapping.get((priority or "").lower(), "не указан")


def format_status(status: str | None) -> str:
    mapping = {
        "open": "активна",
        "completed": "выполнена",
        "done": "выполнена",
        "scheduled": "запланирована",
    }
    return mapping.get((status or "").lower(), "неизвестно")


def format_when(raw_value: str | None) -> str:
    if not raw_value:
        return "без даты"

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return escape(raw_value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=DISPLAY_TZ)
    else:
        parsed = parsed.astimezone(DISPLAY_TZ)

    return parsed.strftime("%d.%m.%Y %H:%M")


def format_task_line(task: dict) -> str:
    title = escape(task.get("title") or "Без названия")
    when = format_when(task.get("when"))
    priority = format_priority(task.get("priority"))
    status = format_status(task.get("status"))

    return (
        f"<b>{title}</b>\n"
        f"   Время: {escape(when)}\n"
        f"   Приоритет: {escape(priority)}\n"
        f"   Статус: {escape(status)}"
    )


def format_summary_message(payload: dict) -> str:
    period = payload.get("period", "day")
    label = "План на день" if period == "day" else "План на неделю"
    summary = escape(payload.get("summary") or "Сводка недоступна.")
    tasks = payload.get("tasks") or []

    lines = [f"<b>{label}</b>", "", summary]

    if tasks:
        if period == "day":
            completed_tasks = [task for task in tasks if (task.get("status") or "").lower() in {"completed", "done"}]
            active_tasks = [task for task in tasks if (task.get("status") or "").lower() not in {"completed", "done"}]

            if completed_tasks:
                lines.extend(["", f"<b>Завершённые ({len(completed_tasks)}):</b>"])
                for index, task in enumerate(completed_tasks, start=1):
                    lines.append(f"\n{index}. {format_task_line(task)}")

            if active_tasks:
                lines.extend(["", f"<b>Предстоящие и активные ({len(active_tasks)}):</b>"])
                for index, task in enumerate(active_tasks, start=1):
                    lines.append(f"\n{index}. {format_task_line(task)}")

            if not completed_tasks and not active_tasks:
                lines.extend(["", "<i>Список задач пуст.</i>"])
        else:
            lines.extend(["", f"<b>Задачи ({len(tasks)}):</b>"])
            for index, task in enumerate(tasks, start=1):
                lines.append(f"\n{index}. {format_task_line(task)}")
    else:
        lines.extend(["", "<i>Список задач пуст.</i>"])

    return "\n".join(lines)


def format_action_message(payload: dict) -> str:
    lines = [
        f"<b>Action #{payload.get('id')}</b>",
        "",
        escape(payload.get("message") or "Результат недоступен."),
    ]

    if payload.get("intent"):
        lines.append(f"\nИнтент: <b>{escape(payload['intent'])}</b>")

    parsed = payload.get("parsed_action") or {}
    if parsed.get("target_title"):
        lines.append(f"Цель: <b>{escape(parsed['target_title'])}</b>")
    elif parsed.get("title"):
        lines.append(f"Новая задача: <b>{escape(parsed['title'])}</b>")

    if parsed.get("new_when"):
        lines.append(f"Новое время: <b>{escape(format_when(parsed['new_when']))}</b>")

    validation_errors = payload.get("validation_errors") or []
    if validation_errors:
        lines.append("\n<b>Ошибки / замечания:</b>")
        for item in validation_errors:
            lines.append(f"• {escape(str(item))}")

    candidates = payload.get("candidates") or []
    if candidates:
        lines.append("\n<b>Кандидаты:</b>")
        for item in candidates:
            title = escape(item.get("title") or "Без названия")
            when = format_when(item.get("when"))
            lines.append(f"• <b>{title}</b> — {escape(when)}")

    if payload.get("status") == "draft":
        lines.append(f"\nПодтвердить: <code>/confirm {payload.get('id')}</code>")
        lines.append(f"Отменить: <code>/cancel_action {payload.get('id')}</code>")

    return "\n".join(lines)


def split_html_message(message: str, max_length: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(message) <= max_length:
        return [message]

    chunks: list[str] = []
    remaining = message

    while len(remaining) > max_length:
        split_at = remaining.rfind("\n\n", 0, max_length)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunk = remaining[:split_at].strip()
        if not chunk:
            chunk = remaining[:max_length].strip()
            split_at = max_length

        chunks.append(chunk)
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


async def send_action_payload(message_target, payload: dict) -> None:
    message = format_action_message(payload)
    keyboard = build_action_keyboard(payload)
    chunks = split_html_message(message)
    for index, chunk in enumerate(chunks):
        await message_target.reply_text(
            chunk,
            parse_mode="HTML",
            reply_markup=keyboard if index == 0 else None,
        )


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = build_keyboard()
    text = "Бот готов. Напиши /help, чтобы увидеть команды и порядок работы."
    if keyboard is None:
        text += " Mini App кнопка отключена: Telegram принимает только https URL, а сейчас указан dev URL."

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
    )


async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        build_help_text(),
        reply_markup=build_keyboard(),
    )


async def connect(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    parts = update.message.text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else None
    telegram_id = str(update.effective_user.id)

    keyboard = build_keyboard()
    payload = {
        "telegram_id": telegram_id,
        "singularity_api_token": token,
        "timezone": "Europe/Moscow",
    }

    try:
        data = await backend_post("/auth/connect", payload)
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Не удалось подключить аккаунт: {format_http_error(exc)}")
        return

    status_text = "подключен" if data.get("connected") else "создан, но без токена"
    miniapp_suffix = (
        f" Mini App: {data.get('telegram_webapp_url')}"
        if keyboard is not None
        else " Mini App кнопка отключена до HTTPS URL."
    )
    await update.message.reply_text(
        f"Профиль {telegram_id} {status_text}.{miniapp_suffix}",
        reply_markup=keyboard,
    )


async def sync(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    keyboard = build_keyboard()
    telegram_id = str(update.effective_user.id)
    try:
        data = await backend_post("/sync/full", {"telegram_id": telegram_id})
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Синхронизация не удалась: {format_http_error(exc)}")
        return

    await update.message.reply_text(
        f"Синхронизация завершена. Задач: {data['tasks_synced']}, событий: {data['events_synced']}.",
        reply_markup=keyboard,
    )


async def day(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await send_summary(update, "/summary/day")


async def week(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await send_summary(update, "/summary/week")


async def action_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "Нужен текст команды. Пример: /action перенеси лабу DSA на завтра 15:00"
        )
        return

    telegram_id = str(update.effective_user.id)
    try:
        payload = await backend_post(
            "/actions/parse",
            {"telegram_id": telegram_id, "text": parts[1].strip()},
        )
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Не удалось создать draft: {format_http_error(exc)}")
        return

    await send_action_payload(update.message, payload)


async def confirm_action(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await update.message.reply_text("Нужен id draft. Пример: /confirm 12")
        return

    telegram_id = str(update.effective_user.id)
    change_request_id = parts[1].strip()
    try:
        payload = await backend_post(
            f"/actions/{change_request_id}/confirm",
            {"telegram_id": telegram_id},
        )
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Не удалось применить draft: {format_http_error(exc)}")
        return

    await send_action_payload(update.message, payload)


async def cancel_action_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await update.message.reply_text("Нужен id draft. Пример: /cancel_action 12")
        return

    telegram_id = str(update.effective_user.id)
    change_request_id = parts[1].strip()
    try:
        payload = await backend_post(
            f"/actions/{change_request_id}/cancel",
            {"telegram_id": telegram_id},
        )
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Не удалось отменить draft: {format_http_error(exc)}")
        return

    await send_action_payload(update.message, payload)


async def handle_action_callback(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None or query.message is None:
        return

    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) < 2:
        return

    action_name = parts[0]
    change_request_id = parts[1]
    telegram_id = str(query.from_user.id)

    try:
        if action_name == "pick" and len(parts) == 3:
            payload = await backend_post(
                f"/actions/{change_request_id}/select-candidate",
                {"telegram_id": telegram_id, "candidate_index": int(parts[2])},
            )
        elif action_name == "confirm":
            payload = await backend_post(
                f"/actions/{change_request_id}/confirm",
                {"telegram_id": telegram_id},
            )
        elif action_name == "cancel":
            payload = await backend_post(
                f"/actions/{change_request_id}/cancel",
                {"telegram_id": telegram_id},
            )
        else:
            await query.answer("Неизвестное действие.", show_alert=True)
            return
    except httpx.HTTPError as exc:
        await query.message.reply_text(f"Не удалось выполнить действие: {format_http_error(exc)}")
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("Failed to clear inline keyboard for action callback")

    await send_action_payload(query.message, payload)


async def send_summary(update: Update, path: str) -> None:
    if update.message is None or update.effective_user is None:
        return

    keyboard = build_keyboard()
    telegram_id = str(update.effective_user.id)
    try:
        data = await backend_get(path, telegram_id)
    except httpx.HTTPError as exc:
        await update.message.reply_text(f"Не удалось получить summary: {format_http_error(exc)}")
        return

    message = format_summary_message(data)
    chunks = split_html_message(message)
    for index, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk,
            reply_markup=keyboard if index == 0 else None,
            parse_mode="HTML",
        )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Telegram bot error", exc_info=context.error)

    if isinstance(update, Update) and update.message is not None:
        await update.message.reply_text(
            "Во время обработки команды произошла ошибка. Попробуй повторить ещё раз или проверь логи backend/bot."
        )


async def idle_mode() -> None:
    while True:
        print("Telegram bot token is not configured. Bot is running in idle mode.", flush=True)
        await asyncio.sleep(60)


def build_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("sync", sync))
    application.add_handler(CommandHandler("day", day))
    application.add_handler(CommandHandler("week", week))
    application.add_handler(CommandHandler("action", action_command))
    application.add_handler(CommandHandler("confirm", confirm_action))
    application.add_handler(CommandHandler("cancel_action", cancel_action_command))
    application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r"^(pick|confirm|cancel):"))
    application.add_error_handler(handle_error)
    return application


def main() -> None:
    logger.info("Bot startup backend_candidates=%s webapp_url=%s", backend_candidates(), WEBAPP_URL)
    if not BOT_TOKEN or BOT_TOKEN == "replace-me" or BOT_TOKEN == "NO":
        asyncio.run(idle_mode())
        return

    application = build_application()
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
