import os
import re
import random
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from supabase import create_client, Client
from docx import Document
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = ApplicationBuilder().token(BOT_TOKEN).build()

user_states = {}  # اضافه شد


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

async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    words = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).order("index").execute().data
    if not words:
        await update.message.reply_text("⚠️ هیچ کلمه‌ای ذخیره نشده.")
        return

    text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n"
    for w in words:
        text += f"{w['index']}. <b>{w['word']}</b> ➜ {w['meaning']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text("❗ لطفاً کلمه یا شماره را وارد کن: /addexample Haus یا /addexample 3")
        return

    keyword = " ".join(context.args).strip()
    words = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).execute().data
    selected = None
    if keyword.isdigit():
        selected = next((w for w in words if w.get("index") == int(keyword)), None)
    else:
        selected = next((w for w in words if w.get("word") == keyword), None)

    if not selected:
        await update.message.reply_text("❌ کلمه‌ای پیدا نشد.")
        return

    context.user_data["add_example_word"] = selected
    await update.message.reply_text(f'✍ لطفاً جمله‌ای برای "{selected["word"]}" ارسال کنید:')

async def export_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ لطفاً شماره‌ها را بعد از /export بنویس، مثل:/export 1 3 5")
        return

    try:
        indexes = [int(x) for x in context.args if x.isdigit()]
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط شماره‌های معتبر وارد کن.")
        return

    data = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).execute().data
    filtered = [w for w in data if w.get("index") in indexes]

    if not filtered:
        await update.message.reply_text("❌ کلمه‌ای با این شماره‌ها پیدا نشد.")
        return

    text = "📋 <b>کلمه‌های انتخاب‌شده:</b>\n"
    for w in filtered:
        text += f"{w['index']}. <b>{w['word']}</b> ➜ {w['meaning']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    doc = Document()
    doc.add_heading("Exportierte Wörter", 0)
    for item in filtered:
        doc.add_heading(f"{item['index']}. {item['word']}", level=1)
        doc.add_paragraph(f"🔹 معنی: {item['meaning']}")
        examples = item.get("examples") or []
        if examples:
            doc.add_paragraph("📝 مثال‌ها:")
            for ex in examples:
                doc.add_paragraph(f"• {ex}", style='List Bullet')

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    await update.message.reply_document(document=buffer, filename="woerter_export.docx")

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

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    data = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).execute().data
    if len(data) < 4:
        await update.message.reply_text("⚠️ حداقل ۴ کلمه لازم است.")
        return

    session = {
        "items": random.sample(data, min(10, len(data))),
        "current": 0,
        "score": 0
    }
    context.user_data["quiz"] = session
    await ask_question(update, context)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = context.user_data["quiz"]
    item = session["items"][session["current"]]
    options = random.sample(session["items"], 3)
    options.append(item)
    random.shuffle(options)

    buttons = [[InlineKeyboardButton(o["meaning"], callback_data=o["word"])] for o in options]
    await update.message.reply_text(
        f"❓ سوال {session['current'] + 1} از {len(session['items'])}: <b>{item['word']}</b> یعنی چی؟",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("quiz")
    if not session:
        return
    current_item = session["items"][session["current"]]
    if query.data == current_item["word"]:
        session["score"] += 1
        await query.edit_message_text("✅ آفرین درست گفتی")
    else:
        await query.edit_message_text(f"❌ جواب اشتباه بود. معنی درست: {current_item['meaning']}")

    session["current"] += 1
    if session["current"] < len(session["items"]):
        await ask_question(query, context)
    else:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"🏁 آزمون تمام شد. امتیاز: {session['score']} از {len(session['items'])}"
        )

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_words))
app.add_handler(CommandHandler("addexample", add_example_command))
app.add_handler(CommandHandler("quiz", quiz))
app.add_handler(CommandHandler("export", export_words))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(answer_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

app.run_polling()