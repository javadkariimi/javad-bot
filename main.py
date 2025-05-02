import os
import json
import random
import re
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from supabase import create_client, Client
from docx import Document

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
user_states = {}
quiz_sessions = {}

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
    options = random.sample(session["items"], 3)
    if item not in options:
        options[random.randint(0, 2)] = item
    random.shuffle(options)
    keyboard = [[InlineKeyboardButton(w["meaning"], callback_data=f"quiz|{user_id}|{w['id']}")] for w in options]
    text = f"❓ سوال {index + 1} از {len(session['items'])}\n<b>{item['word']}</b> یعنی چه؟"
    await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def quiz_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, user_id, answer_id = query.data.split("|")
    session = quiz_sessions.get(user_id)
    if not session:
        return
    current_item = session["items"][session["current"]]
    correct = current_item["id"] == answer_id
    session["score"] += int(correct)
    reply = "✅ درست گفتی!" if correct else f"❌ جواب اشتباه بود. معنی درست:\n<b>{current_item['meaning']}</b>"
    session["current"] += 1
    await query.edit_message_text(reply, parse_mode=ParseMode.HTML)
    if session["current"] < len(session["items"]):
        await send_question(update, context, user_id)
    else:
        score = session["score"]
        total = len(session["items"])
        await context.bot.send_message(chat_id=user_id, text=f"🏁 آزمون تمام شد!\nامتیاز: {score} از {total}")
        quiz_sessions.pop(user_id)

async def add_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = supabase.table("words").select("id,word").eq("user_id", user_id).order("created_at", desc=True).execute().data
    if not data:
        await update.message.reply_text("❗️هیچ کلمه‌ای ثبت نکردی.")
        return
    keyboard = [[InlineKeyboardButton(w["word"], callback_data=f"select_example|{w['id']}")] for w in data]
    await update.message.reply_text("🔍 کلمه‌ای انتخاب کن که می‌خوای جمله براش اضافه کنی:", reply_markup=InlineKeyboardMarkup(keyboard))

async def example_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, word_id = query.data.split("|")
    context.user_data["addexample_id"] = word_id
    await query.edit_message_text("✍ جمله رو وارد کن:")

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


async def export_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ لطفاً شماره‌ها را بعد از /export بنویس، مثل:\n/export 1 3 5")
        return
    try:
        indexes = [int(x) for x in context.args if x.isdigit()]
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط شماره‌های معتبر وارد کن.")
        return

    if not indexes:
        await update.message.reply_text("❗ شماره‌ای وارد نشده یا نامعتبر است.")
        return

    data = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).execute().data
    filtered = [w for w in data if w.get("index") in indexes]

    if not filtered:
        await update.message.reply_text("❌ هیچ کلمه‌ای با این شماره‌ها پیدا نشد.")
        return

    text = "📋 <b>کلمه‌های انتخاب‌شده:</b>\n\n"
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
        "📌 <b>دستورات ربات:</b>\n\n"
        "/start – افزودن کلمه و معنی\n"
        "/addexample [کلمه] – افزودن جمله برای کلمه\n"
        "/list – نمایش لیست کامل\n"
        "/quiz – آزمون ۱۰ سواله\n"
        "/export – خروجی گرفتن از کلمات با شماره‌ها\n"
        "/help – راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_words))
app.add_handler(CommandHandler("quiz", quiz))
app.add_handler(CommandHandler("addexample", add_example))
app.add_handler(CommandHandler("export", export_words))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(quiz_button, pattern="^quiz\\|"))
app.add_handler(CallbackQueryHandler(example_button, pattern="^select_example\\|"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, example_response))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

if __name__ == "__main__":
    print("✅ Bot is running...")
    app.run_polling()
