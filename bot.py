import os
import json
import logging
from datetime import time as dtime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "3"))

LABELS = {
    "breakfast": "Завтрак", "snack1": "Перекус", "lunch": "Обед", 
    "snack2": "Полдник", "dinner": "Ужин"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Возвращаем Inline-кнопку, чтобы она не перекрывала меню приложения
    kb = [[InlineKeyboardButton("📱 Открыть YHealth", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "👋 Привет! Это YHealth.\n\n"
        "Настраивай график прямо в приложении — всё сохранится автоматически.\n"
        "Чтобы обновить список уведомлений здесь, напиши /remind",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    profile = db_get(user_id, "profile")
    
    if not profile:
        await update.effective_message.reply_text("❌ Профиль еще не создан. Открой приложение и настрой график!")
        return

    # Чистим старые задачи
    for job in context.job_queue.get_jobs_by_name(f"user_{user_id}"):
        job.schedule_removal()

    jobs_info = []
    
    # Собираем время еды
    sched = profile.get("schedule", {})
    for k, v in sched.items():
        if v and ":" in v:
            label = LABELS.get(k, "Прием пищи")
            add_job(context, user_id, v, label)
            jobs_info.append(f"⏰ {v} — {label}")

    # Собираем лекарства
    for m in profile.get("meds", []):
        if m.get("time"):
            add_job(context, user_id, m["time"], f"💊 {m['name']}")
            jobs_info.append(f"⏰ {m['time']} — {m['name']}")

    # Собираем витамины (только те, что включены)
    for v in profile.get("vitamins", []):
        if v.get("enabled") and v.get("time"):
            add_job(context, user_id, v["time"], f"🌿 {v['name']}")
            jobs_info.append(f"⏰ {v['time']} — {v['name']}")

    if jobs_info:
        msg = "✅ **Напоминания активны:**\n\n" + "\n".join(sorted(jobs_info))
    else:
        msg = "⚠️ В профиле нет активных напоминаний."

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

def main():
    if not TOKEN: raise ValueError("BOT_TOKEN is missing")
    start_server()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()