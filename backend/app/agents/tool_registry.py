from dataclasses import dataclass
from typing import Any

from app.agents import tools


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    args_schema: dict[str, Any]
    return_schema: dict[str, Any]
    when_to_use: str
    constraints: list[str]
    function: Any

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
    "extract_document_structure": AgentTool(
        name="extract_document_structure",
        description="从文档内容中抽取主题、章节层级、部分摘要和建议学习顺序。",
        args_schema={
            "text": {"type": "string", "description": "用于分析结构的文档文本、摘要或相关片段。"},
        },
        return_schema={
            "title": {"type": "string", "description": "推断出的文档标题或主题。"},
            "summary": {"type": "string", "description": "结构化摘要。"},
            "sections": {"type": "array", "description": "章节或主题分区列表。"},
            "suggested_order": {"type": "array", "description": "建议学习顺序。"},
        },
        when_to_use="用户想了解文档结构、章节脉络、学习路线，或 DocumentStructureAgent 初始化文档学习资产时使用。",
        constraints=["输入内容越完整，结构越可靠。", "不要把推断出的结构当成原文标题。"],
        function=tools.extract_document_structure,
    ),
    "generate_practice": AgentTool(
        name="generate_practice",
        description="基于文档上下文生成自测题、解释题、应用题、对比题或复述提示。",
        args_schema={
            "context": {"type": "string", "description": "生成练习所依据的文档上下文。"},
            "question_count": {"type": "integer", "description": "练习数量，1 到 10。"},
            "difficulty": {"type": "string", "description": "难度：easy、medium、hard。"},
            "practice_type": {"type": "string", "description": "练习类型：mixed、short_answer、application、compare、recall。"},
        },
        return_schema={
            "items": {"type": "array", "description": "练习列表，包含 type、question、reference_answer、target_knowledge、difficulty。"},
        },
        when_to_use="用户要求出题、自测、巩固理解、复述训练或应用练习时使用。",
        constraints=["必须依据给定文档上下文。", "生成的是学习练习，不默认是考试题。"],
        function=tools.generate_practice,
    ),
    "grade_answer": AgentTool(
        name="grade_answer",
        description="基于文档依据批改用户答案，给出得分、反馈、缺失点和复习目标。",
        args_schema={
            "question": {"type": "string", "description": "被回答的问题。"},
            "user_answer": {"type": "string", "description": "用户提交的答案。"},
            "reference_context": {"type": "string", "description": "用于批改的文档依据。"},
        },
        return_schema={
            "score": {"type": "number", "description": "0 到 1 的评分。"},
            "is_correct": {"type": "boolean", "description": "是否基本正确。"},
            "feedback": {"type": "string", "description": "批改反馈。"},
            "missing_points": {"type": "array", "description": "缺失或错误点。"},
            "review_targets": {"type": "array", "description": "建议复习目标。"},
        },
        when_to_use="用户要求批改答案、判断回答是否正确或分析错因时使用。",
        constraints=["需要题目、用户答案和文档依据。", "没有文档依据时只能给低置信反馈。"],
        function=tools.grade_answer,
    ),
    "map_knowledge_relations": AgentTool(
        name="map_knowledge_relations",
        description="分析文档知识点之间的前置、支撑、对比、例子、组成等关系。",
        args_schema={
            "context": {"type": "string", "description": "关系分析所依据的文档上下文。"},
            "knowledge_points": {"type": "array", "description": "可选知识点文本列表。"},
        },
        return_schema={
            "relations": {"type": "array", "description": "关系列表，包含 source、target、relation、reason。"},
        },
        when_to_use="用户想看概念关系、知识图谱、区别联系、前置依赖或学习路径时使用。",
        constraints=["关系必须能从上下文合理推出。", "不要编造文档没有支持的强关系。"],
        function=tools.map_knowledge_relations,
    ),
    "schedule_review": AgentTool(
        name="schedule_review",
        description="根据文档上下文和学习状态生成复习优先级、复习时间和下一步动作建议。",
        args_schema={
            "context": {"type": "string", "description": "用于复盘的文档上下文。"},
            "learning_stats": {"type": "object", "description": "可选学习状态统计。"},
            "knowledge_status": {"type": "array", "description": "可选知识点状态列表。"},
        },
        return_schema={
            "review_items": {"type": "array", "description": "复习项目列表，包含 text、priority、reason、suggested_time、next_action。"},
            "summary": {"type": "string", "description": "整体复习建议。"},
        },
        when_to_use="用户要求复习计划、下一步建议、薄弱点复盘或学习安排时使用。",
        constraints=["当前版本只生成建议，不创建系统提醒。", "应优先使用真实学习状态数据。"],
        function=tools.schedule_review,
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
    if hasattr(tool.function, "invoke"):
        return tool.function.invoke(kwargs)
    return tool.function(**kwargs)
