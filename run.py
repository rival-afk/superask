#!/usr/bin/env python3
"""
Super ASK (SA) — система удалённого управления ПК через Telegram-бота.
Основана на наборе инструментов opencode.

Использование:
  python run.py              # Запуск Telegram-бота
  python run.py --setup      # Первоначальная настройка
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import config
from bot import bot


def setup():
    print("=== Super ASK — Настройка ===")
    token = input("Telegram Bot Token: ").strip()
    if token:
        config.set_bot_token(token)
    uid = input("Telegram Admin User ID (оставьте пустым для текущего): ").strip()
    if uid:
        try:
            config.set_admin_user_id(int(uid))
        except ValueError:
            print("ID должен быть числом")
    print("Настройка завершена. Запустите: python run.py")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    else:
        bot.main()
