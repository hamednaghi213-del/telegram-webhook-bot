"""Phase 4B Telegram channel verification tests."""

from unittest.mock import Mock, patch

from core import telegram_verifier


def _response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def setup_function():
    telegram_verifier.reset_bot_id_cache()


def test_verify_channel_admin_accepts_admin_with_post_permission():
    get_me = _response({"ok": True, "result": {"id": 101}})
    get_member = _response({
        "ok": True,
        "result": {
            "status": "administrator",
            "can_post_messages": True,
        },
    })

    with patch.object(
        telegram_verifier.requests, "get", side_effect=[get_me, get_member]
    ) as request_get:
        verified, note = telegram_verifier.verify_channel_admin(
            "https://api.telegram.org/botTOKEN", "@channel"
        )

    assert verified is True
    assert note == "تأیید شد"
    assert request_get.call_args_list[1].kwargs["params"] == {
        "chat_id": "@channel",
        "user_id": 101,
    }


def test_verify_channel_admin_rejects_admin_without_post_permission():
    responses = [
        _response({"ok": True, "result": {"id": 101}}),
        _response({
            "ok": True,
            "result": {
                "status": "administrator",
                "can_post_messages": False,
            },
        }),
    ]

    with patch.object(telegram_verifier.requests, "get", side_effect=responses):
        verified, note = telegram_verifier.verify_channel_admin(
            "https://api.telegram.org/botTOKEN", "@channel"
        )

    assert verified is False
    assert "مجوز ارسال پیام" in note


def test_bot_id_cache_is_scoped_to_api_url():
    with patch.object(
        telegram_verifier.requests,
        "get",
        side_effect=[
            _response({"ok": True, "result": {"id": 101}}),
            _response({"ok": True, "result": {"id": 202}}),
        ],
    ) as request_get:
        assert telegram_verifier.get_bot_id("https://example.test/botA") == 101
        assert telegram_verifier.get_bot_id("https://example.test/botA") == 101
        assert telegram_verifier.get_bot_id("https://example.test/botB") == 202

    assert request_get.call_count == 2


def test_verify_channel_admin_maps_chat_not_found_error():
    responses = [
        _response({"ok": True, "result": {"id": 101}}),
        _response(
            {"ok": False, "description": "Bad Request: chat not found"},
            status_code=400,
        ),
    ]

    with patch.object(telegram_verifier.requests, "get", side_effect=responses):
        verified, note = telegram_verifier.verify_channel_admin(
            "https://api.telegram.org/botTOKEN", "@missing"
        )

    assert verified is False
    assert "کانال یافت نشد" in note
