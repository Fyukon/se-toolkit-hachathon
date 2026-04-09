import httpx

from app.config import settings
from app.services.errors import SingularityAPIError


class SingularityClient:
    """Adapter for SingularityApp task endpoints using a Bearer API token."""

    def __init__(self, token: str):
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | bool] | None = None,
        json_payload: dict | None = None,
        timeout: float = 20.0,
    ) -> dict | list[dict]:
        with httpx.Client(
            base_url=settings.singularity_api_base_url,
            headers=self._headers(),
            timeout=timeout,
            trust_env=False,
        ) as client:
            try:
                response = client.request(method, path, params=params, json=json_payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or "SingularityApp returned an error."
                raise SingularityAPIError(
                    f"SingularityApp API error {exc.response.status_code}: {detail}",
                    status_code=exc.response.status_code,
                ) from exc
            except httpx.HTTPError as exc:
                raise SingularityAPIError(f"Failed to reach SingularityApp API: {exc}") from exc

            payload = response.json()

        return payload

    def fetch_events(self) -> list[dict]:
        # Version 1 relies on tasks because SingularityApp exposes task CRUD publicly.
        return []

    def validate_token(self) -> None:
        self.fetch_tasks(max_count=1)

    def fetch_tasks(
        self,
        *,
        start_date_from: str | None = None,
        start_date_to: str | None = None,
        include_removed: bool = False,
        include_archived: bool = False,
        include_all_recurrence_instances: bool = True,
        max_count: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        payload = self.fetch_tasks_payload(
            start_date_from=start_date_from,
            start_date_to=start_date_to,
            include_removed=include_removed,
            include_archived=include_archived,
            include_all_recurrence_instances=include_all_recurrence_instances,
            max_count=max_count,
            offset=offset,
        )

        return self.extract_tasks(payload)

    def fetch_tasks_payload(
        self,
        *,
        start_date_from: str | None = None,
        start_date_to: str | None = None,
        include_removed: bool = False,
        include_archived: bool = False,
        include_all_recurrence_instances: bool = True,
        max_count: int = 500,
        offset: int = 0,
    ) -> list[dict] | dict:
        params: dict[str, str | int | bool] = {
            "includeRemoved": include_removed,
            "includeArchived": include_archived,
            "includeAllRecurrenceInstances": include_all_recurrence_instances,
            "maxCount": max_count,
            "offset": offset,
        }
        if start_date_from:
            params["startDateFrom"] = start_date_from
        if start_date_to:
            params["startDateTo"] = start_date_to

        return self._request("GET", "/v2/task", params=params)

    def create_task(self, payload: dict) -> dict:
        result = self._request("POST", "/v2/task", json_payload=payload)
        return result if isinstance(result, dict) else {}

    def update_task(self, task_id: str, payload: dict) -> dict:
        result = self._request("PATCH", f"/v2/task/{task_id}", json_payload=payload)
        return result if isinstance(result, dict) else {}

    @staticmethod
    def extract_tasks(payload: list[dict] | dict) -> list[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("items", "results", "data", "tasks"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        return []

    @staticmethod
    def payload_debug_info(payload: list[dict] | dict) -> dict:
        if isinstance(payload, list):
            sample_keys = [str(key) for key in payload[0].keys()] if payload and isinstance(payload[0], dict) else []
            return {
                "payload_type": "list",
                "payload_size": len(payload),
                "selected_collection_key": None,
                "sample_keys": sample_keys,
            }

        if isinstance(payload, dict):
            sample_keys = [str(key) for key in payload.keys()]
            selected_collection_key = None
            payload_size = 0

            for key in ("items", "results", "data", "tasks"):
                value = payload.get(key)
                if isinstance(value, list):
                    selected_collection_key = key
                    payload_size = len(value)
                    if value and isinstance(value[0], dict):
                        sample_keys = [str(item_key) for item_key in value[0].keys()]
                    break

            return {
                "payload_type": "dict",
                "payload_size": payload_size,
                "selected_collection_key": selected_collection_key,
                "sample_keys": sample_keys[:20],
            }

        return {
            "payload_type": type(payload).__name__,
            "payload_size": 0,
            "selected_collection_key": None,
            "sample_keys": [],
        }
