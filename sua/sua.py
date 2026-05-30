import os
import sys
import json
import hashlib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "superask"
CONFIG_FILE = CONFIG_DIR / "sua_config.json"

def ensure_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    ensure_config()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_config(cfg):
    ensure_config()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def set_password(password: str) -> bool:
    cfg = load_config()
    cfg["sudo_password_hash"] = hash_password(password)
    cfg["sudo_enabled"] = True
    save_config(cfg)
    return True

def verify_password(password: str) -> bool:
    cfg = load_config()
    stored = cfg.get("sudo_password_hash")
    if not stored:
        return False
    return stored == hash_password(password)

def is_sudo_enabled() -> bool:
    cfg = load_config()
    return cfg.get("sudo_enabled", False)

def set_sudo_enabled(enabled: bool):
    cfg = load_config()
    cfg["sudo_enabled"] = enabled
    save_config(cfg)

def get_password() -> str | None:
    cfg = load_config()
    return cfg.get("sudo_password")

def request_confirmation(command: str, caller: str = "superask") -> bool:
    print(f"[SUA] Запрос подтверждения sudo-команды:")
    print(f"  from: {caller}")
    print(f"  command: {command}")
    print(f"  [Y] Одобрить  [N] Отклонить")
    while True:
        choice = input("> ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
