import json
import re


def safe_parse_json(text: str) -> dict | list | None:
    """Extract and parse JSON from LLM output, tolerating markdown code fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find first {...} or [...] block
        m = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


def ensure_keys(d: dict, defaults: dict) -> dict:
    """Return d with any missing keys filled from defaults."""
    return {**defaults, **d}
