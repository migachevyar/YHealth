# YHealth — Telegram Mini App

Промпт для воссоздания: создай Telegram Mini App для трекинга здоровья YHealth.

## Стек
- Python 3.11, python-telegram-bot==20.7, Railway хостинг
- WebApp: HTML/CSS/JS в одном файле, без фреймворков
- Данные: Telegram CloudStorage (основное) + SQLite на сервере (для бота)
- Иконки: Phosphor Icons v2.1.1, Шрифт: Inter

## Переменные Railway
BOT_TOKEN, WEBAPP_URL, FEEDBACK_CHAT_ID, TZ_OFFSET=3

## Критически важно: Telegram WebApp
В `<head>` index.html обязательно первым скриптом:
```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```
Без него `window.Telegram` = undefined и вся инициализация ломается.

API base URL — никогда не `window.location.origin` (внутри Telegram возвращает `blob:`).
В index.html используется константа `const API = window.location.origin;` которая корректно
работает только потому что server.py подставляет реальный URL при отдаче файла:
```python
content = content.replace(b"__WEBAPP_URL__", webapp_url.encode())
```
Поэтому в index.html должна быть строка `const API = '__WEBAPP_URL__';` — server.py её заменит.

## Telegram Desktop workaround
Desktop-клиент не передаёт `initData` и `initDataUnsafe.user`. Решение:
- При первом открытии на мобиле сохранять `uid` в CloudStorage под ключом `_uid`
- При загрузке приложения читать `_uid` из CS если `TG_USER.id === 0`
- `let _resolvedUid = TG_USER.id || 0;` — мутабельная переменная, дозаполняется в `init()`

## Дизайн
Тёмная тема (#09090f), стиль Apple Fitness. Акцент: зелёный #2fd158, синий #0a84ff,
оранжевый #ff9f0a, фиолетовый #bf5af2, красный #ff453a, teal #5ac8fa.
Полный экран через tg.requestFullscreen().

## Онбординг (4 шага)
1. Имя + Цель (Сбросить вес / Набрать мышцы / Поддержать форму)
2. Пол / Возраст / Вес / Рост
3. Время завтрака → автоматический расчёт расписания (ужин макс 19:30). Редактируемый preview.
4. Выбор витаминов (10 шт, рекомендованные по профилю)

При завершении онбординга сохраняется `joinDate: new Date().toISOString().slice(0,10)`.

## 4 вкладки

**Сегодня:** 3 кольца прогресса (питание/вода/витамины), карточка воды (5 бутылок 0.5л),
список приёмов пищи с галочками, витамины с галочками, лекарства

**Питание:** КБЖУ по Миффлину (коррекция по цели), примеры белка, варианты блюд по дням
(ротация), справочник витаминов

**Статистика:** серия дней, сетка 2×2, графики за 7 дней, история веса с SVG-графиком
и удалением

**Профиль:**
- Карточка пользователя с кнопкой карандаша → модалка редактирования (имя, цель, пол, возраст)
  без сброса остальных данных. Дата «С нами с» берётся из `profile.joinDate`.
- Расписание питания: time input + тогл + каскадный пересчёт при изменении завтрака.
  Кнопка «Добавить приём» → модалка с названием, выбором иконки (14 вариантов), временем.
  Кастомные приёмы удаляются корзиной; при сбросе расписания сохраняются.
- Витамины: тогл видимости + time input + добавить/скрыть
- Лекарства: несколько приёмов в день (`times: string[]`), добавление/удаление времён
  прямо в карточке. Бот обрабатывает как старый формат `{time}`, так и новый `{times:[]}`.
- Замечания, перенастройка профиля

## Хранение
CloudStorage: `profile`, `day_YYYY-MM-DD`, `weights` (массив [{date,value,ts}]), `_uid`
SQLite: таблица `user_data(uid, key, value)`, ключ `profile` для бота

### Структура profile
```js
{
  name, goal, sex, age, weight, height,
  breakfastTime,           // "HH:MM"
  joinDate,                // "YYYY-MM-DD", фиксируется при онбординге
  schedule: [              // порядок по времени
    { id, name, time, enabled, icon?, isCustom? }
  ],
  vitamins: ["omega", ...],  // список id активных витаминов
  vitHidden: ["zinc", ...],  // скрытые (уведомления отключены)
  vitTimes: { omega: "08:00", ... },  // переопределённые времена
  meds: [
    { name, dose, times: ["08:00", "20:00"] }  // times — массив
  ],
  medsHidden: [0, 2, ...]  // индексы скрытых лекарств
}
```
Миграция: при `loadAll()` старый формат `{time: "08:00"}` конвертируется в `{times: ["08:00"]}`.

## Бот (bot.py + server.py)

### server.py
- Отдаёт index.html с подстановкой `__WEBAPP_URL__`
- REST API: GET /api/data, POST /api/day, /api/weight, /api/profile, /api/feedback
- При каждом POST /api/profile кладёт uid в `profile_update_queue` (queue.Queue)
- Верификация через HMAC подпись initData; fallback — uid из payload

### bot.py
Команды: /start, /remind, /stop, /help

`/start` — регистрирует chat_id в `_user_chat_ids[uid]`, после чего авто-rebuild
работает без /remind (в приватных чатах chat_id == user_id, поэтому fallback работает сразу).

`/remind` — показывает всё включённое (еда + витамины + лекарства с временами) и
устанавливает/пересобирает напоминания.

`auto_rebuild_reminders` — job каждые 60 секунд, читает `profile_update_queue`,
пересобирает напоминания молча для всех изменившихся пользователей.

Формат уведомления:
```
⏰ 08:00
🍳 Завтрак
💊 Омега-3
💊 Витамин D3+K2
```

Логирование: `logging.getLogger("httpx").setLevel(logging.WARNING)` — убирает спам
HTTP Request из INFO логов.

### Планировщик напоминаний
```python
utc_total = (local_h * 60 + local_m - TZ_OFFSET * 60) % 1440
```
`run_daily` для постоянных напоминаний + два edge case через `run_once`:
1. UTC-полночь прошла, но локальное время ещё нет (бот на UTC сервере)
2. `/remind` отправлен в течение 5 минут после времени напоминания — отправить сразу

## Витамины (10 шт, время расчётное)
omega(завтрак), vitd(завтрак), magnesium(22:00), vitc(завтрак), zinc(обед),
creatine(завтрак), vitb12(завтрак), iron(за 30 мин до завтрака),
calcium(обед), probiotics(за 30 мин до завтрака)

Несовместимости: iron не с zinc/calcium, vitc не с vitb12 при высоких дозах

## Синхрон расписания
`saveProfile()` вызывается при любом изменении профиля. Функция:
1. Сохраняет в CloudStorage
2. POST /api/profile с uid и profile в body
3. Сервер пишет в SQLite и кладёт uid в очередь
4. Бот через ≤60 сек пересобирает напоминания
