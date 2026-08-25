import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Enable Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

def get_db_connection():
    """Establish and return a database connection."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """Initialize DB tables and auto-patch existing schemas."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Products Table
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
        # Auto-patch legacy schema columns
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'General';")
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'available';")
        
        # 2. Users Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                wallet_balance NUMERIC(10, 2) DEFAULT 0.00,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Transactions Table
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
        logger.info("Database schema initialized and verified successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def is_admin(user_id: int) -> bool:
    """Check if telegram user ID is in admin list."""
    return user_id in ADMIN_IDS

def ensure_user_exists(conn, user_id: int, username: str = "Unknown"):
    """Auto-register user if not present in users table."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, username, wallet_balance) 
        VALUES (%s, %s, 0.00) 
        ON CONFLICT (telegram_id) DO NOTHING;
    """, (user_id, username))
    cur.close()

# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db_connection()
    ensure_user_exists(conn, user.id, user.username or "User")
    conn.commit()
    conn.close()

    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("📦 Stock Control", callback_data="admin_stock"),
             InlineKeyboardButton("💰 Financial Ledger", callback_data="admin_finance")],
            [InlineKeyboardButton("👤 User Moderation", callback_data="admin_users"),
             InlineKeyboardButton("📊 Business Analytics", callback_data="admin_analytics")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚡ *LogVault Admin Dashboard*\nWelcome, Admin {user.first_name}!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"👋 Welcome to LogVault, {user.first_name}!\nUse `/catalog` to browse items or `/balance` to check your wallet.",
            parse_mode="Markdown"
        )

async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, category, title, price 
            FROM products 
            WHERE status = 'available' 
            ORDER BY category, id ASC;
        """)
        products = cur.fetchall()
        cur.close()
        conn.close()

        if not products:
            await update.message.reply_text("📦 *Catalog Status*: No active stock currently available.", parse_mode="Markdown")
            return

        response = "🛒 *Available Product Catalog*\n\n"
        current_cat = None
        for p in products:
            if p['category'] != current_cat:
                current_cat = p['category']
                response += f"\n📂 *Category: {current_cat}*\n"
            response += f"• ID `{p['id']}` — *{p['title']}* | ₦{p['price']:,.2f}\n"

        response += "\nTo purchase, use: `/buy [product_id]`"
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Catalog Error*: `{e}`", parse_mode="Markdown")

async def addproduct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text.replace("/addproduct", "").strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    parsed = {}
    data_lines = []
    is_data = False
    
    for line in lines:
        if line.lower().startswith("data:"):
            is_data = True
            continue
        if is_data:
            data_lines.append(line)
        elif ":" in line:
            k, v = line.split(":", 1)
            parsed[k.strip().lower()] = v.strip()

    category = parsed.get("category", "General")
    title = parsed.get("title")
    price = parsed.get("price")
    data = "\n".join(data_lines).strip()

    if not title or not price or not data:
        await update.message.reply_text(
            "⚠️ *Format Error*\nUse format:\n"
            "```text\n"
            "/addproduct\n"
            "Category: Socials\n"
            "Title: Premium Account\n"
            "Price: 1000\n"
            "Data:\n"
            "user:pass\n"
            "```",
            parse_mode="Markdown"
        )
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO products (category, title, price, data, status)
            VALUES (%s, %s, %s, %s, 'available') RETURNING id;
        """, (category, title, float(price), data))
        pid = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Product ID `{pid}` added under *{category}* at ₦{float(price):,.2f}.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Database Error*: `{e}`", parse_mode="Markdown")

async def bulkadd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text.replace("/bulkadd", "").strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    parsed = {}
    item_lines = []
    is_items = False
    
    for line in lines:
        if line.lower().startswith("items:"):
            is_items = True
            continue
        if is_items:
            item_lines.append(line)
        elif ":" in line:
            k, v = line.split(":", 1)
            parsed[k.strip().lower()] = v.strip()

    category = parsed.get("category", "General")
    title = parsed.get("title")
    price = parsed.get("price")

    if not title or not price or not item_lines:
        await update.message.reply_text(
            "⚠️ *Format Error*\nUse format:\n"
            "```text\n"
            "/bulkadd\n"
            "Category: VPN\n"
            "Title: ExpressVPN Key\n"
            "Price: 1500\n"
            "Items:\n"
            "key1\n"
            "key2\n"
            "```",
            parse_mode="Markdown"
        )
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        count = 0
        for item in item_lines:
            cur.execute("""
                INSERT INTO products (category, title, price, data, status)
                VALUES (%s, %s, %s, %s, 'available');
            """, (category, title, float(price), item))
            count += 1
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"⚡ *Bulk Upload Success!*\nImported {count} items under *{title}* at ₦{float(price):,.2f} each.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Database Error*: `{e}`", parse_mode="Markdown")

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, category, title, price, status FROM products ORDER BY id DESC LIMIT 20;")
        products = cur.fetchall()
        cur.close()
        conn.close()

        if not products:
            await update.message.reply_text("📦 *Stock Empty*", parse_mode="Markdown")
            return

        res = "📦 *Recent Active Stock Listings*\n\n"
        for p in products:
            res += f"• ID `{p['id']}` | [{p['category']}] *{p['title']}* — ₦{p['price']:,.2f} | `{p['status']}`\n"

        await update.message.reply_text(res, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Database Error*: `{e}`", parse_mode="Markdown")

async def addbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Usage: `/addbalance [user_telegram_id] [amount]`", parse_mode="Markdown")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Auto-upsert target user if not present
        ensure_user_exists(conn, target_id, "User")
        
        cur.execute("UPDATE users SET wallet_balance = wallet_balance + %s WHERE telegram_id = %s;", (amount, target_id))
        cur.execute("INSERT INTO transactions (user_id, amount, type) VALUES (%s, %s, 'deposit');", (target_id, amount))
        
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"💰 Balance updated! Added ₦{amount:,.2f} to user `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Database Error*: `{e}`", parse_mode="Markdown")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    ensure_user_exists(conn, uid, update.effective_user.username or "User")
    conn.commit()
    cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (uid,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    bal = res['wallet_balance'] if res else 0.00
    await update.message.reply_text(f"💳 *Wallet Balance*: ₦{bal:,.2f}", parse_mode="Markdown")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        pid = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Usage: `/buy [product_id]`", parse_mode="Markdown")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    ensure_user_exists(conn, uid, update.effective_user.username or "User")
    conn.commit()
    
    # Check Product
    cur.execute("SELECT * FROM products WHERE id = %s AND status = 'available';", (pid,))
    prod = cur.fetchone()

    if not prod:
        await update.message.reply_text("❌ Product unavailable or already sold.", parse_mode="Markdown")
        cur.close()
        conn.close()
        return

    # Check Balance
    cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (uid,))
    user_bal = cur.fetchone()['wallet_balance']

    if user_bal < prod['price']:
        await update.message.reply_text(f"❌ Insufficient funds! Price: ₦{prod['price']:,.2f} | Balance: ₦{user_bal:,.2f}", parse_mode="Markdown")
        cur.close()
        conn.close()
        return

    # Execute Order Transaction
    try:
        cur.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE telegram_id = %s;", (prod['price'], uid))
        cur.execute("UPDATE products SET status = 'sold' WHERE id = %s;", (pid,))
        cur.execute("INSERT INTO transactions (user_id, product_id, amount, type) VALUES (%s, %s, %s, 'purchase');", (uid, pid, prod['price']))
        conn.commit()

        await update.message.reply_text(
            f"🎉 *Purchase Successful!*\n\n"
            f"📦 *Product*: {prod['title']}\n"
            f"💰 *Price*: ₦{prod['price']:,.2f}\n\n"
            f"🔑 *Credentials / Data*:\n`{prod['data']}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        conn.rollback()
        await update.message.reply_text(f"❌ Purchase processing failed: `{e}`", parse_mode="Markdown")
    finally:
        cur.close()
        conn.close()

async def sql_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    query = update.message.text.replace("/sql", "").strip()
    if not query:
        await update.message.reply_text("⚠️ Usage: `/sql [SQL Query]`", parse_mode="Markdown")
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        
        if cur.description:
            rows = cur.fetchall()
            res = f"📊 *Query Result*:\n`{rows}`"
        else:
            res = "✅ Query executed successfully."
            
        cur.close()
        conn.close()
        await update.message.reply_text(res, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *SQL Error*: `{e}`", parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Unauthorized")
        return

    if query.data == "admin_stock":
        msg = "📦 *Stock Control*\n• Use `/addproduct` to add 1 item\n• Use `/bulkadd` to upload batch items\n• Use `/stock` to view current stock"
    elif query.data == "admin_finance":
        msg = "💰 *Financial Ledger*\n• Use `/addbalance [id] [amount]` to top up users"
    elif query.data == "admin_users":
        msg = "👤 *User Moderation*\n• Run `/sql SELECT * FROM users;` to inspect all users"
    elif query.data == "admin_analytics":
        msg = "📊 *Analytics Panel*\n• Run `/sql SELECT COUNT(*), SUM(amount) FROM transactions;`"
    else:
        msg = "Dashboard menu selected."

    await query.edit_message_text(msg, parse_mode="Markdown")


# --- DUMMY HTTP SERVER FOR RENDER PORT CHECK ---

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and polling!")

def run_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Dummy health check server running on port {port}")
    server.serve_forever()


def main():
    logger.info("Initializing database...")
    init_db()

    # Start dummy HTTP server in a background thread to satisfy Render's port scan
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("addproduct", addproduct_command))
    app.add_handler(CommandHandler("bulkadd", bulkadd_command))
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CommandHandler("addbalance", addbalance_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("sql", sql_command))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Initiating bot polling loop...")
    app.run_polling()

if __name__ == "__main__":
    main()
