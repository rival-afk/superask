import os
import json
import socket
import subprocess
import tempfile
from pathlib import Path

SUA_BINARY = Path.home() / ".local" / "bin" / "sua"

class SUAProxy:
    def __init__(self, bot_callback=None):
        self.bot_callback = bot_callback

    def ensure_binary(self) -> bool:
        if SUA_BINARY.exists():
            return True
        print("[SUA] Бинарный файл sua не найден. Установите sua из https://github.com/rival-afk/terminal-utils")
        return False

    def execute_with_sua(self, command: list[str], user_id: int | None = None) -> subprocess.CompletedProcess:
        if not self.ensure_binary():
            return subprocess.CompletedProcess(command, -1, b"", b"sua binary not found")

        cmd_str = " ".join(command)
        if self.bot_callback and user_id:
            confirmed = self.bot_callback(user_id, cmd_str)
            if not confirmed:
                return subprocess.CompletedProcess(command, 1, b"", b"Command denied by user")

        return subprocess.run(
            [str(SUA_BINARY), *command],
            capture_output=True, text=True
        )

    def execute_direct(self, command: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(command, capture_output=True, text=True)
