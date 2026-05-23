"""
End-to-end workflow test with fully mocked LLM and search.
Verifies graph runs from START to END without errors.
"""
import json
import pytest


@pytest.fixture(autouse=True)
def patch_llm_and_search(monkeypatch):
    import agents.utils.llms as llm_mod
    import agents.utils.search as search_mod
    import asyncio

    call_count = 0

    def _fake_llm(prompt: str, **kw) -> str:
        nonlocal call_count
        call_count += 1
        # queries
        if "search queries" in prompt.lower() or "web search" in prompt.lower():
            return '["query1", "query2"]'
        # outline
        if "outline" in prompt.lower() or "curriculum" in prompt.lower():
            return json.dumps([
                {"id": "s1", "title": "基础概念", "description": "基础介绍", "order": 1},
                {"id": "s2", "title": "实践应用", "description": "实际应用", "order": 2},
            ])
        # review
        if "review" in prompt.lower() or "editor" in prompt.lower():
            return '{"decision":"accept","feedback":"","score":9}'
        # default: return markdown content
        return f"## Section Content\n\n这是关于 {prompt[:30]} 的内容...\n\n包含详细解释和示例。"

    async def _fake_search(*a, **kw):
        return [{"title": "Result", "url": "http://example.com", "content": "Sample content about the topic"}]

    monkeypatch.setattr(llm_mod, "call_llm", _fake_llm)
    monkeypatch.setattr(search_mod, "web_search", _fake_search)

    # Patch asyncio.run to avoid event loop conflicts in tests
    monkeypatch.setattr("asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro))


def _make_initial_state(task_id: str = "wf-test-1") -> dict:
    return {
        "task_id": task_id,
        "user_id": "test-user",
        "topic": "Python 异步编程",
        "requirements": "面向初学者",
        "user_profile": {},
        "search_queries": [],
        "web_results": [],
        "research_notes": "",
        "outline": [],
        "sections": {},
        "current_section": {},
        "draft": "",
        "review_feedback": "",
        "review_decision": "",
        "revision_count": 0,
        "human_feedback": "approved",
        "human_decision": "publish",
        "html_content": "",
        "word_filename": "",
        "status": "running",
        "current_agent": "",
        "progress_messages": [],
        "error": None,
    }


def test_graph_builds_without_error():
    from agents.orchestrator import build_graph
    graph = build_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_researcher_to_editor_state_flow(monkeypatch, tmp_path):
    """Verify researcher → editor produces outline in state."""
    from agents.researcher import researcher_node
    from agents.editor import editor_node

    state = _make_initial_state()
    r_out = researcher_node(state)
    assert r_out["research_notes"]

    state.update(r_out)
    e_out = editor_node(state)
    assert len(e_out["outline"]) >= 2


def test_writer_assemble_produces_draft(monkeypatch, tmp_path):
    """Verify writer_assemble combines sections into a draft."""
    from agents.writer import writer_assemble_node

    state = _make_initial_state()
    state["outline"] = [
        {"id": "s1", "title": "基础", "description": "desc", "order": 1},
        {"id": "s2", "title": "进阶", "description": "desc", "order": 2},
    ]
    state["sections"] = {"s1": "## 基础\n\n内容A", "s2": "## 进阶\n\n内容B"}

    result = writer_assemble_node(state)
    assert "draft" in result
    assert "Python 异步编程" in result["draft"]


def test_publisher_produces_html_and_docx(tmp_path, monkeypatch):
    """Verify publisher creates HTML and docx file."""
    monkeypatch.setenv("DOC_GEN_WORD_DIR", str(tmp_path))
    import agents.publisher as pub_mod
    pub_mod._WORD_DIR = str(tmp_path)

    state = _make_initial_state()
    state["draft"] = "# Python 异步编程\n\n## 基础\n\n内容...\n\n## 总结\n\n总结内容"

    from agents.publisher import publisher_node
    result = publisher_node(state)

    assert result["html_content"]
    assert "<" in result["html_content"]
    assert result["word_filename"]
    from pathlib import Path
    assert Path(result["word_filename"]).exists()
