import asyncio
import logging

from agents.utils.llms import call_llm
from agents.utils.profile import build_profile_hint
from agents.utils.search import web_search
from agents.utils.utils import safe_parse_json
from state import DocumentGenerationState

logger = logging.getLogger(__name__)


def _build_queries_prompt(topic: str, requirements: str, user_profile: dict) -> str:
    profile_hint = build_profile_hint(user_profile)
    return f"""You are helping create an educational document on: "{topic}"
Requirements: {requirements}{profile_hint}

Generate 4 focused web search queries to gather comprehensive information.
Return a JSON array of strings only. Example: ["query1", "query2", "query3", "query4"]"""


def _build_synthesis_prompt(topic: str, requirements: str, user_profile: dict, web_results: list[dict]) -> str:
    results_text = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['content'][:600]}" for i, r in enumerate(web_results[:8])
    )
    profile_hint = build_profile_hint(user_profile, "Target learner")
    return f"""You are a research assistant synthesizing information for an educational document.

Topic: {topic}
Requirements: {requirements}{profile_hint}

Web search results:
{results_text or "(no web results available)"}

Write a comprehensive research summary (800-1200 words) covering:
1. Core concepts and definitions
2. Key principles and mechanisms
3. Practical applications and examples
4. Common misconceptions or difficulties
5. Important related topics

Write in clear, organized prose. This will be used as source material for writing the document."""


def researcher_node(state: DocumentGenerationState) -> dict:
    logger.info("researcher_node start task_id=%s", state["task_id"])

    user_profile = state.get("user_profile") or {}

    topic = state["topic"]
    requirements = state.get("requirements", "")

    # Generate search queries
    queries_raw = call_llm(_build_queries_prompt(topic, requirements, user_profile))
    queries = safe_parse_json(queries_raw) or [topic]
    if not isinstance(queries, list):
        queries = [topic]
    queries = [str(q) for q in queries[:5]]

    # Web search (graceful degradation if Tavily unavailable)
    try:
        web_results = asyncio.run(web_search(queries))
    except RuntimeError:
        web_results = []
    logger.info("researcher_node: got %d web results", len(web_results))

    # Synthesize research notes
    research_notes = call_llm(_build_synthesis_prompt(topic, requirements, user_profile, web_results))

    return {
        "user_profile": user_profile,
        "search_queries": queries,
        "web_results": web_results,
        "research_notes": research_notes,
        "current_agent": "researcher",
        "progress_messages": [f"研究完成：收集到 {len(web_results)} 条网络资料，已合成研究摘要"],
    }
