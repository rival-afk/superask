"""
Инструменты Super ASK, основанные на структуре opencode.
https://github.com/anomalyco/opencode.git

Каждый инструмент — это функция с описанием и JSON-схемой параметров,
как в opencode packages/opencode/src/tool/.
"""
import subprocess
import json
from pathlib import Path
from typing import Any


class Tool:
    def __init__(self, name: str, description: str, parameters: dict, fn: callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn

    def execute(self, args: dict) -> str:
        return self.fn(**args)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
            },
        }


def shell_execute(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return f"[timeout] Команда превысила лимит {timeout}с"
    except Exception as e:
        return f"[error] {e}"


shell_tool = Tool(
    name="shell",
    description="Выполнить команду в терминале Linux. Возвращает stdout, stderr и код возврата.",
    parameters={
        "command": {"type": "string", "description": "Команда для выполнения"},
        "timeout": {"type": "integer", "description": "Таймаут в секундах", "default": 30},
    },
    fn=shell_execute,
)


def read_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"[error] Файл не найден: {path}"
    return p.read_text()


read_tool = Tool(
    name="read",
    description="Прочитать содержимое файла.",
    parameters={
        "path": {"type": "string", "description": "Путь к файлу"},
    },
    fn=read_file,
)


def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"[ok] Файл записан: {path}"


write_tool = Tool(
    name="write",
    description="Записать содержимое в файл.",
    parameters={
        "path": {"type": "string", "description": "Путь к файлу"},
        "content": {"type": "string", "description": "Содержимое файла"},
    },
    fn=write_file,
)


def glob_search(pattern: str) -> str:
    from pathlib import Path
    matches = list(Path.cwd().glob(pattern))
    if not matches:
        return "[empty] Нет совпадений"
    return "\n".join(str(m) for m in matches)


glob_tool = Tool(
    name="glob",
    description="Поиск файлов по glob-шаблону.",
    parameters={
        "pattern": {"type": "string", "description": "Glob-шаблон (напр. **/*.py)"},
    },
    fn=glob_search,
)


def grep_search(pattern: str, path: str = ".") -> str:
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.js", "--include=*.ts",
             "--include=*.html", "--include=*.md", "--include=*.json",
             "-e", pattern, path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout
        return "[empty] Нет совпадений"
    except Exception as e:
        return f"[error] {e}"


grep_tool = Tool(
    name="grep",
    description="Поиск текста в файлах проекта.",
    parameters={
        "pattern": {"type": "string", "description": "Регулярное выражение для поиска"},
        "path": {"type": "string", "description": "Путь для поиска (по умолчанию .)"},
    },
    fn=grep_search,
)


def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"[error] Файл не найден: {path}"
    content = p.read_text()
    if old_string not in content:
        return "[error] Строка для замены не найдена"
    new_content = content.replace(old_string, new_string, 1)
    p.write_text(new_content)
    return f"[ok] Замена выполнена в {path}"


edit_tool = Tool(
    name="edit",
    description="Заменить текст в файле (одно вхождение).",
    parameters={
        "path": {"type": "string", "description": "Путь к файлу"},
        "old_string": {"type": "string", "description": "Текст для замены"},
        "new_string": {"type": "string", "description": "Новый текст"},
    },
    fn=edit_file,
)


BUILTIN_TOOLS = {
    "shell": shell_tool,
    "read": read_tool,
    "write": write_tool,
    "glob": glob_tool,
    "grep": grep_tool,
    "edit": edit_tool,
}


def get_all_tools() -> dict[str, Tool]:
    return dict(BUILTIN_TOOLS)


def get_tool(name: str) -> Tool | None:
    return BUILTIN_TOOLS.get(name)
