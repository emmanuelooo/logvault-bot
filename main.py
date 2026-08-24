import os
import re
import threading
import requests
import telebot
from flask import Flask

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def health_check():
    return "LogVault Bot is Active!", 200

# Credentials
BOT_TOKEN = "8760290765:AAEiSfJeKlFx9jxLlGCRep9ZTtdPmXz5Gmw"
ADMIN_ID = 8663858182
BRIDGE_URL = "https://logvault.page.gd/bridge.php"
SECRET_KEY = "Emmanuel16908"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized access.")
        return

    text = message.text

    title_match = re.search(r'Title:\s*(.*?)\n', text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*?)\n', text, re.IGNORECASE)
    data_match = re.search(r'Data:\s*\n(.*)', text, re.DOTALL | re.IGNORECASE)

    if not (title_match and price_match and data_match):
        bot.reply_to(
            message,
            "❌ **Invalid Format!**\n\n"
            "Use this format:\n"
            "`/addproduct`\n"
            "Category: Instagram\n"
            "Title: Aged 2020 Account\n"
            "Price: 3500\n"
            "Data:\nuser:pass",
            parse_mode="Markdown"
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.post(BRIDGE_URL, data=payload, headers=headers, timeout=15)
        if "SUCCESS:" in response.text:
            prod_id = response.text.split(":")[1].strip()
            bot.reply_to(
                message,
                f"✅ *Product Uploaded to LogVault!*\n\n"
                f"🆔 *ID:* `{prod_id}`\n"
                f"📦 *Title:* {title}\n"
                f"💰 *Price:* ₦{float(price):,.2f}",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, f"❌ **Bridge Error:**\n`{response.text}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ **Connection Error:** {str(e)}")

def run_bot():
    # Remove any leftover webhooks/connections before long polling
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    # Start bot thread ONLY when main script runs directly
    threading.Thread(target=run_bot, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
