# Backend Modules

This backend is organized as a modular monolith. Each package owns one business
area and keeps its HTTP router next to the service code that implements it.

- `auth`: registration, login, current-user dependencies, auth schemas.
- `assets`: image asset upload and retrieval.
- `agent`: learning-agent orchestration, prompts, state, and tool registry.
- `explain`: deep explanation streaming.
- `extraction`: knowledge extraction workflows and background jobs.
- `health`: health checks and LLM smoke-test endpoints.
- `knowledge`: learning status, knowledge point records, and study stats.
- `rag`: document indexing, retrieval, embeddings, and vector-store access.

Cross-cutting infrastructure lives in `app.shared`. Database models and app
configuration stay in `app.core` until a domain needs a dedicated repository
boundary.
