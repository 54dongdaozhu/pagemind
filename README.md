# AI 学习助手

> 一款面向学生备考场景的 AI 文档学习工具，能从 docx 文档中自动提取核心知识点，通过高亮 + 智能讲解帮助用户高效学习。

## ✨ 功能特性

- 📄 **docx 文档加载**：上传 Word 文档，前端实时解析渲染
- 🤖 **智能提取知识点**：通过 LLM 自动识别文档中的核心术语和公式
- 🎨 **原文高亮**：知识点在文档中以颜色标注，一目了然
- 💬 **单击看简介**：点击高亮立刻显示 2-3 句精简解释
- 📚 **双击深度讲解**：流式输出详细讲解，逐字呈现
- 🔎 **文档 RAG 问答**：围绕当前文档检索片段并生成回答
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
- **LangGraph + LangChain**：多步知识点提取流水线
- **SQLite Chunk Retrieval**：当前文档 RAG 检索

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
pip install -r requirements.txt
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
| `/api/rag/index` | POST | 接收完整文本并建立 RAG chunk 索引 |
| `/api/rag/query` | POST | 检索当前文档并生成问答 |
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
LangGraph 三步流水线：召回提取 → 质量过滤 → 重要性分级
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
