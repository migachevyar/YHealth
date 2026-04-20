import os, logging, random
from datetime import datetime, time as dtime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get, profile_update_queue

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)   # hide HTTP Request spam
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
TOKEN        = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL   = os.environ.get("WEBAPP_URL", "")
FEEDBACK_ID  = os.environ.get("FEEDBACK_CHAT_ID", "")
TZ_OFFSET    = int(os.environ.get("TZ_OFFSET", "3"))   # hours ahead of UTC

VIT_NAMES = {
    "omega":"Омега-3", "vitd":"Витамин D3+K2", "vitc":"Витамин C",
    "vitb12":"Витамин B12", "creatine":"Креатин", "magnesium":"Магний B6",
    "zinc":"Цинк", "calcium":"Кальций", "iron":"Железо", "probiotics":"Пробиотики",
}

MEAL_ICONS = {
    "water":"💧", "breakfast":"🍳", "snack1":"🥜",
    "lunch":"🥗", "snack2":"🍎", "dinner":"🐟",
}

# ── Creative message pools ─────────────────────────────────────────────────────
MEAL_MESSAGES = {
    "water": [
        ("💧 Время пить воду!", "Факт: 60% тела — это вода. Ты буквально наполнен жизнью 🌊"),
        ("💧 Стакан воды = быстрый перезапуск", "Обезвоживание на 2% снижает концентрацию на 20%. Один глоток — и мозг скажет спасибо 🧠"),
        ("💧 Пора сделать глоток!", "Кожа, мышцы, суставы — всё работает лучше, когда ты пьёшь воду. Твоё тело уже ждёт 😊"),
        ("💧 Hydration check!", "Кофе не считается. Вода считается. Давай, один стакан — и ты красавчик 💪"),
        ("💧 Вода — лучший энергетик", "Усталость часто = жажда. Попробуй выпить воды прямо сейчас, и посмотри как изменится самочувствие ✨"),
    ],
    "breakfast": [
        ("🌅 Доброе утро!", "Завтрак запускает метаболизм и повышает концентрацию на весь день. Позволь себе поесть по-человечески 🍳\n\n✨ Приятного аппетита!"),
        ("☀️ Время завтракать!", "Люди, которые завтракают регулярно, в среднем стройнее и энергичнее. Ты уже делаешь всё правильно 🙌\n\n✨ Наслаждайся каждым кусочком!"),
        ("🌄 Утро начинается с еды!", "Без завтрака мозг буквально экономит энергию — это и есть та \"утренняя туманность\". Заправься и начни день на полную 🚀\n\n✨ Bon appétit!"),
        ("🍳 Завтрак подан!", "Совет: добавь белок с утра (яйца, творог, греческий йогурт) — он даст насыщение на 3–4 часа и уберёт тягу к сладкому 💡\n\n✨ Приятного аппетита!"),
        ("🌻 Заряди себя с утра!", "Завтрак — это инвестиция в продуктивность. Причём с гарантированным возвратом 📈\n\n✨ Ешь с удовольствием!"),
    ],
    "snack1": [
        ("🥜 Перекус #1 — не пропускай!", "Небольшой перекус между завтраком и обедом стабилизирует сахар в крови и не даёт переесть в обед 🎯"),
        ("🍏 Время лёгкого перекуса!", "Орехи, фрукт, творог — 15 минут еды сейчас сэкономят тебе 2 часа голодного раздражения потом 😄"),
        ("🥜 Перекус — это не слабость!", "Это стратегия. Спортсмены едят 4–6 раз в день. Ты тоже спортсмен — просто ещё не все об этом знают 💪"),
        ("🍇 Мини-дозаправка!", "Совет: перекус с клетчаткой + белком (яблоко + орехи, морковь + хумус) держит сытость вдвое дольше 🌱"),
        ("🌰 Время для перекуса!", "Факт: люди, которые делают запланированные перекусы, потребляют меньше калорий за день в целом. Парадокс? Нет, физиология 🔬"),
    ],
    "lunch": [
        ("🥗 Обед — дело серьёзное!", "Совет: сначала съешь овощи/салат, потом белок, потом углеводы. Сахар поднимется плавно, энергия будет ровной 📊\n\n✨ Приятного аппетита!"),
        ("🍽 Время обеда!", "Люди, которые едят обед медленно (20+ минут), потребляют на 15% меньше калорий. Жуй, наслаждайся, не торопись 🧘\n\n✨ Bon appétit!"),
        ("🥗 Обед — заряд на вторую половину дня!", "Хороший обед = углеводы (энергия) + белок (восстановление) + жиры (гормоны). Твой организм — высокоточная машина 🏎\n\n✨ Приятного аппетита!"),
        ("🌿 Пора пообедать!", "Совет дня: не ешь за рабочим столом. Даже 10-минутный перерыв снижает стресс и улучшает пищеварение 🌿\n\n✨ Ешь с удовольствием!"),
        ("🥘 Обеденный перерыв!", "Факт: пропуск обеда повышает кортизол (гормон стресса) и снижает силу воли ближе к вечеру. Поешь — и ты будешь сильнее 💡\n\n✨ Приятного аппетита!"),
    ],
    "snack2": [
        ("🍎 Перекус #2 — держим темп!", "До ужина ещё далеко. Небольшой перекус сейчас — и ты придёшь за стол без зверского голода 🎯"),
        ("🫐 Время для второго перекуса!", "Ягоды, фрукты, йогурт — лёгкий перекус сейчас не даст переесть вечером. Это работает, проверено 📌"),
        ("🍊 Полдник!", "Совет: фрукты лучше есть отдельно от основного приёма пищи или хотя бы через час после. Так и усваивается лучше, и живот доволен 🙂"),
        ("🥛 Время перекусить!", "Греческий йогурт, творог, горсть орехов — быстро, вкусно, и держит тебя до ужина без срывов 💪"),
        ("🍏 Мини-заправка перед вечером!", "Факт: вечерние срывы почти всегда из-за пропущенного дневного перекуса. Ешь сейчас — побеждай вечером 🏆"),
    ],
    "dinner": [
        ("🌙 Ужин — финальный аккорд дня!", "Совет: лёгкий ужин за 2–3 часа до сна улучшает качество сна и восстановление. Твоё тело скажет спасибо утром 🌟\n\n✨ Приятного аппетита!"),
        ("🐟 Время ужинать!", "Белок на ужин (рыба, курица, творог) питает мышцы всю ночь. Тело восстанавливается, пока ты спишь 💪\n\n✨ Bon appétit!"),
        ("🌆 Вечерний ритуал — ужин!", "Ешь без гаджетов хотя бы иногда. Осознанный приём пищи снижает переедание и улучшает отношение с едой 🧘\n\n✨ Приятного аппетита!"),
        ("🫚 Ужин подан!", "Совет: добавь овощи к ужину. Клетчатка накормит полезные бактерии кишечника, и они отблагодарят тебя хорошим настроением завтра 🌱\n\n✨ Ешь медленно и с удовольствием!"),
        ("🌙 Финальный приём пищи!", "Не бойся жиров на ужин (авокадо, орехи, оливковое масло) — они нужны для синтеза гормонов и восстановления клеток 🔬\n\n✨ Приятного аппетита!"),
    ],
}

VIT_FACTS = {
    "omega":     "🐟 Омега-3 снижает воспаление, улучшает память и поддерживает сердце",
    "vitd":      "☀️ Витамин D3 — гормон солнца. Влияет на иммунитет, настроение и кости",
    "vitc":      "🍊 Витамин C усиливает иммунитет и помогает усваивать железо",
    "vitb12":    "⚡ B12 — топливо для нервной системы и производства энергии",
    "creatine":  "💪 Креатин увеличивает силу и ускоряет восстановление после тренировок",
    "magnesium": "😴 Магний расслабляет мышцы, снижает стресс и улучшает сон",
    "zinc":      "🛡 Цинк — щит иммунитета и помощник в заживлении",
    "calcium":   "🦴 Кальций строит кости и поддерживает работу сердца",
    "iron":      "🩸 Железо переносит кислород. Без него — усталость и туман в голове",
    "probiotics":"🦠 Пробиотики кормят полезные бактерии. Кишечник = второй мозг",
}

MED_MESSAGES = [
    "Не забудь про лекарства — это важная часть твоего ритуала заботы о себе 💙",
    "Постоянство в приёме лекарств — это суперсила. Так держать 🌟",
    "Небольшое напоминание, большая польза для здоровья 💊",
    "Твоё тело знает, когда ты о нём заботишься. Вот прямо сейчас — хороший момент 🤍",
]

# uid (str) → chat_id (int) — populated on /start so auto-rebuild needs no /remind
_chat: dict[str, int] = {}


# ── Build reminders ───────────────────────────────────────────────────────────
def _pick(pool: list, seed: int) -> any:
    """Deterministically pick from pool by day-of-year so it varies daily."""
    day = datetime.now().timetuple().tm_yday
    return pool[(day + seed) % len(pool)]


def build_reminders(profile: dict) -> list[dict]:
    """Return [{time:'HH:MM', text:str}] sorted by time."""
    if not profile:
        return []

    sched_list  = profile.get("schedule", [])
    vit_list    = profile.get("vitamins", [])
    vit_hidden  = profile.get("vitHidden", [])
    vit_times   = profile.get("vitTimes", {})
    meds_list   = profile.get("meds", [])
    meds_hidden = profile.get("medsHidden", [])

    print(
        f"[BUILD] meals={[(m.get('id'), m.get('time'), m.get('enabled')) for m in sched_list if isinstance(m, dict)]}"
        f" | vits={vit_list} | vitHidden={vit_hidden}"
        f" | meds={len(meds_list)} | medsHidden={meds_hidden}",
        flush=True,
    )

    def t2m(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def m2t(mins: int) -> str:
        h, m = divmod(int(mins) % 1440, 60)
        return f"{h:02d}:{m:02d}"

    bf = next((m.get("time") for m in sched_list
               if isinstance(m, dict) and m.get("id") == "breakfast"), None) \
         or profile.get("breakfastTime", "08:00")
    ln = next((m.get("time") for m in sched_list
               if isinstance(m, dict) and m.get("id") == "lunch"), None) or "13:00"

    VIT_DEFAULTS = {
        "omega": bf, "vitd": bf, "vitc": bf, "vitb12": bf, "creatine": bf,
        "magnesium": "22:00",
        "zinc": ln, "calcium": ln,
        "iron": m2t(t2m(bf) - 30), "probiotics": m2t(t2m(bf) - 30),
    }

    # slot_data[time] = {meals:[], vits:[], meds:[]}
    slots: dict[str, dict] = {}

    def get_slot(t: str) -> dict:
        if t not in slots:
            slots[t] = {"meals": [], "vits": [], "meds": []}
        return slots[t]

    # Meals
    for meal in sched_list:
        if not isinstance(meal, dict): continue
        if not meal.get("enabled", True): continue
        t = meal.get("time", "")
        if not t: continue
        get_slot(t)["meals"].append(meal)

    # Active vitamins (excluding hidden)
    active_vits = [v for v in vit_list if v not in vit_hidden]
    for idx, vid in enumerate(active_vits):
        t = vit_times.get(vid) or VIT_DEFAULTS.get(vid, bf)
        get_slot(t)["vits"].append((idx, vid))

    # Meds
    for i, med in enumerate(meds_list):
        if not isinstance(med, dict): continue
        if i in meds_hidden: continue
        name = med.get("name", "")
        times = med.get("times") or ([med["time"]] if med.get("time") else [])
        for t in times:
            if not t: continue
            get_slot(t)["meds"].append(name)

    reminders = []
    for t, slot in sorted(slots.items()):
        parts = []

        # ── Meals block ──
        for meal in slot["meals"]:
            mid  = meal.get("id", "")
            name = meal.get("name", "")
            pool = MEAL_MESSAGES.get(mid)
            if pool:
                seed = list(MEAL_MESSAGES.keys()).index(mid) if mid in MEAL_MESSAGES else 0
                title, tip = _pick(pool, seed)
                parts.append(f"{title}\n{name}\n\n{tip}")
            else:
                ico = MEAL_ICONS.get(mid, "🍽")
                parts.append(f"{ico} {name}")

        # ── Vitamins block ──
        if slot["vits"]:
            vit_lines = []
            for idx, vid in slot["vits"]:
                name = VIT_NAMES.get(vid, vid)
                fact = VIT_FACTS.get(vid, "")
                vit_lines.append(f"• {name}" + (f"\n  _{fact}_" if fact else ""))
            header = "💊 *Витамины:*" if len(slot["vits"]) > 1 else "💊 *Витамин:*"
            parts.append(header + "\n" + "\n".join(vit_lines))

        # ── Meds block ──
        if slot["meds"]:
            med_tip = _pick(MED_MESSAGES, len(slot["meds"]))
            med_lines = "\n".join(f"• {m}" for m in slot["meds"])
            parts.append(f"💉 *Лекарства:*\n{med_lines}\n\n{med_tip}")

        if not parts:
            continue

        text = f"⏰ *{t}*\n\n" + "\n\n".join(parts)
        reminders.append({"time": t, "text": text})

    return reminders


# ── Job scheduling ────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _schedule_jobs(jq, chat_id: int, reminders: list[dict]):
    """Register run_daily jobs. Also run_once for reminders that are still
    upcoming today in local time but whose UTC time has already passed
    (happens when the bot restarts after midnight UTC but before local midnight)."""
    now_utc  = _now_utc()
    tz_delta = timedelta(hours=TZ_OFFSET)

    for r in reminders:
        lh, lm = map(int, r["time"].split(":"))
        utc_total = (lh * 60 + lm - TZ_OFFSET * 60) % 1440
        utc_h, utc_m = utc_total // 60, utc_total % 60

        # Daily job (fires every day going forward)
        jq.run_daily(
            send_reminder,
            time=dtime(utc_h, utc_m, 0),
            data={"chat_id": chat_id, "text": r["text"], "local_time": r["time"]},
            name=f"rem_{chat_id}_{r['time']}",
        )

        # Handle two edge cases with run_once:
        target_utc_today = now_utc.replace(hour=utc_h, minute=utc_m, second=0, microsecond=0)
        local_now_mins   = (now_utc + tz_delta).hour * 60 + (now_utc + tz_delta).minute
        local_rem_mins   = lh * 60 + lm

        if target_utc_today <= now_utc and local_rem_mins > local_now_mins:
            # Case 1: UTC crossed midnight but local time hasn't — fire today
            jq.run_once(
                send_reminder,
                when=target_utc_today + timedelta(days=1),
                data={"chat_id": chat_id, "text": r["text"], "local_time": r["time"]},
            )


def _remove_user_jobs(jq, chat_id: int):
    for job in jq.jobs():
        if job.data and job.data.get("chat_id") == chat_id:
            job.schedule_removal()


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    _chat[uid] = chat_id   # register so auto-rebuild works without /remind
    print(f"[START] uid={uid} chat_id={chat_id}", flush=True)
    kb = [[InlineKeyboardButton("📱 Открыть YHealth", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "👋 Привет! Это YHealth — твой дневник здоровья.\n\n"
        "Настрой профиль в приложении, напоминания включатся автоматически.\n"
        "Или напиши /remind чтобы включить сейчас.",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def setup_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    _chat[uid] = chat_id
    print(f"[REMIND] uid={uid}", flush=True)

    profile = db_get(uid, "profile")
    if not profile:
        await update.message.reply_text(
            "❌ Профиль не найден.\n\n"
            "Открой приложение → Профиль → измени любой параметр → сохранится автоматически.\n"
            "Затем снова напиши /remind"
        )
        return

    _remove_user_jobs(context.job_queue, chat_id)
    reminders = build_reminders(profile)
    _schedule_jobs(context.job_queue, chat_id, reminders)
    print(f"[REMIND] built {len(reminders)} reminders: {[r['time'] for r in reminders]}", flush=True)

    if not reminders:
        await update.message.reply_text("⚠️ Нет активных приёмов пищи, витаминов или лекарств.")
        return

    tz_name = {3:"Москва",4:"Самара",5:"Екатеринбург",7:"Красноярск",
               8:"Иркутск",10:"Владивосток"}.get(TZ_OFFSET, f"UTC+{TZ_OFFSET}")

    lines = []
    for r in reminders:
        # r["text"] is "⏰ HH:MM\n<items>" — extract items line
        items_text = r["text"].split("\n", 1)[1] if "\n" in r["text"] else ""
        lines.append(f"*{r['time']}* — {items_text.replace(chr(10), ', ')}")

    msg = (
        f"✅ Напоминания включены — {len(reminders)} уведомлений\n"
        f"🕐 Часовой пояс: {tz_name}\n\n"
        + "\n".join(lines) +
        "\n\nЧтобы отключить — /stop"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    d  = context.job.data
    kb = [[InlineKeyboardButton("Открыть трекер", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await context.bot.send_message(
        chat_id=d["chat_id"],
        text=d["text"],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def stop_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _remove_user_jobs(context.job_queue, chat_id)
    await update.message.reply_text("🔕 Напоминания отключены. Чтобы включить — /remind")


async def auto_rebuild_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Silently rebuilds reminders on every profile save (drains queue every 60s)."""
    processed: set[str] = set()
    while not profile_update_queue.empty():
        try:
            uid = profile_update_queue.get_nowait()
        except Exception:
            break
        if uid in processed:
            continue
        processed.add(uid)

        # Use stored chat_id; fallback: in private chats chat_id == user_id
        chat_id = _chat.get(uid) or int(uid)

        profile = db_get(uid, "profile")
        if not profile:
            continue

        _remove_user_jobs(context.job_queue, chat_id)
        reminders = build_reminders(profile)
        _schedule_jobs(context.job_queue, chat_id, reminders)
        print(
            f"[AUTO] uid={uid} rebuilt {len(reminders)} reminders: {[r['time'] for r in reminders]}",
            flush=True,
        )


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text
    if text.startswith("/"): return
    if FEEDBACK_ID:
        user = update.effective_user
        await context.bot.send_message(chat_id=FEEDBACK_ID, text=f"💬 {user.first_name}:\n\n{text}")
    await update.message.reply_text("Получено, спасибо!")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:    raise ValueError("BOT_TOKEN missing")
    if not WEBAPP_URL: raise ValueError("WEBAPP_URL missing")
    start_server()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("remind", setup_reminders))
    app.add_handler(CommandHandler("stop",   stop_reminders))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback))
    # Auto-rebuild reminders when profile changes (drains queue every 60s)
    app.job_queue.run_repeating(auto_rebuild_reminders, interval=60, first=10)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
