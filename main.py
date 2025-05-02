
import os
import random
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
from supabase import create_client, Client

# بارگذاری محیط
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = 52134388

# اتصال به Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# وضعیت کاربران
STEP_WORD = "word"
STEP_MEANING = "meaning"
user_states = {}
quiz_sessions = {}

# UptimeRobot
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات زنده است ✅"

# شروع اضافه کردن کلمه
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("شما اجازه استفاده از این ربات را ندارید ❌")
        return
    user_states[update.effective_user.id] = {"step": STEP_WORD}
    await update.message.reply_text("📝 لطفاً کلمه خود را وارد کنید")

# لیست کلمات
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ اجازه دسترسی ندارید.")
        return
    try:
        result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
        items = result.data
        if not items:
            await update.message.reply_text("📭 هنوز هیچ کلمه‌ای ذخیره نکردی.")
            return
        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>"
        for i, item in enumerate(items, 1):
            text += f"{i}. <b>{item['word']}</b>🟢 {item['meaning']}"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اطلاعات: {e}")

# آزمون چهارگزینه‌ای
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ اجازه دسترسی ندارید.")
        return
    result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
    items = result.data
    if len(items) < 4:
        await update.message.reply_text("📭 حداقل ۴ کلمه برای کوییز نیاز است.")
        return
    question = random.choice(items)
    correct_meaning = question["meaning"]
    options = [correct_meaning]
    while len(options) < 4:
        option = random.choice(items)["meaning"]
        if option not in options:
            options.append(option)
    random.shuffle(options)
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"{opt}")] for opt in options]
    quiz_sessions[user_id] = {
        "question": question["word"],
        "correct": correct_meaning
    }
    await update.message.reply_text(
        f"❓ معنی این کلمه چیست؟

📘 <b>{question['word']}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

# پاسخ به انتخاب دکمه
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    session = quiz_sessions.get(user_id)
    if not session:
        await query.edit_message_text("❌ جلسه کوییز یافت نشد. دوباره /quiz بزن.")
        return
    correct = session["correct"]
    if data == correct:
        await query.edit_message_text("✅ آفرین درست گفتی")
    else:
        await query.edit_message_text(f"❌ نه، جواب درست بود:
<b>{correct}</b>", parse_mode=ParseMode.HTML)
    quiz_sessions.pop(user_id)

# پیام‌های متنی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id != OWNER_ID:
        return
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("لطفاً ابتدا /start را بزن.")
        return
    if state["step"] == STEP_WORD:
        state["word"] = text
        state["step"] = STEP_MEANING
        await update.message.reply_text("🧠 حالا معنی کلمه را وارد کن")
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

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = (
        "📌 <b>دستورات موجود:</b>\n\n"
        "/start – افزودن کلمه جدید\n"
        "/list – نمایش همه کلمات ذخیره‌شده\n"
        "/quiz – آزمون چهارگزینه‌ای از کلمات\n"
        "/help – نمایش همین راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# اجرای ربات
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("list", list_words))
    telegram_app.add_handler(CommandHandler("quiz", quiz))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CallbackQueryHandler(handle_answer))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.run_polling()
