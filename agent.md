# Super ASK — Agent Rules

При любом изменении кода делай коммит на github.

Репозиторий: https://github.com/youcapybara228-svg/superask.git

## Архитектура

```
Telegram ←webhook→ Render (FastAPI) ←poll→ Agent (AI + tools) на ПК
```

- **Render** — релей: получает сообщение из Telegram, кладёт в очередь, забирает ответ, шлёт обратно
- **Agent** — AI-цикл: промпт → opencode/zen → tool calls → execute → результат → AI → ответ

## Файлы

- `render/app.py` — FastAPI сервер для Render (webhook + task queue)
- `render/requirements.txt` — зависимости для Render
- `render/render.yaml` — конфиг деплоя
- `agent/agent.py` — локальный агент (опрашивает Render, отправляет промпты в AI)
- `core/ai.py` — AI-клиент (opencode/zen API, цикл tool calling)
- `core/tools.py` — 13 opencode-инструментов (shell, read, write, edit, и т.д.)

### Деплой Render
1. Создать Web Service на render.com из репозитория
2. Build Command: `pip install -r render/requirements.txt`
3. Start Command: `uvicorn render.app:app --host 0.0.0.0 --port $PORT`
4. Добавить BOT_TOKEN и ADMIN_USER_ID в Environment Variables
5. После деплоя настроить webhook:
   ```
   curl -F "url=https://<app>.onrender.com/webhook" "https://api.telegram.org/bot<TOKEN>/setWebhook"
   ```

### Локальный агент
```bash
sa server https://<app>.onrender.com
sa apikey <ключ_с_opencode.ai/zen>
sa agent on
```
