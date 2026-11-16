from dataclasses import asdict, dataclass, field


@dataclass
class Page:
    """One scraped web page."""
    url: str
    title: str = ""
    text: str = ""                                  # cleaned body text
    headings: list = field(default_factory=list)
    faqs: list = field(default_factory=list)        # [{"question": ..., "answer": ...}]
    section: str = ""                               # e.g. "products", "services", "faq", "about"


@dataclass
class Chunk:
    """A retrievable piece of website knowledge."""
    id: str
    text: str
    url: str = ""
    title: str = ""
    section: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(id=str(d.get("id", "")), text=str(d.get("text", "")), url=str(d.get("url", "")),
                   title=str(d.get("title", "")), section=str(d.get("section", "")))
