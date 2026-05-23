import logging

from agents.utils.llms import call_llm
from agents.utils.utils import safe_parse_json, ensure_keys
from state import DocumentGenerationState

logger = logging.getLogger(__name__)

_MAX_REVISIONS = 3


def _review_prompt(topic: str, requirements: str, draft: str, user_profile: dict, revision_count: int) -> str:
    profile_hint = ""
    if user_profile:
        level = user_profile.get("level", "")
        if level:
            profile_hint = f"\nTarget audience: {level} learners."

    return f"""You are a senior editor reviewing an educational document.

Topic: {topic}
Requirements: {requirements}{profile_hint}
Revision round: {revision_count + 1}

Document draft:
{draft[:5000]}

Evaluate the document on:
1. Logical flow and coherence
2. Accuracy and depth of content
3. Educational appropriateness for the audience
4. Completeness (intro, body, conclusion, references present)
5. Clarity of explanations and examples

Return a JSON object:
{{
  "decision": "accept" or "revise",
  "feedback": "Specific, actionable feedback if revising; empty string if accepting",
  "score": 1-10
}}

Be constructive. Only request revision if there are significant issues worth fixing."""


def reviewer_node(state: DocumentGenerationState) -> dict:
    logger.info("reviewer_node task_id=%s revision=%d", state["task_id"], state.get("revision_count", 0))

    revision_count = state.get("revision_count", 0)

    # Force accept after max revisions
    if revision_count >= _MAX_REVISIONS:
        logger.warning("reviewer_node: forcing accept after %d revisions", revision_count)
        return {
            "review_decision": "accept",
            "review_feedback": "",
            "current_agent": "reviewer",
            "progress_messages": [f"审阅通过（已达最大修订轮次 {_MAX_REVISIONS}）"],
        }

    raw = call_llm(_review_prompt(
        state["topic"],
        state.get("requirements", ""),
        state.get("draft", ""),
        state.get("user_profile", {}),
        revision_count,
    ))

    result = safe_parse_json(raw) or {}
    result = ensure_keys(result, {"decision": "accept", "feedback": "", "score": 7})

    decision = result["decision"] if result["decision"] in ("accept", "revise") else "accept"
    feedback = result.get("feedback", "")
    score = result.get("score", 7)

    msg = f"审阅完成（评分 {score}/10）：{'通过' if decision == 'accept' else '需要修订'}"
    if feedback and decision == "revise":
        msg += f" — {feedback[:100]}"

    return {
        "review_decision": decision,
        "review_feedback": feedback,
        "current_agent": "reviewer",
        "progress_messages": [msg],
    }
