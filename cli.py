#!/usr/bin/env python3
"""
Super ASK (SA) — CLI для управления системой из терминала.

Использование:
  superask bot <token>         — Установить токен Telegram-бота
  superask userid <id>         — Установить ID администратора
  superask model <op> <api> <m> — Сменить модель
  superask status              — Статус системы и сервиса
  superask wol                 — Информация Wake-on-LAN
  superask tools               — Список всех инструментов
  superask shell <cmd>         — Выполнить команду
  superask restart             — Перезапустить сервис superask
  superask logs                — Логи сервиса superask

Без аргументов — запускает Telegram-бота (foreground).
"""
import sys
import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from core import config
from core import tools
from sua import sua


def cmd_bot(token):
    config.set_bot_token(token)
    print(f"[SA] Токен бота сохранён: {token[:12]}...")
    print("[SA] Перезапустите сервис: superask restart")


def cmd_userid(uid):
    try:
        config.set_admin_user_id(int(uid))
        print(f"[SA] ID администратора сохранён: {uid}")
    except ValueError:
        print("[SA] Ошибка: ID должен быть числом")


def cmd_model(args):
    if len(args) < 3:
        print("[SA] Использование: superask model <operator> <api> <model>")
        return
    config.set_model(args[0], args[1], args[2])
    print(f"[SA] Модель изменена: {args[0]} / {args[1]} / {args[2]}")


def cmd_status():
    print("=== Super ASK ===")
    print(f"  Токен:             {'✅ задан' if config.get_bot_token() else '❌ не задан'}")
    print(f"  Админ ID:          {config.get_admin_user_id() or '❌ не задан'}")
    model = config.get_model()
    print(f"  Модель:            {model['operator']} / {model['api']} / {model['model']}")
    print(f"  Sudo:              {'✅ включён' if sua.is_sudo_enabled() else '❌ выключен'}")
    try:
        r = subprocess.run(["systemctl", "is-active", "superask"], capture_output=True, text=True)
        print(f"  Сервис superask:   {r.stdout.strip()}")
        r2 = subprocess.run(["systemctl", "is-enabled", "superask"], capture_output=True, text=True)
        print(f"  Автозагрузка:      {r2.stdout.strip()}")
    except:
        print("  Сервис:            не найден")
    print(f"\n  {len(tools.get_all_tools())} инструментов загружено")


def cmd_wol():
    mac = "8c:16:45:ff:40:15"
    print("[SA] Wake-on-LAN")
    print(f"  Интерфейс: enp2s0")
    print(f"  MAC-адрес: {mac}")
    print(f"  Статус:    {'✅ включён' if _check_wol() else '❌ выключен'}")
    print(f"  Для отправки magic packet:")
    print(f"    wakeonlan {mac}")
    print(f"  Или из Python:")
    print(f"    from wakeonlan import send_magic_packet")
    print(f"    send_magic_packet('{mac}')")


def _check_wol() -> bool:
    try:
        r = subprocess.run(["sudo", "ethtool", "enp2s0"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "Wake-on" in line and not "Supports" in line:
                return "g" in line
    except:
        pass
    return False


def cmd_tools():
    print("=== Доступные инструменты Super ASK ===")
    for name, tool in tools.get_all_tools().items():
        desc = tool.description.split("\n")[0]
        print(f"  {name:15s}  {desc}")


def cmd_shell(command: str):
    result = tools.shell_tool.execute({"command": command, "description": "cli command"})
    print(result.output)


def cmd_restart():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "superask"], check=True)
    except subprocess.CalledProcessError:
        print("[SA] Не удалось перезапустить. Попробуйте: sudo systemctl restart superask")


def cmd_logs():
    try:
        subprocess.run(["sudo", "journalctl", "-u", "superask", "-n", "50", "--no-pager"])
    except:
        print("[SA] Не удалось получить логи.")


def main():
    if len(sys.argv) < 2:
        from bot import bot
        bot.main()
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "bot": lambda: cmd_bot(args[0]) if args else print("Использование: superask bot <token>"),
        "userid": lambda: cmd_userid(args[0]) if args else print("Использование: superask userid <id>"),
        "model": lambda: cmd_model(args),
        "status": cmd_status,
        "wol": cmd_wol,
        "tools": cmd_tools,
        "shell": lambda: cmd_shell(" ".join(args)) if args else print("Использование: superask shell <command>"),
        "restart": cmd_restart,
        "logs": cmd_logs,
    }

    fn = commands.get(cmd)
    if fn:
        fn()
    else:
        print(f"[SA] Неизвестная команда: {cmd}")
        print(__doc__.strip())


if __name__ == "__main__":
    main()
