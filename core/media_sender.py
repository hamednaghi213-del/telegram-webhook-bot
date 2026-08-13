import requests
import logging

logger = logging.getLogger(__name__)

def send_media_to_channel(api_url, channel_id, file_id, media_type, caption=""):
    try:
        if media_type == "photo":
            endpoint = f"{api_url}/sendPhoto"
        elif media_type == "video":
            endpoint = f"{api_url}/sendVideo"
        elif media_type == "document":
            endpoint = f"{api_url}/sendDocument"
        elif media_type == "voice":
            endpoint = f"{api_url}/sendVoice"
        elif media_type == "audio":
            endpoint = f"{api_url}/sendAudio"
        else:
            return False

        resp = requests.post(
            endpoint,
            json={"chat_id": channel_id, media_type: file_id, "caption": caption},
            timeout=30
        )
        resp.raise_for_status()
        logger.info(f"✅ {media_type} در کانال منتشر شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال رسانه: {e}")
        return False

def send_media_group(api_url, channel_id, files, caption=""):
    try:
        media_group = []
        for i, file in enumerate(files):
            if file["type"] == "photo":
                media = {"type": "photo", "media": file["file_id"]}
            elif file["type"] == "video":
                media = {"type": "video", "media": file["file_id"]}
            else:
                continue
            if i == 0 and caption:
                media["caption"] = caption
            media_group.append(media)

        if not media_group:
            return False

        resp = requests.post(
            f"{api_url}/sendMediaGroup",
            json={"chat_id": channel_id, "media": media_group},
            timeout=30
        )
        resp.raise_for_status()
        logger.info(f"✅ آلبوم با {len(media_group)} رسانه ارسال شد")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال آلبوم: {e}")
        return False
