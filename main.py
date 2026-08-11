from flask import Flask, request
import requests

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
CHANNEL = "@Donya24News"
API = f"https://api.telegram.org/bot{TOKEN}/"

def format_text(text):
    if not text:
        return ""

    lines = text.split("\n")
    output = []

    # تیتر
    output.append(f"❇️ {lines[0].strip()}")

    # بندها
    for line in lines[1:]:
        line = line.strip()

        # حذف هر خطی که @ دارد
        if "@" in line:
            continue

        if line:
            output.append(f"🔹 {line}")

    # تگ کانال
    output.append("#دنیا_۲۴_نیوز")
    output.append("@Donya24News")

    return "\n\n".join(output)

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.json

    if "message" in data:
        msg = data["message"]

        if "text" in msg:
            text = format_text(msg["text"])
            requests.post(API + "sendMessage", data={
                "chat_id": CHANNEL,
                "text": text
            })

        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendPhoto", data={
                "chat_id": CHANNEL,
                "photo": file_id,
                "caption": caption
            })

        if "video" in msg:
            file_id = msg["video"]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendVideo", data={
                "chat_id": CHANNEL,
                "video": file_id,
                "caption": caption
            })

        if "document" in msg:
            file_id = msg["document"]["file_id"]
            caption = format_text(msg.get("caption", ""))
            requests.post(API + "sendDocument", data={
                "chat_id": CHANNEL,
                "document": file_id,
                "caption": caption
            })

    return "ok"

