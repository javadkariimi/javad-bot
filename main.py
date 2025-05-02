import os
import random
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
user_state = {}
quiz_sessions = {}
add_example_state = {}

# ------------------ START ------------------ #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    user_state[update.effective_chat.id] = {"step": "word"}
    await update.message.reply_text("📝 لطفاً کلمه خود را وارد کنید")

# ------------------ MESSAGE HANDLER ------------------ #
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_user.id != OWNER_ID:
        return
    if chat_id not in user_state:
        return

    step = user_state[chat_id]["step"]
    text = update.message.text.strip()

    if step == "word":
        user_state[chat_id]["word"] = text
        user_state[chat_id]["step"] = "meaning"
        await update.message.reply_text("🧠 حالا معنی کلمه را وارد کنید")
    elif step == "meaning":
        word = user_state[chat_id]["word"]
        meaning = text
        try:
            supabase.table("words").insert({
                "word": word,
                "meaning": meaning,
                "examples": []
            }).execute()
            await update.message.reply_text("✅ کلمه با موفقیت ذخیره شد.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ذخیره‌سازی: {e}")
        user_state.pop(chat_id)

# ------------------ ADD EXAMPLE ------------------ #
async def add_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("🔍 لطفاً کلمه‌ای را انتخاب کنید که می‌خواهید برایش جمله اضافه کنید:")
    response = supabase.table("words").select("word").execute()
    words = [w["word"] for w in response.data]
    if not words:
        await update.message.reply_text("⚠️ هیچ کلمه‌ای ذخیره نشده.")
        return
    keyboard = [[InlineKeyboardButton(w, callback_data=f"addexample|{w}")] for w in words]
    await update.message.reply_text("👇 انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

# ------------------ CALLBACK ------------------ #
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("addexample|"):
        word = data.split("|")[1]
        add_example_state[query.message.chat.id] = word
        await query.message.reply_text(f"✍️ لطفاً جمله‌ای برای \"{word}\" ارسال کنید:")

    elif data.startswith("quiz|"):
        choice = data.split("|")[1]
        chat_id = query.message.chat.id
        session = quiz_sessions.get(chat_id)

        if not session:
            return

        current_item = session["items"][session["current"]]
        correct_meaning = current_item["meaning"]

        if choice == correct_meaning:
            await query.message.reply_text("✅ آفرین درست گفتی!")
        else:
            await query.message.reply_text(f"❌ جواب اشتباه بود. معنی درست:\n<b>{correct_meaning}</b>", parse_mode=ParseMode.HTML)

        session["current"] += 1
        if session["current"] < len(session["items"]):
            await send_quiz_question(chat_id, context)
        else:
            await query.message.reply_text("🏁 آزمون تمام شد!")
            quiz_sessions.pop(chat_id)

# ------------------ MESSAGE FOR EXAMPLE ------------------ #
async def message_for_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in add_example_state:
        return

    word = add_example_state[chat_id]
    example_text = update.message.text.strip()

    try:
        existing = supabase.table("words").select("examples").eq("word", word).single().execute()
        examples = existing.data.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        examples.append(example_text)

        supabase.table("words").update({"examples": examples}).eq("word", word).execute()
        await update.message.reply_text("✅ جمله با موفقیت ذخیره شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ذخیره‌سازی جمله:\n{e}")

    add_example_state.pop(chat_id)

# ------------------ LIST ------------------ #
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    response = supabase.table("words").select("*").order("created_at", desc=True).execute()
    data = response.data

    if not data:
        await update.message.reply_text("⚠️ هیچ کلمه‌ای ذخیره نشده.")
        return

    text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
    for i, word in enumerate(data, 1):
        examples = word.get("examples")
        if not isinstance(examples, list):
            examples = []
        examples_text = ""
        if examples:
            examples_text = "\n📝 مثال:\n" + "\n".join(f"▫️ {e}" for e in examples)
        text += f"{i}. <b>{word['word']}</b> ➜ {word['meaning']}{examples_text}\n\n"

    await update.message.reply_text(text.strip(), parse_mode=ParseMode.HTML)

# ------------------ QUIZ ------------------ #
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    response = supabase.table("words").select("*").execute()
    items = response.data

    if len(items) < 4:
        await update.message.reply_text("⚠️ حداقل ۴ کلمه نیاز است.")
        return

    session = {
        "items": random.sample(items, min(10, len(items))),
        "current": 0
    }
    quiz_sessions[update.effective_chat.id] = session
    await send_quiz_question(update.effective_chat.id, context)

async def send_quiz_question(chat_id, context):
    session = quiz_sessions.get(chat_id)
    if not session:
        return

    item = session["items"][session["current"]]
    correct = item["meaning"]

    options = [correct]
    others = [i["meaning"] for i in session["items"] if i["meaning"] != correct]
    options += random.sample(others, min(3, len(others)))
    random.shuffle(options)

    buttons = [[InlineKeyboardButton(opt, callback_data=f"quiz|{opt}")] for opt in options]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❓ سوال {session['current'] + 1} از {len(session['items'])}\nکلمه: <b>{item['word']}</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )

# ------------------ HELP ------------------ #
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = (
        "📌 <b>دستورات موجود:</b>\n\n"
        "/start – افزودن کلمه جدید\n"
        "/addexample – افزودن جمله به کلمه\n"
        "/list – نمایش کلمات و مثال‌ها\n"
        "/quiz – آزمون چهارگزینه‌ای\n"
        "/help – راهنمای دستورات"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ------------------ MAIN ------------------ #
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addexample", add_example))
    app.add_handler(CommandHandler("list", list_words))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_for_example))

    print("🤖 Bot is running...")
    app.run_polling()
