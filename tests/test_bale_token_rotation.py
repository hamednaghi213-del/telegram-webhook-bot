"""Regression tests for the centrally managed Bale bot token."""

import importlib
import sys
import types


def _load_branding_manager(monkeypatch, tenant):
    fake_database = types.ModuleType("core.database")
    fake_database.get_tenant = lambda _user_id: tenant
    fake_database.save_tenant = lambda **_kwargs: True
    fake_database.update_bale_settings = lambda *_args: True
    monkeypatch.setitem(sys.modules, "core.database", fake_database)
    sys.modules.pop("core.branding_manager", None)
    return importlib.import_module("core.branding_manager")


def test_render_bale_token_overrides_stale_tenant_token(monkeypatch):
    monkeypatch.setenv("BALE_BOT_TOKEN", "new-central-token")
    branding_manager = _load_branding_manager(monkeypatch, {
        "hashtag": "#news",
        "channel_tag": "@news",
        "bale_channel": "@news_bale",
        "bale_token": "revoked-old-token",
    })

    branding = branding_manager.get_branding(1)

    assert branding["bale_token"] == "new-central-token"


def test_tenant_token_remains_backward_compatible_without_render_token(monkeypatch):
    monkeypatch.delenv("BALE_BOT_TOKEN", raising=False)
    branding_manager = _load_branding_manager(monkeypatch, {
        "bale_channel": "@news_bale",
        "bale_token": "legacy-token",
    })

    branding = branding_manager.get_branding(1)

    assert branding["bale_token"] == "legacy-token"
