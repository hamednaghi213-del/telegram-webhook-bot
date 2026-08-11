import re
from flask import Flask, request
import requests

TOKEN = "8780146510:AAG0jmX2A-_TL86GceCglsNxS4Tyz6EW784"
CHANNEL = "@Donya24News"
API = f"https://api.telegram.org/bot{TOKEN}/"

# حذف آیدی‌ها
def remove_usernames(text):
    return re.sub(r"@\S+", "", text)

# حذف لینک‌ها و آدرس‌های سایت
def remove_links(text):
    return re.sub(r"(https?://\S+|www\.\S+|\S+\.(com|ir|org|net|info|news))", "", text)

# حذف کاراکترهای پنهان
def clean_hidden_chars(text):
    return re.sub(r"[\u200c\u200d\u200e\u200f\ufeff]", "", text)

# نیم‌فاصلهٔ حرفه‌ای (ZWJ + Space)
def fix_spacing(text):
    pattern = r"([اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی])([اآبپتثجچحخدذرزسشصضطظعغفقکگلمنوهی])"
    return re.sub(pattern, r"\1\u200d \2", text)

# نگه‌داشتن فقط تا آخرین حرف واقعی
def keep_until_last_letter(text):
    match = re.search(r".*[a-zA-Z0-9آ-ی]", text)
    return match.group(0) if match else ""

# حذف ایموجی‌های اول خط و نگه‌داشتن فقط یک 🔹
def normalize_bullet(text):
    text = re.sub(r"^[^\wآ-ی]+", "", text)
    if re.search(r"[a-zA-Z0-9آ-ی]", text):
        return "🔹 " + text
    return ""

# تشخیص وجود فعل (فقط برای بندهای خبری)
def has_verb(text):
    verbs = [
        "است", "هست", "شد", "می‌شود", "می شود", "می‌کند", "می کند",
        "خواهد", "کرد", "می‌گردد", "می گردد", "بود", "می‌باشد", "می باشد",
        "گفت", "اعلام کرد", "توضیح داد", "افزود", "تصریح کرد",
        "خواهد شد", "خواهد بود", "پرواز کرد", "خارج کرد", "خارج شده",
        "انجام شد", "به نظر برسد"
    ]
    return any(v in text for v in verbs)

def format_text(text):
    if not text:
        return ""

    lines = text.split("\n")
    output = []

    # --- تیتر (بدون فیلتر فعل) ---
    title = lines[0].strip()
    title = remove_usernames(title)
    title = remove_links(title)
    title = clean_hidden_chars(title)
    title = keep_until_last_letter(title).strip()
    title = fix_spacing(title)

    # اگر تیتر خالی شد، یک تیتر جایگزین می‌گذاریم تا خروجی صفر نشود
    if not title:
        title = "خبر"

    output.append(f"❇️ {title}")

    # --- بندهای خبر (با فیلتر فعل) ---
    for line in lines[1:]:
        raw = line.strip()

        # حذف آیدی‌ها اما بدون حذف کل خروجی
        if raw.startswith("@"):
            continue

        clean = remove_links(raw)
        clean = remove_usernames(clean)
        clean = clean_hidden_chars(clean).strip()
        clean = keep_until_last_letter(clean).strip()
        clean = fix_spacing(clean)
        clean = normalize_bullet(clean).strip()

        # فیلتر فعل فقط برای بندهای خبری
        if not has_verb(clean):
            continue

        if not clean:
            continue

        output.append(clean)

    # همیشه این دو خط آخر اضافه شوند
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



