import os
import re
import threading
import psycopg2
import telebot
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "LogVault Bot Active", 200

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8663858182"))
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = telebot.TeleBot(BOT_TOKEN)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    text = message.text

    title_match = re.search(r'Title:\s*(.*?)\n', text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*?)\n', text, re.IGNORECASE)
    data_match = re.search(r'Data:\s*\n(.*)', text, re.DOTALL | re.IGNORECASE)

    if not (title_match and price_match and data_match):
        bot.reply_to(
            message,
            "❌ Format incorrect! Send message using:\n\n"
            "/addproduct\n"
            "Category: Instagram\n"
            "Title: Aged 2020 Account\n"
            "Price: 3500\n"
            "Data:\nuser:pass"
        )
        return

    title = title_match.group(1).strip()
    price = price_match.group(1).strip()
    accounts_data = data_match.group(1).strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO products (title, price, data) VALUES (%s, %s, %s) RETURNING id;",
            (title, float(price), accounts_data)
        )
        prod_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(
            message,
            f"✅ Product Added!\n🆔 ID: {prod_id}\n📦 Title: {title}\n💰 Price: ₦{price}"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

def start_polling():
    print("Clearing old webhooks/connections...")
    bot.remove_webhook()
    print("Starting bot polling...")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    init_db()
    
    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
