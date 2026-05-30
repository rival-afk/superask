"""
Super ASK (SA) — основная логика.
Функция запуска с ядром полностью удалена согласно ТЗ.
Управление осуществляется исключительно через Telegram-бот.
"""
import os
import sys
import time
import signal
import threading
from pathlib import Path

from . import config
from . import tools
from sua import sua

CORE_DIR = Path(__file__).parent
PROJECT_DIR = CORE_DIR.parent


class SuperASK:
    def __init__(self):
        self.running = False
        self.session_active = False
        self.current_command = None
        self._stop_event = threading.Event()
        self._ping_thread = None

    def check_config_ready(self) -> list[str]:
        warnings = []
        if not config.get_bot_token():
            warnings.append("❌ Не задан токен Telegram-бота. Установите: /SA bot <токен>")
        if config.get_admin_user_id() is None:
            warnings.append("⚠️ Не задан ID администратора. Любой может управлять ботом. Установите: /SA userid <ID>")
        if not sua.is_sudo_enabled():
            warnings.append("⚠️ Права sudo не выданы. Если нужны — используйте /suaon")
        if not sua.get_sudo_password_hash():
            warnings.append("⚠️ Пароль sudo не сохранён. Если нужны sudo-команды: /sua <пароль>")
        return warnings

    def start(self) -> bool:
        self.running = True
        self.session_active = True
        self._stop_event.clear()
        self._start_ping()
        return True

    def stop(self) -> bool:
        self.running = False
        self.session_active = False
        self._stop_event.set()
        if self.current_command:
            self.current_command = None
        return True

    def stop_session(self) -> bool:
        self.session_active = False
        self._stop_event.set()
        return True

    def disable_permanently(self) -> bool:
        self.running = False
        self.session_active = False
        self._stop_event.set()
        cfg = config.load()
        cfg["permanently_disabled"] = True
        config.save(cfg)
        return True

    def is_permanently_disabled(self) -> bool:
        cfg = config.load()
        return cfg.get("permanently_disabled", False)

    def _start_ping(self):
        def ping_loop():
            counter = 0
            while not self._stop_event.is_set():
                counter += 10
                if counter <= 30:
                    print(f"[SA] ПИНГ {counter} с. SA РАБОТАЕТ")
                time.sleep(10)
        self._ping_thread = threading.Thread(target=ping_loop, daemon=True)
        self._ping_thread.start()

    def execute_command(self, command: str) -> str:
        if not self.running:
            return "[SA] Система остановлена. Используйте /on для запуска."

        command = command.strip()
        if not command:
            return "[SA] Пустая команда. Напишите что-нибудь."

        self.current_command = command

        if command.startswith("sudo "):
            if not sua.is_sudo_enabled():
                return (
                    "[SA] Права sudo не выданы. Сначала настройте SUA:\n"
                    "  1. /sua <пароль> — сохранить пароль sudo\n"
                    "  2. /suaon — выдать права sudo нейросети\n"
                    "Либо используйте команду без sudo."
                )
            if not sua.get_sudo_password_hash():
                return (
                    "[SA] Пароль sudo не сохранён в SUA.\n"
                    "  Используйте: /sua <пароль_от_sudo>\n"
                    "  Чтобы нейросеть могла выполнять sudo-команды."
                )

        result = tools.shell_tool.execute({"command": command, "description": command[:60]})
        self.current_command = None
        return result.output

    def execute_tool(self, tool_name: str, params: dict) -> str:
        if not self.running:
            return "[SA] Система остановлена."

        tool = tools.get_tool(tool_name)
        if not tool:
            available = ", ".join(tools.get_all_tools().keys())
            return f"[SA] Инструмент '{tool_name}' не найден.\nДоступны: {available}"

        if not params:
            return "[SA] Не переданы параметры для инструмента."

        result = tool.execute(params)
        return result.output
