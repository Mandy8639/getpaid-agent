"""Build the OpenRouter client from settings."""

from getpaid.config import Settings, get_settings
from getpaid.llm.openrouter import Ledger, OpenRouterClient


def client_from_settings(settings: Settings | None = None) -> OpenRouterClient:
    s = settings or get_settings()
    ledger = Ledger(s.spend_ledger_path, s.total_spend_cap_usd, s.spend_reserve_usd)
    return OpenRouterClient(s.openrouter_api_key.get_secret_value(), s.model_list(), ledger)
