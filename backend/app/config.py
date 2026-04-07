from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_debug: bool = True
    backend_cors_origins: str = Field(default="http://localhost:5173")
    backend_internal_url: str = "http://backend:8000"

    postgres_db: str = "se_toolkit"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_host: str = "db"
    postgres_port: int = 5432

    telegram_bot_token: str = "replace-me"
    telegram_webapp_url: str = "http://localhost:5173"

    singularity_api_base_url: str = "https://api.singularity-app.com"
    singularity_api_token: str | None = None
    default_telegram_user_id: str = "local-dev"

    llm_api_key: str = "replace-me"
    llm_model: str = "replace-me"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?connect_timeout=5"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
