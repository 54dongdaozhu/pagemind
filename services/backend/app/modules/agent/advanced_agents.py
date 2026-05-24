import logging

from app.modules.agent.state import LearningAgentState
from app.modules.agent.tool_registry import call_tool
from app.shared import db_log

logger = logging.getLogger(__name__)


def document_structure_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    try:
        result = call_tool("extract_document_structure", text=context)
    except Exception as exc:
        logger.exception("[DocumentStructureAgent] extract_document_structure failed: %s", exc)
        return {
            "answer": "文档结构解析暂时不可用，请稍后重试。",
            "active_agent": "DocumentStructureAgent",
            "tools_used": [*state["tools_used"], "extract_document_structure"],
            "stop_reason": "tool_error",
        }
    return {
        "answer": _format_structure_answer(result),
        "active_agent": "DocumentStructureAgent",
        "tools_used": [*state["tools_used"], "extract_document_structure"],
        "stop_reason": "answered",
    }


def relation_mapping_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    try:
        result = call_tool("map_knowledge_relations", context=context, knowledge_points=[])
    except Exception as exc:
        logger.exception("[RelationMappingAgent] map_knowledge_relations failed: %s", exc)
        return {
            "answer": "知识关系分析暂时不可用，请稍后重试。",
            "active_agent": "RelationMappingAgent",
            "tools_used": [*state["tools_used"], "map_knowledge_relations"],
            "stop_reason": "tool_error",
        }
    return {
        "answer": _format_relation_answer(result),
        "active_agent": "RelationMappingAgent",
        "tools_used": [*state["tools_used"], "map_knowledge_relations"],
        "stop_reason": "answered",
    }


def reflection_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    try:
        stats = call_tool("get_learning_stats", user_id=state["user_id"])
        result = call_tool("schedule_review", context=context, learning_stats=stats, knowledge_status=[])
    except Exception as exc:
        logger.exception("[ReflectionAgent] schedule_review failed: %s", exc)
        return {
            "answer": "复习计划生成暂时不可用，请稍后重试。",
            "active_agent": "ReflectionAgent",
            "tools_used": [*state["tools_used"], "get_learning_stats", "schedule_review"],
            "stop_reason": "tool_error",
        }
    db_log.log_review_records(
        user_id=state["user_id"],
        doc_id=state["doc_id"],
        review_items=result.get("review_items") or [],
    )
    return {
        "answer": _format_review_answer(result),
        "active_agent": "ReflectionAgent",
        "tools_used": [*state["tools_used"], "get_learning_stats", "schedule_review"],
        "stop_reason": "answered",
    }


def _context_text(state: LearningAgentState) -> str:
    source_text = "\n\n".join(
        f"[片段 {source.chunk_index + 1}]\n{source.content}"
        for source in state["sources"]
    )
    if state["summary"] and source_text:
        return f"【文档摘要】\n{state['summary']}\n\n【相关片段】\n{source_text}"
    if state["summary"]:
        return state["summary"]
    return source_text or state["message"]


def _format_structure_answer(result: dict) -> str:
    title = result.get("title") or "文档结构"
    summary = result.get("summary") or ""
    sections = result.get("sections") or []
    lines = [f"**{title}**"]
    if summary:
        lines.append(summary)
    for section in sections:
        section_title = section.get("title", "未命名部分")
        section_summary = section.get("summary", "")
        goal = section.get("learning_goal", "")
        line = f"- {section_title}"
        if section_summary:
            line += f"：{section_summary}"
        if goal:
            line += f"（学习目标：{goal}）"
        lines.append(line)
    order = result.get("suggested_order") or []
    if order:
        lines.append("建议学习顺序：" + " -> ".join(order))
    return "\n".join(lines)


def _format_relation_answer(result: dict) -> str:
    relations = result.get("relations") or []
    if not relations:
        return "当前上下文里没有发现明确的知识关系。"
    lines = ["知识关系："]
    for item in relations:
        source = item.get("source", "")
        target = item.get("target", "")
        relation = item.get("relation", "")
        reason = item.get("reason", "")
        lines.append(f"- {source} -> {target}（{relation}）：{reason}")
    return "\n".join(lines)


def _format_review_answer(result: dict) -> str:
    lines = []
    summary = result.get("summary")
    if summary:
        lines.append(summary)
    for item in result.get("review_items") or []:
        text = item.get("text", "")
        priority = item.get("priority", "medium")
        reason = item.get("reason", "")
        suggested_time = item.get("suggested_time", "")
        next_action = item.get("next_action", "")
        lines.append(f"- [{priority}] {text}：{reason}。建议时间：{suggested_time}。下一步：{next_action}")
    return "\n".join(lines) or "当前学习记录还不够生成复习建议。"
