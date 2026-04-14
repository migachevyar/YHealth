import os
import json
import logging
import random
from datetime import time as dtime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server

logging.basicConfig(level=logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
FEEDBACK_CHAT_ID = os.environ.get("FEEDBACK_CHAT_ID", "")

with open("webapp/config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)

# ─── REMINDER TEXTS ───
# Multiple variants per time slot — bot picks random each day
REMINDER_TEXTS = {
    "07:30": [
        "💧 Доброе утро! Стакан воды прямо сейчас — запускает метаболизм и смывает сонливость",
        "💧 Просыпаемся! Вода натощак — самый простой способ ускорить обмен веществ на весь день",
        "💧 Утро начинается с воды. За ночь ты потерял 0.5–1 л — верни организму своё",
        "💧 Вода, вода, вода! Пока ты не выпил стакан — день официально не начался 😄",
        "💧 Стакан воды = 5 минут до завтрака. Желудок говорит спасибо. Поджелудочная тоже",
    ],
    "08:00": [
        "🍳 Завтрак! Белок утром снижает тягу к сладкому на весь день. Яйца, творог, куриная грудка — выбирай",
        "🍳 Завтрак пропускать — худшая идея. Голодный мозг работает на 20% хуже. Поешь!",
        "🍳 Время завтракать! Исследования показывают: люди завтракающие стройнее тех кто не завтракает",
        "🍳 Завтрак — первый кирпичик сегодняшнего прогресса. Не пропусти его 💪",
        "🍳 Доброе утро! Завтрак через 30–60 мин после подъёма — оптимально для метаболизма",
    ],
    "10:30": [
        "🥜 Перекус! Небольшой приём пищи сейчас = меньше риска переесть на обеде. Творог или орехи",
        "🥜 Небольшой перекус поддержит уровень сахара в крови до обеда. Без скачков энергии!",
        "🥜 10:30 — идеальное время для перекуса. Не жди пока проголодаешься до боли в животе 😅",
        "🥜 Перекус — это не слабость, это стратегия. Кто кушает вовремя — не срывается вечером",
        "🥜 Орехи + фрукт или творог. 5 минут — и следующие 2.5 часа без мыслей о еде",
    ],
    "13:00": [
        "🥗 Обед! Самый важный приём пищи. Белок + углеводы + овощи. Ешь медленно — мозгу нужно 20 мин чтобы зафиксировать сытость",
        "🥗 Время обеда! Лайфхак: начни с белка и овощей, углеводы в конце — меньше скачок сахара",
        "🥗 Обед — это не перерыв от работы, это инвестиция в энергию на вторую половину дня 💡",
        "🥗 Не ешь за компьютером! Мозг не считает еду при параллельной активности — переедание гарантировано",
        "🥗 Обед! Курица + гречка или рыба + рис. Простая формула здорового питания работает",
    ],
    "16:30": [
        "🍎 Перекус 2! До ужина ещё 2.5 часа — без перекуса придёшь к столу голодным и съешь лишнего",
        "🍎 Кефир, яблоко, пара хлебцев с яйцом — выбирай. Главное не печеньки 🙅",
        "🍎 Второй перекус поддержит метаболизм и настроение до ужина. Не игнорируй!",
        "🍎 16:30 — самое коварное время. Именно сейчас тянет на сладкое. Упреди это белковым перекусом",
        "🍎 Небольшой перекус сейчас = спокойный ужин без переедания. Работает 100%",
    ],
    "19:00": [
        "🐟 Ужин! Последний приём пищи дня. Белок + овощи, без тяжёлых углеводов. До сна минимум 3 часа",
        "🐟 Время ужинать! Рыба, курица или творог + овощи. Лёгкий ужин = лёгкий утренний подъём",
        "🐟 Ужин — финальный аккорд сегодняшнего питания. Сделай его правильным! Белок, а не углеводы",
        "🐟 После 19:30 — только вода и витамины. Желудок говорит спасибо, весы тоже 😄",
        "🐟 Ужин без простых углеводов = минус жир ночью. Организм работает пока ты спишь",
    ],
    "22:00": [
        "🌙 Магний перед сном! 1–2 таблетки цитрата. Глубокий сон — это когда мышцы растут и жир сжигается",
        "🌙 Пора принять магний! Снижает кортизол, улучшает качество сна. Утром почувствуешь разницу",
        "🌙 22:00 — время магния. Хороший сон важнее самой лучшей тренировки. Не игнорируй восстановление",
        "🌙 Магний + хороший сон = прогресс. Восстановление происходит ночью, не в зале 💪",
        "🌙 Перед сном: магний выпит, телефон отложен, завтра будет продуктивным. Приятных снов! 🌟",
    ],
}

# Fallback texts for any other time
GENERIC_TEXTS = [
    "⏰ Время следить за здоровьем! Открой YHealth и отметь прогресс",
    "💪 Маленькие шаги каждый день — большой результат через год",
    "✅ Проверь свой прогресс на сегодня в YHealth!",
]


def get_reminder_text(reminder_time: str, reminder_base_text: str) -> str:
    """Get a random text for the given time, falling back to config text."""
    texts = REMINDER_TEXTS.get(reminder_time)
    if texts:
        return random.choice(texts)
    return reminder_base_text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Привет! Нажми кнопку чтобы открыть дневник здоровья.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data sent from Mini App (feedback, etc.)"""
    if not update.message or not update.message.web_app_data:
        return
    try:
        data = json.loads(update.message.web_app_data.data)
        if data.get('type') == 'feedback' and FEEDBACK_CHAT_ID:
            user = update.effective_user
            name = user.first_name or 'Пользователь'
            await context.bot.send_message(
                chat_id=FEEDBACK_CHAT_ID,
                text=f"💬 Замечание от {name} (@{user.username or 'нет'}):\n\n{data.get('text','')}"
            )
    except Exception as e:
        logger.error(f"WebApp data error: {e}")


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    if text.startswith("/"):
        return
    if FEEDBACK_CHAT_ID:
        user = update.effective_user
        name = user.first_name or 'Пользователь'
        await context.bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=f"💬 Сообщение от {name}:\n\n{text}"
        )
    await update.message.reply_text("Получено, спасибо!")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    reminder_time = job.data["time"]
    base_text = job.data["text"]
    text = get_reminder_text(reminder_time, base_text)
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        logger.error(f"Reminder error: {e}")


async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    # Remove old reminders for this user
    for job in jq.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()

    # TZ_OFFSET: hours ahead of UTC (e.g. Moscow = 3, Novosibirsk = 7)
    tz_offset = int(os.environ.get("TZ_OFFSET", "3"))

    reminders = CONFIG.get("reminders", [])
    scheduled = []
    for r in reminders:
        h, m = map(int, r["time"].split(":"))
        # Convert local time to UTC
        utc_total = (h * 60 + m) - tz_offset * 60
        utc_total = utc_total % (24 * 60)  # wrap around midnight
        utc_h = utc_total // 60
        utc_m = utc_total % 60
        jq.run_daily(
            send_reminder,
            time=dtime(utc_h, utc_m, 0),
            data={"chat_id": chat_id, "time": r["time"], "text": r["text"]},
            name=f"rem_{chat_id}_{r['time']}"
        )
        scheduled.append(r["time"])

    tz_name = {0:"UTC", 1:"UTC+1", 2:"UTC+2", 3:"Москва (UTC+3)",
               4:"Самара (UTC+4)", 5:"Екатеринбург (UTC+5)",
               6:"Омск (UTC+6)", 7:"Красноярск (UTC+7)",
               8:"Иркутск (UTC+8)", 9:"Якутск (UTC+9)",
               10:"Владивосток (UTC+10)"}.get(tz_offset, f"UTC+{tz_offset}")

    await update.message.reply_text(
        f"✅ Напоминания включены — {len(reminders)} уведомлений в день\n"
        f"🕐 Часовой пояс: {tz_name}\n\n"
        f"Расписание: " + " • ".join(scheduled) + "\n\n"
        f"Чтобы отключить — /stop"
    )


async def stop_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    removed = 0
    for job in context.job_queue.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()
            removed += 1
    await update.message.reply_text(
        f"🔕 Напоминания отключены ({removed} шт).\n"
        f"Чтобы включить снова — напиши /remind"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "🏥 *YHealth — дневник здоровья*\n\n"
        "📱 /start — открыть трекер\n"
        "🔔 /remind — включить ежедневные напоминания\n"
        "🔕 /stop — отключить напоминания\n"
        "❓ /help — эта справка\n\n"
        "Напоминания приходят по расписанию:\n"
        "7:30 • 8:00 • 10:30 • 13:00 • 16:30 • 19:00 • 22:00",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb)
    )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN не задан")
    if not WEBAPP_URL:
        raise ValueError("WEBAPP_URL не задан")

    start_server()
    logger.info("Server started")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    app.add_handler(CommandHandler("stop", stop_reminders))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
