"""
Super ASK — Render server
Telegram bot (webhook mode) + task queue for local agent

Деплой:
  1. На Render создать Web Service, указать BOT_TOKEN и ADMIN_USER_ID
  2. После деплоя настроить webhook:
     curl -F "url=https://<app>.onrender.com/webhook" \
          "https://api.telegram.org/bot<TOKEN>/setWebhook"

Локальный агент на ПК:
  export SUPERASK_SERVER=https://<app>.onrender.com
  python agent/agent.py
"""
import os
import sys
import json
import uuid
import time
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
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

# ── In-memory config (from env) ──
CONFIG = {
    "bot_token": os.environ.get("BOT_TOKEN", ""),
    "admin_user_id": os.environ.get("ADMIN_USER_ID", ""),
}
try:
    CONFIG["admin_user_id"] = int(CONFIG["admin_user_id"]) if CONFIG["admin_user_id"] else None
except ValueError:
    CONFIG["admin_user_id"] = None

# ── Task queue ──
TASKS: dict[str, dict] = {}

application: Application = None

# ── Admin check ──
def _is_admin(user_id: int) -> bool:
    aid = CONFIG["admin_user_id"]
    if aid is None:
        return True
    return user_id == aid

def _deny(uid: int):
    log.warning(f"Доступ запрещён для user_id={uid}")

# ── Task helpers ──
def _create_task(task_type: str, params: dict, update: Update) -> str:
    tid = uuid.uuid4().hex
    task = {
        "id": tid,
        "type": task_type,
        "params": params,
        "chat_id": update.effective_chat.id,
        "message_id": update.message.message_id,
        "status": "pending",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "completed_at": None,
    }
    TASKS[tid] = task
    return tid

def _cleanup(max_age: int = 300):
    now = time.time()
    for tid in list(TASKS.keys()):
        if TASKS[tid].get("completed_at", 0) and TASKS[tid]["completed_at"] < now - max_age:
            del TASKS[tid]

# ── Bot Handlers ──

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user is None:
            return
        if not _is_admin(update.effective_user.id):
            _deny(update.effective_user.id)
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        return await func(update, context)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/start от user_id={user.id}")

    text = (
        "🤖 <b>Super ASK</b> — удалённое управление ПК\n\n"
        "Бот работает на <b>Render</b>, команды выполняются на вашем ПК "
        "через локального агента.\n\n"
        "/help — список команд"
    )

    if not _is_admin(user.id):
        text += f"\n\n⛔ Доступ ограничен. Владелец: ID {CONFIG['admin_user_id']}"
        await update.message.reply_text(text, parse_mode="HTML")
        return

    await update.message.reply_text(text, parse_mode="HTML")

@admin_required
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Команды:</b>\n\n"
        "/test — Диагностика\n"
        "/on — Включить SA\n"
        "/off — Выключить\n"
        "/offc — Сессию завершить\n"
        "/offall — Отключить навсегда\n"
        "/sua &lt;пароль&gt; — Сохранить sudo\n"
        "/sua — Выдать sudo\n"
        "/suaoff — Отозвать sudo\n"
        "/suaon — Выдать sudo\n"
        "/stop — Остановить процесс\n"
        "/SA userid &lt;id&gt; — Сменить владельца\n"
        "/SA model &lt;op&gt; &lt;api&gt; &lt;модель&gt; — Модель\n\n"
        "💬 Любой текст = shell-команда на ПК"
    )
    await update.message.reply_text(text, parse_mode="HTML")

@admin_required
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Проверка системы...")
    _create_task("system", {"action": "test"}, update)

@admin_required
async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = _create_task("system", {"action": "on"}, update)
    await update.message.reply_text(f"⏳ Включение...")

@admin_required
async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("system", {"action": "off"}, update)
    await update.message.reply_text("⏳ Выключение...")

@admin_required
async def turn_off_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("system", {"action": "off_session"}, update)
    await update.message.reply_text("⏳ Завершение сессии...")

@admin_required
async def turn_off_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("system", {"action": "off_permanent"}, update)
    await update.message.reply_text("⏳ Перманентное отключение...")

@admin_required
async def sua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        password = " ".join(args)
        _create_task("sua", {"action": "set_password", "password": password}, update)
        await update.message.reply_text("⏳ Сохранение пароля sudo...")
    else:
        _create_task("sua", {"action": "enable"}, update)
        await update.message.reply_text("⏳ Выдача прав sudo...")

@admin_required
async def sua_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("sua", {"action": "disable"}, update)
    await update.message.reply_text("⏳ Отзыв прав sudo...")

@admin_required
async def sua_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("sua", {"action": "grant"}, update)
    await update.message.reply_text("⏳ Выдача прав sudo...")

@admin_required
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _create_task("system", {"action": "stop_process"}, update)
    await update.message.reply_text("⏳ Остановка процесса...")

@admin_required
async def sa_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("/SA userid <id> | /SA model <op> <api> <model>")
        return

    cmd = args[0].lower()
    if cmd == "userid":
        try:
            uid = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ ID должен быть числом")
            return
        _create_task("config", {"key": "admin_user_id", "value": uid}, update)
        await update.message.reply_text("⏳ Смена владельца...")
    elif cmd == "model":
        if len(args) < 4:
            await update.message.reply_text("Использование: /SA model <operator> <api> <model>")
            return
        _create_task("config", {
            "key": "model",
            "value": {"operator": args[1], "api": args[2], "name": args[3]},
        }, update)
        await update.message.reply_text("⏳ Смена модели...")
    else:
        await update.message.reply_text(f"❌ Неизвестно: {cmd}")

@admin_required
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith("/"):
        return

    await update.message.reply_text(
        f"⚙️ Команда поставлена в очередь:\n<code>{text[:200]}</code>",
        parse_mode="HTML",
    )
    _create_task("command", {"command": text}, update)
    log.info(f"Задача: command '{text[:60]}...'")

async def error_handler(update: Update | None, context: ContextTypes.DEFAULT_TYPE):
    log.error("Ошибка:", exc_info=context.error)
    if isinstance(context.error, InvalidToken):
        log.critical("Токен невалиден!")

# ── FastAPI ──

app = FastAPI(title="Super ASK Render")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

SELF_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

@app.on_event("startup")
async def startup():
    global application
    token = CONFIG["bot_token"]
    if not token:
        log.critical("BOT_TOKEN не задан!")
        return
    log.info(f"Старт Super ASK Render (токен: {token[:12]}...)")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test))
    application.add_handler(CommandHandler("on", turn_on))
    application.add_handler(CommandHandler("off", turn_off))
    application.add_handler(CommandHandler("offc", turn_off_session))
    application.add_handler(CommandHandler("offall", turn_off_permanent))
    application.add_handler(CommandHandler("sua", sua_command))
    application.add_handler(CommandHandler("suaoff", sua_off))
    application.add_handler(CommandHandler("suaon", sua_on))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("SA", sa_admin_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    await application.initialize()

    webhook_url = f"{SELF_URL}/webhook"
    if webhook_url.startswith("http"):
        await application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
        log.info(f"Webhook: {webhook_url}")
    else:
        log.warning("RENDER_EXTERNAL_URL не задан — webhook не установлен")

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
async def agent_get_task():
    _cleanup()
    for tid, task in TASKS.items():
        if task["status"] == "pending":
            task["status"] = "running"
            return {
                "id": task["id"],
                "type": task["type"],
                "params": task["params"],
            }
    return {"id": None}

@app.post("/agent/task/{task_id}/result")
async def agent_submit_result(task_id: str, request: Request):
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
    result = task.get("result") or task.get("error") or "(пустой вывод)"
    icon = "✅" if task["status"] == "completed" else "❌"
    text = f"{icon} Результат:\n```\n{result[:3500]}\n```"
    if len(result) > 3500:
        text = text + "\n\n... [обрезано]"
    try:
        await application.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except BadRequest:
        clean = result.replace("`", "").replace("*", "").replace("_", "")
        try:
            await application.bot.send_message(chat_id=chat_id, text=f"{icon} Результат:\n{clean[:4000]}")
        except Exception as e:
            log.error(f"Ошибка отправки: {e}")
    except Exception as e:
        log.error(f"Ошибка отправки: {e}")
    TASKS.pop(task["id"], None)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "bot_configured": bool(CONFIG["bot_token"]),
        "pending": sum(1 for t in TASKS.values() if t["status"] == "pending"),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("render.app:app", host="0.0.0.0", port=port, log_level="info")
