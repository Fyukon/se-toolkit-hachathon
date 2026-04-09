import json

from sqlalchemy.orm import Session

from app.models.change_request import ChangeRequest
from app.models.user import User
from app.services.errors import ActionError
from app.services.singularity_client import SingularityClient
from app.services.sync_service import SyncService


class ApplyChangesService:
    """Validates and applies confirmed changes to external systems."""

    def __init__(self, db: Session):
        self.db = db

    def apply(self, user: User, change_request: ChangeRequest) -> dict[str, str]:
        if change_request.status == "applied":
            raise ActionError("Change request is already applied.", status_code=409)
        if change_request.status == "cancelled":
            raise ActionError("Cancelled change request cannot be applied.", status_code=409)
        if change_request.status == "clarification_required":
            raise ActionError("This change request still needs clarification.", status_code=409)
        if change_request.status != "draft":
            raise ActionError(f"Unsupported change request status: {change_request.status}", status_code=409)
        if not change_request.parsed_actions:
            raise ActionError("Change request does not contain an actionable draft.", status_code=400)
        if not user.singularity_access_token:
            raise ActionError("SingularityApp API token is not configured for this user.")

        parsed_action = json.loads(change_request.parsed_actions)
        intent = parsed_action.get("intent")
        payload = parsed_action.get("payload") or {}
        client = SingularityClient(user.singularity_access_token)

        try:
            if intent == "move_task":
                target_task_id = parsed_action.get("target_task_id")
                if not target_task_id:
                    raise ActionError("Move action does not contain a target task.", status_code=400)
                response = client.update_task(target_task_id, payload)
            elif intent == "complete_task":
                target_task_id = parsed_action.get("target_task_id")
                if not target_task_id:
                    raise ActionError("Complete action does not contain a target task.", status_code=400)
                response = client.update_task(target_task_id, payload)
            elif intent == "create_task":
                response = client.create_task(payload)
            else:
                raise ActionError(f"Unsupported action intent: {intent}", status_code=400)
        except Exception:
            change_request.status = "failed"
            self.db.commit()
            raise

        change_request.status = "applied"
        self.db.commit()
        self.db.refresh(change_request)

        # Keep local cache in sync with the source of truth after any confirmed write.
        SyncService(self.db).sync(user)

        return {
            "status": "applied",
            "change_request_id": str(change_request.id),
            "intent": str(intent),
            "external_id": str(response.get("id") or parsed_action.get("target_task_id") or ""),
        }
