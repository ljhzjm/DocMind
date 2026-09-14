import json
from typing import Any, cast


class StructuredOutputError(ValueError):
    """LLM 没有返回可解析的 JSON 对象。"""


def parse_json_object(text: str) -> dict[str, Any]:
    """从纯 JSON 或 Markdown 代码块中提取第一个 JSON 对象。"""
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < start:
        raise StructuredOutputError("response does not contain a JSON object")

    try:
        payload = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("response contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredOutputError("JSON response must be an object")
    return cast(dict[str, Any], payload)
