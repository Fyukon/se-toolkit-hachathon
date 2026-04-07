from app.services.apply_changes_service import ApplyChangesService


def test_apply_changes_placeholder_contract() -> None:
    result = ApplyChangesService().apply(42)
    assert result["status"] == "not_implemented"
    assert result["change_request_id"] == "42"
