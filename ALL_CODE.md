# AI Study Tool - All Code

> Generated from source files. Binary docs/images and package-lock are excluded.

## README.md

```markdown
# AI 学习助手

> 一款面向学生备考场景的 AI 文档学习工具，能从 docx 文档中自动提取核心知识点，通过高亮 + 智能讲解帮助用户高效学习。

## ✨ 功能特性

- 📄 **docx 文档加载**：上传 Word 文档，前端实时解析渲染
- 🤖 **智能提取知识点**：通过 LLM 自动识别文档中的核心术语和公式
- 🎨 **原文高亮**：知识点在文档中以颜色标注，一目了然
- 💬 **单击看简介**：点击高亮立刻显示 2-3 句精简解释
- 📚 **双击深度讲解**：流式输出详细讲解，逐字呈现
- 🧠 **学习记忆系统**：自动追踪学习进度，支持"已掌握"标记
- 👁️ **隐藏已掌握**：聚焦未学习内容，避免重复打扰
- 💾 **跨文档持久化**：学习记录保存在本地，多次使用不丢失

## 🛠️ 技术栈

### 前端
- **React 18** + **Vite**：开发框架与构建工具
- **mammoth.js**：docx 文档解析
- **TreeWalker API**：文本高亮的 DOM 操作
- **Fetch API + 流式读取**：对接 LLM 流式输出

### 后端
- **Python 3.10+** + **FastAPI**：Web 框架
- **SQLite**：用户学习记录存储
- **DeepSeek API**：大语言模型服务

## 📦 项目结构

\`\`\`
ai-study-tool/
├── frontend/              # React 前端
│   ├── src/
│   │   ├── app/          # 应用入口组件
│   │   ├── api/          # 后端 API 调用封装
│   │   ├── features/     # 文档、知识点等业务模块
│   │   ├── styles/       # 全局/页面样式
│   │   ├── types/        # 前端常量与类型约定
│   │   ├── utils/        # 通用工具函数
│   │   └── main.jsx      # React 挂载入口
│   ├── package.json
│   └── vite.config.js
├── backend/               # FastAPI 后端
│   ├── main.py           # 兼容 uvicorn main:app 的启动入口
│   ├── app/
│   │   ├── main.py       # FastAPI 应用工厂与路由注册
│   │   ├── core/         # 配置、数据库连接
│   │   ├── models/       # 领域常量/模型
│   │   ├── schemas/      # Pydantic 请求响应模型
│   │   ├── services/     # LLM、提取、学习状态等业务逻辑
│   │   └── routers/      # API 路由分组
│   ├── venv/             # Python 虚拟环境(已 gitignore)
│   ├── .env              # API Key(已 gitignore)
│   └── user_data.db      # SQLite 数据库(已 gitignore)
├── test-docs/             # 测试用 docx 文档
├── .gitignore
└── README.md
\`\`\`

## 🚀 快速开始

### 前置要求

- Node.js ≥ 18
- Python ≥ 3.10
- DeepSeek API Key（[去注册](https://platform.deepseek.com)）

### 1. 克隆/进入项目

\`\`\`bash
cd /path/to/ai-study-tool
\`\`\`

### 2. 配置后端

\`\`\`bash
cd backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 安装依赖
pip install fastapi uvicorn python-dotenv requests
\`\`\`

在 `backend/` 目录下创建 `.env` 文件：

\`\`\`
DEEPSEEK_API_KEY=你的_DeepSeek_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
\`\`\`

启动后端：

\`\`\`bash
uvicorn main:app --reload --port 8000
\`\`\`

后端运行在 http://localhost:8000

### 3. 配置前端

打开新终端：

\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

前端运行在 http://localhost:5173

### 4. 开始使用

浏览器访问 http://localhost:5173 → 上传一份 docx 文档 → 等待知识点提取完成 → 开始学习

## 📖 使用指南

### 基础交互

| 操作 | 效果 |
|------|------|
| 单击文档高亮 | 右侧显示 2-3 句简介 |
| 双击文档高亮 | 右侧流式生成详细讲解 |
| 单击右侧卡片 | 滚动到文档中对应位置 |
| 双击右侧卡片 | 直接触发详细讲解 |
| 点"标记已掌握" | 该知识点变绿+删除线，不再打扰 |
| 切换"隐藏已掌握" | 已掌握的不显示高亮 |

### 高亮颜色含义

- 🟡 **黄色**：术语（未学习）
- 🟠 **橙色**：公式（未学习）
- 🟡 **浅黄/浅橙**：学习中（已点击 ≥ 3 次）
- 🟢 **绿色 + 删除线**：已掌握

## 🔌 主要 API

| 路径 | 方法 | 用途 |
|------|------|------|
| `/api/extract-knowledge` | POST | 从文本块中提取知识点 |
| `/api/explain-deep` | POST | 流式生成深度讲解 |
| `/api/knowledge/click` | POST | 上报知识点点击 |
| `/api/knowledge/mark-known` | POST | 标记为已掌握 |
| `/api/knowledge/unmark-known` | POST | 取消已掌握 |
| `/api/knowledge/status-batch` | POST | 批量查询学习状态 |
| `/api/knowledge/stats` | GET | 学习总览统计 |
| `/api/knowledge/reset` | POST | 重置所有学习记录 |

完整的接口文档可访问 http://localhost:8000/docs（FastAPI 自动生成的 Swagger UI）。

## 💡 工作原理

### 知识点提取流程

\`\`\`
用户上传 docx
   ↓
mammoth.js 解析为 HTML
   ↓
按段落切分成文本块(每块约 800 字)
   ↓
逐块调用 LLM,要求返回 JSON 格式的知识点列表
   ↓
前端用 TreeWalker API 在原文中精确定位并包裹 <mark> 标签
   ↓
绑定单击/双击事件
\`\`\`

### 学习状态机

\`\`\`
unknown(未学习,默认)
   ↓ 点击 ≥ 3 次
learning(学习中)
   ↓ 用户点"标记已掌握"
known(已掌握)
   ↓ 用户点"取消"
回到 unknown 或 learning
\`\`\`

## 🎯 设计取舍

- **同名知识点全局共享**：基于 `kp_text` 文本作为唯一键，跨文档同步学习状态
- **同一文档同名只高亮一次**：避免视觉污染
- **缓存提取结果**：相同文本块不重复调 LLM，节省成本
- **流式输出**：双击触发的详细讲解逐字呈现，提升体验
- **本地优先**：所有数据存在本地 SQLite，无需注册账号

## 💰 成本估算

使用 DeepSeek API（约 ¥1/百万 tokens）：

- 一份 20 页文档：提取约 ¥0.05-0.10
- 一次详细讲解：约 ¥0.005
- 月成本：轻度使用 ¥10 以内

## 🚧 已知限制

- docx 中的复杂公式（OOXML MathML）暂未渲染，公式以原始文本形式显示
- 不支持 PDF（可将 PDF 转 docx 后使用）
- 知识点提取质量依赖 LLM，偶有遗漏或误判
- 单用户使用，未做账号体系

## 🛣️ 后续规划

- [ ] KaTeX 集成，支持数学公式渲染
- [ ] 学习笔记导出（Markdown）
- [ ] 知识点之间的关联推荐
- [ ] 复习提醒（间隔重复算法）
- [ ] 多文档管理面板
- [ ] PDF 支持

## 📝 开发说明

### 启动开发环境

\`\`\`bash
# 终端 1: 后端
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# 终端 2: 前端
cd frontend
npm run dev
\`\`\`

### 重置学习数据

\`\`\`bash
# 方法 1: 删除数据库文件
rm backend/user_data.db
# 重启后端会自动重建

# 方法 2: 调接口
curl -X POST http://localhost:8000/api/knowledge/reset
\`\`\`

### 调试技巧

- 浏览器控制台查看知识点提取/匹配日志
- 后端终端查看 LLM 请求与响应
- 访问 http://localhost:8000/docs 直接测试 API

## 📄 License

仅供学习使用。

## 🙏 致谢

- 模型服务：[DeepSeek](https://platform.deepseek.com)
- docx 解析：[mammoth.js](https://github.com/mwilliamson/mammoth.js)
- Web 框架：[FastAPI](https://fastapi.tiangolo.com) + [Vite](https://vitejs.dev) + [React](https://react.dev)

---

由 AI 辅助开发，作为 MVP 学习项目。

```

## backend/main.py

```python
from app.main import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

```

## backend/app/services/extract_service.py

```python
import json
from datetime import datetime

from fastapi import HTTPException

from app.core.database import get_db
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


def _load_from_sqlite(chunk_id: str) -> list | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT result_json FROM extract_cache WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["result_json"])
    return [KnowledgePoint(**kp) for kp in data]


def _save_to_sqlite(chunk_id: str, knowledge_points: list):
    now = datetime.utcnow().isoformat()
    result_json = json.dumps([kp.model_dump() for kp in knowledge_points], ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO extract_cache (chunk_id, result_json, created_at) VALUES (?, ?, ?)",
            (chunk_id, result_json, now),
        )
        conn.commit()


def extract_knowledge_from_text(chunk_id: str, text: str) -> ExtractResponse:
    text = text.strip()

    # 1. 查内存缓存
    if chunk_id in _extract_cache:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=_extract_cache[chunk_id])

    # 2. 查 SQLite 持久化缓存
    cached = _load_from_sqlite(chunk_id)
    if cached is not None:
        _extract_cache[chunk_id] = cached
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=cached)

    if len(text) < 30:
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=[])

    # 3. 未命中 → 调 LLM
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

        # 写入两级缓存
        _extract_cache[chunk_id] = knowledge_points
        _save_to_sqlite(chunk_id, knowledge_points)
        return ExtractResponse(chunk_id=chunk_id, knowledge_points=knowledge_points)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回的 JSON 格式错误: {str(e)}")

```

## backend/app/services/explain_service.py

```python
from app.services.llm_service import call_deepseek_stream


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


def stream_deep_explanation(keyword: str, kp_type: str, context: str):
    type_label = "公式/定理" if kp_type == "formula" else "术语/概念"
    user_message = f"""学生在学习时点击了一个{type_label}:「{keyword}」

它出现在以下段落中:
\"\"\"
{context}
\"\"\"

请深入讲解这个知识点,帮助学生真正理解。"""

    messages = [
        {"role": "system", "content": EXPLAIN_DEEP_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    yield from call_deepseek_stream(messages, temperature=0.5)

```

## backend/app/services/llm_service.py

```python
import json

import requests
from fastapi import HTTPException

from app.core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL


def call_deepseek(messages: list, temperature: float = 0.3, json_mode: bool = False) -> str:
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
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
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "stream": True,
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

```

## backend/app/services/knowledge_service.py

```python
from datetime import datetime

from app.core.database import get_db
from app.models.knowledge import LEARNING_THRESHOLD, STATUS_KNOWN, STATUS_LEARNING, STATUS_UNKNOWN


def record_click(kp_text: str, kp_type: str):
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            conn.execute("""
                INSERT INTO user_knowledge
                (kp_text, kp_type, status, click_count, last_clicked_at, created_at)
                VALUES (?, ?, 'unknown', 1, ?, ?)
            """, (kp_text, kp_type, now, now))
            new_count = 1
            new_status = STATUS_UNKNOWN
        else:
            new_count = row["click_count"] + 1
            if row["status"] == STATUS_KNOWN:
                new_status = STATUS_KNOWN
            elif new_count >= LEARNING_THRESHOLD:
                new_status = STATUS_LEARNING
            else:
                new_status = STATUS_UNKNOWN

            conn.execute("""
                UPDATE user_knowledge
                SET click_count = ?, last_clicked_at = ?, status = ?
                WHERE kp_text = ?
            """, (new_count, now, new_status, kp_text))

        conn.commit()

    return {"kp_text": kp_text, "status": new_status, "click_count": new_count}


def mark_known(kp_text: str, kp_type: str):
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            conn.execute("""
                INSERT INTO user_knowledge
                (kp_text, kp_type, status, click_count, marked_known_at, created_at)
                VALUES (?, ?, 'known', 0, ?, ?)
            """, (kp_text, kp_type, now, now))
        else:
            conn.execute("""
                UPDATE user_knowledge
                SET status = 'known', marked_known_at = ?
                WHERE kp_text = ?
            """, (now, kp_text))

        conn.commit()

    return {"kp_text": kp_text, "status": STATUS_KNOWN}


def unmark_known(kp_text: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_knowledge WHERE kp_text = ?",
            (kp_text,),
        ).fetchone()

        if row is None:
            return {"kp_text": kp_text, "status": STATUS_UNKNOWN}

        new_status = STATUS_LEARNING if row["click_count"] >= LEARNING_THRESHOLD else STATUS_UNKNOWN
        conn.execute("""
            UPDATE user_knowledge
            SET status = ?, marked_known_at = NULL
            WHERE kp_text = ?
        """, (new_status, kp_text))
        conn.commit()

    return {"kp_text": kp_text, "status": new_status}


def get_status_batch(kp_texts: list[str]):
    if not kp_texts:
        return {"items": []}

    with get_db() as conn:
        placeholders = ",".join(["?"] * len(kp_texts))
        rows = conn.execute(
            f"SELECT kp_text, status, click_count FROM user_knowledge WHERE kp_text IN ({placeholders})",
            kp_texts,
        ).fetchall()

    items = [
        {"kp_text": row["kp_text"], "status": row["status"], "click_count": row["click_count"]}
        for row in rows
    ]
    return {"items": items}


def get_stats():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM user_knowledge
            GROUP BY status
        """).fetchall()

    stats = {STATUS_UNKNOWN: 0, STATUS_LEARNING: 0, STATUS_KNOWN: 0}
    for row in rows:
        stats[row["status"]] = row["count"]
    return stats


def reset_all():
    with get_db() as conn:
        conn.execute("DELETE FROM user_knowledge")
        conn.commit()
    return {"message": "已重置所有学习记录"}

```

## backend/app/services/__init__.py

```python


```

## backend/app/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, validate_settings
from app.core.database import init_db
from app.routers import explain, extract, health, knowledge


def create_app() -> FastAPI:
    validate_settings()
    init_db()

    app = FastAPI(title="AI 学习助手后端")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(extract.router)
    app.include_router(explain.router)
    app.include_router(knowledge.router)
    return app


app = create_app()

```

## backend/app/schemas/knowledge.py

```python
from typing import List

from pydantic import BaseModel


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

```

## backend/app/schemas/__init__.py

```python


```

## backend/app/models/knowledge.py

```python
LEARNING_THRESHOLD = 3

STATUS_UNKNOWN = "unknown"
STATUS_LEARNING = "learning"
STATUS_KNOWN = "known"

```

## backend/app/models/__init__.py

```python


```

## backend/app/__init__.py

```python


```

## backend/app/core/__init__.py

```python


```

## backend/app/core/database.py

```python
import sqlite3
from contextlib import contextmanager

from app.core.config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extract_cache (
                chunk_id TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

```

## backend/app/core/config.py

```python
import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DB_PATH = BACKEND_DIR / "user_data.db"
ALLOWED_ORIGINS = ["http://localhost:5173"]


def validate_settings():
    if not DEEPSEEK_API_KEY:
        raise ValueError("请在 .env 文件中配置 DEEPSEEK_API_KEY")

```

## backend/app/routers/extract.py

```python
from fastapi import APIRouter

from app.schemas.knowledge import ExtractRequest, ExtractResponse
from app.services.extract_service import extract_knowledge_from_text


router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract-knowledge", response_model=ExtractResponse)
def extract_knowledge(request: ExtractRequest):
    return extract_knowledge_from_text(request.chunk_id, request.text)

```

## backend/app/routers/explain.py

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.knowledge import ExplainDeepRequest
from app.services.explain_service import stream_deep_explanation


router = APIRouter(prefix="/api", tags=["explain"])


@router.post("/explain-deep")
def explain_deep(request: ExplainDeepRequest):
    stream = stream_deep_explanation(
        keyword=request.keyword.strip(),
        kp_type=request.kp_type,
        context=request.context.strip(),
    )
    return StreamingResponse(stream, media_type="text/plain; charset=utf-8")

```

## backend/app/routers/knowledge.py

```python
from fastapi import APIRouter

from app.schemas.knowledge import ClickRequest, MarkKnownRequest, StatusBatchRequest, UnmarkKnownRequest
from app.services import knowledge_service


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/click")
def record_click(request: ClickRequest):
    return knowledge_service.record_click(request.kp_text, request.kp_type)


@router.post("/mark-known")
def mark_known(request: MarkKnownRequest):
    return knowledge_service.mark_known(request.kp_text, request.kp_type)


@router.post("/unmark-known")
def unmark_known(request: UnmarkKnownRequest):
    return knowledge_service.unmark_known(request.kp_text)


@router.post("/status-batch")
def get_status_batch(request: StatusBatchRequest):
    return knowledge_service.get_status_batch(request.kp_texts)


@router.get("/stats")
def get_stats():
    return knowledge_service.get_stats()


@router.post("/reset")
def reset_all():
    return knowledge_service.reset_all()

```

## backend/app/routers/__init__.py

```python


```

## backend/app/routers/health.py

```python
from fastapi import APIRouter

from app.schemas.knowledge import ChatRequest, ChatResponse
from app.services.llm_service import call_deepseek


router = APIRouter(tags=["health"])


@router.get("/")
def root():
    return {"status": "ok", "message": "AI 学习助手后端运行中"}


@router.post("/api/test-llm", response_model=ChatResponse)
def test_llm(request: ChatRequest):
    messages = [{"role": "user", "content": request.message}]
    reply = call_deepseek(messages)
    return ChatResponse(reply=reply)

```

## frontend/src/api/knowledge.js

```javascript
import { API_BASE, postJson } from './client'


export function extractKnowledge(text, chunkId) {
  return postJson('/api/extract-knowledge', { text, chunk_id: chunkId })
}


export function fetchKnowledgeStatuses(kpTexts) {
  return postJson('/api/knowledge/status-batch', { kp_texts: kpTexts })
}


export function recordKnowledgeClick(kp) {
  return postJson('/api/knowledge/click', { kp_text: kp.text, kp_type: kp.type })
}


export function markKnowledgeKnown(kp) {
  return postJson('/api/knowledge/mark-known', { kp_text: kp.text, kp_type: kp.type })
}


export function unmarkKnowledgeKnown(kp) {
  return postJson('/api/knowledge/unmark-known', { kp_text: kp.text, kp_type: kp.type })
}


export function requestDeepExplanation(kp, context, signal) {
  return fetch(`${API_BASE}/api/explain-deep`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword: kp.text, kp_type: kp.type, context }),
    signal,
  })
}

```

## frontend/src/api/client.js

```javascript
export const API_BASE = 'http://localhost:8000'


export async function postJson(path, body, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...options,
  })

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  return response.json()
}

```

## frontend/src/main.jsx

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './app/App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

```

## frontend/src/styles/App.css

```css
/* ========== CSS 变量 ========== */
:root {
  --sidebar-bg: rgb(255, 255, 255);
  --sidebar-border: #E9E9E9;
  --sidebar-text: #6B6B6B;
  --sidebar-text-active: #1A1A1A;
  --sidebar-hover: rgb(245, 245, 245);
  --sidebar-active-bg: rgb(245, 245, 245);
  --sidebar-accent: #E87040;

  --header-bg: #FFFFFF;
  --header-border: #EBEBEB;

  --main-bg: rgb(254, 254, 254);
  --doc-bg: rgb(254, 254, 254);
  --panel-bg: rgb(253, 253, 252);
  --panel-border: #EBEBEB;

  --text-primary: #1C1917;
  --text-secondary: #78716C;
  --text-muted: #A8A29E;

  --accent: #E87040;
  --accent-hover: #CF5F2E;
  --accent-light: #FEF3EC;

  --border: #E7E3DE;
  --border-strong: #D6CFC8;

  --radius-sm: 5px;
  --radius-md: 8px;
  --radius-lg: 12px;

  --toc-width: 240px;
  --header-height: 52px;
  --kp-width: 320px;
}

/* ========== 全局 Reset ========== */
*, *::before, *::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "PingFang SC",
    "Microsoft YaHei", "Segoe UI", sans-serif;
  background: var(--main-bg);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}

/* ========== 整体 Grid 布局 ========== */
.app {
  display: grid;
  grid-template-columns: var(--toc-width) 1fr var(--kp-width);
  grid-template-rows: var(--header-height) 1fr;
  height: 100vh;
  overflow: hidden;
  transition: grid-template-columns 0.25s ease;
}

.app.toc-collapsed {
  grid-template-columns: 52px 1fr var(--kp-width);
}

/* ========== 左侧 Logo/Header 区域 ========== */
.sidebar-header {
  grid-column: 1;
  grid-row: 1;
  background: var(--sidebar-bg);
  border-bottom: 1px solid var(--sidebar-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  overflow: hidden;
  flex-shrink: 0;
}

.app-logo {
  color: var(--sidebar-accent);
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toc-toggle-btn {
  background: transparent;
  border: none;
  color: var(--sidebar-text);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 6px 4px;
  border-radius: var(--radius-sm);
  transition: color 0.15s, background 0.15s;
  flex-shrink: 0;
  line-height: 1;
}

.toc-toggle-btn:hover {
  color: var(--sidebar-text-active);
  background: var(--sidebar-hover);
}

/* ========== 主区域 Header ========== */
.main-header {
  grid-column: 2 / 4;
  grid-row: 1;
  background: var(--header-bg);
  border-bottom: 1px solid var(--header-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  gap: 12px;
  overflow: hidden;
}

.header-file {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.file-name {
  font-size: 0.875rem;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-hint {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.extract-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--accent-light);
  color: var(--accent);
  font-size: 0.75rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
  white-space: nowrap;
  flex-shrink: 0;
}

.extract-badge::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--accent);
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.toggle-label input[type="checkbox"] {
  accent-color: var(--accent);
  cursor: pointer;
}

.upload-button {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.15s;
  user-select: none;
}

.upload-button:hover {
  background: var(--accent-hover);
}

/* ========== 目录侧边栏 ========== */
.toc-sidebar {
  grid-column: 1;
  grid-row: 2;
  background: var(--sidebar-bg);
  overflow-y: auto;
  overflow-x: hidden;
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
}

.toc-sidebar::-webkit-scrollbar {
  width: 4px;
}
.toc-sidebar::-webkit-scrollbar-track {
  background: transparent;
}
.toc-sidebar::-webkit-scrollbar-thumb {
  background: #D4D4D4;
  border-radius: 2px;
}

.toc-section-title {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--sidebar-text);
  opacity: 0.6;
  padding: 16px 14px 8px;
  flex-shrink: 0;
}

.toc-nav {
  flex: 1;
  padding: 4px 0 16px;
}

.toc-empty {
  font-size: 0.8rem;
  color: var(--sidebar-text);
  opacity: 0.5;
  padding: 12px 14px;
  line-height: 1.6;
  white-space: pre-line;
}

/* 目录项 */
.toc-item {
  display: block;
  padding: 5px 14px;
  font-size: 0.82rem;
  color: var(--sidebar-text);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-left: 2px solid transparent;
  transition: color 0.12s, background 0.12s, border-color 0.12s;
  line-height: 1.5;
}

.toc-item:hover {
  color: var(--sidebar-text-active);
  background: var(--sidebar-hover);
}

.toc-item.toc-active {
  color: var(--sidebar-text-active);
  border-left-color: var(--sidebar-accent);
  background: var(--sidebar-active-bg);
  font-weight: 500;
}

/* 按层级缩进 */
.toc-level-1 { padding-left: 14px; font-weight: 500; font-size: 0.85rem; }
.toc-level-2 { padding-left: 22px; }
.toc-level-3 { padding-left: 32px; font-size: 0.79rem; opacity: 0.85; }
.toc-level-4 { padding-left: 42px; font-size: 0.76rem; opacity: 0.75; }

/* ========== 文档主区域 ========== */
.document-area {
  grid-column: 2;
  grid-row: 2;
  background: var(--doc-bg);
  overflow-y: auto;
  border-right: 1px solid var(--border);
}

.document-area::-webkit-scrollbar {
  width: 6px;
}
.document-area::-webkit-scrollbar-track {
  background: transparent;
}
.document-area::-webkit-scrollbar-thumb {
  background: #D6CFC8;
  border-radius: 3px;
}

/* 欢迎页 */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  padding: 2rem;
  text-align: center;
}

.welcome-icon {
  font-size: 3rem;
  opacity: 0.4;
}

.welcome-text {
  font-size: 1rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.welcome-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.doc-placeholder {
  color: var(--text-muted);
  text-align: center;
  margin-top: 3rem;
  font-size: 0.9rem;
}

.doc-error {
  margin: 2rem;
  padding: 12px 16px;
  background: #FEF2F2;
  color: #B91C1C;
  border: 1px solid #FECACA;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
}

/* 文档内容 */
.document-content {
  max-width: 760px;
  margin: 0 auto;
  padding: 2.5rem 3rem 4rem;
  line-height: 1.85;
  font-size: 15px;
  color: var(--text-primary);
}

.document-content h1,
.document-content h2,
.document-content h3,
.document-content h4 {
  margin: 1.8em 0 0.7em;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text-primary);
  scroll-margin-top: 24px;
}

.document-content h1 { font-size: 1.75em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }
.document-content h2 { font-size: 1.4em; }
.document-content h3 { font-size: 1.15em; }
.document-content h4 { font-size: 1em; }

.document-content p {
  margin: 0.75em 0;
}

.document-content ul,
.document-content ol {
  margin: 0.75em 0;
  padding-left: 1.75em;
}

.document-content li {
  margin: 0.3em 0;
}

.document-content table {
  border-collapse: collapse;
  margin: 1.2em 0;
  width: 100%;
  font-size: 0.9em;
}

.document-content table td,
.document-content table th {
  border: 1px solid var(--border);
  padding: 8px 12px;
}

.document-content table th {
  background: var(--main-bg);
  font-weight: 600;
}

.document-content img {
  max-width: 100%;
  height: auto;
  margin: 1em 0;
  border-radius: var(--radius-sm);
}

/* ========== 知识点高亮 ========== */
.kp-highlight {
  background: #FEF08A;
  padding: 1px 2px;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}

.kp-highlight:hover {
  background: #FDE047;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}

.kp-highlight-formula {
  background: #FED7AA;
}

.kp-highlight-formula:hover {
  background: #FDBA74;
}

.kp-highlight.active {
  background: var(--accent);
  color: #fff;
  font-weight: 500;
}

/* 已掌握状态 */
.document-content mark.kp-status-known {
  background: #DCFCE7;
  color: #86868b;
  text-decoration: line-through;
  text-decoration-color: #BBF7D0;
  text-decoration-thickness: 1px;
}

.document-content mark.kp-status-known:hover {
  background: #BBF7D0;
  color: #555;
}

/* 学习中状态 */
.document-content mark.kp-status-learning {
  background: #FEF9C3;
}

.document-content mark.kp-status-learning.kp-highlight-formula {
  background: #FFEDD5;
}

/* 隐藏已掌握 */
.document-content.hide-known mark.kp-status-known {
  background: transparent;
  color: inherit;
  text-decoration: none;
  cursor: default;
  padding: 0;
}

/* ========== 知识点面板 ========== */
.kp-panel {
  grid-column: 3;
  grid-row: 2;
  background: var(--panel-bg);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--panel-border);
}

.kp-panel::-webkit-scrollbar {
  width: 4px;
}
.kp-panel::-webkit-scrollbar-track {
  background: transparent;
}
.kp-panel::-webkit-scrollbar-thumb {
  background: #D6CFC8;
  border-radius: 2px;
}

.kp-panel-header {
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--panel-border);
  background: var(--panel-bg);
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 1;
}

.kp-panel-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.kp-stats {
  font-size: 0.72rem;
  color: var(--text-muted);
}

/* 选中知识点面板 */
.selected-kp-panel {
  margin: 12px 12px 0;
  background: rgb(244, 244, 241);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  flex-shrink: 0;
}

.selected-kp-header {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 8px;
}

.selected-kp-title {
  flex: 1;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
  margin: 0;
  line-height: 1.4;
}

.selected-kp-content {
  font-size: 0.85rem;
  line-height: 1.65;
  color: var(--text-secondary);
}

/* 操作按钮组 */
.kp-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.deep-btn {
  padding: 5px 12px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 500;
  transition: background 0.15s;
}

.deep-btn:hover {
  background: var(--accent-hover);
}

.known-btn {
  padding: 5px 12px;
  background: #fff;
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 500;
  transition: all 0.15s;
}

.known-btn:hover {
  background: var(--main-bg);
  border-color: #A8A29E;
}

.known-btn.is-known {
  background: #22C55E;
  color: #fff;
  border-color: #22C55E;
}

.known-btn.is-known:hover {
  background: #16A34A;
  border-color: #16A34A;
}

/* 深度讲解面板 */
.deep-panel {
  margin: 10px 12px 0;
  background: rgb(244, 244, 241);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: 0 2px 12px rgba(232,112,64,0.06);
  flex-shrink: 0;
  max-height: 42vh;
  display: flex;
  flex-direction: column;
}

.deep-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.deep-title {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 5px;
}

.deep-content {
  font-size: 0.83rem;
  line-height: 1.75;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
  flex: 1;
}

.deep-content::-webkit-scrollbar {
  width: 3px;
}
.deep-content::-webkit-scrollbar-thumb {
  background: #D6CFC8;
  border-radius: 2px;
}

.placeholder-inline {
  color: var(--text-muted);
  font-style: italic;
  font-size: 0.83rem;
}

/* 关闭按钮 */
.close-btn {
  background: transparent;
  border: none;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 2px;
  flex-shrink: 0;
  transition: color 0.12s;
}

.close-btn:hover {
  color: var(--text-primary);
}

/* 知识点类型标签 */
.kp-type-badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 0.68rem;
  font-weight: 600;
  border-radius: 4px;
  flex-shrink: 0;
}

.kp-term .kp-type-badge,
.kp-type-badge-term {
  background: #EFF6FF;
  color: #2563EB;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 1px;
}

.kp-formula .kp-type-badge,
.kp-type-badge-formula {
  background: #FFF7ED;
  color: #EA580C;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 1px;
}

/* 知识点列表 */
.kp-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px 16px;
  min-height: 0;
}

.placeholder {
  color: var(--text-muted);
  font-size: 0.82rem;
  text-align: center;
  padding: 2rem 1rem;
  line-height: 1.6;
}

/* 知识点卡片 */
.kp-card {
  background: rgb(244, 244, 241);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.kp-card:hover {
  border-color: var(--accent);
  box-shadow: 0 2px 8px rgba(232,112,64,0.1);
}

.kp-card.selected {
  border-color: var(--accent);
  background: var(--accent-light);
}

.kp-card-known {
  opacity: 0.5;
}

.kp-card-known:hover {
  opacity: 1;
}

.kp-card-learning {
  border-left: 3px solid #F59E0B;
}

.kp-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
}

.kp-text {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  word-break: break-word;
  flex: 1;
}

.kp-explanation {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.55;
}

/* 状态图标 */
.status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #22C55E;
  color: #fff;
  font-size: 0.6rem;
  font-weight: bold;
  flex-shrink: 0;
  margin-left: auto;
}

.status-icon.learning {
  background: #F59E0B;
  font-size: 0.45rem;
}

/* ========== 动画 ========== */
.thinking-dot {
  color: var(--accent);
  animation: pulse 1.4s ease-in-out infinite;
  font-size: 0.65rem;
}

.cursor-blink {
  display: inline-block;
  color: var(--accent);
  animation: blink 1s step-end infinite;
  margin-left: 1px;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ========== 滚动条统一 ========== */
.kp-list::-webkit-scrollbar {
  width: 4px;
}
.kp-list::-webkit-scrollbar-track {
  background: transparent;
}
.kp-list::-webkit-scrollbar-thumb {
  background: #D6CFC8;
  border-radius: 2px;
}

```

## frontend/src/index.css

```css
/* 清空，所有样式写在 App.css 里 */
```

## frontend/src/utils/hash.js

```javascript
export function hashString(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}

```

## frontend/src/features/knowledge/highlightDom.js

```javascript
export function highlightFirstMatch(container, keyword, kpId, kpType, status) {
  if (!keyword || !container) return false
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        if (node.parentElement && node.parentElement.tagName === 'MARK') {
          return NodeFilter.FILTER_REJECT
        }
        return NodeFilter.FILTER_ACCEPT
      },
    },
  )
  let textNode
  while ((textNode = walker.nextNode())) {
    const text = textNode.nodeValue
    const idx = text.indexOf(keyword)
    if (idx !== -1) {
      const before = text.slice(0, idx)
      const after = text.slice(idx + keyword.length)
      const mark = document.createElement('mark')
      mark.className = `kp-highlight kp-highlight-${kpType} kp-status-${status || 'unknown'}`
      mark.dataset.kpId = kpId
      mark.dataset.kpText = keyword
      mark.textContent = keyword
      const parent = textNode.parentNode
      if (before) parent.insertBefore(document.createTextNode(before), textNode)
      parent.insertBefore(mark, textNode)
      if (after) parent.insertBefore(document.createTextNode(after), textNode)
      parent.removeChild(textNode)
      return true
    }
  }
  return false
}


export function findContextForKP(container, kpId) {
  if (!container) return ''
  const mark = container.querySelector(`mark[data-kp-id="${kpId}"]`)
  if (!mark) return ''
  let node = mark.parentElement
  const blockTags = ['P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TD', 'DIV']
  while (node && !blockTags.includes(node.tagName)) node = node.parentElement
  return node ? node.textContent.trim() : mark.textContent
}


export function updateMarkStatusInDom(container, kpText, status) {
  if (!container) return
  const marks = container.querySelectorAll(`mark[data-kp-text="${CSS.escape(kpText)}"]`)
  marks.forEach(m => {
    m.classList.remove('kp-status-unknown', 'kp-status-learning', 'kp-status-known')
    m.classList.add(`kp-status-${status}`)
  })
}

```

## frontend/src/features/knowledge/hooks/useKnowledgeStatus.js

```javascript
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  fetchKnowledgeStatuses,
  markKnowledgeKnown,
  recordKnowledgeClick,
  unmarkKnowledgeKnown,
} from '../../../api/knowledge'


export function useKnowledgeStatus(knowledgePoints) {
  const [kpStatusMap, setKpStatusMap] = useState({})

  const getKpStatus = useCallback(
    (kpText) => kpStatusMap[kpText] || 'unknown',
    [kpStatusMap],
  )

  useEffect(() => {
    if (knowledgePoints.length === 0) return
    const texts = knowledgePoints.map(kp => kp.text)
    fetchKnowledgeStatuses(texts)
      .then(data => {
        if (!data) return
        const map = {}
        for (const item of data.items) map[item.kp_text] = item.status
        setKpStatusMap(prev => ({ ...prev, ...map }))
      })
      .catch(err => console.error('拉取状态失败:', err))
  }, [knowledgePoints])

  const recordClick = useCallback(async (kp) => {
    try {
      const data = await recordKnowledgeClick(kp)
      setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
    } catch (err) {
      console.error('上报点击失败:', err)
    }
  }, [])

  const toggleKnown = useCallback(async (kp) => {
    const currentStatus = getKpStatus(kp.text)
    try {
      const data = currentStatus === 'known'
        ? await unmarkKnowledgeKnown(kp)
        : await markKnowledgeKnown(kp)
      setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
    } catch (err) {
      console.error('切换状态失败:', err)
    }
  }, [getKpStatus])

  const stats = useMemo(() => {
    const counts = { unknown: 0, learning: 0, known: 0 }
    for (const kp of knowledgePoints) {
      const status = getKpStatus(kp.text)
      counts[status] = (counts[status] || 0) + 1
    }
    return counts
  }, [knowledgePoints, getKpStatus])

  return {
    kpStatusMap,
    getKpStatus,
    recordClick,
    toggleKnown,
    stats,
  }
}

```

## frontend/src/features/knowledge/hooks/useKnowledgeExtraction.js

```javascript
import { useCallback, useMemo, useRef, useState } from 'react'

import { extractKnowledge } from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


export function useKnowledgeExtraction() {
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extracting, setExtracting] = useState(false)
  const extractingRef = useRef(false)

  const resetExtraction = useCallback(() => {
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const extractAllChunks = useCallback(async (html) => {
    if (extractingRef.current) return
    extractingRef.current = true
    setExtracting(true)
    const chunks = splitIntoChunks(html)
    setExtractProgress({ done: 0, total: chunks.length })
    const allKPs = []

    for (let i = 0; i < chunks.length; i++) {
      const text = chunks[i]
      const chunkId = hashString(text)
      try {
        const data = await extractKnowledge(text, chunkId)
        const kpsWithMeta = data.knowledge_points.map(kp => ({
          ...kp,
          chunkIndex: i,
          id: hashString(kp.text + i),
        }))
        allKPs.push(...kpsWithMeta)
        setKnowledgePoints([...allKPs])
      } catch (err) {
        console.error(`块 ${i} 提取出错:`, err)
      }
      setExtractProgress({ done: i + 1, total: chunks.length })
    }
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const uniqueKPs = useMemo(() => {
    const items = []
    const seenTexts = new Set()
    for (const kp of knowledgePoints) {
      if (!seenTexts.has(kp.text)) {
        seenTexts.add(kp.text)
        items.push(kp)
      }
    }
    return items
  }, [knowledgePoints])

  return {
    extracting,
    extractProgress,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
  }
}

```

## frontend/src/features/knowledge/components/KnowledgeList.jsx

```jsx
function KnowledgeList({
  docLoaded,
  extracting,
  knowledgePoints,
  selectedKP,
  getKpStatus,
  onCardClick,
  onCardDoubleClick,
}) {
  return (
    <div className="kp-list">
      {!docLoaded && <p className="placeholder">上传文档后将自动提取知识点</p>}
      {docLoaded && knowledgePoints.length === 0 && !extracting && (
        <p className="placeholder">暂无提取到的知识点</p>
      )}
      {knowledgePoints.map((kp) => {
        const status = getKpStatus(kp.text)
        return (
          <div
            key={kp.id}
            className={`kp-card kp-${kp.type} kp-card-${status}${selectedKP?.id === kp.id ? ' selected' : ''}`}
            onClick={() => onCardClick(kp)}
            onDoubleClick={() => onCardDoubleClick(kp)}
            title="单击定位 | 双击深入讲解"
          >
            <div className="kp-header">
              <span className="kp-type-badge">
                {kp.type === 'term' ? '术语' : '公式'}
              </span>
              <span className="kp-text">{kp.text}</span>
              {status === 'known' && <span className="status-icon" title="已掌握">✓</span>}
              {status === 'learning' && <span className="status-icon learning" title="学习中">●</span>}
            </div>
            <div className="kp-explanation">{kp.explanation}</div>
          </div>
        )
      })}
    </div>
  )
}

export default KnowledgeList

```

## frontend/src/features/knowledge/components/SelectedKnowledgePanel.jsx

```jsx
function SelectedKnowledgePanel({
  selectedKP,
  showDeep,
  status,
  onClose,
  onStartDeepExplain,
  onToggleKnown,
}) {
  if (!selectedKP) return null

  return (
    <div className="selected-kp-panel">
      <div className="selected-kp-header">
        <span className={`kp-type-badge kp-type-badge-${selectedKP.type}`}>
          {selectedKP.type === 'term' ? '术语' : '公式'}
        </span>
        <h3 className="selected-kp-title">{selectedKP.text}</h3>
        <button className="close-btn" onClick={onClose} title="关闭">×</button>
      </div>
      <div className="selected-kp-content">{selectedKP.explanation}</div>
      <div className="kp-actions">
        {!showDeep && (
          <button className="deep-btn" onClick={() => onStartDeepExplain(selectedKP)}>
            深入讲解
          </button>
        )}
        <button
          className={`known-btn${status === 'known' ? ' is-known' : ''}`}
          onClick={() => onToggleKnown(selectedKP)}
        >
          {status === 'known' ? '✓ 已掌握' : '标记已掌握'}
        </button>
      </div>
    </div>
  )
}

export default SelectedKnowledgePanel

```

## frontend/src/features/knowledge/components/KnowledgePanel.jsx

```jsx
import DeepExplanationPanel from '../../explanation/DeepExplanationPanel'
import KnowledgeList from './KnowledgeList'
import SelectedKnowledgePanel from './SelectedKnowledgePanel'


function KnowledgePanel({
  selectedKP,
  showDeep,
  deepLoading,
  deepExplanation,
  extracting,
  docLoaded,
  knowledgePoints,
  stats,
  getKpStatus,
  onCloseSelected,
  onStartDeepExplain,
  onToggleKnown,
  onCloseDeep,
  onCardClick,
  onCardDoubleClick,
}) {
  return (
    <aside className="kp-panel">
      <SelectedKnowledgePanel
        selectedKP={selectedKP}
        showDeep={showDeep}
        status={selectedKP ? getKpStatus(selectedKP.text) : 'unknown'}
        onClose={onCloseSelected}
        onStartDeepExplain={onStartDeepExplain}
        onToggleKnown={onToggleKnown}
      />

      <DeepExplanationPanel
        showDeep={showDeep}
        deepLoading={deepLoading}
        deepExplanation={deepExplanation}
        onClose={onCloseDeep}
      />

      <div className="kp-panel-header">
        <span className="kp-panel-title">知识点</span>
        {!extracting && knowledgePoints.length > 0 && (
          <span className="kp-stats">
            {stats.known} 掌握 · {stats.learning} 学习中 · {stats.unknown} 未学
          </span>
        )}
      </div>

      <KnowledgeList
        docLoaded={docLoaded}
        extracting={extracting}
        knowledgePoints={knowledgePoints}
        selectedKP={selectedKP}
        getKpStatus={getKpStatus}
        onCardClick={onCardClick}
        onCardDoubleClick={onCardDoubleClick}
      />
    </aside>
  )
}

export default KnowledgePanel

```

## frontend/src/features/document/hooks/useDocumentUpload.js

```javascript
import { useCallback, useState } from 'react'
import mammoth from 'mammoth'


export function useDocumentUpload({ docContentRef, onBeforeLoad, onHtmlLoaded }) {
  const [fileName, setFileName] = useState('')
  const [docLoaded, setDocLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFileUpload = useCallback(async (event) => {
    const file = event.target.files[0]
    if (!file) return
    if (!file.name.endsWith('.docx')) {
      setError('请上传 .docx 格式的文件')
      return
    }

    setError('')
    setLoading(true)
    setFileName(file.name)
    setDocLoaded(false)
    onBeforeLoad()

    if (docContentRef.current) docContentRef.current.innerHTML = ''

    try {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      if (docContentRef.current) docContentRef.current.innerHTML = result.value
      setDocLoaded(true)
      await onHtmlLoaded(result.value)
    } catch (err) {
      setError('文档解析失败：' + err.message)
    } finally {
      setLoading(false)
    }
  }, [docContentRef, onBeforeLoad, onHtmlLoaded])

  return {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
  }
}

```

## frontend/src/features/document/components/DocumentViewer.jsx

```jsx
function DocumentViewer({ documentAreaRef, docContentRef, loading, error, docLoaded }) {
  return (
    <section className="document-area" ref={documentAreaRef}>
      {loading && <p className="doc-placeholder">正在解析文档...</p>}
      {error && <p className="doc-error">{error}</p>}
      {!loading && !docLoaded && !error && (
        <div className="welcome">
          <div className="welcome-icon">📖</div>
          <p className="welcome-text">上传一份 docx 文档开始学习</p>
          <p className="welcome-hint">单击高亮词语查看简介，双击深入讲解</p>
        </div>
      )}
      <div
        ref={docContentRef}
        className="document-content"
        style={{ display: docLoaded ? 'block' : 'none' }}
      />
    </section>
  )
}

export default DocumentViewer

```

## frontend/src/features/document/documentUtils.js

```javascript
export function splitIntoChunks(html) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const blocks = []
  const elements = doc.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, td')
  elements.forEach(el => {
    const text = el.textContent.trim()
    if (text.length > 0) blocks.push(text)
  })
  const chunks = []
  let buffer = ''
  for (const block of blocks) {
    if (buffer.length + block.length > 800 && buffer.length > 0) {
      chunks.push(buffer)
      buffer = block
    } else {
      buffer = buffer ? buffer + '\n' + block : block
    }
  }
  if (buffer.length > 0) chunks.push(buffer)
  return chunks
}

```

## frontend/src/features/layout/AppHeader.jsx

```jsx
function AppHeader({
  fileName,
  extracting,
  extractProgress,
  docLoaded,
  hideKnown,
  onHideKnownChange,
  onFileUpload,
}) {
  return (
    <header className="main-header">
      <div className="header-file">
        {fileName
          ? <span className="file-name">📄 {fileName}</span>
          : <span className="header-hint">上传文档后开始学习</span>
        }
        {extracting && (
          <span className="extract-badge">
            提取中 {extractProgress.done}/{extractProgress.total}
          </span>
        )}
      </div>
      <div className="header-controls">
        {docLoaded && (
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={hideKnown}
              onChange={e => onHideKnownChange(e.target.checked)}
            />
            <span>隐藏已掌握</span>
          </label>
        )}
        <label htmlFor="file-upload" className="upload-button">
          上传文档
        </label>
        <input
          id="file-upload"
          type="file"
          accept=".docx"
          onChange={onFileUpload}
          style={{ display: 'none' }}
        />
      </div>
    </header>
  )
}

export default AppHeader

```

## frontend/src/features/explanation/useDeepExplanation.js

```javascript
import { useCallback, useRef, useState } from 'react'

import { requestDeepExplanation } from '../../api/knowledge'
import { findContextForKP } from '../knowledge/highlightDom'


export function useDeepExplanation(docContentRef) {
  const [deepExplanation, setDeepExplanation] = useState('')
  const [deepLoading, setDeepLoading] = useState(false)
  const [showDeep, setShowDeep] = useState(false)
  const deepAbortRef = useRef(null)

  const closeDeep = useCallback(() => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(false)
    setDeepExplanation('')
    setDeepLoading(false)
  }, [])

  const resetDeep = useCallback(() => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setDeepExplanation('')
    setDeepLoading(false)
    setShowDeep(false)
    deepAbortRef.current = null
  }, [])

  const startDeepExplain = useCallback(async (kp) => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(true)
    setDeepExplanation('')
    setDeepLoading(true)
    const context = findContextForKP(docContentRef.current, kp.id) || kp.text
    const controller = new AbortController()
    deepAbortRef.current = controller
    try {
      const response = await requestDeepExplanation(kp, context, controller.signal)
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        setDeepExplanation(prev => prev + decoder.decode(value, { stream: true }))
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setDeepExplanation(prev => prev + `\n\n[错误] ${err.message}`)
      }
    } finally {
      setDeepLoading(false)
      deepAbortRef.current = null
    }
  }, [docContentRef])

  return {
    deepExplanation,
    deepLoading,
    showDeep,
    closeDeep,
    resetDeep,
    startDeepExplain,
  }
}

```

## frontend/src/features/explanation/DeepExplanationPanel.jsx

```jsx
function DeepExplanationPanel({ showDeep, deepLoading, deepExplanation, onClose }) {
  if (!showDeep) return null

  return (
    <div className="deep-panel">
      <div className="deep-header">
        <span className="deep-title">
          详细讲解
          {deepLoading && <span className="thinking-dot">●</span>}
        </span>
        <button className="close-btn" onClick={onClose} title="关闭">×</button>
      </div>
      <div className="deep-content">
        {deepExplanation || (deepLoading && <span className="placeholder-inline">AI 正在思考...</span>)}
        {deepLoading && deepExplanation && <span className="cursor-blink">▋</span>}
      </div>
    </div>
  )
}

export default DeepExplanationPanel

```

## frontend/src/features/toc/components/TocSidebar.jsx

```jsx
function TocSidebar({ tocOpen, tocItems, activeTocId, docLoaded, onSelectHeading }) {
  return (
    <aside className="toc-sidebar">
      {tocOpen && (
        <>
          <div className="toc-section-title">文档目录</div>
          <nav className="toc-nav">
            {tocItems.length === 0 ? (
              <div className="toc-empty">
                {docLoaded ? '此文档无标题结构' : '上传文档后\n自动生成目录'}
              </div>
            ) : (
              tocItems.map(item => (
                <div
                  key={item.id}
                  className={`toc-item toc-level-${item.level}${activeTocId === item.id ? ' toc-active' : ''}`}
                  onClick={() => onSelectHeading(item.id)}
                  title={item.text}
                >
                  {item.text}
                </div>
              ))
            )}
          </nav>
        </>
      )}
    </aside>
  )
}

export default TocSidebar

```

## frontend/src/features/toc/components/SidebarHeader.jsx

```jsx
function SidebarHeader({ tocOpen, onToggle }) {
  return (
    <div className="sidebar-header">
      {tocOpen && <span className="app-logo">AI 学习助手</span>}
      <button
        className="toc-toggle-btn"
        onClick={onToggle}
        title={tocOpen ? '收起目录' : '展开目录'}
      >
        {tocOpen ? '◀' : '▶'}
      </button>
    </div>
  )
}

export default SidebarHeader

```

## frontend/src/app/App.jsx

```jsx
import { useState, useRef, useEffect, useCallback } from 'react'
import DocumentViewer from '../features/document/components/DocumentViewer'
import { useDocumentUpload } from '../features/document/hooks/useDocumentUpload'
import { useDeepExplanation } from '../features/explanation/useDeepExplanation'
import AppHeader from '../features/layout/AppHeader'
import {
  highlightFirstMatch,
  updateMarkStatusInDom,
} from '../features/knowledge/highlightDom'
import KnowledgePanel from '../features/knowledge/components/KnowledgePanel'
import { useKnowledgeExtraction } from '../features/knowledge/hooks/useKnowledgeExtraction'
import { useKnowledgeStatus } from '../features/knowledge/hooks/useKnowledgeStatus'
import SidebarHeader from '../features/toc/components/SidebarHeader'
import TocSidebar from '../features/toc/components/TocSidebar'
import '../styles/App.css'

// ========== React 组件 ==========

function App() {
  const [selectedKP, setSelectedKP] = useState(null)
  const [hideKnown, setHideKnown] = useState(true)

  // 目录相关
  const [tocItems, setTocItems] = useState([])
  const [tocOpen, setTocOpen] = useState(true)
  const [activeTocId, setActiveTocId] = useState(null)

  const docContentRef = useRef(null)
  const documentAreaRef = useRef(null)
  const highlightedIdsRef = useRef(new Set())

  const {
    extracting,
    extractProgress,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
  } = useKnowledgeExtraction()

  const {
    deepExplanation,
    deepLoading,
    showDeep,
    closeDeep,
    resetDeep,
    startDeepExplain,
  } = useDeepExplanation(docContentRef)

  const resetDocumentState = useCallback(() => {
    resetExtraction()
    setSelectedKP(null)
    resetDeep()
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()
  }, [resetDeep, resetExtraction])

  const {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
  } = useDocumentUpload({
    docContentRef,
    onBeforeLoad: resetDocumentState,
    onHtmlLoaded: extractAllChunks,
  })

  const {
    kpStatusMap,
    getKpStatus,
    recordClick,
    toggleKnown,
    stats,
  } = useKnowledgeStatus(uniqueKPs)

  // 增量高亮
  useEffect(() => {
    if (!docContentRef.current || !docLoaded) return
    for (const kp of uniqueKPs) {
      if (highlightedIdsRef.current.has(kp.id)) continue
      const status = getKpStatus(kp.text)
      highlightFirstMatch(docContentRef.current, kp.text, kp.id, kp.type, status)
      highlightedIdsRef.current.add(kp.id)
    }
  }, [uniqueKPs, docLoaded, kpStatusMap, getKpStatus])

  // 同步 mark 状态 class
  useEffect(() => {
    if (!docContentRef.current) return
    for (const kpText in kpStatusMap) {
      updateMarkStatusInDom(docContentRef.current, kpText, kpStatusMap[kpText])
    }
  }, [kpStatusMap])

  // hideKnown 开关
  useEffect(() => {
    if (!docContentRef.current) return
    if (hideKnown) {
      docContentRef.current.classList.add('hide-known')
    } else {
      docContentRef.current.classList.remove('hide-known')
    }
  }, [hideKnown, docLoaded])

  // 文档点击/双击委托
  useEffect(() => {
    const container = docContentRef.current
    if (!container) return

    const selectMark = async (mark) => {
      const kpId = mark.dataset.kpId
      const kp = uniqueKPs.find(k => k.id === kpId)
      if (kp) {
        setSelectedKP(kp)
        container.querySelectorAll('mark.active').forEach(el => el.classList.remove('active'))
        mark.classList.add('active')
        recordClick(kp)
      }
      return kp
    }

    const handleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) selectMark(target)
    }

    const handleDoubleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) {
        selectMark(target).then(kp => { if (kp) startDeepExplain(kp) })
      }
    }

    container.addEventListener('click', handleClick)
    container.addEventListener('dblclick', handleDoubleClick)
    return () => {
      container.removeEventListener('click', handleClick)
      container.removeEventListener('dblclick', handleDoubleClick)
    }
  }, [uniqueKPs, kpStatusMap, recordClick, startDeepExplain])

  // 提取目录（文档加载后）
  useEffect(() => {
    if (!docLoaded || !docContentRef.current) return
    const items = []
    let counter = 0
    docContentRef.current.querySelectorAll('h1, h2, h3, h4').forEach(h => {
      const level = parseInt(h.tagName[1])
      const text = h.textContent.trim()
      if (!text) return
      const id = `doc-h-${counter++}`
      h.id = id
      items.push({ id, text, level })
    })
    setTocItems(items)
    setActiveTocId(null)
  }, [docLoaded])

  // IntersectionObserver 跟踪当前章节
  useEffect(() => {
    if (!docLoaded || tocItems.length === 0 || !documentAreaRef.current) return
    const root = documentAreaRef.current
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter(e => e.isIntersecting)
        if (visible.length > 0) setActiveTocId(visible[0].target.id)
      },
      { root, rootMargin: '0px 0px -65% 0px', threshold: 0 }
    )
    tocItems.forEach(item => {
      const el = document.getElementById(item.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [docLoaded, tocItems])

  const scrollToHeading = (id) => {
    const el = document.getElementById(id)
    const container = documentAreaRef.current
    if (el && container) {
      const elTop = el.getBoundingClientRect().top
      const containerTop = container.getBoundingClientRect().top
      container.scrollBy({ top: elTop - containerTop - 24, behavior: 'smooth' })
      setActiveTocId(id)
    }
  }

  const handleKPCardClick = (kp) => {
    setSelectedKP(kp)
    if (!docContentRef.current) return
    const mark = docContentRef.current.querySelector(`mark[data-kp-id="${kp.id}"]`)
    if (mark) {
      mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
      docContentRef.current.querySelectorAll('mark.active').forEach(el => el.classList.remove('active'))
      mark.classList.add('active')
    }
    recordClick(kp)
  }

  const handleKPCardDblClick = (kp) => {
    setSelectedKP(kp)
    startDeepExplain(kp)
  }

  return (
    <div className={`app${tocOpen ? '' : ' toc-collapsed'}`}>
      <SidebarHeader
        tocOpen={tocOpen}
        onToggle={() => setTocOpen(!tocOpen)}
      />

      <AppHeader
        fileName={fileName}
        extracting={extracting}
        extractProgress={extractProgress}
        docLoaded={docLoaded}
        hideKnown={hideKnown}
        onHideKnownChange={setHideKnown}
        onFileUpload={handleFileUpload}
      />

      <TocSidebar
        tocOpen={tocOpen}
        tocItems={tocItems}
        activeTocId={activeTocId}
        docLoaded={docLoaded}
        onSelectHeading={scrollToHeading}
      />

      <DocumentViewer
        documentAreaRef={documentAreaRef}
        docContentRef={docContentRef}
        loading={loading}
        error={error}
        docLoaded={docLoaded}
      />

      <KnowledgePanel
        selectedKP={selectedKP}
        showDeep={showDeep}
        deepLoading={deepLoading}
        deepExplanation={deepExplanation}
        extracting={extracting}
        docLoaded={docLoaded}
        knowledgePoints={uniqueKPs}
        stats={stats}
        getKpStatus={getKpStatus}
        onCloseSelected={() => setSelectedKP(null)}
        onStartDeepExplain={startDeepExplain}
        onToggleKnown={toggleKnown}
        onCloseDeep={closeDeep}
        onCardClick={handleKPCardClick}
        onCardDoubleClick={handleKPCardDblClick}
      />
    </div>
  )
}

export default App

```

## frontend/src/types/knowledge.js

```javascript
export const KNOWLEDGE_STATUS = {
  UNKNOWN: 'unknown',
  LEARNING: 'learning',
  KNOWN: 'known',
}

```

## frontend/eslint.config.js

```javascript
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
])

```

## frontend/package.json

```json
{
  "name": "frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "eslint .",
    "preview": "vite preview"
  },
  "dependencies": {
    "mammoth": "^1.12.0",
    "react": "^19.2.5",
    "react-dom": "^19.2.5"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "@types/react": "^19.2.14",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.1",
    "eslint": "^10.2.1",
    "eslint-plugin-react-hooks": "^7.1.1",
    "eslint-plugin-react-refresh": "^0.5.2",
    "globals": "^17.5.0",
    "vite": "^8.0.10"
  }
}

```

## frontend/README.md

```markdown
# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

```

## frontend/vite.config.js

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})

```

## frontend/index.html

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>frontend</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>

```

## LICENSE

```text
MIT License

Copyright (c) 2026 54dongdaozhu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

