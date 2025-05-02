import os
import random
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = 52134388  # آیدی عددی جــواد

# اتصال به Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# وضعیت کاربران
STEP_WORD = "word"
STEP_MEANING = "meaning"
user_states = {}
quiz_states = {}

# Flask برای UptimeRobot
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات زنده است ✅"

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("شما اجازه استفاده از این ربات را ندارید ❌")
        return

    user_id = update.effective_user.id
    user_states[user_id] = {"step": STEP_WORD}
    await update.message.reply_text("📝 لطفاً کلمه خود را وارد کنید")

# /list
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ شما اجازه استفاده از این دستور را ندارید.")
        return

    try:
        result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
        items = result.data

        if not items:
            await update.message.reply_text("📭 هنوز هیچ کلمه‌ای ذخیره نکردی.")
            return

        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
        for i, item in enumerate(items, 1):
            text += f"<b>{i}.</b> {item['word']} ➜ {item['meaning']}\n"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اطلاعات: {e}")

# /quiz
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ شما اجازه استفاده از این دستور را ندارید.")
        return

    result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
    items = result.data

    if not items:
        await update.message.reply_text("📭 هنوز هیچ کلمه‌ای برای کوییز نداری.")
        return

    question = random.choice(items)
    quiz_states[user_id] = question

    await update.message.reply_text(f"❓ معنی این کلمه چیست؟\n\n<b>{question['word']}</b>", parse_mode=ParseMode.HTML)

# پیام‌های متنی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id != OWNER_ID:
        return

    # پاسخ به کوییز
    if user_id in quiz_states:
        answer = text.lower()
        correct = quiz_states[user_id]["meaning"].lower()

        if answer == correct:
            await update.message.reply_text("✅ آفرین! درست جواب دادی.")
        else:
            await update.message.reply_text(f"❌ نه متأسفم. جواب درست بود:\n<b>{correct}</b>", parse_mode=ParseMode.HTML)

        quiz_states.pop(user_id)
        return

    # ورود کلمه و معنی
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("لطفاً ابتدا /start را وارد کنید.")
        return

    if state["step"] == STEP_WORD:
        state["word"] = text
        state["step"] = STEP_MEANING
        await update.message.reply_text("🧠 حالا معنی کلمه را وارد کنید")
    elif state["step"] == STEP_MEANING:
        state["meaning"] = text

        try:
            supabase.table("words").insert({
                "word": state["word"],
                "meaning": state["meaning"],
                "user_id": str(user_id)
            }).execute()

            await update.message.reply_text("✅ کلمه و معنی با موفقیت ذخیره شدند!")

        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ذخیره‌سازی: {e}")

        user_states.pop(user_id)

# اجرای ربات
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("list", list_words))
    telegram_app.add_handler(CommandHandler("quiz", quiz))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.run_polling()
