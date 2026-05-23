import operator
from typing import Annotated, Any
from typing_extensions import TypedDict


class SectionOutline(TypedDict):
    id: str
    title: str
    description: str
    order: int


def _merge_section_dicts(a: dict[str, str], b: dict[str, str]) -> dict[str, str]:
    return {**a, **b}


class DocumentGenerationState(TypedDict):
    # Identity
    task_id: str
    user_id: str

    # Input
    topic: str
    requirements: str
    user_profile: dict[str, Any]

    # Research
    search_queries: list[str]
    web_results: list[dict[str, Any]]
    research_notes: str

    # Planning
    outline: list[SectionOutline]

    # Writing (fan-out / fan-in via Send API)
    sections: Annotated[dict[str, str], _merge_section_dicts]
    current_section: SectionOutline  # per Send payload, not persisted in main state

    # Assembly
    draft: str

    # Review
    review_feedback: str
    review_decision: str   # "accept" | "revise"
    revision_count: int

    # Human
    human_feedback: str
    human_decision: str    # "publish" | "revise"

    # Output
    html_content: str
    word_filename: str

    # Control
    status: str            # running | waiting_human | done | error
    current_agent: str
    progress_messages: Annotated[list[str], operator.add]
    error: str | None
