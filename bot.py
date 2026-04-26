import os, logging
from datetime import datetime, time as dtime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from server import start_server, db_get, profile_update_queue

try:
    from messages import MEAL_MESSAGES, VIT_FACTS
except ImportError:
    MEAL_MESSAGES = {}
    VIT_FACTS = {}

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
TOKEN        = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL   = os.environ.get("WEBAPP_URL", "")
FEEDBACK_ID  = os.environ.get("FEEDBACK_CHAT_ID", "")
TZ_OFFSET    = int(os.environ.get("TZ_OFFSET", "3"))

VIT_NAMES = {
    "omega":"Омега-3", "vitd":"Витамин D3+K2", "vitc":"Витамин C",
    "vitb12":"Витамин B12", "creatine":"Креатин", "magnesium":"Магний B6",
    "zinc":"Цинк", "calcium":"Кальций", "iron":"Железо", "probiotics":"Пробиотики",
}

MEAL_ICONS = {
    "water":"💧", "breakfast":"🍳", "snack1":"🥜",
    "lunch":"🥗", "snack2":"🍎", "dinner":"🐟",
}

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
        dose = med.get("dose", "")
        label = f"{name} — {dose}" if dose else name
        times = med.get("times") or ([med["time"]] if med.get("time") else [])
        for t in times:
            if not t: continue
            get_slot(t)["meds"].append(label)

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
                parts.append(f"{title}\n\n{tip}")
            else:
                ico = MEAL_ICONS.get(mid, "🍽")
                parts.append(f"{ico} {name}")

        # ── Vitamins block ──
        if slot["vits"]:
            has_meals = bool(slot["meals"])
            solo = not has_meals and len(slot["vits"]) == 1
            vit_lines = []
            for idx, vid in slot["vits"]:
                name = VIT_NAMES.get(vid, vid)
                if solo:
                    facts = VIT_FACTS.get(vid, [])
                    fact = _pick(facts, idx) if facts else ""
                    vit_lines.append(f"• {name}" + (f"\n  _{fact}_" if fact else ""))
                else:
                    vit_lines.append(f"• {name}")
            header = "💊 *Витамины:*" if len(slot["vits"]) > 1 else "💊 *Витамин:*"
            parts.append(header + "\n" + "\n".join(vit_lines))

        # ── Meds block ──
        if slot["meds"]:
            med_lines = "\n".join(f"• {m}" for m in slot["meds"])
            parts.append(f"💉 *Лекарства:*\n{med_lines}")

        if not parts:
            continue

        text = f"⏰ *{t}*\n\n" + "\n\n".join(parts)

        meal_ids = [m.get("id","") for m in slot["meals"] if m.get("id")]
        vit_ids  = [vid for _, vid in slot["vits"]]

        # Clean summary for /remind command (no tips, just items)
        summary_items = []
        for meal in slot["meals"]:
            ico = MEAL_ICONS.get(meal.get("id", ""), "🍽")
            summary_items.append(f"{ico} {meal.get('name', '')}")
        for _, vid in slot["vits"]:
            summary_items.append(f"💊 {VIT_NAMES.get(vid, vid)}")
        for m in slot["meds"]:
            summary_items.append(f"💉 {m}")
        summary = ", ".join(summary_items)

        reminders.append({"time": t, "text": text, "summary": summary,
                          "meal_ids": meal_ids, "vit_ids": vit_ids})

    return reminders


# ── Job scheduling ────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _schedule_jobs(jq, chat_id: int, uid: str, reminders: list[dict]):
    now_utc  = _now_utc()
    tz_delta = timedelta(hours=TZ_OFFSET)

    for r in reminders:
        lh, lm = map(int, r["time"].split(":"))
        utc_total = (lh * 60 + lm - TZ_OFFSET * 60) % 1440
        utc_h, utc_m = utc_total // 60, utc_total % 60

        job_data = {
            "chat_id":   chat_id,
            "uid":       uid,
            "text":      r["text"],
            "local_time": r["time"],
            "meal_ids":  r.get("meal_ids", []),
            "vit_ids":   r.get("vit_ids", []),
        }

        jq.run_daily(
            send_reminder,
            time=dtime(utc_h, utc_m, 0),
            data=job_data,
            name=f"rem_{chat_id}_{r['time']}",
        )

        target_utc_today = now_utc.replace(hour=utc_h, minute=utc_m, second=0, microsecond=0)
        local_now_mins   = (now_utc + tz_delta).hour * 60 + (now_utc + tz_delta).minute
        local_rem_mins   = lh * 60 + lm

        if target_utc_today <= now_utc and local_rem_mins > local_now_mins:
            jq.run_once(
                send_reminder,
                when=target_utc_today + timedelta(days=1),
                data=job_data,
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
    _schedule_jobs(context.job_queue, chat_id, uid, reminders)
    print(f"[REMIND] built {len(reminders)} reminders: {[r['time'] for r in reminders]}", flush=True)

    if not reminders:
        await update.message.reply_text("⚠️ Нет активных приёмов пищи, витаминов или лекарств.")
        return

    tz_name = {3:"Москва",4:"Самара",5:"Екатеринбург",7:"Красноярск",
               8:"Иркутск",10:"Владивосток"}.get(TZ_OFFSET, f"UTC+{TZ_OFFSET}")

    lines = []
    for r in reminders:
        lines.append(f"*{r['time']}* — {r['summary']}")

    msg = (
        f"✅ Напоминания включены — {len(reminders)} уведомлений\n"
        f"🕐 Часовой пояс: {tz_name}\n\n"
        + "\n".join(lines) +
        "\n\nЧтобы отключить — /stop"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    uid      = d.get("uid", "")
    meal_ids = d.get("meal_ids", [])
    vit_ids  = d.get("vit_ids", [])

    # Skip if all items in this slot are already marked done today
    if uid and (meal_ids or vit_ids):
        today = (datetime.utcnow() + timedelta(hours=TZ_OFFSET)).strftime("%Y-%m-%d")
        day_data = db_get(uid, "days") or {}
        day = day_data.get(today, {})
        meals_done = all(day.get("meals", {}).get(mid) for mid in meal_ids) if meal_ids else True
        # Check both old key format ("omega") and new format ("omega_0", "omega_1", ...)
        def _vit_done(vid):
            vits_dict = day.get("vitamins", {})
            if vits_dict.get(vid):
                return True
            return vits_dict.get(vid+"_0") or vits_dict.get(vid+"_1")
        vits_done = all(_vit_done(vid) for vid in vit_ids) if vit_ids else True
        if meals_done and vits_done and (meal_ids or vit_ids):
            print(f"[SKIP] uid={uid} time={d.get('local_time')} — all done", flush=True)
            return

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
        _schedule_jobs(context.job_queue, chat_id, uid, reminders)
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
