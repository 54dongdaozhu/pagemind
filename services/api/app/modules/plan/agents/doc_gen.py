import json
import logging
from collections.abc import Generator

from app.shared.llm import call_deepseek, call_deepseek_stream

logger = logging.getLogger(__name__)

_DOC_PROMPT = """\
你是一位技术写作专家。请为用户生成一份教学文档。

用户身份：{identity}
学习目的：{purpose}
用户请求：{message}

背景研究：
{research_context}

{draft_hint}

请生成一份详细的 Markdown 格式教学文档，包含：
1. 概念介绍与背景
2. 核心原理详解
3. 代码示例（如适用）
4. 常见问题与误区
5. 延伸阅读方向

使用中文，深入浅出，适合自学。"""

_QUALITY_PROMPT = """\
请评估以下教学文档的质量：

{draft}

评估标准：
- 内容完整性（是否覆盖核心概念）
- 示例清晰度
- 结构合理性

返回 JSON：{{"ok": true/false, "issues": "改进建议（如ok为true则留空）"}}
仅返回 JSON。"""


def _encode(chunk_type: str, text: str) -> str:
    return json.dumps({"type": chunk_type, "text": text}, ensure_ascii=False) + "\n"


def generate_doc(state: dict) -> Generator[str, None, None]:
    profile = state.get("profile") or {}
    state.setdefault("doc_draft", "")
    state.setdefault("doc_iterations", 0)

    for i in range(2):
        yield _encode("status", f"生成教学文档（第{i + 1}轮）...")
        draft_hint = ""
        if state["doc_draft"]:
            draft_hint = f"请在以下草稿基础上改进：\n{state['doc_draft'][:1000]}"

        prompt = _DOC_PROMPT.format(
            identity=profile.get("identity", "未知"),
            purpose=profile.get("purpose", "未知"),
            message=state["message"],
            research_context=state.get("research_context", ""),
            draft_hint=draft_hint,
        )
        try:
            draft = ""
            for chunk in call_deepseek_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                purpose="doc_generation",
            ):
                draft += chunk
                yield _encode("content", chunk)
            state["doc_draft"] = draft
            state["doc_iterations"] = i + 1

            if i < 1:
                try:
                    quality_raw = call_deepseek(
                        messages=[{"role": "user", "content": _QUALITY_PROMPT.format(draft=draft[:2000])}],
                        temperature=0.2,
                        json_mode=True,
                        purpose="doc_quality_check",
                    )
                    quality = json.loads(quality_raw)
                    if quality.get("ok", True):
                        state["doc_quality_ok"] = True
                        break
                    yield _encode("status", "优化文档质量...")
                except Exception as e:
                    logger.warning("Doc quality check failed: %s", e)
                    break
        except Exception as e:
            logger.warning("Doc generation failed at iteration %d: %s", i, e)
            yield _encode("error", f"文档生成失败：{e}")
            break

    state["generated_content"] = state.get("doc_draft", "")
