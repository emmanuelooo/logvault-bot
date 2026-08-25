import os
import re
import time
import threading
import psycopg2
import telebot
from telebot import types
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def health_check():
    return "LogVault Core Service Online", 200

# Environment Configuration
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
        print("Database schema successfully deployed.")
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

# --- KEYBOARD DASHBOARDS ---

def get_admin_dashboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("📦 Stock Control", callback_data="admin_inv_menu")
    b2 = types.InlineKeyboardButton("💰 Financial Ledger", callback_data="admin_fin_menu")
    b3 = types.InlineKeyboardButton("👤 User Moderation", callback_data="admin_user_menu")
    b4 = types.InlineKeyboardButton("📊 Business Analytics", callback_data="admin_stats")
    b5 = types.InlineKeyboardButton("📢 Mass Broadcast", callback_data="admin_broadcast_help")
    b6 = types.InlineKeyboardButton("⚙️ System Status", callback_data="admin_settings")
    markup.add(b1, b2, b3, b4, b5, b6)
    return markup

def get_user_dashboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("🛒 Store Catalog", callback_data="user_catalog")
    b2 = types.InlineKeyboardButton("💳 Account Wallet", callback_data="user_balance")
    b3 = types.InlineKeyboardButton("📜 Order History", callback_data="user_history")
    b4 = types.InlineKeyboardButton("➕ Fund Wallet", callback_data="user_fund")
    b5 = types.InlineKeyboardButton("🆘 Admin Support", callback_data="user_support")
    markup.add(b1, b2, b3, b4, b5)
    return markup

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = int(message.from_user.id)
    username = message.from_user.username or "Customer"
    register_user(user_id, username)

    if user_id == ADMIN_ID:
        admin_text = (
            f"👑 **LogVault Master Control System**\n"
            f"Logged in: `@${username}` | ID: `{user_id}`\n\n"
            "🛠️ **Command Index:**\n"
            "• `/addproduct` — Single item upload\n"
            "• `/bulkadd` — Bulk stock import\n"
            "• `/stock` — Display current stock IDs\n"
            "• `/searchstock [key]` — Search item data\n"
            "• `/editprice [id] [price]` — Price adjustment\n"
            "• `/deleteproduct [id]` — Purge single item\n"
            "• `/addbalance [id] [amt]` — Credit wallet\n"
            "• `/deductbalance [id] [amt]` — Debit wallet\n"
            "• `/setbalance [id] [amt]` — Set explicit balance\n"
            "• `/userinfo [id]` — Full account audit\n"
            "• `/banuser [id]` / `/unbanuser [id]` — Restrict user\n"
            "• `/broadcast [msg]` — Blast notification\n"
            "• `/saleslog` — View recent revenue stream\n"
            "• `/sql [query]` — Postgres execution engine\n\n"
            "Tap any control category below:"
        )
        bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=get_admin_dashboard())
    else:
        user_text = (
            f"👋 **Welcome to LogVault, {username}!**\n\n"
            "Your automated platform for digital accounts and credentials.\n\n"
            "📌 **Quick Menu Commands:**\n"
            "• `/catalog` — View available accounts\n"
            "• `/balance` — Check balance & deposit info\n"
            "• `/history` — Review delivered orders\n"
            "• `/buy [id]` — Purchase item instantly\n\n"
            "Use buttons below to begin:"
        )
        bot.reply_to(message, user_text, parse_mode="Markdown", reply_markup=get_user_dashboard())

# --- CALLBACK QUERY HANDLER ---

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = int(call.from_user.id)
    admin_id = int(ADMIN_ID)

    if call.data == "admin_inv_menu":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = (
            "📦 **Inventory Command Directory**\n\n"
            "• `/addproduct` — Add single product entry\n"
            "• `/bulkadd` — Add multiple items automatically\n"
            "• `/stock` — Show raw active stock listing\n"
            "• `/searchstock [query]` — Find item inside stock\n"
            "• `/editprice [id] [price]` — Change price tag\n"
            "• `/deleteproduct [id]` — Delete product row"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "admin_fin_menu":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = (
            "💰 **Financial Operations Suite**\n\n"
            "• `/addbalance [user_id] [amount]` — Credit user\n"
            "• `/deductbalance [user_id] [amount]` — Debit user\n"
            "• `/setbalance [user_id] [amount]` — Fixed override\n"
            "• `/saleslog` — Review sales revenue ledger"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "admin_user_menu":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = (
            "👤 **User Governance**\n\n"
            "• `/userinfo [user_id]` — Detailed user audit profile\n"
            "• `/banuser [user_id]` — Restrict platform access\n"
            "• `/unbanuser [user_id]` — Unblock user"
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "admin_stats":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), COALESCE(SUM(price), 0) FROM products WHERE status = 'available';")
            stock_count, total_val = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM users;")
            user_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'purchase';")
            sales_count, gross_revenue = cur.fetchone()
            cur.close()
            conn.close()

            msg = (
                "📊 **LogVault Operations Metrics:**\n\n"
                f"👤 **Total Users:** `{user_count}`\n"
                f"📦 **Stock Inventory Available:** `{stock_count}`\n"
                f"💵 **Stock Value:** ₦`{total_val:,.2f}`\n"
                f"🛍️ **Total Orders Processed:** `{sales_count}`\n"
                f"💳 **Gross Store Sales:** ₦`{gross_revenue:,.2f}`"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Database Error: {str(e)}")

    elif call.data == "admin_settings":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        settings_text = (
            "⚙️ **System Diagnostics**\n\n"
            "• **DB Host:** Render PostgreSQL\n"
            "• **Webhook State:** Auto Polling Active\n"
            "• **SQL Interceptor:** `/sql` Enabled\n"
            "• **Fail-over Worker:** Threading Engine Active"
        )
        bot.send_message(call.message.chat.id, settings_text, parse_mode="Markdown")

    elif call.data == "admin_broadcast_help":
        if user_id != admin_id:
            bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📢 **Broadcast Format:**\n`/broadcast [Your Announcement Message]`", parse_mode="Markdown")

    elif call.data == "user_catalog":
        bot.answer_callback_query(call.id)
        handle_catalog(call.message)

    elif call.data == "user_balance":
        bot.answer_callback_query(call.id)
        handle_balance(call.message)

    elif call.data == "user_history":
        bot.answer_callback_query(call.id)
        handle_history(call.message)

    elif call.data == "user_fund":
        bot.answer_callback_query(call.id)
        msg = (
            "➕ **Wallet Funding Options:**\n\n"
            "To credit your LogVault wallet balance, contact store admin directly:\n"
            "👤 Admin Handle: `@LogVaultAdmin_bot`\n\n"
            "Provide your Telegram User ID (`" + str(user_id) + "`) to request automatic balance top-ups."
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "user_support":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🆘 Customer support: Reach admin via `@LogVaultAdmin_bot`.")

# --- ADMIN PRODUCT & STOCK MANAGEMENT ---

@bot.message_handler(commands=['addproduct'])
def handle_add_product(message):
    if int(message.from_user.id) != ADMIN_ID:
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
            "❌ Format incorrect! Send message as:\n\n"
            "/addproduct\n"
            "Category: Socials\n"
            "Title: 2021 Instagram Log\n"
            "Price: 4500\n"
            "Data:\nuser:pass:email"
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
            f"✅ **Item Listed Successfully!**\n🆔 ID: `{prod_id}`\n📁 Category: {category}\n📦 Title: {title}\n💰 Price: ₦{price}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['bulkadd'])
def handle_bulk_add(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    text = message.text
    category_match = re.search(r'Category:\s*(.*?)\n', text, re.IGNORECASE)
    title_match = re.search(r'Title:\s*(.*?)\n', text, re.IGNORECASE)
    price_match = re.search(r'Price:\s*(.*?)\n', text, re.IGNORECASE)
    items_match = re.search(r'Items:\s*\n(.*)', text, re.DOTALL | re.IGNORECASE)

    if not (title_match and price_match and items_match):
        bot.reply_to(
            message,
            "❌ Format incorrect! Send message as:\n\n"
            "/bulkadd\n"
            "Category: Netflix\n"
            "Title: Premium Account\n"
            "Price: 1500\n"
            "Items:\n"
            "user1:pass1\n"
            "user2:pass2\n"
            "user3:pass3"
        )
        return

    category = category_match.group(1).strip() if category_match else "General"
    title = title_match.group(1).strip()
    price = float(price_match.group(1).strip())
    raw_items = items_match.group(1).strip().split("\n")

    added_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        for item_data in raw_items:
            clean_item = item_data.strip()
            if clean_item:
                cur.execute(
                    "INSERT INTO products (category, title, price, data) VALUES (%s, %s, %s, %s);",
                    (category, title, price, clean_item)
                )
                added_count += 1

        conn.commit()
        cur.close()
        conn.close()

        bot.reply_to(message, f"⚡ Bulk Upload Successful!\n📦 Imported `{added_count}` stock items under **{title}** at ₦{price:.2f} each.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Bulk Import Error: {str(e)}")

@bot.message_handler(commands=['stock'])
def handle_stock(message):
    if int(message.from_user.id) != ADMIN_ID:
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
            bot.reply_to(message, "📦 Stock table is currently empty.")
            return

        response = "📦 **Inventory Stock Ledger:**\n\n"
        for row in rows:
            prod_id, category, title, price, status = row
            response += f"🆔 `{prod_id}` | [{category}] **{title}** - ₦{price:.2f} ({status})\n"

        bot.reply_to(message, response[:4000], parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['searchstock'])
def handle_search_stock(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    query = message.text.replace("/searchstock", "").strip()
    if not query:
        bot.reply_to(message, "❌ Format: `/searchstock [keyword]`", parse_mode="Markdown")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title, price, status FROM products WHERE title ILIKE %s OR category ILIKE %s OR data ILIKE %s;", (f"%{query}%", f"%{query}%", f"%{query}%"))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "🔎 No stock records match query.")
            return

        res = f"🔎 **Search Results for '{query}':**\n\n"
        for row in rows:
            res += f"🆔 `{row[0]}` | **{row[1]}** - ₦{row[2]:.2f} ({row[3]})\n"
        bot.reply_to(message, res, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Search Error: {str(e)}")

@bot.message_handler(commands=['editprice'])
def handle_edit_price(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/editprice [product_id] [new_price]`", parse_mode="Markdown")
        return

    prod_id = int(parts[1])
    try:
        new_price = float(parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Price must be a valid number.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE products SET price = %s WHERE id = %s RETURNING title;", (new_price, prod_id))
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"✅ Updated price for `{res[0]}` (ID: `{prod_id}`) to ₦{new_price:.2f}.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Product ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['deleteproduct'])
def handle_delete_product(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/deleteproduct [product_id]`", parse_mode="Markdown")
        return

    prod_id = int(parts[1])

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM products WHERE id = %s RETURNING title;", (prod_id,))
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"🗑️ Product `{res[0]}` (ID: `{prod_id}`) deleted permanently.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Product ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

# --- FINANCIAL CONTROLS & LEDGER ---

@bot.message_handler(commands=['addbalance'])
def handle_add_balance(message):
    if int(message.from_user.id) != ADMIN_ID:
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
        
        cur.execute("INSERT INTO transactions (user_id, product_id, amount, type) VALUES (%s, 0, %s, 'credit');", (target_id, amount))

        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"💰 Credited User `{target_id}` with ₦{amount:.2f}. New Balance: ₦{res[0]:.2f}", parse_mode="Markdown")
            try:
                bot.send_message(target_id, f"🎉 Your wallet has been credited with ₦{amount:.2f}! Balance: ₦{res[0]:.2f}")
            except:
                pass
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['deductbalance'])
def handle_deduct_balance(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/deductbalance [user_id] [amount]`", parse_mode="Markdown")
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
        cur.execute("UPDATE users SET wallet_balance = GREATEST(0, wallet_balance - %s) WHERE telegram_id = %s RETURNING wallet_balance;", (amount, target_id))
        res = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"📉 Debited User `{target_id}` by ₦{amount:.2f}. New Balance: ₦{res[0]:.2f}", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['setbalance'])
def handle_set_balance(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/setbalance [user_id] [amount]`", parse_mode="Markdown")
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
        cur.execute("UPDATE users SET wallet_balance = %s WHERE telegram_id = %s RETURNING wallet_balance;", (amount, target_id))
        res = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"⚙️ Wallet balance for User `{target_id}` set to ₦{res[0]:.2f}", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['saleslog'])
def handle_sales_log(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, t.user_id, t.amount, t.type, t.created_at 
            FROM transactions t ORDER BY t.id DESC LIMIT 15;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "📜 No transactions logged yet.")
            return

        msg = "💳 **Recent Financial Ledger Log:**\n\n"
        for r in rows:
            msg += f"🆔 TX:`{r[0]}` | User:`{r[1]}` | Amount: ₦{r[2]:.2f} ({r[3]})\n"

        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error loading log: {str(e)}")

# --- USER MODERATION & BROADCAST ---

@bot.message_handler(commands=['userinfo'])
def handle_user_info(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/userinfo [user_id]`", parse_mode="Markdown")
        return

    target_id = int(parts[1])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT telegram_id, username, wallet_balance, status, created_at FROM users WHERE telegram_id = %s;", (target_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            msg = (
                f"👤 **User Audit Profile:**\n\n"
                f"🆔 **ID:** `{user[0]}`\n"
                f"👤 **Username:** @{user[1]}\n"
                f"💳 **Wallet Balance:** ₦{user[2]:,.2f}\n"
                f"🚦 **Account Status:** `{user[3]}`\n"
                f"📅 **Registered:** `{user[4]}`"
            )
            bot.reply_to(message, msg, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ User not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['banuser'])
def handle_ban_user(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/banuser [user_id]`", parse_mode="Markdown")
        return

    target_id = int(parts[1])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'banned' WHERE telegram_id = %s RETURNING telegram_id;", (target_id,))
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"🚫 User `{target_id}` is now banned.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['unbanuser'])
def handle_unban_user(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/unbanuser [user_id]`", parse_mode="Markdown")
        return

    target_id = int(parts[1])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'active' WHERE telegram_id = %s RETURNING telegram_id;", (target_id,))
        res = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if res:
            bot.reply_to(message, f"✅ User `{target_id}` has been unbanned.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ User ID not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Database Error: {str(e)}")

@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "❌ Format: `/broadcast [Your message here]`", parse_mode="Markdown")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT telegram_id FROM users WHERE status = 'active';")
        users = cur.fetchall()
        cur.close()
        conn.close()

        success, failed = 0, 0
        for u in users:
            try:
                bot.send_message(u[0], f"📢 **LogVault Announcement:**\n\n{msg_text}", parse_mode="Markdown")
                success += 1
            except:
                failed += 1

        bot.reply_to(message, f"📢 Broadcast Dispatch Finalized:\n✅ Delivered: `{success}`\n❌ Blocked/Failed: `{failed}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Broadcast Error: {str(e)}")

@bot.message_handler(commands=['sql'])
def handle_sql(message):
    if int(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorized.")
        return

    query = message.text.replace("/sql", "").strip()
    if not query:
        bot.reply_to(message, "❌ Format: `/sql [Your PostgreSQL Query]`", parse_mode="Markdown")
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
            bot.reply_to(message, f"📊 **Query Output:**\n`{rows}`", parse_mode="Markdown")
        else:
            conn.commit()
            cur.close()
            conn.close()
            bot.reply_to(message, "✅ Execution Successful.")
    except Exception as e:
        bot.reply_to(message, f"❌ SQL Error: {str(e)}")

# --- PUBLIC CUSTOMER FRONTEND ---

@bot.message_handler(commands=['catalog'])
def handle_catalog(message):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, category, title, price FROM products WHERE status = 'available' ORDER BY category ASC, id ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            bot.reply_to(message, "🛒 Store catalog is empty. Check back soon!")
            return

        response = "🛒 **Available Store Accounts & Inventory:**\n\n"
        current_cat = ""
        for row in rows:
            prod_id, category, title, price = row
            if category != current_cat:
                response += f"\n📁 **--- {category.upper()} ---**\n"
                current_cat = category
            response += f"🆔 `{prod_id}` | **{title}** — ₦{price:.2f}\n👉 `/buy {prod_id}`\n"

        bot.reply_to(message, response, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Catalog Error: {str(e)}")

@bot.message_handler(commands=['balance'])
def handle_balance(message):
    user_id = int(message.from_user.id)
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
        bot.reply_to(message, f"❌ Balance Error: {str(e)}")

@bot.message_handler(commands=['buy'])
def handle_buy(message):
    user_id = int(message.from_user.id)
    parts = message.text.split()

    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Format: `/buy [product_id]`", parse_mode="Markdown")
        return

    prod_id = int(parts[1])

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check User Status
        cur.execute("SELECT status, wallet_balance FROM users WHERE telegram_id = %s;", (user_id,))
        user_res = cur.fetchone()
        
        if user_res and user_res[0] == 'banned':
            bot.reply_to(message, "⛔ Account restriction enabled. Contact store manager.")
            cur.close()
            conn.close()
            return

        user_balance = user_res[1] if user_res else 0.00

        # Check Product Status
        cur.execute("SELECT title, price, data, status FROM products WHERE id = %s;", (prod_id,))
        product = cur.fetchone()

        if not product or product[3] != 'available':
            bot.reply_to(message, "❌ Item unavailable or already sold.")
            cur.close()
            conn.close()
            return

        title, price, account_data, _ = product

        if user_balance < price:
            bot.reply_to(message, f"❌ Insufficient wallet balance!\nPrice: ₦{price:.2f}\nYour Balance: ₦{user_balance:.2f}\n\nTop-up wallet balance via admin.")
            cur.close()
            conn.close()
            return

        # Atomic Transaction Lock
        cur.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE telegram_id = %s;", (price, user_id))
        cur.execute("UPDATE products SET status = 'sold' WHERE id = %s;", (prod_id,))
        cur.execute("INSERT INTO transactions (user_id, product_id, amount, type) VALUES (%s, %s, %s, 'purchase');", (user_id, prod_id, price))

        conn.commit()
        cur.close()
        conn.close()

        delivery = (
            f"🎉 **Purchase Successful!**\n\n"
            f"📦 **Product:** {title}\n"
            f"💰 **Price:** ₦{price:.2f}\n\n"
            f"🔐 **Delivered Data:**\n`{account_data}`"
        )
        bot.reply_to(message, delivery, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Transaction Error: {str(e)}")

@bot.message_handler(commands=['history'])
def handle_history(message):
    user_id = int(message.from_user.id)
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
            bot.reply_to(message, "📜 No purchase transactions recorded.")
            return

        msg = "📜 **Your Purchase Order History:**\n\n"
        for row in rows:
            tx_id, title, amount, date = row
            msg += f"🆔 `{tx_id}` | **{title}** — ₦{amount:.2f}\n"

        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error loading history: {str(e)}")

# --- RUNTIME THREAD & SERVER ---

def start_polling():
    print("Flushing webhooks...")
    bot.remove_webhook()
    print("Initiating bot polling loop...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling Exception Caught: {e}")
            time.sleep(5)

if __name__ == "__main__":
    init_db()

    t = threading.Thread(target=start_polling)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
