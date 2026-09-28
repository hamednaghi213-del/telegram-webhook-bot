import sys
from types import ModuleType

import pytest

from core import admin_control
from core import admin_panel


def _fake_database(**values):
    module = ModuleType(
        "core.database"
    )

    for key, value in values.items():
        setattr(
            module,
            key,
            value,
        )

    return module


def test_destination_admin_defaults_active_when_disabled(
    monkeypatch,
):
    monkeypatch.setenv(
        "ENABLE_ADMIN_CONTROL",
        "false",
    )

    assert (
        admin_control
        .destination_admin_state(10)
        == "active"
    )

    assert (
        admin_control
        .destination_admin_allowed(10)
        is True
    )


def test_destination_admin_paused_is_not_allowed(
    monkeypatch,
):
    monkeypatch.setenv(
        "ENABLE_ADMIN_CONTROL",
        "true",
    )

    fake = _fake_database(
        get_admin_destination_control=(
            lambda destination_id: {
                "destination_id": (
                    destination_id
                ),
                "admin_state": "paused",
            }
        )
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake,
    )

    assert (
        admin_control
        .destination_admin_state(10)
        == "paused"
    )

    assert (
        admin_control
        .destination_admin_allowed(10)
        is False
    )


def test_blocked_external_destination_cannot_be_readded(
    monkeypatch,
):
    monkeypatch.setenv(
        "ENABLE_ADMIN_CONTROL",
        "true",
    )

    fake = _fake_database(
        list_admin_destination_inventory=(
            lambda: [
                {
                    "id": 10,
                    "platform": "telegram",
                    "external_id": (
                        "@BlockedChannel"
                    ),
                    "admin_state": (
                        "blocked"
                    ),
                }
            ]
        )
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake,
    )

    assert (
        admin_control
        .external_destination_is_blocked(
            "telegram",
            "@blockedchannel",
        )
        is True
    )


def test_admin_root_has_no_placeholder(
    monkeypatch,
):
    monkeypatch.setenv(
        "ADMIN_TELEGRAM_USER_ID",
        "999",
    )

    sent = []

    assert (
        admin_panel.handle_admin_root(
            999,
            lambda _chat, text: (
                sent.append(text)
                or True
            ),
            "telegram",
        )
        is True
    )

    message = sent[-1]

    assert (
        "/adminregistrations"
        in message
    )

    assert (
        "/adminrequests"
        in message
    )

    assert (
        "/admindestinations"
        in message
    )

    assert (
        "/adminaudit"
        in message
    )

    assert (
        "در حال تکمیل"
        not in message
    )


def test_registration_approve_activates_user_and_audits(
    monkeypatch,
):
    monkeypatch.setenv(
        "ADMIN_TELEGRAM_USER_ID",
        "999",
    )

    reviewed = []
    statuses = []
    audits = []

    fake = _fake_database(
        list_pending_admin_registration_requests=(
            lambda: [
                {
                    "id": 20,
                    "user_id": 5,
                    "status": "pending",
                    "requested_platform": (
                        "telegram"
                    ),
                    "requested_external_user_id": (
                        123
                    ),
                }
            ]
        ),
        review_admin_registration_request=(
            lambda *args, **kwargs: (
                reviewed.append(
                    (
                        args,
                        kwargs,
                    )
                )
                or {
                    "id": 20,
                    "status": (
                        "approved"
                    ),
                }
            )
        ),
        update_user_status=(
            lambda user_id, status: (
                statuses.append(
                    (
                        user_id,
                        status,
                    )
                )
                or {
                    "id": user_id,
                    "status": status,
                }
            )
        ),
        record_admin_audit_log=(
            lambda *args, **kwargs: (
                audits.append(
                    (
                        args,
                        kwargs,
                    )
                )
                or {"id": 1}
            )
        ),
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake,
    )

    sent = []

    assert (
        admin_panel
        .handle_admin_registration_approve(
            "20",
            999,
            lambda _chat, text: (
                sent.append(text)
                or True
            ),
            "telegram",
        )
        is True
    )

    assert reviewed

    assert statuses == [
        (
            5,
            "active",
        )
    ]

    assert audits

    assert (
        "تأیید شد"
        in sent[-1]
    )


def test_registration_reject_inactivates_user(
    monkeypatch,
):
    monkeypatch.setenv(
        "ADMIN_TELEGRAM_USER_ID",
        "999",
    )

    statuses = []

    fake = _fake_database(
        list_pending_admin_registration_requests=(
            lambda: [
                {
                    "id": 21,
                    "user_id": 6,
                    "status": "pending",
                    "requested_platform": (
                        "telegram"
                    ),
                    "requested_external_user_id": (
                        124
                    ),
                }
            ]
        ),
        review_admin_registration_request=(
            lambda *args, **kwargs: {
                "id": 21,
                "status": "rejected",
            }
        ),
        update_user_status=(
            lambda user_id, status: (
                statuses.append(
                    (
                        user_id,
                        status,
                    )
                )
                or {
                    "id": user_id,
                    "status": status,
                }
            )
        ),
        record_admin_audit_log=(
            lambda *args, **kwargs: {
                "id": 1
            }
        ),
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake,
    )

    assert (
        admin_panel
        .handle_admin_registration_reject(
            "21",
            999,
            lambda _chat, _text: True,
            "telegram",
        )
        is True
    )

    assert statuses == [
        (
            6,
            "inactive",
        )
    ]


@pytest.mark.parametrize(
    "handler,state,action",
    [
        (
            admin_panel
            .handle_admin_pause,
            "paused",
            "pause_destination",
        ),
        (
            admin_panel
            .handle_admin_resume,
            "active",
            "resume_destination",
        ),
        (
            admin_panel
            .handle_admin_block,
            "blocked",
            "block_destination",
        ),
        (
            admin_panel
            .handle_admin_unblock,
            "active",
            "unblock_destination",
        ),
    ],
)
def test_destination_admin_actions(
    monkeypatch,
    handler,
    state,
    action,
):
    monkeypatch.setenv(
        "ADMIN_TELEGRAM_USER_ID",
        "999",
    )

    state_changes = []
    audits = []

    fake = _fake_database(
        list_admin_destination_inventory=(
            lambda: [
                {
                    "id": 10,
                    "workspace_id": 6,
                    "platform": (
                        "telegram"
                    ),
                    "external_id": (
                        "@channel"
                    ),
                    "status": "active",
                    "admin_state": (
                        "active"
                    ),
                }
            ]
        ),
        upsert_admin_destination_control=(
            lambda *args, **kwargs: (
                state_changes.append(
                    (
                        args,
                        kwargs,
                    )
                )
                or {
                    "destination_id": (
                        10
                    ),
                    "admin_state": (
                        state
                    ),
                }
            )
        ),
        record_admin_audit_log=(
            lambda *args, **kwargs: (
                audits.append(
                    (
                        args,
                        kwargs,
                    )
                )
                or {
                    "id": 1
                }
            )
        ),
    )

    monkeypatch.setitem(
        sys.modules,
        "core.database",
        fake,
    )

    assert (
        handler(
            "10 test reason",
            999,
            lambda _chat, _text: True,
            "telegram",
        )
        is True
    )

    assert state_changes

    assert (
        state_changes[0][0][0]
        == 10
    )

    assert (
        state_changes[0][0][1]
        == state
    )

    assert audits

    assert (
        audits[0][0][0]
        == action
    )
