import json
from datetime import date

import httpx

from app.config import settings
from app.services.errors import ActionError


class LLMService:
    """Wraps LLM calls for summaries and action parsing."""

    def summarize(self, payload: dict) -> str:
        return "LLM integration is not implemented yet."

    def parse_action_command(
        self,
        *,
        text: str,
        today: date,
        timezone: str,
        candidate_tasks: list[dict],
    ) -> dict | None:
        if not settings.llm_api_key or settings.llm_api_key in {"replace-me", "NO"}:
            return None

        system_prompt = (
            "You convert user scheduling commands into strict JSON. "
            "Never explain. Never wrap in markdown. "
            "Supported intents: move_task, create_task, complete_task, unknown. "
            "If the user wants to move an existing task, use move_task. "
            "If the user wants to create a new task, use create_task. "
            "If the user wants to mark an existing task as completed, use complete_task. "
            "Use candidate_tasks as grounding hints only. "
            "Do not fabricate task ids. "
            "Return concise target_hint/title/date_hint/time_hint values."
        )

        user_payload = {
            "today": today.isoformat(),
            "timezone": timezone,
            "text": text,
            "candidate_tasks": candidate_tasks[:20],
        }

        body = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "action_command",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "intent": {
                                "type": "string",
                                "enum": ["move_task", "create_task", "complete_task", "unknown"],
                            },
                            "target_hint": {"type": ["string", "null"]},
                            "title": {"type": ["string", "null"]},
                            "date_hint": {"type": ["string", "null"]},
                            "time_hint": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"]},
                            "reason": {"type": ["string", "null"]},
                        },
                        "required": ["intent", "target_hint", "title", "date_hint", "time_hint", "confidence", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        if settings.llm_site_url:
            headers["HTTP-Referer"] = settings.llm_site_url
        if settings.llm_app_name:
            headers["X-OpenRouter-Title"] = settings.llm_app_name

        try:
            with httpx.Client(timeout=40.0) as client:
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ActionError(f"OpenRouter request failed: {exc}", status_code=502) from exc

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ActionError("OpenRouter returned an unexpected response shape.", status_code=502) from exc

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ActionError("OpenRouter returned invalid JSON for action parsing.", status_code=502) from exc
