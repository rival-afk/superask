#!/usr/bin/env python3
"""
Super ASK — Local Agent

Режимы:
  1. proxy (по умолчанию) — запускает Telegram-бота локально,
     используя Render как HTTPS-прокси для Telegram API.
  2. relay (SA_MODE=relay) — опрашивает Render через task queue.
"""
import sys
import os
import json
import time
import asyncio
import subprocess
import logging
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

VENV_PY = PROJECT_DIR / ".venv" / "bin" / "python3"
if VENV_PY.exists() and sys.executable != str(VENV_PY):
    os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

MODE = os.environ.get("SA_AGENT_MODE", "proxy")
SERVER_URL = os.environ.get("SUPERASK_SERVER", "").rstrip("/")
POLL_INTERVAL = 2

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] AGENT: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("superask.agent")


def _notify(title: str, message: str):
    try:
        subprocess.run(
            ["notify-send", "-a", "Super ASK", title, message[:200]],
            capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ═══════════════════════════════════════════
#  MODE: proxy — локальный бот через Render-прокси
# ═══════════════════════════════════════════

def run_proxy_mode():
    """Запускает Telegram-бота локально, используя Render как прокси."""
    from telegram import Update
    from telegram.ext import (
        Application, CommandHandler, MessageHandler, filters,
        ContextTypes,
    )
    from telegram.error import InvalidToken, TimedOut, NetworkError, RetryAfter
    from core import config as local_config
    from core import ai

    CONTEXTS: dict[int, list[dict]] = {}
    MAX_CONTEXT = 20

    token = local_config.get_bot_token()
    if not token:
        log.critical("Токен бота не задан! sa bot <token>")
        sys.exit(1)

    api_key = local_config.get_api_key()
    if not api_key:
        log.critical("API-ключ не задан! sa apikey <ключ>")
        sys.exit(1)

    base_url = f"{SERVER_URL}/proxy/bot" if SERVER_URL else None
    log.info(f"Запуск локального бота через {base_url or 'прямое соединение'}")

    builder = Application.builder().token(token)
    if base_url:
        builder = builder.base_url(base_url)
    app = builder.build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Super ASK</b> — AI-агент для ПК.\n\n"
            "Основан на <b>opencode</b> (github.com/anomalyco/opencode)\n"
            "Напиши, что нужно сделать.",
            parse_mode="HTML",
        )

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if not text or text.startswith("/"):
            return

        chat_id = update.effective_chat.id
        log.info(f"Промпт: {text[:100]}...")
        _notify("Super ASK", f"⏳ {text[:100]}...")

        ctx = CONTEXTS.get(chat_id, [])
        result = ai.process_prompt(text, context=ctx)

        response = result.get("response", "")
        tool_log = result.get("tool_log", "")
        rounds = result.get("rounds", 0)
        elapsed = result.get("elapsed", 0)

        CONTEXTS.setdefault(chat_id, [])
        CONTEXTS[chat_id].append({"role": "user", "content": text})
        CONTEXTS[chat_id].append({"role": "assistant", "content": response})
        CONTEXTS[chat_id] = CONTEXTS[chat_id][-MAX_CONTEXT * 2:]

        final = response
        if tool_log and rounds > 1:
            final = f"{response}\n\n📋 Выполнено ({rounds} шаг, {elapsed:.1f}с):\n<code>{tool_log[:2000]}</code>"
        elif rounds > 1:
            final = f"{response}\n\n⚡ {rounds} шагов за {elapsed:.1f}с"

        try:
            await update.message.reply_text(final.strip()[:4000])
        except Exception as e:
            log.error(f"Ошибка отправки: {e}")

        _notify("Super ASK", f"✅ Ответ получен ({elapsed:.1f}с)")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Бот запущен, ожидание команд...")
    _notify("Super ASK", "Бот запущен")

    RETRY_DELAY = 10
    while True:
        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False,
            )
        except InvalidToken:
            log.critical("Токен невалиден!")
            sys.exit(1)
        except (NetworkError, TimedOut) as e:
            log.warning(f"Сетевая ошибка: {e}. Повтор через {RETRY_DELAY}с...")
            time.sleep(RETRY_DELAY)
        except RetryAfter as e:
            log.warning(f"Flood control. Ждём {e.retry_after}с...")
            time.sleep(e.retry_after)
        except Exception as e:
            log.error(f"Ошибка бота: {e}. Повтор через {RETRY_DELAY}с...")
            time.sleep(RETRY_DELAY)


# ═══════════════════════════════════════════
#  MODE: relay — опрос Render через task queue
# ═══════════════════════════════════════════

def run_relay_mode():
    """Опрашивает Render, получает задачи, выполняет, возвращает результат."""
    import requests
    from core import config as local_config
    from core import ai

    CONTEXTS: dict[int, list[dict]] = {}
    MAX_CONTEXT = 20

    if not SERVER_URL:
        log.critical("Установите SUPERASK_SERVER")
        sys.exit(1)

    log.info(f"Relay-режим: {SERVER_URL}")
    _notify("Super ASK", "Агент запущен (relay)")

    while True:
        try:
            resp = requests.get(f"{SERVER_URL}/agent/task", timeout=10)
            if resp.status_code != 200:
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
            _notify("Super ASK", f"⏳ {text[:100]}...")

            ctx = CONTEXTS.get(chat_id, [])
            result = ai.process_prompt(text, context=ctx)
            response = result.get("response", "")
            tool_log = result.get("tool_log", "")
            rounds = result.get("rounds", 0)
            elapsed = result.get("elapsed", 0)

            CONTEXTS.setdefault(chat_id, [])
            CONTEXTS[chat_id].append({"role": "user", "content": text})
            CONTEXTS[chat_id].append({"role": "assistant", "content": response})
            CONTEXTS[chat_id] = CONTEXTS[chat_id][-MAX_CONTEXT * 2:]

            final = response
            if tool_log and rounds > 1:
                final = f"{response}\n\n📋 Выполнено ({rounds} шаг, {elapsed:.1f}с):\n<code>{tool_log[:2000]}</code>"
            elif rounds > 1:
                final = f"{response}\n\n⚡ {rounds} шагов за {elapsed:.1f}с"

            status = "✅" if True else "❌"
            preview = final[:200]
            log.info(f"Результат: {status} {preview}...")

            requests.post(
                f"{SERVER_URL}/agent/task/{tid}/result",
                json={"success": True, "result": final.strip()},
                timeout=30,
            )

            _notify("Super ASK", f"✅ Ответ получен ({elapsed:.1f}с)")

        except requests.ConnectionError:
            log.warning(f"Нет соединения. Повтор через 10с...")
            time.sleep(10)
        except Exception as e:
            log.error(f"Ошибка: {e}")
            time.sleep(POLL_INTERVAL)


# ═══════════════════════════════════════════
#  Entry
# ═══════════════════════════════════════════

def main():
    mode = os.environ.get("SA_AGENT_MODE", "proxy")
    if mode == "relay":
        run_relay_mode()
    else:
        run_proxy_mode()


if __name__ == "__main__":
    main()
