import os
import re
import time
import threading
import psycopg2
import telebot
from telebot import types
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
        
        # Products Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100) DEFAULT 'General',
                title VARCHAR(255) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                data TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Users Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                wallet_balance NUMERIC(10, 2) DEFAULT 0.00,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Transactions Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(telegram_id),
                product_id INT,
                amount NUMERIC(10, 2) NOT NULL,
                type VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def register_user(user_id, username):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, username)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username;
        """, (user_id, username))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error registering user: {e}")

# --- START COMMAND & DASHBOARD MENU ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Customer"
    register_user(user_id, username)

    markup = types.InlineKeyboardMarkup(row_width=2)

    if user_id == ADMIN_ID:
        # Admin Menu Markup
        btn1 = types.InlineKeyboardButton("📦 Stock & Catalog", callback_data="admin_stock")
        btn2 = types.InlineKeyboardButton("📊 System Stats", callback_data="admin_stats")
        btn3 = types.InlineKeyboardButton("⚙️ Settings Menu", callback_data="admin_settings")
        btn4 = types.InlineKeyboardButton("💬 Broadcast", callback_data="admin_broadcast_help")
        markup.add(btn1, btn2, btn3, btn4)

        admin_text = (
            f"👑 **Welcome Master Admin ({username})**\n\n"
            "🛠️ **Complete Admin Command Directory:**\n"
            "• `/addproduct` — Add new stock item\n"
            "• `/stock` — View all stock and raw IDs\n"
            "• `/deleteproduct [id]` — Delete a product\n"
            "• `/editprice [id] [price]` — Update product price\n"
            "• `/addbalance [user_id] [amount]` — Credit user wallet\n"
            "• `/stats` — Store performance metrics\n"
            "• `/broadcast [message]` — Message all users\n"
            "• `/sql [query]` — Execute raw PostgreSQL query\n\n"
            "Use the interactive buttons below to quick-navigate control settings:"
        )
        bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=markup)
    else:
        # Customer Menu Markup
        btn1 = types.InlineKeyboardButton("🛒 Browse Catalog", callback_data="user_catalog")
        btn2 = types.InlineKeyboardButton("💰 My Balance", callback_data="user_balance")
        btn3 = types.InlineKeyboardButton("📜 Order History", callback_data="user_history")
        btn4 = types.InlineKeyboardButton("🆘 Support", callback_data="user_support")
        markup.add(btn1, btn2, btn3, btn4)

        user_text = (
            f"👋 **Welcome to LogVault, {username}!**\n\n"
            "Your trusted platform for digital accounts and credentials.\n\n"
            "📌 **Quick Commands:**\n"
            "• `/catalog` — View available products\n"
            "• `/balance` — Check wallet balance\n"
            "• `/history` — View past purchases\n"
            "• `/buy [id]` — Purchase a log item\n\n"
            "Select an option below to get started:"
        )
        bot.reply_to(message, user_text, parse_mode="Markdown", reply_markup=markup)

# --- INLINE BUTTON CALLBACK HANDLER ---

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id

    if call.data == "admin_stock":
        if user_id != ADMIN_ID: return
        handle_stock(call.message)
    elif call.data == "admin_stats":
        if user_id != ADMIN_ID: return
        handle_stats(call.message)
    elif call.data == "admin_settings":
        if user_id != ADMIN_ID: return
        settings_text = (
            "⚙️ **System Control & Settings**\n\n"
            "• **Database Host:** Render PostgreSQL\n"
            "• **Webhook:** Polling (Active)\n"
            "• **Database Engine:** `/sql` Enabled\n"
            "• **Auto-Reconnect:** Active\n\n"
            "To adjust parameters, run your commands directly in chat."
        )
        bot.send_message(call.message.chat.id, settings_text, parse_mode="Markdown")
    elif call.data == "admin_broadcast_help":
        bot.send_message(call.message.chat.id, "📢 Usage: `/broadcast [Your Announcement Message]`", parse_mode="Markdown")
    elif call.data == "user_catalog":
        handle_catalog(call.message)
    elif call.data == "user_balance":
        handle_balance(call.message)
    elif call.data == "user_history":
        handle_history(call.message)
    elif call.data == "user_support":
        bot.send_message(call.message.chat.id, "🆘 Need help? Contact store management directly at `@LogVaultAdmin_bot`.")

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    text = message.text
    category_match = re.search(r'Category:\s*(.*?)\n', text, re.IGNORECASE)
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

    category = category_match.group(1).strip() if category_match else "General"
    title = title_match.group(1).strip()
    price = price_match.group(1).strip()
    accounts_data = data_match.group(1).strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO products (category, title, price, data) VALUES (%s, %s, %s, %s) RETURNING id;",
            (category, title, float(price), accounts_data)
        )
        prod_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(
            message,
            f"✅ Product Added!\n🆔 ID: `{prod_id}`\n📁 Category: {category}\n📦 Title: {title}\n💰 Price: ₦{price}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['stock'])
def handle_stock(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, category, title, price, status FROM products ORDER BY id ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "📦 Stock is empty.")
            return

        response = "📦 **Admin Stock View:**\n\n"
        for row in rows:
            prod_id, category, title, price, status = row
            response += f"🆔 `{prod_id}` | [{category}] **{title}** - ₦{price:.2f} ({status})\n"

        bot.reply_to(message, response, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['addbalance'])
def handle_add_balance(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/addbalance [user_id] [amount]`", parse_mode="Markdown")
        return

    target_id = int(parts[1])
    try:
        amount = float(parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Amount must be a number.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET wallet_balance = wallet_balance + %s WHERE telegram_id = %s RETURNING wallet_balance;", (amount, target_id))
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"💰 Credited User `{target_id}` with ₦{amount:.2f}. New Balance: ₦{res[0]:.2f}", parse_mode="Markdown")
            try:
                bot.send_message(target_id, f"🎉 Your wallet has been credited with ₦{amount:.2f}! New Balance: ₦{res[0]:.2f}")
            except:
                pass
        else:
            bot.reply_to(message, "❌ User ID not found in database.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['sql'])
def handle_sql(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    query = message.text.replace("/sql", "").strip()
    if not query:
        bot.reply_to(message, "❌ Format: `/sql [Your SQL Query]`", parse_mode="Markdown")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query)
        if cur.description:
            rows = cur.fetchall()
            conn.commit()
            cur.close()
            conn.close()
            bot.reply_to(message, f"📊 **Query Result:**\n`{rows}`", parse_mode="Markdown")
        else:
            conn.commit()
            cur.close()
            conn.close()
            bot.reply_to(message, "✅ Query Executed Successfully!")
    except Exception as e:
        bot.reply_to(message, f"❌ SQL Error: {str(e)}")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(price), 0) FROM products WHERE status = 'available';")
        stock_count, total_value = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM users;")
        user_count = cur.fetchone()[0]
        cur.close()
        conn.close()

        msg = (
            "📊 **LogVault Store Metrics:**\n\n"
            f"👤 **Registered Users:** `{user_count}`\n"
            f"📦 **Available Products:** `{stock_count}`\n"
            f"💵 **Total Stock Value:** ₦`{total_value:,.2f}`"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

# --- CUSTOMER COMMANDS ---

@bot.message_handler(commands=['catalog'])
def handle_catalog(message):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, category, title, price FROM products WHERE status = 'available' ORDER BY id ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "🛒 Catalog is currently empty. Check back soon!")
            return

        response = "🛒 **Available Store Inventory:**\n\n"
        for row in rows:
            prod_id, category, title, price = row
            response += f"📁 **{category}** | 📦 **{title}**\n💰 **Price:** ₦{price:.2f}\n👉 Buy command: `/buy {prod_id}`\n\n"

        bot.reply_to(message, response, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error loading catalog: {str(e)}")

@bot.message_handler(commands=['balance'])
def handle_balance(message):
    user_id = message.from_user.id
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (user_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()

        balance = res[0] if res else 0.00
        bot.reply_to(message, f"💳 **Your Wallet Balance:** ₦{balance:,.2f}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error fetching balance: {str(e)}")

@bot.message_handler(commands=['buy'])
def handle_buy(message):
    user_id = message.from_user.id
    parts = message.text.split()

    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/buy [product_id]`\nExample: `/buy 1`", parse_mode="Markdown")
        return

    prod_id = int(parts[1])

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check Product
        cur.execute("SELECT title, price, data, status FROM products WHERE id = %s;", (prod_id,))
        product = cur.fetchone()

        if not product or product[3] != 'available':
            bot.reply_to(message, "❌ Product is unavailable or sold out.")
            cur.close()
            conn.close()
            return

        title, price, account_data, _ = product

        # Check User Balance
        cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (user_id,))
        user_res = cur.fetchone()
        user_balance = user_res[0] if user_res else 0.00

        if user_balance < price:
            bot.reply_to(message, f"❌ Insufficient balance!\nProduct Price: ₦{price:.2f}\nYour Balance: ₦{user_balance:.2f}")
            cur.close()
            conn.close()
            return

        # Deduct balance and deliver product
        cur.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE telegram_id = %s;", (price, user_id))
        cur.execute("UPDATE products SET status = 'sold' WHERE id = %s;", (prod_id,))
        cur.execute("INSERT INTO transactions (user_id, product_id, amount, type) VALUES (%s, %s, %s, 'purchase');", (user_id, prod_id, price))

        conn.commit()
        cur.close()
        conn.close()

        delivery_msg = (
            f"🎉 **Purchase Successful!**\n\n"
            f"📦 **Product:** {title}\n"
            f"💰 **Amount Paid:** ₦{price:.2f}\n\n"
            f"🔐 **Account Credentials:**\n`{account_data}`"
        )
        bot.reply_to(message, delivery_msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Purchase Error: {str(e)}")

@bot.message_handler(commands=['history'])
def handle_history(message):
    user_id = message.from_user.id
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, p.title, t.amount, t.created_at 
            FROM transactions t 
            JOIN products p ON t.product_id = p.id 
            WHERE t.user_id = %s ORDER BY t.id DESC LIMIT 10;
        """, (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "📜 You have no past purchases.")
            return

        msg = "📜 **Your Past Purchases:**\n\n"
        for row in rows:
            tx_id, title, amount, date = row
            msg += f"🆔 `{tx_id}` | **{title}** - ₦{amount:.2f}\n"

        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error loading history: {str(e)}")

# --- AUTO-RECONNECT POLLING LOOP ---

def start_polling():
    print("Clearing webhooks...")
    bot.remove_webhook()
    print("Starting bot polling with auto-reconnect...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling network disconnect: {e}")
            time.sleep(5)

if __name__ == "__main__":
    init_db()

    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
