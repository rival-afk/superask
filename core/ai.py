"""
AI-клиент для Super ASK.
Вызывает opencode/zen API (OpenAI-compatible), управляет циклом tool calling.
"""
import json
import logging
import time
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from . import config
from . import tools

log = logging.getLogger("superask.ai")

ZEN_URL = "https://opencode.ai/zen/v1/chat/completions"

SYSTEM_PROMPT = """Ты — Super ASK, AI-агент для удалённого управления ПК через Telegram.

У тебя есть набор инструментов для работы с файловой системой, выполнения команд и поиска информации.

Правила:
1. Когда пользователь даёт задачу — используй инструменты для её выполнения.
2. Если результат работы инструмента неполный — используй дополнительные инструменты.
3. Отвечай пользователю на том же языке, на котором написан запрос.
4. Все пути к файлам должны быть абсолютными.
5. Если команда требует прав sudo — используй shell с sudo (если sudo настроен).
6. Если инструмент вернул ошибку — попробуй другой подход и сообщи пользователю.

Ты можешь выполнить несколько вызовов инструментов последовательно, если это необходимо для достижения цели."""


def _build_tool_defs() -> list[dict]:
    result = []
    for name, tool in tools.get_all_tools().items():
        tdict = tool.to_dict()
        result.append({
            "type": "function",
            "function": {
                "name": tdict["name"],
                "description": tdict["description"],
                "parameters": tdict["parameters"],
            },
        })
    return result


def _call_api(messages: list[dict]) -> dict:
    api_key = config.get_api_key()
    if not api_key:
        raise RuntimeError("API-ключ не задан. Используйте: sa apikey <ключ>")

    model = config.get_model()
    body = json.dumps({
        "model": model["model"],
        "messages": messages,
        "tools": _build_tool_defs(),
        "tool_choice": "auto",
        "max_tokens": 8192,
    }).encode()

    req = Request(
        ZEN_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SuperASK/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"API error {e.code}: {error_body}")
    except URLError as e:
        raise RuntimeError(f"API connection error: {e.reason}")


def _execute_tool(name: str, args: dict) -> str:
    tool = tools.get_tool(name)
    if not tool:
        return json.dumps({"error": f"Tool '{name}' not found"})
    try:
        result = tool.execute(args)
        return result.output if result.output else "(empty result)"
    except Exception as e:
        return json.dumps({"error": str(e)})


def process_prompt(user_text: str) -> str:
    """Send user prompt to AI, handle tool call loop, return final response."""
    start_time = time.time()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    max_rounds = 10
    for round_idx in range(max_rounds):
        log.info(f"AI round {round_idx + 1}/{max_rounds}")

        try:
            response = _call_api(messages)
        except RuntimeError as e:
            log.error(f"API call failed: {e}")
            return f"❌ Ошибка AI: {e}"

        choice = response["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason")

        if finish == "stop":
            elapsed = time.time() - start_time
            content = message.get("content", "") or ""
            log.info(f"AI ответил за {elapsed:.1f}с ({len(content)} символов)")
            return content

        if finish == "tool_calls":
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                return "❌ AI не вернул ни текста, ни вызовов инструментов."

            log.info(f"AI вызвал {len(tool_calls)} инструментов")
            messages.append({
                "role": "assistant",
                "content": message.get("content") or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                log.info(f"  → {name}({json.dumps(args)[:100]})")
                result = _execute_tool(name, args)
                log.info(f"  ← {result[:200]}...")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result[:4000],
                })

            continue

        elapsed = time.time() - start_time
        log.warning(f"Неизвестный finish_reason: {finish}")
        return message.get("content", "") or f"(finish_reason: {finish})"

    return "❌ AI превысил лимит итераций. Попробуйте упростить запрос."
