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

# بارگذاری تنظیمات
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = 52134388

# اتصال به Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

STEP_WORD = "word"
STEP_MEANING = "meaning"
user_states = {}
quiz_sessions = {}

# UptimeRobot
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات زنده است ✅"

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("شما اجازه استفاده از این ربات را ندارید ❌")
        return
    user_states[update.effective_user.id] = {"step": STEP_WORD}
    await update.message.reply_text("📝 لطفاً کلمه خود را وارد کنید")

# /list
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
        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
        for i, item in enumerate(items, 1):
            text += f"{i}. <b>{item['word']}</b>\n🟢 {item['meaning']}\n\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اطلاعات: {e}")

# /quiz (۱۰ سواله با امتیاز)
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
    random.shuffle(items)
    quiz_sessions[user_id] = {
        "items": items[:10],
        "score": 0,
        "current": 0
    }
    await send_next_question(update, context, user_id)

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    session = quiz_sessions[user_id]
    if session["current"] >= len(session["items"]):
        total = len(session["items"])
        score = session["score"]
        await update.message.reply_text(f"✅ آزمون تمام شد!\nامتیاز شما: {score} از {total}")
        quiz_sessions.pop(user_id)
        return
    question = session["items"][session["current"]]
    correct = question["meaning"]
    options = [correct]
    while len(options) < 4:
        other = random.choice(session["items"])["meaning"]
        if other not in options:
            options.append(other)
    random.shuffle(options)
    keyboard = [[InlineKeyboardButton(opt, callback_data=opt)] for opt in options]
    context.user_data["current_answer"] = correct
    context.user_data["user_id"] = user_id
    await update.message.reply_text(
        f"❓ سوال {session['current'] + 1} از {len(session['items'])}\n\n📘 <b>{question['word']}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

# پاسخ دکمه‌ای
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = quiz_sessions.get(user_id)
    if not session:
        await query.edit_message_text("❌ جلسه کوییز یافت نشد. دوباره /quiz بزن.")
        return
    correct = context.user_data.get("current_answer")
    selected = query.data
    if selected == correct:
        session["score"] += 1
        await query.edit_message_text("✅ آفرین درست گفتی")
    else:
        await query.edit_message_text(f"❌ نه، جواب درست بود:\n<b>{correct}</b>", parse_mode=ParseMode.HTML)
    session["current"] += 1
    await send_next_question(query, context, user_id)

# پیام‌های متنی – ذخیره کلمه و معنی
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
        "/quiz – آزمون ۱۰ سواله چهارگزینه‌ای\n"
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
