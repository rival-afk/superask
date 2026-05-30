#!/usr/bin/env python3
"""
Super ASK (SA) — CLI для управления системой из терминала.

Использование:
  superask bot <token>           — Установить токен Telegram-бота
  superask userid <id>           — Установить ID администратора
  superask model <op> <api> <m>  — Сменить модель
  superask status                — Статус системы и сервиса
  superask wol                   — Информация Wake-on-LAN
  superask tools                 — Список всех инструментов
  superask shell <cmd>           — Выполнить команду
  superask restart               — Перезапустить сервис superask
  superask logs                  — Логи сервиса superask
  superask install               — Запустить установщик
  superask help                  — Эта справка

Без аргументов — запускает Telegram-бота (foreground).
"""
import sys
import os
import subprocess
import shlex
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from core import config
from core import tools
from sua import sua


def _e(msg: str) -> None:
    print(f"[SA] {msg}", file=sys.stderr)


def _die(msg: str, code: int = 1) -> None:
    _e(msg)
    sys.exit(code)


def _check_systemd() -> bool:
    try:
        r = subprocess.run(["systemctl", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except:
        return False


def cmd_bot(token):
    """Установить токен Telegram-бота"""
    if not token:
        _die("Укажите токен: superask bot <token>")

    token = token.strip().strip("\"'")
    if not config.validate_token(token):
        _die("Токен невалиден. Должен быть формата 123456789:ABCdef... (получен от @BotFather)")

    config.set_bot_token(token)
    print(f"[SA] Токен бота сохранён: {token[:12]}...")
    if _check_systemd():
        try:
            r = subprocess.run(["systemctl", "is-active", "superask"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() == "active":
                _e("Сервис перезапускается...")
                subprocess.run(["sudo", "systemctl", "restart", "superask"], capture_output=True, text=True, timeout=30)
                print("[SA] Сервис перезапущен.")
            else:
                print("[SA] Запустите сервис: superask restart")
        except:
            print("[SA] Запустите сервис: superask restart")
    else:
        print("[SA] Запустите бота: superask (без аргументов)")


def cmd_userid(uid):
    """Установить ID администратора Telegram"""
    if not uid:
        _die("Укажите ID: superask userid <telegram_id>")

    try:
        uid_int = int(uid)
    except ValueError:
        _die(f"ID должен быть числом. Получено: '{uid}'")

    if uid_int <= 0:
        _die("ID должен быть положительным числом")

    config.set_admin_user_id(uid_int)
    print(f"[SA] ID администратора сохранён: {uid_int}")
    print("[SA] Теперь только этот пользователь сможет управлять ботом.")
    print("[SA] Чтобы узнать свой ID, напишите @userinfobot в Telegram.")


def cmd_model(args):
    """Сменить модель нейросети"""
    if len(args) < 3:
        _die("Использование: superask model <operator> <api> <model>\n"
             "  Например: superask model opencode zen deepseek-v4-flash-free")

    config.set_model(args[0], args[1], args[2])
    print(f"[SA] Модель изменена: {args[0]} / {args[1]} / {args[2]}")

    if _check_systemd():
        try:
            r = subprocess.run(["systemctl", "is-active", "superask"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() == "active":
                _e("Сервис перезапускается для применения модели...")
                subprocess.run(["sudo", "systemctl", "restart", "superask"], capture_output=True, text=True, timeout=30)
                print("[SA] Сервис перезапущен.")
        except:
            pass


def cmd_status():
    """Показать статус системы"""
    print("── Super ASK ──────────────────────────────")

    token = config.get_bot_token()
    if token:
        if config.validate_token(token):
            print(f"  Токен бота:         ✅ {token[:12]}...")
        else:
            print(f"  Токен бота:         ❌ невалидный токен ({token[:12]}...)")
            _e("  Подсказка: superask bot <новый_токен>")
    else:
        print(f"  Токен бота:         ❌ не задан")
        _e("  Подсказка: superask bot <токен_от_BotFather>")

    admin_id = config.get_admin_user_id()
    if admin_id:
        print(f"  Админ ID:           {admin_id}")
    else:
        print(f"  Админ ID:           ❌ не задан (бот доступен всем)")

    model = config.get_model()
    print(f"  Модель:             {model['operator']} / {model['api']} / {model['model']}")

    sudo_enabled = sua.is_sudo_enabled()
    print(f"  Sudo:               {'✅ включён' if sudo_enabled else '❌ выключен'}")

    # Сервис superask
    if _check_systemd():
        try:
            r = subprocess.run(["systemctl", "is-active", "superask"], capture_output=True, text=True, timeout=5)
            status = r.stdout.strip()
            if status == "active":
                print(f"  Сервис superask:    ✅ активен")
            elif status == "activating":
                print(f"  Сервис superask:    ⏳ запускается (нет токена?)")
            else:
                print(f"  Сервис superask:    ❌ {status}")
                _e("  Подсказка: sudo systemctl start superask")
        except:
            print(f"  Сервис superask:    ❓ не удалось проверить")

        try:
            r = subprocess.run(["systemctl", "is-enabled", "superask"], capture_output=True, text=True, timeout=5)
            print(f"  Автозагрузка:       {'✅' if r.stdout.strip() == 'enabled' else '❌'} {r.stdout.strip()}")
        except:
            pass
    else:
        print(f"  Сервис superask:    ❌ systemd не найден")

    print(f"  Инструментов:       {len(tools.get_all_tools())}")

    # WoL
    wol_status = _check_wol()
    print(f"  Wake-on-LAN:        {'✅ включён' if wol_status else '❌ выключен'}")
    if wol_status:
        print(f"  MAC (enp2s0):        8c:16:45:ff:40:15")

    print("──────────────────────────────────────────")


def _check_wol() -> bool:
    try:
        r = subprocess.run(["sudo", "ethtool", "enp2s0"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            r = subprocess.run(["ethtool", "enp2s0"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if "Wake-on" in line and "Supports" not in line:
                return "g" in line
    except:
        pass
    return False


def cmd_wol():
    """Показать информацию о Wake-on-LAN"""
    print("── Wake-on-LAN ────────────────────────────")

    # Определяем ethernet-интерфейс
    eth = "enp2s0"
    mac = "8c:16:45:ff:40:15"

    try:
        for iface in sorted(Path("/sys/class/net").iterdir()):
            name = iface.name
            if name.startswith("lo") or name.startswith("wl") or "vir" in name or "docker" in name:
                continue
            mac_file = iface / "address"
            if mac_file.exists():
                eth = name
                mac = mac_file.read_text().strip()
                break
    except:
        pass

    print(f"  Интерфейс:          {eth}")
    print(f"  MAC-адрес:          {mac}")

    # Проверка WoL
    try:
        r = subprocess.run(["sudo", "ethtool", eth], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            r = subprocess.run(["ethtool", eth], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if "Supports Wake-on" in line:
                print(f"  Поддерживает:       {line.split(':')[1].strip()}")
            if "Wake-on" in line and "Supports" not in line:
                val = line.split(':')[1].strip()
                print(f"  Статус:             {'✅ включён (g)' if val == 'g' else '❌ выключен (' + val + ')'}")
    except FileNotFoundError:
        print(f"  Ошибка: ethtool не установлен")
        _e("  Установите: sudo pacman -S ethtool (или аналог)")
    except:
        print(f"  Статус:             ❓ не удалось проверить")

    print()
    print("  Отправка magic packet:")
    print(f"    wakeonlan {mac}")
    print()
    print("  Или из Python:")
    print("    from wakeonlan import send_magic_packet")
    print(f"    send_magic_packet('{mac}')")
    print("──────────────────────────────────────────")


def cmd_tools():
    """Показать список доступных инструментов"""
    all_tools = tools.get_all_tools()
    if not all_tools:
        _e("Нет загруженных инструментов. Проверьте core/tools.py")
        sys.exit(1)

    print(f"── Доступные инструменты ({len(all_tools)}) ────────")
    for name, tool in sorted(all_tools.items()):
        desc = tool.description.split("\n")[0] if tool.description else "(нет описания)"
        params = list(tool.parameters.keys()) if tool.parameters else []
        params_str = " ".join(f"<{p}>" for p in params[:3])
        if len(params) > 3:
            params_str += " ..."
        print(f"  {name:15s} {desc[:70]}")
        if params:
            print(f"  {' ':<15s} Параметры: {params_str}")
    print("──────────────────────────────────────────")


def cmd_shell(command: str):
    """Выполнить команду в shell"""
    if not command:
        _die("Укажите команду: superask shell <command>")

    print(f"[SA] Выполняется: {command}")
    try:
        result = tools.shell_tool.execute({"command": command, "description": "superask shell", "timeout": 60000})
        output = result.output
        if not output:
            print("[SA] Команда выполнена (пустой вывод)")
        else:
            print(output, end="")
    except Exception as e:
        _die(f"Ошибка выполнения: {e}")


def cmd_restart():
    """Перезапустить сервис superask"""
    if not _check_systemd():
        _die("systemd не найден. Перезапустите бота вручную.")

    token = config.get_bot_token()
    if not token:
        _e("Предупреждение: токен бота не задан. Сервис не сможет запуститься.")
        _e("Установите токен: superask bot <token>")
        if input("  Всё равно перезапустить? [y/N] ").lower() not in ("y", "yes"):
            print("[SA] Отменено.")
            return

    print("[SA] Перезапуск сервиса superask...")
    try:
        r = subprocess.run(
            ["sudo", "systemctl", "restart", "superask"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            print("[SA] Сервис перезапущен.")
            time.sleep(1)
            r2 = subprocess.run(["systemctl", "is-active", "superask"], capture_output=True, text=True, timeout=5)
            status = r2.stdout.strip()
            if status == "active":
                print("[SA] Сервис работает.")
            elif status == "activating":
                _e("Сервис запускается... (возможно, нет токена)")
            else:
                _e(f"Сервис не активен: {status}")
                _e("Проверьте логи: superask logs")
        else:
            _e(f"Не удалось перезапустить сервис (код: {r.returncode})")
            _e(f"stderr: {r.stderr}")
            _e("Попробуйте: sudo systemctl restart superask")
    except FileNotFoundError:
        _die("systemctl не найден. Установите systemd или запустите бота вручную.")
    except subprocess.TimeoutExpired:
        _die("Таймаут при перезапуске сервиса.")
    except Exception as e:
        _die(f"Ошибка: {e}")


def cmd_logs():
    """Показать логи сервиса superask"""
    if not _check_systemd():
        _die("systemd не найден. Логи недоступны.")

    print("[SA] Последние 50 строк лога:")
    print("──────────────────────────────────────────")
    try:
        r = subprocess.run(
            ["sudo", "journalctl", "-u", "superask", "-n", "50", "--no-pager", "-o", "short-monotonic"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            output = r.stdout.strip()
            if output:
                print(output)
            else:
                print("(логов нет)")
        else:
            _e(f"Ошибка получения логов: {r.stderr}")
            # Пробуем без sudo
            r2 = subprocess.run(
                ["journalctl", "-u", "superask", "-n", "50", "--no-pager"],
                capture_output=True, text=True, timeout=10
            )
            if r2.returncode == 0 and r2.stdout.strip():
                print(r2.stdout.strip())
            else:
                _e("Логи недоступны. Попробуйте: sudo journalctl -u superask -n 50")
    except FileNotFoundError:
        _die("journalctl не найден.")
    except subprocess.TimeoutExpired:
        _die("Таймаут при получении логов.")
    except Exception as e:
        _die(f"Ошибка: {e}")
    print("──────────────────────────────────────────")


def cmd_install():
    """Запустить установщик"""
    install_sh = Path(__file__).parent / "install.sh"
    if not install_sh.exists():
        _die(f"Файл install.sh не найден в {install_sh.parent}")

    print("[SA] Запуск установщика...")
    os.chmod(install_sh, 0o755)
    try:
        subprocess.run(["bash", str(install_sh)])
    except KeyboardInterrupt:
        print("\n[SA] Установка прервана.")
        sys.exit(1)
    except Exception as e:
        _die(f"Ошибка запуска установщика: {e}")


def cmd_help():
    """Показать справку"""
    print(__doc__.strip())


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print("\n[SA] Прервано пользователем.")
        sys.exit(0)
    except Exception as e:
        _die(f"Необработанная ошибка: {e}", 1)


def _main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        cmd_help()
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "bot": lambda: cmd_bot(args[0]) if args else _die("Укажите токен: superask bot <token>"),
        "userid": lambda: cmd_userid(args[0]) if args else _die("Укажите ID: superask userid <id>"),
        "model": lambda: cmd_model(args),
        "status": cmd_status,
        "wol": cmd_wol,
        "tools": cmd_tools,
        "shell": lambda: cmd_shell(" ".join(args)) if args else _die("Укажите команду: superask shell <command>"),
        "restart": cmd_restart,
        "logs": cmd_logs,
        "install": cmd_install,
        "help": cmd_help,
    }

    fn = commands.get(cmd)
    if fn:
        fn()
    else:
        _e(f"Неизвестная команда: {cmd}")
        print()
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
