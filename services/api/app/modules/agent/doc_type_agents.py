import logging
from typing import TypedDict

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = None
    StateGraph = None

from app.modules.agent.prompts import DOC_TYPE_PROMPT
from app.modules.agent.utils import safe_parse_json
from app.shared.llm import call_deepseek

logger = logging.getLogger(__name__)

_DOC_TYPE_VALUES = {"教材", "论文", "讲义", "技术文档", "试卷", "报告", "其他"}
_CONFIDENCE_RETRY_THRESHOLD = 0.6
_MAX_RETRY = 2

_doc_type_graph = None


class DocTypeState(TypedDict):
    title: str
    chunks: list[str]
    doc_type: str | None
    confidence: float
    retry_count: int


def _build_context(title: str, chunks: list[str], retry_count: int) -> str:
    # 首次用前 5 个 chunk，重试时扩展到前 10 个
    limit = 5 if retry_count == 0 else 10
    chunk_text = "\n\n".join(chunks[:limit])
    parts = []
    if title:
        parts.append(f"标题：{title}")
    parts.append(f"内容摘录：\n{chunk_text[:3000]}")
    return "\n\n".join(parts)


def _classify_node(state: DocTypeState) -> dict:
    context = _build_context(state["title"], state["chunks"], state["retry_count"])
    messages = [
        {"role": "system", "content": DOC_TYPE_PROMPT},
        {"role": "user", "content": context},
    ]
    try:
        raw = call_deepseek(messages, temperature=0.1, json_mode=True)
        parsed = safe_parse_json(raw)
        doc_type = parsed.get("doc_type", "其他")
        if doc_type not in _DOC_TYPE_VALUES:
            doc_type = "其他"
        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except Exception as e:
        logger.warning("[DocTypeAgent] classify failed (retry=%s): %s", state["retry_count"], e)
        doc_type = "其他"
        confidence = 0.0
    return {"doc_type": doc_type, "confidence": confidence, "retry_count": state["retry_count"] + 1}


def _should_retry(state: DocTypeState) -> str:
    if state["confidence"] < _CONFIDENCE_RETRY_THRESHOLD and state["retry_count"] < _MAX_RETRY:
        return "retry"
    return "done"


def _build_doc_type_graph():
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph dependency is not installed")
    workflow = StateGraph(DocTypeState)
    workflow.add_node("ClassifierNode", _classify_node)
    workflow.set_entry_point("ClassifierNode")
    workflow.add_conditional_edges(
        "ClassifierNode",
        _should_retry,
        {"retry": "ClassifierNode", "done": END},
    )
    return workflow.compile()


def _get_doc_type_graph():
    global _doc_type_graph
    if _doc_type_graph is None:
        _doc_type_graph = _build_doc_type_graph()
    return _doc_type_graph


def classify_document_type(title: str, chunks: list[str]) -> dict:
    """运行文档类型识别工作流，返回 {doc_type, confidence}。LangGraph 不可用时降级直接调用 LLM。"""
    try:
        graph = _get_doc_type_graph()
        initial: DocTypeState = {
            "title": title or "",
            "chunks": chunks,
            "doc_type": None,
            "confidence": 0.0,
            "retry_count": 0,
        }
        result = graph.invoke(initial)
        return {"doc_type": result.get("doc_type", "其他"), "confidence": result.get("confidence", 0.0)}
    except Exception as e:
        logger.warning("[DocTypeAgent] graph invoke failed, fallback to direct LLM: %s", e)
        # 降级：直接单次 LLM 调用
        state: DocTypeState = {"title": title or "", "chunks": chunks, "doc_type": None, "confidence": 0.0, "retry_count": 0}
        result = _classify_node(state)
        return {"doc_type": result.get("doc_type", "其他"), "confidence": result.get("confidence", 0.0)}
