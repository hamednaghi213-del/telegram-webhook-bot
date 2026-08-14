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
# از سقف واقعی کمی فاصله نگه می‌داریم.
# =========================================================

TELEGRAM_CAPTION_SAFE_LIMIT = 1000
TELEGRAM_MESSAGE_SAFE_LIMIT = 4000

BALE_CAPTION_SAFE_LIMIT = 4000
BALE_MESSAGE_SAFE_LIMIT = 4000


# =========================================================
# PUBLICATION PLAN
# =========================================================

class PublicationPlan:
    """
    نقشه انتشار مستقل برای Telegram و Bale.

    Caption Manager فقط Plan می‌سازد.
    هیچ API Call در این کلاس یا ماژول انجام نمی‌شود.
    """

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

        # برای توسعه آینده Entityها
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
    """
    تبدیل مقدار ورودی به متن امن و Trim شده.
    """

    if not text:
        return ""

    return str(text).strip()


def get_text_length(
    text: Optional[str]
) -> int:
    """
    طول متن.
    """

    if not text:
        return 0

    return len(text)


def append_branding(
    text: str,
    branding: str
) -> str:
    """
    افزودن Branding با فاصله استاندارد.

    Branding فقط در مرحله تصمیم‌گیری نهایی
    باید اضافه شود.
    """

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
    """
    بهترین نقطه Split را پیدا می‌کند.

    اولویت:

    1. Paragraph
    2. Line
    3. Sentence
    4. Word
    5. Hard cut فقط در شرایط اجتناب‌ناپذیر
    """

    if not text:
        return 0

    if limit <= 0:
        return 0

    if len(text) <= limit:
        return len(text)

    search_text = text[:limit]

    # =====================================================
    # 1. PARAGRAPH
    # =====================================================

    position = search_text.rfind(
        "\n\n"
    )

    if position > 0:
        return position

    # =====================================================
    # 2. LINE
    # =====================================================

    position = search_text.rfind(
        "\n"
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
        "۔"
    )

    best_sentence_position = -1

    for mark in sentence_marks:

        position = search_text.rfind(
            mark
        )

        if position > best_sentence_position:
            best_sentence_position = position

    if best_sentence_position > 0:

        return (
            best_sentence_position
            + 1
        )

    # =====================================================
    # 4. WORD
    # =====================================================

    position = search_text.rfind(
        " "
    )

    if position > 0:
        return position

    # =====================================================
    # 5. EXTREMELY LONG TOKEN
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
    """
    تقسیم منطقی متن به بخش‌های حداکثر limit.
    """

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

        if len(remaining) <= limit:

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

        if new_remaining == remaining:

            logger.error(
                "❌ split_text made no progress"
            )

            break

        remaining = new_remaining

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
    """
    Split دو مرحله‌ای.

    اولین Chunk:
        مناسب Media Caption

    باقی متن:
        مناسب sendMessage
    """

    text = normalize_text(
        text
    )

    result = {
        "media_caption": "",
        "followup_messages": []
    }

    if not text:
        return result

    # =====================================================
    # ENTIRE TEXT FITS CAPTION
    # =====================================================

    if len(text) <= caption_limit:

        result[
            "media_caption"
        ] = text

        return result

    # =====================================================
    # FIRST PART FOR CAPTION
    # =====================================================

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

    # =====================================================
    # REMAINING TEXT USES MESSAGE LIMIT
    # =====================================================

    if remaining:

        result[
            "followup_messages"
        ] = split_text(
            remaining,
            message_limit
        )

    return result


# =========================================================
# BRANDING PLACEMENT
# =========================================================

def place_branding(
    media_caption: str,
    followup_messages: List[str],
    branding: str,
    caption_limit: int,
    message_limit: int
) -> Dict[str, Any]:
    """
    Branding را فقط یک بار و در آخرین محل منطقی قرار می‌دهد.

    اولویت:

    1. اگر Follow-up وجود ندارد و Caption جا دارد:
       Caption

    2. اگر Follow-up وجود دارد و آخرین Follow-up جا دارد:
       آخرین Follow-up

    3. در غیر این صورت:
       Follow-up مستقل Branding
    """

    media_caption = normalize_text(
        media_caption
    )

    branding = normalize_text(
        branding
    )

    messages = list(
        followup_messages or []
    )

    if not branding:

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    # =====================================================
    # FOLLOW-UP EXISTS
    # =====================================================

    if messages:

        last_message = messages[-1]

        combined = append_branding(
            last_message,
            branding
        )

        if len(combined) <= message_limit:

            messages[-1] = combined

        else:

            if len(branding) <= message_limit:

                messages.append(
                    branding
                )

            else:

                branding_parts = split_text(
                    branding,
                    message_limit
                )

                messages.extend(
                    branding_parts
                )

        return {
            "media_caption": media_caption,
            "followup_messages": messages
        }

    # =====================================================
    # NO FOLLOW-UP
    # TRY MEDIA CAPTION
    # =====================================================

    combined_caption = append_branding(
        media_caption,
        branding
    )

    if len(combined_caption) <= caption_limit:

        media_caption = (
            combined_caption
        )

    else:

        if len(branding) <= message_limit:

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
    """
    ساخت Telegram HTML Blockquote Messages.

    Blockquote قبل از HTML شدن Split می‌شود.
    """

    combined_blocks: List[
        Dict[str, Any]
    ] = []

    # =====================================================
    # NORMAL
    # =====================================================

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

    # =====================================================
    # EXPANDABLE
    # =====================================================

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

    # =====================================================
    # BUILD
    # =====================================================

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

        raw_parts = split_text(
            raw_text,
            raw_limit
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

            retry_parts = split_text(
                raw_part,
                retry_limit
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
    """
    Blockquote Plain Text برای Bale.

    مثال:

    ▌ خط اول
    ▌ خط دوم
    """

    text = normalize_text(
        text
    )

    if not text:
        return ""

    lines = text.splitlines()

    output_lines = []

    for line in lines:

        line = line.strip()

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
    """
    تبدیل تمام Blockquoteها به Plain Text برای Bale.
    """

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

        raw_parts = split_text(
            raw_text,
            raw_limit
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

            retry_parts = split_text(
                raw_part,
                max(
                    500,
                    raw_limit // 2
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
# TELEGRAM PLAN
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
    """
    ساخت Publication Plan برای Telegram.
    """

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

    # =====================================================
    # MAIN TEXT
    # =====================================================

    split_result = split_for_media(
        main_text,
        TELEGRAM_CAPTION_SAFE_LIMIT,
        TELEGRAM_MESSAGE_SAFE_LIMIT
    )

    media_caption = split_result[
        "media_caption"
    ]

    followup_messages = split_result[
        "followup_messages"
    ]

    # =====================================================
    # BRANDING
    # =====================================================

    branded_result = place_branding(
        media_caption,
        followup_messages,
        branding,
        TELEGRAM_CAPTION_SAFE_LIMIT,
        TELEGRAM_MESSAGE_SAFE_LIMIT
    )

    plan[
        "media_caption"
    ] = branded_result[
        "media_caption"
    ]

    plan[
        "followup_messages"
    ] = branded_result[
        "followup_messages"
    ]

    # =====================================================
    # BLOCKQUOTES
    # =====================================================

    plan[
        "blockquote_messages"
    ] = (
        create_telegram_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    # =====================================================
    # FINAL VALIDATION
    # =====================================================

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
        f"📋 Telegram plan | "
        f"caption={len(plan['media_caption'])} | "
        f"followup={len(plan['followup_messages'])} | "
        f"blockquote={len(plan['blockquote_messages'])} | "
        f"fallback={plan['document_fallback']}"
    )

    return plan


# =========================================================
# BALE PLAN
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
    """
    ساخت Publication Plan مستقل برای Bale.
    """

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

    # =====================================================
    # MAIN TEXT
    # =====================================================

    split_result = split_for_media(
        main_text,
        BALE_CAPTION_SAFE_LIMIT,
        BALE_MESSAGE_SAFE_LIMIT
    )

    media_caption = split_result[
        "media_caption"
    ]

    followup_messages = split_result[
        "followup_messages"
    ]

    # =====================================================
    # BRANDING
    # =====================================================

    branded_result = place_branding(
        media_caption,
        followup_messages,
        branding,
        BALE_CAPTION_SAFE_LIMIT,
        BALE_MESSAGE_SAFE_LIMIT
    )

    plan[
        "media_caption"
    ] = branded_result[
        "media_caption"
    ]

    plan[
        "followup_messages"
    ] = branded_result[
        "followup_messages"
    ]

    # =====================================================
    # BLOCKQUOTES
    # =====================================================

    plan[
        "blockquote_messages"
    ] = (
        create_bale_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    # =====================================================
    # FINAL VALIDATION
    # =====================================================

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
        f"📋 Bale plan | "
        f"caption={len(plan['media_caption'])} | "
        f"followup={len(plan['followup_messages'])} | "
        f"blockquote={len(plan['blockquote_messages'])} | "
        f"fallback={plan['document_fallback']}"
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
    """
    تحلیل کامل محتوا و ساخت Publication Plan.

    این تابع هیچ ارسال واقعی انجام نمی‌دهد.

    INPUT:

        main_text
        blockquote_blocks
        expandable_blocks
        other_entities
        branding

    OUTPUT:

        PublicationPlan
    """

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
        f"blockquote={len(blockquote_blocks)} | "
        f"expandable={len(expandable_blocks)} | "
        f"other={len(other_entities)} | "
        f"branding={len(branding)}"
    )

    # =====================================================
    # PLAN
    # =====================================================

    plan = PublicationPlan()

    # سایر Entityها برای آینده حفظ می‌شوند.
    plan.metadata[
        "other_entities"
    ] = other_entities

    # =====================================================
    # TELEGRAM
    # =====================================================

    plan.telegram = (
        create_telegram_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    # =====================================================
    # BALE
    # =====================================================

    plan.bale = (
        create_bale_plan(
            main_text,
            blockquote_blocks,
            expandable_blocks,
            branding
        )
    )

    # =====================================================
    # SUMMARY
    # =====================================================

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

    logger.info(
        f"✅ Publication Plan ready | "
        f"telegram_messages="
        f"{telegram_total_messages} | "
        f"bale_messages="
        f"{bale_total_messages}"
    )

    return plan
