import os
import json
import logging
import random
from datetime import time as dtime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "3"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ВАЖНО: Используем обычную кнопку меню (Reply), только она умеет принимать данные от Web App
    kb = [[KeyboardButton("📱 Открыть трекер YHealth", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "👋 Привет! Я твой помощник YHealth.\n\n"
        "Нажми кнопку внизу, чтобы настроить график.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    # Загружаем профиль из базы
    profile = db_get(user_id, "profile")
    times = []
    
    if not profile:
        logger.info(f"No profile in DB for {user_id}")
        times = ["07:30", "13:00", "19:00"] # Дефолт
    else:
        # Собираем время из всех разделов
        if profile.get("schedule"):
            s = profile["schedule"]
            for k in ["breakfast", "snack1", "lunch", "snack2", "dinner"]:
                if s.get(k): times.append(s[k])
        if profile.get("meds"):
            for m in profile.get("meds", []):
                if m.get("time"): times.append(m["time"])
        if profile.get("vitamins"):
            for v in profile.get("vitamins", []):
                if v.get("time"): times.append(v["time"])

    # Чистим старые задачи
    current_jobs = context.job_queue.get_jobs_by_name(f"user_{user_id}")
    for job in current_jobs:
        job.schedule_removal()

    # Ставим новые и готовим текст для пользователя
    sorted_times = sorted(list(set(times)))
    for t_str in sorted_times:
        try:
            h, m = map(int, t_str.split(':'))
            utc_h = (h - TZ_OFFSET) % 24
            context.job_queue.run_daily(
                send_reminder,
                dtime(hour=utc_h, minute=m),
                chat_id=chat_id,
                name=f"user_{user_id}",
                data={"time": t_str}
            )
        except: continue

    # ТЕПЕРЬ БОТ ПИШЕТ РАСПИСАНИЕ
    if sorted_times:
        schedule_text = "\n".join([f"⏰ {t}" for t in sorted_times])
        msg = f"✅ **Напоминания обновлены!**\n\nВаш новый график:\n{schedule_text}"
    else:
        msg = "✅ График обновлен, но активных напоминаний не найдено."

    await update.effective_message.reply_text(msg, parse_mode="Markdown")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    t_str = job.data.get("time")
    await context.bot.send_message(job.chat_id, text=f"🔔 Пора! Сейчас {t_str}. Не забудь про план!")

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Этот код ловит сигнал от кнопки 'Сохранить' из приложения"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        if data.get("action") == "reload_reminders":
            await setup_reminders(update, context)
    except Exception as e:
        logger.error(f"Error handling web_app_data: {e}")

def main():
    if not TOKEN or not WEBAPP_URL:
        raise ValueError("BOT_TOKEN или WEBAPP_URL не заданы!")

    start_server()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    # Магия связи приложения с ботом
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()