from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "sqlite+aiosqlite:///./data/rankos.db"

    # Master switch: no outbound traffic of any kind until True.
    network_enabled: bool = False

    crawl_user_agent: str = "RankOSBot/0.1 (+https://rankos.local)"
    crawl_concurrency: int = 4
    crawl_max_pages: int = 500
    crawl_timeout_s: float = 15.0

    openai_api_key: str | None = None
    openai_model: str = "sol"
    openai_base_url: str | None = None
    # Send reasoning={"effort": ...}; only valid for reasoning models, so opt-in.
    openai_reasoning: bool = False

    gsc_service_account_json: str | None = None

    github_token: str | None = None
    repo_local_path: str | None = None

    worker_enabled: bool = True
    worker_poll_s: float = 1.5
    worker_concurrency: int = Field(default=2, ge=1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


class NetworkDisabledError(RuntimeError):
    """Raised by every outbound integration while NETWORK_ENABLED is false."""

    def __init__(self, what: str) -> None:
        super().__init__(f"Network is disabled (NETWORK_ENABLED=false); refused to {what}")


def assert_network(what: str) -> None:
    if not get_settings().network_enabled:
        raise NetworkDisabledError(what)
