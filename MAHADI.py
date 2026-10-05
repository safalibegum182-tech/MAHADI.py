import os
import re
import sqlite3
import logging
import random
import tempfile
from datetime import datetime, timezone

from gtts import gTTS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("RIYA")

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN is missing. Add TOKEN in Railway Variables.")

OWNER_IDS = {8136997138, 8827019486}
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "riya_bot.db")

db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row


def db_exec(sql, params=(), fetch=False):
    cur = db.cursor()
    cur.execute(sql, params)
    db.commit()
    return cur.fetchall() if fetch else cur.lastrowid


def init_db():
    db_exec("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        blocked INTEGER DEFAULT 0,
        created_at TEXT,
        last_seen TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS admins(
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        created_at TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS replies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT UNIQUE,
        response TEXT,
        enabled INTEGER DEFAULT 1
    )""")


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    d = datetime.now(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def register(user):
    if not user:
        return
    row = db_exec("SELECT user_id FROM users WHERE user_id=?", (user.id,), True)
    if row:
        db_exec(
            "UPDATE users SET first_name=?, username=?, last_seen=? WHERE user_id=?",
            (user.first_name or "", user.username or "", now(), user.id)
        )
    else:
        db_exec(
            "INSERT INTO users(user_id,first_name,username,created_at,last_seen) VALUES(?,?,?,?,?)",
            (user.id, user.first_name or "", user.username or "", now(), now())
        )


def usage(user_id):
    db_exec("INSERT INTO usage(user_id,created_at) VALUES(?,?)", (user_id, now()))


def blocked(uid):
    rows = db_exec("SELECT blocked FROM users WHERE user_id=?", (uid,), True)
    return bool(rows and rows[0]["blocked"])


def owner(uid):
    return uid in OWNER_IDS


def admin(uid):
    if owner(uid):
        return True
    return bool(db_exec("SELECT user_id FROM admins WHERE user_id=?", (uid,), True))


def clean_voice(text):
    # Remove emoji and variation/joiner characters so gTTS speaks only text.
    text = re.sub(
        r"[\U0001F1E0-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\u200D\uFE0F\u20E3]+",
        " ",
        text
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_voice(text):
    clean = clean_voice(text)
    if not clean:
        return None
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        gTTS(clean, lang="bn", slow=False).save(path)
        return path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        return None


async def send_text_voice(message, text, voice=True):
    await message.reply_text(text)
    if not voice:
        return
    path = make_voice(text)
    if not path:
        return
    try:
        with open(path, "rb") as f:
            await message.reply_voice(voice=f)
    except Exception as exc:
        logger.warning("Voice failed: %s", exc)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def user_keyboard(bot_username):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "➕ Add Your Group",
            url=f"https://t.me/{bot_username}?startgroup=true"
        )],
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("🌹 Rose", callback_data="rose")
        ],
        [
            InlineKeyboardButton("😂 Joke", callback_data="joke"),
            InlineKeyboardButton("💖 Love", callback_data="love")
        ]
    ])


def dashboard_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="stats"),
            InlineKeyboardButton("👥 Users", callback_data="users")
        ],
        [
            InlineKeyboardButton("🚫 Block", callback_data="block"),
            InlineKeyboardButton("✅ Unblock", callback_data="unblock")
        ],
        [
            InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")
        ],
        [InlineKeyboardButton("👑 Admin List", callback_data="admin_list")],
        [InlineKeyboardButton("💬 Reply System", callback_data="reply_menu")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="dashboard")]
    ])


def back_dashboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Dashboard", callback_data="dashboard")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user = update.effective_user
    register(user)
    if blocked(user.id):
        await update.message.reply_text("🚫 আপনার account blocked করা হয়েছে।")
        return
    usage(user.id)
    bot = await context.bot.get_me()
    text = (
        f"🌟 হ্যালো {user.first_name or 'বন্ধু'}!\n\n"
        "🤖 আমি RIYA Bot। নিচের button ব্যবহার করো।\n\n"
        "➕ Add Your Group চাপলে bot-কে group-এ add করতে পারবে।\n"
        "Group-এ bot-কে admin permission দিতে হবে।"
    )
    await update.message.reply_text(text, reply_markup=user_keyboard(bot.username))


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    register(user)
    if not admin(user.id):
        await update.message.reply_text("🚫 এই panel শুধুমাত্র admin/owner-এর জন্য।")
        return
    await show_dashboard(update.message)


async def show_dashboard(message):
    total = db_exec("SELECT COUNT(*) c FROM users", fetch=True)[0]["c"]
    active = db_exec(
        "SELECT COUNT(DISTINCT user_id) c FROM usage WHERE created_at>=?",
        (today(),), True
    )[0]["c"]
    uses = db_exec("SELECT COUNT(*) c FROM usage", fetch=True)[0]["c"]
    extra_admins = db_exec("SELECT COUNT(*) c FROM admins", fetch=True)[0]["c"]
    text = (
        "👑 RIYA BOT ADMIN PANEL\n\n"
        f"👥 Total Users: {total}\n"
        f"📅 Today Active: {active}\n"
        f"📈 Total Uses: {uses}\n"
        f"👑 Owners: {len(OWNER_IDS)}\n"
        f"🛡 Extra Admins: {extra_admins}"
    )
    await message.reply_text(text, reply_markup=dashboard_keyboard())


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    register(user)
    data = q.data

    if data == "help":
        await q.edit_message_text(
            "📖 Help\n\n"
            "➕ Add Your Group — group-এ bot add করার জন্য\n"
            "🌹 Rose — rose message\n"
            "😂 Joke — joke\n"
            "💖 Love — friendly message",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="home")]]
            )
        )
        return

    if data == "home":
        bot = await context.bot.get_me()
        await q.edit_message_text(
            "🌟 RIYA Bot Home",
            reply_markup=user_keyboard(bot.username)
        )
        return

    if data == "rose":
        await q.message.reply_text(random.choice([
            "🌹 তোমার জন্য একটি সুন্দর গোলাপ!",
            "🌹💐 তোমার দিনটা সুন্দর হোক।"
        ]))
        return

    if data == "joke":
        await q.message.reply_text(random.choice([
            "😂 শিক্ষক: পড়া শিখেছো? ছাত্র: স্যার, বই খুলেছি—এটাই অনেক!",
            "🤣 আমার WiFi এত slow যে Google-ও ভাবছে আমি offline!"
        ]))
        return

    if data == "love":
        await q.message.reply_text("💖 ভালো থেকো, হাসিখুশি থেকো এবং সবাইকে সম্মান করো।")
        return

    if not admin(user.id):
        await q.answer("🚫 Admin access required.", show_alert=True)
        return

    if data == "dashboard":
        await q.edit_message_text("👑 RIYA BOT ADMIN PANEL", reply_markup=dashboard_keyboard())
        return

    if data == "stats":
        total = db_exec("SELECT COUNT(*) c FROM users", fetch=True)[0]["c"]
        active = db_exec(
            "SELECT COUNT(DISTINCT user_id) c FROM usage WHERE created_at>=?",
            (today(),), True
        )[0]["c"]
        uses = db_exec("SELECT COUNT(*) c FROM usage", fetch=True)[0]["c"]
        blocked_count = db_exec("SELECT COUNT(*) c FROM users WHERE blocked=1", fetch=True)[0]["c"]
        await q.edit_message_text(
            f"📊 STATISTICS\n\n👥 Users: {total}\n🟢 Today Active: {active}\n"
            f"📈 Total Uses: {uses}\n🚫 Blocked: {blocked_count}",
            reply_markup=back_dashboard()
        )
        return

    if data == "users":
        rows = db_exec(
            "SELECT user_id,first_name,username,blocked FROM users ORDER BY last_seen DESC LIMIT 30",
            fetch=True
        )
        if not rows:
            text = "👥 No users."
        else:
            parts = ["👥 RECENT USERS\n"]
            for r in rows:
                name = r["first_name"] or "Unknown"
                un = f" @{r['username']}" if r["username"] else ""
                status = "🚫" if r["blocked"] else "🟢"
                parts.append(f"{status} {name}{un}\nID: {r['user_id']}")
            text = "\n".join(parts)
        await q.edit_message_text(text, reply_markup=back_dashboard())
        return

    if data in {"block", "unblock", "add_admin", "remove_admin"}:
        if data in {"add_admin", "remove_admin"} and not owner(user.id):
            await q.answer("শুধু owner এই কাজ করতে পারে।", show_alert=True)
            return
        context.user_data["action"] = data
        prompts = {
            "block": "🚫 যেই user-কে block করতে চাও তার Telegram ID পাঠাও।",
            "unblock": "✅ যেই user-কে unblock করতে চাও তার Telegram ID পাঠাও।",
            "add_admin": "➕ নতুন admin-এর Telegram ID পাঠাও।",
            "remove_admin": "➖ যে admin-কে remove করতে চাও তার Telegram ID পাঠাও।"
        }
        await q.message.reply_text(prompts[data])
        return

    if data == "admin_list":
        rows = db_exec("SELECT user_id FROM admins ORDER BY added_at", fetch=True)
        text = "👑 OWNERS\n\n" + "\n".join(f"👑 {x}" for x in sorted(OWNER_IDS))
        text += "\n\n🛡 EXTRA ADMINS\n"
        text += "\n".join(f"🛡 {r['user_id']}" for r in rows) if rows else "None"
        await q.edit_message_text(text, reply_markup=back_dashboard())
        return

    if data == "reply_menu":
        await q.edit_message_text(
            "💬 REPLY SYSTEM",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Reply", callback_data="reply_add")],
                [InlineKeyboardButton("📋 View Replies", callback_data="reply_list")],
                [InlineKeyboardButton("🗑 Delete Reply", callback_data="reply_delete")],
                [InlineKeyboardButton("⬅️ Dashboard", callback_data="dashboard")]
            ])
        )
        return

    if data == "reply_add":
        context.user_data["action"] = "reply_add"
        await q.message.reply_text(
            "➕ এই format-এ পাঠাও:\n\nkeyword | reply message\n\n"
            "Example:\nhello | Hi! Welcome."
        )
        return

    if data == "reply_list":
        rows = db_exec("SELECT id,keyword,response,enabled FROM replies ORDER BY id DESC", fetch=True)
        if not rows:
            text = "💬 No replies."
        else:
            text = "💬 AUTO REPLIES\n\n" + "\n".join(
                f"#{r['id']} | {r['keyword']} | {'ON' if r['enabled'] else 'OFF'}\n↳ {r['response']}"
                for r in rows
            )
        await q.edit_message_text(
            text[:3900],
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Reply Menu", callback_data="reply_menu")]]
            )
        )
        return

    if data == "reply_delete":
        context.user_data["action"] = "reply_delete"
        await q.message.reply_text("🗑 যে reply delete করতে চাও তার ID পাঠাও।")
        return

    if data == "broadcast":
        if not owner(user.id):
            await q.answer("শুধু owner broadcast করতে পারবে।", show_alert=True)
            return
        context.user_data["action"] = "broadcast"
        await q.message.reply_text("📢 যে message broadcast করতে চাও সেটি পাঠাও।")
        return


async def private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    register(user)

    if blocked(user.id):
        await update.message.reply_text("🚫 আপনার account blocked করা হয়েছে।")
        return

    state = context.user_data.get("action")
    text = update.message.text.strip()

    if admin(user.id) and state:
        action = state

        if action in {"block", "unblock", "add_admin", "remove_admin"}:
            try:
                target = int(text)
            except ValueError:
                await update.message.reply_text("❌ শুধু numeric Telegram ID পাঠাও।")
                return

            if action == "block":
                if target in OWNER_IDS:
                    await update.message.reply_text("❌ Owner-কে block করা যাবে না।")
                else:
                    db_exec("UPDATE users SET blocked=1 WHERE user_id=?", (target,))
                    await update.message.reply_text(f"🚫 {target} blocked.")
            elif action == "unblock":
                db_exec("UPDATE users SET blocked=0 WHERE user_id=?", (target,))
                await update.message.reply_text(f"✅ {target} unblocked.")
            elif action == "add_admin":
                if not owner(user.id):
                    await update.message.reply_text("🚫 শুধু owner পারবে।")
                elif target in OWNER_IDS:
                    await update.message.reply_text("ℹ️ এটি already owner.")
                else:
                    db_exec(
                        "INSERT OR REPLACE INTO admins(user_id,added_by,added_at) VALUES(?,?,?)",
                        (target, user.id, now())
                    )
                    await update.message.reply_text(f"✅ {target} added as admin.")
            elif action == "remove_admin":
                if target in OWNER_IDS:
                    await update.message.reply_text("❌ Owner remove করা যাবে না।")
                else:
                    db_exec("DELETE FROM admins WHERE user_id=?", (target,))
                    await update.message.reply_text(f"✅ {target} removed.")
            context.user_data.pop("action", None)
            return

        if action == "reply_add":
            if "|" not in text:
                await update.message.reply_text("❌ Format: keyword | reply message")
                return
            keyword, response = [x.strip() for x in text.split("|", 1)]
            if not keyword or not response:
                await update.message.reply_text("❌ দুটো অংশই দিতে হবে।")
                return
            db_exec(
                "INSERT OR REPLACE INTO replies(keyword,response,enabled) VALUES(?,?,1)",
                (keyword.lower(), response)
            )
            context.user_data.pop("action", None)
            await update.message.reply_text("✅ Auto-reply saved.")
            return

        if action == "reply_delete":
            try:
                rid = int(text)
            except ValueError:
                await update.message.reply_text("❌ Reply ID দাও।")
                return
            db_exec("DELETE FROM replies WHERE id=?", (rid,))
            context.user_data.pop("action", None)
            await update.message.reply_text(f"🗑 Reply #{rid} deleted.")
            return

        if action == "broadcast":
            if not owner(user.id):
                await update.message.reply_text("🚫 শুধু owner broadcast করতে পারে।")
                context.user_data.pop("action", None)
                return
            rows = db_exec("SELECT user_id FROM users WHERE blocked=0", fetch=True)
            sent = failed = 0
            await update.message.reply_text("📢 Broadcast শুরু হয়েছে...")
            for row in rows:
                try:
                    await context.bot.send_message(row["user_id"], text)
                    sent += 1
                except Exception:
                    failed += 1
            context.user_data.pop("action", None)
            await update.message.reply_text(
                f"📢 Broadcast complete.\n\n✅ Sent: {sent}\n❌ Failed: {failed}"
            )
            return

    usage(user.id)
    lower = text.lower()
    if "hello" in lower or lower == "hi":
        reply = "হ্যালো! কেমন আছো?"
    elif "কেমন আছো" in lower:
        reply = "আমি ভালো আছি। তুমি কেমন আছো?"
    elif "জোক" in lower or "joke" in lower:
        reply = "😂 শিক্ষক: পড়া শিখেছো? ছাত্র: স্যার, বই খুলেছি—এটাই অনেক!"
    elif "গোলাপ" in lower or "rose" in lower:
        reply = "🌹 তোমার জন্য একটি সুন্দর গোলাপ!"
    else:
        reply = "🤖 তোমার message পেয়েছি। নিচের button ব্যবহার করে features ব্যবহার করতে পারো।"
    await send_text_voice(update.message, reply, voice=True)


async def group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if user:
        register(user)
    text = update.message.text.lower()
    rows = db_exec(
        "SELECT keyword,response FROM replies WHERE enabled=1 ORDER BY LENGTH(keyword) DESC",
        fetch=True
    )
    for row in rows:
        if row["keyword"].lower() in text:
            await update.message.reply_text(row["response"])
            return


async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"🌟 Welcome {member.first_name or 'বন্ধু'}!\nRIYA Bot group-এ active হয়েছে।"
        )


async def error_handler(update, context):
    logger.error("Telegram error: %s", context.error)


def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Only two commands: /start and /dashboard.
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))

    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_members
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            private_text
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            group_text
        )
    )

    app.add_error_handler(error_handler)

    logger.info("RIYA Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
