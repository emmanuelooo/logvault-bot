import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
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

# Conversation States for Add Product Wizard
CATEGORY, TITLE, PRICE, DATA = range(4)

def get_db_connection():
    """Establish and return a database connection."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """Initialize DB tables and auto-patch existing schemas."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
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
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100) DEFAULT 'General';")
        cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'available';")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                wallet_balance NUMERIC(10, 2) DEFAULT 0.00,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
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
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def ensure_user_exists(conn, user_id: int, username: str = "Unknown"):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, username, wallet_balance) 
        VALUES (%s, %s, 0.00) 
        ON CONFLICT (telegram_id) DO NOTHING;
    """, (user_id, username))
    cur.close()

# --- COMMAND & MENU HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db_connection()
    ensure_user_exists(conn, user.id, user.username or "User")
    conn.commit()
    conn.close()

    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("🛒 View Catalog", callback_data="menu_catalog"),
             InlineKeyboardButton("💳 Check Balance", callback_data="menu_balance")],
            [InlineKeyboardButton("➕ Add Product Wizard", callback_data="wizard_start"),
             InlineKeyboardButton("📦 Stock Control", callback_data="admin_stock")],
            [InlineKeyboardButton("💰 Financial Ledger", callback_data="admin_finance"),
             InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"⚡ *LogVault Admin Dashboard*\nWelcome, {user.first_name}! Tap an option below:"
    else:
        keyboard = [
            [InlineKeyboardButton("🛒 Browse Catalog", callback_data="menu_catalog"),
             InlineKeyboardButton("💳 My Wallet Balance", callback_data="menu_balance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"👋 Welcome to LogVault, {user.first_name}!\nChoose an option below:"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        target_message = query.message
    else:
        target_message = update.message

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
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")]]
            await target_message.reply_text("📦 *Catalog Status*: No active stock currently available.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        response = "🛒 *Available Product Catalog*\nTap any item below to purchase instantly:\n"
        keyboard = []
        for p in products:
            keyboard.append([InlineKeyboardButton(f"[{p['category']}] {p['title']} — ₦{p['price']:,.2f}", callback_data=f"buy_item_{p['id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await target_message.reply_text(response, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        await target_message.reply_text(f"❌ *Catalog Error*: `{e}`", parse_mode="Markdown")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        uid = query.from_user.id
        target_msg = query.message
    else:
        uid = update.effective_user.id
        target_msg = update.message

    conn = get_db_connection()
    cur = conn.cursor()
    ensure_user_exists(conn, uid, update.effective_user.username if not query else query.from_user.username or "User")
    conn.commit()
    cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (uid,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    bal = res['wallet_balance'] if res else 0.00
    keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"💳 *Your Wallet Balance*: ₦{bal:,.2f}"
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await target_msg.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


# --- STEP-BY-STEP ADD PRODUCT WIZARD (CONVERSATION HANDLER) ---

async def wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Unauthorized", show_alert=True)
        return
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Socials", callback_data="cat_Socials"),
         InlineKeyboardButton("VPN", callback_data="cat_VPN")],
        [InlineKeyboardButton("Streaming", callback_data="cat_Streaming"),
         InlineKeyboardButton("General", callback_data="cat_General")],
        [InlineKeyboardButton("❌ Cancel Wizard", callback_data="menu_main")]
    ]
    await query.message.edit_text("➕ *Add Product Wizard*\nStep 1/4: Select or type category:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CATEGORY

async def wizard_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    context.user_data['wizard_category'] = cat
    
    await query.message.edit_text(f"Selected Category: *{cat}*\n\nStep 2/4: Send the product *Title* (e.g., Netflix UHD Account):", parse_mode="Markdown")
    return TITLE

async def wizard_category_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['wizard_category'] = update.message.text.strip()
    await update.message.reply_text("Step 2/4: Send the product *Title* (e.g., Netflix UHD Account):", parse_mode="Markdown")
    return TITLE

async def wizard_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['wizard_title'] = update.message.text.strip()
    await update.message.reply_text("Step 3/4: Send the product *Price* in Naira numbers only (e.g., 1500):", parse_mode="Markdown")
    return PRICE

async def wizard_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data['wizard_price'] = price
    except ValueError:
        await update.message.reply_text("⚠️ Invalid amount. Send numbers only for price (e.g., 2000):")
        return PRICE

    await update.message.reply_text("Step 4/4: Send the item *Data / Credentials* (e.g., email:password or license key):", parse_mode="Markdown")
    return DATA

async def wizard_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.text.strip()
    cat = context.user_data.get('wizard_category', 'General')
    title = context.user_data.get('wizard_title')
    price = context.user_data.get('wizard_price')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO products (category, title, price, data, status)
            VALUES (%s, %s, %s, %s, 'available') RETURNING id;
        """, (cat, title, price, data))
        pid = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()

        keyboard = [[InlineKeyboardButton("➕ Add Another", callback_data="wizard_start"),
                     InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")]]
        
        await update.message.reply_text(
            f"✅ *Product Successfully Created!*\n\n"
            f"• ID: `{pid}`\n• Category: *{cat}*\n• Title: *{title}*\n• Price: ₦{price:,.2f}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Database error: `{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ Product wizard cancelled.", parse_mode="Markdown")
    return ConversationHandler.END


# --- CALLBACK ROUTER FOR BUTTON TAPS ---

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "menu_main":
        await start_command(update, context)
    elif data == "menu_catalog":
        await catalog_command(update, context)
    elif data == "menu_balance":
        await balance_command(update, context)
    elif data.startswith("buy_item_"):
        pid = int(data.replace("buy_item_", ""))
        await process_purchase(query, uid, pid)
    elif data == "admin_stock":
        await show_stock_panel(query)
    elif data == "admin_finance":
        await query.edit_message_text("💰 *Financial Ledger*\nTo top up a user via chat, reply or use command/sql.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_main")]]), parse_mode="Markdown")
    elif data == "admin_analytics":
        await show_analytics(query)

async def process_purchase(query, uid, pid):
    conn = get_db_connection()
    cur = conn.cursor()
    ensure_user_exists(conn, uid, query.from_user.username or "User")
    conn.commit()

    cur.execute("SELECT * FROM products WHERE id = %s AND status = 'available';", (pid,))
    prod = cur.fetchone()

    if not prod:
        await query.message.reply_text("❌ Product is no longer available or already sold.")
        cur.close()
        conn.close()
        return

    cur.execute("SELECT wallet_balance FROM users WHERE telegram_id = %s;", (uid,))
    user_bal = cur.fetchone()['wallet_balance']

    if user_bal < prod['price']:
        keyboard = [[InlineKeyboardButton("🔙 Back to Catalog", callback_data="menu_catalog")]]
        await query.edit_message_text(
            f"❌ *Insufficient Funds!*\nPrice: ₦{prod['price']:,.2f} | Your Balance: ₦{user_bal:,.2f}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        cur.close()
        conn.close()
        return

    try:
        cur.execute("UPDATE users SET wallet_balance = wallet_balance - %s WHERE telegram_id = %s;", (prod['price'], uid))
        cur.execute("UPDATE products SET status = 'sold' WHERE id = %s;", (pid,))
        cur.execute("INSERT INTO transactions (user_id, product_id, amount, type) VALUES (%s, %s, %s, 'purchase');", (uid, pid, prod['price']))
        conn.commit()

        keyboard = [[InlineKeyboardButton("🛒 Browse More", callback_data="menu_catalog"),
                     InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")]]
        
        await query.edit_message_text(
            f"🎉 *Purchase Successful!*\n\n"
            f"📦 *Item*: {prod['title']}\n"
            f"💰 *Cost*: ₦{prod['price']:,.2f}\n\n"
            f"🔑 *Your Credentials*:\n`{prod['data']}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        conn.rollback()
        await query.message.reply_text(f"❌ Error processing transaction: `{e}`")
    finally:
        cur.close()
        conn.close()

async def show_stock_panel(query):
    if not is_admin(query.from_user.id):
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total, status FROM products GROUP BY status;")
    stats = cur.fetchall()
    cur.close()
    conn.close()
    
    stat_text = "\n".join([f"• `{s['status']}`: {s['total']}" for s in stats])
    keyboard = [
        [InlineKeyboardButton("➕ Add Product via Wizard", callback_data="wizard_start")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]
    ]
    await query.edit_message_text(f"📦 *Stock Management Panel*\n\nInventory breakdown:\n{stat_text}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_analytics(query):
    if not is_admin(query.from_user.id):
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as users_count FROM users;")
    u_count = cur.fetchone()['users_count']
    cur.execute("SELECT COUNT(*) as sales_count, SUM(amount) as revenue FROM transactions WHERE type='purchase';")
    tx = cur.fetchone()
    cur.close()
    conn.close()

    rev = tx['revenue'] if tx['revenue'] else 0.00
    keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
    await query.edit_message_text(
        f"📊 *Business Analytics Dashboard*\n\n"
        f"👥 Total Users: `{u_count}`\n"
        f"🛒 Total Sales: `{tx['sales_count']}`\n"
        f"💰 Total Revenue: `₦{rev:,.2f}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


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

    # Start dummy HTTP server in background thread for Render
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Wizard Handler for adding products interactively
    add_product_wizard = ConversationHandler(
        entry_points=[CallbackQueryHandler(wizard_start, pattern="^wizard_start$")],
        states={
            CATEGORY: [
                CallbackQueryHandler(wizard_category, pattern="^cat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_category_text)
            ],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_title)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_price)],
            DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_save)],
        },
        fallbacks=[CallbackQueryHandler(wizard_cancel, pattern="^menu_main$")],
    )

    # Register Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(add_product_wizard)
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Initiating interactive button bot polling loop...")
    app.run_polling()

if __name__ == "__main__":
    main()
