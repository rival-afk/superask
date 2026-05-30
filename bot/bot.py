"""
Telegram-бот для управления Super ASK.
Все команды принимаются только от администратора (владельца).
"""
import asyncio
import logging
import sys
import traceback
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes
)
from telegram.error import (
    TelegramError, InvalidToken, RetryAfter, TimedOut, NetworkError,
    Forbidden, BadRequest
)

from core import config
from core import tools
from core.superask import SuperASK
from sua import sua

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("superask.bot")

sa = SuperASK()


def is_admin(update: Update) -> bool:
    admin_id = config.get_admin_user_id()
    if admin_id is None:
        return True
    return update.effective_user.id == admin_id


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user is None:
            return
        if not is_admin(update):
            log.warning(f"Доступ запрещён для user_id={update.effective_user.id}")
            await update.message.reply_text("⛔ Доступ запрещён. Вы не являетесь администратором.\n"
                                           "Обратитесь к владельцу бота для получения доступа.")
            return
        return await func(update, context)

    wrapper.__name__ = func.__name__
    return wrapper


async def error_handler(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Исключение при обработке update:", exc_info=context.error)

    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    log.error(f"Traceback:\n{tb}")

    if isinstance(context.error, InvalidToken):
        log.critical("Токен бота невалиден! Проверьте: superask bot <новый_токен>")
        return

    if isinstance(context.error, RetryAfter):
        log.warning(f"Flood control. Ждём {context.error.retry_after}с...")
        await asyncio.sleep(context.error.retry_after)
        return

    if isinstance(context.error, TimedOut):
        log.warning("Таймаут соединения с Telegram. Переподключение...")
        return

    if isinstance(context.error, NetworkError):
        log.warning(f"Сетевая ошибка: {context.error}. Повтор через 5с...")
        await asyncio.sleep(5)
        return

    if isinstance(context.error, Forbidden):
        log.warning(f"Бот заблокирован пользователем: {context.error}")
        return

    if isinstance(context.error, BadRequest):
        log.warning(f"Неверный запрос: {context.error}")
        if update and update.message:
            try:
                await update.message.reply_text(f"❌ Ошибка запроса: {context.error}")
            except:
                pass
        return

    if update and update.message:
        try:
            await update.message.reply_text("❌ Произошла внутренняя ошибка. Проверьте логи: superask logs")
        except:
            pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"Команда /start от user_id={user.id} username=@{user.username}")
    await update.message.reply_text(
        "🤖 <b>Super ASK</b> — система удалённого управления ПК через Telegram.\n\n"
        "Используйте /help для списка команд.",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Команды управления:</b>\n\n"
        "/test — Проверка работы нейросети и доступа к sudo\n"
        "/on — Включить Super ASK\n"
        "/off — Выключить Super ASK\n"
        "/offc — Отключить SA в текущей сессии\n"
        "/offall — Отключить SA навсегда (перманентно)\n"
        "/sua &lt;пароль&gt; — Сохранить пароль sudo для SUA\n"
        "/sua — Предоставить нейросети права sudo без подтверждения\n"
        "/suaoff — Отозвать права sudo у Super ASK\n"
        "/suaon — Выдать права sudo для Super ASK\n"
        "/stop — Остановить текущий активный процесс\n\n"
        "🔧 <b>Команды настройки:</b>\n"
        "/SA userid &lt;tg_id&gt; — Сменить владельца бота\n"
        "/SA bot &lt;token&gt; — Сменить токен бота\n"
        "/SA model &lt;op&gt; &lt;api&gt; &lt;model&gt; — Сменить модель\n\n"
        "💬 Любое текстовое сообщение будет выполнено как shell-команда."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudo_status = "✅ Доступны" if sua.is_sudo_enabled() else "❌ Не запрошены"
    model = config.get_model()
    await update.message.reply_text(
        f"🤖 <b>Super ASK</b>\n\n"
        f"📡 Модель: {model['operator']} / {model['api']} / {model['model']}\n"
        f"🔑 Sudo: {sudo_status}\n"
        f"⚙️ Статус: {'🟢 Активен' if sa.running else '🔴 Остановлен'}\n"
        f"🛠 Инструментов: {len(tools.get_all_tools())}",
        parse_mode="HTML",
    )


async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sa.is_permanently_disabled():
        await update.message.reply_text("⛔ Super ASK перманентно отключён.\n"
                                       "Для включения измените конфиг вручную.")
        return
    if sa.running:
        await update.message.reply_text("Super ASK уже запущен.")
        return
    sa.start()
    log.info("Super ASK включён")
    await update.message.reply_text("🟢 Super ASK запущен. Команды принимаются.")


async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not sa.running:
        await update.message.reply_text("Super ASK уже остановлен.")
        return
    sa.stop()
    log.info("Super ASK выключен")
    await update.message.reply_text("🔴 Super ASK остановлен.")


async def turn_off_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sa.stop_session()
    log.info("Сессия Super ASK завершена")
    await update.message.reply_text("⏹ Текущая сессия Super ASK завершена.")


async def turn_off_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sa.disable_permanently()
    log.warning("Super ASK перманентно отключён")
    await update.message.reply_text("⛔ Super ASK перманентно отключён.\n"
                                   "Для включения отредактируйте config.json вручную.")


async def sua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        password = args[0]
        if len(password) < 4:
            await update.message.reply_text("❌ Пароль должен быть минимум 4 символа.")
            return
        sua.set_password(password)
        log.info("Пароль sudo сохранён")
        await update.message.reply_text("🔑 Пароль sudo сохранён в SUA.")
    else:
        sua.set_sudo_enabled(True)
        log.info("Права sudo выданы без подтверждения")
        await update.message.reply_text(
            "🤖 Нейросети предоставлены права sudo без ручного подтверждения.\n"
            "Уведомления о командах будут отправляться."
        )


async def sua_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sua.set_sudo_enabled(False)
    log.info("Права sudo отозваны")
    await update.message.reply_text("🔒 Права sudo отозваны у Super ASK.")


async def sua_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sua.set_sudo_enabled(True)
    log.info("Права sudo выданы")
    await update.message.reply_text("🔓 Права sudo выданы для Super ASK.")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sa.current_command:
        sa.current_command = None
        log.info("Текущий процесс остановлен пользователем")
        await update.message.reply_text("⏹ Текущий активный процесс остановлен.")
    else:
        await update.message.reply_text("Нет активного процесса для остановки.")


async def sa_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "/SA userid &lt;tg_id&gt; — Сменить владельца\n"
            "/SA bot &lt;token&gt; — Сменить токен\n"
            "/SA model &lt;op&gt; &lt;api&gt; &lt;model&gt; — Сменить модель",
            parse_mode="HTML",
        )
        return

    cmd = args[0].lower()

    if cmd == "userid":
        try:
            tg_id = int(args[1])
            if tg_id <= 0:
                await update.message.reply_text("❌ ID должен быть положительным числом.")
                return
            config.set_admin_user_id(tg_id)
            log.info(f"Владелец бота изменён на ID: {tg_id}")
            await update.message.reply_text(f"✅ Владелец бота изменён на ID: {tg_id}\n"
                                           f"Теперь только этот пользователь может управлять ботом.")
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")

    elif cmd == "bot":
        token = args[1]
        if not config.validate_token(token):
            await update.message.reply_text("❌ Токен невалиден. Должен быть формата 123456:ABCdef...")
            return
        config.set_bot_token(token)
        log.info("Токен бота обновлён")
        await update.message.reply_text("✅ Токен бота обновлён.\n"
                                       "⚠️ Перезапустите бота для применения нового токена:\n"
                                       "   superask restart (в терминале)")

    elif cmd == "model":
        if len(args) < 4:
            await update.message.reply_text("Использование: /SA model &lt;operator&gt; &lt;api&gt; &lt;model&gt;",
                                           parse_mode="HTML")
            return
        config.set_model(args[1], args[2], args[3])
        log.info(f"Модель изменена: {args[1]} / {args[2]} / {args[3]}")
        await update.message.reply_text(f"✅ Модель изменена: {args[1]} / {args[2]} / {args[3]}")

    else:
        await update.message.reply_text(f"❌ Неизвестная команда: {cmd}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not sa.running:
        await update.message.reply_text("Super ASK не запущен. Используйте /on.")
        return

    text = update.message.text
    if not text or text.startswith("/"):
        return

    log.info(f"Выполнение команды: {text[:100]}...")
    await update.message.reply_text("⚙️ Команда выполняется...")

    try:
        result = sa.execute_command(text)
    except Exception as e:
        log.error(f"Ошибка выполнения команды: {e}")
        await update.message.reply_text(f"❌ Ошибка выполнения: {e}")
        return

    MAX_LEN = 4000
    if len(result) > MAX_LEN:
        result = result[:MAX_LEN] + "\n\n... [вывод обрезан]"

    if not result or not result.strip():
        result = "(пустой вывод)"

    try:
        await update.message.reply_text(f"✅ Результат:\n```\n{result}\n```", parse_mode="Markdown")
    except BadRequest:
        result_clean = result.replace("`", "").replace("*", "").replace("_", "")
        await update.message.reply_text(f"✅ Результат:\n{result_clean[:4000]}")
    except Exception as e:
        log.error(f"Ошибка отправки результата: {e}")
        await update.message.reply_text(f"✅ Команда выполнена (ошибка форматирования вывода)")


def main():
    token = config.get_bot_token()
    if not token:
        log.critical("Токен бота не задан!")
        log.critical("Установите токен: superask bot <токен_от_BotFather>")
        sys.exit(1)

    if not config.validate_token(token):
        log.critical(f"Токен бота невалиден: {token[:12]}...")
        log.critical("Получите новый токен у @BotFather")
        sys.exit(1)

    log.info(f"Запуск Super ASK бота (токен: {token[:12]}...)")

    try:
        app = Application.builder().token(token).build()
    except InvalidToken:
        log.critical("Токен бота отклонён Telegram. Проверьте токен.")
        sys.exit(1)
    except Exception as e:
        log.critical(f"Не удалось создать приложение бота: {e}")
        sys.exit(1)

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

    app.add_error_handler(error_handler)

    log.info("Super ASK бот запущен. Ожидание команд...")
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False,
        )
    except InvalidToken:
        log.critical("Токен бота невалиден при подключении.")
        sys.exit(1)
    except NetworkError as e:
        log.critical(f"Ошибка сети при подключении к Telegram: {e}")
        log.critical("Проверьте интернет-соединение.")
        sys.exit(1)
    except Exception as e:
        log.critical(f"Критическая ошибка бота: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
