class ApplyChangesService:
    """Validates and applies confirmed changes to external systems."""

    def apply(self, change_request_id: int) -> dict[str, str]:
        return {"status": "not_implemented", "change_request_id": str(change_request_id)}
