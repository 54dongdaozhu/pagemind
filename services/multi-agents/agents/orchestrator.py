import logging

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from agents.editor import editor_node
from agents.human import human_interrupt_node
from agents.publisher import publisher_node
from agents.researcher import researcher_node
from agents.reviser import reviser_node
from agents.reviewer import reviewer_node
from agents.writer import section_writer_node, writer_assemble_node
from state import DocumentGenerationState

logger = logging.getLogger(__name__)


def _fan_out_sections(state: DocumentGenerationState) -> list[Send]:
    """Fan out to one section_writer per outline section."""
    return [
        Send("section_writer", {**state, "current_section": sec})
        for sec in state.get("outline", [])
    ]


def _route_after_review(state: DocumentGenerationState) -> str:
    return "human_interrupt" if state.get("review_decision") == "accept" else "reviser"


def _route_after_human(state: DocumentGenerationState) -> str:
    return "publisher" if state.get("human_decision") != "revise" else "reviser"


def _error_handler_node(state: DocumentGenerationState) -> dict:
    logger.error("error_handler_node task_id=%s error=%s", state["task_id"], state.get("error"))
    return {"status": "error"}


def build_graph() -> StateGraph:
    workflow = StateGraph(DocumentGenerationState)

    workflow.add_node("researcher", researcher_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("section_writer", section_writer_node)
    workflow.add_node("writer_assemble", writer_assemble_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("reviser", reviser_node)
    workflow.add_node("human_interrupt", human_interrupt_node)
    workflow.add_node("publisher", publisher_node)
    workflow.add_node("error_handler", _error_handler_node)

    workflow.set_entry_point("researcher")

    workflow.add_edge("researcher", "editor")
    # Fan-out: editor → N parallel section_writers
    workflow.add_conditional_edges("editor", _fan_out_sections, ["section_writer"])
    # Fan-in: all section_writers → writer_assemble
    workflow.add_edge("section_writer", "writer_assemble")
    workflow.add_edge("writer_assemble", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        _route_after_review,
        {"human_interrupt": "human_interrupt", "reviser": "reviser"},
    )

    workflow.add_edge("reviser", "reviewer")

    workflow.add_conditional_edges(
        "human_interrupt",
        _route_after_human,
        {"publisher": "publisher", "reviser": "reviser"},
    )

    workflow.add_edge("publisher", END)
    workflow.add_edge("error_handler", END)

    return workflow


_checkpointer = MemorySaver()
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph().compile(checkpointer=_checkpointer)
    return _graph
