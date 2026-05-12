import logging
import json
import time

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
from app.services import db_log
from app.services.llm_service import call_deepseek, call_deepseek_stream


logger = logging.getLogger(__name__)
STREAM_META_MARKER = "\n[STREAM_META]\n"
STREAM_DONE_MARKER = "\n[STREAM_DONE]\n"

# intent → 对应的专项 agent 函数（复杂 agent，内部调工具而非直接调 LLM 流）
_COMPLEX_AGENT_MAP = {
    "practice": practice_agent,
    "grade": grading_agent,
    "relation": relation_mapping_agent,
    "structure": document_structure_agent,
    "review": reflection_agent,
}

# 复杂 agent 在等待 LLM 响应期间立刻向用户展示的状态提示
_COMPLEX_AGENT_STATUS = {
    "practice": "正在根据文档内容生成练习题...\n\n",
    "grade": "正在批改答案...\n\n",
    "relation": "正在分析知识点之间的关系...\n\n",
    "structure": "正在解析文档结构...\n\n",
    "review": "正在生成复习计划...\n\n",
}


# ── 基础 agent 函数 ────────────────────────────────────────────────────────────

def supervisor_agent(message: str, doc_id: str | None, history: list[dict[str, str]] | None = None) -> dict:
    if not doc_id:
        return {
            "intent": "unknown",
            "query": message,
            "active_agent": "SupervisorAgent",
        }

    heuristic = _heuristic_supervisor(message)
    if heuristic["intent"] != "qa":
        return heuristic

    user_content = _format_supervisor_input(message, history or [])
    messages = [
        {"role": "system", "content": f"{SUPERVISOR_PROMPT}\n\n【可用工具】\n{_format_tool_catalog()}"},
        {"role": "user", "content": user_content},
    ]
    try:
        raw_reply = call_deepseek(messages, temperature=0.1, json_mode=True)
        parsed = safe_parse_json(raw_reply)
        intent = parsed.get("intent", "qa")
        if intent not in [
            "qa", "explain", "summarize", "compare",
            "practice", "grade", "relation", "structure", "review", "unknown",
        ]:
            intent = "qa"
        return {
            "intent": intent,
            "query": str(parsed.get("query") or message).strip() or message,
            "active_agent": str(parsed.get("active_agent") or "RetrievalAgent"),
        }
    except Exception as e:
        logger.exception("[SupervisorAgent] failed, using heuristic intent: %s", e)
        return heuristic


def retrieval_agent(state: LearningAgentState) -> dict:
    if not state["doc_id"]:
        return {
            "summary": "",
            "sources": [],
            "tools_used": state["tools_used"],
            "stop_reason": "no_document",
        }

    if state["intent"] in {"summarize", "structure"}:
        cached_summary = call_tool(
            "read_document_summary",
            user_id=state["user_id"],
            doc_id=state["doc_id"],
        )
        if cached_summary:
            return {
                "summary": cached_summary,
                "sources": [],
                "tools_used": [*state["tools_used"], "read_document_summary"],
                "stop_reason": "retrieved",
            }
        result = call_tool(
            "summarize_full_document",
            user_id=state["user_id"],
            doc_id=state["doc_id"],
            request=state["message"],
        )
        return {
            "summary": result.get("summary") or "",
            "sources": [],
            "tools_used": [*state["tools_used"], "summarize_full_document"],
            "stop_reason": "full_document_summarized",
        }

    sources = call_tool(
        "search_document_chunks",
        user_id=state["user_id"],
        doc_id=state["doc_id"],
        query=state["query"],
        top_k=5,
    )
    if state["intent"] in {"qa", "explain"}:
        return {
            "summary": "",
            "sources": sources,
            "tools_used": [*state["tools_used"], "search_document_chunks"],
            "stop_reason": "retrieved",
        }

    summary = call_tool("read_document_summary", user_id=state["user_id"], doc_id=state["doc_id"])
    return {
        "summary": summary,
        "sources": sources,
        "tools_used": [*state["tools_used"], "read_document_summary", "search_document_chunks"],
        "stop_reason": "retrieved",
    }


def tutor_agent(state: LearningAgentState) -> dict:
    if not state["summary"] and not state["sources"]:
        return {
            "answer": _fallback_answer(state["message"]),
            "active_agent": "TutorAgent",
            "stop_reason": "no_context",
        }
    context = _format_context(state["sources"])
    history = _format_history(state.get("history", []))
    messages = [
        {"role": "system", "content": TUTOR_PROMPT},
        {"role": "user", "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【最近对话（真实历史，不是示例）】\n{history}\n\n【当前用户问题】\n{state['message']}"},
    ]
    return {
        "answer": call_deepseek(messages, temperature=0.25),
        "active_agent": "TutorAgent",
        "stop_reason": "answered",
    }


def synthesis_agent(state: LearningAgentState) -> dict:
    if not state["summary"] and not state["sources"]:
        return {
            "answer": _fallback_answer(state["message"]),
            "active_agent": "SynthesisAgent",
            "stop_reason": "no_context",
        }
    context = _format_context(state["sources"])
    history = _format_history(state.get("history", []))
    messages = [
        {"role": "system", "content": SYNTHESIS_PROMPT},
        {"role": "user", "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【最近对话（真实历史，不是示例）】\n{history}\n\n【当前用户请求】\n{state['message']}"},
    ]
    return {
        "answer": call_deepseek(messages, temperature=0.2),
        "active_agent": "SynthesisAgent",
        "stop_reason": "answered",
    }


# ── 共享编排 helper ────────────────────────────────────────────────────────────

def _init_state(
    user_id: str,
    doc_id: str | None,
    message: str,
    decision: dict,
    history: list[dict[str, str]] | None = None,
) -> LearningAgentState:
    return {
        "user_id": user_id,
        "doc_id": doc_id,
        "message": message,
        "history": _sanitize_history(history or []),
        "intent": decision["intent"],
        "query": decision["query"],
        "summary": "",
        "sources": [],
        "answer": "",
        "tools_used": ["SupervisorAgent"],
        "active_agent": "SupervisorAgent",
        "stop_reason": "started",
    }


def _log_supervisor(
    message: str,
    doc_id: str | None,
    run_id: str,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """运行 supervisor_agent 并记录步骤日志，返回 decision dict。"""
    step_id = db_log.create_workflow_step(
        run_id=run_id, step_name="supervisor", step_order=1,
        input_data={"message": message[:500]},
    )
    token = db_log.current_step_id.set(step_id)
    ok, decision = True, None
    try:
        decision = supervisor_agent(message, doc_id, history=history)
        return decision
    except Exception:
        ok = False
        raise
    finally:
        db_log.current_step_id.reset(token)
        db_log.finish_workflow_step(
            step_id, success=ok,
            output_data={"intent": decision.get("intent") if decision else None},
        )


def _log_retrieval(state: LearningAgentState, run_id: str) -> None:
    """运行 retrieval_agent 并记录步骤日志，就地更新 state。"""
    step_id = db_log.create_workflow_step(
        run_id=run_id, step_name="retrieval", step_order=2,
        input_data={"query": state["query"]},
    )
    token = db_log.current_step_id.set(step_id)
    try:
        state.update(retrieval_agent(state))
    finally:
        db_log.current_step_id.reset(token)
        db_log.finish_workflow_step(step_id, output_data={"source_count": len(state.get("sources", []))})


def _build_llm_messages(state: LearningAgentState) -> tuple[list, float]:
    """为流式路径构建最终 LLM 消息，返回 (messages, temperature)。"""
    context = _format_context(state["sources"])
    history = _format_history(state.get("history", []))
    if state["intent"] in ["summarize", "compare"]:
        return [
            {"role": "system", "content": SYNTHESIS_PROMPT},
            {"role": "user", "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【最近对话（真实历史，不是示例）】\n{history}\n\n【当前用户请求】\n{state['message']}"},
        ], 0.2
    return [
        {"role": "system", "content": TUTOR_PROMPT},
        {"role": "user", "content": f"【文档摘要】\n{state['summary'] or '无'}\n\n【相关片段】\n{context}\n\n【最近对话（真实历史，不是示例）】\n{history}\n\n【当前用户问题】\n{state['message']}"},
    ], 0.25


# ── 公共编排入口 ───────────────────────────────────────────────────────────────

def run_learning_agents(
    user_id: str,
    message: str,
    doc_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> LearningAgentState:
    history = _sanitize_history(history or [])
    run_id = db_log.create_workflow_run(
        workflow_type="agent_chat",
        user_id=user_id, doc_id=doc_id,
        input_data={"message": message[:500], "history_count": len(history)},
    )
    run_id_token = db_log.current_run_id.set(run_id)
    success, error_info, state, start = True, None, None, time.monotonic()
    try:
        decision = _log_supervisor(message, doc_id, run_id, history=history)
        state = _init_state(user_id, doc_id, message, decision, history=history)

        if state["intent"] == "unknown" and not doc_id:
            state.update({
                "answer": _fallback_answer(message),
                "active_agent": "SupervisorAgent",
                "stop_reason": "no_document",
            })
            return state

        _log_retrieval(state, run_id)

        agent_name = state.get("active_agent") or state["intent"]
        step_id = db_log.create_workflow_step(
            run_id=run_id, step_name=agent_name, step_order=3,
            input_data={"intent": state["intent"]},
        )
        step_id_token = db_log.current_step_id.set(step_id)
        final_ok, final_err = True, None
        try:
            agent_fn = _COMPLEX_AGENT_MAP.get(state["intent"])
            if agent_fn:
                state.update(agent_fn(state))
            elif state["intent"] in ["summarize", "compare"]:
                state.update(synthesis_agent(state))
            else:
                state.update(tutor_agent(state))
        except Exception as e:
            final_ok, final_err = False, {"error": str(e)}
            raise
        finally:
            db_log.current_step_id.reset(step_id_token)
            db_log.finish_workflow_step(
                step_id, success=final_ok,
                output_data={"stop_reason": state.get("stop_reason")},
                error_details=final_err,
            )

        state["tools_used"] = _dedupe_tools(state["tools_used"])
        return state
    except Exception as e:
        success, error_info = False, {"error": str(e)}
        raise
    finally:
        db_log.current_run_id.reset(run_id_token)
        db_log.finish_workflow_run(
            run_id, success=success,
            output_data={
                "latency_ms": int((time.monotonic() - start) * 1000),
                "intent": state.get("intent") if state else None,
                "agent": state.get("active_agent") if state else None,
            },
            error_details=error_info,
        )


def stream_learning_agents(
    user_id: str,
    message: str,
    doc_id: str | None = None,
    history: list[dict[str, str]] | None = None,
):
    history = _sanitize_history(history or [])
    run_id = db_log.create_workflow_run(
        workflow_type="agent_chat_stream",
        user_id=user_id, doc_id=doc_id,
        input_data={"message": message[:500], "history_count": len(history)},
    )
    run_id_token = db_log.current_run_id.set(run_id)
    success, error_info, state, start = True, None, None, time.monotonic()
    try:
        decision = _log_supervisor(message, doc_id, run_id, history=history)
        state = _init_state(user_id, doc_id, message, decision, history=history)

        if state["intent"] == "unknown" and not doc_id:
            answer_parts = []
            for chunk in call_deepseek_stream(
                [{"role": "system", "content": FALLBACK_PROMPT}, {"role": "user", "content": message}],
                temperature=0.3,
            ):
                answer_parts.append(chunk)
                yield chunk
            state.update({
                "answer": "".join(answer_parts),
                "active_agent": "SupervisorAgent",
                "stop_reason": "no_document",
            })
            state["tools_used"] = _dedupe_tools(state["tools_used"])
            _log_stream_qa(state, start)
            yield _format_stream_metadata(state)
            return

        _log_retrieval(state, run_id)

        agent_name = state.get("active_agent") or state["intent"]
        step_id = db_log.create_workflow_step(
            run_id=run_id, step_name=agent_name, step_order=3,
            input_data={"intent": state["intent"]},
        )
        step_id_token = db_log.current_step_id.set(step_id)
        final_ok, final_err = True, None
        try:
            agent_fn = _COMPLEX_AGENT_MAP.get(state["intent"])
            if agent_fn:
                yield _COMPLEX_AGENT_STATUS.get(state["intent"], "正在处理...\n\n")
                state.update(agent_fn(state))
                yield state["answer"]
            else:
                messages, temp = _build_llm_messages(state)
                answer_parts = []
                for chunk in call_deepseek_stream(messages, temperature=temp):
                    answer_parts.append(chunk)
                    yield chunk
                state.update({
                    "answer": "".join(answer_parts),
                    "active_agent": "SynthesisAgent" if state["intent"] in ["summarize", "compare"] else "TutorAgent",
                    "stop_reason": "answered",
                })
            state["tools_used"] = _dedupe_tools(state["tools_used"])
            _log_stream_qa(state, start)
            yield _format_stream_metadata(state)
        except Exception as e:
            final_ok, final_err = False, {"error": str(e)}
            raise
        finally:
            db_log.current_step_id.reset(step_id_token)
            db_log.finish_workflow_step(
                step_id, success=final_ok,
                output_data={"intent": state.get("intent")},
                error_details=final_err,
            )
    except Exception as e:
        success, error_info = False, {"error": str(e)}
        raise
    finally:
        db_log.current_run_id.reset(run_id_token)
        db_log.finish_workflow_run(
            run_id, success=success,
            output_data={
                "latency_ms": int((time.monotonic() - start) * 1000),
                "intent": state.get("intent") if state else None,
                "agent": state.get("active_agent") if state else None,
            },
            error_details=error_info,
        )


# ── 私有工具函数 ───────────────────────────────────────────────────────────────

def _log_stream_qa(state: LearningAgentState, start: float) -> None:
    db_log.log_qa(
        user_id=state["user_id"],
        doc_id=state["doc_id"],
        question=state["message"],
        answer=state["answer"],
        intent=state["intent"],
        agent=state["active_agent"],
        tools_used=state["tools_used"],
        latency_ms=int((time.monotonic() - start) * 1000),
        sources=state["sources"],
    )

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
    if any(k in text for k in practice_keywords):
        intent, active_agent = "practice", "PracticeAgent"
    elif any(k in text for k in grade_keywords):
        intent, active_agent = "grade", "PracticeAgent"
    elif any(k in text for k in relation_keywords):
        intent, active_agent = "relation", "RelationMappingAgent"
    elif any(k in text for k in review_keywords):
        intent, active_agent = "review", "ReflectionAgent"
    elif any(k in text for k in structure_keywords):
        intent, active_agent = "structure", "DocumentStructureAgent"
    elif any(k in text for k in summarize_keywords):
        intent, active_agent = "summarize", "SynthesisAgent"
    elif any(k in text for k in compare_keywords):
        intent, active_agent = "compare", "SynthesisAgent"
    elif any(k in text for k in explain_keywords):
        intent, active_agent = "explain", "TutorAgent"

    return {"intent": intent, "query": text, "active_agent": active_agent}


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


def _format_stream_metadata(state: LearningAgentState) -> str:
    payload = {
        "agent": state["active_agent"],
        "intent": state["intent"],
        "tools_used": state["tools_used"],
        "stop_reason": state["stop_reason"],
        "sources": [_source_to_dict(source) for source in state["sources"]],
    }
    return f"{STREAM_META_MARKER}{json.dumps(payload, ensure_ascii=False)}{STREAM_DONE_MARKER}"


def _source_to_dict(source) -> dict:
    if isinstance(source, dict):
        return source
    if hasattr(source, "model_dump"):
        return source.model_dump()
    return {
        "chunk_index": getattr(source, "chunk_index", None),
        "content": getattr(source, "content", ""),
        "score": getattr(source, "score", None),
        "retrieval_method": getattr(source, "retrieval_method", "keyword"),
    }


def _sanitize_history(history) -> list[dict[str, str]]:
    cleaned = []
    for item in history[-8:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:1200]})
    return cleaned


def _format_history(history: list[dict[str, str]]) -> str:
    history = _sanitize_history(history)
    if not history:
        return "无"
    role_names = {"user": "用户", "assistant": "助手"}
    return "\n".join(f"{role_names[item['role']]}：{item['content']}" for item in history)


def _format_supervisor_input(message: str, history: list[dict[str, str]]) -> str:
    formatted_history = _format_history(history)
    return (
        "请只判断当前用户问题的意图。最近对话是真实历史，不是 few-shot 示例；"
        "如果当前问题包含代词或省略，请结合历史改写 query。\n\n"
        f"【最近对话】\n{formatted_history}\n\n"
        f"【当前用户问题】\n{message}"
    )


def _fallback_answer(message: str) -> str:
    return call_deepseek(
        [{"role": "system", "content": FALLBACK_PROMPT}, {"role": "user", "content": message}],
        temperature=0.3,
    )


def _dedupe_tools(tools: list[str]) -> list[str]:
    seen: set[str] = set()
    return [t for t in tools if not (t in seen or seen.add(t))]
