#!/usr/bin/env python3
"""
Super ASK — Local Agent
Периодически опрашивает Render-сервер на наличие задач,
выполняет их локально (команды, системные действия, конфиг, SUA),
отправляет результат обратно.

Запуск:
  export SUPERASK_SERVER=https://<app>.onrender.com
  python agent/agent.py
"""
import sys
import os
import json
import time
import logging
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

VENV_PY = PROJECT_DIR / ".venv" / "bin" / "python3"
if VENV_PY.exists() and sys.executable != str(VENV_PY):
    os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)

import requests
from core import tools
from core import config as local_config
from core.superask import SuperASK
from sua import sua

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] AGENT: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("superask.agent")

SERVER_URL = os.environ.get("SUPERASK_SERVER", "").rstrip("/")
POLL_INTERVAL = 2

sa = SuperASK()


def execute_task(task: dict) -> dict:
    task_type = task["type"]
    params = task.get("params", {})

    if task_type == "command":
        command = params.get("command", "")
        if not command:
            return {"success": False, "error": "Пустая команда"}
        result = sa.execute_command(command)
        return {"success": True, "result": result}

    if task_type == "system":
        action = params.get("action", "")
        if action == "on":
            ok = sa.start()
            return {"success": ok, "result": "Super ASK запущен" if ok else "Ошибка запуска"}
        if action == "off":
            sa.stop()
            return {"success": True, "result": "Super ASK остановлен"}
        if action == "off_session":
            sa.stop_session()
            return {"success": True, "result": "Сессия завершена"}
        if action == "off_permanent":
            sa.disable_permanently()
            return {"success": True, "result": "Super ASK отключён навсегда"}
        if action == "stop_process":
            sa.current_command = None
            return {"success": True, "result": "Процесс остановлен"}
        if action == "test":
            model = local_config.get_model()
            lines = [
                f"🤖 Super ASK — Диагностика",
                f"",
                f"📡 Модель: {model['operator']} / {model['api']} / {model['name']}",
                f"⚙️ Статус: {'🟢 Активен' if sa.running else '🔴 Остановлен'}",
                f"🛠 Инструментов: {len(tools.get_all_tools())}",
                f"",
                f"<b>SUA:</b>",
                f"{'✅ Права sudo выданы' if sua.is_sudo_enabled() else '❌ Права sudo не выданы'}",
                f"{'✅ Пароль sudo сохранён' if sua.get_sudo_password_hash() else '❌ Пароль sudo не сохранён'}",
                f"",
                f"<b>Конфигурация:</b>",
            ]
            warnings = sa.check_config_ready()
            if warnings:
                lines.extend(warnings)
            else:
                lines.append("✅ Все настройки выполнены")
            return {"success": True, "result": "\n".join(lines)}
        return {"success": False, "error": f"Неизвестное действие: {action}"}

    if task_type == "sua":
        action = params.get("action", "")
        if action == "set_password":
            pw = params.get("password", "")
            if len(pw) < 4:
                return {"success": False, "error": "Пароль должен быть минимум 4 символа"}
            sua.set_password(pw)
            return {"success": True, "result": "🔑 Пароль sudo сохранён"}
        if action == "enable":
            if not sua.get_sudo_password_hash():
                return {"success": False, "error": "Сначала сохраните пароль: /sua <пароль>"}
            sua.set_sudo_enabled(True)
            return {"success": True, "result": "🤖 Права sudo выданы"}
        if action == "disable":
            sua.set_sudo_enabled(False)
            return {"success": True, "result": "🔒 Права sudo отозваны"}
        if action == "grant":
            if not sua.get_sudo_password_hash():
                return {"success": False, "error": "Сначала сохраните пароль: /sua <пароль>"}
            sua.set_sudo_enabled(True)
            return {"success": True, "result": "🔓 Права sudo выданы"}
        return {"success": False, "error": f"Неизвестное действие SUA: {action}"}

    if task_type == "config":
        key = params.get("key", "")
        value = params.get("value")
        if key == "admin_user_id":
            local_config.set_admin_user_id(int(value))
            return {"success": True, "result": f"✅ Владелец изменён на ID {value}"}
        if key == "model":
            local_config.set_model(value["operator"], value["api"], value["name"])
            return {"success": True, "result": f"✅ Модель изменена: {value['operator']} / {value['api']} / {value['name']}"}
        if key == "bot_token":
            local_config.set_bot_token(value)
            return {"success": True, "result": "✅ Токен обновлён"}
        return {"success": False, "error": f"Неизвестный ключ: {key}"}

    return {"success": False, "error": f"Неизвестный тип задачи: {task_type}"}


def main():
    if not SERVER_URL:
        log.critical("Установите SUPERASK_SERVER")
        log.critical("  export SUPERASK_SERVER=https://my-app.onrender.com")
        sys.exit(1)

    log.info(f"Подключение к {SERVER_URL}")
    log.info("Ожидание задач...")

    while True:
        try:
            resp = requests.get(f"{SERVER_URL}/agent/task", timeout=10)
            if resp.status_code != 200:
                log.warning(f"Ошибка сервера: {resp.status_code}")
                time.sleep(POLL_INTERVAL)
                continue

            data = resp.json()
            if not data or not data.get("id"):
                time.sleep(POLL_INTERVAL)
                continue

            tid = data["id"]
            log.info(f"Задача {tid[:8]}: {data['type']} / {data.get('params', {})}")

            result = execute_task(data)

            status = "✅" if result["success"] else "❌"
            preview = (result.get("result") or result.get("error") or "")[:100]
            log.info(f"Результат: {status} {preview}...")

            resp2 = requests.post(
                f"{SERVER_URL}/agent/task/{tid}/result",
                json=result,
                timeout=10,
            )
            if resp2.status_code == 200:
                log.info(f"Результат отправлен")
            else:
                log.warning(f"Ошибка отправки: {resp2.status_code}")

        except requests.ConnectionError:
            log.warning(f"Нет соединения с {SERVER_URL}. Повтор через 10с...")
            time.sleep(10)
        except Exception as e:
            log.error(f"Ошибка: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
