import os
import re
import threading
import requests
import telebot
import js2py
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

def get_infinityfree_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # First request to grab the AES challenge
    res = session.get(BRIDGE_URL)
    if "slowAES" in res.text:
        # Extract script logic and resolve cookie
        aes_js = session.get("https://logvault.page.gd/aes.js").text
        
        # Combine script and challenge
        full_js = aes_js + "\n" + re.search(r'<script>(.*?)</script>', res.text, re.DOTALL).group(1)
        full_js = full_js.replace("location.href=", "//")
        
        # Execute JS environment to retrieve document.cookie
        context = js2py.EvalJs()
        context.execute("var document = {}; " + full_js)
        
        cookie_str = context.document.cookie
        cookie_name, cookie_val = cookie_str.split(';')[0].split('=')
        session.cookies.set(cookie_name, cookie_val)
        
    return session

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
        bot.reply_to(message, "❌ Invalid Format!")
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

    try:
        session = get_infinityfree_session()
        res = session.post(BRIDGE_URL, data=payload, timeout=15)
        
        if "SUCCESS:" in res.text:
            prod_id = res.text.split(":")[1].strip()
            bot.reply_to(message, f"✅ Product Added!\n🆔 ID: {prod_id}\n📦 Title: {title}\n💰 Price: ₦{price}")
        else:
            bot.reply_to(message, f"❌ Bridge Error:\n`{res.text}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Connection Error: {str(e)}")

def start_polling():
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
