import logging

from agents.utils.llms import call_llm
from state import DocumentGenerationState

logger = logging.getLogger(__name__)


def _revise_prompt(topic: str, draft: str, feedback: str) -> str:
    return f"""You are revising an educational document based on editor feedback.

Topic: {topic}

Editor feedback:
{feedback}

Current draft:
{draft[:6000]}

Apply the feedback to improve the document. Make targeted edits—do not rewrite sections that don't need changes.
Return the complete revised document in Markdown."""


def reviser_node(state: DocumentGenerationState) -> dict:
    logger.info("reviser_node task_id=%s", state["task_id"])

    revised_draft = call_llm(_revise_prompt(
        state["topic"],
        state.get("draft", ""),
        state.get("review_feedback", ""),
    ))

    return {
        "draft": revised_draft,
        "revision_count": state.get("revision_count", 0) + 1,
        "current_agent": "reviser",
        "progress_messages": [f"修订完成（第 {state.get('revision_count', 0) + 1} 轮）"],
    }
