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


@dataclass(frozen=True)
class IndexedText:
    """Paragraphs of one attachment plus how much of the file Zotero indexed.

    Zotero stops indexing at a page limit for PDFs (100 by default) and a
    character limit for text files, and reports both the indexed and the
    total count. The counts are ``None`` when Zotero does not report them.
    """

    paragraphs: list[str]
    indexed_pages: int | None = None
    total_pages: int | None = None
    indexed_chars: int | None = None
    total_chars: int | None = None

    @classmethod
    def from_payload(cls, paragraphs: list[str], payload: dict[str, object]) -> "IndexedText":
        """Build from a Zotero ``/fulltext`` response."""
        return cls(
            paragraphs=paragraphs,
            indexed_pages=_optional_count(payload.get("indexedPages")),
            total_pages=_optional_count(payload.get("totalPages")),
            indexed_chars=_optional_count(payload.get("indexedChars")),
            total_chars=_optional_count(payload.get("totalChars")),
        )

    @property
    def partial(self) -> bool:
        """Return True when Zotero indexed only part of the file."""
        return _below(self.indexed_pages, self.total_pages) or _below(
            self.indexed_chars, self.total_chars
        )

    def coverage(self) -> dict[str, object]:
        """Response fields for index coverage; counts only for a partial index."""
        fields: dict[str, object] = {"partial_index": self.partial}
        if self.partial:
            for name in ("indexed_pages", "total_pages", "indexed_chars", "total_chars"):
                value = getattr(self, name)
                if value is not None:
                    fields[name] = value
        return fields


def _optional_count(value: object) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _below(indexed: int | None, total: int | None) -> bool:
    return indexed is not None and total is not None and indexed < total


@dataclass
class ItemRecord:
    """Metadata about a top-level Zotero item."""

    item_key: str
    citation_key: str
    title: str
    creators: list[dict[str, str]] = field(default_factory=list)
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
        """Human-readable author summary from creators with role 'author'."""
        authors = [c["name"] for c in self.creators if c.get("role") == "author"]
        if not authors:
            # fall back to all creators if none are explicitly authors
            authors = [c["name"] for c in self.creators]
        if not authors:
            return "Unknown author"
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]} & {authors[1]}"
        return f"{authors[0]} et al."

    @property
    def creators_by_role(self) -> dict[str, list[str]]:
        """Group creator names by role (e.g. author, editor)."""
        grouped: dict[str, list[str]] = {}
        for creator in self.creators:
            role = creator.get("role", "author")
            grouped.setdefault(role, []).append(creator["name"])
        return grouped

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
            creators=_deserialize_creators(data.get("creators", [])),
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


def _deserialize_creators(raw: object) -> list[dict[str, str]]:
    """Deserialize creators, handling both old (list[str]) and new (list[dict]) formats."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict):
            result.append({"name": str(entry.get("name", "")), "role": str(entry.get("role", "author"))})
        elif isinstance(entry, str):
            result.append({"name": entry, "role": "author"})
    return result
