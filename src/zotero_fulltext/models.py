"""Data models used by zotero-fulltext."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class AttachmentRecord:
    """Metadata about an attachment item."""

    item_key: str
    parent_item_key: str | None
    title: str
    content_type: str | None
    link_mode: str | None
    version: int | None = None

    def is_pdf(self) -> bool:
        """Return True when this attachment is a PDF."""
        return (self.content_type or "").lower() == "application/pdf"

    def is_text_like(self) -> bool:
        """Return True when the attachment is likely to have readable fulltext."""
        content_type = (self.content_type or "").lower()
        return self.is_pdf() or content_type.startswith("text/")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "AttachmentRecord":
        """Deserialize from a JSON-compatible dictionary."""
        return cls(
            item_key=str(data["item_key"]),
            parent_item_key=(
                None if data.get("parent_item_key") in (None, "") else str(data["parent_item_key"])
            ),
            title=str(data.get("title", "")),
            content_type=None if data.get("content_type") in (None, "") else str(data["content_type"]),
            link_mode=None if data.get("link_mode") in (None, "") else str(data["link_mode"]),
            version=None if data.get("version") in (None, "") else int(data["version"]),
        )


@dataclass
class ItemRecord:
    """Metadata about a top-level Zotero item."""

    item_key: str
    citation_key: str
    title: str
    creators: list[str] = field(default_factory=list)
    year: str | None = None
    date: str | None = None
    item_type: str = ""
    abstract: str | None = None
    publication_title: str | None = None
    doi: str | None = None
    url: str | None = None
    collection_keys: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    attachment_key: str | None = None
    aliases: list[str] = field(default_factory=list)
    generated_citation_key: bool = False
    version: int | None = None

    @property
    def has_fulltext(self) -> bool:
        """Return True when a readable attachment is known."""
        return self.attachment_key is not None

    @property
    def author_summary(self) -> str:
        """Human-readable author summary."""
        if not self.creators:
            return "Unknown author"
        if len(self.creators) == 1:
            return self.creators[0]
        if len(self.creators) == 2:
            return f"{self.creators[0]} & {self.creators[1]}"
        return f"{self.creators[0]} et al."

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ItemRecord":
        """Deserialize from a JSON-compatible dictionary."""
        return cls(
            item_key=str(data["item_key"]),
            citation_key=str(data["citation_key"]),
            title=str(data.get("title", "")),
            creators=[str(value) for value in data.get("creators", [])],
            year=None if data.get("year") in (None, "") else str(data["year"]),
            date=None if data.get("date") in (None, "") else str(data["date"]),
            item_type=str(data.get("item_type", "")),
            abstract=None if data.get("abstract") in (None, "") else str(data["abstract"]),
            publication_title=(
                None
                if data.get("publication_title") in (None, "")
                else str(data["publication_title"])
            ),
            doi=None if data.get("doi") in (None, "") else str(data["doi"]),
            url=None if data.get("url") in (None, "") else str(data["url"]),
            collection_keys=[str(value) for value in data.get("collection_keys", [])],
            tags=[str(value) for value in data.get("tags", [])],
            attachment_key=(
                None if data.get("attachment_key") in (None, "") else str(data["attachment_key"])
            ),
            aliases=[str(value) for value in data.get("aliases", [])],
            generated_citation_key=bool(data.get("generated_citation_key", False)),
            version=None if data.get("version") in (None, "") else int(data["version"]),
        )
