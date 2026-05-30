import json
import os
import sys
import shutil
from pathlib import Path

DEFAULT_CONFIG = {
    "bot_token": "",
    "admin_user_id": None,
    "model_operator": "opencode",
    "model_api": "zen",
    "model_name": "deepseek-v4-flash-free",
    "sudo_enabled": False,
    "session_active": False,
    "session_pid": None,
    "proxy_url": "",
    "proxy_enabled": False,
    "server_url": "",
}


def _get_config_dir() -> Path:
    if "SUPERASK_CONFIG_DIR" in os.environ:
        return Path(os.environ["SUPERASK_CONFIG_DIR"]).expanduser().resolve()
    if os.getuid() == 0:
        return Path("/etc/superask")
    return Path.home() / ".config" / "superask"


def _get_config_file() -> Path:
    if "SUPERASK_CONFIG_FILE" in os.environ:
        return Path(os.environ["SUPERASK_CONFIG_FILE"]).expanduser().resolve()
    return _get_config_dir() / "config.json"


CONFIG_DIR = _get_config_dir()
CONFIG_FILE = _get_config_file()


def ensure_config():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[SA] Ошибка: нет прав на создание {CONFIG_DIR}", file=sys.stderr)
        print(f"[SA] Попробуйте: sudo mkdir -p {CONFIG_DIR} && sudo chown $USER {CONFIG_DIR}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"[SA] Ошибка при создании {CONFIG_DIR}: {e}", file=sys.stderr)
        sys.exit(1)


def load() -> dict:
    ensure_config()
    if CONFIG_FILE.exists():
        try:
            raw = CONFIG_FILE.read_text().strip()
            if not raw:
                return dict(DEFAULT_CONFIG)
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[SA] Предупреждение: config.json повреждён ({e}). Используются настройки по умолчанию.", file=sys.stderr)
            backup = CONFIG_FILE.with_suffix(".json.bak")
            try:
                shutil.copy2(CONFIG_FILE, backup)
                print(f"[SA] Создана резервная копия: {backup}", file=sys.stderr)
            except OSError:
                pass
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save(cfg: dict):
    ensure_config()
    for key in DEFAULT_CONFIG:
        if key not in cfg:
            cfg[key] = DEFAULT_CONFIG[key]
    try:
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        tmp.replace(CONFIG_FILE)
    except PermissionError:
        print(f"[SA] Ошибка: нет прав на запись {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"[SA] Ошибка при сохранении {CONFIG_FILE}: {e}", file=sys.stderr)
        sys.exit(1)


def get(key: str, default=None):
    return load().get(key, default)


def set_key(key: str, value):
    if key not in DEFAULT_CONFIG:
        print(f"[SA] Предупреждение: неизвестный ключ конфига '{key}'", file=sys.stderr)
    cfg = load()
    cfg[key] = value
    save(cfg)


def validate_token(token: str) -> bool:
    if not token or len(token) < 10:
        return False
    if not ":" in token:
        return False
    parts = token.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False
    return True


def set_admin_user_id(tg_id: int):
    if not isinstance(tg_id, int) or tg_id <= 0:
        print("[SA] Ошибка: ID пользователя должен быть положительным числом", file=sys.stderr)
        return
    set_key("admin_user_id", tg_id)


def get_admin_user_id():
    return get("admin_user_id")


def set_bot_token(token: str):
    token = token.strip().strip("\"'")
    if not validate_token(token):
        print("[SA] Ошибка: токен бота невалиден. Должен быть формата 123456:ABCdef...", file=sys.stderr)
        return
    set_key("bot_token", token)


def get_bot_token():
    return get("bot_token")


def set_model(operator: str, api: str, model: str):
    operator = operator.strip()
    api = api.strip()
    model = model.strip()
    if not operator or not api or not model:
        print("[SA] Ошибка: operator, api и model не могут быть пустыми", file=sys.stderr)
        return
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


def validate_proxy(url: str) -> bool:
    if not url:
        return True
    url = url.strip()
    if not url.startswith(("http://", "https://", "socks5://", "socks5h://")):
        return False
    return True


def set_proxy(url: str):
    url = url.strip().strip("\"'")
    if not validate_proxy(url):
        print("[SA] Ошибка: URL прокси должен начинаться с http://, https://, socks5:// или socks5h://", file=sys.stderr)
        return
    cfg = load()
    cfg["proxy_url"] = url
    cfg["proxy_enabled"] = True
    save(cfg)


def get_proxy() -> str:
    cfg = load()
    if cfg.get("proxy_enabled"):
        return cfg.get("proxy_url", "")
    return ""


def clear_proxy():
    cfg = load()
    cfg["proxy_url"] = ""
    cfg["proxy_enabled"] = False
    save(cfg)


def set_server_url(url: str):
    url = url.strip().strip("\"'").rstrip("/")
    if not url.startswith("http"):
        print("[SA] URL должен начинаться с http:// или https://", file=sys.stderr)
        return
    cfg = load()
    cfg["server_url"] = url
    save(cfg)


def get_server_url() -> str:
    cfg = load()
    return cfg.get("server_url", "")
