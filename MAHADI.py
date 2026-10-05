import logging
import os
import random
import tempfile

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from gtts import gTTS


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError(
        "TOKEN is missing. Please add TOKEN in Railway Variables."
    )


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# TEXT TO VOICE
# =========================================================

def text_to_voice(text: str):
    """
    Convert Bengali text to an MP3 voice file.
    A temporary file is used so multiple users don't conflict.
    """

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".mp3",
        delete=False
    )

    filename = temp_file.name
    temp_file.close()

    try:
        tts = gTTS(
            text=text,
            lang="bn",
            slow=False
        )
        tts.save(filename)
        return filename

    except Exception:
        if os.path.exists(filename):
            os.remove(filename)
        raise


# =========================================================
# SEND TEXT + VOICE
# =========================================================

async def send_text_and_voice(
    update: Update,
    text: str
):
    if not update.message:
        return

    # Text
    await update.message.reply_text(text)

    # Voice
    voice_file = None

    try:
        voice_file = text_to_voice(text)

        with open(voice_file, "rb") as audio:
            await update.message.reply_voice(
                voice=audio
            )

    except Exception as e:
        logger.error(
            "Voice generation failed: %s",
            e
        )

    finally:
        if voice_file and os.path.exists(voice_file):
            try:
                os.remove(voice_file)
            except Exception:
                pass


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_name = (
        update.effective_user.first_name
        if update.effective_user
        else "বন্ধু"
    )

    welcome_msg = (
        f"🌟✨ হ্যালো {user_name}! 👋💖\n\n"
        "🤖 আমি RIYA AI Bot! 🥰✨\n"
        "আমার সাথে আড্ডা, মজার কথা এবং AI-style chat করতে পারো।\n\n"
        "💬 Available Commands:\n\n"
        "🌹 /rose — গোলাপ ও শুভেচ্ছা\n"
        "💖 /lovechat — মিষ্টি ভালোবাসার মেসেজ\n"
        "😂 /joke — মজার জোকস\n"
        "🤭 /naughty — মজার দুষ্টু জোকস\n"
        "📌 /help — সব কমান্ড দেখতে\n\n"
        "💡 যেকোনো সাধারণ মেসেজ লিখলেও আমি উত্তর দেওয়ার চেষ্টা করব।"
    )

    await update.message.reply_text(welcome_msg)


# =========================================================
# /HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    help_text = (
        "📌✨ RIYA Bot Menu 🌸\n\n"
        "🧠 AI Chat\n"
        "সাধারণ মেসেজ পাঠালে RIYA উত্তর দেবে।\n\n"
        "💖 /lovechat\n"
        "মিষ্টি ভালোবাসার মেসেজ।\n\n"
        "🌹 /rose\n"
        "গোলাপের শুভেচ্ছা।\n\n"
        "😂 /joke\n"
        "মজার জোকস।\n\n"
        "🤭 /naughty\n"
        "হালকা মজার দুষ্টু জোকস।\n\n"
        "🎙️ Voice Reply\n"
        "অনেক উত্তরের সাথে Bengali voice reply পাঠানো হবে।\n\n"
        "🎉 Group Welcome\n"
        "নতুন member join করলে welcome message পাঠাবে।"
    )

    await update.message.reply_text(help_text)


# =========================================================
# JOKES
# =========================================================

async def joke_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    jokes = [
        (
            "🤣 শিক্ষক: পল্টু, বল তো বক্তৃতা আর সংশোধনের মধ্যে "
            "পার্থক্য কী?\n\n"
            "🧠 পল্টু: স্যার, অনেকক্ষণ ভুল কথা বলা হলো বক্তৃতা, "
            "আর সেই ভুলের জন্য বকা খাওয়া হলো সংশোধন! 😂"
        ),

        (
            "😂 পল্টু: ডাক্তার সাহেব, আমি যা দেখি সব ডবল দেখি!\n"
            "🩺 ডাক্তার: আচ্ছা, ওই সোফায় বসুন।\n"
            "😳 পল্টু: কোন সোফায়? এখানে তো চারটা সোফা! 🤣"
        ),

        (
            "🤭 বন্ধু: রাতে ঘুম হলো?\n"
            "😴 পল্টু: হয়েছিল।\n"
            "বন্ধু: তাহলে সকালে এত দেরি?\n"
            "😂 পল্টু: ঘুমটা সুন্দর ছিল, তাই ছাড়তে মন চায়নি!"
        ),
    ]

    selected_joke = random.choice(jokes)

    await send_text_and_voice(
        update,
        selected_joke
    )


# =========================================================
# NAUGHTY / FUN
# =========================================================

async def naughty_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    stories = [
        (
            "🤭 দুষ্টু জোকস:\n\n"
            "👩: তুমি আমাকে কতটা ভালোবাসো?\n"
            "😎: এতটাই যে তোমার জন্য চকলেটও ভাগ করে খাব!\n"
            "😂 তারপর নিজের অংশটা লুকিয়ে ফেলল!"
        ),

        (
            "😜 বন্ধু: তুই এত হাসিস কেন?\n"
            "😂 পল্টু: কারণ আমার হাসির জন্য কোনো ডাটা প্যাক লাগে না!"
        ),
    ]

    selected = random.choice(stories)

    await send_text_and_voice(
        update,
        selected
    )


# =========================================================
# LOVE CHAT
# =========================================================

async def lovechat_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    messages = [
        (
            "💖✨ তোমার সাথে কথা বললে মনটা ভালো হয়ে যায়। "
            "তোমার দিনটা সুন্দর হোক—এই শুভকামনা রইল। 🌸"
        ),

        (
            "🌹💖 কিছু মানুষ জীবনে এসে সাধারণ মুহূর্তকেও "
            "সুন্দর করে তোলে। তোমার জন্য রইল একগুচ্ছ শুভকামনা। ✨"
        ),

        (
            "🥰✨ হাসিখুশি থেকো, নিজের যত্ন নিও এবং "
            "প্রতিদিন নতুন কিছু শেখার চেষ্টা করো। 🌸💖"
        ),
    ]

    selected = random.choice(messages)

    await send_text_and_voice(
        update,
        selected
    )


# =========================================================
# ROSE
# =========================================================

async def rose_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    roses = [
        (
            "🌹✨ এই নাও তোমার জন্য সুন্দর একটি গোলাপ! "
            "তোমার দিনটা আনন্দে ভরে উঠুক। 💖"
        ),

        (
            "🌹🌹🌹 একগুচ্ছ গোলাপ তোমার জন্য! "
            "হাসিখুশি থেকো আর সুন্দর সময় কাটাও। ✨"
        ),

        (
            "🌹💐 গোলাপের মতো সুন্দর হোক তোমার আজকের দিন। "
            "অনেক শুভকামনা! 💖✨"
        ),
    ]

    selected = random.choice(roses)

    await send_text_and_voice(
        update,
        selected
    )


# =========================================================
# GROUP WELCOME
# =========================================================

async def welcome_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:

        name = member.first_name or "বন্ধু"

        welcome_text = (
            f"🌟🎉 Welcome {name}! 🥳💖\n\n"
            "আমাদের গ্রুপে তোমাকে স্বাগতম! ✨\n"
            "আশা করি আমাদের সাথে তোমার সময়টা সুন্দর কাটবে। 🌸"
        )

        await send_text_and_voice(
            update,
            welcome_text
        )


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.text:
        return

    user_input = update.message.text.strip()
    text = user_input.lower()

    if not user_input:
        return

    # Love
    if (
        "i love you" in text
        or "ভালোবাসি" in text
    ):
        reply = (
            "❤️✨ তোমার কথাটা শুনে ভালো লাগল! "
            "তোমার জন্য অনেক শুভকামনা ও ভালোবাসা রইল। 🌹🥰"
        )

    # Meri Jaan
    elif (
        "meri jaan" in text
        or "মেরি জান" in text
    ):
        reply = (
            "😊💖 বলো, কী খবর? "
            "আমি শুনছি। 🌸✨"
        )

    # Relationship
    elif (
        "রিলেশন" in text
        or "প্রেম" in text
        or "relationship" in text
    ):
        reply = (
            "💖 সম্পর্কের সবচেয়ে গুরুত্বপূর্ণ বিষয় হলো "
            "সম্মান, বিশ্বাস এবং ভালো যোগাযোগ। 🌸✨"
        )

    # Rose
    elif (
        "rose" in text
        or "গোলাপ" in text
        or "ফুল" in text
    ):
        await rose_handler(update, context)
        return

    # Naughty
    elif (
        "দুষ্টু" in text
        or "naughty" in text
    ):
        await naughty_handler(update, context)
        return

    # How are you
    elif (
        "কেমন আছো" in text
        or "how are you" in text
    ):
        reply = (
            "😊✨ আমি ভালো আছি! "
            "তোমার সাথে কথা বলছি। তুমি কেমন আছো?"
        )

    # Who are you
    elif (
        "কে তুমি" in text
        or "who are you" in text
    ):
        reply = (
            "🤖✨ আমি RIYA Bot!\n\n"
            "আমি একটি Telegram bot, "
            "যে বিভিন্ন command এবং message-এর "
            "উত্তর দিতে পারে। 💖"
        )

    # Joke
    elif (
        "জোক" in text
        or "জোকস" in text
        or "joke" in text
        or "jokes" in text
        or "মজার কাহিনী" in text
    ):
        await joke_handler(update, context)
        return

    # General message
    else:
        reply = (
            "🤖✨ RIYA AI Chat\n\n"
            f"💬 তুমি লিখেছো:\n{user_input}\n\n"
            "🌸 তোমার মেসেজটি পেয়েছি! "
            "আমি এখনো একটি simple chatbot mode-এ আছি, "
            "তাই সব প্রশ্নের real AI উত্তর দিতে পারি না। "
            "তবে /help লিখলে available features দেখতে পারবে। 😊"
        )

    await send_text_and_voice(
        update,
        reply
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram bot error: %s",
        context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    logger.info("Starting RIYA Telegram Bot...")

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "joke",
            joke_handler
        )
    )

    app.add_handler(
        CommandHandler(
            "naughty",
            naughty_handler
        )
    )

    app.add_handler(
        CommandHandler(
            "rose",
            rose_handler
        )
    )

    app.add_handler(
        CommandHandler(
            "lovechat",
            lovechat_handler
        )
    )

    # New group members
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_member
        )
    )

    # Normal text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # Errors
    app.add_error_handler(error_handler)

    logger.info(
        "🤖 RIYA Bot is running successfully..."
    )

    # Start polling
    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
