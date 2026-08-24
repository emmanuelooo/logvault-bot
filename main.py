import os
import re
import requests
import telebot

# Credentials
BOT_TOKEN = "8760290765:AAEiSfJeKlFx9jxLlGCRep9ZTtdPmXz5Gmw"
ADMIN_ID = 8663858182
BRIDGE_URL = "https://logvault.page.gd/bridge.php"
SECRET_KEY = "Emmanuel16908"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    # Security check: ignore anyone who isn't you
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized access.")
        return

    text = message.text

    # Extract fields using regex patterns
    cat_match = re.search(r'Category:\s*(.*?)\n', text, re.IGNORECASE)
    title_match = re.search(r'Title:\s*(.*?)\n', text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*?)\n', text, re.IGNORECASE)
    data_match = re.search(r'Data:\s*\n(.*)', text, re.DOTALL | re.IGNORECASE)

    # Validate that required fields exist
    if not (title_match and price_match and data_match):
        bot.reply_to(
            message,
            "❌ **Invalid Format!**\n\n"
            "Please use this format:\n"
            "`/addproduct`\n"
            "Category: Instagram\n"
            "Title: Aged 2020 Account + Cookies\n"
            "Price: 3500\n"
            "Data:\n"
            "user1:pass1:email1:epass1\n"
            "user2:pass2:email2:epass2",
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

    # Custom User-Agent header to bypass basic free-host bot filters
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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

# Keep bot listening continuously
if __name__ == "__main__":
    print("LogVault Telegram Bot is running...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Render assigns dynamic ports via $PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
