from dataclasses import dataclass, field


@dataclass
class DraftSection:
    id: str
    title: str
    order: int
    content: str = ""
    word_count: int = 0

    def set_content(self, text: str) -> None:
        self.content = text
        self.word_count = len(text.split())


@dataclass
class DraftMemory:
    sections: dict[str, DraftSection] = field(default_factory=dict)

    def add(self, section: DraftSection) -> None:
        self.sections[section.id] = section

    def assemble(self, outline_order: list[str]) -> str:
        ordered = [self.sections[sid] for sid in outline_order if sid in self.sections]
        return "\n\n".join(s.content for s in ordered)
