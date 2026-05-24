import json


def sanitize_history(history) -> list[dict[str, str]]:
    cleaned = []
    for item in history[-20:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:800]})
    total = sum(len(m["content"]) for m in cleaned)
    while total > 4000 and cleaned:
        total -= len(cleaned.pop(0)["content"])
    return cleaned


def format_history(history: list[dict[str, str]]) -> str:
    history = sanitize_history(history)
    if not history:
        return "无"
    role_names = {"user": "用户", "assistant": "助手"}
    return "\n".join(f"{role_names[item['role']]}：{item['content']}" for item in history)


def ensure_keys(data: dict, defaults: dict) -> dict:
    for key, default in defaults.items():
        if data.get(key) is None:
            data[key] = default
    return data


def safe_parse_json(content: str) -> dict:
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(content[start:end + 1])
        raise
