"""Persistent metadata index for citekey-native lookups."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

from .models import AttachmentRecord, ItemRecord


_CITATION_KEY_LINE_RE = re.compile(
    r"^\s*(?:Citation Key|citationkey)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_lookup_key(value: str) -> str:
    """Normalize a citekey for case-insensitive lookup."""
    return value.strip().casefold()


def extract_preferred_citation_key(data: dict[str, object]) -> str | None:
    """Read the preferred citekey from Zotero metadata."""
    native = str(data.get("citationKey", "") or "").strip()
    if native:
        return native
    extra = str(data.get("extra", "") or "")
    match = _CITATION_KEY_LINE_RE.search(extra)
    if match:
        return match.group(1).strip()
    return None


def extract_year(date_value: str | None) -> str:
    """Extract a publication year from a Zotero date field."""
    if not date_value:
        return "nd"
    match = _YEAR_RE.search(str(date_value))
    return match.group(0) if match else "nd"


def slugify_ascii(value: str) -> str:
    """Create a deterministic ASCII slug."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("", normalized.casefold())
    return slug or "item"


def creator_names(creators: list[dict[str, object]]) -> list[str]:
    """Convert Zotero creator objects into readable names."""
    names: list[str] = []
    for creator in creators:
        last_name = str(creator.get("lastName", "") or "").strip()
        first_name = str(creator.get("firstName", "") or "").strip()
        single_name = str(creator.get("name", "") or "").strip()
        if last_name:
            names.append(last_name)
        elif single_name:
            names.append(single_name)
        elif first_name:
            names.append(first_name)
    return names


def generated_base_key(data: dict[str, object]) -> str:
    """Generate the base fallback citekey for items without one."""
    creators = data.get("creators") or []
    if isinstance(creators, list):
        for creator in creators:
            if not isinstance(creator, dict):
                continue
            creator_type = str(creator.get("creatorType", "") or "").strip().lower()
            if creator_type == "author":
                last_name = str(creator.get("lastName", "") or creator.get("name", "")).strip()
                if last_name:
                    return f"{slugify_ascii(last_name)}{extract_year(str(data.get('date', '') or ''))}"
        for creator in creators:
            if not isinstance(creator, dict):
                continue
            last_name = str(creator.get("lastName", "") or creator.get("name", "")).strip()
            if last_name:
                return f"{slugify_ascii(last_name)}{extract_year(str(data.get('date', '') or ''))}"
    title = str(data.get("title", "") or data.get("shortTitle", "") or "item")
    first_token = title.split()[0] if title.split() else "item"
    return f"{slugify_ascii(first_token)}{extract_year(str(data.get('date', '') or ''))}"


def is_top_level_bibliographic(data: dict[str, object]) -> bool:
    """Return True for top-level items we want to expose."""
    item_type = str(data.get("itemType", "") or "")
    if item_type in {"attachment", "note", "annotation"}:
        return False
    if data.get("parentItem"):
        return False
    return True


def attachment_from_data(data: dict[str, object], version: int | None) -> AttachmentRecord | None:
    """Create an attachment record from Zotero JSON."""
    item_key = str(data.get("key", "") or "")
    if not item_key:
        return None
    return AttachmentRecord(
        item_key=item_key,
        parent_item_key=(
            None if data.get("parentItem") in (None, "") else str(data.get("parentItem"))
        ),
        title=str(data.get("title", "") or ""),
        content_type=None if data.get("contentType") in (None, "") else str(data.get("contentType")),
        link_mode=None if data.get("linkMode") in (None, "") else str(data.get("linkMode")),
        version=version,
    )


def item_from_data(
    data: dict[str, object],
    version: int | None,
    *,
    citation_key: str,
    generated_citation_key: bool,
    aliases: list[str] | None = None,
) -> ItemRecord:
    """Create a top-level item record from Zotero JSON."""
    tags = [
        str(tag.get("tag", "")).strip()
        for tag in data.get("tags", [])
        if isinstance(tag, dict) and str(tag.get("tag", "")).strip()
    ]
    creators = creator_names(
        [value for value in data.get("creators", []) if isinstance(value, dict)]
    )
    return ItemRecord(
        item_key=str(data.get("key", "") or ""),
        citation_key=citation_key,
        title=str(data.get("title", "") or ""),
        creators=creators,
        year=extract_year(str(data.get("date", "") or "")),
        date=None if data.get("date") in (None, "") else str(data.get("date")),
        item_type=str(data.get("itemType", "") or ""),
        abstract=None
        if data.get("abstractNote") in (None, "")
        else str(data.get("abstractNote")),
        publication_title=None
        if data.get("publicationTitle") in (None, "")
        else str(data.get("publicationTitle")),
        doi=None if data.get("DOI") in (None, "") else str(data.get("DOI")),
        url=None if data.get("url") in (None, "") else str(data.get("url")),
        collection_keys=[str(value) for value in data.get("collections", [])],
        tags=tags,
        aliases=list(aliases or []),
        generated_citation_key=generated_citation_key,
        version=version,
    )


@dataclass
class MetadataIndex:
    """Persistent citekey and attachment metadata."""

    library_version: int | None = None
    items_by_key: dict[str, ItemRecord] | None = None
    attachments_by_key: dict[str, AttachmentRecord] | None = None
    citekey_to_item_key: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.items_by_key is None:
            self.items_by_key = {}
        if self.attachments_by_key is None:
            self.attachments_by_key = {}
        if self.citekey_to_item_key is None:
            self.citekey_to_item_key = {}

    @classmethod
    def load(cls, path: Path) -> "MetadataIndex":
        """Load an index from disk, or return an empty one."""
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            library_version=payload.get("library_version"),
            items_by_key={
                item_key: ItemRecord.from_dict(item)
                for item_key, item in payload.get("items_by_key", {}).items()
            },
            attachments_by_key={
                item_key: AttachmentRecord.from_dict(item)
                for item_key, item in payload.get("attachments_by_key", {}).items()
            },
        )._rebuild_citekey_map()

    def save(self, path: Path) -> None:
        """Persist the index to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "library_version": self.library_version,
            "items_by_key": {
                item_key: item.to_dict() for item_key, item in sorted(self.items_by_key.items())
            },
            "attachments_by_key": {
                item_key: item.to_dict()
                for item_key, item in sorted(self.attachments_by_key.items())
            },
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def rebuild_from_items(
        cls,
        raw_items: list[dict[str, object]],
        library_version: int | None,
        *,
        previous: "MetadataIndex | None" = None,
    ) -> "MetadataIndex":
        """Build a fresh index from a full Zotero item snapshot."""
        index = cls(library_version=library_version)
        previous = previous or cls()
        prepared: list[tuple[dict[str, object], int | None, str | None]] = []
        for raw_item in raw_items:
            data = raw_item.get("data", raw_item)
            if not isinstance(data, dict):
                continue
            version = _item_version(raw_item, data)
            item_type = str(data.get("itemType", "") or "")
            if item_type == "attachment":
                if data.get("deleted"):
                    continue
                attachment = attachment_from_data(data, version)
                if attachment is not None:
                    index.attachments_by_key[attachment.item_key] = attachment
                continue
            if not is_top_level_bibliographic(data) or data.get("deleted"):
                continue
            prepared.append((data, version, extract_preferred_citation_key(data)))

        index._assign_records(prepared, previous)
        index._rebuild_attachment_selection()
        index._rebuild_citekey_map()
        return index

    def apply_updates(
        self,
        raw_items: list[dict[str, object]],
        deleted_item_keys: list[str] | tuple[str, ...],
        library_version: int | None,
    ) -> None:
        """Apply incremental item and attachment updates."""
        touched_parents: set[str] = set()
        for item_key in deleted_item_keys:
            touched_parents.update(self._remove_item(item_key))

        prepared: list[tuple[dict[str, object], int | None, str | None]] = []
        for raw_item in raw_items:
            data = raw_item.get("data", raw_item)
            if not isinstance(data, dict):
                continue
            item_key = str(data.get("key", "") or "")
            version = _item_version(raw_item, data)
            if data.get("deleted"):
                touched_parents.update(self._remove_item(item_key))
                continue
            item_type = str(data.get("itemType", "") or "")
            if item_type == "attachment":
                attachment = attachment_from_data(data, version)
                if attachment is not None:
                    self.attachments_by_key[attachment.item_key] = attachment
                    if attachment.parent_item_key:
                        touched_parents.add(attachment.parent_item_key)
                continue
            if not is_top_level_bibliographic(data):
                continue
            prepared.append((data, version, extract_preferred_citation_key(data)))

        if prepared:
            previous = MetadataIndex(
                library_version=self.library_version,
                items_by_key={key: ItemRecord.from_dict(item.to_dict()) for key, item in self.items_by_key.items()},
                attachments_by_key=self.attachments_by_key.copy(),
            )
            self._assign_records(prepared, previous)
            touched_parents.update(str(data.get("key", "")) for data, _, _ in prepared)

        if touched_parents:
            self._rebuild_attachment_selection(touched_parents)
        self.library_version = library_version
        self._rebuild_citekey_map()

    def get_by_citekey(self, citekey: str) -> ItemRecord | None:
        """Look up a record by citekey or alias."""
        item_key = self.citekey_to_item_key.get(normalize_lookup_key(citekey))
        return None if item_key is None else self.items_by_key.get(item_key)

    def attachment_candidates(self, parent_item_key: str) -> list[AttachmentRecord]:
        """Return readable attachment candidates for a parent item."""
        candidates = [
            attachment
            for attachment in self.attachments_by_key.values()
            if attachment.parent_item_key == parent_item_key and attachment.is_text_like()
        ]
        return sorted(candidates, key=_attachment_priority)

    def _assign_records(
        self,
        prepared: list[tuple[dict[str, object], int | None, str | None]],
        previous: "MetadataIndex",
    ) -> None:
        ordered = sorted(prepared, key=lambda value: str(value[0].get("key", "")))

        real_key_items: list[tuple[dict[str, object], int | None, str]] = []
        generated_items: list[tuple[dict[str, object], int | None]] = []
        for data, version, preferred in ordered:
            if preferred:
                real_key_items.append((data, version, preferred))
            else:
                generated_items.append((data, version))

        for data, version, preferred in real_key_items:
            item_key = str(data.get("key", "") or "")
            previous_item = previous.items_by_key.get(item_key)
            citekey = self._dedupe_real_key(preferred, exclude_item_key=item_key)
            aliases = self._merged_aliases(previous_item, citekey)
            self.items_by_key[item_key] = item_from_data(
                data,
                version,
                citation_key=citekey,
                generated_citation_key=False,
                aliases=aliases,
            )

        for data, version in generated_items:
            item_key = str(data.get("key", "") or "")
            previous_item = previous.items_by_key.get(item_key)
            if (
                previous_item is not None
                and previous_item.generated_citation_key
                and self._citation_key_available(previous_item.citation_key, exclude_item_key=item_key)
            ):
                citekey = previous_item.citation_key
            else:
                citekey = self._reserve_generated_key(data, exclude_item_key=item_key)
            aliases = previous_item.aliases[:] if previous_item is not None else []
            self.items_by_key[item_key] = item_from_data(
                data,
                version,
                citation_key=citekey,
                generated_citation_key=True,
                aliases=aliases,
            )

    def _merged_aliases(self, previous_item: ItemRecord | None, current_citekey: str) -> list[str]:
        aliases: list[str] = []
        if previous_item is None:
            return aliases
        aliases.extend(previous_item.aliases)
        if normalize_lookup_key(previous_item.citation_key) != normalize_lookup_key(current_citekey):
            aliases.append(previous_item.citation_key)
        seen: set[str] = set()
        deduped: list[str] = []
        current_normalized = normalize_lookup_key(current_citekey)
        for alias in aliases:
            normalized = normalize_lookup_key(alias)
            if normalized == current_normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(alias)
        return deduped

    def _dedupe_real_key(self, preferred: str, *, exclude_item_key: str) -> str:
        candidate = preferred.strip()
        if not candidate:
            candidate = "item"
        if self._citation_key_available(candidate, exclude_item_key=exclude_item_key):
            return candidate
        suffix = 2
        while True:
            candidate_with_suffix = f"{candidate}-{suffix}"
            if self._citation_key_available(candidate_with_suffix, exclude_item_key=exclude_item_key):
                return candidate_with_suffix
            suffix += 1

    def _reserve_generated_key(self, data: dict[str, object], *, exclude_item_key: str) -> str:
        base = generated_base_key(data)
        for suffix in _alpha_suffixes():
            candidate = f"{base}{suffix}"
            if self._citation_key_available(candidate, exclude_item_key=exclude_item_key):
                return candidate
        raise RuntimeError("Unable to allocate a generated citation key.")

    def _citation_key_available(self, candidate: str, *, exclude_item_key: str) -> bool:
        normalized = normalize_lookup_key(candidate)
        for item_key, item in self.items_by_key.items():
            if item_key == exclude_item_key:
                continue
            if normalize_lookup_key(item.citation_key) == normalized:
                return False
            for alias in item.aliases:
                if normalize_lookup_key(alias) == normalized:
                    return False
        return True

    def _remove_item(self, item_key: str) -> set[str]:
        touched_parents: set[str] = set()
        if item_key in self.items_by_key:
            touched_parents.add(item_key)
            self.items_by_key.pop(item_key, None)

        attachment = self.attachments_by_key.pop(item_key, None)
        if attachment is not None and attachment.parent_item_key:
            touched_parents.add(attachment.parent_item_key)

        child_attachment_keys = [
            key
            for key, value in self.attachments_by_key.items()
            if value.parent_item_key == item_key
        ]
        for child_key in child_attachment_keys:
            self.attachments_by_key.pop(child_key, None)
        if child_attachment_keys:
            touched_parents.add(item_key)
        return touched_parents

    def _rebuild_attachment_selection(self, parent_keys: set[str] | None = None) -> None:
        target_keys = parent_keys if parent_keys is not None else set(self.items_by_key)
        for item_key in target_keys:
            record = self.items_by_key.get(item_key)
            if record is None:
                continue
            candidates = self.attachment_candidates(item_key)
            record.attachment_key = candidates[0].item_key if candidates else None

    def _rebuild_citekey_map(self) -> "MetadataIndex":
        self.citekey_to_item_key = {}
        for item in self.items_by_key.values():
            self.citekey_to_item_key[normalize_lookup_key(item.citation_key)] = item.item_key
            for alias in item.aliases:
                normalized = normalize_lookup_key(alias)
                self.citekey_to_item_key.setdefault(normalized, item.item_key)
        return self


def _item_version(raw_item: dict[str, object], data: dict[str, object]) -> int | None:
    raw_version = raw_item.get("version", data.get("version"))
    return None if raw_version in (None, "") else int(raw_version)


def _attachment_priority(attachment: AttachmentRecord) -> tuple[int, str]:
    if attachment.is_pdf():
        return (0, attachment.item_key)
    if attachment.is_text_like():
        return (1, attachment.item_key)
    return (2, attachment.item_key)


def _alpha_suffixes() -> list[str]:
    suffixes = [""]
    alphabet = [chr(value) for value in range(ord("a"), ord("z") + 1)]
    suffixes.extend(alphabet)
    for first in alphabet:
        for second in alphabet:
            suffixes.append(f"{first}{second}")
    return suffixes
