from flask import Flask, request
import requests
import re

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
CHANNEL = "@Donya24News"
API = f"https://api.telegram.org/bot{TOKEN}/"

# حذف هر چیزی شبیه @username
def remove_usernames(text):
    return re.sub(r"@\S+", "", text)

def format_text(text):
    if not text:
        return ""

    lines = text.split("\n")
    output = []

    # --- تیتر ---
    title = remove_usernames(lines[0].strip())
    output.append(f"❇️ {title}")

    # --- بندهای خبر ---
    for line in lines[1:]:
        raw = line.strip()

        # اگر خط شامل @ باشد → کل خط حذف شود (ایموجی‌ها هم حذف می‌شوند)
        if "@" in raw:
            continue

        # حذف آیدی‌های احتمالی باقی‌مانده
        clean = remove_usernames(raw).strip()

        # اگر بعد از حذف خالی شد → رد کن
        if not clean:
            continue

        output.append(f"🔹 {clean}")

    # --- تگ کانال ---
    output.append("#دنیا_۲۴_نیوز")
    output.append("@Donya24News")

    return "\n\n".join(output)

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.json

    if "message" in data:
        msg = data["message"]

        # متن
        if "text" in msg:
            text = format_text(msg["text"])
            requests.post(API + "sendMessage", data={
                "chat_id": CHANNEL,
                "text": text
            })

        # عکس
        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendPhoto", data={
                "chat_id": CHANNEL,
                "photo": file_id,
                "caption": caption
            })

        # ویدیو
        if "video" in msg:
            file_id = msg["video"]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendVideo", data={
                "chat_id": CHANNEL,
                "video": file_id,
                "caption": caption
            })

        # سند
        if "document" in msg:
            file_id = msg["document"]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendDocument", data={
                "chat_id": CHANNEL,
                "document": file_id,
                "caption": caption
            })

    return "ok"
