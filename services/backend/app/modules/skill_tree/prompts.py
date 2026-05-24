SKILL_TREE_ANALYZE_PROMPT = """你是一位技术学习顾问。请根据用户的行为信号，分析用户当前的技能状况，并生成一份个性化技能树 JSON。

## 用户信息
{profile_section}

## 行为信号
{signals_section}

## 要求
请输出一个 JSON 对象，格式如下：
{{
  "summary": "对用户学习状态的一句话总结（中文，30字以内）",
  "nodes": [
    {{
      "id": "唯一字符串ID",
      "skill": "技能名称（简洁，5-15字）",
      "category": "技能分类（如：编程语言/框架/工具/理论）",
      "priority": "high|medium|low",
      "status": "gap|learning|known",
      "evidence": ["支撑推荐的行为证据1", "证据2"],
      "parent_id": null
    }}
  ]
}}

## 规则
- nodes 最多 12 个，优先列出 priority=high 的
- status=known 表示用户已掌握（从已掌握 KP 推断），不重点推荐
- status=learning 表示用户正在学习（频繁点击但未掌握）
- status=gap 表示明显的知识盲区（应重点推荐）
- evidence 列表每项不超过 20 字，最多 3 条
- 输出纯 JSON，不要包含 markdown 代码块"""


SKILL_TREE_FINALIZE_PROMPT = """你是一位技术学习顾问。请根据用户行为信号和联网验证信息，生成最终的个性化技能树 JSON。

## 用户信息
{profile_section}

## 行为信号
{signals_section}

## 联网验证信息
{web_section}

## 要求
请输出一个 JSON 对象，格式如下：
{{
  "summary": "对用户学习状态的一句话总结（中文，30字以内）",
  "nodes": [
    {{
      "id": "唯一字符串ID",
      "skill": "技能名称（简洁，5-15字）",
      "category": "技能分类",
      "priority": "high|medium|low",
      "status": "gap|learning|known",
      "evidence": ["行为证据1", "证据2"],
      "web_validated": true,
      "web_snippet": "联网验证摘要（可选，来自 web_section）",
      "parent_id": null
    }}
  ]
}}

## 规则
- nodes 最多 12 个，优先列出 priority=high 的
- 有联网验证信息的技能，web_validated=true 并填写 web_snippet（不超过 80 字）
- 无联网信息的技能，web_validated=false，web_snippet 省略
- 输出纯 JSON，不要包含 markdown 代码块"""
