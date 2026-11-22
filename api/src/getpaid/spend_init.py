"""`make spend-init`: create the spend ledger once. Never resets an existing one."""

from getpaid.config import get_settings
from getpaid.llm.openrouter import Ledger


def main() -> None:
    s = get_settings()
    Ledger(s.spend_ledger_path, s.total_spend_cap_usd, s.spend_reserve_usd).create()
    print(f"spend ledger created at {s.spend_ledger_path} (cap ${s.total_spend_cap_usd:.2f})")


if __name__ == "__main__":
    main()
