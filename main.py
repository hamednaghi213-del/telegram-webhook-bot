from flask import Flask, request
import requests
import re

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
CHANNEL = "@Donya24News"
API = f"https://api.telegram.org/bot{TOKEN}/"

# حذف هر چیزی شبیه @username
def remove_usernames(text):
    return re.sub(r"@\S+", "", text)

# حذف کاراکترهای پنهان، RTL/LTR، نیم‌فاصله، Zero-width
def clean_hidden_chars(text):
    return re.sub(r"[\u200c\u200d\u200e\u200f\ufeff]", "", text)

# تشخیص اینکه خط فقط ایموجی/علامت است
def is_emoji_line(text):
    # اگر هیچ حرف فارسی/انگلیسی/عدد ندارد → فقط ایموجی/علامت است
    return not re.search(r"[a-zA-Z0-9آ-ی]", text)

def format_text(text):
    if not text:
        return ""

    lines = text.split("\n")
    output = []

    # --- تیتر ---
    title = clean_hidden_chars(remove_usernames(lines[0].strip()))
    output.append(f"❇️ {title}")

    # --- بندهای خبر ---
    for line in lines[1:]:
        raw = clean_hidden_chars(line.strip())

        # اگر خط شامل @ باشد → کل خط حذف شود
        if "@" in raw:
            continue

        # حذف آیدی‌های احتمالی
        clean = clean_hidden_chars(remove_usernames(raw)).strip()

        # اگر خط فقط ایموجی/علامت باشد → حذف
        if is_emoji_line(clean):
            continue

        # اگر بعد از حذف خالی شد → حذف
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

