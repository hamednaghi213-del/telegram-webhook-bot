from core.telegram_rich_message import (
    is_rich_message,
    parse_rich_message,
    parse_rich_message_from_message,
)


def test_detects_telegram_rich_message():
    message = {
        "message_id": 100,
        "rich_message": {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": "متن خبر",
                }
            ]
        },
    }

    assert is_rich_message(message) is True
    assert is_rich_message({"message_id": 101}) is False


def test_parses_basic_rich_text_message():
    rich_message = {
        "is_rtl": True,
        "blocks": [
            {
                "type": "heading",
                "text": "تیتر خبر",
                "size": 2,
            },
            {
                "type": "paragraph",
                "text": "متن اصلی خبر",
            },
        ],
    }

    result = parse_rich_message(rich_message)

    assert result.is_rtl is True
    assert result.main_text == (
        "تیتر خبر\n\n"
        "متن اصلی خبر"
    )

    assert result.files == []
    assert result.block_count == 2
    assert result.unsupported_blocks == []


def test_parses_slideshow_with_photo_and_video():
    message = {
        "message_id": 200,
        "rich_message": {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": "ورق بزنید",
                },
                {
                    "type": "slideshow",
                    "caption": {
                        "text": "شرح خبر",
                    },
                    "blocks": [
                        {
                            "type": "photo",
                            "photo": [
                                {
                                    "file_id": "PHOTO_SMALL",
                                    "width": 100,
                                    "height": 100,
                                },
                                {
                                    "file_id": "PHOTO_LARGE",
                                    "width": 1280,
                                    "height": 720,
                                },
                            ],
                        },
                        {
                            "type": "video",
                            "video": {
                                "file_id": "VIDEO_1",
                                "width": 1280,
                                "height": 720,
                                "duration": 10,
                            },
                        },
                    ],
                },
            ]
        },
    }

    result = (
        parse_rich_message_from_message(
            message
        )
    )

    assert result.has_slideshow is True
    assert result.has_collage is False

    assert result.main_text == (
        "ورق بزنید\n\n"
        "شرح خبر"
    )

    assert result.files == [
        {
            "type": "photo",
            "file_id": "PHOTO_LARGE",
        },
        {
            "type": "video",
            "file_id": "VIDEO_1",
        },
    ]

    assert result.block_count == 4


def test_parses_collage():
    rich_message = {
        "blocks": [
            {
                "type": "collage",
                "blocks": [
                    {
                        "type": "photo",
                        "photo": [
                            {
                                "file_id": "PHOTO_1",
                            }
                        ],
                    },
                    {
                        "type": "photo",
                        "photo": [
                            {
                                "file_id": "PHOTO_2",
                            }
                        ],
                    },
                ],
            }
        ]
    }

    result = parse_rich_message(
        rich_message
    )

    assert result.has_collage is True
    assert result.has_slideshow is False

    assert [
        item["file_id"]
        for item in result.files
    ] == [
        "PHOTO_1",
        "PHOTO_2",
    ]


def test_parses_blockquotes():
    rich_message = {
        "blocks": [
            {
                "type": "blockquote",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "متن نقل قول",
                    }
                ],
            },
            {
                "type": "expandable_blockquote",
                "text": "ادامه تحلیل",
            },
            {
                "type": "pullquote",
                "text": "نقل قول برجسته",
            },
        ]
    }

    result = parse_rich_message(
        rich_message
    )

    assert result.blockquote_blocks == [
        {
            "type": "blockquote",
            "text": "متن نقل قول",
        },
        {
            "type": "blockquote",
            "text": "نقل قول برجسته",
            "source_type": "pullquote",
        },
    ]

    assert result.expandable_blocks == [
        {
            "type": "expandable_blockquote",
            "text": "ادامه تحلیل",
        }
    ]


def test_unknown_future_block_does_not_break_message():
    rich_message = {
        "blocks": [
            {
                "type": "paragraph",
                "text": "قبل",
            },
            {
                "type": "future_telegram_block",
                "text": "متن آینده",
            },
            {
                "type": "paragraph",
                "text": "بعد",
            },
        ]
    }

    result = parse_rich_message(
        rich_message
    )

    assert result.main_text == (
        "قبل\n\n"
        "متن آینده\n\n"
        "بعد"
    )

    assert result.unsupported_blocks == [
        "future_telegram_block"
    ]


def test_deduplicates_same_media_file():
    rich_message = {
        "blocks": [
            {
                "type": "slideshow",
                "blocks": [
                    {
                        "type": "photo",
                        "photo": [
                            {
                                "file_id": "SAME_PHOTO",
                            }
                        ],
                    },
                    {
                        "type": "photo",
                        "photo": [
                            {
                                "file_id": "SAME_PHOTO",
                            }
                        ],
                    },
                ],
            }
        ]
    }

    result = parse_rich_message(
        rich_message
    )

    assert result.files == [
        {
            "type": "photo",
            "file_id": "SAME_PHOTO",
        }
    ]


def test_preserves_rich_text_entity_offsets():
    rich_message = {
        "blocks": [
            {
                "type": "paragraph",
                "text": [
                    "خبر ",
                    {
                        "type": "bold",
                        "text": "مهم",
                    },
                ],
            }
        ]
    }

    result = parse_rich_message(
        rich_message
    )

    assert result.main_text == "خبر مهم"

    assert result.other_entities == [
        {
            "type": "bold",
            "offset": 4,
            "length": 3,
        }
    ]
