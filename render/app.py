"""
Super ASK — Render server

Режимы:
  prod — Telegram bot (webhook) + task queue для агента
  proxy — HTTPS-прокси для Telegram API (бот на ПК)
"""
import os
import json
import uuid
import time
import asyncio
import logging

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes,
)
from telegram.error import InvalidToken, BadRequest

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("superask.render")

MODE = os.environ.get("SA_MODE", "proxy")  # prod | proxy

# ── Shared ──
CONFIG = {
    "bot_token": os.environ.get("BOT_TOKEN", ""),
    "admin_user_id": os.environ.get("ADMIN_USER_ID", ""),
}
try:
    CONFIG["admin_user_id"] = int(CONFIG["admin_user_id"]) if CONFIG["admin_user_id"] else None
except ValueError:
    CONFIG["admin_user_id"] = None

TASKS: dict[str, dict] = {}
application: Application = None
SELF_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
TG_API = "https://api.telegram.org"

app = FastAPI(title="Super ASK")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# ═══════════════════════════════════════════
#  MODE: proxy — просто прокси для Telegram API
# ═══════════════════════════════════════════

@app.api_route("/proxy/{path:path}", methods=["GET", "POST", "DELETE", "PATCH", "PUT"])
async def proxy_handler(path: str, request: Request):
    """Прокси для Telegram Bot API. Агент шлёт запросы сюда вместо api.telegram.org."""
    url = f"{TG_API}/{path}"
    body = await request.body()
    headers = {}
    for key in ("content-type", "accept"):
        val = request.headers.get(key)
        if val:
            headers[key] = val

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
        )

    return Response(content=resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mode": MODE,
        "bot_configured": bool(CONFIG["bot_token"]),
        "version": "2.0-proxy",
    }


# ═══════════════════════════════════════════
#  MODE: prod — Telegram bot + task queue
# ═══════════════════════════════════════════

if MODE == "prod":

    def _is_admin(user_id: int) -> bool:
        aid = CONFIG["admin_user_id"]
        if aid is None:
            return True
        return user_id == aid

    def _create_task(params: dict, update: Update) -> str:
        tid = uuid.uuid4().hex
        TASKS[tid] = {
            "id": tid,
            "params": params,
            "chat_id": update.effective_chat.id,
            "message_id": update.message.message_id,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "completed_at": None,
        }
        return tid

    async def webhook_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        log.info(f"/start от {user.id}")
        text = (
            "🤖 <b>Super ASK</b> — AI-агент для управления ПК.\n\n"
            "Основан на <b>opencode</b> (github.com/anomalyco/opencode)\n\n"
            "Напиши, что нужно сделать."
        )
        if not _is_admin(user.id):
            text += "\n\n⛔ Доступ только для владельца."
        await update.message.reply_text(text, parse_mode="HTML")

    async def webhook_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📋 Напиши что угодно — AI выполнит.\n\n"
            "Примеры:\n"
            "  покажи свободное место на диске\n"
            "  найди файл superask.py\n"
            "  проверь доступ к sudo\n"
            "  обнови пакеты\n"
            "  сколько процессов запущено"
        )

    async def webhook_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not _is_admin(user.id):
            log.warning(f"Доступ запрещён {user.id}")
            return
        text = update.message.text
        if not text or text.startswith("/"):
            return
        await update.message.reply_text("⏳ AI-агент обрабатывает запрос...")
        _create_task({"text": text}, update)
        log.info(f"Задача: {text[:80]}...")

    async def error_handler(update: Update | None, context: ContextTypes.DEFAULT_TYPE):
        log.error("Ошибка:", exc_info=context.error)
        if isinstance(context.error, InvalidToken):
            log.critical("Токен бота невалиден!")

    @app.on_event("startup")
    async def startup():
        global application
        token = CONFIG["bot_token"]
        if not token:
            log.critical("BOT_TOKEN не задан!")
            return
        log.info(f"Запуск bot-режима (токен: {token[:12]}...)")
        application = Application.builder().token(token).build()
        application.add_handler(CommandHandler("start", webhook_start))
        application.add_handler(CommandHandler("help", webhook_help))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, webhook_message))
        application.add_error_handler(error_handler)
        await application.initialize()
        webhook_url = f"{SELF_URL}/webhook"
        if webhook_url.startswith("http"):
            await application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
            log.info(f"Webhook: {webhook_url}")

    @app.on_event("shutdown")
    async def shutdown():
        if application:
            await application.shutdown()

    @app.post("/webhook")
    async def webhook(request: Request):
        if not application:
            return {"error": "Bot not initialized"}
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return {"ok": True}

    @app.get("/agent/task")
    async def agent_task():
        for tid, task in TASKS.items():
            if task["status"] == "pending":
                task["status"] = "running"
                return {
                    "id": tid,
                    "text": task["params"].get("text", ""),
                    "chat_id": task["chat_id"],
                }
        return {"id": None}

    @app.post("/agent/task/{task_id}/result")
    async def agent_result(task_id: str, request: Request):
        if task_id not in TASKS:
            raise HTTPException(404, "Task not found")
        body = await request.json()
        task = TASKS[task_id]
        task["status"] = "completed" if body.get("success") else "failed"
        task["result"] = body.get("result", "")
        task["error"] = body.get("error", "")
        task["completed_at"] = time.time()
        asyncio.create_task(_send_result(task))
        return {"ok": True}

    async def _send_result(task: dict):
        if not application:
            return
        chat_id = task["chat_id"]
        result = task.get("result") or task.get("error") or "(пусто)"
        try:
            await application.bot.send_message(chat_id=chat_id, text=result[:4000])
        except Exception as e:
            log.error(f"Ошибка отправки: {e}")
        TASKS.pop(task["id"], None)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("render.app:app", host="0.0.0.0", port=port, log_level="info")
