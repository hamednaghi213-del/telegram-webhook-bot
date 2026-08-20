"""Production-readiness helpers that are safe to test without booting the app."""

import re
from pathlib import Path
from typing import Mapping, Sequence


REQUIRED_ENVIRONMENT = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_SECRET_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_KEY",
)


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None or not str(value).strip():
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def missing_required_environment(environment: Mapping[str, str]) -> Sequence[str]:
    return [name for name in REQUIRED_ENVIRONMENT if not environment.get(name)]


def validate_migration_sequence(schema_dir: Path) -> Sequence[Path]:
    """Return ordered migrations, rejecting duplicates and numbering gaps."""
    migrations = sorted(schema_dir.glob("[0-9][0-9][0-9]_*.sql"))
    numbers = []
    for migration in migrations:
        match = re.match(r"^(\d{3})_", migration.name)
        if match:
            numbers.append(int(match.group(1)))
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        raise ValueError(
            f"Migration sequence must be contiguous from 001: found {numbers}"
        )
    return migrations
