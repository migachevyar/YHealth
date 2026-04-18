import os, json, logging, random
from datetime import time as dtime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get, profile_update_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
FEEDBACK_CHAT_ID = os.environ.get("FEEDBACK_CHAT_ID", "")
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "3"))

MEAL_TEXTS = {
    "water":     ["💧 Стакан воды — запускает метаболизм и пробуждает организм"],
    "breakfast": ["🍳 Завтрак! Белок утром снижает тягу к сладкому на весь день",
                  "🍳 Не пропускай завтрак — голодный мозг работает на 20% хуже"],
    "snack1":    ["🥜 Перекус! Небольшой приём сейчас = меньше риска переесть на обеде",
                  "🥜 Творог, орехи или яйцо — идеальный перекус"],
    "lunch":     ["🥗 Обед! Белок + углеводы + овощи. Ешь медленно!",
                  "🥗 Самый важный приём пищи — не пропускай"],
    "snack2":    ["🍎 Перекус 2! До ужина ещё далеко — поддержи уровень энергии",
                  "🍎 Кефир, яблоко или хлебцы — выбирай"],
    "dinner":    ["🐟 Ужин! Белок + овощи, без тяжёлых углеводов. До сна 3 часа",
                  "🐟 Лёгкий ужин = лёгкий подъём завтра утром"],
}

VIT_NAMES = {
    "omega":"Омега-3","vitd":"Витамин D3+K2","vitc":"Витамин C",
    "vitb12":"Витамин B12","creatine":"Креатин","magnesium":"Магний B6",
    "zinc":"Цинк","calcium":"Кальций","iron":"Железо","probiotics":"Пробиотики",
}

# Maps telegram uid (str) -> chat_id for users who have active reminders
_user_chat_ids: dict = {}


def build_reminders(profile):
    """Build grouped reminders from profile. Returns [{time, text}]"""
    if not profile:
        return []

    vit_list   = profile.get("vitamins", [])
    meds_list  = profile.get("meds", [])
    sched_list = profile.get("schedule", [])

    print(
        f"[BUILD] schedule={[(m.get('id'), m.get('time'), m.get('enabled')) for m in sched_list if isinstance(m, dict)]}"
        f" | vitamins={vit_list}"
        f" | vitHidden={profile.get('vitHidden', [])}"
        f" | meds_count={len(meds_list)}"
        f" | medsHidden={profile.get('medsHidden', [])}",
        flush=True
    )

    events = {}

    # Meals
    for meal in sched_list:
        if not isinstance(meal, dict): continue
        if not meal.get("enabled", True): continue
        t = meal.get("time", "")
        if not t: continue
        events.setdefault(t, []).append(("meal", meal.get("name", ""), meal.get("id", "")))

    # Vitamins
    vit_hidden = profile.get("vitHidden", [])
    vit_times  = profile.get("vitTimes", {})
    bf_time = (
        next((m.get("time") for m in sched_list
              if isinstance(m, dict) and m.get("id") == "breakfast"), None)
        or profile.get("breakfastTime", "08:00")
    )
    ln_time = (
        next((m.get("time") for m in sched_list
              if isinstance(m, dict) and m.get("id") == "lunch"), None)
        or "13:00"
    )

    def mins_to_time(mins):
        h, m = divmod(int(mins) % 1440, 60)
        return f"{h:02d}:{m:02d}"

    def time_to_mins(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m

    bf_mins = time_to_mins(bf_time)

    VIT_DEFAULT_TIMES = {
        "omega":      bf_time,
        "vitd":       bf_time,
        "vitc":       bf_time,
        "vitb12":     bf_time,
        "creatine":   bf_time,
        "magnesium":  "22:00",
        "zinc":       ln_time,
        "calcium":    ln_time,
        "iron":       mins_to_time(bf_mins - 30),
        "probiotics": mins_to_time(bf_mins - 30),
    }

    for vid in vit_list:
        if vid in vit_hidden: continue
        t = vit_times.get(vid) or VIT_DEFAULT_TIMES.get(vid, bf_time)
        name = VIT_NAMES.get(vid, vid)
        events.setdefault(t, []).append(("vit", name, vid))

    # Meds — medsHidden stores integer indices
    meds_hidden = profile.get("medsHidden", [])
    for i, med in enumerate(meds_list):
        if not isinstance(med, dict): continue
        if i in meds_hidden: continue
        t = med.get("time", "")
        if not t: continue
        events.setdefault(t, []).append(("med", med.get("name", ""), ""))

    reminders = []
    for t, items in sorted(events.items()):
        lines = []
        for typ, name, mid in items:
            if typ == "meal":
                texts = MEAL_TEXTS.get(mid, [f"🍽 {name}"])
                lines.append(random.choice(texts))
            elif typ == "vit":
                lines.append(f"💊 {name} — время принять!")
            elif typ == "med":
                lines.append(f"💉 {name}")
        if lines:
            reminders.append({"time": t, "text": "\n".join(lines)})

    return reminders


def _schedule_jobs(job_queue, chat_id, reminders):
    for r in reminders:
        h, m = map(int, r["time"].split(":"))
        utc_total = (h * 60 + m - TZ_OFFSET * 60) % 1440
        utc_h, utc_m = utc_total // 60, utc_total % 60
        job_queue.run_daily(
            send_reminder,
            time=dtime(utc_h, utc_m, 0),
            data={"chat_id": chat_id, "text": r["text"], "local_time": r["time"]},
            name=f"rem_{chat_id}_{r['time']}"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[START] user={update.effective_user.id}", flush=True)
    kb = [[InlineKeyboardButton("📱 Открыть YHealth", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "👋 Привет! Это YHealth — твой дневник здоровья.\n\n"
        "Настрой профиль в приложении, затем напиши /remind чтобы включить уведомления.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    print(f"[REMIND] user_id={user_id}", flush=True)

    profile = db_get(user_id, "profile")
    print(f"[REMIND] profile={'found' if profile else 'NOT FOUND'}", flush=True)

    if not profile:
        await update.message.reply_text(
            "❌ Профиль не найден в базе.\n\n"
            "Открой приложение → Профиль → поменяй любой тогл и подожди 2 секунды. "
            "Затем снова напиши /remind"
        )
        return

    _user_chat_ids[user_id] = chat_id

    for job in context.job_queue.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()

    reminders = build_reminders(profile)
    print(f"[REMIND] built {len(reminders)} reminders: {[r['time'] for r in reminders]}", flush=True)

    _schedule_jobs(context.job_queue, chat_id, reminders)

    if reminders:
        lines = "\n".join(f"• {r['time']}" for r in reminders)
        tz_name = {3:"Москва",4:"Самара",5:"Екатеринбург",7:"Красноярск",
                   8:"Иркутск",10:"Владивосток"}.get(TZ_OFFSET, f"UTC+{TZ_OFFSET}")
        await update.message.reply_text(
            f"✅ Напоминания включены — {len(reminders)} уведомлений\n"
            f"🕐 Часовой пояс: {tz_name}\n\n"
            f"Расписание:\n{lines}\n\n"
            f"Чтобы отключить — /stop"
        )
    else:
        await update.message.reply_text("⚠️ В профиле нет активных приёмов пищи или витаминов.")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await context.bot.send_message(
        chat_id=job.data["chat_id"],
        text=job.data["text"],
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def stop_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for job in context.job_queue.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()
    await update.message.reply_text("🔕 Напоминания отключены. Чтобы включить — /remind")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show raw profile state stored in DB."""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    profile = db_get(user_id, "profile")

    if not profile:
        await update.message.reply_text("❌ Профиль не найден.")
        return

    sched      = profile.get("schedule", [])
    vitamins   = profile.get("vitamins", [])
    vit_hidden = profile.get("vitHidden", [])
    meds       = profile.get("meds", [])
    meds_hidden= profile.get("medsHidden", [])

    lines = ["📋 *Профиль в базе:*\n"]

    lines.append("*Питание:*")
    for m in sched:
        if isinstance(m, dict):
            flag = "✅" if m.get("enabled", True) else "❌"
            lines.append(f"  {flag} {m.get('name','')} — {m.get('time','?')}")

    lines.append(f"\n*Витамины* ({len(vitamins)} шт):")
    for vid in vitamins:
        flag = "🙈" if vid in vit_hidden else "💊"
        lines.append(f"  {flag} {VIT_NAMES.get(vid, vid)}")
    if not vitamins:
        lines.append("  (нет)")

    lines.append(f"\n*Лекарства* ({len(meds)} шт):")
    for i, med in enumerate(meds):
        if isinstance(med, dict):
            flag = "🙈" if i in meds_hidden else "💉"
            lines.append(f"  {flag} [{i}] {med.get('name','')} {med.get('dose','')} — {med.get('time','?')}")
    if not meds:
        lines.append("  (нет)")

    active = sorted(j.data["local_time"] for j in context.job_queue.jobs()
                    if j.data and j.data.get("chat_id") == chat_id)
    lines.append(f"\n*Активных напоминаний:* {len(active)}")
    if active:
        lines.append("  " + ", ".join(active))

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def auto_rebuild_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Silently rebuilds reminders when profile changes."""
    processed = set()
    while not profile_update_queue.empty():
        try:
            uid = profile_update_queue.get_nowait()
        except Exception:
            break
        if uid in processed:
            continue
        processed.add(uid)

        chat_id = _user_chat_ids.get(uid)
        if not chat_id:
            continue

        profile = db_get(uid, "profile")
        if not profile:
            continue

        for job in context.job_queue.jobs():
            if job.data and job.data.get("chat_id") == chat_id:
                job.schedule_removal()

        reminders = build_reminders(profile)
        _schedule_jobs(context.job_queue, chat_id, reminders)
        print(f"[AUTO-REMIND] uid={uid} rebuilt {len(reminders)} reminders: {[r['time'] for r in reminders]}", flush=True)


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text
    if text.startswith("/"): return
    if FEEDBACK_CHAT_ID:
        user = update.effective_user
        await context.bot.send_message(
            chat_id=FEEDBACK_CHAT_ID,
            text=f"💬 {user.first_name}:\n\n{text}"
        )
    await update.message.reply_text("Получено, спасибо!")


def main():
    if not TOKEN: raise ValueError("BOT_TOKEN missing")
    if not WEBAPP_URL: raise ValueError("WEBAPP_URL missing")
    start_server()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    app.add_handler(CommandHandler("stop",   stop_reminders))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback))
    app.job_queue.run_repeating(auto_rebuild_reminders, interval=60, first=10)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
