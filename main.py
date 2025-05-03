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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("📥 لطفاً کلمه را ارسال کن:فرمت: Wort , der , -e ➜ معنی")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    text = update.message.text
    if "➜" in text:
        word, meaning = map(str.strip, text.split("➜", 1))
        existing = supabase.table("words").select("index").eq("user_id", str(update.effective_user.id)).execute().data
        max_index = max([w["index"] for w in existing if "index" in w], default=0)
        result = supabase.table("words").insert({
            "word": word,
            "meaning": meaning,
            "user_id": str(update.effective_user.id),
            "index": max_index + 1
        }).execute()
        if result.data:
            await update.message.reply_text("✅ کلمه ذخیره شد.")
        else:
            await update.message.reply_text("❌ خطا در ذخیره‌سازی.")
    elif "add_example_word" in context.user_data:
        word_data = context.user_data.pop("add_example_word")
        examples = word_data.get("examples") or []
        if isinstance(examples, str):
            import json
            examples = json.loads(examples)
        examples.append(text)
        result = supabase.table("words").update({"examples": examples}).eq("id", word_data["id"]).execute()
        if result.data:
            await update.message.reply_text("✅ جمله ذخیره شد.")
        else:
            await update.message.reply_text("❌ خطا در ذخیره‌سازی جمله.")
    else:
        await update.message.reply_text("❗ لطفاً از فرمت درست استفاده کن: Wort , der , -e ➜ معنی")


async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    words = supabase.table("words").select("*").eq("user_id", str(update.effective_user.id)).order("index").execute().data
    if not words:
        await update.message.reply_text("⚠️ هیچ کلمه‌ای ذخیره نشده.")
        return

    text = "📚 <b>کلمه‌های ذخیره‌شده:</b>"
    for w in words:
        text += f"{w['index']}. <b>{w['word']}</b> ➜ {w['meaning']}"
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
    await update.message.reply_text(f"✍ لطفاً جمله‌ای برای "{selected['word']}" ارسال کنید:")


async def export_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ لطفاً شماره‌ها را بعد از /export بنویس، مثل:
/export 1 3 5")
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

    text = "📋 <b>کلمه‌های انتخاب‌شده:</b>"
    for w in filtered:
        text += f"{w['index']}. <b>{w['word']}</b> ➜ {w['meaning']}"
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
        "📌 <b>دستورات ربات:</b>"
        "/start – افزودن کلمه و معنی"
        "/addexample [کلمه یا شماره] – افزودن جمله برای کلمه"
        "/list – نمایش لیست کلمات"
        "/quiz – آزمون چهارگزینه‌ای"
        "/export – خروجی گرفتن از شماره کلمات"
        "/help – راهنمای دستورات"
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


async def ask_question(update, context):
    session = context.user_data["quiz"]
    item = session["items"][session["current"]]
    options = random.sample(session["items"], 3)
    options.append(item)
    random.shuffle(options)

    buttons = [[InlineKeyboardButton(o["meaning"], callback_data=o["word"])] for o in options]
    await update.message.reply_text(
        f"❓ سوال {session['current'] + 1} از {len(session['items'])}
<b>{item['word']}</b> یعنی چی؟",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def answer_callback(update, context):
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
        await query.edit_message_text(f"❌ جواب اشتباه بود. معنی درست:
{current_item['meaning']}")

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
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()