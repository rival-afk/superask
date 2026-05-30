"""
Telegram-бот для управления Super ASK.
Все команды принимаются только от администратора (владельца).
"""
import asyncio
import logging
import sys
import time
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
        log.critical("Токен бота невалиден! Проверьте: sa bot <новый_токен>")
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
            await update.message.reply_text("❌ Произошла внутренняя ошибка. Проверьте логи: sa logs")
        except:
            pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"Команда /start от user_id={user.id} username=@{user.username}")

    msg = (
        "🤖 <b>Super ASK</b> — система удалённого управления ПК через Telegram.\n\n"
        "Используйте /help для списка команд.\n\n"
    )

    if not is_admin(update):
        admin_id = config.get_admin_user_id()
        msg += f"⛔ Доступ ограничен. Этот бот принадлежит пользователю ID: {admin_id}"
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    warnings = sa.check_config_ready()
    if warnings:
        msg += "📋 <b>Статус настройки:</b>\n" + "\n".join(warnings)
    else:
        msg += "✅ Все настройки выполнены."

    await update.message.reply_text(msg, parse_mode="HTML")


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
    model = config.get_model()
    lines = [
        "🤖 <b>Super ASK — Диагностика</b>",
        "",
        f"📡 Модель: {model['operator']} / {model['api']} / {model['model']}",
        f"⚙️ Статус: {'🟢 Активен' if sa.running else '🔴 Остановлен'}"
    ]

    if sa.running:
        lines.append(f"🛠 Инструментов: {len(tools.get_all_tools())}")
    else:
        lines.append("🛠 Инструменты не загружены (SA остановлен)")

    lines.append("")
    lines.append("<b>Проверка SUA:</b>")

    if sua.is_sudo_enabled():
        lines.append("✅ Права sudo: выданы")
    else:
        lines.append("❌ Права sudo: не выданы")
        lines.append("   → Используйте /sua <пароль>, затем /suaon")

    if sua.get_sudo_password_hash():
        lines.append("✅ Пароль sudo: сохранён")
    else:
        lines.append("❌ Пароль sudo: не сохранён")
        lines.append("   → Используйте /sua <пароль_от_sudo>")

    lines.append("")
    lines.append("<b>Проверка конфигурации:</b>")
    warnings = sa.check_config_ready()
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("✅ Все настройки выполнены (токен, админ, SUA)")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sa.is_permanently_disabled():
        await update.message.reply_text(
            "⛔ Super ASK перманентно отключён.\n"
            "Для включения измените конфиг вручную:\n"
            "  nano ~/.config/superask/config.json\n"
            "  (установите permanently_disabled: false)"
        )
        return
    if sa.running:
        await update.message.reply_text("Super ASK уже запущен. Используйте /test для проверки.")
        return
    sa.start()
    log.info("Super ASK включён")

    msg = "🟢 Super ASK запущен. Команды принимаются."

    warnings = sa.check_config_ready()
    if warnings:
        msg += "\n\n⚠️ <b>Есть незавершённые настройки:</b>\n" + "\n".join(warnings)
        msg += "\n\nИспользуйте /test для полной диагностики."

    await update.message.reply_text(msg, parse_mode="HTML")


async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not sa.running:
        await update.message.reply_text("Super ASK уже остановлен. Используйте /on для запуска.")
        return
    sa.stop()
    log.info("Super ASK выключен")
    await update.message.reply_text("🔴 Super ASK остановлен. Команды больше не принимаются.\nДля включения: /on")


async def turn_off_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not sa.session_active:
        await update.message.reply_text("Нет активной сессии для завершения.")
        return
    sa.stop_session()
    log.info("Сессия Super ASK завершена")
    await update.message.reply_text("⏹ Текущая сессия Super ASK завершена.\nSuper ASK остановлен.")


async def turn_off_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sa.disable_permanently()
    log.warning("Super ASK перманентно отключён")
    await update.message.reply_text(
        "⛔ Super ASK перманентно отключён.\n"
        "Теперь включить можно только через терминал:\n"
        "  superask shell 'sed -i \"s/permanently_disabled.*/permanently_disabled: false/\" ~/.config/superask/config.json'\n"
        "  Или вручную отредактировать config.json."
    )


async def sua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        password = " ".join(args)
        if len(password) < 4:
            await update.message.reply_text("❌ Пароль должен быть минимум 4 символа.")
            return
        sua.set_password(password)
        log.info("Пароль sudo сохранён")
        await update.message.reply_text(
            "🔑 Пароль sudo сохранён в SUA.\n"
            "Теперь выдайте права: /suaon\n"
            "Либо используйте /sua без пароля для автоматического включения."
        )
    else:
        if not sua.get_sudo_password_hash():
            await update.message.reply_text(
                "❌ Сначала сохраните пароль sudo.\n"
                "Используйте: /sua <пароль_от_sudo>\n\n"
                "После этого можно будет выдать права sudo нейросети."
            )
            return
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
    if not sua.get_sudo_password_hash():
        await update.message.reply_text(
            "❌ Не удалось выдать права sudo.\n"
            "Сначала сохраните пароль: /sua <пароль_от_sudo>\n\n"
            "SUA использует этот пароль для выполнения sudo-команд."
        )
        return
    sua.set_sudo_enabled(True)
    log.info("Права sudo выданы")
    await update.message.reply_text(
        "🔓 Права sudo выданы для Super ASK.\n"
        "Теперь нейросеть может выполнять команды с sudo."
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not sa.running:
        await update.message.reply_text("Super ASK остановлен. Нечего останавливать.")
        return
    if sa.current_command:
        sa.current_command = None
        log.info("Текущий процесс остановлен пользователем")
        await update.message.reply_text("⏹ Текущий активный процесс остановлен.")
    else:
        await update.message.reply_text(
            "Нет активного процесса для остановки.\n"
            "Если хотите остановить SA: /off"
        )


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
                                       "   sa restart (в терминале)")

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
        await update.message.reply_text(
            "Super ASK не запущен. Используйте /on.\n"
            "Если хотите проверить настройки: /test"
        )
        return

    text = update.message.text
    if not text or text.startswith("/"):
        return

    text = text.strip()

    log.info(f"Выполнение команды: {text[:100]}...")

    if text.lower().startswith("sudo "):
        if not sua.is_sudo_enabled():
            await update.message.reply_text(
                "❌ Команда требует sudo, но права не выданы.\n\n"
                "Чтобы настроить:\n"
                "  1. /sua <пароль> — сохранить пароль\n"
                "  2. /suaon — выдать права\n\n"
                "Либо уберите sudo из команды."
            )
            return
        if not sua.get_sudo_password_hash():
            await update.message.reply_text(
                "❌ Пароль sudo не сохранён в SUA.\n"
                "Используйте: /sua <пароль_от_sudo>\n"
                "Затем повторите команду."
            )
            return
        await update.message.reply_text("⚙️ Выполняется sudo-команда...")
    else:
        await update.message.reply_text("⚙️ Команда выполняется...")

    try:
        result = sa.execute_command(text)
    except Exception as e:
        log.error(f"Ошибка выполнения команды: {e}")
        await update.message.reply_text(
            f"❌ Ошибка выполнения:\n<code>{e}</code>\n\n"
            "Проверьте команду и попробуйте снова.",
            parse_mode="HTML",
        )
        return

    MAX_LEN = 3900
    if len(result) > MAX_LEN:
        result = result[:MAX_LEN] + "\n\n... [вывод обрезан]"

    if not result or not result.strip():
        result = "(пустой вывод)"

    try:
        await update.message.reply_text(f"✅ Результат:\n```\n{result}\n```", parse_mode="Markdown")
    except BadRequest:
        try:
            result_clean = result.replace("`", "").replace("*", "").replace("_", "")
            await update.message.reply_text(f"✅ Результат:\n{result_clean[:4000]}")
        except Exception:
            await update.message.reply_text("✅ Команда выполнена. Вывод слишком большой для отображения.")
    except Exception as e:
        log.error(f"Ошибка отправки результата: {e}")
        await update.message.reply_text("✅ Команда выполнена (ошибка форматирования вывода)")


def _build_app():
    token = config.get_bot_token()
    if not token:
        log.critical("Токен бота не задан!")
        log.critical("Установите токен: sa bot <токен_от_BotFather>")
        sys.exit(1)

    if not config.validate_token(token):
        log.critical(f"Токен бота невалиден: {token[:12]}...")
        log.critical("Получите новый токен у @BotFather")
        sys.exit(1)

    log.info(f"Запуск Super ASK бота (токен: {token[:12]}...)")

    proxy = config.get_proxy()
    builder = Application.builder().token(token)
    if proxy:
        log.info(f"Используется прокси: {proxy[:40]}...")
        builder = builder.proxy_url(proxy).connect_kwargs({"timeout": 30})
    try:
        app = builder.build()
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
    return app


def main():
    RETRY_DELAY = 10
    while True:
        try:
            app = _build_app()
            log.info("Super ASK бот запущен. Ожидание команд...")
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False,
            )
        except InvalidToken:
            log.critical("Токен бота невалиден при подключении.")
            sys.exit(1)
        except (NetworkError, TimedOut) as e:
            log.warning(f"Сетевая ошибка: {e}. Повтор через {RETRY_DELAY}с...")
            time.sleep(RETRY_DELAY)
        except (RetryAfter) as e:
            log.warning(f"Flood control. Ждём {e.retry_after}с...")
            time.sleep(e.retry_after)
        except Exception as e:
            log.error(f"Критическая ошибка бота: {e}. Повтор через {RETRY_DELAY}с...")
            time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    main()
