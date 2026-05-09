from app.agents.state import LearningAgentState
from app.agents.tool_registry import call_tool


def document_structure_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    result = call_tool("extract_document_structure", text=context)
    return {
        "answer": _format_structure_answer(result),
        "active_agent": "DocumentStructureAgent",
        "tools_used": [*state["tools_used"], "extract_document_structure"],
        "stop_reason": "answered",
    }


def practice_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    result = call_tool(
        "generate_practice",
        context=context,
        question_count=5,
        difficulty="medium",
        practice_type="mixed",
    )
    return {
        "answer": _format_practice_answer(result),
        "active_agent": "PracticeAgent",
        "tools_used": [*state["tools_used"], "generate_practice"],
        "stop_reason": "answered",
    }


def grading_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    result = call_tool(
        "grade_answer",
        question=state["query"],
        user_answer=state["message"],
        reference_context=context,
    )
    return {
        "answer": _format_grading_answer(result),
        "active_agent": "PracticeAgent",
        "tools_used": [*state["tools_used"], "grade_answer"],
        "stop_reason": "answered",
    }


def relation_mapping_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    result = call_tool("map_knowledge_relations", context=context, knowledge_points=[])
    return {
        "answer": _format_relation_answer(result),
        "active_agent": "RelationMappingAgent",
        "tools_used": [*state["tools_used"], "map_knowledge_relations"],
        "stop_reason": "answered",
    }


def reflection_agent(state: LearningAgentState) -> dict:
    context = _context_text(state)
    stats = call_tool("get_learning_stats", user_id=state["user_id"])
    result = call_tool("schedule_review", context=context, learning_stats=stats, knowledge_status=[])
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


def _format_practice_answer(result: dict) -> str:
    items = result.get("items") or []
    if not items:
        return "这段内容暂时不适合生成练习。"
    lines = ["下面是基于当前文档生成的练习："]
    for idx, item in enumerate(items, start=1):
        question = item.get("question", "")
        answer = item.get("reference_answer", "")
        difficulty = item.get("difficulty", "medium")
        lines.append(f"{idx}. [{difficulty}] {question}")
        if answer:
            lines.append(f"参考答案：{answer}")
    return "\n".join(lines)


def _format_grading_answer(result: dict) -> str:
    score = result.get("score", 0)
    feedback = result.get("feedback", "")
    missing = result.get("missing_points") or []
    review = result.get("review_targets") or []
    lines = [f"评分：{score}", feedback]
    if missing:
        lines.append("缺失或需要修正：" + "、".join(missing))
    if review:
        lines.append("建议复习：" + "、".join(review))
    return "\n".join(line for line in lines if line)


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
