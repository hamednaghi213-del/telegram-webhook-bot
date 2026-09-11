from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# =========================================================
# TRANSLATION UI
# =========================================================
#
# NEW FILE
#
# وظیفه:
# رابط عمومی ترجمه برای Shared Engine
#
# این فایل:
# - دکمه ترجمه می‌سازد
# - زبان مقصد را انتخاب می‌کند
# - زبان‌های بیشتر را صفحه‌بندی می‌کند
# - زبان دلخواه را پشتیبانی می‌کند
# - دکمه‌های Preview / Confirm / Edit / Cancel را می‌سازد
#
# هیچ پیام شبکه‌ای ارسال نمی‌کند.
# هیچ Publication فعلی را تغییر نمی‌دهد.
# Telegram / Bale / Workspace / Legacy مستقل هستند.
#
# =========================================================


TRANSLATION_CALLBACK_PREFIX = "tr"

ACTION_OPEN = "open"
ACTION_LANGUAGE = "lang"
ACTION_MORE = "more"
ACTION_CUSTOM = "custom"
ACTION_CONFIRM = "confirm"
ACTION_EDIT = "edit"
ACTION_CANCEL = "cancel"
ACTION_BACK = "back"
ACTION_ORIGINAL = "original"
ACTION_RETRANSLATE = "retranslate"
ACTION_RETRANSLATE_CONFIRM = "retryok"

DEFAULT_LANGUAGE_PAGE_SIZE = 8
MAX_LANGUAGE_PAGE_SIZE = 12
MAX_CALLBACK_LENGTH = 64


# =========================================================
# MODELS
# =========================================================

@dataclass(frozen=True)
class TranslationLanguage:
    code: str
    native_name: str
    english_name: str
    emoji: str = "🌐"
    rtl: bool = False
    popular: bool = False


@dataclass(frozen=True)
class TranslationButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class TranslationCallback:
    valid: bool
    action: str = ""
    value: str = ""
    page: int = 0
    raw: str = ""


TranslationKeyboard = List[List[TranslationButton]]


# =========================================================
# LANGUAGE REGISTRY
# =========================================================
#
# این لیست فقط Shortcut رابط کاربری است.
# موتور ترجمه محدود به این زبان‌ها نیست.
# زبان دلخواه برای سایر زبان‌ها وجود دارد.
#
# =========================================================

LANGUAGES: Tuple[TranslationLanguage, ...] = (
    TranslationLanguage(
        code="fa",
        native_name="فارسی",
        english_name="Persian",
        emoji="🇮🇷",
        rtl=True,
        popular=True,
    ),
    TranslationLanguage(
        code="en",
        native_name="English",
        english_name="English",
        emoji="🇬🇧",
        popular=True,
    ),
    TranslationLanguage(
        code="ar",
        native_name="العربية",
        english_name="Arabic",
        emoji="🇸🇦",
        rtl=True,
        popular=True,
    ),
    TranslationLanguage(
        code="tr",
        native_name="Türkçe",
        english_name="Turkish",
        emoji="🇹🇷",
        popular=True,
    ),
    TranslationLanguage(
        code="ru",
        native_name="Русский",
        english_name="Russian",
        emoji="🇷🇺",
        popular=True,
    ),
    TranslationLanguage(
        code="fr",
        native_name="Français",
        english_name="French",
        emoji="🇫🇷",
        popular=True,
    ),
    TranslationLanguage(
        code="de",
        native_name="Deutsch",
        english_name="German",
        emoji="🇩🇪",
        popular=True,
    ),
    TranslationLanguage(
        code="es",
        native_name="Español",
        english_name="Spanish",
        emoji="🇪🇸",
        popular=True,
    ),
    TranslationLanguage(
        code="zh",
        native_name="中文",
        english_name="Chinese",
        emoji="🇨🇳",
        popular=True,
    ),
    TranslationLanguage(
        code="it",
        native_name="Italiano",
        english_name="Italian",
        emoji="🇮🇹",
    ),
    TranslationLanguage(
        code="pt",
        native_name="Português",
        english_name="Portuguese",
        emoji="🇵🇹",
    ),
    TranslationLanguage(
        code="ja",
        native_name="日本語",
        english_name="Japanese",
        emoji="🇯🇵",
    ),
    TranslationLanguage(
        code="ko",
        native_name="한국어",
        english_name="Korean",
        emoji="🇰🇷",
    ),
    TranslationLanguage(
        code="hi",
        native_name="हिन्दी",
        english_name="Hindi",
        emoji="🇮🇳",
    ),
    TranslationLanguage(
        code="ur",
        native_name="اردو",
        english_name="Urdu",
        emoji="🇵🇰",
        rtl=True,
    ),
    TranslationLanguage(
        code="az",
        native_name="Azərbaycan",
        english_name="Azerbaijani",
        emoji="🇦🇿",
    ),
    TranslationLanguage(
        code="hy",
        native_name="Հայերեն",
        english_name="Armenian",
        emoji="🇦🇲",
    ),
    TranslationLanguage(
        code="ka",
        native_name="ქართული",
        english_name="Georgian",
        emoji="🇬🇪",
    ),
    TranslationLanguage(
        code="he",
        native_name="עברית",
        english_name="Hebrew",
        emoji="🇮🇱",
        rtl=True,
    ),
    TranslationLanguage(
        code="el",
        native_name="Ελληνικά",
        english_name="Greek",
        emoji="🇬🇷",
    ),
    TranslationLanguage(
        code="nl",
        native_name="Nederlands",
        english_name="Dutch",
        emoji="🇳🇱",
    ),
    TranslationLanguage(
        code="sv",
        native_name="Svenska",
        english_name="Swedish",
        emoji="🇸🇪",
    ),
    TranslationLanguage(
        code="pl",
        native_name="Polski",
        english_name="Polish",
        emoji="🇵🇱",
    ),
    TranslationLanguage(
        code="uk",
        native_name="Українська",
        english_name="Ukrainian",
        emoji="🇺🇦",
    ),
    TranslationLanguage(
        code="id",
        native_name="Bahasa Indonesia",
        english_name="Indonesian",
        emoji="🇮🇩",
    ),
    TranslationLanguage(
        code="ms",
        native_name="Bahasa Melayu",
        english_name="Malay",
        emoji="🇲🇾",
    ),
    TranslationLanguage(
        code="th",
        native_name="ไทย",
        english_name="Thai",
        emoji="🇹🇭",
    ),
    TranslationLanguage(
        code="vi",
        native_name="Tiếng Việt",
        english_name="Vietnamese",
        emoji="🇻🇳",
    ),
)


LANGUAGE_BY_CODE: Dict[str, TranslationLanguage] = {
    language.code: language
    for language in LANGUAGES
}


# =========================================================
# CALLBACK HELPERS
# =========================================================

def _sanitize_callback_value(
    value: Optional[str]
) -> str:
    if value is None:
        return ""

    value = str(value).strip()

    value = value.replace(
        ":",
        "_",
    )

    value = re.sub(
        r"\s+",
        "_",
        value,
    )

    return value


def build_translation_callback(
    action: str,
    value: Optional[str] = None,
) -> str:
    action = _sanitize_callback_value(
        action
    )

    value = _sanitize_callback_value(
        value
    )

    if value:
        callback = (
            f"{TRANSLATION_CALLBACK_PREFIX}:"
            f"{action}:"
            f"{value}"
        )
    else:
        callback = (
            f"{TRANSLATION_CALLBACK_PREFIX}:"
            f"{action}"
        )

    if len(
        callback.encode("utf-8")
    ) > MAX_CALLBACK_LENGTH:
        raise ValueError(
            "translation callback_data exceeds Telegram limit"
        )

    return callback


def parse_translation_callback(
    callback_data: Optional[str]
) -> TranslationCallback:
    raw = str(
        callback_data or ""
    ).strip()

    if not raw:
        return TranslationCallback(
            valid=False,
            raw=raw,
        )

    parts = raw.split(":")

    if len(parts) < 2:
        return TranslationCallback(
            valid=False,
            raw=raw,
        )

    if parts[0] != TRANSLATION_CALLBACK_PREFIX:
        return TranslationCallback(
            valid=False,
            raw=raw,
        )

    action = parts[1].strip()

    value = ""

    if len(parts) >= 3:
        value = parts[2].strip()

    page = 0

    if action == ACTION_MORE:
        try:
            page = max(
                0,
                int(value or 0),
            )
        except (
            TypeError,
            ValueError,
        ):
            page = 0

    return TranslationCallback(
        valid=True,
        action=action,
        value=value,
        page=page,
        raw=raw,
    )


# =========================================================
# LANGUAGE HELPERS
# =========================================================

def get_language(
    code: Optional[str]
) -> Optional[TranslationLanguage]:
    normalized = (
        str(code or "")
        .strip()
        .lower()
    )

    return LANGUAGE_BY_CODE.get(
        normalized
    )


def language_display_name(
    language: TranslationLanguage
) -> str:
    return (
        f"{language.emoji} "
        f"{language.native_name}"
    )


def get_popular_languages() -> List[TranslationLanguage]:
    return [
        language
        for language in LANGUAGES
        if language.popular
    ]


def get_other_languages() -> List[TranslationLanguage]:
    return [
        language
        for language in LANGUAGES
        if not language.popular
    ]


# =========================================================
# TELEGRAM MARKUP CONVERTER
# =========================================================

def keyboard_to_telegram_markup(
    keyboard: TranslationKeyboard
) -> Dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": button.text,
                    "callback_data": button.callback_data,
                }
                for button in row
            ]
            for row in keyboard
        ]
    }


# =========================================================
# MAIN TRANSLATE BUTTON
# =========================================================

def build_translate_button() -> TranslationButton:
    return TranslationButton(
        text="🌐 ترجمه",
        callback_data=(
            build_translation_callback(
                ACTION_OPEN
            )
        ),
    )


def build_translate_keyboard() -> TranslationKeyboard:
    return [
        [
            build_translate_button()
        ]
    ]


# =========================================================
# LANGUAGE BUTTON
# =========================================================

def _language_button(
    language: TranslationLanguage
) -> TranslationButton:
    return TranslationButton(
        text=language_display_name(
            language
        ),
        callback_data=(
            build_translation_callback(
                ACTION_LANGUAGE,
                language.code,
            )
        ),
    )


# =========================================================
# MAIN LANGUAGE MENU
# =========================================================

def build_language_keyboard(
    *,
    include_custom: bool = True,
    include_cancel: bool = True,
) -> TranslationKeyboard:
    languages = get_popular_languages()

    keyboard: TranslationKeyboard = []

    for index in range(
        0,
        len(languages),
        2,
    ):
        row = [
            _language_button(
                languages[index]
            )
        ]

        if index + 1 < len(languages):
            row.append(
                _language_button(
                    languages[index + 1]
                )
            )

        keyboard.append(row)

    keyboard.append(
        [
            TranslationButton(
                text="🌍 زبان‌های بیشتر",
                callback_data=(
                    build_translation_callback(
                        ACTION_MORE,
                        "0",
                    )
                ),
            )
        ]
    )

    if include_custom:
        keyboard.append(
            [
                TranslationButton(
                    text="✍️ زبان دلخواه",
                    callback_data=(
                        build_translation_callback(
                            ACTION_CUSTOM
                        )
                    ),
                )
            ]
        )

    if include_cancel:
        keyboard.append(
            [
                TranslationButton(
                    text="❌ لغو",
                    callback_data=(
                        build_translation_callback(
                            ACTION_CANCEL
                        )
                    ),
                )
            ]
        )

    return keyboard


# =========================================================
# MORE LANGUAGES
# =========================================================

def build_more_languages_keyboard(
    page: int = 0,
    *,
    page_size: int = DEFAULT_LANGUAGE_PAGE_SIZE,
) -> TranslationKeyboard:
    try:
        page = max(
            0,
            int(page),
        )
    except (
        TypeError,
        ValueError,
    ):
        page = 0

    try:
        page_size = int(
            page_size
        )
    except (
        TypeError,
        ValueError,
    ):
        page_size = DEFAULT_LANGUAGE_PAGE_SIZE

    page_size = max(
        2,
        min(
            page_size,
            MAX_LANGUAGE_PAGE_SIZE,
        ),
    )

    languages = get_other_languages()

    total = len(languages)

    start = page * page_size

    if start >= total and page > 0:
        page = 0
        start = 0

    end = min(
        start + page_size,
        total,
    )

    current = languages[
        start:end
    ]

    keyboard: TranslationKeyboard = []

    for index in range(
        0,
        len(current),
        2,
    ):
        row = [
            _language_button(
                current[index]
            )
        ]

        if index + 1 < len(current):
            row.append(
                _language_button(
                    current[index + 1]
                )
            )

        keyboard.append(row)

    navigation: List[TranslationButton] = []

    if page > 0:
        navigation.append(
            TranslationButton(
                text="⬅️ قبلی",
                callback_data=(
                    build_translation_callback(
                        ACTION_MORE,
                        str(page - 1),
                    )
                ),
            )
        )

    if end < total:
        navigation.append(
            TranslationButton(
                text="بعدی ➡️",
                callback_data=(
                    build_translation_callback(
                        ACTION_MORE,
                        str(page + 1),
                    )
                ),
            )
        )

    if navigation:
        keyboard.append(
            navigation
        )

    keyboard.append(
        [
            TranslationButton(
                text="✍️ زبان دلخواه",
                callback_data=(
                    build_translation_callback(
                        ACTION_CUSTOM
                    )
                ),
            )
        ]
    )

    keyboard.append(
        [
            TranslationButton(
                text="🔙 بازگشت",
                callback_data=(
                    build_translation_callback(
                        ACTION_BACK
                    )
                ),
            ),
            TranslationButton(
                text="❌ لغو",
                callback_data=(
                    build_translation_callback(
                        ACTION_CANCEL
                    )
                ),
            ),
        ]
    )

    return keyboard


# =========================================================
# PREVIEW ACTIONS
# =========================================================

def build_translation_preview_keyboard(review_id: str) -> TranslationKeyboard:
    return [
        [TranslationButton(text="🔄 ترجمه مجدد", callback_data=build_translation_callback(ACTION_RETRANSLATE, review_id))],
        [
            TranslationButton(
                text="✅ تأیید و انتشار",
                callback_data=(
                    build_translation_callback(
                        ACTION_CONFIRM, review_id
                    )
                ),
            )
        ],
        [
            TranslationButton(
                text="✏️ اصلاح ترجمه",
                callback_data=(
                    build_translation_callback(
                        ACTION_EDIT, review_id
                    )
                ),
            ),
            TranslationButton(
                text="📄 متن اصلی",
                callback_data=(
                    build_translation_callback(
                        ACTION_ORIGINAL, review_id
                    )
                ),
            ),
        ],
        [
            TranslationButton(
                text="❌ لغو",
                callback_data=(
                    build_translation_callback(
                        ACTION_CANCEL, review_id
                    )
                ),
            )
        ],
    ]


# =========================================================
# DISPLAY TEXTS
# =========================================================

def build_language_selection_text() -> str:
    return (
        "🌐 ترجمه هوشمند\n\n"
        "زبان مقصد را انتخاب کنید.\n\n"
        "زبان متن اصلی به‌صورت خودکار تشخیص داده می‌شود "
        "و ترجمه با حفظ مفهوم، نام‌ها، اعداد، لینک‌ها "
        "و ساختار محتوا انجام خواهد شد."
    )


def build_more_languages_text(
    page: int = 0
) -> str:
    return (
        "🌍 زبان‌های بیشتر\n\n"
        f"صفحه {page + 1}\n\n"
        "زبان مقصد را انتخاب کنید یا از گزینه "
        "«زبان دلخواه» استفاده کنید."
    )


def build_custom_language_prompt() -> str:
    return (
        "✍️ نام زبان مقصد را ارسال کنید.\n\n"
        "مثال:\n"
        "English\n"
        "فارسی\n"
        "العربية\n"
        "Türkçe\n"
        "French\n"
        "Japanese\n\n"
        "ترجمه محدود به زبان‌های داخل منو نیست."
    )


def build_translation_started_text(
    target_language: str
) -> str:
    return (
        "🌐 ترجمه در حال آماده‌سازی است...\n\n"
        f"زبان مقصد: {target_language}"
    )


def build_translation_failed_text(
    reason: Optional[str] = None
) -> str:
    text = (
        "❌ ترجمه با اطمینان کافی انجام نشد.\n\n"
        "متن اصلی بدون تغییر باقی مانده است."
    )

    if reason:
        text += (
            "\n\n"
            f"کد خطا: {reason}"
        )

    return text


def build_translation_preview_text(
    target_language: str
) -> str:
    return (
        "🌐 پیش‌نمایش ترجمه\n\n"
        f"زبان مقصد: {target_language}\n\n"
        "متن ترجمه‌شده را بررسی کنید و سپس "
        "تأیید، اصلاح یا لغو را انتخاب کنید."
    )


# =========================================================
# CALLBACK CHECK
# =========================================================

def is_translation_callback(
    callback_data: Optional[str]
) -> bool:
    raw = str(
        callback_data or ""
    ).strip()

    return raw.startswith(
        f"{TRANSLATION_CALLBACK_PREFIX}:"
    )
