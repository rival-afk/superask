# Деплой Super ASK на Render

## Что тебе понадобится

1. **Аккаунт на Render.com** — зарегистрируйся на https://render.com (через GitHub)
2. **Токен Telegram-бота** — получи у @BotFather
3. **Свой Telegram ID** — напиши @userinfobot

---

## Шаг 1. Пушим код на GitHub

Код уже должен быть на GitHub. Если нет:

```bash
cd /opt/superask
git add -A
git commit -m "initial"
git push origin main
```

---

## Шаг 2. Создаём Web Service на Render

1. Зайди на https://dashboard.render.com
2. Нажми **New +** → **Web Service**
3. Выбери свой репозиторий `youcapybara228-svg/superask`
4. Заполни поля:

| Поле | Значение |
|------|----------|
| **Name** | `superask` (или любое) |
| **Region** | `Frankfurt (EU)` — важно для России |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r render/requirements.txt` |
| **Start Command** | `uvicorn render.app:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free |

5. Нажми **Advanced** → **Add Environment Variable**
   - `BOT_TOKEN` = твой токен от BotFather
   - `ADMIN_USER_ID` = твой Telegram ID (число)

6. Нажми **Create Web Service**

Жди 2-5 минут, пока Render соберёт и запустит приложение.

---

## Шаг 3. Настраиваем Webhook (самое важное)

Когда сервер запустится, Render покажет URL твоего приложения:
`https://superask.onrender.com`

Открой **Terminal на ПК** и выполни:

```bash
curl -F "url=https://superask.onrender.com/webhook" \
     "https://api.telegram.org/bot<ТВОЙ_ТОКЕН_БОТА>/setWebhook"
```

Замени `<ТВОЙ_ТОКЕН_БОТА>` на реальный токен.

Должен прийти ответ:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

---

## Шаг 4. Проверяем бота

Напиши в Telegram своему боту команду `/start`.

Если бот ответил — **Render работает**, можно подключать ПК.

---

## Шаг 5. Получаем API-ключ opencode/zen

Зайди на https://opencode.ai/zen и получи API-ключ.
Он нужен агенту для вызова AI-модели.

---

## Шаг 6. Запускаем локального агента на ПК

На том же ПК, где стоит Super ASK:

```bash
# Указываем адрес твоего Render-сервера
sa server https://superask.onrender.com

# Сохраняем API-ключ
sa apikey <ключ_с_opencode.ai/zen>

# Запускаем агента как системный сервис
sa agent on
```

Проверяем:

```bash
sa status
# Должно быть: Агент: ✅ активен, API-ключ: ✅
```

---

## Шаг 7. Пользуемся

Просто напиши боту на русском, что нужно сделать. AI сам решит, какие команды выполнить:

```
покажи свободное место на диске
найди файл config.py
обнови все пакеты
сколько процессов запущено
```

---

## Если что-то пошло не так

### Бот не отвечает
Проверь статус:
```bash
sa status
sa logs         # логи бота
sa agent logs   # логи агента
```

### Webhook не установился
Проверь, что Render-сервер отвечает:
```bash
curl https://superask.onrender.com/health
```

### Permission denied при sa
```bash
sudo chmod +x /opt/superask/cli.py
```

### Ошибка "Agent: ❌ не активен"
```bash
sudo journalctl -u superask-agent -n 30 --no-pager
```

---

## Полезное

- Render бесплатный, но сервер "засыпает" после 15 минут бездействия.
  При первом запросе просыпается за 30-60 секунд.
- Чтобы не ждать — установи **UptimeRobot** (https://uptimerobot.com) пинговать `/health` каждые 5 минут.
- Если бот внезапно перестал отвечать — проверь логи агента: `sa agent logs`
