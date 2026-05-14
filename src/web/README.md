# AI 文档学习助手前端

这里是 AI 文档学习助手的 React + Vite 前端应用，负责文档上传解析、知识点高亮、深度讲解、当前文档问答和学习状态展示。

## 目录结构

```text
src/web/
├── public/                 # 静态资源
├── src/
│   ├── main.jsx            # React 挂载入口
│   ├── app/
│   │   └── App.jsx         # 主界面与业务状态编排
│   ├── api/                # 后端 API 封装
│   │   ├── client.js       # fetch 基础封装
│   │   ├── knowledge.js    # 知识点与掌握状态接口
│   │   ├── rag.js          # 文档索引与 RAG 问答接口
│   │   └── chat.js         # Agent/聊天接口
│   ├── features/           # 按业务拆分的功能模块
│   │   ├── document/       # docx/PDF/txt/Markdown 解析与切块
│   │   ├── knowledge/      # 原文高亮、定位与 mark 标签处理
│   │   ├── explanation/    # 简介/深度讲解面板与流式输出
│   │   ├── chat/           # 当前文档问答面板
│   │   └── layout/         # 页面布局组件
│   ├── styles/             # 页面级样式
│   ├── types/              # 前端类型约定与常量
│   ├── utils/              # 通用工具函数
│   └── assets/             # 图片和前端资源
├── package.json            # npm scripts 与依赖
└── vite.config.js          # Vite 配置
```

## 常用命令

```bash
npm install
npm run dev
npm run build
npm run lint
```

开发服务默认运行在 `http://localhost:5173`。使用前请先启动后端服务，默认 API 地址为 `http://localhost:8000`。
