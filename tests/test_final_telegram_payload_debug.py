import json

import core.media_handler as media_handler


HASHTAG = "#دنیا_۲۴_نیوز"
CHANNEL_TAG = "@Donya24News"


def utf16_length(text):
    return len(
        text.encode("utf-16-le")
    ) // 2


def utf16_slice(text, offset, length):
    encoded = text.encode("utf-16-le")

    start = offset * 2
    end = (offset + length) * 2

    return encoded[start:end].decode(
        "utf-16-le"
    )


def test_final_telegram_payload_debug(
    monkeypatch
):
    """
    هدف این تست:

    بررسی Payload واقعی در آخرین نقطه
    قبل از ارسال به Telegram.

    می‌خواهیم بدانیم:
    1. هشتگ واقعاً چند بار در Caption وجود دارد.
    2. caption_entities دقیقاً چیست.
    3. هر Entity روی چه متنی قرار گرفته است.
    4. آیا Entity روی Branding افتاده است یا نه.
    """

    captured = {}

    # ---------------------------------------------
    # Telegram API fake
    # ---------------------------------------------

    class FakeResponse:

        status_code = 200
        text = '{"ok": true}'

        def json(self):
            return {
                "ok": True,
                "result": {
                    "message_id": 999
                }
            }

    def fake_telegram_post(
        endpoint,
        payload
    ):
        captured["endpoint"] = endpoint
        captured["payload"] = payload

        return FakeResponse()

    monkeypatch.setattr(
        media_handler,
        "telegram_post",
        fake_telegram_post
    )

    monkeypatch.setattr(
        media_handler,
        "API_URL",
        "https://example.invalid"
    )

    monkeypatch.setattr(
        media_handler,
        "CHANNEL_ID",
        "@test_channel"
    )

    # ---------------------------------------------
    # نمونه مشابه خبر واقعی
    # ---------------------------------------------

    main_text = (
        "❇️ گواهی امنیتی برخی سایت‌های بانک "
        "مرکزی لغو شد / بانک مرکزی: این موضوع "
        "به معنای حمله به زیرساخت‌های بانک نیست"
        "\n\n"
        "🔹 اطلاعیه بانک مرکزی درباره گواهی "
        "امنیتی پایگاه‌های اطلاع‌رسانی:"
    )

    expandable_text = (
        "در پی اقدامات خصمانه دشمن صهیونی "
        "آمریکایی در حوزه‌های نظامی و سایبری، "
        "گواهی امنیتی برخی پایگاه‌های "
        "اطلاع‌رسانی مرتبط لغو شده است."
    )

    # ---------------------------------------------
    # ساخت Caption با همان ماژول واقعی پروژه
    # ---------------------------------------------

    from core.telegram_caption_entities import (
        build_telegram_caption_entities
    )

    result = build_telegram_caption_entities(
        main_text=main_text,
        blockquote_blocks=[],
        expandable_blocks=[
            {
                "type": "expandable_blockquote",
                "text": expandable_text,
                "offset": 100
            }
        ],
        branding=(
            f"{HASHTAG}\n"
            f"{CHANNEL_TAG}"
        )
    )

    caption = result["caption"]
    caption_entities = result[
        "caption_entities"
    ]

    # ---------------------------------------------
    # ارسال از مسیر واقعی Media Handler
    # ---------------------------------------------

    success = (
        media_handler
        .send_single_media_to_channel(
            file_id="TEST_FILE_ID",
            media_type="photo",
            caption=caption,
            caption_entities=caption_entities
        )
    )

    assert success is True

    # ---------------------------------------------
    # Payload نهایی
    # ---------------------------------------------

    payload = captured["payload"]

    final_caption = payload.get(
        "caption",
        ""
    )

    final_entities = payload.get(
        "caption_entities",
        []
    )

    # ---------------------------------------------
    # اطلاعات تشخیصی
    # ---------------------------------------------

    print("\n")
    print("=" * 70)
    print("FINAL TELEGRAM PAYLOAD DEBUG")
    print("=" * 70)

    print(
        "\nENDPOINT:"
    )
    print(
        captured["endpoint"]
    )

    print(
        "\nFINAL CAPTION:"
    )
    print(
        final_caption
    )

    print(
        "\nFINAL CAPTION REPR:"
    )
    print(
        repr(final_caption)
    )

    print(
        "\nFINAL CAPTION PYTHON LENGTH:"
    )
    print(
        len(final_caption)
    )

    print(
        "\nFINAL CAPTION UTF16 LENGTH:"
    )
    print(
        utf16_length(
            final_caption
        )
    )

    print(
        "\nHASHTAG COUNT:"
    )
    print(
        final_caption.count(
            HASHTAG
        )
    )

    print(
        "\nCHANNEL TAG COUNT:"
    )
    print(
        final_caption.count(
            CHANNEL_TAG
        )
    )

    hashtag_index = (
        final_caption.find(
            HASHTAG
        )
    )

    print(
        "\nHASHTAG PYTHON INDEX:"
    )
    print(
        hashtag_index
    )

    if hashtag_index >= 0:

        print(
            "\nHASHTAG UTF16 OFFSET:"
        )

        print(
            utf16_length(
                final_caption[
                    :hashtag_index
                ]
            )
        )

    print(
        "\nFINAL CAPTION ENTITIES:"
    )

    print(
        json.dumps(
            final_entities,
            ensure_ascii=False,
            indent=2
        )
    )

    print(
        "\nENTITY COVERAGE:"
    )

    for index, entity in enumerate(
        final_entities,
        start=1
    ):

        entity_type = entity.get(
            "type"
        )

        offset = entity.get(
            "offset",
            0
        )

        length = entity.get(
            "length",
            0
        )

        covered_text = utf16_slice(
            final_caption,
            offset,
            length
        )

        print(
            f"\nENTITY #{index}"
        )

        print(
            "TYPE:",
            entity_type
        )

        print(
            "OFFSET:",
            offset
        )

        print(
            "LENGTH:",
            length
        )

        print(
            "COVERED REPR:",
            repr(
                covered_text
            )
        )

        print(
            "COVERS HASHTAG:",
            HASHTAG in covered_text
        )

        print(
            "COVERS CHANNEL TAG:",
            CHANNEL_TAG in covered_text
        )

    print(
        "\nBOUNDARY BEFORE HASHTAG:"
    )

    if hashtag_index >= 0:

        boundary_start = max(
            0,
            hashtag_index - 20
        )

        boundary = final_caption[
            boundary_start:
            hashtag_index
            + len(HASHTAG)
            + 5
        ]

        print(
            repr(boundary)
        )

        print(
            "\nBOUNDARY CODEPOINTS:"
        )

        for char in boundary:

            print(
                repr(char),
                "U+"
                f"{ord(char):04X}"
            )

    print("\n")
    print("=" * 70)
    print("END DEBUG")
    print("=" * 70)
    print("\n")

    # ---------------------------------------------
    # ASSERTIONS
    # ---------------------------------------------

    assert (
        final_caption.count(
            HASHTAG
        )
        == 1
    )

    assert (
        final_caption.count(
            CHANNEL_TAG
        )
        == 1
    )

    # هیچ Blockquote Entity نباید Branding را بپوشاند.

    for entity in final_entities:

        covered_text = utf16_slice(
            final_caption,
            entity.get(
                "offset",
                0
            ),
            entity.get(
                "length",
                0
            )
        )

        assert (
            HASHTAG
            not in covered_text
        )

        assert (
            CHANNEL_TAG
            not in covered_text
        )
