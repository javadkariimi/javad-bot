
import os
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# بارگذاری .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 52134388  # آیدی عددی جـواد

# Flask برای alive نگه‌داشتن در Render
app = Flask(__name__)

@app.route("/")
def home():
    return "ربات آنلاین است ✅"

# فرمان start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("شما اجازه استفاده از این ربات را ندارید ❌")
    else:
        await update.message.reply_text("سلام جـواد عزیز، ربات فعاله و فقط به روی تو بازه 💌")

if __name__ == "__main__":
    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.run_polling()
