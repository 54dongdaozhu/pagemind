import logging

from agents.utils.llms import call_llm
from agents.utils.utils import safe_parse_json, ensure_keys
from state import DocumentGenerationState, SectionOutline

logger = logging.getLogger(__name__)


def _build_outline_prompt(topic: str, requirements: str, research_notes: str, user_profile: dict) -> str:
    profile_hint = ""
    if user_profile:
        level = user_profile.get("level", "")
        if level:
            profile_hint = f"\nTarget audience: {level} learners."

    return f"""You are an expert curriculum designer creating an educational document outline.

Topic: {topic}
Requirements: {requirements}{profile_hint}

Research notes:
{research_notes[:2000]}

Create a document outline with 4-6 main sections (excluding Introduction and Conclusion).
Each section should cover a distinct aspect of the topic.

Return a JSON array like:
[
  {{"id": "s1", "title": "Section Title", "description": "What this section covers in 1-2 sentences", "order": 1}},
  {{"id": "s2", "title": "Section Title", "description": "...", "order": 2}}
]

Return ONLY the JSON array, nothing else."""


def editor_node(state: DocumentGenerationState) -> dict:
    """Generate outline and store in state. Fan-out handled by orchestrator routing."""
    logger.info("editor_node start task_id=%s", state["task_id"])

    raw = call_llm(_build_outline_prompt(
        state["topic"],
        state.get("requirements", ""),
        state.get("research_notes", ""),
        state.get("user_profile", {}),
    ))

    sections_raw = safe_parse_json(raw) or []
    if not isinstance(sections_raw, list) or not sections_raw:
        sections_raw = [
            {"id": "s1", "title": "核心概念", "description": "介绍核心概念与基础知识", "order": 1},
            {"id": "s2", "title": "原理与机制", "description": "深入讲解工作原理", "order": 2},
            {"id": "s3", "title": "实践应用", "description": "实际案例与应用场景", "order": 3},
        ]

    outline: list[SectionOutline] = [
        ensure_keys(s, {"id": f"s{i}", "title": "Section", "description": "", "order": i})
        for i, s in enumerate(sections_raw, 1)
    ]

    logger.info("editor_node: outline has %d sections", len(outline))

    return {
        "outline": outline,
        "sections": {},
        "current_agent": "editor",
        "progress_messages": [f"大纲规划完成：{len(outline)} 个章节"],
    }
