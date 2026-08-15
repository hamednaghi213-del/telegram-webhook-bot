import logging
from typing import (
    Dict,
    List,
    Optional,
    Any
)

from core.content_entities import (
    build_blockquote_html
)

logger = logging.getLogger(__name__)


# =========================================================
# PLATFORM LIMITS
# =========================================================

# Telegram
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096

# Bale
BALE_CAPTION_LIMIT = 4096
BALE_MESSAGE_LIMIT = 4096


# =========================================================
# INTERNAL SAFE LIMITS
# =========================================================
#
# Media و HTML همچنان کمی پایین‌تر از سقف رسمی
# برنامه‌ریزی می‌شوند.
#
# اما Telegram Text Plan برای پیام Plain Text
# می‌تواند از سقف کامل 4096 استفاده کند.
# =========================================================

TELEGRAM_CAPTION_SAFE_LIMIT = 1000
TELEGRAM_MESSAGE_SAFE_LIMIT = 4000

BALE_CAPTION_SAFE_LIMIT = 4000
BALE_MESSAGE_SAFE_LIMIT = 4000


# =========================================================
# PUBLICATION PLAN
# =========================================================

class PublicationPlan:

    def __init__(self):

        self.telegram: Dict[str, Any] = {
            "media_caption": "",
            "followup_messages": [],
            "blockquote_messages": [],
            "document_fallback": False
        }

        self.bale: Dict[str, Any] = {
            "media_caption": "",
            "followup_messages": [],
            "blockquote_messages": [],
            "document_fallback": False
        }

        self.text: Dict[str, Any] = {
            "telegram": {
                "messages": [],
                "blockquote_messages": []
            },
            "bale": {
                "messages": [],
                "blockquote_messages": []
            }
        }

        self.metadata: Dict[str, Any] = {
            "other_entities": []
        }

    def to_dict(self) -> Dict[str, Any]:

        return {
            "telegram": self.telegram,
            "bale": self.bale,
            "metadata": self.metadata
        }


# =========================================================
# BASIC HELPERS
# =========================================================

def normalize_text(
    text: Optional[str]
) -> str:

    if not text:
        return ""

    return str(
        text
    ).strip()


def get_text_length(
    text: Optional[str]
) -> int:

    if not text:
        return 0

    return len(
        text
    )


def append_branding(
    text: str,
    branding: str
) -> str:

    text = normalize_text(
        text
    )

    branding = normalize_text(
        branding
    )

    if not branding:
        return text

    if not text:
        return branding

    return (
        f"{text}\n\n"
        f"{branding}"
    )


# =========================================================
# FIND LOGICAL SPLIT POSITION
# =========================================================

def find_split_position(
    text: str,
    limit: int
) -> int:

    if not text:
        return 0

    if limit <= 0:
        return 0

    if len(text) <= limit:
        return len(text)

    search_text = text[
        :limit
    ]

    # =====================================================
    # 1. PARAGRAPH
    # =====================================================

    position = (
        search_text.rfind(
            "\n\n"
        )
    )

    if position > 0:
        return position

    # =====================================================
    # 2. LINE
    # =====================================================

    position = (
        search_text.rfind(
            "\n"
        )
    )

    if position > 0:
        return position

    # =====================================================
    # 3. SENTENCE
    # =====================================================

    sentence_marks = (
        "؟",
        "!",
        ".",
        "?",
        "۔",
        "…"
    )

    best_sentence_position = -1

    for mark in sentence_marks:

        position = (
            search_text.rfind(
                mark
            )
        )

        if (
            position
            > best_sentence_position
        ):

            best_sentence_position = (
                position
            )

    if (
        best_sentence_position
        > 0
    ):

        return (
            best_sentence_position
            + 1
        )

    # =====================================================
    # 4. WORD
    # =====================================================

    position = (
        search_text.rfind(
            " "
        )
    )

    if position > 0:
        return position

    # =====================================================
    # 5. HARD CUT
    # =====================================================

    logger.warning(
        f"⚠️ Hard split required | "
        f"limit={limit} | "
        f"preview={text[:80]!r}"
    )

    return limit


# =========================================================
# SMART TEXT SPLITTER
# =========================================================

def split_text(
    text: str,
    limit: int
) -> List[str]:

    text = normalize_text(
        text
    )

    if not text:
        return []

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero"
        )

    if len(text) <= limit:

        return [
            text
        ]

    parts: List[str] = []

    remaining = text

    safety_counter = 0

    while remaining:

        safety_counter += 1

        if safety_counter > 10000:

            logger.error(
                "❌ split_text safety limit reached"
            )

            break

        if (
            len(remaining)
            <= limit
        ):

            final_part = (
                remaining.strip()
            )

            if final_part:

                parts.append(
                    final_part
                )

            break

        split_position = (
            find_split_position(
                remaining,
                limit
            )
        )

        if split_position <= 0:
            split_position = limit

        part = (
            remaining[
                :split_position
            ]
            .strip()
        )

        if part:

            parts.append(
                part
            )

        new_remaining = (
            remaining[
                split_position:
            ]
            .strip()
        )

        if (
            new_remaining
            == remaining
        ):

            logger.error(
                "❌ split_text made no progress"
            )

            break

        remaining = (
            new_remaining
        )

    logger.info(
        f"✂️ Text split | "
        f"original={len(text)} | "
        f"limit={limit} | "
        f"parts={len(parts)}"
    )

    return parts


# =========================================================
# SPLIT MAIN TEXT FOR MEDIA
# =========================================================

def split_for_media(
    text: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:

    text = normalize_text(
        text
    )

    result = {
        "media_caption": "",
        "followup_messages": []
    }

    if not text:
        return result

    if (
        len(text)
        <= caption_limit
    ):

        result[
            "media_caption"
        ] = text

        return result

    split_position = (
        find_split_position(
            text,
            caption_limit
        )
    )

    if split_position <= 0:
        split_position = caption_limit

    first_part = (
        text[
            :split_position
        ]
        .strip()
    )

    remaining = (
        text[
            split_position:
        ]
        .strip()
    )

    result[
        "media_caption"
    ] = first_part

    if remaining:

        result[
            "followup_messages"
        ] = split_text(
            remaining,
            message_limit
        )

    return result


# =========================================================
# MEDIA BRANDING PLACEMENT
# =========================================================

def place_branding(
    media_caption: str,
    followup_messages: List[str],
    branding: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:

    media_caption = normalize_text(
        media_caption
    )

    branding = normalize_text(
        branding
    )

    messages = list(
        followup_messages
        or []
    )

    if not branding:

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    if messages:

        last_message = (
            messages[-1]
        )

        combined = (
            append_branding(
                last_message,
                branding
            )
        )

        if (
            len(combined)
            <= message_limit
        ):

            messages[-1] = (
                combined
            )

        else:

            if (
                len(branding)
                <= message_limit
            ):

                messages.append(
                    branding
                )

            else:

                messages.extend(
                    split_text(
                        branding,
                        message_limit
                    )
                )

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    combined_caption = (
        append_branding(
            media_caption,
            branding
        )
    )

    if (
        len(combined_caption)
        <= caption_limit
    ):

        media_caption = (
            combined_caption
        )

    else:

        if (
            len(branding)
            <= message_limit
        ):

            messages.append(
                branding
            )

        else:

            messages.extend(
                split_text(
                    branding,
                    message_limit
                )
            )

    return {
        "media_caption": media_caption,
        "followup_messages": messages
    }


# =========================================================
# TEXT BRANDING PLACEMENT
# =========================================================

def place_branding_in_text_messages(
    messages: List[str],
    branding: str,
    message_limit: int
) -> List[str]:

    result = list(
        messages
        or []
    )

    branding = normalize_text(
        branding
    )

    if not branding:
        return result

    if not result:

        if (
            len(branding)
            <= message_limit
        ):

            return [
                branding
            ]

        return split_text(
            branding,
            message_limit
        )

    last_message = (
        result[-1]
    )

    combined = (
        append_branding(
            last_message,
            branding
        )
    )

    if (
        len(combined)
        <= message_limit
    ):

        result[-1] = (
            combined
        )

        return result

    if (
        len(branding)
        <= message_limit
    ):

        result.append(
            branding
        )

        return result

    result.extend(
        split_text(
            branding,
            message_limit
        )
    )

    return result


# =========================================================
# TELEGRAM BLOCKQUOTE
# =========================================================

def create_telegram_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    combined_blocks: List[
        Dict[str, Any]
    ] = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": False
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            ),
            "expandable": True
        })

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    result: List[str] = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        expandable = bool(
            block.get(
                "expandable",
                False
            )
        )

        raw_limit = (
            TELEGRAM_MESSAGE_SAFE_LIMIT
            - 100
        )

        raw_parts = (
            split_text(
                raw_text,
                raw_limit
            )
        )

        for raw_part in raw_parts:

            html_message = (
                build_blockquote_html(
                    raw_part,
                    expandable=expandable
                )
            )

            if (
                len(html_message)
                <= TELEGRAM_MESSAGE_SAFE_LIMIT
            ):

                result.append(
                    html_message
                )

                continue

            retry_limit = max(
                500,
                raw_limit // 2
            )

            retry_parts = (
                split_text(
                    raw_part,
                    retry_limit
                )
            )

            for retry_part in retry_parts:

                retry_html = (
                    build_blockquote_html(
                        retry_part,
                        expandable=expandable
                    )
                )

                if (
                    len(retry_html)
                    <= TELEGRAM_MESSAGE_LIMIT
                ):

                    result.append(
                        retry_html
                    )

                else:

                    logger.error(
                        "❌ Telegram blockquote "
                        "still exceeds message limit"
                    )

    return result


# =========================================================
# BALE BLOCKQUOTE
# =========================================================

def build_bale_blockquote(
    text: str
) -> str:

    text = normalize_text(
        text
    )

    if not text:
        return ""

    lines = (
        text.splitlines()
    )

    output_lines = []

    for line in lines:

        line = (
            line.strip()
        )

        if not line:
            continue

        output_lines.append(
            f"▌ {line}"
        )

    return "\n".join(
        output_lines
    )


def create_bale_blockquote_messages(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> List[str]:

    combined_blocks = []

    for block in (
        blockquote_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            )
        })

    for block in (
        expandable_blocks
        or []
    ):

        combined_blocks.append({
            "offset": block.get(
                "offset",
                0
            ),
            "text": block.get(
                "text",
                ""
            )
        })

    combined_blocks.sort(
        key=lambda item: (
            item.get(
                "offset",
                0
            )
        )
    )

    result = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        raw_limit = (
            BALE_MESSAGE_SAFE_LIMIT
            - 200
        )

        raw_parts = (
            split_text(
                raw_text,
                raw_limit
            )
        )

        for raw_part in raw_parts:

            bale_message = (
                build_bale_blockquote(
                    raw_part
                )
            )

            if (
                len(bale_message)
                <= BALE_MESSAGE_SAFE_LIMIT
            ):

                result.append(
                    bale_message
                )

                continue

            retry_parts = (
                split_text(
                    raw_part,
                    max(
                        500,
                        raw_limit // 2
                    )
                )
            )

            for retry_part in retry_parts:

                retry_message = (
                    build_bale_blockquote(
                        retry_part
                    )
                )

                if (
                    len(retry_message)
                    <= BALE_MESSAGE_LIMIT
                ):

                    result.append(
                        retry_message
                    )

                else:

                    logger.error(
                        "❌ Bale blockquote "
                        "still exceeds message limit"
                    )

    return result


# =========================================================
# TELEGRAM MEDIA PLAN
# =========================================================

def create_telegram_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    plan = {
        "media_caption": "",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    split_result = (
        split_for_media(
            main_text,
            TELEGRAM_CAPTION_SAFE_LIMIT,
            TELEGRAM_MESSAGE_SAFE_LIMIT
        )
    )

    media_caption = (
        split_result[
            "media_caption"
        ]
    )

    followup_messages = (
        split_result[
            "followup_messages"
        ]
    )

    branded_result = (
        place_branding(
            media_caption,
            followup_messages,
            branding,
            TELEGRAM_CAPTION_SAFE_LIMIT,
            TELEGRAM_MESSAGE_SAFE_LIMIT
        )
    )

    plan[
        "media_caption"
    ] = (
        branded_result[
            "media_caption"
        ]
    )

    plan[
        "followup_messages"
    ] = (
        branded_result[
            "followup_messages"
        ]
    )

    plan[
        "blockquote_messages"
    ] = (
        create_telegram_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if (
        len(
            plan[
                "media_caption"
            ]
        )
        > TELEGRAM_CAPTION_LIMIT
    ):

        logger.error(
            "❌ Telegram media caption exceeds "
            "official limit after planning"
        )

        plan[
            "document_fallback"
        ] = True

    valid_followups = []

    for message in (
        plan[
            "followup_messages"
        ]
    ):

        if (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            valid_followups.append(
                message
            )

        else:

            valid_followups.extend(
                split_text(
                    message,
                    TELEGRAM_MESSAGE_SAFE_LIMIT
                )
            )

    plan[
        "followup_messages"
    ] = valid_followups

    logger.info(
        f"📋 Telegram media plan | "
        f"caption="
        f"{len(plan['media_caption'])} | "
        f"followup="
        f"{len(plan['followup_messages'])} | "
        f"blockquote="
        f"{len(plan['blockquote_messages'])} | "
        f"fallback="
        f"{plan['document_fallback']}"
    )

    return plan


# =========================================================
# BALE MEDIA PLAN
# =========================================================

def create_bale_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    plan = {
        "media_caption": "",
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    split_result = (
        split_for_media(
            main_text,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    media_caption = (
        split_result[
            "media_caption"
        ]
    )

    followup_messages = (
        split_result[
            "followup_messages"
        ]
    )

    branded_result = (
        place_branding(
            media_caption,
            followup_messages,
            branding,
            BALE_CAPTION_SAFE_LIMIT,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    plan[
        "media_caption"
    ] = (
        branded_result[
            "media_caption"
        ]
    )

    plan[
        "followup_messages"
    ] = (
        branded_result[
            "followup_messages"
        ]
    )

    plan[
        "blockquote_messages"
    ] = (
        create_bale_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if (
        len(
            plan[
                "media_caption"
            ]
        )
        > BALE_CAPTION_LIMIT
    ):

        logger.error(
            "❌ Bale media caption exceeds "
            "configured platform limit"
        )

        plan[
            "document_fallback"
        ] = True

    valid_followups = []

    for message in (
        plan[
            "followup_messages"
        ]
    ):

        if (
            len(message)
            <= BALE_MESSAGE_LIMIT
        ):

            valid_followups.append(
                message
            )

        else:

            valid_followups.extend(
                split_text(
                    message,
                    BALE_MESSAGE_SAFE_LIMIT
                )
            )

    plan[
        "followup_messages"
    ] = valid_followups

    logger.info(
        f"📋 Bale media plan | "
        f"caption="
        f"{len(plan['media_caption'])} | "
        f"followup="
        f"{len(plan['followup_messages'])} | "
        f"blockquote="
        f"{len(plan['blockquote_messages'])} | "
        f"fallback="
        f"{plan['document_fallback']}"
    )

    return plan


# =========================================================
# TELEGRAM TEXT PLAN
# =========================================================

def create_telegram_text_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:
    """
    Text Plan مستقل Telegram.

    قانون اصلی:

    اگر:

        main_text + branding <= 4096

    باشد، خروجی دقیقاً یک پیام خواهد بود.

    فقط زمانی Split انجام می‌شود که خروجی نهایی
    واقعاً از سقف رسمی Telegram عبور کند.
    """

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    messages: List[str] = []

    # =====================================================
    # FAST PATH
    # FINAL CONTENT FITS ONE TELEGRAM MESSAGE
    # =====================================================

    combined_content = (
        append_branding(
            main_text,
            branding
        )
    )

    if (
        combined_content
        and len(combined_content)
        <= TELEGRAM_MESSAGE_LIMIT
    ):

        messages = [
            combined_content
        ]

    else:

        # =================================================
        # MAIN TEXT REALLY NEEDS SPLITTING
        # =================================================

        if main_text:

            messages = (
                split_text(
                    main_text,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

        # =================================================
        # BRANDING
        # =================================================

        messages = (
            place_branding_in_text_messages(
                messages,
                branding,
                TELEGRAM_MESSAGE_LIMIT
            )
        )

    # =====================================================
    # FINAL VALIDATION
    # =====================================================

    safe_messages: List[str] = []

    for message in messages:

        if not message:
            continue

        if (
            len(message)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            safe_messages.append(
                message
            )

        else:

            safe_messages.extend(
                split_text(
                    message,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

    # =====================================================
    # BLOCKQUOTES
    # =====================================================

    blockquote_messages = (
        create_telegram_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    plan = {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }

    logger.info(
        f"📋 Telegram text plan | "
        f"messages="
        f"{len(plan['messages'])} | "
        f"blockquote="
        f"{len(plan['blockquote_messages'])} | "
        f"main={len(main_text)} | "
        f"branding={len(branding)}"
    )

    return plan


# =========================================================
# BALE TEXT PLAN
# =========================================================

def create_bale_text_plan(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> Dict[str, Any]:

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    messages = []

    if main_text:

        messages = split_text(
            main_text,
            BALE_MESSAGE_SAFE_LIMIT
        )

    messages = (
        place_branding_in_text_messages(
            messages,
            branding,
            BALE_MESSAGE_SAFE_LIMIT
        )
    )

    safe_messages = []

    for message in messages:

        if (
            len(message)
            <= BALE_MESSAGE_LIMIT
        ):

            safe_messages.append(
                message
            )

        else:

            safe_messages.extend(
                split_text(
                    message,
                    BALE_MESSAGE_SAFE_LIMIT
                )
            )

    blockquote_messages = (
        create_bale_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    plan = {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }

    logger.info(
        f"📋 Bale text plan | "
        f"messages="
        f"{len(plan['messages'])} | "
        f"blockquote="
        f"{len(plan['blockquote_messages'])}"
    )

    return plan


# =========================================================
# MAIN ANALYZER
# =========================================================

def analyze_content(
    main_text: str,
    blockquote_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    expandable_blocks: Optional[
        List[Dict[str, Any]]
    ] = None,
    other_entities: Optional[
        List[Dict[str, Any]]
    ] = None,
    branding: str = ""
) -> PublicationPlan:

    main_text = normalize_text(
        main_text
    )

    blockquote_blocks = list(
        blockquote_blocks
        or []
    )

    expandable_blocks = list(
        expandable_blocks
        or []
    )

    other_entities = list(
        other_entities
        or []
    )

    branding = normalize_text(
        branding
    )

    logger.info(
        f"🔍 Caption Manager analyzing | "
        f"main={len(main_text)} | "
        f"blockquote="
        f"{len(blockquote_blocks)} | "
        f"expandable="
        f"{len(expandable_blocks)} | "
        f"other="
        f"{len(other_entities)} | "
        f"branding={len(branding)}"
    )

    plan = PublicationPlan()

    plan.metadata[
        "other_entities"
    ] = (
        other_entities
    )

    plan.telegram = (
        create_telegram_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.bale = (
        create_bale_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.text[
        "telegram"
    ] = (
        create_telegram_text_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    plan.text[
        "bale"
    ] = (
        create_bale_text_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    telegram_total_messages = (
        1
        + len(
            plan.telegram[
                "followup_messages"
            ]
        )
        + len(
            plan.telegram[
                "blockquote_messages"
            ]
        )
    )

    bale_total_messages = (
        1
        + len(
            plan.bale[
                "followup_messages"
            ]
        )
        + len(
            plan.bale[
                "blockquote_messages"
            ]
        )
    )

    telegram_text_total = (
        len(
            plan.text[
                "telegram"
            ][
                "messages"
            ]
        )
        + len(
            plan.text[
                "telegram"
            ][
                "blockquote_messages"
            ]
        )
    )

    bale_text_total = (
        len(
            plan.text[
                "bale"
            ][
                "messages"
            ]
        )
        + len(
            plan.text[
                "bale"
            ][
                "blockquote_messages"
            ]
        )
    )

    logger.info(
        f"✅ Publication Plan ready | "
        f"telegram_media_messages="
        f"{telegram_total_messages} | "
        f"bale_media_messages="
        f"{bale_total_messages} | "
        f"telegram_text_messages="
        f"{telegram_text_total} | "
        f"bale_text_messages="
        f"{bale_text_total}"
    )

    return plan
