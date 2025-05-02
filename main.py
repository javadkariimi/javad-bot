import os
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# مراحل ورودی کاربر
STEP_WORD = "word"
STEP_MEANING = "meaning"
STEP_EXAMPLE = "example"
user_states = {}

# پشتیبانی از UptimeRobot
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات فعاله ✅"

# /start – شروع افزودن کلمه
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ اجازه استفاده از این ربات را نداری.")
        return
    user_states[update.effective_user.id] = {"step": STEP_WORD}
    await update.message.reply_text("📝 لطفاً کلمه را وارد کن")

# /list – نمایش کلمات، معانی و جملات
async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ اجازه دسترسی نداری.")
        return
    try:
        result = supabase.table("words").select("*").eq("user_id", str(user_id)).execute()
        items = result.data
        if not items:
            await update.message.reply_text("📭 هنوز هیچ کلمه‌ای ذخیره نکردی.")
            return
        text = "📚 <b>کلمه‌های ذخیره‌شده:</b>\n\n"
        for i, item in enumerate(items, 1):
            text += f"{i}. <b>{item['word']}</b>\n🟢 {item['meaning']}\n✏️ {item.get('example', '-')}\n\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")

# ذخیره مراحل
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id != OWNER_ID:
        return
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("لطفاً اول /start رو بزن.")
        return

    if state["step"] == STEP_WORD:
        state["word"] = text
        state["step"] = STEP_MEANING
        await update.message.reply_text("🧠 حالا معنی این کلمه رو بنویس")
    elif state["step"] == STEP_MEANING:
        state["meaning"] = text
        state["step"] = STEP_EXAMPLE
        await update.message.reply_text("✏️ حالا یک جمله نمونه برای این کلمه بنویس")
    elif state["step"] == STEP_EXAMPLE:
        state["example"] = text
        try:
            supabase.table("words").insert({
                "word": state["word"],
                "meaning": state["meaning"],
                "example": state["example"],
                "user_id": str(user_id)
            }).execute()
            await update.message.reply_text("✅ کلمه، معنی و جمله ذخیره شدند!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ذخیره‌سازی: {e}")
        user_states.pop(user_id)

# /help – راهنما
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    text = (
        "📌 <b>دستورات ربات:</b>\n\n"
        "/start – افزودن کلمه، معنی و جمله نمونه\n"
        "/list – نمایش کلمه‌ها و جملات ذخیره‌شده\n"
        "/help – نمایش این راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# اجرای ربات
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()
    app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("list", list_words))
    app_telegram.add_handler(CommandHandler("help", help_command))
    app_telegram.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app_telegram.run_polling()
