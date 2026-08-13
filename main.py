import os
import time
import logging
import threading
import requests
from flask import Flask, request
from core.webhook_handler import handle_webhook
from core.database import init_db

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("توکن تنظیم نشده.")

API = f"https://api.telegram.org/bot{TOKEN}"

# ---------- لاگ ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- دیتابیس ----------
init_db()

# ---------- Self-Ping ----------
def self_ping():
    while True:
        try:
            requests.get("https://telegram-webhook-bot-onyd.onrender.com/", timeout=10)
            logger.info("🔄 Self-ping: OK")
        except Exception as e:
            logger.error(f"❌ Self-ping: {e}")
        time.sleep(420)

threading.Thread(target=self_ping, daemon=True).start()
logger.info("✅ Self-ping فعال شد")

# ---------- Webhook ----------
@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        return handle_webhook()
    return "ربات خبری فعال است"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
