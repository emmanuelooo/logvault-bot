import os
import re
import threading
import requests
import telebot
import pyaes
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "LogVault Bot Active", 200

BOT_TOKEN = "8760290765:AAGNQIoMP4UwhbKlvQFm9mcnF76logqNv1o"
ADMIN_ID = 8663858182
BRIDGE_URL = "https://logvault.page.gd/bridge.php"
SECRET_KEY = "Emmanuel16908"

bot = telebot.TeleBot(BOT_TOKEN)

def hex_to_bytes(hex_str):
    return bytes.fromhex(hex_str)

def solve_infinityfree_cookie(html):
    # Extract AES parameters from InfinityFree anti-bot challenge
    a_hex = re.search(r'a=toNumbers\("([a-f0-9]+)"\)', html).group(1)
    b_hex = re.search(r'b=toNumbers\("([a-f0-9]+)"\)', html).group(1)
    c_hex = re.search(r'c=toNumbers\("([a-f0-9]+)"\)', html).group(1)

    key = hex_to_bytes(a_hex)
    iv = hex_to_bytes(b_hex)
    ciphertext = hex_to_bytes(c_hex)

    # Decrypt CBC mode cleanly
    decryptor = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(key, iv))
    decrypted = decryptor.feed(ciphertext)
    
    return decrypted.hex()

def get_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    res = s.get(BRIDGE_URL)
    if "slowAES" in res.text:
        cookie_val = solve_infinityfree_cookie(res.text)
        s.cookies.set("__test", cookie_val, domain="logvault.page.gd", path="/")
    return s

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

    payload = {
        'key': SECRET_KEY,
        'title': title,
        'price': price,
        'data': accounts_data
    }

    try:
        session = get_session()
        res = session.post(BRIDGE_URL, data=payload, timeout=15)
        
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
    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
