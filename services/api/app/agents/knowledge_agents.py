import json
import logging

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = None
    StateGraph = None

from app.agents.prompts import (
    CHUNK_CRITIC_PROMPT,
    CROSS_CHUNK_DEDUP_PROMPT,
    DOC_IMPORTANCE_PROMPT,
    KNOWLEDGE_DISCOVERY_PROMPT,
    KNOWLEDGE_FILTER_PROMPT,
    RAG_VERIFY_PROMPT,
)
from app.agents.state import DocumentKPState, KnowledgeAgentState
from app.agents.utils import safe_parse_json
from app.services.llm_service import call_deepseek, get_llm


logger = logging.getLogger(__name__)

# 常见过宽泛词，Python 层直接拦截，不浪费 LLM token
_BROAD_TERM_BLACKLIST = frozenset({
    "数据", "系统", "方法", "技术", "信息", "问题", "模型", "过程",
    "结果", "功能", "特征", "应用", "领域", "概念", "算法", "工具",
    "框架", "理论", "方式", "形式", "内容", "结构", "类型", "情况",
    "data", "system", "method", "model", "process", "result", "type",
})

_knowledge_graph = None
_doc_kp_graph = None


# ── 通用数据处理 ───────────────────────────────────────────────────────────────

def normalize_knowledge_item(kp: dict, original_text: str) -> dict | None:
    if not isinstance(kp, dict):
        return None
    if not all(k in kp for k in ["text", "type", "explanation"]):
        return None
    if kp["type"] not in ["term", "formula"]:
        return None
    kp_text = kp.get("text", "")
    if not isinstance(kp_text, str) or kp_text not in original_text:
        return None
    if kp_text in _BROAD_TERM_BLACKLIST:
        return None
    return {
        "text": kp_text,
        "type": kp["type"],
        "explanation": str(kp["explanation"]).strip()[:120],
        "importance": "high" if kp.get("importance") == "high" else "medium",
    }


def dedupe_knowledge_items(kps: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for kp in kps:
        text = kp["text"]
        if text in seen:
            continue
        seen.add(text)
        deduped.append(kp)
    return deduped


def finalize_knowledge_items(kps_data: list[dict], text: str) -> list[dict]:
    normalized = [normalize_knowledge_item(kp, text) for kp in kps_data]
    normalized = [kp for kp in normalized if kp is not None]
    normalized = dedupe_knowledge_items(normalized)
    normalized.sort(key=lambda item: 0 if item["importance"] == "high" else 1)
    return normalized


# ── Phase 1：chunk 级节点 ──────────────────────────────────────────────────────

def knowledge_discovery_agent(state: KnowledgeAgentState) -> dict:
    llm = get_llm(temperature=0.2 if state["retry_count"] == 0 else 0.4)
    retry_note = (
        "\n这是一次重试：请重新判断是否确实没有学习价值高的知识点，不要为了填充而提取。"
        if state["retry_count"] else ""
    )
    prompt = (
        f"{KNOWLEDGE_DISCOVERY_PROMPT}\n\n"
        f"【文档片段】\n\"\"\"{state['current_text']}\"\"\"\n"
        f"{retry_note}\n"
        f"请由内容本身决定知识点数量。只输出 JSON，不要输出解释性文字。"
    )
    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        discovered = parsed.get("knowledge_points", [])
        logger.info("[KnowledgeDiscoveryAgent] retry=%s found=%s", state["retry_count"], len(discovered))
        return {"discovered_kps": discovered, "stop_reason": "discovered"}
    except Exception as e:
        logger.exception("[KnowledgeDiscoveryAgent] failed: %s", e)
        return {"discovered_kps": [], "stop_reason": "discovery_failed"}


def chunk_critic_agent(state: KnowledgeAgentState) -> dict:
    """替代旧的 FilterAgent + RankAgent。先做 Python 规则预过滤，再用 LLM 做质量审查。"""
    candidates = state["discovered_kps"]
    if not candidates:
        return {"filtered_kps": [], "ranked_kps": [], "stop_reason": "no_candidates"}

    original_text = state["original_text"]

    # Python 预过滤：精确匹配 + 黑名单
    pre_filtered = []
    for kp in candidates:
        if not isinstance(kp, dict):
            continue
        text = kp.get("text", "")
        if not isinstance(text, str) or not text:
            continue
        if text not in original_text:
            continue
        if text in _BROAD_TERM_BLACKLIST:
            continue
        pre_filtered.append(kp)

    if not pre_filtered:
        return {"filtered_kps": [], "ranked_kps": [], "stop_reason": "all_filtered_by_rules"}

    # LLM 审查
    llm = get_llm(temperature=0.1)
    raw_list = json.dumps(pre_filtered, ensure_ascii=False, indent=2)
    prompt = (
        f"{CHUNK_CRITIC_PROMPT}\n\n"
        f"【原文片段】\n\"\"\"{original_text}\"\"\"\n\n"
        f"【候选知识点】\n{raw_list}\n\n"
        f"只输出 JSON，不要输出解释性文字。"
    )
    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        approved = parsed.get("approved", [])
    except Exception as e:
        logger.exception("[ChunkCriticAgent] LLM failed, using pre-filtered: %s", e)
        approved = pre_filtered

    final = finalize_knowledge_items(approved, original_text)
    logger.info("[ChunkCriticAgent] pre_filtered=%s approved=%s", len(pre_filtered), len(final))
    return {"filtered_kps": final, "ranked_kps": final, "stop_reason": "critic_done"}


def retry_knowledge_discovery(state: KnowledgeAgentState) -> dict:
    text = state["original_text"]
    return {
        "current_text": text[:900] if len(text) > 900 else text,
        "discovered_kps": [],
        "filtered_kps": [],
        "ranked_kps": [],
        "retry_count": state["retry_count"] + 1,
        "stop_reason": "retrying",
    }


def should_retry_knowledge_discovery(state: KnowledgeAgentState) -> str:
    if (
        len(state["ranked_kps"]) == 0
        and len(state["original_text"]) >= 120
        and state["retry_count"] < 1
    ):
        return "retry"
    return "done"


def _build_knowledge_graph():
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph dependency is not installed")

    workflow = StateGraph(KnowledgeAgentState)
    workflow.add_node("KnowledgeDiscoveryAgent", knowledge_discovery_agent)
    workflow.add_node("ChunkCriticAgent", chunk_critic_agent)
    workflow.add_node("RetryKnowledgeDiscovery", retry_knowledge_discovery)

    workflow.set_entry_point("KnowledgeDiscoveryAgent")
    workflow.add_edge("KnowledgeDiscoveryAgent", "ChunkCriticAgent")
    workflow.add_conditional_edges(
        "ChunkCriticAgent",
        should_retry_knowledge_discovery,
        {"retry": "RetryKnowledgeDiscovery", "done": END},
    )
    workflow.add_edge("RetryKnowledgeDiscovery", "KnowledgeDiscoveryAgent")
    return workflow.compile()


def _get_knowledge_graph():
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = _build_knowledge_graph()
    return _knowledge_graph


def fallback_discover_knowledge(text: str) -> list[dict]:
    messages = [
        {"role": "system", "content": KNOWLEDGE_DISCOVERY_PROMPT},
        {
            "role": "user",
            "content": f"请从以下文档片段中识别有学习价值的知识点。不要预设数量，只输出 JSON：\n\n{text}",
        },
    ]
    raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
    parsed = safe_parse_json(raw_reply)
    candidates = parsed.get("knowledge_points", [])
    pre_filtered = [
        kp for kp in candidates
        if isinstance(kp, dict)
        and isinstance(kp.get("text", ""), str)
        and kp["text"] in text
        and kp["text"] not in _BROAD_TERM_BLACKLIST
    ]
    return finalize_knowledge_items(pre_filtered, text)


def discover_knowledge_points(text: str) -> list[dict]:
    initial: KnowledgeAgentState = {
        "original_text": text,
        "current_text": text,
        "discovered_kps": [],
        "filtered_kps": [],
        "ranked_kps": [],
        "retry_count": 0,
        "stop_reason": "started",
    }
    if StateGraph is None:
        logger.warning("LangGraph is not installed, using fallback discovery")
        return fallback_discover_knowledge(text)

    result = _get_knowledge_graph().invoke(initial)
    return finalize_knowledge_items(result.get("ranked_kps", []), text)


# ── Phase 2：文档级节点（True Agents）─────────────────────────────────────────

def _python_exact_dedup(all_kps: list[dict]) -> tuple[dict, list[dict]]:
    """Python 精确去重，返回 (global_registry, deduped_list)。
    同一 text 出现多次时，保留 importance=high 的那条，并记录出现次数。
    """
    registry: dict[str, dict] = {}
    chunk_counts: dict[str, int] = {}

    for kp in all_kps:
        text = kp.get("text", "")
        if not text:
            continue
        chunk_counts[text] = chunk_counts.get(text, 0) + 1
        existing = registry.get(text)
        if existing is None:
            registry[text] = dict(kp)
        elif kp.get("importance") == "high" and existing.get("importance") != "high":
            registry[text] = dict(kp)

    for text, kp in registry.items():
        kp["chunk_count"] = chunk_counts[text]

    deduped = list(registry.values())
    deduped.sort(key=lambda k: (0 if k.get("importance") == "high" else 1, k["text"]))
    return registry, deduped


def _find_near_duplicate_groups(kps: list[dict]) -> list[list[dict]]:
    """找出可能近义的候选组（一个的 text 是另一个的子串），供 LLM 判断。"""
    texts = [kp["text"] for kp in kps]
    groups = []
    visited = set()
    for i, t1 in enumerate(texts):
        if i in visited:
            continue
        group = [kps[i]]
        for j, t2 in enumerate(texts):
            if j <= i or j in visited:
                continue
            if t1 in t2 or t2 in t1:
                group.append(kps[j])
                visited.add(j)
        if len(group) > 1:
            visited.add(i)
            groups.append(group)
    return groups


def cross_chunk_dedup_agent(state: DocumentKPState) -> dict:
    """
    真正的 Agent：维护跨 chunk 的全局知识点注册表，完成精确去重 + LLM 语义去重。
    内部状态（global_registry）在整个文档处理生命周期内持续累积。
    """
    all_kps = state["all_chunk_kps"]
    if not all_kps:
        return {"global_registry": {}, "deduped_kps": [], "stop_reason": "no_kps"}

    # Step 1: Python 精确去重，建立基础注册表
    registry, deduped = _python_exact_dedup(all_kps)
    logger.info("[CrossChunkDedup] raw=%s after_exact_dedup=%s", len(all_kps), len(deduped))

    # Step 2: 找近义候选组，交给 LLM 判断
    near_dup_groups = _find_near_duplicate_groups(deduped)
    if not near_dup_groups:
        logger.info("[CrossChunkDedup] no near-duplicate groups found")
        return {"global_registry": registry, "deduped_kps": deduped, "stop_reason": "dedup_done"}

    try:
        groups_json = json.dumps(near_dup_groups, ensure_ascii=False, indent=2)
        prompt = (
            f"{CROSS_CHUNK_DEDUP_PROMPT}\n\n"
            f"【待去重的近义候选组】\n{groups_json}\n\n"
            f"只输出 JSON，不要输出解释性文字。"
        )
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        llm_deduped = parsed.get("deduplicated", [])

        # 用 LLM 结果替换对应的近义组
        llm_texts = {kp["text"] for kp in llm_deduped if isinstance(kp, dict) and "text" in kp}
        group_texts = {kp["text"] for group in near_dup_groups for kp in group}

        # 从 deduped 中移除近义组的所有项，再加入 LLM 选定的结果
        final = [kp for kp in deduped if kp["text"] not in group_texts]
        for kp in llm_deduped:
            if isinstance(kp, dict) and kp.get("text") and kp["text"] in llm_texts:
                kp.setdefault("chunk_count", 1)
                final.append(kp)

        # 更新 registry
        for kp in final:
            registry[kp["text"]] = kp

        final.sort(key=lambda k: (0 if k.get("importance") == "high" else 1, k["text"]))
        logger.info(
            "[CrossChunkDedup] near_dup_groups=%s after_llm_dedup=%s",
            len(near_dup_groups), len(final),
        )
        return {"global_registry": registry, "deduped_kps": final, "stop_reason": "dedup_done"}

    except Exception as e:
        logger.exception("[CrossChunkDedup] LLM dedup failed, keeping exact-dedup result: %s", e)
        return {"global_registry": registry, "deduped_kps": deduped, "stop_reason": "dedup_done"}


def document_importance_agent(state: DocumentKPState) -> dict:
    """
    真正的 Agent：调用 read_document_summary 工具获取文档全局视角，
    再基于摘要为所有去重后的 KPs 打全局重要性分。
    """
    from app.agents.tool_registry import call_tool

    deduped_kps = state["deduped_kps"]
    if not deduped_kps:
        return {"doc_summary": "", "scored_kps": [], "stop_reason": "no_kps"}

    user_id = state["user_id"]
    doc_id = state["doc_id"]

    # 调用工具：读取文档摘要
    doc_summary = ""
    try:
        doc_summary = call_tool("read_document_summary", user_id=user_id, doc_id=doc_id) or ""
        logger.info("[DocImportanceAgent] doc_summary_len=%s", len(doc_summary))
    except Exception as e:
        logger.warning("[DocImportanceAgent] read_document_summary failed: %s", e)

    if not doc_summary:
        # 没有摘要时跳过重新打分，保留原有 importance
        return {"doc_summary": "", "scored_kps": deduped_kps, "stop_reason": "no_summary_skip"}

    # 多次出现的 KP（chunk_count > 1）倾向于 high
    multi_chunk = {kp["text"] for kp in deduped_kps if kp.get("chunk_count", 1) > 1}

    # LLM 基于摘要重新打分
    try:
        kps_json = json.dumps(deduped_kps, ensure_ascii=False, indent=2)
        prompt = (
            f"{DOC_IMPORTANCE_PROMPT}\n\n"
            f"【文档摘要】\n{doc_summary}\n\n"
            f"【知识点列表（含跨块出现次数 chunk_count）】\n{kps_json}\n\n"
            f"只输出 JSON，不要输出解释性文字。"
        )
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        scored = parsed.get("ranked", deduped_kps)

        # 强制：多块出现的 KP 至少为 high
        for kp in scored:
            if isinstance(kp, dict) and kp.get("text") in multi_chunk:
                kp["importance"] = "high"

        logger.info("[DocImportanceAgent] scored=%s", len(scored))
        return {"doc_summary": doc_summary, "scored_kps": scored, "stop_reason": "scored"}

    except Exception as e:
        logger.exception("[DocImportanceAgent] scoring failed, keeping deduped: %s", e)
        return {"doc_summary": doc_summary, "scored_kps": deduped_kps, "stop_reason": "scored_fallback"}


def rag_verify_agent(state: DocumentKPState) -> dict:
    """
    真正的 Agent：对每个 KP 调用 search_document_chunks 工具做 RAG 二次验证，
    丢弃在文档语义空间中完全无法检索到的可疑 KP。
    """
    from app.agents.tool_registry import call_tool

    scored_kps = state["scored_kps"]
    if not scored_kps:
        return {"verified_kps": [], "stop_reason": "no_kps"}

    user_id = state["user_id"]
    doc_id = state["doc_id"]

    verified = []
    dropped = 0

    for kp in scored_kps:
        if not isinstance(kp, dict) or not kp.get("text"):
            continue

        text = kp["text"]
        kp_type = kp.get("type", "term")
        chunk_count = kp.get("chunk_count", 1)

        # 公式 / 短词 / 多块出现的 KP 直接通过，不走 RAG 验证
        if kp_type == "formula" or len(text) <= 2 or chunk_count > 1:
            verified.append(kp)
            continue

        # 调用 RAG 工具检索
        try:
            sources = call_tool(
                "search_document_chunks",
                user_id=user_id,
                doc_id=doc_id,
                query=text,
                top_k=1,
            )
            top_score = sources[0].score if sources else 0.0
        except Exception as e:
            logger.warning("[RAGVerifyAgent] search failed for '%s': %s", text, e)
            verified.append(kp)
            continue

        if top_score >= 0.4:
            verified.append(kp)
        elif top_score >= 0.2:
            kp = dict(kp)
            kp["importance"] = "medium"
            verified.append(kp)
        else:
            dropped += 1
            logger.info("[RAGVerifyAgent] dropped '%s' (score=%.3f)", text, top_score)

    logger.info("[RAGVerifyAgent] kept=%s dropped=%s", len(verified), dropped)
    verified.sort(key=lambda k: (0 if k.get("importance") == "high" else 1, k.get("text", "")))
    return {"verified_kps": verified, "stop_reason": "verified"}


def _build_doc_kp_graph():
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph dependency is not installed")

    workflow = StateGraph(DocumentKPState)
    workflow.add_node("CrossChunkDeduplicationAgent", cross_chunk_dedup_agent)
    workflow.add_node("DocumentImportanceAgent", document_importance_agent)
    workflow.add_node("RAGVerificationAgent", rag_verify_agent)

    workflow.set_entry_point("CrossChunkDeduplicationAgent")
    workflow.add_edge("CrossChunkDeduplicationAgent", "DocumentImportanceAgent")
    workflow.add_edge("DocumentImportanceAgent", "RAGVerificationAgent")
    workflow.add_edge("RAGVerificationAgent", END)
    return workflow.compile()


def _get_doc_kp_graph():
    global _doc_kp_graph
    if _doc_kp_graph is None:
        _doc_kp_graph = _build_doc_kp_graph()
    return _doc_kp_graph


def refine_document_knowledge(user_id: str, doc_id: str, all_chunk_kps: list[dict]) -> list[dict]:
    """Phase 2 入口：对整篇文档的 chunk KPs 做跨块去重 + 全局重要性 + RAG 验证。"""
    if not all_chunk_kps:
        return []

    initial: DocumentKPState = {
        "doc_id": doc_id,
        "user_id": user_id,
        "all_chunk_kps": all_chunk_kps,
        "global_registry": {},
        "deduped_kps": [],
        "doc_summary": "",
        "scored_kps": [],
        "verified_kps": [],
        "stop_reason": "started",
    }

    if StateGraph is None:
        logger.warning("[Phase2] LangGraph not installed, running fallback dedup only")
        _, deduped = _python_exact_dedup(all_chunk_kps)
        return deduped

    try:
        result = _get_doc_kp_graph().invoke(initial)
        verified = result.get("verified_kps", [])
        logger.info("[Phase2] refine complete: final_kps=%s", len(verified))
        return verified
    except Exception as e:
        logger.exception("[Phase2] graph failed, returning exact-dedup fallback: %s", e)
        _, deduped = _python_exact_dedup(all_chunk_kps)
        return deduped
