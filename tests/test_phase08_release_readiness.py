from pathlib import Path

import pytest

from core.release_readiness import (
    missing_required_environment,
    parse_bool,
    validate_migration_sequence,
)


def test_required_environment_reports_missing_values():
    environment = {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_SECRET_TOKEN": "secret",
        "SUPABASE_URL": "url",
        "SUPABASE_KEY": "",
    }
    assert missing_required_environment(environment) == ["SUPABASE_KEY"]


def test_self_ping_boolean_is_strict_and_defaults_off():
    assert parse_bool("") is False
    assert parse_bool("true") is True
    assert parse_bool("OFF") is False
    with pytest.raises(ValueError):
        parse_bool("sometimes")


def test_repository_migrations_are_contiguous():
    schema_dir = Path(__file__).resolve().parents[1] / "schema"
    migrations = validate_migration_sequence(schema_dir)
    assert [item.name[:3] for item in migrations] == [
        "001", "002", "003", "004", "005", "006", "007", "008", "009",
        "010", "011", "012", "013", "014", "015", "016", "017", "018", "019", "020", "021",
    ]


def test_workspace_pending_action_migration_is_additive_and_constrained():
    migration = (
        Path(__file__).resolve().parents[1]
        / "schema"
        / "015_workspace_pending_actions.sql"
    ).read_text(encoding="utf-8").lower()

    assert "add column if not exists pending_workspace_action text null" in migration
    assert "add column if not exists pending_workspace_id bigint null" in migration
    assert "'create_workspace_name'" in migration
    assert "'rename_workspace'" in migration
    assert "references public.workspaces(id)" in migration
    assert "on delete set null" in migration
    assert "update public.users" not in migration
    assert "delete from" not in migration


def test_migration_gap_is_rejected(tmp_path):
    (tmp_path / "001_first.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 3", encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        validate_migration_sequence(tmp_path)
