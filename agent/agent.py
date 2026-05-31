#!/usr/bin/env python3
"""
Super ASK — Local Agent
Опрашивает Render-сервер, получает промпты от пользователя,
отправляет их в AI-модель (opencode/zen), выполняет tool-вызовы,
возвращает результат.
"""
import sys
import os
import json
import time
import logging
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

VENV_PY = PROJECT_DIR / ".venv" / "bin" / "python3"
if VENV_PY.exists() and sys.executable != str(VENV_PY):
    os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

import requests
from core import config as local_config
from core import ai

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] AGENT: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("superask.agent")

SERVER_URL = os.environ.get("SUPERASK_SERVER", "").rstrip("/")
POLL_INTERVAL = 2


def process_prompt(text: str) -> dict:
    """Send prompt to AI, execute tools, return final result."""
    log.info(f"Промпт: {text[:100]}...")

    api_key = local_config.get_api_key()
    if not api_key:
        return {"success": False, "error": "API-ключ не задан. Используйте: sa apikey <ключ>"}

    try:
        result = ai.process_prompt(text)
        if not result or not result.strip():
            result = "(AI не вернул ответ)"
        return {"success": True, "result": result}
    except Exception as e:
        log.error(f"AI ошибка: {e}")
        return {"success": False, "error": f"❌ Ошибка AI: {e}"}


def main():
    if not SERVER_URL:
        log.critical("Установите SUPERASK_SERVER")
        log.critical("  export SUPERASK_SERVER=https://my-app.onrender.com")
        sys.exit(1)

    log.info(f"Подключение к {SERVER_URL}")
    log.info("Ожидание задач...")

    while True:
        try:
            resp = requests.get(f"{SERVER_URL}/agent/task", timeout=10)
            if resp.status_code != 200:
                log.warning(f"Ошибка сервера: {resp.status_code}")
                time.sleep(POLL_INTERVAL)
                continue

            data = resp.json()
            if not data or not data.get("id"):
                time.sleep(POLL_INTERVAL)
                continue

            tid = data["id"]
            text = data.get("text", "")
            log.info(f"Задача {tid[:8]}: {text[:80]}...")

            result = process_prompt(text)

            status = "✅" if result["success"] else "❌"
            preview = (result.get("result") or result.get("error") or "")[:200]
            log.info(f"Результат: {status} {preview}...")

            resp2 = requests.post(
                f"{SERVER_URL}/agent/task/{tid}/result",
                json=result,
                timeout=30,
            )
            if resp2.status_code == 200:
                log.info("Результат отправлен в Telegram")
            else:
                log.warning(f"Ошибка отправки: {resp2.status_code}")

        except requests.ConnectionError:
            log.warning(f"Нет соединения с {SERVER_URL}. Повтор через 10с...")
            time.sleep(10)
        except Exception as e:
            log.error(f"Ошибка: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
