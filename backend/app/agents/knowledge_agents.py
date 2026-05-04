import json
import logging

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = None
    StateGraph = None

from app.agents.prompts import (
    KNOWLEDGE_DISCOVERY_PROMPT,
    KNOWLEDGE_FILTER_PROMPT,
    KNOWLEDGE_RANK_PROMPT,
)
from app.agents.state import KnowledgeAgentState
from app.agents.utils import safe_parse_json
from app.services.llm_service import call_deepseek, get_llm


logger = logging.getLogger(__name__)

_knowledge_graph = None


def normalize_knowledge_item(kp: dict, original_text: str) -> dict | None:
    if not isinstance(kp, dict):
        return None
    if not all(k in kp for k in ["text", "type", "explanation"]):
        return None
    if kp["type"] not in ["term", "formula"]:
        return None
    if not isinstance(kp["text"], str) or kp["text"] not in original_text:
        return None
    return {
        "text": kp["text"],
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
    normalized = []
    for kp in kps_data:
        item = normalize_knowledge_item(kp, text)
        if item is not None:
            normalized.append(item)

    normalized = dedupe_knowledge_items(normalized)
    normalized.sort(key=lambda item: 0 if item["importance"] == "high" else 1)
    return normalized


def knowledge_discovery_agent(state: KnowledgeAgentState) -> dict:
    llm = get_llm(temperature=0.2 if state["retry_count"] == 0 else 0.4)
    retry_note = "\n这是一次重试：请重新判断是否确实没有学习价值高的知识点，不要为了填充而提取。" if state["retry_count"] else ""
    prompt = f"""{KNOWLEDGE_DISCOVERY_PROMPT}

【文档片段】
\"\"\"{state["current_text"]}\"\"\"
{retry_note}

请由内容本身决定知识点数量。只输出 JSON，不要输出解释性文字。"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        discovered = parsed.get("knowledge_points", [])
        logger.info("[KnowledgeDiscoveryAgent] retry=%s found=%s", state["retry_count"], len(discovered))
        return {"discovered_kps": discovered, "stop_reason": "discovered"}
    except Exception as e:
        logger.exception("[KnowledgeDiscoveryAgent] failed: %s", e)
        return {"discovered_kps": [], "stop_reason": "discovery_failed"}


def knowledge_filter_agent(state: KnowledgeAgentState) -> dict:
    if not state["discovered_kps"]:
        return {"filtered_kps": [], "stop_reason": "no_candidates"}

    llm = get_llm(temperature=0.1)
    raw_list = json.dumps(state["discovered_kps"], ensure_ascii=False, indent=2)
    prompt = f"""{KNOWLEDGE_FILTER_PROMPT}

【原文片段】
\"\"\"{state["original_text"]}\"\"\"

【候选知识点】
{raw_list}

只输出 JSON，不要输出解释性文字。"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        approved = parsed.get("approved", [])
    except Exception as e:
        logger.exception("[KnowledgeFilterAgent] failed, using local validation: %s", e)
        approved = state["discovered_kps"]

    filtered = finalize_knowledge_items(approved, state["original_text"])
    logger.info("[KnowledgeFilterAgent] approved=%s", len(filtered))
    return {"filtered_kps": filtered, "stop_reason": "filtered"}


def knowledge_rank_agent(state: KnowledgeAgentState) -> dict:
    if not state["filtered_kps"]:
        return {"ranked_kps": [], "stop_reason": "no_approved_items"}

    llm = get_llm(temperature=0.2)
    kps_list = json.dumps(state["filtered_kps"], ensure_ascii=False, indent=2)
    prompt = f"""{KNOWLEDGE_RANK_PROMPT}

【原文片段】
\"\"\"{state["original_text"]}\"\"\"

【已通过审查的知识点】
{kps_list}

只输出 JSON，不要输出解释性文字。"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        ranked = parsed.get("ranked", state["filtered_kps"])
    except Exception as e:
        logger.exception("[KnowledgeRankAgent] failed, keeping filtered items: %s", e)
        ranked = state["filtered_kps"]

    final_kps = finalize_knowledge_items(ranked, state["original_text"])
    logger.info("[KnowledgeRankAgent] final=%s", len(final_kps))
    return {"ranked_kps": final_kps, "stop_reason": "ranked"}


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
    if len(state["ranked_kps"]) == 0 and len(state["original_text"]) >= 120 and state["retry_count"] < 1:
        return "retry"
    return "done"


def _build_knowledge_graph():
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph dependency is not installed")

    workflow = StateGraph(KnowledgeAgentState)
    workflow.add_node("KnowledgeDiscoveryAgent", knowledge_discovery_agent)
    workflow.add_node("KnowledgeFilterAgent", knowledge_filter_agent)
    workflow.add_node("KnowledgeRankAgent", knowledge_rank_agent)
    workflow.add_node("RetryKnowledgeDiscovery", retry_knowledge_discovery)
    workflow.set_entry_point("KnowledgeDiscoveryAgent")
    workflow.add_edge("KnowledgeDiscoveryAgent", "KnowledgeFilterAgent")
    workflow.add_edge("KnowledgeFilterAgent", "KnowledgeRankAgent")
    workflow.add_conditional_edges(
        "KnowledgeRankAgent",
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
    return finalize_knowledge_items(parsed.get("knowledge_points", []), text)


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
