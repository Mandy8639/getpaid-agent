"""Settings from the environment (.env in development). Secrets never have defaults."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_models: str = ""
    total_spend_cap_usd: float = Field(default=5.0, gt=0, le=5.0)  # user: whole build ≤ $5
    spend_reserve_usd: float = Field(default=0.05, ge=0)
    spend_ledger_path: Path = REPO_ROOT / ".spend" / "ledger.json"
    database_url: str = "postgresql+psycopg://getpaid:getpaid@localhost:5434/getpaid"

    drafter: Literal["template", "llm"] = "template"
    web_origin: str = "http://localhost:3000"

    def model_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
