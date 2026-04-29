import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DB_PATH = os.path.join(os.path.dirname(__file__), "user_data.db")

if not DEEPSEEK_API_KEY:
    raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")


# ========== 数据库 ==========

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_knowledge (
                kp_text TEXT PRIMARY KEY,
                kp_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unknown',
                click_count INTEGER NOT NULL DEFAULT 0,
                last_clicked_at TEXT,
                marked_known_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


init_db()


# ========== FastAPI ==========

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
    chunk_id: str

class KnowledgePoint(BaseModel):
    text: str
    type: str
    explanation: str

class ExtractResponse(BaseModel):
    chunk_id: str
    knowledge_points: List[KnowledgePoint]

class ExplainDeepRequest(BaseModel):
    keyword: str
    kp_type: str
    context: str

class ClickRequest(BaseModel):
    kp_text: str
    kp_type: str

class MarkKnownRequest(BaseModel):
    kp_text: str
    kp_type: str

class UnmarkKnownRequest(BaseModel):
    kp_text: str

class KnowledgeStatus(BaseModel):
    kp_text: str
    status: str
    click_count: int

class StatusBatchRequest(BaseModel):
    kp_texts: List[str]


# ========== LLM 调用 ==========

def call_deepseek(messages: list, temperature: float = 0.3, json_mode: bool = False) -> str:
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


def call_deepseek_stream(messages: list, temperature: float = 0.5):
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "stream": True
    }

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=60) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except requests.exceptions.RequestException as e:
        yield f"\n\n[错误] LLM 调用失败: {str(e)}"


# ========== 缓存 ==========
_extract_cache = {}


# ========== 知识点提取 ==========

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


@app.post("/api/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(request: ExtractRequest):
    chunk_id = request.chunk_id
    text = request.text.strip()

    if chunk_id in _extract_cache:
        return ExtractResponse(
            chunk_id=chunk_id,
            knowledge_points=_extract_cache[chunk_id]
        )

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请从以下文本中提取知识点:\n\n{text}"}
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

        return ExtractResponse(
            chunk_id=chunk_id,
            knowledge_points=knowledge_points
        )
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回的 JSON 格式错误: {str(e)}")


# ========== 深度讲解(流式) ==========

EXPLAIN_DEEP_SYSTEM_PROMPT = """你是一位专业、耐心的备考辅导老师。你的任务是为学生深入讲解某个知识点,帮助他们真正理解并能在考试中应用。

讲解原则:
1. 先用一句通俗易懂的话给出定义,避免堆砌术语
2. 解释这个知识点为什么重要、考试中常考什么角度
3. 如果是公式,逐一解释每个符号的含义和单位
4. 如果是术语,可以用类比、举例帮助理解
5. 指出常见的混淆点或易错点(如果有的话)
6. 篇幅控制在 200-400 字之间,不要太长
7. 用清晰的小段落组织,适当使用 Markdown 格式(如加粗关键词)
8. 用亲切自然的语气,像朋友在讲解,而不是机械地复读教科书"""


@app.post("/api/explain-deep")
def explain_deep(request: ExplainDeepRequest):
    keyword = request.keyword.strip()
    kp_type = request.kp_type
    context = request.context.strip()

    type_label = "公式/定理" if kp_type == "formula" else "术语/概念"

    user_message = f"""学生在学习时点击了一个{type_label}:「{keyword}」

它出现在以下段落中:
\"\"\"
{context}
\"\"\"

请深入讲解这个知识点,帮助学生真正理解。"""

    messages = [
        {"role": "system", "content": EXPLAIN_DEEP_SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

    def generate():
        for chunk in call_deepseek_stream(messages, temperature=0.5):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ========== 用户记忆系统 ==========

LEARNING_THRESHOLD = 3  # 点击多少次进入 learning 状态


@app.post("/api/knowledge/click")
def record_click(request: ClickRequest):
    """记录一次知识点点击,自动更新状态"""
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        # 查询现有记录
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (request.kp_text,)
        ).fetchone()
        
        if row is None:
            # 新建记录
            conn.execute("""
                INSERT INTO user_knowledge 
                (kp_text, kp_type, status, click_count, last_clicked_at, created_at)
                VALUES (?, ?, 'unknown', 1, ?, ?)
            """, (request.kp_text, request.kp_type, now, now))
            new_count = 1
            new_status = 'unknown'
        else:
            new_count = row['click_count'] + 1
            # 已掌握的状态不会因点击降级
            if row['status'] == 'known':
                new_status = 'known'
            elif new_count >= LEARNING_THRESHOLD:
                new_status = 'learning'
            else:
                new_status = 'unknown'
            
            conn.execute("""
                UPDATE user_knowledge 
                SET click_count = ?, last_clicked_at = ?, status = ?
                WHERE kp_text = ?
            """, (new_count, now, new_status, request.kp_text))
        
        conn.commit()
    
    return {"kp_text": request.kp_text, "status": new_status, "click_count": new_count}


@app.post("/api/knowledge/mark-known")
def mark_known(request: MarkKnownRequest):
    """标记知识点为已掌握"""
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (request.kp_text,)
        ).fetchone()
        
        if row is None:
            conn.execute("""
                INSERT INTO user_knowledge 
                (kp_text, kp_type, status, click_count, marked_known_at, created_at)
                VALUES (?, ?, 'known', 0, ?, ?)
            """, (request.kp_text, request.kp_type, now, now))
        else:
            conn.execute("""
                UPDATE user_knowledge 
                SET status = 'known', marked_known_at = ?
                WHERE kp_text = ?
            """, (now, request.kp_text))
        
        conn.commit()
    
    return {"kp_text": request.kp_text, "status": "known"}


@app.post("/api/knowledge/unmark-known")
def unmark_known(request: UnmarkKnownRequest):
    """取消已掌握标记,回到 unknown 或 learning 状态"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (request.kp_text,)
        ).fetchone()
        
        if row is None:
            return {"kp_text": request.kp_text, "status": "unknown"}
        
        # 根据 click_count 判断回到哪个状态
        new_status = 'learning' if row['click_count'] >= LEARNING_THRESHOLD else 'unknown'
        conn.execute("""
            UPDATE user_knowledge 
            SET status = ?, marked_known_at = NULL
            WHERE kp_text = ?
        """, (new_status, request.kp_text))
        conn.commit()
    
    return {"kp_text": request.kp_text, "status": new_status}


@app.post("/api/knowledge/status-batch")
def get_status_batch(request: StatusBatchRequest):
    """批量查询知识点状态"""
    if not request.kp_texts:
        return {"items": []}
    
    with get_db() as conn:
        placeholders = ','.join(['?'] * len(request.kp_texts))
        rows = conn.execute(
            f"SELECT kp_text, status, click_count FROM user_knowledge WHERE kp_text IN ({placeholders})",
            request.kp_texts
        ).fetchall()
    
    items = [
        {"kp_text": row['kp_text'], "status": row['status'], "click_count": row['click_count']}
        for row in rows
    ]
    return {"items": items}


@app.get("/api/knowledge/stats")
def get_stats():
    """学习总览统计"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) as count 
            FROM user_knowledge 
            GROUP BY status
        """).fetchall()
    
    stats = {"unknown": 0, "learning": 0, "known": 0}
    for row in rows:
        stats[row['status']] = row['count']
    return stats


@app.post("/api/knowledge/reset")
def reset_all():
    """清空所有学习记录(测试用)"""
    with get_db() as conn:
        conn.execute("DELETE FROM user_knowledge")
        conn.commit()
    return {"message": "已重置所有学习记录"}


# ========== 健康检查与测试接口 ==========

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