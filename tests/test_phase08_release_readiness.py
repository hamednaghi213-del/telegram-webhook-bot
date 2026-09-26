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
        "010", "011", "012", "013", "014", "015", "016", "017", "018",
        "019", "020", "021", "022", "023", "024", "025", "026", "027",
        "028", "029", "030", "031", "032", "033", "034", "035",
    ]


def test_bale_only_identity_migration_preserves_telegram_uniqueness():
    schema = Path(__file__).resolve().parents[1] / "schema"

    foundation = (
        schema / "001_phase1_workspace_foundation.sql"
    ).read_text(
        encoding="utf-8"
    ).lower()

    migration = (
        schema / "030_nullable_telegram_user_identity.sql"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "telegram_user_id bigint not null unique" in foundation
    assert "alter table public.users" in migration
    assert "alter column telegram_user_id drop not null" in migration
    assert "drop constraint" not in migration
    assert "drop index" not in migration
    assert "update public.users" not in migration
    assert "delete from" not in migration


def test_workspace_pending_action_migration_is_additive_and_constrained():
    migration = (
        Path(__file__).resolve().parents[1]
        / "schema"
        / "015_workspace_pending_actions.sql"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "add column if not exists pending_workspace_action text null" in migration
    assert "add column if not exists pending_workspace_id bigint null" in migration
    assert "'create_workspace_name'" in migration
    assert "'rename_workspace'" in migration
    assert "references public.workspaces(id)" in migration
    assert "on delete set null" in migration
    assert "update public.users" not in migration
    assert "delete from" not in migration


def test_canonical_branding_profile_sync_migration_is_present_and_safe():
    migration = (
        Path(__file__).resolve().parents[1]
        / "schema"
        / "034_canonical_branding_profile_sync.sql"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "sync_workspace_branding_to_media_identity" in migration
    assert "workspace_branding_canonical_media_sync" in migration
    assert "publication_icons" in migration
    assert "icons_enabled" in migration
    assert "publication_profile" in migration
    assert "media_identity_members" in migration
    assert "workspace_destinations" in migration
    assert "media_identity_id" in migration
    assert "on conflict (identity_key)" in migration
    assert "after insert or update of" in migration
    assert "delete from" not in migration
    assert "drop table" not in migration


def test_migration_gap_is_rejected(tmp_path):
    (tmp_path / "001_first.sql").write_text(
        "SELECT 1",
        encoding="utf-8",
    )
    (tmp_path / "003_third.sql").write_text(
        "SELECT 3",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contiguous"):
        validate_migration_sequence(tmp_path)