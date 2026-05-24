import re


def split_text_for_rag(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    chunk_size = max(200, min(chunk_size, 2000))
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))
    paragraphs = _split_paragraphs(text)

    chunks = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_long_text(paragraph, chunk_size, chunk_overlap))
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)

    return _with_overlap(chunks, chunk_overlap)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    paragraphs, current, in_fence = [], [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            current.append(line)
        elif not in_fence and line.strip() == "" and current:
            para = "\n".join(current).strip()
            if para:
                paragraphs.append(para)
            current = []
        else:
            current.append(line)
    if current:
        para = "\n".join(current).strip()
        if para:
            paragraphs.append(para)
    return paragraphs


def _split_long_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _sentence_prefix(text: str, max_chars: int) -> str:
    tail = text[-max_chars:]
    matches = list(re.finditer(r"[.!?。！？]\s+", tail))
    if matches:
        return tail[matches[-1].end():].strip()
    return tail.strip()


def _with_overlap(chunks: list[str], chunk_overlap: int) -> list[str]:
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped = [chunks[0]]
    for idx in range(1, len(chunks)):
        prefix = _sentence_prefix(chunks[idx - 1], chunk_overlap)
        current = chunks[idx]
        overlapped.append(f"{prefix}\n\n{current}" if prefix else current)
    return overlapped
