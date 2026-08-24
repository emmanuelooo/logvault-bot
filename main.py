import os
import re
import threading
import requests
import telebot
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "LogVault Bot Active", 200

BOT_TOKEN = "8760290765:AAEiSfJeKlFx9jxLlGCRep9ZTtdPmXz5Gmw"
ADMIN_ID = 8663858182
BRIDGE_URL = "https://logvault.page.gd/bridge.php"
SECRET_KEY = "Emmanuel16908"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    print(f"Incoming message from User ID: {message.from_user.id}")
    
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

    payload = {
        'key': SECRET_KEY,
        'title': title,
        'price': price,
        'data': accounts_data
    }

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        res = requests.post(BRIDGE_URL, data=payload, headers=headers, timeout=15)
        print(f"Bridge raw response: {res.text}")
        
        if "SUCCESS:" in res.text:
            prod_id = res.text.split(":")[1].strip()
            bot.reply_to(message, f"✅ Product Added!\n🆔 ID: {prod_id}\n📦 Title: {title}\n💰 Price: ₦{price}")
        else:
            bot.reply_to(message, f"❌ Bridge Response Error:\n`{res.text}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Connection Error: {str(e)}")

def start_polling():
    print("Clearing old webhooks/connections...")
    bot.remove_webhook()
    print("Starting bot polling...")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    # Start single thread for bot polling
    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    # Bind port for Render Web Service health checks
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
