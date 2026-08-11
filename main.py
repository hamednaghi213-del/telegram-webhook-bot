from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
API = f"https://api.telegram.org/bot{TOKEN}"

# کانال واقعی تو
CHANNEL_TAG = "@Donya24News"
CHANNEL_HASHTAG = "#دنیا_۲۴_نیوز"

def send_message(chat_id, text):
    requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        data = request.get_json()

        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]

            # متن پیام
            text = msg.get("text", "")
            # کپشن برای عکس/فایل
            caption = msg.get("caption", "")
            # پیام فوروارد
            is_forward = "forward_from" in msg or "forward_from_chat" in msg

            # پاکسازی
            if text:
                text = text.strip()
            if caption:
                caption = caption.strip()

            # فوروارد
            if is_forward:
                send_message(chat_id, f"{CHANNEL_TAG}\n{caption or text}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # عکس
            if "photo" in msg:
                send_message(chat_id, f"{CHANNEL_TAG}\nعکس دریافت شد.\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # فایل
            if "document" in msg:
                send_message(chat_id, f"{CHANNEL_TAG}\nفایل دریافت شد.\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # ویس
            if "voice" in msg:
                send_message(chat_id, f"{CHANNEL_TAG}\nویس دریافت شد.\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # پیام متنی معمولی
            if text:
                send_message(chat_id, f"{CHANNEL_TAG}\n{text}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # پیام بدون متن
            if caption:
                send_message(chat_id, f"{CHANNEL_TAG}\n{caption}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

        return {"ok": True}

    return "Bot is running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)




