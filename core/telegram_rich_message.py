"""
Telegram Rich Message input parser.

Purpose:
    Normalize Telegram Bot API Rich Messages into the existing
    shared publication model without adding publication logic here.

Telegram Bot API:
    Rich Messages introduced in Bot API 10.1 and extended through 10.3.

Architecture:
    Telegram rich_message
        -> telegram_rich_message.py
        -> normalized text / entities / quotes / media
        -> PreparedContent
        -> Shared Publication Engine

IMPORTANT:
    This module is Telegram-input-specific.
    It must NOT publish to Telegram/Bale.
    It must NOT run branding, formatter, duplicate guard,
    editorial review, smart summary, or caption manager.
"""

import logging

from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)


logger = logging.getLogger(__name__)


# =========================================================
# TELEGRAM RICH MESSAGE LIMITS
# Bot API 10.3
# =========================================================

MAX_RICH_TEXT_UTF8_BYTES = 32768
MAX_RICH_BLOCKS = 500
MAX_RICH_NESTING_DEPTH = 16
MAX_RICH_MEDIA_ATTACHMENTS = 50
MAX_RICH_TABLE_COLUMNS = 20


# =========================================================
# KNOWN TELEGRAM RICH BLOCK TYPES
# Bot API 10.3
# =========================================================

KNOWN_BLOCK_TYPES: Set[str] = {
    "paragraph",
    "heading",
    "pre",
    "footer",
    "divider",
    "mathematical_expression",
    "anchor",
    "list",
    "blockquote",
    "expandable_blockquote",
    "pullquote",
    "collage",
    "slideshow",
    "table",
    "details",
    "map",
    "buttons",
    "animation",
    "audio",
    "document",
    "photo",
    "video",
    "voice_note",
    "thinking",
}


# =========================================================
# MEDIA BLOCK TYPES
# =========================================================

MEDIA_BLOCK_TYPES: Set[str] = {
    "animation",
    "audio",
    "document",
    "photo",
    "video",
    "voice_note",
}


# =========================================================
# RICH MEDIA NAVIGATION HINTS
# =========================================================
#
# These are short UI instructions commonly placed in a
# Rich Message alongside slideshow/collage media.
#
# They are interaction/navigation instructions, not the
# editorial body of the news.
#
# Detection is deliberately conservative:
# - removal happens only if slideshow/collage exists
# - only exact short standalone phrases are removed
# - longer body sentences are preserved
# =========================================================

RICH_MEDIA_NAVIGATION_HINTS: Set[str] = {
    "ورق بزنید",
    "ورق بزن",
    "اسلاید بعد",
    "اسلاید بعدی",
    "برای ادامه ورق بزنید",
    "برای دیدن تصاویر ورق بزنید",
    "برای مشاهده تصاویر ورق بزنید",
    "swipe",
    "swipe left",
    "swipe right",
    "swipe to see more",
}


# =========================================================
# RICH TEXT TYPES THAT MAP TO TELEGRAM MESSAGE ENTITIES
# =========================================================

DIRECT_ENTITY_TYPES: Set[str] = {
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "spoiler",
    "code",
    "mention",
    "hashtag",
    "cashtag",
    "bot_command",
}


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass
class ParsedRichMessage:

    main_text: str = ""

    blockquote_blocks: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    expandable_blocks: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    other_entities: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    files: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    unsupported_blocks: List[
        str
    ] = field(
        default_factory=list
    )

    block_count: int = 0

    max_depth_seen: int = 0

    is_rtl: bool = False

    has_slideshow: bool = False

    has_collage: bool = False

    raw_block_types: List[
        str
    ] = field(
        default_factory=list
    )

    def to_dict(
        self
    ) -> Dict[str, Any]:

        return {
            "main_text":
                self.main_text,

            "blockquote_blocks":
                list(
                    self.blockquote_blocks
                ),

            "expandable_blocks":
                list(
                    self.expandable_blocks
                ),

            "other_entities":
                list(
                    self.other_entities
                ),

            "files":
                list(
                    self.files
                ),

            "unsupported_blocks":
                list(
                    self.unsupported_blocks
                ),

            "block_count":
                self.block_count,

            "max_depth_seen":
                self.max_depth_seen,

            "is_rtl":
                self.is_rtl,

            "has_slideshow":
                self.has_slideshow,

            "has_collage":
                self.has_collage,

            "raw_block_types":
                list(
                    self.raw_block_types
                ),
        }


# =========================================================
# INTERNAL WALK STATE
# =========================================================

@dataclass
class _WalkState:

    block_count: int = 0

    media_count: int = 0

    max_depth_seen: int = 0

    unsupported_blocks: Set[
        str
    ] = field(
        default_factory=set
    )

    raw_block_types: List[
        str
    ] = field(
        default_factory=list
    )

    files: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    blockquote_blocks: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    expandable_blocks: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    main_parts: List[
        Tuple[
            str,
            List[
                Dict[str, Any]
            ]
        ]
    ] = field(
        default_factory=list
    )

    seen_text_parts: Set[
        str
    ] = field(
        default_factory=set
    )

    has_slideshow: bool = False

    has_collage: bool = False


# =========================================================
# PUBLIC DETECTION
# =========================================================

def is_rich_message(
    message: Optional[
        Dict[str, Any]
    ]
) -> bool:
    """
    Returns True only when Telegram Message contains
    a valid rich_message object.
    """

    if not isinstance(
        message,
        dict
    ):

        return False

    rich_message = (
        message.get(
            "rich_message"
        )
    )

    return isinstance(
        rich_message,
        dict
    )


# =========================================================
# UTF-16 HELPERS
# Telegram entity offsets use UTF-16 code units.
# =========================================================

def _utf16_length(
    value: str
) -> int:

    value = str(
        value
        or ""
    )

    return (
        len(
            value.encode(
                "utf-16-le"
            )
        )
        // 2
    )


# =========================================================
# NORMALIZE STRING
# =========================================================

def _clean_text(
    value: Any
) -> str:

    if value is None:

        return ""

    if isinstance(
        value,
        str
    ):

        return value

    return str(
        value
    )


# =========================================================
# RICH TEXT PARSER
# =========================================================

def parse_rich_text(
    rich_text: Any
) -> Tuple[
    str,
    List[
        Dict[str, Any]
    ]
]:
    """
    Convert Telegram RichText recursively to plain text plus
    Telegram-compatible MessageEntity-like dictionaries.

    RichText can be:
        - String
        - Array[RichText]
        - RichText object

    Unsupported formatting is flattened to text instead of
    rejecting the whole message.
    """

    text_parts: List[str] = []

    entities: List[
        Dict[str, Any]
    ] = []

    current_utf16_offset = 0

    def append_plain(
        value: str
    ) -> None:

        nonlocal current_utf16_offset

        value = _clean_text(
            value
        )

        if not value:

            return

        text_parts.append(
            value
        )

        current_utf16_offset += (
            _utf16_length(
                value
            )
        )

    def walk(
        node: Any,
        depth: int = 0
    ) -> None:

        nonlocal current_utf16_offset

        if depth > (
            MAX_RICH_NESTING_DEPTH
            + 4
        ):

            logger.warning(
                "⚠️ RichText nesting exceeded safety limit"
            )

            return

        if node is None:

            return

        # -------------------------------------------------
        # Plain string
        # -------------------------------------------------

        if isinstance(
            node,
            str
        ):

            append_plain(
                node
            )

            return

        # -------------------------------------------------
        # Array of RichText
        # -------------------------------------------------

        if isinstance(
            node,
            (list, tuple)
        ):

            for item in node:

                walk(
                    item,
                    depth + 1
                )

            return

        # -------------------------------------------------
        # Unexpected primitive
        # -------------------------------------------------

        if not isinstance(
            node,
            dict
        ):

            append_plain(
                str(node)
            )

            return

        rich_type = (
            str(
                node.get(
                    "type",
                    ""
                )
                or ""
            )
            .strip()
            .lower()
        )

        # -------------------------------------------------
        # Custom Emoji
        # -------------------------------------------------

        if (
            rich_type
            == "custom_emoji"
        ):

            alternative_text = (
                _clean_text(
                    node.get(
                        "alternative_text",
                        ""
                    )
                )
            )

            start = (
                current_utf16_offset
            )

            append_plain(
                alternative_text
            )

            length = (
                current_utf16_offset
                - start
            )

            custom_emoji_id = (
                node.get(
                    "custom_emoji_id"
                )
            )

            if (
                length > 0
                and custom_emoji_id
            ):

                entities.append({
                    "type":
                        "custom_emoji",

                    "offset":
                        start,

                    "length":
                        length,

                    "custom_emoji_id":
                        str(
                            custom_emoji_id
                        ),
                })

            return

        # -------------------------------------------------
        # Mathematical expression
        # -------------------------------------------------

        if (
            rich_type
            == "mathematical_expression"
        ):

            append_plain(
                _clean_text(
                    node.get(
                        "expression",
                        ""
                    )
                )
            )

            return

        # -------------------------------------------------
        # Anchor
        # -------------------------------------------------

        if rich_type == "anchor":

            return

        # -------------------------------------------------
        # Rich inline button
        # -------------------------------------------------

        if rich_type == "button":

            button = (
                node.get(
                    "button"
                )
                or {}
            )

            if isinstance(
                button,
                dict
            ):

                walk(
                    button.get(
                        "text",
                        ""
                    ),
                    depth + 1
                )

            return

        # -------------------------------------------------
        # Most RichText wrappers contain "text".
        # -------------------------------------------------

        nested_text = (
            node.get(
                "text"
            )
        )

        start = (
            current_utf16_offset
        )

        if nested_text is not None:

            walk(
                nested_text,
                depth + 1
            )

        else:

            for fallback_key in (
                "alternative_text",
                "expression",
                "username",
                "hashtag",
                "cashtag",
                "bot_command",
                "email_address",
                "phone_number",
            ):

                fallback_value = (
                    node.get(
                        fallback_key
                    )
                )

                if fallback_value:

                    append_plain(
                        _clean_text(
                            fallback_value
                        )
                    )

                    break

        length = (
            current_utf16_offset
            - start
        )

        if length <= 0:

            return

        # -------------------------------------------------
        # Direct Telegram entity mapping
        # -------------------------------------------------

        if (
            rich_type
            in DIRECT_ENTITY_TYPES
        ):

            entities.append({
                "type":
                    rich_type,

                "offset":
                    start,

                "length":
                    length,
            })

            return

        # -------------------------------------------------
        # URL -> text_link
        # -------------------------------------------------

        if rich_type == "url":

            url = (
                node.get(
                    "url"
                )
            )

            if url:

                entities.append({
                    "type":
                        "text_link",

                    "offset":
                        start,

                    "length":
                        length,

                    "url":
                        str(
                            url
                        ),
                })

            return

        # -------------------------------------------------
        # User mention
        # -------------------------------------------------

        if (
            rich_type
            == "text_mention"
        ):

            user = (
                node.get(
                    "user"
                )
            )

            if isinstance(
                user,
                dict
            ):

                entities.append({
                    "type":
                        "text_mention",

                    "offset":
                        start,

                    "length":
                        length,

                    "user":
                        dict(
                            user
                        ),
                })

            return

        # -------------------------------------------------
        # Email
        # -------------------------------------------------

        if (
            rich_type
            == "email_address"
        ):

            entities.append({
                "type":
                    "email",

                "offset":
                    start,

                "length":
                    length,
            })

            return

        # -------------------------------------------------
        # Phone
        # -------------------------------------------------

        if (
            rich_type
            == "phone_number"
        ):

            entities.append({
                "type":
                    "phone_number",

                "offset":
                    start,

                "length":
                    length,
            })

            return

    walk(
        rich_text
    )

    return (
        "".join(
            text_parts
        ),
        entities
    )


# =========================================================
# CAPTION PARSER
# =========================================================

def _parse_caption(
    caption: Any
) -> Tuple[
    str,
    List[
        Dict[str, Any]
    ]
]:
    """
    Parse RichBlockCaption.

    Telegram RichBlockCaption:
        text
        credit
    """

    if not isinstance(
        caption,
        dict
    ):

        return (
            "",
            []
        )

    caption_text, entities = (
        parse_rich_text(
            caption.get(
                "text"
            )
        )
    )

    credit_text, credit_entities = (
        parse_rich_text(
            caption.get(
                "credit"
            )
        )
    )

    if (
        credit_text
        and credit_text.strip()
    ):

        if caption_text:

            prefix = "\n"

            shift = (
                _utf16_length(
                    caption_text
                    + prefix
                )
            )

            shifted_credit = []

            for entity in (
                credit_entities
            ):

                item = dict(
                    entity
                )

                item[
                    "offset"
                ] = (
                    int(
                        item.get(
                            "offset",
                            0
                        )
                    )
                    + shift
                )

                shifted_credit.append(
                    item
                )

            caption_text = (
                caption_text
                + prefix
                + credit_text
            )

            entities.extend(
                shifted_credit
            )

        else:

            caption_text = (
                credit_text
            )

            entities = list(
                credit_entities
            )

    return (
        caption_text,
        entities
    )


# =========================================================
# ENTITY SHIFT
# =========================================================

def _shift_entities(
    entities: Iterable[
        Dict[str, Any]
    ],
    offset: int
) -> List[
    Dict[str, Any]
]:

    result: List[
        Dict[str, Any]
    ] = []

    for entity in (
        entities
        or []
    ):

        if not isinstance(
            entity,
            dict
        ):

            continue

        item = dict(
            entity
        )

        try:

            item[
                "offset"
            ] = (
                int(
                    item.get(
                        "offset",
                        0
                    )
                )
                + int(
                    offset
                )
            )

        except Exception:

            continue

        result.append(
            item
        )

    return result


# =========================================================
# TEXT APPENDER
# =========================================================

def _append_main_text(
    state: _WalkState,
    text: str,
    entities: Optional[
        List[
            Dict[str, Any]
        ]
    ] = None,
    *,
    deduplicate: bool = False
) -> None:

    text = _clean_text(
        text
    ).strip()

    if not text:

        return

    normalized = (
        " ".join(
            text.split()
        )
    )

    if (
        deduplicate
        and normalized
        and normalized
        in state.seen_text_parts
    ):

        return

    if normalized:

        state.seen_text_parts.add(
            normalized
        )

    state.main_parts.append(
        (
            text,
            list(
                entities
                or []
            )
        )
    )


# =========================================================
# PHOTO FILE ID
# =========================================================

def _extract_photo_file_id(
    photo: Any
) -> Optional[str]:

    if not isinstance(
        photo,
        list
    ):

        return None

    valid_sizes = [
        item
        for item
        in photo
        if isinstance(
            item,
            dict
        )
        and item.get(
            "file_id"
        )
    ]

    if not valid_sizes:

        return None

    return str(
        valid_sizes[
            -1
        ][
            "file_id"
        ]
    )


# =========================================================
# GENERIC TELEGRAM FILE ID
# =========================================================

def _extract_object_file_id(
    value: Any
) -> Optional[str]:

    if not isinstance(
        value,
        dict
    ):

        return None

    file_id = (
        value.get(
            "file_id"
        )
    )

    if not file_id:

        return None

    return str(
        file_id
    )


# =========================================================
# MEDIA BLOCK PARSER
# =========================================================

def _consume_media_block(
    block: Dict[str, Any],
    block_type: str,
    state: _WalkState
) -> None:

    if state.media_count >= (
        MAX_RICH_MEDIA_ATTACHMENTS
    ):

        logger.warning(
            "⚠️ Rich Message media attachment limit reached | "
            f"limit={MAX_RICH_MEDIA_ATTACHMENTS}"
        )

        return

    file_id: Optional[str] = None

    normalized_type = (
        block_type
    )

    if block_type == "photo":

        file_id = (
            _extract_photo_file_id(
                block.get(
                    "photo"
                )
            )
        )

    elif block_type == "video":

        file_id = (
            _extract_object_file_id(
                block.get(
                    "video"
                )
            )
        )

    elif block_type == "document":

        file_id = (
            _extract_object_file_id(
                block.get(
                    "document"
                )
            )
        )

    elif block_type == "audio":

        file_id = (
            _extract_object_file_id(
                block.get(
                    "audio"
                )
            )
        )

    elif block_type == "voice_note":

        file_id = (
            _extract_object_file_id(
                block.get(
                    "voice_note"
                )
            )
        )

        normalized_type = "voice"

    elif block_type == "animation":

        file_id = (
            _extract_object_file_id(
                block.get(
                    "animation"
                )
            )
        )

        normalized_type = "animation"

    caption_text, caption_entities = (
        _parse_caption(
            block.get(
                "caption"
            )
        )
    )

    if file_id:

        file_item: Dict[
            str,
            Any
        ] = {
            "type":
                normalized_type,

            "file_id":
                file_id,
        }

        if caption_text:

            file_item[
                "caption"
            ] = caption_text

        if block.get(
            "has_spoiler"
        ):

            file_item[
                "has_spoiler"
            ] = True

        state.files.append(
            file_item
        )

        state.media_count += 1

    else:

        logger.warning(
            "⚠️ Rich media block has no usable file_id | "
            f"type={block_type}"
        )

    if caption_text:

        _append_main_text(
            state,
            caption_text,
            caption_entities,
            deduplicate=True
        )


# =========================================================
# TABLE FALLBACK
# =========================================================

def _consume_table(
    block: Dict[str, Any],
    state: _WalkState
) -> None:

    caption_text, caption_entities = (
        parse_rich_text(
            block.get(
                "caption"
            )
        )
    )

    if caption_text:

        _append_main_text(
            state,
            caption_text,
            caption_entities,
            deduplicate=True
        )

    cells = (
        block.get(
            "cells"
        )
        or []
    )

    if not isinstance(
        cells,
        list
    ):

        return

    rows: List[str] = []

    for row in cells:

        if not isinstance(
            row,
            list
        ):

            continue

        values: List[str] = []

        for cell in (
            row[
                :MAX_RICH_TABLE_COLUMNS
            ]
        ):

            if not isinstance(
                cell,
                dict
            ):

                continue

            value, _ = (
                parse_rich_text(
                    cell.get(
                        "text"
                    )
                )
            )

            values.append(
                value.strip()
            )

        if values:

            rows.append(
                " | ".join(
                    values
                )
            )

    if rows:

        _append_main_text(
            state,
            "\n".join(
                rows
            ),
            deduplicate=True
        )


# =========================================================
# BUTTON FALLBACK
# =========================================================

def _consume_buttons(
    block: Dict[str, Any],
    state: _WalkState
) -> None:

    buttons = (
        block.get(
            "buttons"
        )
        or []
    )

    if not isinstance(
        buttons,
        list
    ):

        return

    labels: List[str] = []

    for button in buttons:

        if not isinstance(
            button,
            dict
        ):

            continue

        value, _ = (
            parse_rich_text(
                button.get(
                    "text"
                )
            )
        )

        value = (
            value.strip()
        )

        if value:

            labels.append(
                value
            )

    if labels:

        _append_main_text(
            state,
            " | ".join(
                labels
            ),
            deduplicate=True
        )


# =========================================================
# MAP FALLBACK
# =========================================================

def _consume_map(
    block: Dict[str, Any],
    state: _WalkState
) -> None:

    caption_text, caption_entities = (
        _parse_caption(
            block.get(
                "caption"
            )
        )
    )

    if caption_text:

        _append_main_text(
            state,
            caption_text,
            caption_entities,
            deduplicate=True
        )

    location = (
        block.get(
            "location"
        )
        or {}
    )

    if not isinstance(
        location,
        dict
    ):

        return

    latitude = (
        location.get(
            "latitude"
        )
    )

    longitude = (
        location.get(
            "longitude"
        )
    )

    if (
        latitude is not None
        and longitude is not None
    ):

        _append_main_text(
            state,
            (
                f"{latitude}, "
                f"{longitude}"
            ),
            deduplicate=True
        )


# =========================================================
# BLOCK WALKER
# =========================================================

def _walk_block(
    block: Any,
    state: _WalkState,
    depth: int = 1
) -> None:

    if depth > (
        MAX_RICH_NESTING_DEPTH
    ):

        logger.warning(
            "⚠️ Rich Message block nesting limit exceeded | "
            f"depth={depth}"
        )

        return

    state.max_depth_seen = max(
        state.max_depth_seen,
        depth
    )

    if state.block_count >= (
        MAX_RICH_BLOCKS
    ):

        logger.warning(
            "⚠️ Rich Message block count limit reached | "
            f"limit={MAX_RICH_BLOCKS}"
        )

        return

    if not isinstance(
        block,
        dict
    ):

        return

    state.block_count += 1

    block_type = (
        str(
            block.get(
                "type",
                ""
            )
            or ""
        )
        .strip()
        .lower()
    )

    if not block_type:

        state.unsupported_blocks.add(
            "<missing-type>"
        )

        return

    state.raw_block_types.append(
        block_type
    )

    if (
        block_type
        not in KNOWN_BLOCK_TYPES
    ):

        state.unsupported_blocks.add(
            block_type
        )

        logger.warning(
            "⚠️ Unknown Telegram RichBlock | "
            f"type={block_type}"
        )

        fallback_text, fallback_entities = (
            parse_rich_text(
                block.get(
                    "text"
                )
            )
        )

        if fallback_text:

            _append_main_text(
                state,
                fallback_text,
                fallback_entities
            )

        nested_blocks = (
            block.get(
                "blocks"
            )
            or []
        )

        if isinstance(
            nested_blocks,
            list
        ):

            for child in nested_blocks:

                _walk_block(
                    child,
                    state,
                    depth + 1
                )

        return

    # =====================================================
    # SIMPLE TEXT BLOCKS
    # =====================================================

    if block_type in {
        "paragraph",
        "heading",
        "pre",
        "footer",
    }:

        text, entities = (
            parse_rich_text(
                block.get(
                    "text"
                )
            )
        )

        _append_main_text(
            state,
            text,
            entities
        )

        return

    # =====================================================
    # DIVIDER
    # =====================================================

    if block_type == "divider":

        return

    # =====================================================
    # MATHEMATICAL EXPRESSION
    # =====================================================

    if (
        block_type
        == "mathematical_expression"
    ):

        expression = (
            _clean_text(
                block.get(
                    "expression",
                    ""
                )
            )
        )

        _append_main_text(
            state,
            expression
        )

        return

    # =====================================================
    # ANCHOR
    # =====================================================

    if block_type == "anchor":

        return

    # =====================================================
    # LIST
    # =====================================================

    if block_type == "list":

        items = (
            block.get(
                "items"
            )
            or []
        )

        if not isinstance(
            items,
            list
        ):

            return

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                continue

            label = (
                _clean_text(
                    item.get(
                        "label",
                        ""
                    )
                )
                .strip()
            )

            if not label:

                value = (
                    item.get(
                        "value"
                    )
                )

                if value is not None:

                    label = (
                        f"{value}."
                    )

                else:

                    label = "•"

            child_state = (
                _WalkState()
            )

            for child in (
                item.get(
                    "blocks"
                )
                or []
            ):

                _walk_block(
                    child,
                    child_state,
                    depth + 1
                )

            state.block_count += (
                child_state.block_count
            )

            state.media_count += (
                child_state.media_count
            )

            state.max_depth_seen = max(
                state.max_depth_seen,
                child_state.max_depth_seen
            )

            state.files.extend(
                child_state.files
            )

            state.blockquote_blocks.extend(
                child_state.blockquote_blocks
            )

            state.expandable_blocks.extend(
                child_state.expandable_blocks
            )

            state.unsupported_blocks.update(
                child_state.unsupported_blocks
            )

            state.raw_block_types.extend(
                child_state.raw_block_types
            )

            item_text = (
                _assemble_main_text(
                    child_state
                )[0]
            )

            if item_text:

                _append_main_text(
                    state,
                    f"{label} {item_text}"
                )

        return

    # =====================================================
    # BLOCKQUOTE
    # =====================================================

    if block_type == "blockquote":

        quote_state = (
            _WalkState()
        )

        for child in (
            block.get(
                "blocks"
            )
            or []
        ):

            _walk_block(
                child,
                quote_state,
                depth + 1
            )

        quote_text, _ = (
            _assemble_main_text(
                quote_state
            )
        )

        credit_text, _ = (
            parse_rich_text(
                block.get(
                    "credit"
                )
            )
        )

        if credit_text:

            quote_text = (
                (
                    quote_text
                    + "\n"
                    + credit_text
                )
                if quote_text
                else credit_text
            )

        if quote_text.strip():

            state.blockquote_blocks.append({
                "type":
                    "blockquote",

                "text":
                    quote_text.strip(),
            })

        state.files.extend(
            quote_state.files
        )

        state.media_count += (
            quote_state.media_count
        )

        state.expandable_blocks.extend(
            quote_state.expandable_blocks
        )

        state.unsupported_blocks.update(
            quote_state.unsupported_blocks
        )

        state.raw_block_types.extend(
            quote_state.raw_block_types
        )

        state.block_count += (
            quote_state.block_count
        )

        state.max_depth_seen = max(
            state.max_depth_seen,
            quote_state.max_depth_seen
        )

        return

    # =====================================================
    # EXPANDABLE BLOCKQUOTE
    # =====================================================

    if (
        block_type
        == "expandable_blockquote"
    ):

        text, _ = (
            parse_rich_text(
                block.get(
                    "text"
                )
            )
        )

        credit_text, _ = (
            parse_rich_text(
                block.get(
                    "credit"
                )
            )
        )

        if credit_text:

            text = (
                (
                    text
                    + "\n"
                    + credit_text
                )
                if text
                else credit_text
            )

        if text.strip():

            state.expandable_blocks.append({
                "type":
                    "expandable_blockquote",

                "text":
                    text.strip(),
            })

        return

    # =====================================================
    # PULLQUOTE
    # =====================================================

    if block_type == "pullquote":

        text, _ = (
            parse_rich_text(
                block.get(
                    "text"
                )
            )
        )

        credit_text, _ = (
            parse_rich_text(
                block.get(
                    "credit"
                )
            )
        )

        if credit_text:

            text = (
                (
                    text
                    + "\n"
                    + credit_text
                )
                if text
                else credit_text
            )

        if text.strip():

            state.blockquote_blocks.append({
                "type":
                    "blockquote",

                "text":
                    text.strip(),

                "source_type":
                    "pullquote",
            })

        return

    # =====================================================
    # COLLAGE / SLIDESHOW
    # =====================================================

    if block_type in {
        "collage",
        "slideshow",
    }:

        if block_type == "slideshow":

            state.has_slideshow = True

        else:

            state.has_collage = True

        caption_text, caption_entities = (
            _parse_caption(
                block.get(
                    "caption"
                )
            )
        )

        if caption_text:

            _append_main_text(
                state,
                caption_text,
                caption_entities,
                deduplicate=True
            )

        children = (
            block.get(
                "blocks"
            )
            or []
        )

        if isinstance(
            children,
            list
        ):

            for child in children:

                _walk_block(
                    child,
                    state,
                    depth + 1
                )

        return

    # =====================================================
    # TABLE
    # =====================================================

    if block_type == "table":

        _consume_table(
            block,
            state
        )

        return

    # =====================================================
    # DETAILS
    # =====================================================

    if block_type == "details":

        summary_text, summary_entities = (
            parse_rich_text(
                block.get(
                    "summary"
                )
            )
        )

        if summary_text:

            _append_main_text(
                state,
                summary_text,
                summary_entities,
                deduplicate=True
            )

        children = (
            block.get(
                "blocks"
            )
            or []
        )

        if isinstance(
            children,
            list
        ):

            for child in children:

                _walk_block(
                    child,
                    state,
                    depth + 1
                )

        return

    # =====================================================
    # MAP
    # =====================================================

    if block_type == "map":

        _consume_map(
            block,
            state
        )

        return

    # =====================================================
    # BUTTONS
    # =====================================================

    if block_type == "buttons":

        _consume_buttons(
            block,
            state
        )

        return

    # =====================================================
    # MEDIA
    # =====================================================

    if (
        block_type
        in MEDIA_BLOCK_TYPES
    ):

        _consume_media_block(
            block,
            block_type,
            state
        )

        return

    # =====================================================
    # THINKING
    # =====================================================

    if block_type == "thinking":

        text, entities = (
            parse_rich_text(
                block.get(
                    "text"
                )
            )
        )

        if text:

            _append_main_text(
                state,
                text,
                entities
            )

        return


# =========================================================
# NORMALIZE NAVIGATION HINT
# =========================================================

def _normalize_navigation_hint(
    text: str
) -> str:

    value = (
        str(
            text
            or ""
        )
        .strip()
        .lower()
    )

    # Remove common UI emoji/symbol decoration around
    # navigation instructions.
    value = value.strip(
        " \t\r\n"
        "➡⬅👉👈"
        "🔽🔼✨⭐"
        "◀▶"
        "✅☑️"
        "🟢🔵"
    )

    return (
        " ".join(
            value.split()
        )
    )


# =========================================================
# REMOVE SLIDESHOW / COLLAGE UI HINT
# =========================================================

def _remove_rich_media_navigation_hint(
    state: _WalkState
) -> None:
    """
    Remove short standalone Rich Message navigation instructions
    such as 'ورق بزنید' when slideshow/collage media exists.

    This belongs to the Telegram input adapter because the phrase
    controls Telegram presentation rather than representing the
    editorial content itself.
    """

    if not (
        state.has_slideshow
        or state.has_collage
    ):

        return

    if not state.main_parts:

        return

    cleaned_parts: List[
        Tuple[
            str,
            List[
                Dict[str, Any]
            ]
        ]
    ] = []

    removed_count = 0

    for text, entities in (
        state.main_parts
    ):

        normalized = (
            _normalize_navigation_hint(
                text
            )
        )

        if (
            normalized
            in RICH_MEDIA_NAVIGATION_HINTS
            and len(
                normalized
            ) <= 40
        ):

            removed_count += 1

            continue

        cleaned_parts.append(
            (
                text,
                entities
            )
        )

    if removed_count:

        state.main_parts = (
            cleaned_parts
        )

        logger.info(
            "🧹 Rich media navigation hint removed | "
            f"count={removed_count}"
        )


# =========================================================
# BUILD MAIN TEXT + SHIFT ENTITIES
# =========================================================

def _assemble_main_text(
    state: _WalkState
) -> Tuple[
    str,
    List[
        Dict[str, Any]
    ]
]:

    output_parts: List[
        str
    ] = []

    output_entities: List[
        Dict[str, Any]
    ] = []

    current_offset = 0

    for (
        text,
        entities
    ) in (
        state.main_parts
    ):

        text = (
            _clean_text(
                text
            )
            .strip()
        )

        if not text:

            continue

        if output_parts:

            separator = "\n\n"

            output_parts.append(
                separator
            )

            current_offset += (
                _utf16_length(
                    separator
                )
            )

        output_parts.append(
            text
        )

        output_entities.extend(
            _shift_entities(
                entities,
                current_offset
            )
        )

        current_offset += (
            _utf16_length(
                text
            )
        )

    return (
        "".join(
            output_parts
        ),
        output_entities
    )


# =========================================================
# FILE DEDUPLICATION
# =========================================================

def _deduplicate_files(
    files: Iterable[
        Dict[str, Any]
    ]
) -> List[
    Dict[str, Any]
]:

    result: List[
        Dict[str, Any]
    ] = []

    seen: Set[
        Tuple[
            str,
            str
        ]
    ] = set()

    for item in (
        files
        or []
    ):

        if not isinstance(
            item,
            dict
        ):

            continue

        media_type = (
            str(
                item.get(
                    "type",
                    ""
                )
                or ""
            )
        )

        file_id = (
            str(
                item.get(
                    "file_id",
                    ""
                )
                or ""
            )
        )

        if not file_id:

            continue

        key = (
            media_type,
            file_id
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        result.append(
            dict(
                item
            )
        )

        if len(result) >= (
            MAX_RICH_MEDIA_ATTACHMENTS
        ):

            break

    return result


# =========================================================
# PUBLIC PARSER
# =========================================================

def parse_rich_message(
    rich_message: Any
) -> ParsedRichMessage:
    """
    Parse Telegram RichMessage object.

    Returns a transport-normalized ParsedRichMessage.

    This function is fail-soft:
        unknown/new Telegram blocks are logged and skipped or
        flattened where possible instead of rejecting the entire
        message.
    """

    result = (
        ParsedRichMessage()
    )

    if not isinstance(
        rich_message,
        dict
    ):

        return result

    state = (
        _WalkState()
    )

    result.is_rtl = bool(
        rich_message.get(
            "is_rtl",
            False
        )
    )

    blocks = (
        rich_message.get(
            "blocks"
        )
        or []
    )

    if not isinstance(
        blocks,
        list
    ):

        logger.warning(
            "⚠️ Telegram rich_message.blocks is not a list"
        )

        return result

    for block in blocks:

        _walk_block(
            block,
            state,
            depth=1
        )

        if state.block_count >= (
            MAX_RICH_BLOCKS
        ):

            break

    # -----------------------------------------------------
    # Telegram UI-only navigation text must not enter
    # the shared editorial/publication content.
    # -----------------------------------------------------

    _remove_rich_media_navigation_hint(
        state
    )

    main_text, entities = (
        _assemble_main_text(
            state
        )
    )

    utf8_size = len(
        main_text.encode(
            "utf-8"
        )
    )

    if utf8_size > (
        MAX_RICH_TEXT_UTF8_BYTES
    ):

        logger.warning(
            "⚠️ Parsed Rich Message exceeds documented "
            "Telegram text limit | "
            f"bytes={utf8_size} | "
            f"limit={MAX_RICH_TEXT_UTF8_BYTES}"
        )

    result.main_text = (
        main_text
    )

    result.other_entities = (
        entities
    )

    result.blockquote_blocks = (
        list(
            state.blockquote_blocks
        )
    )

    result.expandable_blocks = (
        list(
            state.expandable_blocks
        )
    )

    result.files = (
        _deduplicate_files(
            state.files
        )
    )

    result.unsupported_blocks = (
        sorted(
            state.unsupported_blocks
        )
    )

    result.block_count = (
        state.block_count
    )

    result.max_depth_seen = (
        state.max_depth_seen
    )

    result.has_slideshow = (
        state.has_slideshow
    )

    result.has_collage = (
        state.has_collage
    )

    result.raw_block_types = (
        list(
            state.raw_block_types
        )
    )

    logger.info(
        "🧩 Telegram Rich Message parsed | "
        f"text={len(result.main_text)} | "
        f"files={len(result.files)} | "
        f"blockquote={len(result.blockquote_blocks)} | "
        f"expandable={len(result.expandable_blocks)} | "
        f"blocks={result.block_count} | "
        f"depth={result.max_depth_seen} | "
        f"slideshow={result.has_slideshow} | "
        f"collage={result.has_collage} | "
        f"unsupported={result.unsupported_blocks or '-'}"
    )

    return result


# =========================================================
# MESSAGE CONVENIENCE PARSER
# =========================================================

def parse_rich_message_from_message(
    message: Optional[
        Dict[str, Any]
    ]
) -> ParsedRichMessage:
    """
    Convenience wrapper for a complete Telegram Message.

    Does not modify the original message.
    """

    if not is_rich_message(
        message
    ):

        return (
            ParsedRichMessage()
        )

    return parse_rich_message(
        (
            message
            or {}
        ).get(
            "rich_message"
        )
    )
