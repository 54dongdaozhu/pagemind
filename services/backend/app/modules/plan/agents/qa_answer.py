import json
import logging
from collections.abc import Generator

from app.shared.llm import call_deepseek_stream

logger = logging.getLogger(__name__)

_QA_SYSTEM = """\
你是一位学习助手，请根据对话历史回答用户的问题。
用户身份：{identity}
学习目的：{purpose}
请用中文简洁准确地回答，必要时举例说明。"""


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def answer_qa(state: dict) -> Generator[str, None, None]:
    profile = state.get("profile") or {}
    system_msg = _QA_SYSTEM.format(
        identity=profile.get("identity", "用户"),
        purpose=profile.get("purpose", "学习"),
    )
    messages = [{"role": "system", "content": system_msg}]
    messages.extend(state.get("history", [])[-10:])
    messages.append({"role": "user", "content": state["message"]})

    try:
        accumulated = ""
        for chunk in call_deepseek_stream(
            messages=messages,
            temperature=0.5,
            purpose="plan_qa_answer",
        ):
            accumulated += chunk
            yield _encode("terminal", chunk)
        state["generated_content"] = accumulated
    except Exception as e:
        logger.warning("QA answer failed: %s", e)
        yield _encode("error", f"回答失败：{e}")
