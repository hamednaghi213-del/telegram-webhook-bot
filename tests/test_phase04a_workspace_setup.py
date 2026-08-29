"""
Phase 4A — One-Time Workspace Setup Tests
==========================================
26 focused tests covering:
  1-6   : Setup state lifecycle
  7-8   : Workspace branding
  9-11  : Destination registration
  12-13 : Setup completion requirements
  14-17 : Member / multi-workspace
  18-20 : Legacy & Phase 1/2/3 regression
  21-26 : Full command-handler integration
"""

import importlib
import sys
import types
from copy import deepcopy
from typing import Any, Dict, List, Optional


# =========================================================
# IN-MEMORY DATABASE (Phase 4A extended)
# =========================================================

class InMemoryDb4A:
    """
    In-memory database stub for Phase 4A tests.
    Extends the Phase 3 stub with new setup/branding/verification tables.
    """

    def __init__(self):
        self.users: List[Dict] = []
        self.workspaces: List[Dict] = []
        self.workspace_members: List[Dict] = []
        self.workspace_setup_states: Dict[int, Dict] = {}
        self.workspace_brandings: Dict[int, Dict] = {}
        self.publication_destinations: List[Dict] = []
        self.destination_verifications: Dict[int, Dict] = {}
        self.destination_brandings: Dict[int, Dict] = {}
        self.user_workspace_preferences: Dict[int, Dict] = {}
        self.tenants: Dict[int, Dict] = {}
        self._next_id = 1

    def _next(self):
        val = self._next_id
        self._next_id += 1
        return val

    # ── users ──────────────────────────────────────────
    def get_user_by_telegram_id(self, telegram_user_id):
        for u in self.users:
            if u["telegram_user_id"] == telegram_user_id:
                return u
        return None

    def get_or_create_user_by_telegram_id(self, telegram_user_id, status="active"):
        user = self.get_user_by_telegram_id(telegram_user_id)
        if user:
            return user
        user = {"id": self._next(), "telegram_user_id": telegram_user_id, "status": status}
        self.users.append(user)
        return user

    # ── tenants (legacy) ───────────────────────────────
    def get_tenant(self, user_id):
        return self.tenants.get(user_id)

    def save_tenant(self, user_id, bot_token, telegram_channel,
                    bale_channel="", bale_token="", hashtag=None, channel_tag=None):
        self.tenants[user_id] = {
            "user_id": user_id, "bot_token": bot_token,
            "telegram_channel": telegram_channel,
            "bale_channel": bale_channel, "bale_token": bale_token,
            "hashtag": hashtag, "channel_tag": channel_tag,
        }
        return True

    def update_bale_settings(self, user_id, bale_channel, bale_token):
        t = self.tenants.get(user_id)
        if not t:
            return False
        t["bale_channel"] = bale_channel
        t["bale_token"] = bale_token
        return True

    # ── workspaces ─────────────────────────────────────
    def list_owned_workspaces(self, owner_user_id, include_inactive=False):
        rows = [w for w in self.workspaces if w["owner_user_id"] == owner_user_id]
        if not include_inactive:
            rows = [w for w in rows if w.get("status") == "active"]
        return sorted(rows, key=lambda x: x["id"])

    def create_workspace(self, name, owner_user_id, status="active"):
        ws = {"id": self._next(), "name": name, "owner_user_id": owner_user_id, "status": status}
        self.workspaces.append(ws)
        self.add_workspace_member(ws["id"], owner_user_id, role="owner", status="active")
        return ws

    def get_workspace(self, workspace_id):
        for w in self.workspaces:
            if w["id"] == workspace_id:
                return w
        return None

    # ── workspace members ──────────────────────────────
    def get_workspace_member(self, workspace_id, user_id):
        for m in self.workspace_members:
            if m["workspace_id"] == workspace_id and m["user_id"] == user_id:
                return m
        return None

    def add_workspace_member(self, workspace_id, user_id, role="writer", status="active"):
        existing = self.get_workspace_member(workspace_id, user_id)
        if existing:
            return existing
        m = {"id": self._next(), "workspace_id": workspace_id, "user_id": user_id,
             "role": role, "status": status}
        self.workspace_members.append(m)
        return m

    def update_workspace_member_role(self, workspace_id, user_id, role):
        m = self.get_workspace_member(workspace_id, user_id)
        if m:
            m["role"] = role
        return m

    def update_workspace_member_status(self, workspace_id, user_id, status):
        m = self.get_workspace_member(workspace_id, user_id)
        if m:
            m["status"] = status
        return m

    def list_workspace_members(self, workspace_id, status_filter="active"):
        rows = [m for m in self.workspace_members if m["workspace_id"] == workspace_id]
        if status_filter:
            rows = [m for m in rows if m.get("status") == status_filter]
        return rows

    def list_user_workspaces(self, user_id, include_inactive=False):
        rows = []
        for member in self.workspace_members:
            if member["user_id"] != user_id:
                continue
            if not include_inactive and member.get("status") != "active":
                continue
            workspace = self.get_workspace(member["workspace_id"])
            if not workspace:
                continue
            if not include_inactive and workspace.get("status") != "active":
                continue
            row = deepcopy(workspace)
            row["membership_role"] = member.get("role")
            row["membership_status"] = member.get("status")
            rows.append(row)
        return sorted(rows, key=lambda item: item["id"])

    def get_active_workspace_preference(self, user_id):
        return deepcopy(self.user_workspace_preferences.get(user_id))

    def set_active_workspace(self, user_id, workspace_id):
        member = self.get_workspace_member(workspace_id, user_id)
        if not member or member.get("status") != "active":
            raise ValueError("User is not an active member")
        row = {
            "user_id": user_id,
            "active_workspace_id": workspace_id,
            "context_type": "workspace",
        }
        self.user_workspace_preferences[user_id] = row
        return deepcopy(row)

    def set_active_legacy_context(self, user_id):
        row = {
            "user_id": user_id,
            "active_workspace_id": None,
            "context_type": "legacy",
        }
        self.user_workspace_preferences[user_id] = row
        return deepcopy(row)

    # ── workspace setup state ──────────────────────────
    def get_workspace_setup_state(self, workspace_id):
        return self.workspace_setup_states.get(workspace_id)

    def upsert_workspace_setup_state(self, workspace_id, step, current_step_key=None):
        row = dict(self.workspace_setup_states.get(workspace_id) or {})
        row.update({
            "workspace_id": workspace_id,
            "step": step,
            "current_step_key": current_step_key,
        })
        row.setdefault("branding_sample_text", "")
        row.setdefault("branding_sample_icons", [])
        row.setdefault("branding_sample_status", "not_started")
        row.setdefault("branding_sample_bale_url", "")
        row.setdefault("branding_sample_bale_channel", "")
        row.setdefault("branding_sample_bale_status", "none")
        row.setdefault("branding_sample_profile", {})
        self.workspace_setup_states[workspace_id] = row
        return deepcopy(row)

    def update_workspace_branding_sample(self, workspace_id, sample_text,
                                         sample_icons, status, bale_url=None,
                                         bale_channel=None, bale_status=None,
                                         profile=None):
        row = self.workspace_setup_states[workspace_id]
        row.update({
            "branding_sample_text": (sample_text or "").strip(),
            "branding_sample_icons": list(sample_icons or []),
            "branding_sample_status": status,
        })
        if bale_url is not None:
            row["branding_sample_bale_url"] = (bale_url or "").strip()
        if bale_channel is not None:
            row["branding_sample_bale_channel"] = (bale_channel or "").strip()
        if bale_status is not None:
            row["branding_sample_bale_status"] = bale_status
        if profile is not None:
            row["branding_sample_profile"] = dict(profile or {})
        return deepcopy(row)

    # ── workspace branding ─────────────────────────────
    def get_workspace_branding(self, workspace_id):
        return self.workspace_brandings.get(workspace_id)

    def upsert_workspace_branding(self, workspace_id, media_name, hashtag, channel_tag):
        row = dict(self.workspace_brandings.get(workspace_id) or {})
        row.update({
            "workspace_id": workspace_id,
            "media_name": (media_name or "").strip(),
            "hashtag": (hashtag or "").strip(),
            "channel_tag": (channel_tag or "").strip(),
        })
        row.setdefault("publication_icons", [])
        row.setdefault("icons_enabled", False)
        row.setdefault("publication_profile", {})
        self.workspace_brandings[workspace_id] = row
        return deepcopy(row)

    def update_workspace_branding_icons(self, workspace_id, icons, enabled=True):
        row = self.workspace_brandings[workspace_id]
        row["publication_icons"] = list(icons or [])
        row["icons_enabled"] = bool(enabled and icons)
        return deepcopy(row)

    def update_workspace_branding_profile(self, workspace_id, profile):
        row = self.workspace_brandings[workspace_id]
        row["publication_profile"] = dict(profile or {})
        return deepcopy(row)

    # ── publication destinations ───────────────────────
    def list_workspace_destinations(self, workspace_id, include_removed=False):
        rows = [d for d in self.publication_destinations if d["workspace_id"] == workspace_id]
        if not include_removed:
            rows = [d for d in rows if d.get("status") != "removed"]
        return sorted(rows, key=lambda x: x["id"])

    def create_publication_destination(self, workspace_id, platform, destination_type,
                                        name, external_id, status="active", is_default=False):
        ws = self.get_workspace(workspace_id)
        if not ws:
            raise ValueError(f"Workspace not found: {workspace_id}")
        # Duplicate check
        for d in self.publication_destinations:
            if (d["workspace_id"] == workspace_id
                    and d["platform"] == platform
                    and d["external_id"] == str(external_id).strip()
                    and d.get("status") != "removed"):
                return d
        dest = {
            "id": self._next(),
            "workspace_id": workspace_id,
            "platform": platform,
            "destination_type": destination_type,
            "name": name,
            "external_id": str(external_id).strip(),
            "status": status,
            "is_default": is_default,
        }
        self.publication_destinations.append(dest)
        return deepcopy(dest)

    # ── destination verification ───────────────────────
    def get_destination_verification(self, destination_id):
        return self.destination_verifications.get(destination_id)

    def upsert_destination_verification(self, destination_id, verified=False, verification_note=""):
        row = {
            "destination_id": destination_id,
            "verified": verified,
            "verification_note": (verification_note or "").strip(),
        }
        self.destination_verifications[destination_id] = row
        return deepcopy(row)

    # ── destination branding ────────────────────────────
    def get_destination_branding(self, destination_id):
        return self.destination_brandings.get(destination_id)

    def upsert_destination_branding(self, destination_id, hashtag="", channel_tag="",
                                     custom_footer=None, footer_enabled=False):
        row = {
            "destination_id": destination_id,
            "hashtag": (hashtag or "").strip(),
            "channel_tag": (channel_tag or "").strip(),
            "custom_footer": custom_footer,
            "footer_enabled": bool(footer_enabled),
        }
        self.destination_brandings[destination_id] = row
        return deepcopy(row)


# =========================================================
# LOADER HELPERS
# =========================================================

def _make_fake_db_module(db: InMemoryDb4A) -> types.ModuleType:
    """Build a fake core.database module backed by db."""
    mod = types.ModuleType("core.database")
    mod.get_tenant = db.get_tenant
    mod.save_tenant = db.save_tenant
    mod.update_bale_settings = db.update_bale_settings
    mod.get_user_by_telegram_id = db.get_user_by_telegram_id
    mod.get_or_create_user_by_telegram_id = db.get_or_create_user_by_telegram_id
    mod.create_workspace = db.create_workspace
    mod.list_owned_workspaces = db.list_owned_workspaces
    mod.get_workspace = db.get_workspace
    mod.get_workspace_member = db.get_workspace_member
    mod.add_workspace_member = db.add_workspace_member
    mod.update_workspace_member_role = db.update_workspace_member_role
    mod.update_workspace_member_status = db.update_workspace_member_status
    mod.list_workspace_members = db.list_workspace_members
    mod.list_user_workspaces = db.list_user_workspaces
    mod.get_active_workspace_preference = db.get_active_workspace_preference
    mod.set_active_workspace = db.set_active_workspace
    mod.set_active_legacy_context = db.set_active_legacy_context
    # Phase 4A additions
    mod.get_workspace_setup_state = db.get_workspace_setup_state
    mod.upsert_workspace_setup_state = db.upsert_workspace_setup_state
    mod.update_workspace_branding_sample = db.update_workspace_branding_sample
    mod.get_workspace_branding = db.get_workspace_branding
    mod.upsert_workspace_branding = db.upsert_workspace_branding
    mod.update_workspace_branding_icons = db.update_workspace_branding_icons
    mod.update_workspace_branding_profile = db.update_workspace_branding_profile
    mod.list_workspace_destinations = db.list_workspace_destinations
    mod.create_publication_destination = db.create_publication_destination
    mod.get_destination_verification = db.get_destination_verification
    mod.upsert_destination_verification = db.upsert_destination_verification
    mod.get_destination_branding = db.get_destination_branding
    mod.upsert_destination_branding = db.upsert_destination_branding
    return mod


def _load_modules(monkeypatch):
    """Load workspace_setup and command_handler with the in-memory db wired in."""
    db = InMemoryDb4A()
    fake_db = _make_fake_db_module(db)

    for mod_name in ["core.database", "core.workspace_setup", "core.command_handler"]:
        sys.modules.pop(mod_name, None)

    monkeypatch.setitem(sys.modules, "core.database", fake_db)

    ws_mod = importlib.import_module("core.workspace_setup")
    ws_mod = importlib.reload(ws_mod)

    ch_mod = importlib.import_module("core.command_handler")
    ch_mod = importlib.reload(ch_mod)

    sent: List = []
    sent_keyboards: List = []
    monkeypatch.setattr(ch_mod, "send_message",
                        lambda cid, txt, parse_mode=None: sent.append((cid, txt)) or True)
    monkeypatch.setattr(ch_mod, "send_long_message",
                        lambda cid, txt, max_len=4096: sent.append((cid, txt)) or True)
    monkeypatch.setattr(
        ch_mod,
        "send_message_with_keyboard",
        lambda cid, txt, keyboard: (
            sent.append((cid, txt)),
            sent_keyboards.append((cid, keyboard)),
            True,
        )[-1],
    )
    ch_mod._test_sent_keyboards = sent_keyboards

    return ws_mod, ch_mod, db, sent


# =========================================================
# TESTS: SETUP STATE LIFECYCLE  (1-6)
# =========================================================

def test_01_new_workspace_begins_incomplete(monkeypatch):
    """New workspace has no setup state → treated as not_started."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1001)
    ws = db.create_workspace("رسانه من", user["id"])

    state = ws_mod.get_or_init_setup_state(ws["id"])
    assert state["step"] == "not_started"
    assert state["current_step_key"] is None


def test_02_setup_enters_in_progress_on_start(monkeypatch):
    """start_setup transitions state to in_progress at setup_channel."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1002)
    ws = db.create_workspace("رسانه من", user["id"])

    state = ws_mod.start_setup(ws["id"])
    assert state["step"] == "in_progress"
    assert state["current_step_key"] == "setup_channel"


def test_03_setup_state_persists_in_db(monkeypatch):
    """After start_setup, state reads back correctly from db."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1003)
    ws = db.create_workspace("رسانه من", user["id"])

    ws_mod.start_setup(ws["id"])
    stored = db.get_workspace_setup_state(ws["id"])
    assert stored is not None
    assert stored["step"] == "in_progress"
    assert stored["current_step_key"] == "setup_channel"


def test_04_interrupted_setup_resumes_from_correct_step(monkeypatch):
    """advance_to_step persists step; start_setup resumes it."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1004)
    ws = db.create_workspace("رسانه من", user["id"])

    ws_mod.start_setup(ws["id"])
    ws_mod.advance_to_step(ws["id"], "setup_branding")

    # Simulate new session: call start_setup again
    resumed = ws_mod.start_setup(ws["id"])
    assert resumed["step"] == "in_progress"
    assert resumed["current_step_key"] == "setup_branding"


def test_05_repeated_start_does_not_restart_setup(monkeypatch):
    """Calling start multiple times does not reset a completed setup."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1005)
    ws = db.create_workspace("رسانه من", user["id"])

    db.upsert_workspace_setup_state(ws["id"], "completed", None)

    # start_setup on completed workspace must leave it completed
    state = ws_mod.start_setup(ws["id"])
    assert state["step"] == "completed"


def test_06_completed_setup_stays_completed(monkeypatch):
    """complete_setup marks state as completed; subsequent calls are idempotent."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(1006)
    ws = db.create_workspace("رسانه من", user["id"])

    db.upsert_workspace_branding(ws["id"], "رسانه‌ام", "#هشتگ", "@تگ")
    db.upsert_workspace_setup_state(ws["id"], "in_progress", "setup_member")
    db.update_workspace_branding_sample(ws["id"], "نمونه", [], "confirmed")
    db.create_publication_destination(ws["id"], "telegram", "channel", "ch", "@testchan", "inactive")

    ok, err = ws_mod.complete_setup(ws["id"], user["id"])
    assert ok, f"Expected completion, got error: {err}"
    assert ws_mod.is_setup_completed(ws["id"])

    # Call again — still completed, no error
    ok2, _ = ws_mod.complete_setup(ws["id"], user["id"])
    assert ok2
    assert ws_mod.is_setup_completed(ws["id"])


# =========================================================
# TESTS: WORKSPACE BRANDING  (7-8)
# =========================================================

def test_07_workspace_branding_stored_correctly(monkeypatch):
    """save_workspace_branding writes media_name, hashtag, channel_tag."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(2001)
    ws = db.create_workspace("رسانه من", user["id"])

    branding = ws_mod.save_workspace_branding(ws["id"], "دنیا۲۴", "#دنیا_۲۴", "@Donya24News")
    assert branding is not None
    assert branding["media_name"] == "دنیا۲۴"
    assert branding["hashtag"] == "#دنیا_۲۴"
    assert branding["channel_tag"] == "@Donya24News"
    assert branding["workspace_id"] == ws["id"]


def test_08_branding_belongs_to_workspace_not_user(monkeypatch):
    """Two users in different workspaces have independent branding."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    u1 = db.get_or_create_user_by_telegram_id(2002)
    u2 = db.get_or_create_user_by_telegram_id(2003)
    ws1 = db.create_workspace("رسانه ۱", u1["id"])
    ws2 = db.create_workspace("رسانه ۲", u2["id"])

    ws_mod.save_workspace_branding(ws1["id"], "برند ۱", "#h1", "@t1")
    ws_mod.save_workspace_branding(ws2["id"], "برند ۲", "#h2", "@t2")

    b1 = db.get_workspace_branding(ws1["id"])
    b2 = db.get_workspace_branding(ws2["id"])
    assert b1["media_name"] == "برند ۱"
    assert b2["media_name"] == "برند ۲"
    # Branding is keyed by workspace, not user
    assert b1["workspace_id"] == ws1["id"]
    assert b2["workspace_id"] == ws2["id"]


# =========================================================
# TESTS: DESTINATION REGISTRATION  (9-11)
# =========================================================

def test_09_two_destinations_added_in_same_setup(monkeypatch):
    """Both channels can be registered in a single setup session."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(3001)
    ws = db.create_workspace("رسانه من", user["id"])

    d1, dup1 = ws_mod.register_channel_destination(ws["id"], "@Channel1", "کانال ۱")
    d2, dup2 = ws_mod.register_channel_destination(ws["id"], "@Channel2", "کانال ۲")

    assert not dup1 and d1 is not None
    assert not dup2 and d2 is not None
    all_dests = db.list_workspace_destinations(ws["id"])
    assert len(all_dests) == 2


def test_10_more_than_two_destinations_supported(monkeypatch):
    """No hard cap: three or more channels can be added."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(3002)
    ws = db.create_workspace("رسانه من", user["id"])

    for i in range(5):
        d, dup = ws_mod.register_channel_destination(ws["id"], f"@Chan{i}", f"کانال {i}")
        assert not dup and d is not None

    assert len(db.list_workspace_destinations(ws["id"])) == 5


def test_11_duplicate_destination_protected(monkeypatch):
    """Registering the same channel twice returns is_duplicate=True."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(3003)
    ws = db.create_workspace("رسانه من", user["id"])

    _, dup1 = ws_mod.register_channel_destination(ws["id"], "@SameChan", "کانال")
    _, dup2 = ws_mod.register_channel_destination(ws["id"], "@SameChan", "کانال")
    assert not dup1
    assert dup2
    assert len(db.list_workspace_destinations(ws["id"])) == 1


# =========================================================
# TESTS: SETUP COMPLETION REQUIREMENTS  (12-13)
# =========================================================

def test_12_setup_cannot_complete_without_valid_destination(monkeypatch):
    """complete_setup fails when no destination is registered."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(4001)
    ws = db.create_workspace("رسانه من", user["id"])
    db.upsert_workspace_branding(ws["id"], "رسانه‌ام", "#h", "@t")

    ok, reason = ws_mod.complete_setup(ws["id"], user["id"])
    assert not ok
    assert reason is not None


def test_13_setup_cannot_complete_without_branding(monkeypatch):
    """complete_setup fails when branding has no media_name."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(4002)
    ws = db.create_workspace("رسانه من", user["id"])
    db.create_publication_destination(ws["id"], "telegram", "channel", "ch", "@ch", "inactive")
    # No branding stored at all

    ok, reason = ws_mod.complete_setup(ws["id"], user["id"])
    assert not ok
    assert reason is not None


# =========================================================
# TESTS: MEMBER / MULTI-WORKSPACE  (14-17)
# =========================================================

def test_14_owner_remains_active_owner_after_setup(monkeypatch):
    """Owner membership is preserved with role=owner, status=active."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(5001)
    ws = db.create_workspace("رسانه من", user["id"])

    db.upsert_workspace_branding(ws["id"], "رسانه", "#h", "@t")
    db.upsert_workspace_setup_state(ws["id"], "in_progress", "setup_member")
    db.update_workspace_branding_sample(ws["id"], "نمونه", [], "confirmed")
    db.create_publication_destination(ws["id"], "telegram", "channel", "c", "@c", "inactive")
    ok, _ = ws_mod.complete_setup(ws["id"], user["id"])
    assert ok

    m = db.get_workspace_member(ws["id"], user["id"])
    assert m["role"] == "owner"
    assert m["status"] == "active"


def test_15_second_member_can_be_added(monkeypatch):
    """add_member_to_workspace adds a non-owner member successfully."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    owner = db.get_or_create_user_by_telegram_id(5002)
    ws = db.create_workspace("رسانه من", owner["id"])

    membership, err = ws_mod.add_member_to_workspace(ws["id"], 9999, "manager")
    assert err is None
    assert membership is not None
    assert membership["role"] == "manager"


def test_16_same_telegram_user_belongs_to_two_workspaces(monkeypatch):
    """Admin B can be a member of both workspace A and workspace B."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    owner_a = db.get_or_create_user_by_telegram_id(5003)
    owner_b = db.get_or_create_user_by_telegram_id(5004)
    shared_admin_tg = 8888

    ws_a = db.create_workspace("رسانه الف", owner_a["id"])
    ws_b = db.create_workspace("رسانه ب", owner_b["id"])

    m_a, err_a = ws_mod.add_member_to_workspace(ws_a["id"], shared_admin_tg, "manager")
    m_b, err_b = ws_mod.add_member_to_workspace(ws_b["id"], shared_admin_tg, "publisher")

    assert err_a is None and m_a is not None
    assert err_b is None and m_b is not None

    # Same Telegram user → same user row, but different memberships
    shared_user = db.get_user_by_telegram_id(shared_admin_tg)
    assert shared_user is not None
    mem_a = db.get_workspace_member(ws_a["id"], shared_user["id"])
    mem_b = db.get_workspace_member(ws_b["id"], shared_user["id"])
    assert mem_a is not None
    assert mem_b is not None
    assert mem_a["id"] != mem_b["id"]   # different membership rows
    assert len([u for u in db.users if u["telegram_user_id"] == shared_admin_tg]) == 1


def test_17_member_role_is_workspace_specific(monkeypatch):
    """The same user can have different roles in different workspaces."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    owner_a = db.get_or_create_user_by_telegram_id(5005)
    owner_b = db.get_or_create_user_by_telegram_id(5006)
    shared_tg = 7777

    ws_a = db.create_workspace("رسانه الف", owner_a["id"])
    ws_b = db.create_workspace("رسانه ب", owner_b["id"])

    ws_mod.add_member_to_workspace(ws_a["id"], shared_tg, "writer")
    ws_mod.add_member_to_workspace(ws_b["id"], shared_tg, "manager")

    user = db.get_user_by_telegram_id(shared_tg)
    assert db.get_workspace_member(ws_a["id"], user["id"])["role"] == "writer"
    assert db.get_workspace_member(ws_b["id"], user["id"])["role"] == "manager"


# =========================================================
# TESTS: LEGACY PROTECTION + PHASE 1/2/3 REGRESSION  (18-20)
# =========================================================

def test_18_legacy_tenant_user_remains_unaffected(monkeypatch):
    """A user with a legacy tenant record is never put through workspace setup."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    db.tenants[9001] = {"user_id": 9001, "telegram_channel": "@legacy"}

    ch_mod.handle_start(9001)

    assert any("register" in m[1].lower() or "استفاده کنید" in m[1] for m in sent)
    assert len(db.workspaces) == 0
    assert len(db.users) == 0


def test_19_get_tenant_unchanged_for_legacy_user(monkeypatch):
    """get_tenant continues to return the legacy record for legacy users."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    db.tenants[9002] = {"user_id": 9002, "telegram_channel": "@oldchannel"}

    # handle_start for legacy user should NOT call get_or_create_user
    ch_mod.handle_start(9002)

    tenant = db.get_tenant(9002)
    assert tenant is not None
    assert tenant["telegram_channel"] == "@oldchannel"
    # workspace table must be empty — legacy user was not onboarded
    assert len(db.workspaces) == 0


def test_20_phase1_and_phase2_workspace_member_helpers_unchanged(monkeypatch):
    """Phase 1/2 workspace + member helpers work correctly in Phase 4A env."""
    _, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(9103)
    ws = db.create_workspace("رسانه تست", user["id"])
    assert ws["name"] == "رسانه تست"

    owner_mem = db.get_workspace_member(ws["id"], user["id"])
    assert owner_mem["role"] == "owner"

    # Update role and status
    db.update_workspace_member_role(ws["id"], user["id"], "manager")
    assert db.get_workspace_member(ws["id"], user["id"])["role"] == "manager"

    db.update_workspace_member_status(ws["id"], user["id"], "suspended")
    assert db.get_workspace_member(ws["id"], user["id"])["status"] == "suspended"


# =========================================================
# TESTS: COMMAND-HANDLER INTEGRATION  (21-26)
# =========================================================

def test_21_start_new_user_shows_setup_prompt(monkeypatch):
    """/start for a brand-new workspace user shows /setup prompt."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1001)

    assert len(db.workspaces) == 1
    last_msg = sent[-1][1]
    assert "/setup" in last_msg
    assert ch_mod._test_sent_keyboards == [
        (1001, [[{
            "text": "🚀 شروع راه‌اندازی",
            "callback_data": "setup:start",
        }]])
    ]


def test_22_start_completed_setup_shows_ready_panel(monkeypatch):
    """/start after completed setup shows the ready panel, not the wizard."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1002)  # creates workspace + not_started state

    user = db.get_user_by_telegram_id(1002)
    ws = db.list_owned_workspaces(user["id"])[0]
    db.upsert_workspace_setup_state(ws["id"], "completed", None)

    sent.clear()
    ch_mod.handle_start(1002)
    last_msg = sent[-1][1]
    assert "آماده" in last_msg or "/settings" in last_msg
    assert "/setup" not in last_msg


def test_23_repeated_start_does_not_duplicate_workspace(monkeypatch):
    """/start called twice must not create duplicate workspaces/members."""
    _, ch_mod, db, _ = _load_modules(monkeypatch)
    ch_mod.handle_start(1003)
    ch_mod.handle_start(1003)

    assert len(db.workspaces) == 1
    assert len(db.users) == 1
    owner_mems = [m for m in db.workspace_members if m["role"] == "owner"]
    assert len(owner_mems) == 1


def test_23a_setup_command_starts_new_user_at_first_step(monkeypatch):
    _, ch_mod, db, _ = _load_modules(monkeypatch)
    ch_mod.handle_start(1004)

    assert ch_mod.handle_command("/setup", 1004) is True
    state = db.get_workspace_setup_state(db.workspaces[0]["id"])
    assert state["step"] == "in_progress"
    assert state["current_step_key"] == "setup_channel"


def test_23b_setup_command_resumes_saved_step(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1005)
    workspace_id = db.workspaces[0]["id"]
    db.upsert_workspace_setup_state(
        workspace_id,
        "in_progress",
        "setup_branding",
    )

    sent.clear()
    assert ch_mod.handle_command("/setup", 1005) is True
    state = db.get_workspace_setup_state(workspace_id)
    assert state["current_step_key"] == "setup_branding"
    assert "مرحله ۲" in sent[-1][1]


def test_23c_setup_command_does_not_reset_completed_workspace(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1006)
    workspace_id = db.workspaces[0]["id"]
    db.upsert_workspace_setup_state(workspace_id, "completed", None)

    sent.clear()
    assert ch_mod.handle_command("/setup", 1006) is True
    state = db.get_workspace_setup_state(workspace_id)
    assert state["step"] == "completed"
    assert state["current_step_key"] is None
    assert "قبلاً کامل شده" in sent[-1][1]


def test_23d_workspace_help_explains_complete_new_user_flow(monkeypatch):
    _, ch_mod, _, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1007)

    sent.clear()
    assert ch_mod.handle_command("/help", 1007) is True
    help_text = sent[-1][1]
    assert "راهنمای کامل کاربر جدید" in help_text
    assert "🚀 شروع راه‌اندازی" in help_text
    assert "/addchannel @channel" in help_text
    assert "/skipbale" in help_text
    assert "/confirmbranding" in help_text
    assert "/addmember TELEGRAM_ID manager" in help_text
    assert "/workspaces" in help_text
    assert "/register" in help_text


def test_23e_workspace_help_reports_saved_setup_step(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(1008)
    workspace_id = db.workspaces[0]["id"]
    db.upsert_workspace_setup_state(
        workspace_id,
        "in_progress",
        "setup_branding_sample",
    )

    sent.clear()
    assert ch_mod.handle_command("/help", 1008) is True
    assert "ارسال و تأیید نمونه پیام" in sent[-1][1]
    assert "برای ادامه از همان مرحله: /setup" in sent[-1][1]


def test_24_addchannel_command_registers_unverified_destination(monkeypatch):
    """/addchannel stores channel as inactive + creates verification record."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2001)

    ch_mod.handle_command("/addchannel @TestChannel", 2001)

    dests = db.list_workspace_destinations(db.workspaces[0]["id"])
    assert len(dests) == 1
    dest = dests[0]
    assert dest["external_id"] == "@TestChannel"
    assert dest["status"] == "inactive"   # NOT active/ready for publication

    verification = db.get_destination_verification(dest["id"])
    assert verification is not None
    assert verification["verified"] is False
    assert "pending" in verification["verification_note"].lower()


def test_25_setbranding_command_saves_workspace_branding(monkeypatch):
    """/setbranding stores branding on the workspace, not the user."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2002)

    ch_mod.handle_command("/setbranding دنیا۲۴ #دنیا_۲۴ @Donya24News", 2002)

    ws = db.workspaces[0]
    branding = db.get_workspace_branding(ws["id"])
    assert branding is not None
    assert branding["media_name"] == "دنیا۲۴"
    assert branding["hashtag"] == "#دنیا_۲۴"
    assert branding["channel_tag"] == "@Donya24News"
    assert branding["workspace_id"] == ws["id"]


def test_25a_stepwise_branding_preserves_full_media_name(monkeypatch):
    """The onboarding path collects name, hashtag and tag independently."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2025)
    ch_mod.handle_setup(2025)

    ch_mod.handle_command("/setbranding دنیا ۲۴ انگلیسی", 2025)
    ws = db.workspaces[0]
    branding = db.get_workspace_branding(ws["id"])
    assert branding["media_name"] == "دنیا ۲۴ انگلیسی"
    assert db.get_workspace_setup_state(ws["id"])["current_step_key"] == "setup_channel"
    assert "/sethashtag" in sent[-1][1]

    ch_mod.handle_command("/sethashtag #دنیا۲۴_انگلیسی", 2025)
    branding = db.get_workspace_branding(ws["id"])
    assert branding["hashtag"] == "#دنیا۲۴_انگلیسی"
    assert "/setchanneltag" in sent[-1][1]

    ch_mod.handle_command("/setchanneltag @Donya24News_En", 2025)
    branding = db.get_workspace_branding(ws["id"])
    assert branding["channel_tag"] == "@Donya24News_En"
    assert db.get_workspace_setup_state(ws["id"])["current_step_key"] == (
        "setup_branding_sample"
    )
    assert "نمونه پیام" in sent[-1][1]


def test_25b_stepwise_hashtag_rejects_spaces(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2026)
    ch_mod.handle_command("/setbranding رسانه آزمایشی", 2026)
    ch_mod.handle_command("/sethashtag #هشتگ نادرست", 2026)

    assert "فاصله نداشته باشد" in sent[-1][1]
    assert not (db.get_workspace_branding(db.workspaces[0]["id"]) or {}).get("hashtag")


def test_26_finishsetup_requires_branding_and_destination(monkeypatch):
    """/finishsetup fails gracefully when requirements are missing."""
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2003)

    # No branding, no channel — finish must fail
    sent.clear()
    ch_mod.handle_command("/finishsetup", 2003)
    last_msg = sent[-1][1]
    assert "❌" in last_msg

    # Add channel but still no branding — still fails
    ch_mod.handle_command("/addchannel @SomeChannel", 2003)
    sent.clear()
    ch_mod.handle_command("/finishsetup", 2003)
    last_msg = sent[-1][1]
    assert "❌" in last_msg

    # Add branding, preview and confirm the required sample — now finish succeeds
    ch_mod.handle_command("/setbranding رسانه‌ام #test @test", 2003)
    ch_mod.handle_branding_sample_message(
        {"text": "🟢 تیتر نمونه\n\n🔵 متن نمونه"},
        2003,
    )
    ch_mod.handle_command("/confirmbranding", 2003)
    sent.clear()
    ch_mod.handle_command("/finishsetup", 2003)
    last_msg = sent[-1][1]
    assert "🎉" in last_msg or "✅" in last_msg
    assert "آیا اکنون می‌خواهید رسانه دیگری" in last_msg
    keyboard = ch_mod._test_sent_keyboards[-1][1]
    callback_values = {
        button["callback_data"]
        for row in keyboard
        for button in row
    }
    assert callback_values == {
        "setup:add_media",
        "setup:done",
        "setup:later",
    }
    preference = db.get_active_workspace_preference(db.users[0]["id"])
    assert preference["context_type"] == "workspace"
    assert preference["active_workspace_id"] == db.workspaces[0]["id"]


def test_26a_branding_sample_requires_preview_confirmation(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2010)
    ch_mod.handle_command("/setbranding آزمایش #آزمایش @TestChannel", 2010)

    ws = db.workspaces[0]
    assert db.get_workspace_setup_state(ws["id"])["current_step_key"] == (
        "setup_branding_sample"
    )

    sent.clear()
    handled = ch_mod.handle_branding_sample_message(
        {"text": "🟢 تیتر نمونه\n\n🔵 متن نمونه\n\n@source | #old"},
        2010,
    )
    assert handled is True
    state = db.get_workspace_setup_state(ws["id"])
    assert state["branding_sample_status"] == "pending_confirmation"
    assert state["branding_sample_icons"] == ["🟢", "🔵"]
    assert db.get_workspace_branding(ws["id"])["icons_enabled"] is False
    assert any("#old" in message and "@source" in message for _, message in sent)
    assert any("/confirmbranding" in message for _, message in sent)

    ch_mod.handle_command("/confirmbranding", 2010)
    state = db.get_workspace_setup_state(ws["id"])
    branding = db.get_workspace_branding(ws["id"])
    assert state["branding_sample_status"] == "confirmed"
    assert state["current_step_key"] == "setup_member"
    assert branding["publication_icons"] == ["🟢", "🔵"]
    assert branding["icons_enabled"] is True
    assert branding["hashtag"] == "#old"
    assert branding["channel_tag"] == "@source"


def test_26b_resample_discards_unconfirmed_preview(monkeypatch):
    _, ch_mod, db, _ = _load_modules(monkeypatch)
    ch_mod.handle_start(2011)
    ch_mod.handle_command("/setbranding آزمایش #آزمایش @TestChannel", 2011)
    ch_mod.handle_branding_sample_message({"text": "🔴 نمونه اول"}, 2011)
    ch_mod.handle_command("/resamplebranding", 2011)

    state = db.get_workspace_setup_state(db.workspaces[0]["id"])
    assert state["current_step_key"] == "setup_branding_sample"
    assert state["branding_sample_status"] == "not_started"
    assert state["branding_sample_text"] == ""
    assert state["branding_sample_icons"] == []


def test_26c_sample_saves_hidden_bale_suggestion_without_blocking(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    ch_mod.handle_start(2013)
    ch_mod.handle_command("/setbranding فردای نو #فردای_نو @farda_nou", 2013)

    title = "جانشین اینفانتینو از آسیا می‌آید؟"
    cta = "📌 فردای‌نو را در بله دنبال کنید"
    sample = f"🟩 {title}\n\n🔷 بند خبر.\n\n{cta}\n\n#قدیمی\n@old"
    cta_start = sample.index(cta)
    utf16 = lambda value: len(value.encode("utf-16-le")) // 2
    handled = ch_mod.handle_branding_sample_message(
        {
            "text": sample,
            "entities": [{
                "type": "text_link",
                "offset": utf16(sample[:cta_start]),
                "length": utf16(cta),
                "url": "https://ble.ir/farda_nou",
            }],
        },
        2013,
    )

    assert handled is True
    state = db.get_workspace_setup_state(db.workspaces[0]["id"])
    assert state["branding_sample_icons"] == ["🟩", "🔷", "📌"]
    assert state["branding_sample_profile"]["cta_icons"] == ["📌"]
    assert state["branding_sample_bale_channel"] == "@farda_nou"
    assert state["branding_sample_bale_status"] == "pending"
    assert any("/confirmbalesuggestion" in message for _, message in sent)
    preview_messages = [message for _, message in sent if "بند خبر" in message]
    assert preview_messages
    assert "📌" in preview_messages[0]
    assert "در بله دنبال کنید" in preview_messages[0]
    assert "@old" not in preview_messages[0]


def test_26d_dual_user_status_follows_selected_media_context(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    telegram_id = 2012
    db.tenants[telegram_id] = {
        "user_id": telegram_id,
        "telegram_channel": "@Donya24News",
        "bale_channel": "",
        "bale_token": "",
    }
    user = db.get_or_create_user_by_telegram_id(telegram_id)
    workspace = db.create_workspace("رسانه جدید", user["id"])
    db.create_publication_destination(
        workspace["id"], "telegram", "channel", "جدید", "@NewChannel", "active"
    )

    db.set_active_legacy_context(user["id"])
    ch_mod.handle_status(telegram_id)
    assert "@Donya24News" in sent[-1][1]
    assert "حساب قدیمی" in sent[-1][1]

    db.set_active_workspace(user["id"], workspace["id"])
    ch_mod.handle_status(telegram_id)
    assert "رسانه جدید" in sent[-1][1]
    assert "@NewChannel" in sent[-1][1]


def test_26e_legacy_user_can_open_workspaces_and_create_new_media(monkeypatch):
    _, ch_mod, db, sent = _load_modules(monkeypatch)
    telegram_id = 2014
    original_tenant = {
        "user_id": telegram_id,
        "telegram_channel": "@Donya24News",
        "bale_channel": "@donya24_news",
        "bale_token": "legacy-token",
    }
    db.tenants[telegram_id] = deepcopy(original_tenant)

    assert db.get_user_by_telegram_id(telegram_id) is None
    ch_mod.handle_workspaces(telegram_id)

    user = db.get_user_by_telegram_id(telegram_id)
    assert user is not None
    keyboard = ch_mod._test_sent_keyboards[-1][1]
    callbacks = {
        button["callback_data"]
        for row in keyboard
        for button in row
    }
    assert "ws:legacy" in callbacks
    assert "setup:create_workspace" in callbacks
    assert "ابتدا /start" not in sent[-1][1]

    ch_mod.handle_create_workspace(telegram_id)
    assert len(db.workspaces) == 1
    workspace = db.workspaces[0]
    assert db.get_workspace_setup_state(workspace["id"])["step"] == "in_progress"
    preference = db.get_active_workspace_preference(user["id"])
    assert preference["active_workspace_id"] == workspace["id"]
    assert preference["context_type"] == "workspace"

    # Duplicate callback delivery resumes the unfinished workspace instead of
    # creating another one, and legacy settings remain byte-for-byte intact.
    ch_mod.handle_create_workspace(telegram_id)
    assert len(db.workspaces) == 1
    assert db.tenants[telegram_id] == original_tenant


# =========================================================
# TESTS: DESTINATION BRANDING  (27-35)
# =========================================================

def _setup_workspace_with_two_destinations(db, ws_mod):
    """Helper: create a workspace with two registered destinations."""
    user = db.get_or_create_user_by_telegram_id(9101)
    ws = db.create_workspace("دو-کانال", user["id"])
    db.add_workspace_member(ws["id"], user["id"], "owner", "active")
    dest_a, _ = ws_mod.register_channel_destination(ws["id"], "@beneshaneh", "بی‌نشانه")
    dest_b, _ = ws_mod.register_channel_destination(ws["id"], "@farda_no", "فردای نو")
    return ws, user, dest_a, dest_b


def test_27_two_destinations_can_have_different_branding(monkeypatch):
    """Two destinations in one workspace may have independent branding rows."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    ws_mod.save_destination_branding(dest_a["id"], hashtag="#بی_نشانه", channel_tag="@beneshaneh")
    ws_mod.save_destination_branding(dest_b["id"], hashtag="#فردای_نو", channel_tag="@farda_no")

    brand_a = ws_mod.get_branding_for_destination(dest_a["id"])
    brand_b = ws_mod.get_branding_for_destination(dest_b["id"])

    assert brand_a is not None
    assert brand_b is not None
    assert brand_a["destination_id"] != brand_b["destination_id"]


def test_28_different_hashtag_per_destination(monkeypatch):
    """Each destination stores its own hashtag."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    ws_mod.save_destination_branding(dest_a["id"], hashtag="#بی_نشانه")
    ws_mod.save_destination_branding(dest_b["id"], hashtag="#فردای_نو")

    assert ws_mod.get_branding_for_destination(dest_a["id"])["hashtag"] == "#بی_نشانه"
    assert ws_mod.get_branding_for_destination(dest_b["id"])["hashtag"] == "#فردای_نو"


def test_29_different_channel_tag_per_destination(monkeypatch):
    """Each destination stores its own channel_tag."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    ws_mod.save_destination_branding(dest_a["id"], channel_tag="@beneshaneh")
    ws_mod.save_destination_branding(dest_b["id"], channel_tag="@farda_no")

    assert ws_mod.get_branding_for_destination(dest_a["id"])["channel_tag"] == "@beneshaneh"
    assert ws_mod.get_branding_for_destination(dest_b["id"])["channel_tag"] == "@farda_no"


def test_30_different_custom_footer_per_destination(monkeypatch):
    """Each destination can store a completely different custom footer text."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    footer_a = "📌 بی‌نشانه | @beneshaneh"
    footer_b = "🌅 فردای نو\n@farda_no\n#فردای_نو"

    ws_mod.save_destination_branding(dest_a["id"], custom_footer=footer_a, footer_enabled=True)
    ws_mod.save_destination_branding(dest_b["id"], custom_footer=footer_b, footer_enabled=True)

    assert ws_mod.get_branding_for_destination(dest_a["id"])["custom_footer"] == footer_a
    assert ws_mod.get_branding_for_destination(dest_b["id"])["custom_footer"] == footer_b


def test_31_custom_footer_may_be_empty_or_disabled(monkeypatch):
    """custom_footer is optional; footer_enabled=False is valid with no footer text."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    ws_mod.save_destination_branding(dest_a["id"], custom_footer=None, footer_enabled=False)
    ws_mod.save_destination_branding(dest_b["id"], custom_footer="", footer_enabled=False)

    brand_a = ws_mod.get_branding_for_destination(dest_a["id"])
    brand_b = ws_mod.get_branding_for_destination(dest_b["id"])

    assert brand_a["custom_footer"] is None
    assert brand_b["footer_enabled"] is False
    assert brand_b["custom_footer"] == ""


def test_32_updating_one_destination_branding_does_not_affect_another(monkeypatch):
    """Updating branding for dest_a must not change dest_b's branding."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    ws, _user, dest_a, dest_b = _setup_workspace_with_two_destinations(db, ws_mod)

    ws_mod.save_destination_branding(dest_a["id"], hashtag="#اول", channel_tag="@first")
    ws_mod.save_destination_branding(dest_b["id"], hashtag="#دوم", channel_tag="@second")

    # Update only dest_a
    ws_mod.save_destination_branding(dest_a["id"], hashtag="#اول_ویرایش", channel_tag="@first_v2")

    brand_b_after = ws_mod.get_branding_for_destination(dest_b["id"])
    assert brand_b_after["hashtag"] == "#دوم"
    assert brand_b_after["channel_tag"] == "@second"


def test_33_workspace_branding_remains_available_as_default(monkeypatch):
    """workspace_branding is still readable as a fallback when no destination branding exists."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(9102)
    ws = db.create_workspace("پیش‌فرض", user["id"])

    ws_mod.save_workspace_branding(ws["id"], "پیش‌فرض رسانه", "#ws_tag", "@ws_channel")

    dest, _ = ws_mod.register_channel_destination(ws["id"], "@no_brand_ch", "بدون برند")
    # No destination branding saved for this dest
    dest_brand = ws_mod.get_branding_for_destination(dest["id"])
    ws_brand = db.get_workspace_branding(ws["id"])

    assert dest_brand is None
    assert ws_brand is not None
    assert ws_brand["hashtag"] == "#ws_tag"


def test_34_legacy_tenant_branding_unchanged(monkeypatch):
    """Destination branding operations do not touch legacy tenant rows."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)

    # Set up a legacy tenant
    db.save_tenant(8101, "tok", "@legacy_ch", hashtag="#legacy", channel_tag="@leg")

    user = db.get_or_create_user_by_telegram_id(9103)
    ws = db.create_workspace("تست", user["id"])
    dest, _ = ws_mod.register_channel_destination(ws["id"], "@new_ch", "جدید")
    ws_mod.save_destination_branding(dest["id"], hashtag="#new_hash", channel_tag="@new_tag",
                                     custom_footer="Footer جدید", footer_enabled=True)

    # Legacy tenant must be unchanged
    tenant = db.get_tenant(8101)
    assert tenant["hashtag"] == "#legacy"
    assert tenant["channel_tag"] == "@leg"
    assert tenant["bot_token"] == "tok"


def test_35_destination_branding_none_before_any_save(monkeypatch):
    """A freshly registered destination has no branding row until one is saved."""
    ws_mod, _, db, _ = _load_modules(monkeypatch)
    user = db.get_or_create_user_by_telegram_id(9104)
    ws = db.create_workspace("خالی", user["id"])
    dest, _ = ws_mod.register_channel_destination(ws["id"], "@empty_ch", "خالی")

    assert ws_mod.get_branding_for_destination(dest["id"]) is None

def test_26f_onboarding_activates_owned_workspace_instead_of_manager_workspace(monkeypatch):
    """
    Regression:
    A user may already be manager of another workspace.

    When /start creates the user's own onboarding workspace, that owned
    workspace must become the active setup context. Branding must never
    overwrite the workspace where the user is only a manager.
    """
    _, ch_mod, db, _ = _load_modules(monkeypatch)
    telegram_id = 2027

    existing_owner = db.get_or_create_user_by_telegram_id(999001)
    existing_workspace = db.create_workspace("بی‌نشانه", existing_owner["id"])
    db.upsert_workspace_branding(
        existing_workspace["id"],
        "بی‌نشانه",
        "#بی_نشانه",
        "@beneshaneh",
    )

    user = db.get_or_create_user_by_telegram_id(telegram_id)
    db.add_workspace_member(
        existing_workspace["id"],
        user["id"],
        role="manager",
        status="active",
    )
    db.set_active_workspace(user["id"], existing_workspace["id"])

    ch_mod.handle_start(telegram_id)

    owned = db.list_owned_workspaces(user["id"])
    assert len(owned) == 1
    owned_workspace = owned[0]
    assert owned_workspace["id"] != existing_workspace["id"]

    preference = db.get_active_workspace_preference(user["id"])
    assert preference is not None
    assert preference["context_type"] == "workspace"
    assert preference["active_workspace_id"] == owned_workspace["id"]

    ch_mod.handle_command(
        "/setbranding فردای نو #فردای_نو @farda_nou",
        telegram_id,
    )

    manager_branding = db.get_workspace_branding(existing_workspace["id"])
    owned_branding = db.get_workspace_branding(owned_workspace["id"])

    assert manager_branding["media_name"] == "بی‌نشانه"
    assert manager_branding["hashtag"] == "#بی_نشانه"
    assert manager_branding["channel_tag"] == "@beneshaneh"

    assert owned_branding is not None
    assert owned_branding["media_name"] == "فردای نو"
    assert owned_branding["hashtag"] == "#فردای_نو"
    assert owned_branding["channel_tag"] == "@farda_nou"

def test_26g_start_does_not_override_completed_users_intentional_workspace_selection(monkeypatch):
    """
    Regression guard:
    If a user's own workspace onboarding is already completed and they
    intentionally selected another workspace where they are a manager,
    /start must not force-switch them back to their owned workspace.
    """
    _, ch_mod, db, _ = _load_modules(monkeypatch)

    telegram_id = 2028

    # User's own workspace
    user = db.get_or_create_user_by_telegram_id(telegram_id)
    owned_workspace = db.create_workspace(
        "رسانه شخصی",
        user["id"],
    )

    db.add_workspace_member(
        owned_workspace["id"],
        user["id"],
        role="owner",
        status="active",
    )

    db.upsert_workspace_branding(
        owned_workspace["id"],
        "رسانه شخصی",
        "#رسانه_شخصی",
        "@personal_media",
    )

    # Complete onboarding for the owned workspace.
    db.upsert_workspace_setup_state(
    owned_workspace["id"],
    "completed",
)

    # Another workspace where this same user is only manager.
    other_owner = db.get_or_create_user_by_telegram_id(999002)
    manager_workspace = db.create_workspace(
        "رسانه مدیریتی",
        other_owner["id"],
    )

    db.add_workspace_member(
        manager_workspace["id"],
        user["id"],
        role="manager",
        status="active",
    )

    # User intentionally selected the manager workspace.
    db.set_active_workspace(
        user["id"],
        manager_workspace["id"],
    )

    ch_mod.handle_start(telegram_id)

    preference = db.get_active_workspace_preference(user["id"])

    assert preference is not None
    assert preference["context_type"] == "workspace"
    assert preference["active_workspace_id"] == manager_workspace["id"]

def test_unchecked_workspace_is_not_restored_from_active_preference(monkeypatch):
    """
    Regression:
    An unchecked workspace must never become a publication target merely
    because it is the active workspace.

    Active workspace controls management context.
    Checkmarks control publication targets.
    """
    _load_modules(monkeypatch)

    from core.workspace_publisher import resolve_workspaces_for_user

    telegram_id = 404040
    user = {"id": 10, "telegram_user_id": telegram_id}

    workspace_a = {
        "id": 101,
        "name": "رسانه الف",
        "membership_role": "owner",
    }
    workspace_b = {
        "id": 202,
        "name": "رسانه ب",
        "membership_role": "owner",
    }

    selected, error = resolve_workspaces_for_user(
        telegram_id,
        get_user_fn=lambda _telegram_id: user,
        list_workspaces_fn=lambda _user_id: [
            workspace_a,
            workspace_b,
        ],
        get_active_preference_fn=lambda _user_id: {
            "context_type": "workspace",
            "active_workspace_id": workspace_b["id"],
        },
        # User has explicitly left BOTH workspaces unchecked.
        list_selected_ids_fn=lambda _user_id: [],
    )

    assert selected == []
    assert error is not None
