
import os
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
OWNER_ID = 52134388  # آیدی عددی جــواد

# اتصال به دیتابیس
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["telegram_bot"]
collection = db["words"]

# حافظه مرحله‌ای کاربران
user_states = {}

# مرحله‌های ورودی
STEP_WORD = "word"
STEP_MEANING = "meaning"
STEP_EXAMPLE = "example"

# Flask برای زنده نگه داشتن
app = Flask(__name__)
@app.route("/")
def home():
    return "ربات زنده است و به MongoDB وصله ✅"

# شروع فرآیند
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("شما اجازه استفاده از این ربات را ندارید ❌")
        return

    user_id = update.effective_user.id
    user_states[user_id] = {"step": STEP_WORD}
    await update.message.reply_text("لطفاً کلمه خود را وارد کنید 📝")

# مدیریت پیام‌ها
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id != OWNER_ID:
        return

    state = user_states.get(user_id)

    if not state:
        await update.message.reply_text("لطفاً ابتدا /start را وارد کنید.")
        return

    if state["step"] == STEP_WORD:
        state["word"] = text
        state["step"] = STEP_MEANING
        await update.message.reply_text("حالا معنی کلمه را وارد کنید 🧠")
    elif state["step"] == STEP_MEANING:
        state["meaning"] = text
        state["step"] = STEP_EXAMPLE
        await update.message.reply_text("حالا برای این کلمه یک مثال بزنید ✍️")
    elif state["step"] == STEP_EXAMPLE:
        state["example"] = text

        # ذخیره در دیتابیس
        collection.insert_one({
            "word": state["word"],
            "meaning": state["meaning"],
            "example": state["example"],
            "user_id": user_id
        })

        # پاک کردن وضعیت
        user_states.pop(user_id)
        await update.message.reply_text("✅ کلمه با موفقیت ذخیره شد!")

if __name__ == "__main__":
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    telegram_app.run_polling()
