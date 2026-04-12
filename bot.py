import os
import json
import logging
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from server import start_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
FEEDBACK_CHAT_ID = os.environ.get("FEEDBACK_CHAT_ID", "")

with open("webapp/config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(
        "Открыть трекер",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )]]
    await update.message.reply_text(
        "Привет! Нажми кнопку чтобы открыть дневник здоровья.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    if text.startswith("/"):
        return
    if FEEDBACK_CHAT_ID:
        user = update.effective_user
        name = user.first_name or "Пользователь"
        await context.bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=f"Замечание от {name}:\n\n{text}"
        )
    await update.message.reply_text("Замечание получено, спасибо!")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    text = job.data["text"]
    kb = [[InlineKeyboardButton(
        "Открыть трекер",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )]]
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    reminders = CONFIG.get("reminders", [])
    for r in reminders:
        h, m = map(int, r["time"].split(":"))
        jq.run_daily(
            send_reminder,
            time=time(h, m, 0),
            data={"chat_id": chat_id, "text": r["text"]},
            name=f"reminder_{chat_id}_{r['time']}"
        )
    await update.message.reply_text(
        f"Напоминания включены. Настроено {len(reminders)} напоминаний."
    )


async def stop_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    jobs = jq.get_jobs_by_name
    removed = 0
    current_jobs = jq.jobs()
    for job in current_jobs:
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()
            removed += 1
    await update.message.reply_text(f"Напоминания отключены ({removed} шт).")


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN не задан в переменных окружения")
    if not WEBAPP_URL:
        raise ValueError("WEBAPP_URL не задан в переменных окружения")

    start_server()
    logger.info("Mini App server started")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    app.add_handler(CommandHandler("stop", stop_reminders))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback))
    app.run_polling()


if __name__ == "__main__":
    main()
