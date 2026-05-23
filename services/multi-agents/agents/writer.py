import logging

from agents.utils.llms import call_llm
from state import DocumentGenerationState, SectionOutline

logger = logging.getLogger(__name__)


def _section_prompt(section: SectionOutline, topic: str, requirements: str, research_notes: str, user_profile: dict) -> str:
    profile_hint = ""
    if user_profile:
        level = user_profile.get("level", "")
        if level:
            profile_hint = f"\nWrite for {level} level learners."

    return f"""You are writing a section of an educational document.

Document topic: {topic}
Requirements: {requirements}{profile_hint}

Section to write:
Title: {section['title']}
Description: {section['description']}

Research notes (use as source material):
{research_notes[:3000]}

Write this section in clear, well-structured Markdown (600-900 words).
Use ## for the section heading, ### for subsections.
Include concrete examples where appropriate.
Do NOT include an introduction or conclusion for the whole document—just this section."""


def _assemble_prompt(topic: str, requirements: str, sections_text: str, user_profile: dict) -> str:
    profile_hint = ""
    if user_profile:
        level = user_profile.get("level", "")
        if level:
            profile_hint = f"\nAudience: {level} learners."

    return f"""You are completing an educational document by writing the introduction, conclusion, and reference list.

Document topic: {topic}
Requirements: {requirements}{profile_hint}

Body sections already written:
{sections_text[:4000]}

Write the following in Markdown:

1. A compelling **Introduction** (## 引言, 200-300 words) that motivates the topic and outlines what readers will learn.
2. A **Conclusion** (## 总结, 150-200 words) summarizing key takeaways.
3. A **Further Reading** section (## 延伸阅读) with 5-8 relevant resource suggestions.

Return them in order, separated by newlines. Use Markdown headings."""


def section_writer_node(state: DocumentGenerationState) -> dict:
    """Write a single section (called in parallel via Send)."""
    section = state["current_section"]
    logger.info("section_writer_node section=%s task_id=%s", section["id"], state["task_id"])

    content = call_llm(_section_prompt(
        section,
        state["topic"],
        state.get("requirements", ""),
        state.get("research_notes", ""),
        state.get("user_profile", {}),
    ))

    return {
        "sections": {section["id"]: content},
        "progress_messages": [f"章节完成：{section['title']}"],
    }


def writer_assemble_node(state: DocumentGenerationState) -> dict:
    """Assemble sections + write intro/conclusion/refs into full draft."""
    logger.info("writer_assemble_node task_id=%s", state["task_id"])

    outline = state.get("outline", [])
    sections = state.get("sections", {})

    # Order by outline order
    ordered = sorted(outline, key=lambda s: s["order"])
    body_parts = [sections.get(s["id"], f"## {s['title']}\n\n*(内容生成中)*") for s in ordered]
    body_text = "\n\n".join(body_parts)

    # Write framing content
    framing = call_llm(_assemble_prompt(
        state["topic"],
        state.get("requirements", ""),
        body_text,
        state.get("user_profile", {}),
    ))

    # Combine: title + intro + body + conclusion
    title = f"# {state['topic']}\n\n"
    draft = title + framing + "\n\n" + body_text

    return {
        "draft": draft,
        "current_agent": "writer",
        "progress_messages": ["全文草稿已完成，共 {} 个章节".format(len(ordered))],
    }
