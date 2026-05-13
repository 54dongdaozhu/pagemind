# AI 文档学习助手

![AI Study Tool 封面](https://placehold.co/1200x420/png?text=AI+Study+Tool)

![React](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=111)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/Storage-PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Queue-Redis-DC382D?logo=redis&logoColor=white)

## 项目定位

AI 文档学习助手是一款面向文档阅读、知识整理和深度理解的学习工具。它可以把用户上传的文档解析成可阅读页面，自动提取核心知识点，在原文中高亮显示，并通过智能讲解帮助用户快速理解内容。

它适合用来学习技术文档、课程笔记、企业培训材料、论文摘要和长篇知识型资料。

## 核心体验

![文档阅读场景](https://placehold.co/1000x520/png?text=Document+Reading+%2B+Knowledge+Highlights)

- 上传 docx、PDF、txt、Markdown 或 Markdown 文件夹。
- 自动解析文档结构，并生成目录。
- 使用 AI 提取核心概念、公式、术语和关键知识点。
- 在原文中高亮知识点，点击查看简介，双击查看深度讲解。
- 支持围绕当前文档进行 RAG 问答。
- 记录知识点掌握状态，隐藏已经掌握的内容。

## Markdown 支持

当前版本已经支持 Markdown 文档，并且可以显示线上图片：

```md
![线上图片](https://placehold.co/800x300/png?text=Online+Image)
```

如果上传 Markdown 文件夹，也可以支持本地相对路径图片：

```text
note-folder/
  note.md
  images/
    flow.png
```

```md
![本地图](./images/flow.png)
```

第一版本地图片会被映射成浏览器内的 `blob:` URL，适合当前会话内阅读和学习。

## 系统架构

![系统架构示意图](https://placehold.co/1100x560/png?text=React+Frontend+%E2%86%92+FastAPI+API+%E2%86%92+LLM+%2B+RAG+%2B+PostgreSQL)

项目采用前后端分离架构：

| 层级 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | React 19 + Vite | 文档上传、解析、阅读、目录、高亮、交互 |
| API | FastAPI | 认证、知识点提取、讲解、RAG 问答 |
| AI 工作流 | LangGraph + LLM | 多步提取、过滤、排序和解释 |
| 向量检索 | Embedding + ChromaDB | 文档切块、向量索引、相关片段召回 |
| 数据层 | PostgreSQL + Redis | 用户状态、知识点记录、队列和缓存 |

## 学习流程

1. 用户上传文档。
2. 前端解析文档并渲染 HTML。
3. 文档被切成多个文本块。
4. 后端调用 AI 工作流提取知识点。
5. 前端把知识点高亮回原文。
6. 用户点击知识点查看解释，或者使用 RAG 对当前文档提问。
7. 系统保存掌握状态，帮助用户持续复习。

## 项目价值

![学习闭环](https://placehold.co/1000x420/png?text=Read+%E2%86%92+Extract+%E2%86%92+Explain+%E2%86%92+Review)

这个项目的重点不是简单地“总结文档”，而是把阅读过程拆成更适合学习的闭环：

- 原文仍然是中心，AI 不替代阅读。
- 知识点直接贴回原文，降低上下文切换成本。
- 简介和深度讲解分层，适合快速扫读和深入理解。
- 掌握状态可持续记录，适合长期学习。

## 后续方向

- Markdown 图片资源持久化。
- 图片 OCR 和图表理解。
- 更完整的 GFM 支持，例如任务列表、脚注和代码高亮。
- 多文档知识库检索。
- 针对课程、论文、代码文档的专项学习模式。

## 验证图片

下面这张图用于快速确认线上图片渲染链路是否正常：

![在线图片验证](https://placehold.co/900x260/png?text=Online+Image+Render+OK)
