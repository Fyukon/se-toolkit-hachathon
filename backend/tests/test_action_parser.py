from app.services.user_service import UserService


def test_user_service_resolves_default_telegram_id() -> None:
    service = UserService(db=None)  # type: ignore[arg-type]
    assert service.resolve_telegram_id(None) == "local-dev"
