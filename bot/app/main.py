import asyncio
import os
from datetime import datetime
from html import escape
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes


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
        "",
        "Рекомендуемый порядок:",
        "1. /connect <token>",
        "2. /sync",
        "3. /day или /week",
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


async def backend_get(path: str, telegram_id: str) -> dict:
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=20.0) as client:
        response = await client.get(path, params={"telegram_id": telegram_id})
        response.raise_for_status()
        return response.json()


async def backend_post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=30.0) as client:
        response = await client.post(path, json=payload)
        response.raise_for_status()
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
    return application


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "replace-me" or BOT_TOKEN == "NO":
        asyncio.run(idle_mode())
        return

    application = build_application()
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
