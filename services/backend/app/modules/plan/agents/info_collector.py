import json
from collections.abc import Generator

_FIELD_QUESTIONS: dict[str, str] = {
    "identity": "请问你目前的技术背景是什么？（如：软件工程师、转行开发者、产品经理转技术等）",
    "purpose": "请问你学习这个的主要目的是什么？（如：换工作、提升工程能力、做项目等）",
}


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def collect_info(missing_fields: list[str]) -> Generator[str, None, None]:
    if not missing_fields:
        return
    field = missing_fields[0]
    question = _FIELD_QUESTIONS.get(field, f"请问你的{field}是什么？")
    yield _encode("question", question)
