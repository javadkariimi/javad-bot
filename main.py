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

# تنظیمات
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = 52134388

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

STEP_WORD = "word"
STEP_MEANING = "meaning"
STEP_EXAMPLE = "example"
user_states = {}
quiz_sessions = {}
pending_example = {}

# برای UptimeRobot
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات فعاله ✅"

# /start – فقط کلمه و معنی
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    user_states[update.effective_user.id] = {"step": STEP_WORD}
    await update.message.reply_text("📝 لطفاً کلمه را وارد کن")

# دریافت پیام‌های متنی برای مراحل start و addexample
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # افزودن جمله نمونه
    if user_id in pending_example:
        word = pending_example[user_id]
        result = supabase.table("words").select("*").eq("user_id", str(user_id)).eq("word", word).execute()
        if result.data:
            existing = result.data[0]
            examples = existing.get("examples", []) or []
            examples.append(text)
            supabase.table("words").update({"examples": examples}).eq("id", existing["id"]).execute()
            await update.message.reply_text(f"✅ جمله برای «{word}» ذخیره شد!")
        else:
            await update.message.reply_text("❌ کلمه‌ای با این نام پیدا نشد.")
        del pending_example[user_id]
        return

    # افزودن کلمه و معنی
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("لطفاً اول /start را بزن یا /addexample [کلمه] استفاده کن.")
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
                "examples": [],
                "user_id": str(user_id)
            }).execute()
            await update.message.reply_text("✅ کلمه و معنی ذخیره شدند!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ذخیره‌سازی: {e}")
        user_states.pop(user_id)

# /addexample [کلمه]
async def add_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ لطفاً کلمه‌ای بنویس: /addexample Haus")
        return
    word = " ".join(context.args)
    pending_example[user_id] = word
    await update.message.reply_text(f"✏️ حالا جمله‌ای برای «{word}» بنویس:")

# /list – نمایش همه کلمات و جمله‌ها
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
    try:
        result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
        items = result.data
        if not items:
            await update.message.reply_text("📭 هنوز هیچ کلمه‌ای ذخیره نکردی.")
            return
        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
        for i, item in enumerate(items, 1):
            text += f"{i}. <b>{item['word']}</b>\n🟢 {item['meaning']}\n"
            for j, ex in enumerate(item.get("examples", []), 1):
                text += f"✏️ {j}) {ex}\n"
            text += "\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت اطلاعات: {e}")

# /quiz – ۱۰ سواله
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
    result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
    items = result.data
    if len(items) < 4:
        await update.message.reply_text("📭 حداقل ۴ کلمه برای آزمون نیاز است.")
        return
    random.shuffle(items)
    quiz_sessions[user_id] = {
        "items": items[:10],
        "score": 0,
        "current": 0
    }
    await send_next_question(update, context, user_id)

async def send_next_question(update_or_query, context, user_id):
    session = quiz_sessions[user_id]
    if session["current"] >= len(session["items"]):
        await update_or_query.message.reply_text(f"✅ آزمون تمام شد!\nنمره: {session['score']} از {len(session['items'])}")
        quiz_sessions.pop(user_id)
        return
    question = session["items"][session["current"]]
    correct = question["meaning"]
    options = [correct]
    while len(options) < 4:
        alt = random.choice(session["items"])["meaning"]
        if alt not in options:
            options.append(alt)
    random.shuffle(options)
    keyboard = [[InlineKeyboardButton(opt, callback_data=opt)] for opt in options]
    context.user_data["current_answer"] = correct
    await update_or_query.message.reply_text(
        f"❓ سوال {session['current'] + 1} از {len(session['items'])}\n\n📘 <b>{question['word']}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = quiz_sessions.get(user_id)
    if not session:
        await query.edit_message_text("❌ آزمون یافت نشد.")
        return
    correct = context.user_data.get("current_answer")
    selected = query.data
    if selected == correct:
        session["score"] += 1
        await query.edit_message_text("✅ درست گفتی!")
    else:
        await query.edit_message_text(f"❌ نه، جواب درست بود:\n<b>{correct}</b>", parse_mode=ParseMode.HTML)
    session["current"] += 1
    await send_next_question(query, context, user_id)

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = (
        "📌 <b>دستورات:</b>\n\n"
        "/start – افزودن کلمه و معنی\n"
        "/addexample [کلمه] – افزودن جمله نمونه برای کلمه\n"
        "/list – نمایش همه کلمات، معانی و جمله‌ها\n"
        "/quiz – آزمون ۱۰ سواله\n"
        "/help – راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# اجرای ربات
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()
    bot = ApplicationBuilder().token(BOT_TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("addexample", add_example))
    bot.add_handler(CommandHandler("list", list_words))
    bot.add_handler(CommandHandler("quiz", quiz))
    bot.add_handler(CommandHandler("help", help_command))
    bot.add_handler(CallbackQueryHandler(handle_answer))
    bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    bot.run_polling()
