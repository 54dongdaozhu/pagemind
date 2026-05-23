import pytest


@pytest.fixture
def mock_llm(monkeypatch):
    """Patch call_llm to return a canned response."""
    def _factory(response: str = "mock response"):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: response)
        return response
    return _factory


@pytest.fixture
def mock_search(monkeypatch):
    """Patch web_search to return empty results."""
    import agents.utils.search as search_mod
    import asyncio

    async def _fake_search(*a, **kw):
        return [{"title": "Result", "url": "http://example.com", "content": "Sample content"}]

    monkeypatch.setattr(search_mod, "web_search", _fake_search)


@pytest.fixture
def base_state():
    return {
        "task_id": "test-task-1",
        "user_id": "user-1",
        "topic": "Python 异步编程",
        "requirements": "面向初学者",
        "user_profile": {"level": "beginner"},
        "search_queries": [],
        "web_results": [],
        "research_notes": "Python asyncio 是一个用于编写并发代码的库...",
        "outline": [
            {"id": "s1", "title": "基础概念", "description": "介绍 asyncio 基础", "order": 1},
            {"id": "s2", "title": "核心 API", "description": "async/await 语法", "order": 2},
        ],
        "sections": {},
        "current_section": {"id": "s1", "title": "基础概念", "description": "介绍 asyncio 基础", "order": 1},
        "draft": "# Python 异步编程\n\n## 基础概念\n\n内容...",
        "review_feedback": "",
        "review_decision": "",
        "revision_count": 0,
        "human_feedback": "",
        "human_decision": "",
        "html_content": "",
        "word_filename": "",
        "status": "running",
        "current_agent": "",
        "progress_messages": [],
        "error": None,
    }
