import os
import json
import logging
from datetime import time as dtime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "3"))

# Словарь для красивых названий
LABELS = {
    "breakfast": "Завтрак", "snack1": "Перекус", "lunch": "Обед", 
    "snack2": "Полдник", "dinner": "Ужин", "water": "Вода"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton("📱 Открыть трекер YHealth", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "👋 Привет! Я твой помощник YHealth.\n\nНажми кнопку внизу, чтобы настроить график.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    profile = db_get(user_id, "profile")
    
    if not profile:
        logger.info(f"No profile in DB for {user_id}")
        await update.effective_message.reply_text("❌ Профиль не найден. Открой приложение и нажми 'Сохранить'.")
        return

    # Чистим старые задачи
    for job in context.job_queue.get_jobs_by_name(f"user_{user_id}"):
        job.schedule_removal()

    jobs_info = []
    
    # 1. Еда
    sched = profile.get("schedule", {})
    for k, v in sched.items():
        if v and ":" in v:
            label = LABELS.get(k, "Прием пищи")
            add_job(context, user_id, v, label)
            jobs_info.append(f"⏰ {v} — {label}")

    # 2. Лекарства
    for m in profile.get("meds", []):
        if m.get("time"):
            add_job(context, user_id, m["time"], f"💊 {m['name']}")
            jobs_info.append(f"⏰ {m['time']} — 💊 {m['name']}")

    # 3. Витамины
    for v in profile.get("vitamins", []):
        if v.get("time"):
            add_job(context, user_id, v["time"], f"🌿 {v['name']}")
            jobs_info.append(f"⏰ {v['time']} — 🌿 {v['name']}")

    if jobs_info:
        msg = "✅ **Напоминания установлены:**\n\n" + "\n".join(sorted(jobs_info))
    else:
        msg = "⚠️ В профиле не указано время для напоминаний."

    await update.effective_message.reply_text(msg, parse_mode="Markdown")

def add_job(context, user_id, t_str, label):
    try:
        h, m = map(int, t_str.split(':'))
        utc_h = (h - TZ_OFFSET) % 24
        context.job_queue.run_daily(
            send_reminder, dtime(hour=utc_h, minute=m),
            chat_id=int(user_id), name=f"user_{user_id}", data={"label": label, "time": t_str}
        )
    except: pass

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(context.job.chat_id, text=f"🔔 Пора! {context.job.data['label']} ({context.job.data['time']})")

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get("action") == "reload_reminders":
            await setup_reminders(update, context)
    except Exception as e:
        logger.error(f"WebAppData Error: {e}")

def main():
    start_server()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    app.run_polling()

if __name__ == "__main__":
    main()