import logging
from html import escape
from typing import (
    Dict,
    List,
    Optional,
    Any
)

from core.content_entities import (
    build_blockquote_html
)

from core.cleaner import (
    clean_text
)


logger = logging.getLogger(__name__)


# =========================================================
# PLATFORM LIMITS
# =========================================================

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096

BALE_CAPTION_LIMIT = 4096
BALE_MESSAGE_LIMIT = 4096


# =========================================================
# INTERNAL SAFE LIMITS
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
            "media_parse_mode": None,
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

    return str(text).strip()


def get_text_length(
    text: Optional[str]
) -> int:

    if not text:
        return 0

    return len(text)


def append_branding(
    text: str,
    branding: str
) -> str:

    text = normalize_text(text)
    branding = normalize_text(branding)

    if not branding:
        return text

    if not text:
        return branding

    return (
        f"{text}\n\n"
        f"{branding}"
    )


# =========================================================
# CLEAN BLOCKQUOTE TEXT
# =========================================================

def clean_blockquote_text(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    try:

        cleaned = clean_text(text)

        return normalize_text(cleaned)

    except Exception as e:

        logger.exception(
            f"❌ Blockquote cleaning failed | {e}"
        )

        return text


# =========================================================
# LONG TEXT COMPACT MODE
# =========================================================

def compact_long_text(
    text: str
) -> str:

    text = normalize_text(text)

    if not text:
        return ""

    raw_lines = text.splitlines()

    content_lines: List[str] = []

    for line in raw_lines:

        stripped = line.strip()

        if not stripped:
            continue

        content_lines.append(stripped)

    if not content_lines:
        return ""

    title = content_lines[0]

    if len(content_lines) == 1:
        return title

    body_lines: List[str] = []

    for line in content_lines[1:]:

        cleaned_line = line.strip()

        if cleaned_line.startswith("🔹"):

            cleaned_line = (
                cleaned_line[
                    len("🔹"):
                ]
                .lstrip()
            )

        if not cleaned_line:
            continue

        body_lines.append(cleaned_line)

    if not body_lines:
        return title

    result = (
        title
        + "\n\n"
        + "\n".join(body_lines)
    )

    logger.info(
        f"🗜️ Long text compacted | "
        f"before={len(text)} | "
        f"after={len(result)} | "
        f"saved={len(text) - len(result)}"
    )

    return result


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

    search_text = text[:limit]

    position = search_text.rfind("\n\n")

    if position > 0:
        return position

    position = search_text.rfind("\n")

    if position > 0:
        return position

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

        position = search_text.rfind(mark)

        if position > best_sentence_position:

            best_sentence_position = position

    if best_sentence_position > 0:

        return best_sentence_position + 1

    position = search_text.rfind(" ")

    if position > 0:
        return position

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

    text = normalize_text(text)

    if not text:
        return []

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero"
        )

    if len(text) <= limit:
        return [text]

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

            final_part = remaining.strip()

            if final_part:

                parts.append(final_part)

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
            remaining[:split_position]
            .strip()
        )

        if part:
            parts.append(part)

        new_remaining = (
            remaining[split_position:]
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

    text = normalize_text(text)

    result = {
        "media_caption": "",
        "followup_messages": []
    }

    if not text:
        return result

    # =====================================================
    # NORMAL VERSION FITS
    # =====================================================

    if len(text) <= caption_limit:

        result["media_caption"] = text

        return result

    # =====================================================
    # TRY COMPACT VERSION FIRST
    # =====================================================

    compact_text = compact_long_text(text)

    if (
        compact_text
        and len(compact_text) <= caption_limit
    ):

        result["media_caption"] = compact_text

        logger.info(
            f"🗜️ Media compact mode used | "
            f"before={len(text)} | "
            f"after={len(compact_text)}"
        )

        return result

    # =====================================================
    # COMPACT STILL TOO LONG
    #
    # ادامه متن بعداً توسط Media Handler به صورت Reply
    # ارسال خواهد شد.
    # =====================================================

    source_text = (
        compact_text
        or text
    )

    split_position = (
        find_split_position(
            source_text,
            caption_limit
        )
    )

    if split_position <= 0:
        split_position = caption_limit

    first_part = (
        source_text[:split_position]
        .strip()
    )

    remaining = (
        source_text[split_position:]
        .strip()
    )

    result["media_caption"] = first_part

    if remaining:

        result["followup_messages"] = (
            split_text(
                remaining,
                message_limit
            )
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

    # =====================================================
    # FOLLOW-UP EXISTS
    # =====================================================

    if messages:

        last_message = messages[-1]

        combined = (
            append_branding(
                last_message,
                branding
            )
        )

        if len(combined) <= message_limit:

            messages[-1] = combined

        elif len(branding) <= message_limit:

            messages.append(branding)

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

    # =====================================================
    # NO FOLLOW-UP
    # =====================================================

    combined_caption = (
        append_branding(
            media_caption,
            branding
        )
    )

    if len(combined_caption) <= caption_limit:

        media_caption = combined_caption

    elif len(branding) <= message_limit:

        messages.append(branding)

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

    branding = normalize_text(branding)

    if not branding:
        return result

    if not result:

        if len(branding) <= message_limit:
            return [branding]

        return split_text(
            branding,
            message_limit
        )

    last_message = result[-1]

    combined = (
        append_branding(
            last_message,
            branding
        )
    )

    if len(combined) <= message_limit:

        result[-1] = combined

        return result

    if len(branding) <= message_limit:

        result.append(branding)

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

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
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
                cleaned_text,
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

    return result


# =========================================================
# BUILD INLINE TELEGRAM BLOCKQUOTES
# =========================================================

def build_inline_telegram_blockquotes(
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ]
) -> str:
    """
    Blockquoteهای Telegram را برای قرار گرفتن داخل
    همان Caption خبر می‌سازد.

    این تابع مخصوص Media Caption است.

    نکته مهم:
    Blockquote دیگر ذاتاً پیام جدا نیست.
    ابتدا تلاش می‌کنیم آن را داخل خود Caption قرار دهیم.
    """

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

    html_parts: List[str] = []

    for block in combined_blocks:

        raw_text = normalize_text(
            block.get(
                "text",
                ""
            )
        )

        if not raw_text:
            continue

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
            continue

        html_parts.append(
            build_blockquote_html(
                cleaned_text,
                expandable=bool(
                    block.get(
                        "expandable",
                        False
                    )
                )
            )
        )

    return "\n\n".join(
        html_parts
    )


# =========================================================
# BUILD TELEGRAM HTML MEDIA CAPTION
# =========================================================

def build_telegram_html_caption(
    main_text: str,
    blockquote_blocks: List[
        Dict[str, Any]
    ],
    expandable_blocks: List[
        Dict[str, Any]
    ],
    branding: str
) -> str:
    """
    ساخت Caption کامل Telegram با HTML.

    main_text و branding escape می‌شوند.
    Blockquote HTML واقعی باقی می‌ماند.
    """

    parts: List[str] = []

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    if main_text:

        parts.append(
            escape(
                main_text
            )
        )

    inline_blockquotes = (
        build_inline_telegram_blockquotes(
            blockquote_blocks,
            expandable_blocks
        )
    )

    if inline_blockquotes:

        parts.append(
            inline_blockquotes
        )

    if branding:

        parts.append(
            escape(
                branding
            )
        )

    return "\n\n".join(
        parts
    )


# =========================================================
# BALE BLOCKQUOTE
# =========================================================

def build_bale_blockquote(
    text: str
) -> str:

    text = normalize_text(text)

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

        cleaned_text = (
            clean_blockquote_text(
                raw_text
            )
        )

        if not cleaned_text:
            continue

        raw_limit = (
            BALE_MESSAGE_SAFE_LIMIT
            - 200
        )

        raw_parts = (
            split_text(
                cleaned_text,
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
        "media_parse_mode": None,
        "followup_messages": [],
        "blockquote_messages": [],
        "document_fallback": False
    }

    has_blockquotes = bool(
        blockquote_blocks
        or expandable_blocks
    )

    # =====================================================
    # FIRST TRY:
    # EVERYTHING INSIDE THE SAME MEDIA CAPTION
    # =====================================================

    if has_blockquotes:

        normal_html_caption = (
            build_telegram_html_caption(
                main_text,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            normal_html_caption
            and len(normal_html_caption)
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        ):

            plan[
                "media_caption"
            ] = normal_html_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🧩 Telegram inline blockquote caption | "
                f"length={len(normal_html_caption)}"
            )

            return plan

        # =================================================
        # TRY COMPACT MAIN TEXT + INLINE BLOCKQUOTE
        # =================================================

        compact_main = (
            compact_long_text(
                main_text
            )
        )

        compact_html_caption = (
            build_telegram_html_caption(
                compact_main,
                blockquote_blocks,
                expandable_blocks,
                branding
            )
        )

        if (
            compact_html_caption
            and len(compact_html_caption)
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        ):

            plan[
                "media_caption"
            ] = compact_html_caption

            plan[
                "media_parse_mode"
            ] = "HTML"

            logger.info(
                f"🗜️ Telegram compact inline "
                f"blockquote caption | "
                f"length={len(compact_html_caption)}"
            )

            return plan

        # =================================================
        # BLOCKQUOTE CANNOT FIT WITH FULL MAIN TEXT
        #
        # برای جلوگیری از ارسال مستقل Blockquote،
        # متن اصلی تا جای ممکن فشرده می‌شود و Caption
        # به صورت HTML ساخته می‌شود.
        #
        # اگر کل مجموعه هنوز جا نشود، مسیر طولانی
        # main text استفاده می‌شود. Blockquote مستقل
        # تولید نمی‌کنیم.
        # =================================================

        logger.info(
            "ℹ️ Inline blockquote caption exceeds "
            "Telegram caption safe limit"
        )

    # =====================================================
    # MAIN TEXT MEDIA PLAN
    # =====================================================

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

    followup_messages = list(
        split_result[
            "followup_messages"
        ]
    )

    # =====================================================
    # IF BLOCKQUOTE EXISTS:
    # TRY TO APPEND IT TO CURRENT CAPTION
    # =====================================================

    if has_blockquotes:

        inline_blockquotes = (
            build_inline_telegram_blockquotes(
                blockquote_blocks,
                expandable_blocks
            )
        )

        candidate_parts: List[str] = []

        if media_caption:

            candidate_parts.append(
                escape(
                    media_caption
                )
            )

        if inline_blockquotes:

            candidate_parts.append(
                inline_blockquotes
            )

        candidate_without_branding = (
            "\n\n".join(
                candidate_parts
            )
        )

        candidate = (
            candidate_without_branding
        )

        if branding:

            candidate = (
                candidate
                + (
                    "\n\n"
                    if candidate
                    else ""
                )
                + escape(
                    branding
                )
            )

        if (
            candidate
            and len(candidate)
            <= TELEGRAM_CAPTION_SAFE_LIMIT
        ):

            plan[
                "media_caption"
            ] = candidate

            plan[
                "media_parse_mode"
            ] = "HTML"

            plan[
                "followup_messages"
            ] = followup_messages

            # Blockquote عمداً جدا ارسال نمی‌شود.
            plan[
                "blockquote_messages"
            ] = []

            return plan

        # =================================================
        # LAST INLINE ATTEMPT:
        # reserve caption room for blockquote + branding
        # =================================================

        suffix_parts: List[str] = []

        if inline_blockquotes:

            suffix_parts.append(
                inline_blockquotes
            )

        if branding:

            suffix_parts.append(
                escape(
                    branding
                )
            )

        suffix = "\n\n".join(
            suffix_parts
        )

        separator_length = (
            2
            if suffix
            else 0
        )

        available_for_main = (
            TELEGRAM_CAPTION_SAFE_LIMIT
            - len(suffix)
            - separator_length
        )

        if available_for_main > 50:

            compact_source = (
                compact_long_text(
                    main_text
                )
                or main_text
            )

            if (
                len(compact_source)
                <= available_for_main
            ):

                main_for_caption = (
                    compact_source
                )

                remaining_main = ""

            else:

                split_position = (
                    find_split_position(
                        compact_source,
                        available_for_main
                    )
                )

                if split_position <= 0:

                    split_position = (
                        available_for_main
                    )

                main_for_caption = (
                    compact_source[
                        :split_position
                    ]
                    .strip()
                )

                remaining_main = (
                    compact_source[
                        split_position:
                    ]
                    .strip()
                )

            html_parts: List[str] = []

            if main_for_caption:

                html_parts.append(
                    escape(
                        main_for_caption
                    )
                )

            if suffix:

                html_parts.append(
                    suffix
                )

            final_html_caption = (
                "\n\n".join(
                    html_parts
                )
            )

            if (
                final_html_caption
                and len(final_html_caption)
                <= TELEGRAM_CAPTION_SAFE_LIMIT
            ):

                plan[
                    "media_caption"
                ] = final_html_caption

                plan[
                    "media_parse_mode"
                ] = "HTML"

                plan[
                    "blockquote_messages"
                ] = []

                if remaining_main:

                    plan[
                        "followup_messages"
                    ] = (
                        split_text(
                            remaining_main,
                            TELEGRAM_MESSAGE_SAFE_LIMIT
                        )
                    )

                    # Branding داخل Caption قرار گرفته،
                    # پس به Reply اضافه نمی‌شود.

                else:

                    plan[
                        "followup_messages"
                    ] = []

                logger.info(
                    f"🧩 Telegram blockquote preserved "
                    f"inside long media caption | "
                    f"caption={len(final_html_caption)} | "
                    f"followup="
                    f"{len(plan['followup_messages'])}"
                )

                return plan

        # =================================================
        # EXTREME EDGE CASE
        #
        # خود Blockquote + Branding آنقدر بزرگ است که
        # در Caption جا نمی‌شود.
        #
        # در این حالت نمی‌توان با محدودیت Telegram
        # Blockquote کامل را داخل Caption نگه داشت.
        # برای جلوگیری از ارسال ناقص، fallback فعال می‌شود.
        # =================================================

        logger.error(
            "❌ Inline Telegram blockquote itself "
            "cannot fit media caption"
        )

        plan[
            "document_fallback"
        ] = True

        return plan

    # =====================================================
    # NORMAL MEDIA WITHOUT BLOCKQUOTE
    # =====================================================

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
        f"📋 Telegram media plan | "
        f"caption="
        f"{len(plan['media_caption'])} | "
        f"parse_mode="
        f"{plan['media_parse_mode'] or 'NONE'} | "
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

    main_text = normalize_text(
        main_text
    )

    branding = normalize_text(
        branding
    )

    messages: List[str] = []

    normal_final = (
        append_branding(
            main_text,
            branding
        )
    )

    if (
        normal_final
        and len(normal_final)
        <= TELEGRAM_MESSAGE_LIMIT
    ):

        messages = [
            normal_final
        ]

    else:

        compact_text = (
            compact_long_text(
                main_text
            )
        )

        compact_final = (
            append_branding(
                compact_text,
                branding
            )
        )

        if (
            compact_final
            and len(compact_final)
            <= TELEGRAM_MESSAGE_LIMIT
        ):

            messages = [
                compact_final
            ]

        else:

            source_for_split = (
                compact_text
                or main_text
            )

            if source_for_split:

                messages = (
                    split_text(
                        source_for_split,
                        TELEGRAM_MESSAGE_LIMIT
                    )
                )

            messages = (
                place_branding_in_text_messages(
                    messages,
                    branding,
                    TELEGRAM_MESSAGE_LIMIT
                )
            )

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

    blockquote_messages = (
        create_telegram_blockquote_messages(
            blockquote_blocks,
            expandable_blocks
        )
    )

    return {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }


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

        messages = (
            split_text(
                main_text,
                BALE_MESSAGE_SAFE_LIMIT
            )
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

    return {
        "messages": safe_messages,
        "blockquote_messages": (
            blockquote_messages
        )
    }


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

    logger.info(
        f"✅ Publication Plan ready | "
        f"tg_caption="
        f"{len(plan.telegram['media_caption'])} | "
        f"tg_followup="
        f"{len(plan.telegram['followup_messages'])} | "
        f"tg_inline_html="
        f"{bool(plan.telegram.get('media_parse_mode'))}"
    )

    return plan
