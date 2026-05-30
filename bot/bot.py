"""
Telegram-бот для управления Super ASK.
Все команды принимаются только от администратора (владельца).
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)

from core import config
from core.superask import SuperASK
from sua import sua

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

sa = SuperASK()


def is_admin(update: Update) -> bool:
    admin_id = config.get_admin_user_id()
    if admin_id is None:
        return True
    return update.effective_user.id == admin_id


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update):
            await update.message.reply_text("⛔ Доступ запрещён. Вы не являетесь администратором.")
            return
        return await func(update, context)
    return wrapper


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Super ASK — система удалённого управления ПК через Telegram.\n"
        "Используйте /help для списка команд."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 Команды бота:\n\n"
        "/test — Проверка работы нейросети и доступа к sudo\n"
        "/on — Включить Super ASK\n"
        "/off — Выключить Super ASK\n"
        "/offc — Отключить SA в текущей сессии\n"
        "/offall — Отключить SA навсегда (перманентно)\n"
        "/sua <пароль> — Сохранить пароль sudo для SUA\n"
        "/sua — Предоставить нейросети права sudo без подтверждения\n"
        "/suaoff — Отозвать права sudo у Super ASK\n"
        "/suaon — Выдать права sudo для Super ASK\n"
        "/stop — Остановить текущий активный процесс\n\n"
        "🔧 Команды настройки:\n"
        "/SA userid <tg_id> — Сменить владельца бота\n"
        "/SA bot <token> — Сменить токен бота\n"
        "/SA model <operator> <api> <model> — Сменить модель"
    )
    await update.message.reply_text(text)


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_status = "✅ Доступны" if sua.is_sudo_enabled() else "❌ Не запрошены"
    model = config.get_model()
    await update.message.reply_text(
        f"🤖 Super ASK\n\n"
        f"📡 Модель: {model['operator']} / {model['api']} / {model['model']}\n"
        f"🔑 Sudo: {sudo_status}\n"
        f"⚙️ Статус: {'🟢 Активен' if sa.running else '🔴 Остановлен'}"
    )


async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sa.is_permanently_disabled():
        await update.message.reply_text("⛔ Super ASK перманентно отключён.")
        return
    if sa.running:
        await update.message.reply_text("Super ASK уже запущен.")
        return
    sa.start()
    await update.message.reply_text("🟢 Super ASK запущен. Команды принимаются.")


async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not sa.running:
        await update.message.reply_text("Super ASK уже остановлен.")
        return
    sa.stop()
    await update.message.reply_text("🔴 Super ASK остановлен.")


async def turn_off_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sa.stop_session()
    await update.message.reply_text("⏹ Текущая сессия Super ASK завершена.")


async def turn_off_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sa.disable_permanently()
    await update.message.reply_text("⛔ Super ASK перманентно отключён. Для включения измените конфиг.")


async def sua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        password = args[0]
        sua.set_password(password)
        await update.message.reply_text("🔑 Пароль sudo сохранён в SUA.")
    else:
        sua.set_sudo_enabled(True)
        await update.message.reply_text(
            "🤖 Нейросети предоставлены права sudo без ручного подтверждения.\n"
            "Уведомления о командах будут отправляться."
        )


async def sua_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sua.set_sudo_enabled(False)
    await update.message.reply_text("🔒 Права sudo отозваны.")


async def sua_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sua.set_sudo_enabled(True)
    await update.message.reply_text("🔓 Права sudo выданы для Super ASK.")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sa.current_command:
        sa.current_command = None
        await update.message.reply_text("⏹ Текущий процесс остановлен.")
    else:
        await update.message.reply_text("Нет активного процесса для остановки.")


async def sa_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /SA <команда> <параметры>")
        return

    cmd = args[0].lower()

    if cmd == "userid":
        try:
            tg_id = int(args[1])
            config.set_admin_user_id(tg_id)
            await update.message.reply_text(f"✅ Владелец бота изменён на ID: {tg_id}")
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")

    elif cmd == "bot":
        token = args[1]
        config.set_bot_token(token)
        await update.message.reply_text("✅ Токен бота обновлён. Перезапустите бота для применения.")

    elif cmd == "model":
        if len(args) < 4:
            await update.message.reply_text("Использование: /SA model <operator> <api> <model>")
            return
        config.set_model(args[1], args[2], args[3])
        await update.message.reply_text(
            f"✅ Модель изменена: {args[1]} / {args[2]} / {args[3]}"
        )

    else:
        await update.message.reply_text(f"❌ Неизвестная команда: {cmd}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not sa.running:
        await update.message.reply_text("Super ASK не запущен. Используйте /on.")
        return

    text = update.message.text
    await update.message.reply_text("⚙️ Команда выполняется...")

    result = sa.execute_command(text)

    MAX_LEN = 4000
    if len(result) > MAX_LEN:
        result = result[:MAX_LEN] + "\n... [output truncated]"

    await update.message.reply_text(f"✅ Результат:\n```\n{result}\n```")


def main():
    token = config.get_bot_token()
    if not token:
        log.error("Токен бота не задан. Используйте /SA bot <token> или отредактируйте config.json")
        sys.exit(1)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("test", require_admin(test)))
    app.add_handler(CommandHandler("on", require_admin(turn_on)))
    app.add_handler(CommandHandler("off", require_admin(turn_off)))
    app.add_handler(CommandHandler("offc", require_admin(turn_off_session)))
    app.add_handler(CommandHandler("offall", require_admin(turn_off_permanent)))
    app.add_handler(CommandHandler("sua", require_admin(sua_command)))
    app.add_handler(CommandHandler("suaoff", require_admin(sua_off)))
    app.add_handler(CommandHandler("suaon", require_admin(sua_on)))
    app.add_handler(CommandHandler("stop", require_admin(stop_command)))
    app.add_handler(CommandHandler("SA", require_admin(sa_admin_command)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Super ASK бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
