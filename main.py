from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
API = f"https://api.telegram.org/bot{TOKEN}"

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
            caption = msg.get("caption", "")

            # پیام فوروارد — فقط متن، بدون هیچ اطلاعات فرستنده
            if "forward_from" in msg or "forward_from_chat" in msg or "forward_sender_name" in msg:
                clean = caption or text
                send_message(chat_id, f"{CHANNEL_TAG}\n{clean}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # عکس
            if "photo" in msg:
                clean = caption if caption else "عکس دریافت شد."
                send_message(chat_id, f"{CHANNEL_TAG}\n{clean}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # فایل
            if "document" in msg:
                clean = caption if caption else "فایل دریافت شد."
                send_message(chat_id, f"{CHANNEL_TAG}\n{clean}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # ویس
            if "voice" in msg:
                clean = caption if caption else "ویس دریافت شد."
                send_message(chat_id, f"{CHANNEL_TAG}\n{clean}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            # پیام متنی معمولی — بدون تغییر
            if text:
                send_message(chat_id, f"{CHANNEL_TAG}\n{text}\n\n{CHANNEL_HASHTAG}")
                return {"ok": True}

            #





