from app.agents.knowledge_agents import discover_knowledge_points
from app.agents.prompts import (
    ANSWER_GRADING_PROMPT,
    DOCUMENT_STRUCTURE_PROMPT,
    PRACTICE_GENERATION_PROMPT,
    RELATION_MAPPING_PROMPT,
    REVIEW_SCHEDULE_PROMPT,
)
from app.agents.utils import safe_parse_json
from langchain_core.tools import tool
from app.services.explain_service import stream_deep_explanation
from app.services.knowledge_service import (
    get_status_batch,
    get_stats,
    mark_known,
    record_click,
    unmark_known,
)
from app.services.llm_service import call_deepseek
from app.services.rag_service import answer_with_rag, get_document_summary, retrieve_relevant_chunks


@tool
def search_document_chunks(user_id: str, doc_id: str, query: str, top_k: int = 4):
    """根据查询语句从当前文档中检索相关片段。"""
    return retrieve_relevant_chunks(user_id=user_id, doc_id=doc_id, question=query, top_k=top_k)


@tool
def read_document_summary(user_id: str, doc_id: str) -> str:
    """读取当前已索引文档的整体摘要。"""
    return get_document_summary(user_id, doc_id)


@tool
def answer_with_document_context(user_id: str, doc_id: str, question: str, top_k: int = 4):
    """基于文档摘要和检索片段直接生成文档问答结果。"""
    reply, sources = answer_with_rag(user_id=user_id, doc_id=doc_id, question=question, top_k=top_k)
    return {"reply": reply, "sources": sources}


@tool
def extract_knowledge_from_chunk(text: str):
    """从一段文档文本中发现、过滤并排序有学习价值的知识点。"""
    return {"knowledge_points": discover_knowledge_points(text)}


@tool
def get_knowledge_status_batch(user_id: str, kp_texts: list[str]):
    """批量读取知识点的学习状态和点击次数。"""
    return get_status_batch(user_id, kp_texts)


@tool
def record_knowledge_click(user_id: str, kp_text: str, kp_type: str):
    """记录用户点击某个知识点，并更新学习状态。"""
    return record_click(user_id=user_id, kp_text=kp_text, kp_type=kp_type)


@tool
def mark_knowledge_known(user_id: str, kp_text: str, kp_type: str):
    """将某个知识点标记为已掌握。"""
    return mark_known(user_id=user_id, kp_text=kp_text, kp_type=kp_type)


@tool
def unmark_knowledge_known(user_id: str, kp_text: str):
    """取消某个知识点的已掌握状态。"""
    return unmark_known(user_id=user_id, kp_text=kp_text)


@tool
def get_learning_stats(user_id: str):
    """读取当前用户所有知识点学习状态的聚合统计。"""
    return get_stats(user_id)


@tool
def explain_knowledge_with_context(keyword: str, kp_type: str, context: str):
    """基于知识点名称、类型和上下文生成深入解释。"""
    explanation = "".join(
        stream_deep_explanation(
            keyword=keyword,
            kp_type=kp_type,
            context=context,
        )
    )
    return {"explanation": explanation}


@tool
def extract_document_structure(text: str):
    """从文档内容中抽取主题、章节层级、部分摘要和建议学习顺序。"""
    messages = [
        {"role": "system", "content": DOCUMENT_STRUCTURE_PROMPT},
        {"role": "user", "content": f"请分析以下文档内容的结构：\n\n{text}"},
    ]
    raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
    return safe_parse_json(raw_reply)


@tool
def generate_practice(
    context: str,
    question_count: int = 5,
    difficulty: str = "medium",
    practice_type: str = "mixed",
):
    """基于文档上下文生成自测题、应用题、对比题或复述提示。"""
    question_count = max(1, min(int(question_count), 10))
    messages = [
        {"role": "system", "content": PRACTICE_GENERATION_PROMPT},
        {
            "role": "user",
            "content": (
                f"练习数量：{question_count}\n"
                f"难度：{difficulty}\n"
                f"练习类型：{practice_type}\n\n"
                f"【文档内容】\n{context}"
            ),
        },
    ]
    raw_reply = call_deepseek(messages, temperature=0.25, json_mode=True)
    return safe_parse_json(raw_reply)


@tool
def grade_answer(question: str, user_answer: str, reference_context: str):
    """基于文档依据批改用户答案并给出反馈。"""
    messages = [
        {"role": "system", "content": ANSWER_GRADING_PROMPT},
        {
            "role": "user",
            "content": (
                f"【题目】\n{question}\n\n"
                f"【用户答案】\n{user_answer}\n\n"
                f"【文档依据】\n{reference_context}"
            ),
        },
    ]
    raw_reply = call_deepseek(messages, temperature=0.1, json_mode=True)
    return safe_parse_json(raw_reply)


@tool
def map_knowledge_relations(context: str, knowledge_points: list[str] | None = None):
    """分析文档知识点之间的前置、支撑、对比、例子、组成等关系。"""
    kp_text = "\n".join(f"- {item}" for item in (knowledge_points or [])) or "未提供，请从上下文中自行识别关键知识点。"
    messages = [
        {"role": "system", "content": RELATION_MAPPING_PROMPT},
        {
            "role": "user",
            "content": f"【知识点列表】\n{kp_text}\n\n【文档上下文】\n{context}",
        },
    ]
    raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
    return safe_parse_json(raw_reply)


@tool
def schedule_review(
    context: str,
    learning_stats: dict | None = None,
    knowledge_status: list[dict] | None = None,
):
    """根据文档上下文和学习状态生成复习优先级、复习时间和下一步动作建议。"""
    messages = [
        {"role": "system", "content": REVIEW_SCHEDULE_PROMPT},
        {
            "role": "user",
            "content": (
                f"【学习统计】\n{learning_stats or {}}\n\n"
                f"【知识点状态】\n{knowledge_status or []}\n\n"
                f"【文档上下文】\n{context}"
            ),
        },
    ]
    raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
    return safe_parse_json(raw_reply)
