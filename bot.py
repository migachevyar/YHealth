from server import db_get
import os
import json
import logging
import random
import urllib.request
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
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "3"))

with open("webapp/config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)

REMINDER_TEXTS = {
    "07:30": [
        "💧 Доброе утро! Стакан воды прямо сейчас — запускает метаболизм и смывает сонливость",
        "💧 Просыпаемся! Вода натощак — самый простой способ ускорить обмен веществ на весь день",
        "💧 Утро начинается с воды. За ночь ты потерял 0.5–1 л — верни организму своё",
        "💧 Стакан воды до завтрака = 5 минут заботы о себе. Желудок говорит спасибо 🙏",
    ],
    "08:00": [
        "🍳 Завтрак! Белок утром снижает тягу к сладкому на весь день. Яйца, творог — выбирай",
        "🍳 Завтрак пропускать — худшая идея. Голодный мозг работает на 20% хуже. Поешь!",
        "🍳 Время завтракать! Исследования: люди завтракающие стройнее тех кто не завтракает",
        "🍳 Завтрак — первый кирпичик сегодняшнего прогресса. Не пропусти 💪",
    ],
    "10:30": [
        "🥜 Перекус! Небольшой приём пищи сейчас = меньше риска переесть на обеде. Творог или орехи",
        "🥜 Небольшой перекус поддержит уровень сахара до обеда. Без скачков энергии!",
        "🥜 10:30 — идеальное время. Не жди пока проголодаешься до боли в животе 😅",
        "🥜 Орехи + фрукт или творог. 5 минут — и следующие 2.5 часа без мыслей о еде",
    ],
    "13:00": [
        "🥗 Обед! Белок + углеводы + овощи. Ешь медленно — мозгу нужно 20 мин зафиксировать сытость",
        "🥗 Время обеда! Начни с белка и овощей, углеводы в конце — меньше скачок сахара",
        "🥗 Обед — инвестиция в энергию на вторую половину дня 💡",
        "🥗 Не ешь за компьютером! Мозг не считает еду при параллельной активности",
    ],
    "16:30": [
        "🍎 Перекус 2! До ужина ещё 2.5 часа — без перекуса придёшь голодным и съешь лишнего",
        "🍎 Кефир, яблоко, пара хлебцев с яйцом — выбирай. Главное не печеньки 🙅",
        "🍎 Второй перекус поддержит метаболизм и настроение до ужина",
        "🍎 16:30 — самое коварное время. Именно сейчас тянет на сладкое. Упреди белковым перекусом",
    ],
    "19:00": [
        "🐟 Ужин! Белок + овощи, без тяжёлых углеводов. До сна минимум 3 часа",
        "🐟 Рыба, курица или творог + овощи. Лёгкий ужин = лёгкий утренний подъём",
        "🐟 Ужин — финальный аккорд питания. Сделай его правильным! Белок, не углеводы",
        "🐟 После 19:30 — только вода и витамины. Желудок говорит спасибо 😄",
    ],
    "22:00": [
        "🌙 Магний перед сном! 1–2 таблетки цитрата. Глубокий сон — когда мышцы растут",
        "🌙 Пора принять магний! Снижает кортизол, улучшает качество сна",
        "🌙 22:00 — время магния. Хороший сон важнее самой лучшей тренировки",
        "🌙 Магний + хороший сон = прогресс. Восстановление ночью, не в зале 💪",
    ],
}

MEAL_EMOJIS = {
    "water": "💧", "breakfast": "🍳", "snack1": "🥜", "snack2": "🍎",
    "lunch": "🥗", "dinner": "🐟",
}

MEAL_TIPS = {
    "water": ["Стакан воды — запускает метаболизм и пробуждает организм", "Вода натощак — первый шаг к здоровому дню"],
    "breakfast": ["Белковый завтрак задаёт тон всему дню!", "Не пропускай — голодный мозг работает на 20% хуже"],
    "snack1": ["Небольшой перекус = меньше риска переесть на обеде", "Творог, орехи или яйцо — идеально"],
    "lunch": ["Белок + углеводы + овощи. Ешь медленно!", "Самый важный приём пищи дня"],
    "snack2": ["До ужина ещё далеко — поддержи уровень энергии", "Кефир, яблоко или хлебцы"],
    "dinner": ["Белок + овощи, без тяжёлых углеводов", "Лёгкий ужин = лёгкий подъём завтра"],
}


def get_user_schedule(user_id: int):
    try:
        profile = db_get(str(user_id), "profile")
        print(f"🔥 PROFILE FROM DB: {profile}")
    except Exception as e:
        print(f"❌ ERROR loading profile: {e}")
        profile = None

    if not profile:
        # дефолтное расписание
        return ["07:30","08:00","10:30","13:00","16:30","19:00","22:00"]

    # если есть профиль — берём оттуда
    meals = profile.get("meals", [])

    times = []
    for m in meals:
        t = m.get("time")
        if t:
            times.append(t)

    if not times:
        return ["07:30","08:00","10:30","13:00","16:30","19:00","22:00"]

    return times


def build_reminders_from_schedule(schedule):
    if not schedule:
        return CONFIG.get("reminders", [])

    events = {}

    for meal in schedule.get("meals", []):
        t = meal.get("time", "")
        if not t:
            continue
        events.setdefault(t, []).append(("meal", meal.get("name",""), meal))

    for vit in schedule.get("vitamins", []):
        t = vit.get("time", "")
        if not t:
            continue
        events.setdefault(t, []).append(("vit", vit.get("name",""), vit))

    for med in schedule.get("meds", []):
        t = med.get("time", "")
        if not t:
            continue
        events.setdefault(t, []).append(("med", med.get("name",""), med))

    reminders = []
    for t, items in sorted(events.items()):
        meals = [i for i in items if i[0] == "meal"]
        vits = [i for i in items if i[0] == "vit"]
        meds = [i for i in items if i[0] == "med"]
        text = build_grouped_text(t, meals, vits, meds)
        reminders.append({"time": t, "text": text})

    return reminders


def build_grouped_text(t, meals, vits, meds):
    lines = []

    for _, name, item in meals:
        mid = item.get("id", "")
        emoji = MEAL_EMOJIS.get(mid, "🍽")
        tips = MEAL_TIPS.get(mid, [f"Время: {name}"])
        tip = random.choice(tips)
        lines.append(f"{emoji} {name}: {tip}")

    if len(vits) == 1:
        lines.append(f"💊 {vits[0][1]} — не забудь принять!")
    elif len(vits) > 1:
        vnames = ", ".join(v[1] for v in vits)
        lines.append(f"💊 Витамины: {vnames}")

    if len(meds) == 1:
        dose = meds[0][2].get("dose", "")
        lines.append(f"💉 {meds[0][1]}{' — ' + dose if dose else ''}")
    elif len(meds) > 1:
        lines.append(f"💉 Лекарства: {', '.join(m[1] for m in meds)}")

    if not lines:
        txt = REMINDER_TEXTS.get(t, [])
        if txt:
            return random.choice(txt)
        return f"⏰ {t} — пора следить за здоровьем!"

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Привет! Нажми кнопку чтобы открыть дневник здоровья.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await context.bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=f"💬 Сообщение от {user.first_name}:\n\n{text}"
        )
    await update.message.reply_text("Получено, спасибо!")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    text = job.data["text"]
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.error(f"Reminder error: {e}")


async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    jq = context.job_queue

    for job in jq.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()

    user_schedule = get_user_schedule(user_id)
    reminders = build_reminders_from_schedule(user_schedule)

    scheduled = []
    for r in reminders:
        h, m = map(int, r["time"].split(":"))
        utc_total = (h * 60 + m) - TZ_OFFSET * 60
        utc_total = utc_total % (24 * 60)
        jq.run_daily(
            send_reminder,
            time=dtime(utc_total // 60, utc_total % 60, 0),
            data={"chat_id": chat_id, "time": r["time"], "text": r["text"]},
            name=f"rem_{chat_id}_{r['time']}"
        )
        scheduled.append(r["time"])

    tz_name = {0:"UTC", 1:"UTC+1", 2:"UTC+2", 3:"Москва (UTC+3)",
               4:"Самара", 5:"Екатеринбург", 7:"Красноярск",
               8:"Иркутск", 10:"Владивосток"}.get(TZ_OFFSET, f"UTC+{TZ_OFFSET}")

    source = "твоё личное расписание ✓" if user_schedule else "расписание по умолчанию"
    await update.message.reply_text(
        f"✅ Напоминания включены — {len(reminders)} уведомлений\n"
        f"🕐 Часовой пояс: {tz_name}\n"
        f"📋 {source}\n\n"
        f"Расписание: {' • '.join(scheduled)}\n\n"
        f"Чтобы отключить — /stop"
    )


async def stop_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    removed = sum(1 for job in context.job_queue.jobs()
                  if job.data and job.data.get("chat_id") == chat_id
                  and not job.schedule_removal())
    await update.message.reply_text(
        f"🔕 Напоминания отключены.\nЧтобы включить снова — /remind"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "🏥 YHealth — дневник здоровья\n\n"
        "/start — открыть трекер\n"
        "/remind — включить напоминания\n"
        "/stop — отключить напоминания\n"
        "/help — справка\n\n"
        "Напоминания берутся из твоего расписания в приложении.\n"
        "Если менял расписание — отправь /remind заново.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN не задан")
    if not WEBAPP_URL:
        raise ValueError("WEBAPP_URL не задан")

    start_server()
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
