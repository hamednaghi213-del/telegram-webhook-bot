import os
import uuid
import logging
import tempfile

logger = logging.getLogger(__name__)


# =========================================================
# STORAGE DIRECTORY
# =========================================================

STORAGE_DIR = os.getenv(
    "MEDIA_STORAGE_DIR",
    "/tmp/bot_media"
)


def initialize_storage():
    """
    آماده‌سازی پوشه موقت ذخیره رسانه.
    """

    try:

        os.makedirs(
            STORAGE_DIR,
            exist_ok=True
        )

        logger.info(
            f"✅ Media Storage initialized | "
            f"path={STORAGE_DIR}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ خطا در ساخت Media Storage: {e}"
        )

        return False


# =========================================================
# CREATE TEMP FILE
# =========================================================

def create_temp_file(
    suffix=".bin"
):
    """
    ساخت مسیر فایل موقت بدون نگه داشتن
    محتوای فایل در RAM.
    """

    try:

        os.makedirs(
            STORAGE_DIR,
            exist_ok=True
        )

        filename = (
            f"{uuid.uuid4().hex}"
            f"{suffix}"
        )

        path = os.path.join(
            STORAGE_DIR,
            filename
        )

        logger.info(
            f"📦 فایل موقت ایجاد شد | "
            f"path={path}"
        )

        return path

    except Exception as e:

        logger.exception(
            f"❌ خطا در create_temp_file: {e}"
        )

        return None


# =========================================================
# SAVE BYTES
# =========================================================

def save_bytes(
    content,
    suffix=".bin"
):
    """
    برای فایل‌های کوچک یا داده‌ای که از قبل
    در RAM قرار دارند.
    """

    if not content:

        logger.warning(
            "⚠️ محتوای خالی برای ذخیره دریافت شد."
        )

        return None

    path = create_temp_file(
        suffix
    )

    if not path:

        return None

    try:

        with open(
            path,
            "wb"
        ) as file:

            file.write(
                content
            )

        logger.info(
            f"✅ فایل ذخیره شد | "
            f"size={len(content)} bytes"
        )

        return path

    except Exception as e:

        logger.exception(
            f"❌ خطا در save_bytes: {e}"
        )

        delete_file(
            path
        )

        return None


# =========================================================
# FILE SIZE
# =========================================================

def get_file_size(
    path
):
    """
    دریافت اندازه فایل.
    """

    try:

        if not path:
            return 0

        if not os.path.exists(
            path
        ):
            return 0

        return os.path.getsize(
            path
        )

    except Exception as e:

        logger.warning(
            f"⚠️ خطا در دریافت اندازه فایل: {e}"
        )

        return 0


# =========================================================
# DELETE FILE
# =========================================================

def delete_file(
    path
):
    """
    حذف فایل موقت پس از ارسال.
    """

    if not path:
        return False

    try:

        if os.path.exists(
            path
        ):

            os.remove(
                path
            )

            logger.info(
                f"🧹 فایل موقت حذف شد | "
                f"path={path}"
            )

        return True

    except Exception as e:

        logger.warning(
            f"⚠️ حذف فایل ناموفق بود | "
            f"path={path} | "
            f"error={e}"
        )

        return False


# =========================================================
# CLEANUP STORAGE
# =========================================================

def cleanup_storage():
    """
    پاکسازی فایل‌های باقی‌مانده در Storage.
    """

    try:

        if not os.path.exists(
            STORAGE_DIR
        ):

            return

        count = 0

        for filename in os.listdir(
            STORAGE_DIR
        ):

            path = os.path.join(
                STORAGE_DIR,
                filename
            )

            if os.path.isfile(
                path
            ):

                try:

                    os.remove(
                        path
                    )

                    count += 1

                except Exception:
                    pass

        logger.info(
            f"🧹 Storage cleanup انجام شد | "
            f"files={count}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ خطا در cleanup_storage: {e}"
        )
