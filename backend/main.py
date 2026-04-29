import os
import json
import hashlib
import requests
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

if not DEEPSEEK_API_KEY:
    raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")

app = FastAPI(title="AI 学习助手后端")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 数据模型 ==========

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

class ExtractRequest(BaseModel):
    text: str
    chunk_id: str  # 用于缓存

class KnowledgePoint(BaseModel):
    text: str          # 原文中的术语/公式
    type: str          # "term" 或 "formula"
    explanation: str   # 2-3 句解释

class ExtractResponse(BaseModel):
    chunk_id: str
    knowledge_points: List[KnowledgePoint]


# ========== LLM 调用 ==========

def call_deepseek(messages: list, temperature: float = 0.3, json_mode: bool = False) -> str:
    """调用 DeepSeek API"""
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {str(e)}")
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回格式异常: {str(e)}")


# ========== 简单内存缓存 ==========
# key: chunk_id, value: 提取结果
_extract_cache = {}


# ========== 知识点提取 ==========

EXTRACT_SYSTEM_PROMPT = """你是一个专业的备考辅导助手。你的任务是从学习材料中提取核心知识点，帮助学生抓住重点。

提取规则：
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


@app.post("/api/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(request: ExtractRequest):
    """从文本块中提取知识点"""
    chunk_id = request.chunk_id
    text = request.text.strip()
    
    # 检查缓存
    if chunk_id in _extract_cache:
        return ExtractResponse(
            chunk_id=chunk_id,
            knowledge_points=_extract_cache[chunk_id]
        )
    
    # 太短的文本跳过
    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])
    
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请从以下文本中提取知识点：\n\n{text}"}
    ]
    
    try:
        raw_reply = call_deepseek(messages, temperature=0.2, json_mode=True)
        parsed = json.loads(raw_reply)
        kps_data = parsed.get("knowledge_points", [])
        
        # 验证并构造知识点对象
        knowledge_points = []
        for kp in kps_data:
            if not isinstance(kp, dict):
                continue
            if not all(k in kp for k in ["text", "type", "explanation"]):
                continue
            if kp["type"] not in ["term", "formula"]:
                continue
            # 知识点必须出现在原文中
            if kp["text"] not in text:
                continue
            knowledge_points.append(KnowledgePoint(**kp))
        
        # 写入缓存
        _extract_cache[chunk_id] = knowledge_points
        
        return ExtractResponse(
            chunk_id=chunk_id,
            knowledge_points=knowledge_points
        )
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回的 JSON 格式错误: {str(e)}")


# ========== 原有接口 ==========

@app.get("/")
def root():
    return {"status": "ok", "message": "AI 学习助手后端运行中"}


@app.post("/api/test-llm", response_model=ChatResponse)
def test_llm(request: ChatRequest):
    messages = [{"role": "user", "content": request.message}]
    reply = call_deepseek(messages)
    return ChatResponse(reply=reply)


# ========== 启动入口 ==========

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)