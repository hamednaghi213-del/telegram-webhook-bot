"""Pure rules for optional Bale pairing in a Telegram-first workspace."""

from typing import Dict, Iterable


def has_required_telegram_destination(destinations: Iterable[Dict]) -> bool:
    return any(
        destination.get("platform") == "telegram"
        and destination.get("status") != "removed"
        for destination in destinations
    )
