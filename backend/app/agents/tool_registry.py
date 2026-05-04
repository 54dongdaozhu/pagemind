from dataclasses import dataclass
from typing import Any, Callable

from app.agents import tools


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    args_schema: dict[str, Any]
    return_schema: dict[str, Any]
    when_to_use: str
    constraints: list[str]
    function: Callable[..., Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "args_schema": self.args_schema,
            "return_schema": self.return_schema,
            "when_to_use": self.when_to_use,
            "constraints": self.constraints,
        }


TOOL_REGISTRY: dict[str, AgentTool] = {
    "read_document_summary": AgentTool(
        name="read_document_summary",
        description="读取当前已索引文档的整体摘要，用于快速把握文档主题、范围和核心内容。",
        args_schema={
            "doc_id": {"type": "string", "description": "当前文档 ID。"},
        },
        return_schema={
            "summary": {"type": "string", "description": "文档摘要，可能为空字符串。"},
        },
        when_to_use="当 agent 需要先了解整篇文档背景、回答总结类问题或为检索结果补充全局上下文时使用。",
        constraints=["只能读取已通过 RAG 索引保存过摘要的文档。", "不负责生成最终回答。"],
        function=tools.read_document_summary,
    ),
    "search_document_chunks": AgentTool(
        name="search_document_chunks",
        description="根据查询语句从当前文档中检索相关片段，返回片段内容、索引、分数和检索方式。",
        args_schema={
            "doc_id": {"type": "string", "description": "当前文档 ID。"},
            "query": {"type": "string", "description": "用于检索的精炼问题或关键词。"},
            "top_k": {"type": "integer", "description": "最多返回片段数，默认 4。"},
        },
        return_schema={
            "sources": {
                "type": "array",
                "description": "相关片段列表，每项包含 chunk_index、content、score、retrieval_method。",
            },
        },
        when_to_use="当回答、解释、总结或比较需要文档依据时使用。",
        constraints=["只能检索已索引文档。", "返回片段不代表最终答案，需要交给回答类 agent 综合。"],
        function=tools.search_document_chunks,
    ),
    "answer_with_document_context": AgentTool(
        name="answer_with_document_context",
        description="基于文档摘要和检索片段直接生成一个有依据的文档问答结果。",
        args_schema={
            "doc_id": {"type": "string", "description": "当前文档 ID。"},
            "question": {"type": "string", "description": "用户问题。"},
            "top_k": {"type": "integer", "description": "检索片段数量，默认 4。"},
        },
        return_schema={
            "reply": {"type": "string", "description": "基于文档生成的回答。"},
            "sources": {"type": "array", "description": "回答使用的文档片段。"},
        },
        when_to_use="当用户问题是普通文档问答，且不需要额外教学拆解或结构化总结时使用。",
        constraints=["回答必须受限于当前文档上下文。", "复杂学习任务优先拆成检索和 Tutor/Synthesis。"],
        function=tools.answer_with_document_context,
    ),
    "extract_knowledge_from_chunk": AgentTool(
        name="extract_knowledge_from_chunk",
        description="从一段文档文本中发现有学习价值的知识点，并完成过滤、排序和原文校验。",
        args_schema={
            "text": {"type": "string", "description": "待识别的文档片段原文。"},
        },
        return_schema={
            "knowledge_points": {
                "type": "array",
                "description": "知识点列表，每项包含 text、type、explanation、importance。",
            },
        },
        when_to_use="文档上传、重新识别高亮、或 agent 需要从某段上下文中抽取学习对象时使用。",
        constraints=["text 字段必须能在原文中找到。", "不按固定数量返回，空数组是有效结果。"],
        function=tools.extract_knowledge_from_chunk,
    ),
    "get_knowledge_status_batch": AgentTool(
        name="get_knowledge_status_batch",
        description="批量读取知识点的学习状态和点击次数。",
        args_schema={
            "kp_texts": {"type": "array", "description": "知识点文本列表。"},
        },
        return_schema={
            "items": {
                "type": "array",
                "description": "状态列表，每项包含 kp_text、status、click_count。",
            },
        },
        when_to_use="需要判断用户对哪些知识点已学习、学习中或已掌握时使用。",
        constraints=["只返回已有学习记录的知识点；没有记录代表未知状态。"],
        function=tools.get_knowledge_status_batch,
    ),
    "record_knowledge_click": AgentTool(
        name="record_knowledge_click",
        description="记录用户点击某个知识点，并根据点击次数更新学习状态。",
        args_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
            "kp_type": {"type": "string", "description": "知识点类型，term 或 formula。"},
        },
        return_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
            "status": {"type": "string", "description": "更新后的状态。"},
            "click_count": {"type": "integer", "description": "累计点击次数。"},
        },
        when_to_use="用户点击高亮知识点或 agent 需要记录一次学习行为时使用。",
        constraints=["这是有副作用的写入工具，不能在纯分析或模拟场景中调用。"],
        function=tools.record_knowledge_click,
    ),
    "mark_knowledge_known": AgentTool(
        name="mark_knowledge_known",
        description="将某个知识点标记为已掌握。",
        args_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
            "kp_type": {"type": "string", "description": "知识点类型，term 或 formula。"},
        },
        return_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
            "status": {"type": "string", "description": "固定为 known。"},
        },
        when_to_use="用户明确表示已掌握某个知识点时使用。",
        constraints=["这是有副作用的写入工具，必须由明确用户行为触发。"],
        function=tools.mark_knowledge_known,
    ),
    "unmark_knowledge_known": AgentTool(
        name="unmark_knowledge_known",
        description="取消某个知识点的已掌握状态，并根据历史点击次数恢复为 unknown 或 learning。",
        args_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
        },
        return_schema={
            "kp_text": {"type": "string", "description": "知识点文本。"},
            "status": {"type": "string", "description": "恢复后的状态。"},
        },
        when_to_use="用户明确取消掌握标记时使用。",
        constraints=["这是有副作用的写入工具，必须由明确用户行为触发。"],
        function=tools.unmark_knowledge_known,
    ),
    "get_learning_stats": AgentTool(
        name="get_learning_stats",
        description="读取当前用户所有知识点学习状态的聚合统计。",
        args_schema={},
        return_schema={
            "unknown": {"type": "integer", "description": "未学习数量。"},
            "learning": {"type": "integer", "description": "学习中数量。"},
            "known": {"type": "integer", "description": "已掌握数量。"},
        },
        when_to_use="生成学习进度概览、复盘或下一步建议时使用。",
        constraints=["只反映本地 SQLite 中已有记录。"],
        function=tools.get_learning_stats,
    ),
    "explain_knowledge_with_context": AgentTool(
        name="explain_knowledge_with_context",
        description="基于知识点名称、类型和上下文生成深入解释。",
        args_schema={
            "keyword": {"type": "string", "description": "知识点文本。"},
            "kp_type": {"type": "string", "description": "知识点类型，term 或 formula。"},
            "context": {"type": "string", "description": "知识点出现的原文上下文。"},
        },
        return_schema={
            "explanation": {"type": "string", "description": "深入解释文本。"},
        },
        when_to_use="用户点击高亮、要求解释某个概念或公式时使用。",
        constraints=["应尽量提供原文上下文。", "当前工具内部聚合流式结果后返回完整文本。"],
        function=tools.explain_knowledge_with_context,
    ),
}


def list_tools() -> list[dict[str, Any]]:
    return [tool.public_dict() for tool in TOOL_REGISTRY.values()]


def get_tool(name: str) -> AgentTool:
    try:
        return TOOL_REGISTRY[name]
    except KeyError as e:
        raise ValueError(f"Unknown agent tool: {name}") from e


def call_tool(name: str, **kwargs):
    tool = get_tool(name)
    return tool.function(**kwargs)
