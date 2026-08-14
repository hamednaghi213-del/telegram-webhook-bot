import logging
import html
import bisect
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


# =========================================================
# TELEGRAM ENTITY PARSER
# =========================================================

def parse_telegram_entities(
    text: str,
    entities: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    پردازش Entityهای دریافتی از Telegram.

    Telegram offset و length را بر اساس UTF-16
    ارسال می‌کند، بنابراین برای متن فارسی و ایموجی
    باید تبدیل UTF-16 به index پایتون به‌درستی انجام شود.

    خروجی:

    {
        "main_text": "...",
        "expandable_blocks": [
            {
                "type": "expandable_blockquote",
                "text": "..."
            }
        ],
        "other_entities": [...]
    }
    
    Args:
        text: متن اصلی از Telegram
        entities: لیست entities با offset/length/type
        
    Returns:
        Dict شامل main_text, expandable_blocks, other_entities
    """

    if not text:
        logger.debug("Empty text received")
        return {
            "main_text": "",
            "expandable_blocks": [],
            "other_entities": []
        }

    if not entities:
        logger.info(f"No entities, returning full text: {len(text)} chars")
        return {
            "main_text": text,
            "expandable_blocks": [],
            "other_entities": []
        }

    try:
        # -------------------------------------------------
        # ساخت جدول تبدیل UTF-16 offset به Python index
        # -------------------------------------------------

        utf16_positions = []
        current_position = 0

        for char in text:
            utf16_positions.append(current_position)
            current_position += len(char.encode("utf-16-le")) // 2

        # موقعیت انتهای متن
        utf16_positions.append(current_position)
        
        logger.info(
            f"📊 UTF-16 mapping created: "
            f"{len(text)} chars → {current_position} UTF-16 units"
        )

        def utf16_to_python_index(offset: int) -> int:
            """
            تبدیل offset مبتنی بر UTF-16 به index پایتون.
            """
            if offset <= 0:
                return 0

            if offset >= current_position:
                return len(text)

            # Binary Search برای بهینه‌سازی (O(log n) instead of O(n))
            idx = bisect.bisect_left(utf16_positions, offset)
            return min(idx, len(text))

        # -------------------------------------------------
        # مرتب‌سازی Entityها
        # -------------------------------------------------

        sorted_entities = sorted(
            entities,
            key=lambda entity: (
                entity.get("offset", 0),
                entity.get("length", 0)
            )
        )
        
        logger.info(f"🔍 Processing {len(sorted_entities)} entities")

        main_parts = []
        expandable_blocks = []
        other_entities = []

        last_python_end = 0

        # -------------------------------------------------
        # پردازش Entityها
        # -------------------------------------------------

        for entity in sorted_entities:

            entity_type = entity.get("type", "")
            offset = entity.get("offset", 0)
            length = entity.get("length", 0)

            if length <= 0:
                logger.debug(f"⏭️ Skipping entity with length={length}")
                continue

            start = utf16_to_python_index(offset)
            end = utf16_to_python_index(offset + length)

            # جلوگیری از محدوده نامعتبر
            start = max(0, min(start, len(text)))
            end = max(start, min(end, len(text)))

            # -----------------------------------------
            # Entityهایی که قبل از Entity فعلی هستند
            # -----------------------------------------

            if start > last_python_end:
                main_parts.append(text[last_python_end:start])

            entity_text = text[start:end]
            
            logger.debug(
                f"Entity: type={entity_type}, "
                f"text={entity_text[:30] if len(entity_text) > 30 else entity_text}..."
            )

            # -----------------------------------------
            # Blockquote
            # -----------------------------------------

            if entity_type in ("blockquote", "expandable_blockquote"):

                expandable_blocks.append({
                    "type": entity_type,
                    "text": entity_text
                })

            # -----------------------------------------
            # سایر Entityها
            # -----------------------------------------

            else:

                other_entities.append({
                    "type": entity_type,
                    "offset": offset,
                    "length": length,
                    "text": entity_text
                })

                # فعلاً Entityهای دیگر را از متن حذف نمی‌کنیم
                main_parts.append(entity_text)

            last_python_end = max(last_python_end, end)

        # -------------------------------------------------
        # متن بعد از آخرین Entity
        # -------------------------------------------------

        if last_python_end < len(text):
            main_parts.append(text[last_python_end:])

        main_text = "".join(main_parts).strip()
        
        logger.info(
            f"✅ Parsed: {len(main_text)} main chars, "
            f"{len(expandable_blocks)} blocks, "
            f"{len(other_entities)} entities"
        )

        return {
            "main_text": main_text,
            "expandable_blocks": expandable_blocks,
            "other_entities": other_entities
        }
        
    except Exception as e:
        logger.exception(f"❌ Error parsing entities: {e}")
        return {
            "main_text": text,
            "expandable_blocks": [],
            "other_entities": []
        }


# =========================================================
# HTML ESCAPE
# =========================================================

def escape_html(text: str) -> str:
    """
    Escape کردن کاراکترهای HTML برای استفاده
    امن در Telegram parse_mode=HTML.
    
    Args:
        text: متن برای escape
        
    Returns:
        Escaped HTML string
    """

    if not text:
        return ""

    try:
        escaped = html.escape(str(text), quote=True)
        logger.debug(f"Escaped: {len(text)} → {len(escaped)} chars")
        return escaped
    except Exception as e:
        logger.error(f"❌ HTML escape failed: {e}")
        return str(text)


# =========================================================
# BUILD BLOCKQUOTE HTML
# =========================================================

def build_blockquote_html(
    text: str,
    expandable: bool = False
) -> str:
    """
    تبدیل متن Blockquote به HTML قابل ارسال
    به Telegram.

    expandable=False:
        <blockquote>...</blockquote>

    expandable=True:
        <blockquote expandable>...</blockquote>
        
    Args:
        text: متن blockquote
        expandable: آیا قابل بسط باشد
        
    Returns:
        HTML String
    """

    if not text:
        return ""

    try:
        escaped_text = escape_html(text)

        if expandable:
            result = (
                f"<blockquote expandable>"
                f"{escaped_text}"
                f"</blockquote>"
            )
            logger.debug(f"✅ Built expandable blockquote: {len(result)} chars")
        else:
            result = (
                f"<blockquote>"
                f"{escaped_text}"
                f"</blockquote>"
            )
            logger.debug(f"✅ Built blockquote: {len(result)} chars")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Failed to build blockquote: {e}")
        return escape_html(text)


# =========================================================
# BUILD ENTITY HTML
# =========================================================

def build_entity_html(
    entity_type: str,
    text: str,
    extra_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    تبدیل Entityهای مختلف به HTML برای Telegram.
    
    Args:
        entity_type: نوع Entity (bold, italic, text_link, etc.)
        text: محتوای Entity
        extra_data: اطلاعات اضافی (مثل URL برای text_link)
    
    Returns:
        HTML String آماده برای Telegram
        
    Raises:
        ValueError: اگر entity_type نامعتبر باشد
        
    Examples:
        >>> build_entity_html("bold", "سلام")
        '<b>سلام</b>'
        
        >>> build_entity_html("text_link", "لینک", {"url": "https://example.com"})
        '<a href="https://example.com">لینک</a>'
    """
    
    extra_data = extra_data or {}
    
    # ====================================================
    # Input Validation
    # ====================================================
    
    if not text:
        logger.warning(f"Empty text for entity type: {entity_type}")
        return ""
    
    if not entity_type:
        logger.error("Entity type is required")
        raise ValueError("entity_type cannot be empty")
    
    # ====================================================
    # HTML Escape
    # ====================================================
    
    try:
        escaped_text = escape_html(text)
    except Exception as e:
        logger.error(f"❌ HTML escape failed: {e}")
        escaped_text = str(text)
    
    # ====================================================
    # Entity Type Mapping
    # ====================================================
    
    entity_type = entity_type.lower().strip()
    
    try:
        # Simple Formatting
        if entity_type == "bold":
            result = f"<b>{escaped_text}</b>"
            logger.debug(f"✅ Built bold: {len(result)} chars")
            return result
        
        elif entity_type == "italic":
            result = f"<i>{escaped_text}</i>"
            logger.debug(f"✅ Built italic: {len(result)} chars")
            return result
        
        elif entity_type == "underline":
            result = f"<u>{escaped_text}</u>"
            logger.debug(f"✅ Built underline: {len(result)} chars")
            return result
        
        elif entity_type == "strikethrough":
            result = f"<s>{escaped_text}</s>"
            logger.debug(f"✅ Built strikethrough: {len(result)} chars")
            return result
        
        elif entity_type == "spoiler":
            result = f'<span class="tg-spoiler">{escaped_text}</span>'
            logger.debug(f"✅ Built spoiler: {len(result)} chars")
            return result
        
        elif entity_type == "code":
            result = f"<code>{escaped_text}</code>"
            logger.debug(f"✅ Built code: {len(result)} chars")
            return result
        
        elif entity_type == "pre":
            result = build_pre_html(text, extra_data.get("language"))
            return result
        
        # ====================================================
        # Complex Formatting (require extra data)
        # ====================================================
        
        elif entity_type == "text_link":
            url = extra_data.get("url")
            
            if not url:
                logger.warning(f"text_link missing URL, returning escaped text")
                return escaped_text
            
            # Escape URL
            try:
                escaped_url = escape_html(url)
            except Exception as e:
                logger.error(f"❌ Failed to escape URL: {e}")
                escaped_url = str(url)
            
            result = f'<a href="{escaped_url}">{escaped_text}</a>'
            logger.debug(f"✅ Built text_link: {len(result)} chars")
            return result
        
        elif entity_type == "text_mention":
            user_id = extra_data.get("user_id")
            
            if not user_id:
                logger.warning(f"text_mention missing user_id, returning escaped text")
                return escaped_text
            
            # Telegram User Mention Format
            result = f'<a href="tg://user?id={user_id}">{escaped_text}</a>'
            logger.debug(f"✅ Built text_mention: {len(result)} chars")
            return result
        
        elif entity_type == "email":
            # Email links
            try:
                escaped_email = escape_html(text)
            except Exception as e:
                logger.error(f"❌ Failed to escape email: {e}")
                escaped_email = str(text)
            
            result = f'<a href="mailto:{escaped_email}">{escaped_text}</a>'
            logger.debug(f"✅ Built email: {len(result)} chars")
            return result
        
        elif entity_type == "url":
            # URL links
            try:
                escaped_url = escape_html(text)
            except Exception as e:
                logger.error(f"❌ Failed to escape URL: {e}")
                escaped_url = str(text)
            
            result = f'<a href="{escaped_url}">{escaped_url}</a>'
            logger.debug(f"✅ Built url: {len(result)} chars")
            return result
        
        else:
            logger.error(f"❌ Unknown entity type: {entity_type}")
            raise ValueError(f"Unknown entity type: {entity_type}")
    
    except ValueError as e:
        logger.error(f"❌ ValueError in build_entity_html: {e}")
        raise
    
    except Exception as e:
        logger.exception(f"❌ Unexpected error in build_entity_html: {e}")
        # Fallback: return escaped text
        return escaped_text


# =========================================================
# BUILD PRE CODE BLOCK
# =========================================================

def build_pre_html(
    text: str,
    language: Optional[str] = None
) -> str:
    """
    تبدیل کد block به HTML.
    
    Telegram از دو فرمت پشتیبانی می‌کند:
    1. ساده: <pre>...</pre>
    2. با syntax highlighting: <pre><code class="language-python">...</code></pre>
    
    Args:
        text: متن کد
        language: نوع زبان (python, javascript, etc.)
    
    Returns:
        HTML String
        
    Examples:
        >>> build_pre_html("print('hello')")
        '<pre>print(\'hello\')</pre>'
        
        >>> build_pre_html("print('hello')", "python")
        '<pre><code class="language-python">print(\'hello\')</code></pre>'
    """
    
    try:
        escaped_text = escape_html(text)
    except Exception as e:
        logger.error(f"❌ Failed to escape pre text: {e}")
        escaped_text = str(text)
    
    # Validate language
    if language:
        language = str(language).lower().strip()
        # Whitelist برای زبان‌های معروف
        valid_languages = {
            "python", "js", "javascript", "html", "css",
            "java", "c", "cpp", "csharp", "php", "ruby",
            "go", "rust", "kotlin", "swift", "bash", "sql",
            "json", "xml", "yaml", "markdown", "plaintext",
            "perl", "lua", "r", "scala", "groovy", "clojure"
        }
        
        if language not in valid_languages:
            logger.warning(
                f"⚠️ Unknown language: {language}, "
                f"using plaintext"
            )
            language = None
    
    if language:
        result = (
            f'<pre><code class="language-{language}">'
            f'{escaped_text}'
            f'</code></pre>'
        )
        logger.debug(
            f"✅ Built pre with language={language}: {len(result)} chars"
        )
    else:
        result = f"<pre>{escaped_text}</pre>"
        logger.debug(f"✅ Built plain pre: {len(result)} chars")
    
    return result


# =========================================================
# HELPER: Build Main Text HTML
# =========================================================

def _build_main_text_html(
    text: str,
    entities: List[Dict[str, Any]]
) -> str:
    """
    ساخت HTML برای متن اصل�� با entities.
    
    این تابع entities را دوباره بر روی متن اصلی اعمال می‌کند
    چون parse_telegram_entities آن‌ها را استخراج کرده است.
    
    Args:
        text: متن اصلی
        entities: لیست entities با offset/length/type
        
    Returns:
        HTML String
    """
    
    if not entities:
        logger.debug("No entities to apply")
        return escape_html(text)
    
    try:
        # مرتب‌سازی entities بر اساس offset
        sorted_entities = sorted(
            entities,
            key=lambda e: e.get("offset", 0)
        )
        
        html_parts = []
        last_end = 0
        
        for entity in sorted_entities:
            offset = entity.get("offset", 0)
            length = entity.get("length", 0)
            entity_type = entity.get("type", "")
            
            if length <= 0:
                continue
            
            # Text قبل از entity
            if offset > last_end:
                before_text = text[last_end:offset]
                html_parts.append(escape_html(before_text))
            
            # Entity متن
            entity_text = text[offset:offset + length]
            
            try:
                # اطلاعات اضافی (مثل URL)
                extra_data = {
                    k: v for k, v in entity.items()
                    if k not in ("type", "offset", "length")
                }
                
                entity_html = build_entity_html(
                    entity_type,
                    entity_text,
                    extra_data if extra_data else None
                )
                
                html_parts.append(entity_html)
                logger.debug(
                    f"Applied entity: type={entity_type}, "
                    f"offset={offset}, length={length}"
                )
                
            except Exception as e:
                logger.error(
                    f"❌ Failed to apply entity {entity_type}: {e}"
                )
                # Fallback: escaped text
                html_parts.append(escape_html(entity_text))
            
            last_end = offset + length
        
        # متن بعد از آخرین entity
        if last_end < len(text):
            remaining = text[last_end:]
            html_parts.append(escape_html(remaining))
        
        result = "".join(html_parts)
        logger.debug(f"✅ Main text HTML: {len(result)} chars")
        
        return result
        
    except Exception as e:
        logger.exception(f"❌ Error building main text HTML: {e}")
        return escape_html(text)


# =========================================================
# FULL HTML BUILDER
# =========================================================

def build_full_html(
    text: str,
    entities: Optional[List[Dict[str, Any]]] = None,
    include_blockquotes: bool = True
) -> str:
    """
    تبدیل کامل متن + entities به HTML قابل ارسال به Telegram.
    
    این تابع:
    1. متن را parse می‌کند
    2. Blockquote‌ها را استخراج می‌کند
    3. سایر entities را format می‌کند
    4. همه را ترکیب می‌کند
    
    Args:
        text: متن اصلی از Telegram
        entities: لیست entities از Telegram (offset/length/type)
        include_blockquotes: آیا blockquote‌ها شامل شود؟
    
    Returns:
        HTML String آماده برای ارسال
        
    Examples:
        >>> text = "سلام دنیا"
        >>> entities = [
        ...     {"type": "bold", "offset": 0, "length": 4}
        ... ]
        >>> build_full_html(text, entities)
        '<b>سلام</b> دنیا'
    """
    
    logger.info(
        f"🔨 Building full HTML: {len(text)} chars, "
        f"{len(entities or [])} entities"
    )
    
    if not text:
        logger.warning("Empty text in build_full_html")
        return ""
    
    try:
        # ====================================================
        # Parse Entities
        # ====================================================
        
        parsed = parse_telegram_entities(text, entities)
        logger.info(
            f"📊 Parsed: main={len(parsed['main_text'])} chars, "
            f"blocks={len(parsed['expandable_blocks'])}, "
            f"entities={len(parsed['other_entities'])}"
        )
        
        # ====================================================
        # Build Main HTML with Entities
        # ====================================================
        
        main_html = _build_main_text_html(
            text,
            parsed.get("other_entities", [])
        )
        
        logger.info(f"📝 Main HTML: {len(main_html)} chars")
        
        # ====================================================
        # Build Blockquotes
        # ====================================================
        
        blockquote_html = ""
        
        if include_blockquotes and parsed.get("expandable_blocks"):
            blockquote_parts = []
            
            for block in parsed["expandable_blocks"]:
                block_type = block.get("type", "blockquote")
                block_text = block.get("text", "")
                
                is_expandable = (
                    block_type == "expandable_blockquote"
                )
                
                try:
                    html_block = build_blockquote_html(
                        block_text,
                        expandable=is_expandable
                    )
                    
                    blockquote_parts.append(html_block)
                    logger.debug(
                        f"✅ Built blockquote: {len(html_block)} chars"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Failed to build blockquote: {e}")
                    continue
            
            if blockquote_parts:
                blockquote_html = "\n\n" + "\n\n".join(blockquote_parts)
                logger.info(f"📦 Blockquotes: {len(blockquote_html)} chars")
        
        # ====================================================
        # Combine
        # ====================================================
        
        result = main_html + blockquote_html
        logger.info(f"✅ Full HTML built: {len(result)} chars")
        
        return result
    
    except Exception as e:
        logger.exception(f"❌ Error in build_full_html: {e}")
        # Fallback: return escaped text
        return escape_html(text)


# =========================================================
# Integration Tests
# =========================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s - %(message)s"
    )
    
    print("🧪 Testing Content Entities Functions:\n")
    
    # Test 1: Simple text with bold
    test1_text = "سلام دنیا"
    test1_entities = [
        {"type": "bold", "offset": 0, "length": 4}
    ]
    
    result1 = build_full_html(test1_text, test1_entities)
    print(f"Test 1 (Bold):\n  Input:  {test1_text}\n  Output: {result1}\n")
    
    # Test 2: Text with blockquote
    test2_text = "این یک نقل قول است"
    test2_entities = [
        {"type": "expandable_blockquote", "offset": 0, "length": 18}
    ]
    
    result2 = build_full_html(test2_text, test2_entities)
    print(f"Test 2 (Blockquote):\n  Input:  {test2_text}\n  Output: {result2}\n")
    
    # Test 3: Code block with language
    test3_text = 'print("hello")'
    result3 = build_pre_html(test3_text, "python")
    print(f"Test 3 (Pre with language):\n  Input:  {test3_text}\n  Output: {result3}\n")
    
    # Test 4: Mixed entities
    test4_text = "این یک تست است"
    test4_entities = [
        {"type": "bold", "offset": 0, "length": 3},
        {"type": "italic", "offset": 8, "length": 4}
    ]
    
    result4 = build_full_html(test4_text, test4_entities)
    print(f"Test 4 (Mixed):\n  Input:  {test4_text}\n  Output: {result4}\n")
    
    # Test 5: Text link
    result5 = build_entity_html(
        "text_link",
        "کلیک کنید",
        {"url": "https://example.com"}
    )
    print(f"Test 5 (Text Link):\n  Output: {result5}\n")
    
    print("✅ All tests completed!")
