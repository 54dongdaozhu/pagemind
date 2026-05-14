import json


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
