import logging
import sys

from core.ai_summarizer_provider import (
    gemini_provider_configured,
    get_gemini_model,
    summarize_with_gemini,
)

from core.smart_summarizer import (
    summarize_text_safely,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(levelname)s - "
        "%(message)s"
    )
)

logger = logging.getLogger(
    __name__
)


# =========================================================
# LIVE TEST TEXT
#
# عمداً دارای:
# - نسبت دادن خبر
# - احتمال
# - عدد
# - اطلاعات قابل حذف
#
# است تا Validator را واقعاً تست کنیم.
# =========================================================

TEST_TEXT = (
    "وزیر خارجه گفت احتمال دارد مذاکرات سیاسی "
    "در هفته آینده از سر گرفته شود. "
    "او تأکید کرد هنوز تصمیم نهایی درباره زمان "
    "و محل مذاکرات اتخاذ نشده است. "
    "به گفته وزیر خارجه، رایزنی‌های دیپلماتیک "
    "در روزهای اخیر ادامه داشته و چند پیشنهاد "
    "میان طرف‌ها رد و بدل شده است. "
    "او افزود تاکنون ۳ نشست کارشناسی برگزار شده "
    "اما هیچ توافق نهایی حاصل نشده است. "
    "وزیر خارجه همچنین گفت هدف اصلی گفت‌وگوها "
    "کاهش اختلافات و بررسی امکان دستیابی به "
    "چارچوبی برای ادامه مذاکرات است."
)


# =========================================================
# TARGET
# =========================================================

TARGET_LENGTH = 360


# =========================================================
# MAIN
# =========================================================

def main() -> int:

    logger.info(
        "========================================"
    )

    logger.info(
        "GEMINI LIVE SUMMARIZER TEST"
    )

    logger.info(
        "========================================"
    )

    # =====================================================
    # CONFIG CHECK
    # =====================================================

    if not gemini_provider_configured():

        logger.error(
            "❌ GEMINI_API_KEY is not configured"
        )

        return 1

    logger.info(
        "✅ Gemini API key detected"
    )

    logger.info(
        f"🤖 Model: {get_gemini_model()}"
    )

    logger.info(
        f"📝 Original length: {len(TEST_TEXT)}"
    )

    logger.info(
        f"🎯 Target length: {TARGET_LENGTH}"
    )

    # =====================================================
    # SAFE SUMMARIZATION
    # =====================================================

    result = (
        summarize_text_safely(
            original_text=TEST_TEXT,
            target_length=TARGET_LENGTH,
            summarizer=summarize_with_gemini,
            max_reduction_ratio=0.40
        )
    )

    # =====================================================
    # RESULT
    # =====================================================

    logger.info(
        "========================================"
    )

    logger.info(
        "RESULT"
    )

    logger.info(
        "========================================"
    )

    logger.info(
        f"success={result.success}"
    )

    logger.info(
        f"validation_passed="
        f"{result.validation_passed}"
    )

    logger.info(
        f"reason={result.reason}"
    )

    logger.info(
        f"original_length="
        f"{result.original_length}"
    )

    logger.info(
        f"summary_length="
        f"{result.summary_length}"
    )

    logger.info(
        f"reduction_ratio="
        f"{result.reduction_ratio:.3f}"
    )

    logger.info(
        "========================================"
    )

    logger.info(
        "SUMMARY OUTPUT"
    )

    logger.info(
        "========================================"
    )

    print(
        result.summary_text
    )

    logger.info(
        "========================================"
    )

    # =====================================================
    # VALIDATION FAILURE DETAILS
    # =====================================================

    if not result.success:

        validation = (
            result.metadata.get(
                "validation"
            )
        )

        if validation:

            logger.error(
                f"Validation errors: "
                f"{validation.get('errors')}"
            )

            logger.warning(
                f"Validation warnings: "
                f"{validation.get('warnings')}"
            )

            candidate = (
                result.metadata.get(
                    "candidate_summary"
                )
            )

            if candidate:

                logger.info(
                    "========================================"
                )

                logger.info(
                    "REJECTED GEMINI CANDIDATE"
                )

                logger.info(
                    "========================================"
                )

                print(
                    candidate
                )

        return 2

    # =====================================================
    # SUCCESS
    # =====================================================

    logger.info(
        "✅ LIVE TEST PASSED"
    )

    return 0


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )
