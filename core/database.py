import sqlite3
import os

DB_PATH = "tenants.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            bot_token TEXT,
            telegram_channel TEXT,
            bale_channel TEXT,
            bale_token TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_tenant(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tenants WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_tenant(user_id, bot_token, telegram_channel, bale_channel=None, bale_token=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO tenants (user_id, bot_token, telegram_channel, bale_channel, bale_token)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, bot_token, telegram_channel, bale_channel, bale_token))
    conn.commit()
    conn.close()
