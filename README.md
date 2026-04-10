# Дневник здоровья — Telegram Mini App

## Структура проекта

```
health-bot/
├── bot.py              — Telegram бот и напоминания
├── requirements.txt    — зависимости Python
├── webapp/
│   ├── index.html      — Mini App (всё приложение)
│   └── config.json     — ВСЕ настройки, тексты, данные
└── README.md           — эта инструкция
```

---

## Шаг 1 — Создать бота в Telegram

1. Открой Telegram, найди `@BotFather`
2. Напиши `/newbot`
3. Придумай имя: например `Мой дневник здоровья`
4. Придумай username (латиница, заканчивается на bot): например `my_health_diary_bot`
5. BotFather пришлёт токен вида `7123456789:AAFxxx...` — сохрани его

---

## Шаг 2 — Загрузить код на GitHub

1. Зайди на [github.com](https://github.com) и войди в аккаунт
2. Нажми `+` → `New repository`
3. Имя: `health-bot`, тип: **Private**, нажми `Create repository`
4. Загрузи файлы — перетащи всю папку `health-bot` в окно репозитория
   или используй команды в терминале:
   ```bash
   cd health-bot
   git init
   git add .
   git commit -m "initial"
   git remote add origin https://github.com/ВАШ_ЛОГИН/health-bot.git
   git push -u origin main
   ```

---

## Шаг 3 — Задеплоить на Railway

1. Зайди на [railway.app](https://railway.app) и войди через GitHub
2. Нажми `New Project` → `Deploy from GitHub repo`
3. Выбери репозиторий `health-bot`
4. Railway автоматически обнаружит Python проект

### Настроить переменные окружения (Variables):

В Railway открой проект → вкладка `Variables` → добавь:

| Переменная      | Значение                                      |
|----------------|-----------------------------------------------|
| `BOT_TOKEN`    | токен от BotFather (шаг 1)                    |
| `WEBAPP_URL`   | URL Mini App (смотри шаг 4)                   |
| `FEEDBACK_CHAT_ID` | твой Telegram chat_id (необязательно)    |

### Узнать свой chat_id (для получения замечаний):
Напиши боту `@userinfobot` в Telegram — он пришлёт твой ID.

---

## Шаг 4 — Опубликовать Mini App

Mini App — это обычная веб-страница (`webapp/index.html`).
Её нужно сделать доступной по HTTPS.

**Вариант А — через Railway Static (рекомендуется):**

1. В Railway создай второй сервис: `New Service` → `GitHub repo` → тот же репозиторий
2. В настройках сервиса укажи `Root Directory`: `webapp`
3. Добавь переменную `PORT=3000`
4. В `Settings` → `Networking` → `Generate Domain` — получишь URL вида `webapp-xxx.up.railway.app`
5. Этот URL вставь в переменную `WEBAPP_URL` первого сервиса

**Вариант Б — через Vercel (проще для статики):**

1. Зайди на [vercel.com](https://vercel.com), войди через GitHub
2. `New Project` → выбери `health-bot`
3. В `Root Directory` укажи `webapp`
4. Deploy — получишь URL вида `health-bot.vercel.app`
5. Этот URL вставь в `WEBAPP_URL` на Railway

---

## Шаг 5 — Подключить Mini App к боту

1. Напиши `@BotFather` команду `/mybots`
2. Выбери своего бота
3. `Bot Settings` → `Menu Button` → `Configure menu button`
4. Вставь URL твоего Mini App (из шага 4)
5. Текст кнопки: `Открыть трекер`

---

## Шаг 6 — Включить напоминания

Напиши своему боту команду `/remind` — он настроит все напоминания по расписанию из `config.json`.

Чтобы отключить: `/stop`

---

## Как обновлять приложение

### Изменить тексты, блюда, витамины, время напоминаний:
Открой `webapp/config.json` прямо на GitHub → нажми карандаш → внеси правки → `Commit changes`.
Railway подхватит изменения автоматически через 1–2 минуты.

### Добавить новое блюдо в обед:
```json
// в config.json, раздел "food" → "lunch" → "dishes"
{ "name": "Говядина + рис", "desc": "150 г варёной говядины + 150 г риса.", "products": "говядина, рис" }
```

### Добавить новый витамин:
```json
// в config.json, раздел "vitamins"
{
  "id": "b12",
  "name": "Витамин B12",
  "time": "Утро, с едой",
  "icon": "ph-pill",
  "color": "#ff9f0a",
  "bg": "rgba(255,159,10,0.15)",
  "dose": "500 мкг",
  "enabled": true,
  "desc": "Важен при нагрузках. Поддерживает нервную систему и энергетический обмен."
}
```

### Изменить время напоминания:
```json
// в config.json, раздел "reminders"
{ "time": "07:30", "text": "Доброе утро! Выпей стакан воды." }
```

### Добавить новую функцию в приложение:
Напиши мне в чат что хочешь добавить — я дам готовый код с инструкцией какой файл и что изменить.

---

## Команды бота

| Команда    | Действие                          |
|------------|-----------------------------------|
| `/start`   | Открыть трекер                    |
| `/remind`  | Включить все напоминания          |
| `/stop`    | Выключить напоминания             |

Любое текстовое сообщение боту будет переслано тебе как замечание (если настроен `FEEDBACK_CHAT_ID`).

---

## Иконки

Используется библиотека [Phosphor Icons](https://phosphoricons.com).
Чтобы найти нужную иконку — зайди на сайт, найди иконку, скопируй её название вида `ph-coffee`.
