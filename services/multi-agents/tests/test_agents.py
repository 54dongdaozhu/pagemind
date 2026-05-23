import json
import pytest


class TestResearcherNode:
    def test_returns_research_notes(self, mock_llm, mock_search, base_state, monkeypatch):
        mock_llm('["Python asyncio basics", "Python async tutorial"]')
        import agents.utils.llms as llm_mod
        call_count = 0
        original = llm_mod.call_llm

        def _side_effect(prompt, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '["query1", "query2"]'
            return "Research notes about Python asyncio..."

        monkeypatch.setattr(llm_mod, "call_llm", _side_effect)

        import asyncio
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        from agents.researcher import researcher_node
        result = researcher_node(base_state)

        assert "research_notes" in result
        assert "search_queries" in result
        assert len(result["progress_messages"]) > 0

    def test_handles_invalid_queries_json(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        call_count = 0

        def _side_effect(prompt, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not valid json"
            return "research notes"

        monkeypatch.setattr(llm_mod, "call_llm", _side_effect)

        import agents.utils.search as search_mod
        import asyncio

        async def _no_search(*a, **kw):
            return []

        monkeypatch.setattr(search_mod, "web_search", _no_search)
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro))

        from agents.researcher import researcher_node
        result = researcher_node(base_state)
        # Should fall back to [topic] as queries
        assert result["search_queries"] == [base_state["topic"]]


class TestEditorNode:
    def test_returns_outline(self, monkeypatch, base_state):
        outline_json = json.dumps([
            {"id": "s1", "title": "概念", "description": "基础", "order": 1},
            {"id": "s2", "title": "实践", "description": "应用", "order": 2},
        ])
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: outline_json)

        from agents.editor import editor_node
        result = editor_node(base_state)

        assert "outline" in result
        assert len(result["outline"]) == 2
        assert result["outline"][0]["id"] == "s1"

    def test_fallback_on_bad_json(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: "bad json")

        from agents.editor import editor_node
        result = editor_node(base_state)
        assert len(result["outline"]) == 3  # fallback has 3 sections


class TestWriterNodes:
    def test_section_writer(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: "## 基础概念\n\n内容...")

        from agents.writer import section_writer_node
        result = section_writer_node(base_state)

        assert "sections" in result
        assert "s1" in result["sections"]

    def test_writer_assemble(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: "## 引言\n\n引言内容\n\n## 总结\n\n总结内容")

        state = {**base_state, "sections": {"s1": "## 基础\n\n内容", "s2": "## API\n\n内容"}}
        from agents.writer import writer_assemble_node
        result = writer_assemble_node(state)

        assert "draft" in result
        assert base_state["topic"] in result["draft"]


class TestReviewerNode:
    def test_accept_decision(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: '{"decision":"accept","feedback":"","score":8}')

        from agents.reviewer import reviewer_node
        result = reviewer_node(base_state)
        assert result["review_decision"] == "accept"

    def test_revise_decision(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: '{"decision":"revise","feedback":"需要更多例子","score":5}')

        from agents.reviewer import reviewer_node
        result = reviewer_node(base_state)
        assert result["review_decision"] == "revise"
        assert "需要更多例子" in result["review_feedback"]

    def test_force_accept_after_max_revisions(self, base_state):
        state = {**base_state, "revision_count": 3}
        from agents.reviewer import reviewer_node
        result = reviewer_node(state)
        assert result["review_decision"] == "accept"


class TestReviserNode:
    def test_increments_revision_count(self, monkeypatch, base_state):
        import agents.utils.llms as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", lambda *a, **kw: "# Revised\n\n内容")

        state = {**base_state, "review_feedback": "需要更多细节", "revision_count": 1}
        from agents.reviser import reviser_node
        result = reviser_node(state)

        assert result["revision_count"] == 2
        assert "# Revised" in result["draft"]


class TestPublisherNode:
    def test_generates_html(self, base_state, tmp_path, monkeypatch):
        monkeypatch.setenv("DOC_GEN_WORD_DIR", str(tmp_path))
        import agents.publisher as pub_mod
        pub_mod._WORD_DIR = str(tmp_path)

        from agents.publisher import publisher_node
        result = publisher_node(base_state)

        assert "html_content" in result
        assert "<" in result["html_content"]  # has HTML tags
        assert result["status"] == "done"


class TestUtils:
    def test_safe_parse_json_plain(self):
        from agents.utils.utils import safe_parse_json
        assert safe_parse_json('{"a": 1}') == {"a": 1}

    def test_safe_parse_json_fenced(self):
        from agents.utils.utils import safe_parse_json
        assert safe_parse_json("```json\n[1,2,3]\n```") == [1, 2, 3]

    def test_safe_parse_json_invalid(self):
        from agents.utils.utils import safe_parse_json
        assert safe_parse_json("not json at all") is None

    def test_markdown_to_html_contains_content(self):
        from agents.utils.views import markdown_to_html
        html = markdown_to_html("# Title\n\nParagraph text")
        assert "<h1>" in html
        assert "Paragraph text" in html
