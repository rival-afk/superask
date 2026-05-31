#!/usr/bin/env python3
"""
Super ASK — Local Agent
Опрашивает Render-сервер, получает промпты от пользователя,
отправляет их в AI (opencode/zen) с контекстом, выполняет tool-вызовы,
показывает уведомления на ПК, возвращает результат.
"""
import sys
import os
import json
import time
import subprocess
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

# ── Conversation context ──
CONTEXTS: dict[int, list[dict]] = {}
MAX_CONTEXT = 20  # keep last N messages


def _notify(title: str, message: str):
    """Desktop notification via notify-send."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Super ASK", title, message[:200]],
            capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        pass  # notify-send not available
    except Exception:
        pass


def process_prompt(chat_id: int, text: str) -> dict:
    """Send to AI with context, return result."""
    log.info(f"Промпт: {text[:100]}...")

    api_key = local_config.get_api_key()
    if not api_key:
        return {"success": False, "error": "❌ API-ключ не задан. Используйте: sa apikey <ключ>"}

    context = CONTEXTS.get(chat_id, [])

    result = ai.process_prompt(text, context=context)

    tool_log = result.get("tool_log", "")
    response = result.get("response", "")
    rounds = result.get("rounds", 0)
    elapsed = result.get("elapsed", 0)

    # Store context
    CONTEXTS.setdefault(chat_id, [])
    CONTEXTS[chat_id].append({"role": "user", "content": text})
    CONTEXTS[chat_id].append({"role": "assistant", "content": response})
    CONTEXTS[chat_id] = CONTEXTS[chat_id][-MAX_CONTEXT * 2:]

    # Format response with tool log
    final = response
    if tool_log and rounds > 1:
        final = f"{response}\n\n📋 Выполнено ({rounds} шаг, {elapsed:.1f}с):\n<code>{tool_log[:2000]}</code>"
    elif rounds > 1:
        final = f"{response}\n\n⚡ {rounds} шагов за {elapsed:.1f}с"

    _notify("Super ASK", f"✅ Ответ получен ({elapsed:.1f}с)")

    return {"success": True, "result": final.strip()}


def main():
    if not SERVER_URL:
        log.critical("Установите SUPERASK_SERVER")
        log.critical("  export SUPERASK_SERVER=https://my-app.onrender.com")
        sys.exit(1)

    log.info(f"Подключение к {SERVER_URL}")
    log.info("Ожидание задач...")
    _notify("Super ASK", "Агент запущен и подключён к Render")

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
            chat_id = data.get("chat_id", 0)
            log.info(f"Задача {tid[:8]}: {text[:80]}...")

            _notify("Super ASK", f"⏳ Обработка: {text[:100]}...")

            result = process_prompt(chat_id, text)

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
