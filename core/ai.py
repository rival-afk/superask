"""
AI-клиент для Super ASK.
Вызывает opencode/zen API (OpenAI-compatible), управляет циклом tool calling.
"""
import json
import logging
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from . import config
from . import tools

log = logging.getLogger("superask.ai")

ZEN_URL = "https://opencode.ai/zen/v1/chat/completions"

SYSTEM_PROMPT = """Ты — Super ASK, AI-агент для удалённого управления ПК через Telegram.
Твой пользователь — владелец ПК. Отвечай на том же языке, что и запрос.

Доступные инструменты (opencode):
- shell — выполнить любую shell-команду
- read — прочитать файл
- write — записать файл
- edit — отредактировать файл (замена текста)
- glob — поиск файлов по шаблону
- grep — поиск текста в файлах
- webfetch — загрузить URL
- websearch — поиск в интернете
- task — запустить подзадачу
- question — задать вопрос пользователю
- todowrite — управлять списком задач
- apply_patch — применить патч
- skill — загрузить инструкции

Правила:
1. Для любой задачи используй инструменты. Не предлагай пользователю сделать что-то вручную.
2. Если не уверен в пути — используй glob/grep для поиска.
3. Для проверки sudo используй: shell("sudo -n true && echo sudo_ok || echo sudo_fail")
4. Для long-running команд добавляй timeout (по умолчанию 60000ms).
5. После выполнения инструментов проанализируй результат и дай понятный ответ пользователю.
6. Если инструмент вернул ошибку — попробуй другой подход.

Ты можешь вызывать несколько инструментов последовательно."""


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
        "max_tokens": 12288,
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
        with urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"API error {e.code}: {error_body}")
    except URLError as e:
        raise RuntimeError(f"API connection error: {e.reason}")


def _execute_tool(name: str, args: dict) -> tuple[str, str]:
    """Execute tool, return (result_summary, full_output)."""
    tool = tools.get_tool(name)
    if not tool:
        return "", json.dumps({"error": f"Tool '{name}' not found"})
    try:
        result = tool.execute(args)
        output = result.output if result.output else "(empty result)"
        summary = output[:200].replace("\n", " ").strip()
        return summary, output
    except Exception as e:
        return str(e), json.dumps({"error": str(e)})


def process_prompt(user_text: str, context: list[dict] = None) -> dict:
    """
    Send user prompt to AI, handle tool call loop.
    Returns: {
        "response": str — финальный ответ AI,
        "tool_log": str — лог выполненных инструментов,
        "rounds": int — количество раундов tool calling
    }
    """
    start_time = time.time()
    tool_log: list[str] = []

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if context:
        # Keep system prompt, add context messages (skip old system messages)
        for m in context:
            if m.get("role") != "system" and m not in messages:
                messages.append(m)
    messages.append({"role": "user", "content": user_text})

    max_rounds = 15
    for round_idx in range(max_rounds):
        log.info(f"AI round {round_idx + 1}/{max_rounds}")

        try:
            response = _call_api(messages)
        except RuntimeError as e:
            log.error(f"API call failed: {e}")
            elapsed = time.time() - start_time
            return {
                "response": f"❌ Ошибка AI: {e}",
                "tool_log": "\n".join(tool_log),
                "rounds": round_idx,
                "elapsed": elapsed,
            }

        choice = response["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason")

        if finish == "stop":
            elapsed = time.time() - start_time
            content = message.get("content", "") or ""
            log.info(f"AI ответил за {elapsed:.1f}с ({len(content)} символов)")
            return {
                "response": content,
                "tool_log": "\n".join(tool_log),
                "rounds": round_idx + 1,
                "elapsed": elapsed,
            }

        if finish == "tool_calls":
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                elapsed = time.time() - start_time
                return {
                    "response": "❌ AI не вернул ни текста, ни вызовов инструментов.",
                    "tool_log": "\n".join(tool_log),
                    "rounds": round_idx + 1,
                    "elapsed": elapsed,
                }

            log.info(f"AI вызвал {len(tool_calls)} инструментов")
            assistant_msg = {
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
            }
            messages.append(assistant_msg)

            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                log.info(f"  → {name}({json.dumps(args)[:100]})")
                summary, output = _execute_tool(name, args)
                log.info(f"  ← {summary[:200]}")

                tool_log.append(f"➜ {name}({json.dumps(args)[:200]})")
                tool_log.append(f"  {summary[:300]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": output[:6000],
                })

            continue

        elapsed = time.time() - start_time
        log.warning(f"Неизвестный finish_reason: {finish}")
        return {
            "response": message.get("content", "") or f"(finish_reason: {finish})",
            "tool_log": "\n".join(tool_log),
            "rounds": round_idx + 1,
            "elapsed": elapsed,
        }

    elapsed = time.time() - start_time
    return {
        "response": "❌ AI превысил лимит итераций. Попробуйте упростить запрос.",
        "tool_log": "\n".join(tool_log),
        "rounds": max_rounds,
        "elapsed": elapsed,
    }
