# Super ASK — Agent Rules

При любом изменении кода делай коммит на github.

Репозиторий: https://github.com/youcapybara228-svg/superask.git

## Render хостинг

- `render/app.py` — FastAPI сервер для Render (webhook + task queue)
- `render/requirements.txt` — зависимости для Render
- `render/render.yaml` — конфиг деплоя
- `agent/agent.py` — локальный агент (опрашивает Render, выполняет команды)

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
export SUPERASK_SERVER=https://<app>.onrender.com
python agent/agent.py
```
