import logging

from app.agents.advanced_agents import (
    document_structure_agent,
    grading_agent,
    practice_agent,
    reflection_agent,
    relation_mapping_agent,
)
from app.agents.prompts import FALLBACK_PROMPT, SUPERVISOR_PROMPT, SYNTHESIS_PROMPT, TUTOR_PROMPT
from app.agents.state import Intent, LearningAgentState
from app.agents.tool_registry import call_tool, list_tools
from app.agents.utils import safe_parse_json
from app.services.llm_service import call_deepseek


logger = logging.getLogger(__name__)


def supervisor_agent(message: str, doc_id: str | None) -> dict:
    if not doc_id:
        return {
            "intent": "unknown",
            "query": message,
            "active_agent": "SupervisorAgent",
        }

    messages = [
        {"role": "system", "content": f"{SUPERVISOR_PROMPT}\n\n【可用工具】\n{_format_tool_catalog()}"},
        {"role": "user", "content": message},
    ]
    try:
        raw_reply = call_deepseek(messages, temperature=0.1, json_mode=True)
        parsed = safe_parse_json(raw_reply)
        intent = parsed.get("intent", "qa")
        if intent not in [
            "qa",
            "explain",
            "summarize",
            "compare",
            "practice",
            "grade",
            "relation",
            "structure",
            "review",
            "unknown",
        ]:
            intent = "qa"
        return {
            "intent": intent,
            "query": str(parsed.get("query") or message).strip() or message,
            "active_agent": str(parsed.get("active_agent") or "RetrievalAgent"),
        }
    except Exception as e:
        logger.exception("[SupervisorAgent] failed, using heuristic intent: %s", e)
        return _heuristic_supervisor(message)


def retrieval_agent(state: LearningAgentState) -> dict:
    if not state["doc_id"]:
        return {
            "summary": "",
            "sources": [],
            "tools_used": state["tools_used"],
            "stop_reason": "no_document",
        }

    summary = call_tool("read_document_summary", user_id=state["user_id"], doc_id=state["doc_id"])
    sources = call_tool(
        "search_document_chunks",
        user_id=state["user_id"],
        doc_id=state["doc_id"],
        query=state["query"],
        top_k=5,
    )
    tools_used = [*state["tools_used"], "read_document_summary", "search_document_chunks"]
    return {
        "summary": summary,
        "sources": sources,
        "tools_used": tools_used,
        "stop_reason": "retrieved",
    }


def tutor_agent(state: LearningAgentState) -> dict:
    if not state["summary"] and not state["sources"]:
        answer = _fallback_answer(state["message"])
        return {
            "answer": answer,
            "active_agent": "TutorAgent",
            "stop_reason": "no_context",
        }

    context = _format_context(state["sources"])
    messages = [
        {"role": "system", "content": TUTOR_PROMPT},
        {
            "role": "user",
            "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【用户问题】\n{state['message']}",
        },
    ]
    answer = call_deepseek(messages, temperature=0.25)
    return {
        "answer": answer,
        "active_agent": "TutorAgent",
        "stop_reason": "answered",
    }


def synthesis_agent(state: LearningAgentState) -> dict:
    if not state["summary"] and not state["sources"]:
        answer = _fallback_answer(state["message"])
        return {
            "answer": answer,
            "active_agent": "SynthesisAgent",
            "stop_reason": "no_context",
        }

    context = _format_context(state["sources"])
    messages = [
        {"role": "system", "content": SYNTHESIS_PROMPT},
        {
            "role": "user",
            "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【用户请求】\n{state['message']}",
        },
    ]
    answer = call_deepseek(messages, temperature=0.2)
    return {
        "answer": answer,
        "active_agent": "SynthesisAgent",
        "stop_reason": "answered",
    }


def run_learning_agents(user_id: str, message: str, doc_id: str | None = None) -> LearningAgentState:
    decision = supervisor_agent(message, doc_id)
    intent: Intent = decision["intent"]
    state: LearningAgentState = {
        "user_id": user_id,
        "doc_id": doc_id,
        "message": message,
        "intent": intent,
        "query": decision["query"],
        "summary": "",
        "sources": [],
        "answer": "",
        "tools_used": ["SupervisorAgent"],
        "active_agent": "SupervisorAgent",
        "stop_reason": "started",
    }

    if intent == "unknown" and not doc_id:
        state.update(
            {
                "answer": _fallback_answer(message),
                "active_agent": "SupervisorAgent",
                "stop_reason": "no_document",
            }
        )
        return state

    state.update(retrieval_agent(state))

    if intent == "practice":
        state.update(practice_agent(state))
    elif intent == "grade":
        state.update(grading_agent(state))
    elif intent == "relation":
        state.update(relation_mapping_agent(state))
    elif intent == "structure":
        state.update(document_structure_agent(state))
    elif intent == "review":
        state.update(reflection_agent(state))
    elif intent in ["summarize", "compare"]:
        state.update(synthesis_agent(state))
    else:
        state.update(tutor_agent(state))

    state["tools_used"] = _dedupe_tools(state["tools_used"])
    return state


def _heuristic_supervisor(message: str) -> dict:
    text = message.strip()
    summarize_keywords = ["总结", "概括", "提炼", "笔记", "要点", "结构"]
    compare_keywords = ["比较", "区别", "联系", "相同", "不同"]
    explain_keywords = ["解释", "讲讲", "什么意思", "是什么", "为什么", "如何理解"]
    practice_keywords = ["出题", "练习", "自测", "测试", "巩固", "复述"]
    grade_keywords = ["批改", "评分", "对不对", "是否正确", "错因"]
    relation_keywords = ["关系", "图谱", "前置", "依赖", "关联"]
    structure_keywords = ["结构", "目录", "层级", "脉络", "框架"]
    review_keywords = ["复习", "计划", "下一步", "薄弱", "安排"]

    intent = "qa"
    active_agent = "RetrievalAgent"
    if any(keyword in text for keyword in practice_keywords):
        intent = "practice"
        active_agent = "PracticeAgent"
    elif any(keyword in text for keyword in grade_keywords):
        intent = "grade"
        active_agent = "PracticeAgent"
    elif any(keyword in text for keyword in relation_keywords):
        intent = "relation"
        active_agent = "RelationMappingAgent"
    elif any(keyword in text for keyword in review_keywords):
        intent = "review"
        active_agent = "ReflectionAgent"
    elif any(keyword in text for keyword in structure_keywords):
        intent = "structure"
        active_agent = "DocumentStructureAgent"
    elif any(keyword in text for keyword in summarize_keywords):
        intent = "summarize"
        active_agent = "SynthesisAgent"
    elif any(keyword in text for keyword in compare_keywords):
        intent = "compare"
        active_agent = "SynthesisAgent"
    elif any(keyword in text for keyword in explain_keywords):
        intent = "explain"
        active_agent = "TutorAgent"

    return {
        "intent": intent,
        "query": text,
        "active_agent": active_agent,
    }


def _format_tool_catalog() -> str:
    lines = []
    for tool in list_tools():
        lines.append(f"- {tool['name']}: {tool['description']} 使用时机：{tool['when_to_use']}")
    return "\n".join(lines)


def _format_context(sources) -> str:
    if not sources:
        return "未检索到高相关片段，请优先依据文档摘要回答。"
    return "\n\n".join(
        f"[片段 {source.chunk_index + 1}]\n{source.content}"
        for source in sources
    )


def _fallback_answer(message: str) -> str:
    messages = [
        {"role": "system", "content": FALLBACK_PROMPT},
        {"role": "user", "content": message},
    ]
    return call_deepseek(messages, temperature=0.3)


def _dedupe_tools(tools: list[str]) -> list[str]:
    deduped = []
    for tool in tools:
        if tool not in deduped:
            deduped.append(tool)
    return deduped
