import logging

from langgraph.types import interrupt

from agents.utils.views import markdown_to_html
from state import DocumentGenerationState

logger = logging.getLogger(__name__)


def human_interrupt_node(state: DocumentGenerationState) -> dict:
    """Pause graph and wait for human approval or revision request."""
    logger.info("human_interrupt_node task_id=%s — waiting for human", state["task_id"])

    draft_html = markdown_to_html(state.get("draft", ""))

    # interrupt() suspends the graph; the resume payload will be the human's response
    response = interrupt({
        "type": "human_review",
        "draft_html": draft_html,
        "draft_markdown": state.get("draft", ""),
    })

    decision = response.get("decision", "publish") if isinstance(response, dict) else "publish"
    feedback = response.get("feedback", "") if isinstance(response, dict) else ""

    logger.info("human_interrupt_node: decision=%s task_id=%s", decision, state["task_id"])

    return {
        "human_decision": decision,
        "human_feedback": feedback,
        "status": "running",
        "current_agent": "human",
        "progress_messages": [f"人工审核完成：{decision}"],
    }
