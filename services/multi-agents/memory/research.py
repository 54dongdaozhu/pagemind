from dataclasses import dataclass, field


@dataclass
class WebResult:
    title: str
    url: str
    content: str
    score: float = 0.0


@dataclass
class ResearchFindings:
    topic: str
    queries: list[str] = field(default_factory=list)
    web_results: list[WebResult] = field(default_factory=list)
    notes: str = ""

    def to_context_string(self) -> str:
        lines = [f"# Research: {self.topic}\n"]
        for r in self.web_results[:8]:
            lines.append(f"## {r.title}\nSource: {r.url}\n{r.content[:800]}\n")
        return "\n".join(lines)
