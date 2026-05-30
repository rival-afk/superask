"""
Инструменты Super ASK, основанные на структуре opencode.
https://github.com/anomalyco/opencode.git

Полный набор tools из packages/opencode/src/tool/:
shell, read, write, edit, glob, grep,
webfetch, websearch, task, question, todowrite, apply_patch, skill
"""
import subprocess
import json
import os
import difflib
import shutil
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Callable
from datetime import datetime


class ToolResult:
    def __init__(self, output: str, title: str = "", metadata: dict | None = None):
        self.output = output
        self.title = title
        self.metadata = metadata or {}


class Tool:
    def __init__(self, name: str, description: str, parameters: dict, fn: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn

    def execute(self, args: dict) -> ToolResult:
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


def _run_shell(cmd: str, timeout: int = 60, workdir: str | None = None) -> str:
    if not cmd or not cmd.strip():
        return "[error] Пустая команда"

    if not isinstance(timeout, (int, float)) or timeout <= 0:
        timeout = 60
    if timeout > 3600:
        return "[error] Таймаут не может превышать 3600 секунд (1 час)"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=workdir,
        )
        output = result.stdout or ""
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return f"[timeout] Команда превысила лимит {timeout}с"
    except PermissionError:
        return "[error] Нет прав на выполнение команды"
    except FileNotFoundError:
        return "[error] Команда не найдена"
    except OSError as e:
        return f"[error] Системная ошибка: {e}"
    except Exception as e:
        return f"[error] {e}"


# ── shell ──────────────────────────────────────────────────────────────
def shell_execute(command: str, description: str = "", workdir: str | None = None, timeout: int = 60000) -> ToolResult:
    if not command or not command.strip():
        return ToolResult("[error] Пустая команда")

    if timeout and timeout > 0:
        timeout_sec = timeout / 1000
    else:
        timeout_sec = 60

    output = _run_shell(command, timeout_sec, workdir)
    return ToolResult(output, title=description or command[:60])


shell_tool = Tool(
    name="shell",
    description="Выполнить команду в терминале. Возвращает stdout, stderr и код возврата. Обязательно указывайте description с кратким пояснением что делает команда.",
    parameters={
        "command": {"type": "string", "description": "Команда для выполнения в shell"},
        "description": {"type": "string", "description": "Краткое описание (3-10 слов) что делает эта команда"},
        "workdir": {"type": "string", "description": "Рабочая директория (опционально)"},
        "timeout": {"type": "integer", "description": "Таймаут в миллисекундах", "default": 60000},
    },
    fn=shell_execute,
)

# ── read ───────────────────────────────────────────────────────────────
def read_file(filePath: str, offset: int = 0, limit: int | None = None) -> ToolResult:
    if not filePath or not filePath.strip():
        return ToolResult("[error] Укажите путь к файлу")

    try:
        p = Path(filePath).expanduser().resolve()
    except RuntimeError:
        return ToolResult(f"[error] Некорректный путь: {filePath}")

    if not p.exists():
        return ToolResult(f"[error] Файл не найден: {p}")
    if not p.is_file():
        return ToolResult(f"[error] Не является файлом: {p}")

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return ToolResult(f"[error] Нет прав на чтение: {p}")
    except OSError as e:
        return ToolResult(f"[error] Ошибка чтения {p}: {e}")

    total_lines = content.count("\n") + 1

    if offset > 0:
        lines = content.splitlines()
        if offset > len(lines):
            return ToolResult(f"[error] Строка {offset} больше общего числа строк ({total_lines})")
        content = "\n".join(lines[offset - 1:])

    if limit and limit > 0:
        lines = content.splitlines()
        if limit < len(lines):
            content = "\n".join(lines[:limit]) + f"\n... [показано {limit} из {len(lines)} строк]"

    return ToolResult(content, title=str(p), metadata={"lines": total_lines})


read_tool = Tool(
    name="read",
    description="Прочитать содержимое файла. Полезно для просмотра кода, конфигов, логов.",
    parameters={
        "filePath": {"type": "string", "description": "Абсолютный путь к файлу"},
        "offset": {"type": "integer", "description": "Начать чтение с этой строки (1-индексировано)"},
        "limit": {"type": "integer", "description": "Максимальное количество строк"},
    },
    fn=read_file,
)

# ── write ──────────────────────────────────────────────────────────────
def write_file(filePath: str, content: str) -> ToolResult:
    if not filePath or not filePath.strip():
        return ToolResult("[error] Укажите путь к файлу")
    if content is None:
        return ToolResult("[error] Содержимое файла не может быть None")

    try:
        p = Path(filePath).expanduser().resolve()
    except RuntimeError:
        return ToolResult(f"[error] Некорректный путь: {filePath}")

    if p.exists() and not p.is_file():
        return ToolResult(f"[error] Путь существует и не является файлом: {p}")

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return ToolResult(f"[error] Нет прав на создание директории: {p.parent}")

    old_content = ""
    if p.exists():
        try:
            old_content = p.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError):
            old_content = ""

    try:
        p.write_text(content, encoding="utf-8")
    except PermissionError:
        return ToolResult(f"[error] Нет прав на запись: {p}")
    except IsADirectoryError:
        return ToolResult(f"[error] {p} является директорией")
    except OSError as e:
        return ToolResult(f"[error] Ошибка записи {p}: {e}")

    diff = ""
    if old_content:
        try:
            diff = "".join(difflib.unified_diff(
                old_content.splitlines(True), content.splitlines(True),
                fromfile=str(p), tofile=str(p)
            ))
        except:
            pass

    return ToolResult("Wrote file successfully.", title=str(p), metadata={"diff": diff})


write_tool = Tool(
    name="write",
    description="Записать содержимое в файл. Путь должен быть абсолютным.",
    parameters={
        "filePath": {"type": "string", "description": "Абсолютный путь к файлу для записи"},
        "content": {"type": "string", "description": "Содержимое файла"},
    },
    fn=write_file,
)

# ── edit ───────────────────────────────────────────────────────────────
def edit_file(filePath: str, oldString: str, newString: str, replaceAll: bool = False) -> ToolResult:
    if not filePath or not filePath.strip():
        return ToolResult("[error] Укажите путь к файлу")

    try:
        p = Path(filePath).expanduser().resolve()
    except RuntimeError:
        return ToolResult(f"[error] Некорректный путь: {filePath}")

    if not p.exists():
        return ToolResult(f"[error] Файл не найден: {filePath}")
    if not p.is_file():
        return ToolResult(f"[error] Не является файлом: {filePath}")

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return ToolResult(f"[error] Нет прав на чтение: {p}")
    except OSError as e:
        return ToolResult(f"[error] Ошибка чтения {p}: {e}")

    if not oldString:
        new_content = (newString + "\n" + content) if not content.endswith("\n") else (newString + "\n" + content)
    elif replaceAll:
        if oldString not in content:
            return ToolResult("[error] Строка для замены не найдена в файле")
        new_content = content.replace(oldString, newString)
    else:
        count = content.count(oldString)
        if count == 0:
            return ToolResult("[error] Строка для замены не найдена в файле")
        if count > 1:
            return ToolResult(f"[error] Найдено {count} вхождений. Добавьте больше контекста в oldString или используйте replaceAll=true")
        new_content = content.replace(oldString, newString, 1)

    if content == new_content:
        return ToolResult("[warn] Замена не изменила содержимое файла. oldString и newString совпадают?")

    try:
        p.write_text(new_content, encoding="utf-8")
    except PermissionError:
        return ToolResult(f"[error] Нет прав на запись: {p}")
    except OSError as e:
        return ToolResult(f"[error] Ошибка записи {p}: {e}")

    diff = ""
    try:
        diff = "".join(difflib.unified_diff(
            content.splitlines(True), new_content.splitlines(True),
            fromfile=str(p), tofile=str(p)
        ))
    except:
        pass

    return ToolResult("Edit applied successfully.", title=str(p), metadata={"diff": diff})


edit_tool = Tool(
    name="edit",
    description="Заменить текст в файле. Для точного совпадения используйте окружающий контекст в oldString.",
    parameters={
        "filePath": {"type": "string", "description": "Абсолютный путь к файлу"},
        "oldString": {"type": "string", "description": "Текст для замены (с окружающим контекстом для уникальности)"},
        "newString": {"type": "string", "description": "Новый текст (должен отличаться от oldString)"},
        "replaceAll": {"type": "boolean", "description": "Заменить все вхождения (по умолчанию false)"},
    },
    fn=edit_file,
)

# ── glob ───────────────────────────────────────────────────────────────
def glob_search(pattern: str, path: str = ".") -> ToolResult:
    matches = list(Path(path).expanduser().rglob(pattern))
    if not matches:
        return ToolResult("[empty] Нет совпадений")
    matches = sorted(matches, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    result = "\n".join(str(m) for m in matches)
    return ToolResult(result, title=f"Found {len(matches)} file(s)")


glob_tool = Tool(
    name="glob",
    description="Поиск файлов по glob-шаблону. Возвращает отсортированные по времени изменения.",
    parameters={
        "pattern": {"type": "string", "description": "Glob-шаблон (напр. **/*.py, src/**/*.ts)"},
        "path": {"type": "string", "description": "Директория для поиска (по умолчанию текущая)"},
    },
    fn=glob_search,
)

# ── grep ───────────────────────────────────────────────────────────────
def grep_search(pattern: str, path: str = ".", include: str | None = None) -> ToolResult:
    try:
        cmd = ["grep", "-rn", "-e", pattern, path]
        if include:
            for ext in include.split(","):
                ext = ext.strip()
                if ext.startswith("*."):
                    cmd = ["grep", "-rn", f"--include={ext}", "-e", pattern, path]
                else:
                    cmd = ["grep", "-rn", f"--include=*.{ext}", "-e", pattern, path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            return ToolResult(result.stdout, title=f"Found {len(lines)} match(es)")
        return ToolResult("[empty] Нет совпадений")
    except subprocess.TimeoutExpired:
        return ToolResult("[timeout] Поиск превысил 30с")
    except Exception as e:
        return ToolResult(f"[error] {e}")


grep_tool = Tool(
    name="grep",
    description="Поиск текста в файлах с помощью regex. Поддерживает фильтрацию по расширениям.",
    parameters={
        "pattern": {"type": "string", "description": "Регулярное выражение для поиска"},
        "path": {"type": "string", "description": "Путь для поиска"},
        "include": {"type": "string", "description": "Расширения файлов через запятую (напр. py,ts,js)"},
    },
    fn=grep_search,
)

# ── webfetch ───────────────────────────────────────────────────────────
def webfetch_fetch(url: str, format: str = "markdown", timeout: int = 30) -> ToolResult:
    if not url or not url.strip():
        return ToolResult("[error] Укажите URL")

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return ToolResult(f"[error] URL должен начинаться с http:// или https://")

    if timeout < 1:
        timeout = 30
    if timeout > 120:
        timeout = 120

    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SuperASK/1.0 (Telegram bot; +https://github.com/youcapybara228-svg/superask)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        if format == "text":
            import re
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()
        elif format == "html":
            pass
        else:
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.body_width = 0
                content = h.handle(content)
            except ImportError:
                pass

        if len(content) > 50000:
            content = content[:50000] + "\n\n... [вывод обрезан до 50000 символов]"

        return ToolResult(content, title=f"Fetched {url[:80]}...")
    except urllib.error.HTTPError as e:
        return ToolResult(f"[error] HTTP {e.code}: {e.reason} для {url}")
    except urllib.error.URLError as e:
        return ToolResult(f"[error] Не удалось подключиться к {url}: {e.reason}")
    except ValueError:
        return ToolResult(f"[error] Некорректный URL: {url}")
    except OSError as e:
        return ToolResult(f"[error] Сетевая ошибка: {e}")
    except Exception as e:
        return ToolResult(f"[error] {e}")


webfetch_tool = Tool(
    name="webfetch",
    description="Загрузить содержимое URL. Поддерживает text, markdown, html форматы.",
    parameters={
        "url": {"type": "string", "description": "URL для загрузки"},
        "format": {"type": "string", "description": "Формат: text, markdown, html (по умолчанию markdown)"},
        "timeout": {"type": "integer", "description": "Таймаут в секундах (макс 120)"},
    },
    fn=webfetch_fetch,
)

# ── websearch ──────────────────────────────────────────────────────────
def websearch_search(query: str, numResults: int = 8) -> ToolResult:
    try:
        import urllib.parse, urllib.request, json
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "SuperASK/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        import re
        results = []
        for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL):
            link = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            results.append(f"{title}\n  {link}")
            if len(results) >= numResults:
                break

        if not results:
            for m in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
                link = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if "duckduckgo" not in link:
                    results.append(f"{title}\n  {link}")
                    if len(results) >= numResults:
                        break

        output = "\n\n".join(results) if results else "[empty] Нет результатов поиска"
        return ToolResult(output, title=f"Search results for: {query}", metadata={"provider": "duckduckgo"})
    except Exception as e:
        return ToolResult(f"[error] Поиск не удался: {e}")


websearch_tool = Tool(
    name="websearch",
    description="Поиск в интернете. Используется для получения актуальной информации.",
    parameters={
        "query": {"type": "string", "description": "Поисковый запрос"},
        "numResults": {"type": "integer", "description": "Количество результатов (по умолчанию 8)"},
    },
    fn=websearch_search,
)

# ── task (subagent) ────────────────────────────────────────────────────
_todo_store: list[dict] = []

def task_execute(description: str, prompt: str, subagent_type: str = "general", background: bool = False) -> ToolResult:
    if background:
        import threading
        t = threading.Thread(target=lambda: _run_task(description, prompt, subagent_type), daemon=True)
        t.start()
        return ToolResult(f"[background] Задача '{description}' запущена в фоне.")

    result = _run_task(description, prompt, subagent_type)
    return ToolResult(f"<task state=\"completed\">\n{result}\n</task>", title=description)


def _run_task(description: str, prompt: str, subagent_type: str) -> str:
    import sys
    script_path = Path(sys.argv[0]).parent if not getattr(sys, 'frozen', False) else Path(sys.executable).parent
    tool_outputs = []
    for tool_name, tool in BUILTIN_TOOLS.items():
        tool_outputs.append(f"- {tool.name}: {tool.description}")

    system_prompt = f"""Ты — вспомогательный агент Super ASK.
Твоя задача: {description}
Доступные инструменты:
{chr(10).join(tool_outputs)}

Ответь подробно на задачу выше."""

    full_prompt = f"{system_prompt}\n\n{prompt}"
    print(f"[SA] Task '{description}' started")

    lines = prompt.split("\n")
    combined = []
    for line in lines:
        if line.startswith("!"):
            cmd = line[1:].strip()
            output = _run_shell(cmd)
            combined.append(f"$ {cmd}\n{output}")
        else:
            combined.append(line)

    return "\n".join(combined)


task_tool = Tool(
    name="task",
    description="Запустить подзадачу для выполнения отдельным агентом. Используйте для сложных многошаговых задач.",
    parameters={
        "description": {"type": "string", "description": "Краткое описание задачи (3-5 слов)"},
        "prompt": {"type": "string", "description": "Полное описание задачи для агента"},
        "subagent_type": {"type": "string", "description": "Тип агента: general, explore"},
        "background": {"type": "boolean", "description": "Запустить в фоне"},
    },
    fn=task_execute,
)

# ── question ───────────────────────────────────────────────────────────
def question_ask(questions: list[dict]) -> ToolResult:
    answers = []
    for i, q in enumerate(questions):
        question_text = q.get("question", "Вопрос")
        header = q.get("header", "")
        options = q.get("options", [])

        print(f"\n[{i+1}/{len(questions)}] {question_text}")
        if header:
            print(f"    ({header})")

        if options:
            for j, opt in enumerate(options):
                label = opt.get("label", str(j))
                desc = opt.get("description", "")
                print(f"  {j+1}. {label}")
                if desc:
                    print(f"     {desc}")
            choice = input("  Ваш выбор (номер или текст): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    answers.append({"question": question_text, "answer": options[idx]["label"]})
                else:
                    answers.append({"question": question_text, "answer": choice})
            except ValueError:
                answers.append({"question": question_text, "answer": choice})
        else:
            ans = input("  Ответ: ").strip()
            answers.append({"question": question_text, "answer": ans})

    formatted = "; ".join(f"\"{a['question'][:50]}...\" = \"{a['answer']}\"" for a in answers)
    output = f"User has answered your questions: {formatted}. You can now continue with the user's answers in mind."
    return ToolResult(output, title=f"Asked {len(questions)} question(s)", metadata={"answers": answers})


question_tool = Tool(
    name="question",
    description="Задать вопрос пользователю. Используйте когда нужно получить решение или уточнение.",
    parameters={
        "questions": {
            "type": "array",
            "description": "Список вопросов",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "header": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
    fn=question_ask,
)

# ── todowrite ──────────────────────────────────────────────────────────
def todo_write(todos: list[dict]) -> ToolResult:
    global _todo_store
    _todo_store = todos
    output = json.dumps(todos, indent=2, ensure_ascii=False)
    pending = sum(1 for t in todos if t.get("status") == "pending")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    completed = sum(1 for t in todos if t.get("status") == "completed")
    return ToolResult(
        output,
        title=f"{len(todos)} todos (📋 {pending} | ▶ {in_progress} | ✅ {completed})",
        metadata={"todos": todos},
    )


todowrite_tool = Tool(
    name="todowrite",
    description="Создать и поддерживать структурированный список задач. Отслеживает прогресс, организует многошаговую работу.",
    parameters={
        "todos": {
            "type": "array",
            "description": "Обновлённый список задач",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Краткое описание задачи"},
                    "status": {"type": "string", "description": "Статус: pending, in_progress, completed, cancelled"},
                    "priority": {"type": "string", "description": "Приоритет: high, medium, low"},
                },
            },
        },
    },
    fn=todo_write,
)

# ── apply_patch ────────────────────────────────────────────────────────
def apply_patch(patchText: str) -> ToolResult:
    if not patchText or not patchText.strip():
        return ToolResult("[error] Пустой патч")

    import tempfile
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False, encoding="utf-8")
        tmp.write(patchText)
        tmp.close()

        if not shutil.which("patch"):
            return ToolResult("[error] Утилита 'patch' не найдена. Установите: sudo pacman -S patch")

        result = subprocess.run(
            ["patch", "-p0", "-i", tmp.name],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout or ""
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
            return ToolResult(output, title="Patch failed")
        return ToolResult(output, title="Patch applied")
    except subprocess.TimeoutExpired:
        return ToolResult("[timeout] Применение патча превысило 30с")
    except FileNotFoundError:
        return ToolResult("[error] patch не найден")
    except Exception as e:
        return ToolResult(f"[error] {e}")
    finally:
        if tmp and os.path.exists(tmp.name):
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


apply_patch_tool = Tool(
    name="apply_patch",
    description="Применить патч к файлам. Патч должен быть в формате unified diff.",
    parameters={
        "patchText": {"type": "string", "description": "Полный текст патча со всеми изменениями"},
    },
    fn=apply_patch,
)

# ── skill ──────────────────────────────────────────────────────────────
SKILLS_DIR = Path(__file__).parent.parent / "skills"

def skill_load(name: str) -> ToolResult:
    if not name or not name.strip():
        return ToolResult("[error] Укажите имя скилла")

    name = name.strip()

    skill_file = SKILLS_DIR / f"{name}.md"
    if not skill_file.exists():
        skill_file = SKILLS_DIR / f"{name}.txt"
    if not skill_file.exists():
        available = []
        if SKILLS_DIR.exists():
            try:
                available = sorted(p.stem for p in SKILLS_DIR.glob("*.md"))
                available.extend(sorted(p.stem for p in SKILLS_DIR.glob("*.txt")))
            except OSError:
                pass

        if available:
            return ToolResult(f"[error] Скилл '{name}' не найден. Доступны: {', '.join(available)}")
        return ToolResult(f"[error] Скилл '{name}' не найден. Нет доступных скиллов.\n"
                          f"Создайте файл {SKILLS_DIR / name}.md с инструкциями.")

    try:
        content = skill_file.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return ToolResult(f"[error] Нет прав на чтение скилла: {skill_file}")
    except OSError as e:
        return ToolResult(f"[error] Ошибка чтения скилла: {e}")

    if not content.strip():
        return ToolResult(f"[warn] Скилл '{name}' пуст")

    return ToolResult(
        f"<skill_content name=\"{name}\">\n{content}\n</skill_content>",
        title=f"Loaded skill: {name}",
        metadata={"name": name},
    )


skill_tool = Tool(
    name="skill",
    description="Загрузить специализированный скилл с доменными инструкциями. Используйте когда задача соответствует одному из доступных скиллов.",
    parameters={
        "name": {"type": "string", "description": "Имя скилла из available_skills"},
    },
    fn=skill_load,
)

# ── registry ───────────────────────────────────────────────────────────
BUILTIN_TOOLS: dict[str, Tool] = {
    "shell": shell_tool,
    "read": read_tool,
    "write": write_tool,
    "edit": edit_tool,
    "glob": glob_tool,
    "grep": grep_tool,
    "webfetch": webfetch_tool,
    "websearch": websearch_tool,
    "task": task_tool,
    "question": question_tool,
    "todowrite": todowrite_tool,
    "apply_patch": apply_patch_tool,
    "skill": skill_tool,
}


def get_all_tools() -> dict[str, Tool]:
    return dict(BUILTIN_TOOLS)


def get_tool(name: str) -> Tool | None:
    return BUILTIN_TOOLS.get(name)


def get_tool_list() -> str:
    return "\n".join(f"  {t.name:15s} — {t.description.split(chr(10))[0]}" for t in BUILTIN_TOOLS.values())
