# 服务设计

本项目按可独立部署的运行职责拆成五个服务，源码按应用服务归档，基础设施由 Docker Compose 编排。

## 服务边界

| 服务 | 目录/镜像 | 职责 | 依赖 |
| --- | --- | --- | --- |
| `web` | `src/web` | React/Vite 前端；生产环境由 nginx 托管静态文件，并代理 `/api/*` 到 `api` | `api` |
| `api` | `src/api` | FastAPI HTTP API、认证、RAG、知识点提取入口、学习状态接口 | `postgres`, `redis` |
| `worker` | `src/api` | RQ 异步任务进程，复用 API 业务代码，处理提取结果持久化等后台任务 | `postgres`, `redis` |
| `postgres` | `postgres:16-alpine` | 关系型持久化：用户、文档、知识点、学习状态、工作流记录 | 无应用依赖 |
| `redis` | `redis:7-alpine` | RQ 队列和短期任务协调 | 无应用依赖 |

## 目录结构

```text
ai-study-tool/
├── src/
│   ├── api/              # FastAPI + worker 共用 Python 代码
│   └── web/              # React + Vite + nginx 前端
├── docs/                 # 架构与服务设计文档
├── docker-compose.yml    # 本地/生产构建编排
├── docker-compose.override.yml
└── docker-compose.deploy.yml
```

## 数据与通信

- `web -> api`：浏览器访问 `web`，nginx 将 `/api/*` 反向代理到 `http://api:8000`。
- `api -> postgres`：通过 `DATABASE_URL` 读写 PostgreSQL。
- `api -> redis`：通过 `REDIS_URL` 投递 RQ 任务。
- `worker -> redis/postgres`：从 Redis 队列消费任务，并将结果写入 PostgreSQL。
- `api-data` volume：保存 API/worker 共享的运行数据，例如 ChromaDB 向量索引。
- `postgres-data` volume：保存 PostgreSQL 数据文件。
- `redis-data` volume：保存 Redis 数据文件。

## 配置约定

- `DATABASE_URL` 默认指向 `postgres:5432`。
- `REDIS_URL` 默认指向 `redis:6379/0`。
- `RQ_QUEUE_NAME` 默认使用 `pagemind`。
- 开发模式通过 `docker-compose.override.yml` 挂载 `src/api` 与 `src/web`，分别启用 FastAPI reload 和 Vite dev server。
