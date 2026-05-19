import json
import logging
from collections.abc import Generator

from app.modules.plan.agents.info_collector import collect_info
from app.modules.plan.agents.intent_classify import classify_intent
from app.modules.plan.agents.plan_gen import generate_plan
from app.modules.plan.agents.doc_gen import generate_doc
from app.modules.plan.agents.profile_check import check_profile
from app.modules.plan.agents.qa_answer import answer_qa
from app.modules.plan.agents.research import research
from app.modules.plan.memory import save_plan_memory
from app.shared.job_queue import enqueue_job

logger = logging.getLogger(__name__)


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def stream_plan_agent(
    user_id: str,
    message: str,
    history: list[dict],
    profile: dict | None,
) -> Generator[str, None, None]:
    state: dict = {
        "user_id": user_id,
        "message": message,
        "history": history,
        "profile": profile,
        "intent": "",
        "missing_fields": [],
        "research_context": "",
        "generated_content": "",
        "question_to_user": None,
        "doc_draft": "",
        "doc_iterations": 0,
        "doc_quality_ok": False,
        "stop_reason": "",
    }

    missing = check_profile(profile)
    if missing:
        state["missing_fields"] = missing
        yield from collect_info(missing)
        return

    yield _encode("status", "正在分析意图...")
    try:
        intent = classify_intent(message, history, profile)
    except Exception as e:
        logger.warning("Intent classification failed, defaulting to qa: %s", e)
        intent = "qa"
    state["intent"] = intent

    if intent == "need_info":
        yield from collect_info(["identity"])
        return

    if intent in ("gen_plan", "gen_doc"):
        yield from research(state)
        if intent == "gen_plan":
            yield from generate_plan(state)
        else:
            yield from generate_doc(state)
        yield _encode("terminal", "内容已生成，请查看左侧面板。")
    else:
        yield from answer_qa(state)

    assistant_reply = state.get("generated_content", "")
    if assistant_reply:
        enqueued = enqueue_job(save_plan_memory, user_id, message, assistant_reply)
        if not enqueued:
            try:
                save_plan_memory(user_id, message, assistant_reply)
            except Exception as e:
                logger.warning("Failed to save plan memory synchronously: %s", e)
