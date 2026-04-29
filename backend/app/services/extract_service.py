import json

from fastapi import HTTPException

from app.schemas.knowledge import ExtractResponse, KnowledgePoint
from app.services.llm_service import call_deepseek


EXTRACT_SYSTEM_PROMPT = """你是一个专业的备考辅导助手。你的任务是从学习材料中提取核心知识点,帮助学生抓住重点。

提取规则:
1. 只提取真正需要记忆或理解的核心内容,主要是两类:
   - "term": 专业名词、术语、关键概念
   - "formula": 公式、定理、定律的表达式
2. 不要提取常识词汇或过于宽泛的词
3. 知识点的 text 字段必须是原文中出现的原词原句,不要改写或翻译
4. 每段提取的知识点不超过 12 个,优先选最重要的
5. 如果文本太短或没有值得提取的内容,返回空数组
6. 解释要简洁,2-3 句话说清楚是什么、为什么重要

输出严格的 JSON 格式:
{
  "knowledge_points": [
    {
      "text": "原文中的原词",
      "type": "term",
      "explanation": "2-3 句简洁解释"
    }
  ]
}"""


_extract_cache = {}


def extract_knowledge_from_text(chunk_id: str, text: str) -> ExtractResponse:
    text = text.strip()

    if chunk_id in _extract_cache:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=_extract_cache[chunk_id])

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请从以下文本中提取知识点:\n\n{text}"},
    ]

    try:
        raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
        parsed = json.loads(raw_reply)
        kps_data = parsed.get("knowledge_points", [])

        knowledge_points = []
        for kp in kps_data:
            if not isinstance(kp, dict):
                continue
            if not all(k in kp for k in ["text", "type", "explanation"]):
                continue
            if kp["type"] not in ["term", "formula"]:
                continue
            if kp["text"] not in text:
                continue
            knowledge_points.append(KnowledgePoint(**kp))

        _extract_cache[chunk_id] = knowledge_points
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回的 JSON 格式错误: {str(e)}")
