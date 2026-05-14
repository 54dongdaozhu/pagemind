import time

from app.shared.llm import call_deepseek_stream
from app.shared.cache import (
    ANALYSIS_REPORT_CACHE_TTL_SECONDS,
    get_text,
    set_text,
    stable_hash,
)


def _stream_cached_explanation(text: str, chunk_size: int = 12):
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
        time.sleep(0.01)


EXPLAIN_DEEP_SYSTEM_PROMPT = """你是一位专业、耐心的文档讲解助手。你的任务是为用户深入讲解文档中的某个知识点,帮助他们真正理解并能在实际阅读、工作或研究中应用。

讲解原则:
1. 先用一句通俗易懂的话给出定义,避免堆砌术语
2. 解释这个知识点为什么重要、在当前文档中承担什么作用
3. 如果是公式,逐一解释每个符号的含义和单位
4. 如果是术语,可以用类比、举例帮助理解
5. 指出常见的混淆点或易错点(如果有的话)
6. 篇幅控制在 200-400 字之间,不要太长
7. 用清晰的小段落组织,适当使用 Markdown 格式(如加粗关键词)
8. 用亲切自然的语气,像朋友在讲解,而不是机械地复读教科书"""


def stream_deep_explanation(keyword: str, kp_type: str, context: str):
    cache_key = f"cache:analysis_report:deep_explain:{stable_hash({'keyword': keyword, 'kp_type': kp_type, 'context': context})}"
    cached = get_text(cache_key)
    if cached is not None:
        yield from _stream_cached_explanation(cached)
        return

    type_label = "公式/定理" if kp_type == "formula" else "术语/概念"
    user_message = f"""用户在阅读文档时点击了一个{type_label}:「{keyword}」

它出现在以下段落中:
\"\"\"
{context}
\"\"\"

请深入讲解这个知识点,帮助用户真正理解。"""

    messages = [
        {"role": "system", "content": EXPLAIN_DEEP_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    parts = []
    for chunk in call_deepseek_stream(messages, temperature=0.5, purpose="deep_explain"):
        parts.append(chunk)
        yield chunk
    answer = "".join(parts)
    if answer:
        set_text(cache_key, answer, ANALYSIS_REPORT_CACHE_TTL_SECONDS)
