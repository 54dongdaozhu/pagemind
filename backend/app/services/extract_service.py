"""
知识点提取服务。

优先使用 LangGraph 三步流水线：
extract（召回） -> filter（质检） -> rank（重要性分级）。
如果本地暂未安装 LangGraph 依赖，则退回到优化后的单次 JSON 提取，避免服务启动失败。
"""
import json
import logging
from datetime import datetime
from typing import List, TypedDict

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    END = None
    StateGraph = None

from app.core.database import get_db
from app.schemas.knowledge import ExtractResponse, KnowledgePoint
from app.services.llm_service import call_deepseek, get_llm


logger = logging.getLogger(__name__)


EXTRACT_SYSTEM_PROMPT = """你是一个专业的备考辅导助手，专门帮助学生识别学习材料中真正值得记忆和理解的核心知识点。

【提取标准 - 必须同时满足以下所有条件】
1. 专业性：是该学科领域的专业术语，普通人不一定知道其准确含义
2. 原文性：text 字段必须是原文中出现的原词原句，一个字不能改
3. 备考价值：在考试或理解本文中有实质性帮助

【绝对不提取的情况】
- 过于宽泛的词：如"人工智能"、"计算机"、"数据"、"系统"、"方法"
- 常识性词汇：高中毕业生普遍知道的内容
- 纯动词或形容词：如"优化"、"高效"、"智能化"

【两类知识点】
- "term"：专业名词、术语、核心概念
- "formula"：有具体符号的数学表达式（如 E=mc²）
  注意："能量守恒定律"这种概念归为 term，不是 formula

【解释质量要求】
- 第一句：一句话精准说清是什么（约 20 字）
- 第二句：为什么重要或考试常考什么角度（约 20 字）
- 总共不超过 60 字

输出严格的 JSON 格式:
{
  "knowledge_points": [
    {
      "text": "原文中的原词",
      "type": "term",
      "explanation": "简洁解释，两句话以内",
      "importance": "high"
    }
  ]
}
importance 字段：high = 核心考点，medium = 一般了解"""


class KPState(TypedDict):
    original_text: str
    current_text: str
    raw_kps: List[dict]
    filtered_kps: List[dict]
    final_kps: List[dict]
    retry_count: int


_extract_cache = {}
_graph = None


def safe_parse_json(content: str) -> dict:
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(content[start:end + 1])
        raise


def _normalize_importance(value: str | None) -> str:
    return "high" if value == "high" else "medium"


def _normalize_kp_dict(kp: dict, original_text: str) -> dict | None:
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
        "importance": _normalize_importance(kp.get("importance")),
    }


def _dedupe_kps(kps: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for kp in kps:
        text = kp["text"]
        if text in seen:
            continue
        seen.add(text)
        deduped.append(kp)
    return deduped


def _finalize_kps(kps_data: list[dict], text: str) -> list[KnowledgePoint]:
    normalized = []
    for kp in kps_data:
        item = _normalize_kp_dict(kp, text)
        if item is not None:
            normalized.append(item)

    normalized = _dedupe_kps(normalized)
    normalized.sort(key=lambda x: 0 if x["importance"] == "high" else 1)
    return [KnowledgePoint(**kp) for kp in normalized]


def extract_node(state: KPState) -> dict:
    llm = get_llm(temperature=0.2 if state["retry_count"] == 0 else 0.45)
    retry_note = "\n注意：这是重试，请适当放宽标准，但仍要保证 text 来自原文。" if state["retry_count"] else ""
    prompt = f"""{EXTRACT_SYSTEM_PROMPT}

请从以下学习材料中提取知识点。{retry_note}

【文本内容】
\"\"\"{state["current_text"]}\"\"\"

最多提取 12 个，优先核心专业词汇。只输出 JSON，不要输出解释性文字。"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        raw_kps = parsed.get("knowledge_points", [])
        logger.info("[extract] retry=%s raw=%s", state["retry_count"], len(raw_kps))
        return {"raw_kps": raw_kps}
    except Exception as e:
        logger.exception("[extract] 失败: %s", e)
        return {"raw_kps": []}


def filter_node(state: KPState) -> dict:
    if not state["raw_kps"]:
        return {"filtered_kps": []}

    llm = get_llm(temperature=0.1)
    raw_list = json.dumps(state["raw_kps"], ensure_ascii=False, indent=2)
    prompt = f"""你是严格的知识点质量审查员。

【原文片段】
\"\"\"{state["original_text"][:800]}\"\"\"

【待审查知识点】
{raw_list}

【必须删除的情况】
- 过于宽泛：如"人工智能"、"系统"、"数据"、"方法"、"技术"
- 常识词汇：高中生普遍知道的
- 不在原文：text 字段在原文中找不到
- 重复相似：保留最准确的一个

最多保留 8 个，宁少勿滥。

只输出 JSON：
{{"approved": [{{"text": "...", "type": "...", "explanation": "...", "importance": "medium"}}]}}"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        approved = parsed.get("approved", [])
    except Exception as e:
        logger.exception("[filter] 失败，使用本地规则兜底: %s", e)
        approved = state["raw_kps"]

    filtered = []
    for kp in approved:
        item = _normalize_kp_dict(kp, state["original_text"])
        if item is not None:
            filtered.append(item)

    filtered = _dedupe_kps(filtered)[:8]
    logger.info("[filter] approved=%s", len(filtered))
    return {"filtered_kps": filtered}


def rank_node(state: KPState) -> dict:
    if not state["filtered_kps"]:
        return {"final_kps": []}

    llm = get_llm(temperature=0.2)
    kps_list = json.dumps(state["filtered_kps"], ensure_ascii=False, indent=2)
    prompt = f"""为以下备考知识点标注重要性。

【知识点列表】
{kps_list}

【标注规则】
- importance = "high"：本段核心概念，考试极有可能考到
- importance = "medium"：有价值但不是最核心的

如果解释不够清晰，可优化（保持 60 字以内），但 text 和 type 必须保持不变。

只输出 JSON：
{{"ranked": [{{"text": "...", "type": "...", "explanation": "...", "importance": "high"}}]}}"""

    try:
        resp = llm.invoke(prompt)
        parsed = safe_parse_json(resp.content)
        ranked = parsed.get("ranked", state["filtered_kps"])
    except Exception as e:
        logger.exception("[rank] 失败，保留过滤结果: %s", e)
        ranked = state["filtered_kps"]

    final_kps = []
    for kp in ranked:
        item = _normalize_kp_dict(kp, state["original_text"])
        if item is not None:
            final_kps.append(item)

    final_kps = _dedupe_kps(final_kps)
    final_kps.sort(key=lambda x: 0 if x["importance"] == "high" else 1)
    logger.info("[rank] final=%s high=%s", len(final_kps), sum(kp["importance"] == "high" for kp in final_kps))
    return {"final_kps": final_kps}


def retry_node(state: KPState) -> dict:
    text = state["original_text"]
    return {
        "current_text": text[:600] if len(text) > 600 else text,
        "raw_kps": [],
        "filtered_kps": [],
        "final_kps": [],
        "retry_count": state["retry_count"] + 1,
    }


def should_retry(state: KPState) -> str:
    if len(state["final_kps"]) == 0 and state["retry_count"] < 2:
        return "retry"
    return "done"


def _build_graph():
    if StateGraph is None or END is None:
        raise RuntimeError("LangGraph 依赖未安装")

    workflow = StateGraph(KPState)
    workflow.add_node("extract", extract_node)
    workflow.add_node("filter", filter_node)
    workflow.add_node("rank", rank_node)
    workflow.add_node("retry", retry_node)
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "filter")
    workflow.add_edge("filter", "rank")
    workflow.add_conditional_edges("rank", should_retry, {"retry": "retry", "done": END})
    workflow.add_edge("retry", "extract")
    return workflow.compile()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def _load_from_sqlite(chunk_id: str) -> list | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT result_json FROM extract_cache WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["result_json"])
    return _finalize_kps(data, " ".join(kp.get("text", "") for kp in data))


def _save_to_sqlite(chunk_id: str, knowledge_points: list):
    now = datetime.utcnow().isoformat()
    result_json = json.dumps([kp.model_dump() for kp in knowledge_points], ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO extract_cache (chunk_id, result_json, created_at) VALUES (?, ?, ?)",
            (chunk_id, result_json, now),
        )
        conn.commit()


def _fallback_extract(text: str) -> list[dict]:
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请从以下文本中提取知识点，最多 8 个，只输出 JSON：\n\n{text}"},
    ]
    raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
    parsed = safe_parse_json(raw_reply)
    return parsed.get("knowledge_points", [])


def extract_knowledge_from_text(chunk_id: str, text: str) -> ExtractResponse:
    text = text.strip()

    if chunk_id in _extract_cache:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=_extract_cache[chunk_id])

    cached = _load_from_sqlite(chunk_id)
    if cached is not None:
        _extract_cache[chunk_id] = cached
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached)

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    kps_data = []
    try:
        if StateGraph is None:
            logger.warning("LangGraph 未安装，使用优化单步提取兜底")
            kps_data = _fallback_extract(text)
        else:
            initial: KPState = {
                "original_text": text,
                "current_text": text,
                "raw_kps": [],
                "filtered_kps": [],
                "final_kps": [],
                "retry_count": 0,
            }
            result = _get_graph().invoke(initial)
            kps_data = result.get("final_kps", [])
    except Exception as e:
        logger.exception("知识点提取失败: %s", e)
        kps_data = []

    knowledge_points = _finalize_kps(kps_data, text)

    _extract_cache[chunk_id] = knowledge_points
    _save_to_sqlite(chunk_id, knowledge_points)

    return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)
