import logging
import os

from agents.utils.file_formats import markdown_to_docx
from agents.utils.views import markdown_to_html
from state import DocumentGenerationState

logger = logging.getLogger(__name__)

_WORD_DIR = os.getenv("DOC_GEN_WORD_DIR", "/tmp/doc-gen")


def publisher_node(state: DocumentGenerationState) -> dict:
    logger.info("publisher_node task_id=%s", state["task_id"])

    draft = state.get("draft", "")
    task_id = state["task_id"]

    # Apply any human revision request to the draft (human_decision = "revise" handled by orchestrator routing)
    html_content = markdown_to_html(draft)

    word_path = os.path.join(_WORD_DIR, f"{task_id}.docx")
    try:
        markdown_to_docx(draft, word_path)
        word_filename = word_path
    except Exception as e:
        logger.error("Failed to generate Word file: %s", e)
        word_filename = ""

    return {
        "html_content": html_content,
        "word_filename": word_filename,
        "status": "done",
        "current_agent": "publisher",
        "progress_messages": ["文档已发布，Word 文件已生成"],
    }
