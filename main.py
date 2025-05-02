import os
import json
import random
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from supabase import create_client, Client

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

user_states = {}
quiz_sessions = {}

# --- START: Add new word ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("📄 لطفاً کلمه خود را وارد کنید")
    user_states[update.effective_user.id] = {"step": "word"}

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    if not state:
        return

    text = update.message.text.strip()
    if state["step"] == "word":
        state["word"] = text
        state["step"] = "meaning"
        await update.message.reply_text("🧠 حالا معنی کلمه را وارد کنید")
    elif state["step"] == "meaning":
        state["meaning"] = text
        try:
            supabase.table("words").insert({
                "word": state["word"],
                "meaning": state["meaning"],
                "user_id": str(user_id),
            }).execute()
            await update.message.reply_text("✅ کلمه با موفقیت ذخیره شد.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ذخیره‌سازی:\n{e}")
        user_states.pop(user_id)

# --- LIST ---
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    user_id = str(update.effective_user.id)
    try:
        response = supabase.table("words").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        words = response.data
        if not words:
            await update.message.reply_text("❗️هیچ کلمه‌ای ذخیره نشده.")
            return
        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
        for i, w in enumerate(words, 1):
            text += f"<b>{i}.</b> <code>{w['word']}</code> ➜ {w['meaning']}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا:\n{e}")

# --- QUIZ ---
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    user_id = str(update.effective_user.id)
    response = supabase.table("words").select("*").eq("user_id", user_id).execute()
    items = response.data
    if len(items) < 4:
        await update.message.reply_text("حداقل ۴ کلمه باید ذخیره کرده باشید.")
        return
    quiz_sessions[user_id] = {
        "items": random.sample(items, min(10, len(items))),
        "current": 0,
        "score": 0,
    }
    await send_question(update, context, user_id)

async def send_question(update, context, user_id):
    session = quiz_sessions[user_id]
    index = session["current"]
    item = session["items"][index]
    all_items = session["items"].copy()
    options = random.sample(all_items, 3)
    if item not in options:
        options[random.randint(0, 2)] = item
    random.shuffle(options)

    keyboard = [
        [InlineKeyboardButton(w["meaning"], callback_data=f"quiz|{user_id}|{w['id']}")]
        for w in options
    ]
    text = (
        f"❓ سوال {index + 1} از {len(session['items'])}\n"
        f"<b>{item['word']}</b> یعنی چه؟"
    )
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )

async def quiz_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, user_id, answer_id = query.data.split("|")
    session = quiz_sessions.get(user_id)

    if not session:
        return

    current_item = session["items"][session["current"]]
    if current_item["id"] == answer_id:
        session["score"] += 1
        reply = "✅ درست گفتی!"
    else:
        reply = f"❌ جواب اشتباه بود. معنی درست:\n<b>{current_item['meaning']}</b>"

    session["current"] += 1
    await query.edit_message_text(reply, parse_mode=ParseMode.HTML)

    if session["current"] < len(session["items"]):
        await send_question(update, context, user_id)
    else:
        score = session["score"]
        total = len(session["items"])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🏁 آزمون تمام شد!\nامتیاز: {score} از {total}"
        )
        quiz_sessions.pop(user_id)

# --- Add Example ---
async def add_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = supabase.table("words").select("id,word").eq("user_id", user_id).order("created_at", desc=True).execute()
    words = data.data
    if not words:
        await update.message.reply_text("❗️هیچ کلمه‌ای ثبت نکردی.")
        return
    keyboard = [
        [InlineKeyboardButton(w["word"], callback_data=f"select_example|{w['id']}")]
        for w in words
    ]
    await update.message.reply_text(
        "🔍 لطفاً کلمه‌ای را انتخاب کنید که می‌خواهید برایش جمله اضافه کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def example_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, word_id = query.data.split("|")
    context.user_data["addexample_id"] = word_id
    await query.edit_message_text(f"✍ لطفاً جمله‌ای برای \"{word_id}\" ارسال کنید:")

async def example_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word_id = context.user_data.get("addexample_id")
    if not word_id:
        return
    example = update.message.text.strip()
    try:
        word = supabase.table("words").select("examples").eq("id", word_id).single().execute().data
        examples = word.get("examples") or []
        if isinstance(examples, str):
            examples = json.loads(examples)
        examples.append(example)
        supabase.table("words").update({"examples": examples}).eq("id", word_id).execute()
        await update.message.reply_text("✅ جمله با موفقیت ذخیره شد.")
        context.user_data["addexample_id"] = None
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ذخیره‌سازی جمله:\n{e}")

# --- HELP ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = (
        "📌 <b>دستورات موجود:</b>\n\n"
        "/start – افزودن کلمه جدید\n"
        "/list – نمایش همه کلمات\n"
        "/quiz – آزمون چهارگزینه‌ای\n"
        "/addexample – افزودن جمله\n"
        "/help – نمایش همین راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# --- Main ---
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_words))
app.add_handler(CommandHandler("quiz", quiz))
app.add_handler(CommandHandler("addexample", add_example))
app.add_handler(CommandHandler("help", help_command))

app.add_handler(CallbackQueryHandler(quiz_button, pattern="^quiz\\|"))
app.add_handler(CallbackQueryHandler(example_button, pattern="^select_example\\|"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, example_response))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

if __name__ == "__main__":
    print("✅ Bot is running...")
    app.run_polling()
