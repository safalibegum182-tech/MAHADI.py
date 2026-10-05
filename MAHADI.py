import os
import re
import sqlite3
import logging
import random
import tempfile
from datetime import datetime, timezone, timedelta

from gtts import gTTS

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "TOKEN missing. Add TOKEN in Railway Variables."
    )


# দুইজন BOT OWNER
OWNER_IDS = {
    8136997138,
    8827019486,
}


# Railway Volume ব্যবহার করলে DATA_DIR variable দিতে পারো।
# না দিলে বর্তমান project folder-এ database হবে।
DATA_DIR = os.getenv("DATA_DIR", ".")

os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "riya_bot.db")


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("RIYA")


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(
    DB_FILE,
    check_same_thread=False
)

db.row_factory = sqlite3.Row


def db_execute(query, params=(), fetch=False, many=False):
    cur = db.cursor()

    if many:
        cur.executemany(query, params)
    else:
        cur.execute(query, params)

    db.commit()

    if fetch:
        return cur.fetchall()

    return cur.lastrowid


def init_database():

    db_execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            is_blocked INTEGER DEFAULT 0,
            created_at TEXT,
            last_seen TEXT
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT
        )
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            response TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc).isoformat()


def today_start_utc():

    now = datetime.now(timezone.utc)

    start = datetime(
        now.year,
        now.month,
        now.day,
        tzinfo=timezone.utc
    )

    return start.isoformat()


# =========================================================
# USER MANAGEMENT
# =========================================================

def register_user(user):

    if not user:
        return

    uid = user.id
    first_name = user.first_name or ""
    username = user.username or ""
    current = now_utc()

    existing = db_execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (uid,),
        fetch=True
    )

    if existing:

        db_execute("""
            UPDATE users
            SET first_name=?,
                username=?,
                last_seen=?
            WHERE user_id=?
        """, (
            first_name,
            username,
            current,
            uid
        ))

    else:

        db_execute("""
            INSERT INTO users
            (user_id, first_name, username, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
        """, (
            uid,
            first_name,
            username,
            current,
            current
        ))


def log_usage(user_id):

    db_execute("""
        INSERT INTO usage
        (user_id, created_at)
        VALUES (?, ?)
    """, (
        user_id,
        now_utc()
    ))


def is_blocked(user_id):

    result = db_execute(
        "SELECT is_blocked FROM users WHERE user_id=?",
        (user_id,),
        fetch=True
    )

    if not result:
        return False

    return bool(result[0]["is_blocked"])


# =========================================================
# ADMIN MANAGEMENT
# =========================================================

def is_owner(user_id):
    return user_id in OWNER_IDS


def is_admin(user_id):

    if is_owner(user_id):
        return True

    result = db_execute(
        "SELECT user_id FROM admins WHERE user_id=?",
        (user_id,),
        fetch=True
    )

    return bool(result)


def add_admin(user_id, added_by):

    db_execute("""
        INSERT OR REPLACE INTO admins
        (user_id, added_by, added_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        added_by,
        now_utc()
    ))


def remove_admin(user_id):

    if is_owner(user_id):
        return False

    db_execute(
        "DELETE FROM admins WHERE user_id=?",
        (user_id,)
    )

    return True


def get_admins():

    return db_execute("""
        SELECT user_id, added_by, added_at
        FROM admins
        ORDER BY added_at ASC
    """, fetch=True)


# =========================================================
# BLOCK SYSTEM
# =========================================================

def block_user(user_id):

    db_execute("""
        UPDATE users
        SET is_blocked=1
        WHERE user_id=?
    """, (user_id,))


def unblock_user(user_id):

    db_execute("""
        UPDATE users
        SET is_blocked=0
        WHERE user_id=?
    """, (user_id,))


# =========================================================
# VOICE CLEANER
# =========================================================

def remove_emojis_for_voice(text):

    if not text:
        return ""

    # Emoji / symbol ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "\U00002B00-\U00002BFF"
        "\u200d"
        "\ufe0f"
        "\u20e3"
        "]+",
        flags=re.UNICODE
    )

    cleaned = emoji_pattern.sub(" ", text)

    # Extra symbols
    cleaned = re.sub(
        r"[\u2600-\u27BF]",
        " ",
        cleaned
    )

    # Multiple spaces
    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned
    )

    return cleaned.strip()


# =========================================================
# TEXT TO VOICE
# =========================================================

def create_voice(text):

    clean_text = remove_emojis_for_voice(text)

    if not clean_text:
        return None

    temp = tempfile.NamedTemporaryFile(
        suffix=".mp3",
        delete=False
    )

    filename = temp.name
    temp.close()

    try:

        tts = gTTS(
            text=clean_text,
            lang="bn",
            slow=False
        )

        tts.save(filename)

        return filename

    except Exception:

        if os.path.exists(filename):
            os.remove(filename)

        return None


# =========================================================
# SEND TEXT + VOICE
# =========================================================

async def send_text_voice(
    update,
    text,
    voice=True
):

    if not update.message:
        return

    await update.message.reply_text(text)

    if not voice:
        return

    voice_file = None

    try:

        voice_file = create_voice(text)

        if voice_file:

            with open(voice_file, "rb") as audio:

                await update.message.reply_voice(
                    voice=audio
                )

    except Exception as e:

        logger.error(
            "Voice error: %s",
            e
        )

    finally:

        if voice_file and os.path.exists(voice_file):

            try:
                os.remove(voice_file)
            except Exception:
                pass


# =========================================================
# USER MAIN MENU
# =========================================================

def user_menu(bot_username=None):

    buttons = [

        [
            InlineKeyboardButton(
                "➕ Add Your Group",
                url=(
                    f"https://t.me/{bot_username}"
                    f"?startgroup=true"
                    if bot_username
                    else "https://t.me/"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "📖 Help",
                callback_data="user_help"
            ),
            InlineKeyboardButton(
                "🌹 Rose",
                callback_data="user_rose"
            )
        ],

        [
            InlineKeyboardButton(
                "😂 Joke",
                callback_data="user_joke"
            ),
            InlineKeyboardButton(
                "💖 Love",
                callback_data="user_love"
            )
        ],
    ]

    return InlineKeyboardMarkup(buttons)


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user or not update.message:
        return

    register_user(user)

    if is_blocked(user.id):
        await update.message.reply_text(
            "🚫 আপনার account blocked করা হয়েছে।"
        )
        return

    log_usage(user.id)

    bot_info = await context.bot.get_me()

    text = (
        f"🌟 হ্যালো {user.first_name or 'বন্ধু'}!\n\n"
        "🤖 আমি RIYA Bot.\n"
        "নিচের button থেকে feature ব্যবহার করো।\n\n"
        "➕ Add Your Group চাপলে bot-কে তোমার group-এ "
        "add করতে পারবে।\n\n"
        "⚠️ Group-এ bot-কে প্রয়োজনীয় admin permission দিতে হবে।"
    )

    await update.message.reply_text(
        text,
        reply_markup=user_menu(bot_info.username)
    )


# =========================================================
# HELP BUTTON
# =========================================================

async def show_user_help(
    query
):

    text = (
        "📖 RIYA Bot Help\n\n"
        "➕ Add Your Group — bot-কে group-এ add করার জন্য\n"
        "🌹 Rose — rose message\n"
        "😂 Joke — joke\n"
        "💖 Love — friendly love message\n\n"
        "Group auto-reply চালাতে bot-কে group admin "
        "করতে হবে এবং BotFather থেকে Privacy Mode OFF "
        "করতে হবে।"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="user_home"
                )
            ]
        ])
    )


# =========================================================
# USER BUTTON ACTIONS
# =========================================================

async def user_rose(query):

    roses = [
        "🌹 তোমার জন্য একটি সুন্দর গোলাপ! দিনটা ভালো কাটুক।",
        "🌹💐 অনেক শুভকামনা রইল তোমার জন্য!",
        "🌹 হাসিখুশি থেকো, সুন্দর থাকো।",
    ]

    await query.message.reply_text(
        random.choice(roses)
    )


async def user_joke(query):

    jokes = [
        "😂 শিক্ষক: পড়া শিখেছো?\nছাত্র: স্যার, বই খুলেছি—এটাই অনেক!",
        "🤣 বন্ধু: এত হাসছিস কেন?\nপল্টু: কারণ কান্না করলে সবাই প্রশ্ন করে!",
    ]

    await query.message.reply_text(
        random.choice(jokes)
    )


async def user_love(query):

    messages = [
        "💖 তোমার দিনটা সুন্দর হোক। নিজের যত্ন নিও।",
        "🌸 ভালো থেকো, হাসিখুশি থেকো।",
        "💖 সুন্দর সম্পর্কের ভিত্তি হলো সম্মান ও বিশ্বাস।",
    ]

    await query.message.reply_text(
        random.choice(messages)
    )


# =========================================================
# DASHBOARD MAIN
# =========================================================

def dashboard_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            ),
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users"
            )
        ],

        [
            InlineKeyboardButton(
                "🚫 Block User",
                callback_data="admin_block"
            ),
            InlineKeyboardButton(
                "✅ Unblock User",
                callback_data="admin_unblock"
            )
        ],

        [
            InlineKeyboardButton(
                "➕ Add Admin",
                callback_data="admin_add"
            ),
            InlineKeyboardButton(
                "➖ Remove Admin",
                callback_data="admin_remove"
            )
        ],

        [
            InlineKeyboardButton(
                "👑 Admin List",
                callback_data="admin_list"
            )
        ],

        [
            InlineKeyboardButton(
                "💬 Reply System",
                callback_data="reply_menu"
            )
        ],

        [
            InlineKeyboardButton(
                "📢 Broadcast",
                callback_data="broadcast"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="dashboard"
            )
        ],
    ])


async def dashboard_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    register_user(user)

    if not is_admin(user.id):

        await update.message.reply_text(
            "🚫 এই panel শুধুমাত্র bot admin/owner-এর জন্য।"
        )

        return

    await show_dashboard(
        update.message,
        user.id
    )


async def show_dashboard(
    message,
    user_id
):

    total_users = db_execute(
        "SELECT COUNT(*) AS c FROM users",
        fetch=True
    )[0]["c"]

    today_users = db_execute(
        """
        SELECT COUNT(DISTINCT user_id) AS c
        FROM usage
        WHERE created_at >= ?
        """,
        (today_start_utc(),),
        fetch=True
    )[0]["c"]

    total_uses = db_execute(
        "SELECT COUNT(*) AS c FROM usage",
        fetch=True
    )[0]["c"]

    admins = len(get_admins()) + len(OWNER_IDS)

    text = (
        "👑 RIYA BOT ADMIN PANEL\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📅 Today Active: {today_users}\n"
        f"📈 Total Bot Uses: {total_uses}\n"
        f"👑 Admin/Owners: {admins}\n\n"
        "নিচের button থেকে management করো।"
    )

    await message.reply_text(
        text,
        reply_markup=dashboard_keyboard()
    )


# =========================================================
# STATS
# =========================================================

async def admin_stats(query):

    if not is_admin(query.from_user.id):
        return

    total = db_execute(
        "SELECT COUNT(*) AS c FROM users",
        fetch=True
    )[0]["c"]

    today = db_execute(
        """
        SELECT COUNT(DISTINCT user_id) AS c
        FROM usage
        WHERE created_at >= ?
        """,
        (today_start_utc(),),
        fetch=True
    )[0]["c"]

    uses = db_execute(
        "SELECT COUNT(*) AS c FROM usage",
        fetch=True
    )[0]["c"]

    blocked = db_execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        WHERE is_blocked=1
        """,
        fetch=True
    )[0]["c"]

    text = (
        "📊 BOT STATISTICS\n\n"
        f"👥 Total Users: {total}\n"
        f"🟢 Today Active Users: {today}\n"
        f"📈 Total Uses: {uses}\n"
        f"🚫 Blocked Users: {blocked}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Dashboard",
                    callback_data="dashboard"
                )
            ]
        ])
    )


# =========================================================
# USER LIST
# =========================================================

async def admin_users(query):

    if not is_admin(query.from_user.id):
        return

    users = db_execute("""
        SELECT user_id, first_name, username, is_blocked
        FROM users
        ORDER BY last_seen DESC
        LIMIT 30
    """, fetch=True)

    if not users:

        text = "👥 কোনো user নেই।"

    else:

        lines = ["👥 Recent Users\n"]

        for u in users:

            status = (
                "🚫 BLOCKED"
                if u["is_blocked"]
                else "🟢 ACTIVE"
            )

            name = u["first_name"] or "Unknown"

            username = (
                f"@{u['username']}"
                if u["username"]
                else ""
            )

            lines.append(
                f"{name} {username}\n"
                f"ID: `{u['user_id']}` • {status}\n"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Dashboard",
                    callback_data="dashboard"
                )
            ]
        ])
    )


# =========================================================
# ADMIN LIST
# =========================================================

async def admin_list(query):

    if not is_admin(query.from_user.id):
        return

    lines = [
        "👑 BOT OWNERS\n",
        "👑 8136997138",
        "👑 8827019486",
        "",
        "🛡️ EXTRA ADMINS",
    ]

    admins = get_admins()

    if admins:

        for admin in admins:
            lines.append(
                f"🛡️ {admin['user_id']}"
            )

    else:

        lines.append(
            "No extra admin added."
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Dashboard",
                    callback_data="dashboard"
                )
            ]
        ])
    )


# =========================================================
# REPLY SYSTEM MENU
# =========================================================

def reply_menu_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "➕ Add Reply",
                callback_data="reply_add"
            )
        ],

        [
            InlineKeyboardButton(
                "📋 View Replies",
                callback_data="reply_list"
            )
        ],

        [
            InlineKeyboardButton(
                "🗑 Delete Reply",
                callback_data="reply_delete"
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Dashboard",
                callback_data="dashboard"
            )
        ],
    ])


async def reply_menu(query):

    if not is_admin(query.from_user.id):
        return

    await query.edit_message_text(
        "💬 GROUP AUTO-REPLY SYSTEM\n\n"
        "এখান থেকে group-এর জন্য keyword ও reply message "
        "add/delete করতে পারবে।",
        reply_markup=reply_menu_keyboard()
    )


# =========================================================
# REPLY LIST
# =========================================================

async d
