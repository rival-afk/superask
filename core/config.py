import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "superask"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "bot_token": "",
    "admin_user_id": None,
    "model_operator": "opencode",
    "model_api": "zen",
    "model_name": "deepseek-v4-flash-free",
    "sudo_enabled": False,
    "session_active": False,
    "session_pid": None,
}

def ensure_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load() -> dict:
    ensure_config()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def save(cfg: dict):
    ensure_config()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def get(key: str, default=None):
    return load().get(key, default)

def set_key(key: str, value):
    cfg = load()
    cfg[key] = value
    save(cfg)

def set_admin_user_id(tg_id: int):
    set_key("admin_user_id", tg_id)

def get_admin_user_id():
    return get("admin_user_id")

def set_bot_token(token: str):
    set_key("bot_token", token)

def get_bot_token():
    return get("bot_token")

def set_model(operator: str, api: str, model: str):
    cfg = load()
    cfg["model_operator"] = operator
    cfg["model_api"] = api
    cfg["model_name"] = model
    save(cfg)

def get_model() -> dict:
    cfg = load()
    return {
        "operator": cfg.get("model_operator", "opencode"),
        "api": cfg.get("model_api", "zen"),
        "model": cfg.get("model_name", "deepseek-v4-flash-free"),
    }
