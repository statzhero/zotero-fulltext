"""Persistent metadata index for citekey-native lookups."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import unicodedata

from .models import AttachmentRecord, ItemRecord


_CITATION_KEY_LINE_RE = re.compile(
    r"^\s*(?:Citation Key|citationkey)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_YEAR_TOKEN_RE = re.compile(r"(?:19|20)\d{2}")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Letter runs (any script) or digit runs, so "real-effects" and "smith2016"
# both split into words.
_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+")
# Letters that NFKD leaves intact but readers type in plain ASCII.
_FOLD_TABLE = str.maketrans(
    {"ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ð": "d", "ł": "l", "ı": "i", "þ": "th"}
)
# Function words and name particles that would otherwise match half the
# library ("of", "the", "de", "van").
_SEARCH_STOPWORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is",
        "of", "on", "or", "the", "to", "vs", "via", "with",
        "da", "de", "del", "der", "di", "du", "la", "le", "van", "von",
    }
)
_MAX_NEAR_CITEKEYS = 10


def normalize_lookup_key(value: str) -> str:
    """Normalize a citekey for case-insensitive lookup."""
    return value.strip().casefold()


def fold_text(value: str) -> str:
    """Casefold and strip diacritics, so 'Müller' compares equal to 'muller'."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.translate(_FOLD_TABLE)


def search_tokens(value: str) -> list[str]:
    """Split text into folded word and number tokens."""
    return _TOKEN_RE.findall(fold_text(value))


def query_terms(query: str) -> list[str]:
    """Return the distinct, meaningful search tokens of a query, in order."""
    terms: list[str] = []
    for token in search_tokens(query):
        if token in _SEARCH_STOPWORDS or (len(token) < 2 and not token.isdigit()):
            continue
        if token not in terms:
            terms.append(token)
    return terms


def citekey_parts(citekey: str) -> tuple[str, int | None]:
    """Split a citekey into a folded surname stem and a year.

    The stem is the letters before the first digit ('bar-yosef2019' gives
    'baryosef'); the year is the first four-digit year anywhere in the key.
    """
    folded = fold_text(citekey.strip())
    head = re.split(r"\d", folded, maxsplit=1)[0]
    stem = "".join(_TOKEN_RE.findall(head))
    year_match = _YEAR_RE.search(folded)
    return stem, None if year_match is None else int(year_match.group(0))


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


def creator_names(creators: list[dict[str, object]]) -> list[dict[str, str]]:
    """Convert Zotero creator objects into name/role dicts."""
    result: list[dict[str, str]] = []
    for creator in creators:
        last_name = str(creator.get("lastName", "") or "").strip()
        first_name = str(creator.get("firstName", "") or "").strip()
        single_name = str(creator.get("name", "") or "").strip()
        name = last_name or single_name or first_name
        if name:
            role = str(creator.get("creatorType", "author") or "author").strip()
            result.append({"name": name, "role": role})
    return result


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
    server_id: str | None = None
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
        """Load an index from disk, or return an empty one.

        A missing, unreadable, or corrupt file yields an empty index so the
        next refresh rebuilds it rather than failing startup.
        """
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                library_version=payload.get("library_version"),
                server_id=payload.get("server_id"),
                items_by_key={
                    item_key: ItemRecord.from_dict(item)
                    for item_key, item in payload.get("items_by_key", {}).items()
                },
                attachments_by_key={
                    item_key: AttachmentRecord.from_dict(item)
                    for item_key, item in payload.get("attachments_by_key", {}).items()
                },
            )._rebuild_citekey_map()
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        """Persist the index to disk atomically (temp file + os.replace)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "library_version": self.library_version,
            "server_id": self.server_id,
            "items_by_key": {
                item_key: item.to_dict() for item_key, item in sorted(self.items_by_key.items())
            },
            "attachments_by_key": {
                item_key: item.to_dict()
                for item_key, item in sorted(self.attachments_by_key.items())
            },
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            tmp_path.write_text(text, encoding="utf-8")
            os.replace(tmp_path, path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

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

    def metadata_matches(self, query: str) -> list[ItemRecord]:
        """Rank items whose creators, title, or year match query tokens.

        Tokens match whole words, ignoring case and diacritics. Matching is
        per token, so a query that mixes surnames, a year, and topic words
        still finds the item through whichever tokens hit. An item qualifies
        when a creator surname matches, or when every query token matches
        its title, creators, or year. Title-only partial matches are left to
        Zotero's own search, since a single common word would flood the
        results. A bare year matches nothing on its own.
        """
        terms = query_terms(query)
        years = {term for term in terms if _YEAR_TOKEN_RE.fullmatch(term)}
        words = [term for term in terms if term not in years]
        if not words:
            return []

        ranked: list[tuple[tuple[int, int, int, int, str], ItemRecord]] = []
        for record in list(self.items_by_key.values()):
            creator_tokens: set[str] = set()
            for creator in record.creators:
                creator_tokens.update(search_tokens(creator.get("name", "")))
            creator_hits = {word for word in words if word in creator_tokens}
            title_tokens = set(search_tokens(record.title))
            title_hits = {word for word in words if word in title_tokens}
            year_hit = record.year in years
            matched = len(creator_hits | title_hits) + int(year_hit)
            if not creator_hits and not (title_hits and matched == len(terms)):
                continue
            first_author = _first_author_tokens(record)
            first_author_hit = int(any(word in first_author for word in creator_hits))
            year_value = int(record.year) if record.year and record.year.isdigit() else 0
            sort_key = (
                -matched,
                -len(creator_hits),
                -first_author_hit,
                -year_value,
                record.citation_key.casefold(),
            )
            ranked.append((sort_key, record))
        ranked.sort(key=lambda pair: pair[0])
        return [record for _, record in ranked]

    def near_citekeys(self, citekey: str) -> list[ItemRecord]:
        """Suggest items whose key is close to a citekey that did not resolve.

        A candidate shares the surname stem (through its citekey, an alias,
        or its first author) and lies within one year, so 'smith2016a'
        suggests 'smith2016', 'smith2016b', and 'smith2017'.
        """
        stem, year = citekey_parts(citekey)
        if not stem:
            return []
        ranked: list[tuple[tuple[int, int, str], ItemRecord]] = []
        for record in list(self.items_by_key.values()):
            key_parts = [citekey_parts(key) for key in [record.citation_key, *record.aliases]]
            key_stem_hit = any(key_stem == stem for key_stem, _ in key_parts)
            author_hit = "".join(_first_author_tokens(record)) == stem
            if not key_stem_hit and not author_hit:
                continue
            record_year = int(record.year) if record.year and record.year.isdigit() else None
            if record_year is None:
                record_year = next((key_year for _, key_year in key_parts if key_year), None)
            if year is not None and (record_year is None or abs(record_year - year) > 1):
                continue
            year_gap = 0 if year is None or record_year is None else abs(record_year - year)
            sort_key = (year_gap, int(not key_stem_hit), record.citation_key.casefold())
            ranked.append((sort_key, record))
        ranked.sort(key=lambda pair: pair[0])
        return [record for _, record in ranked[:_MAX_NEAR_CITEKEYS]]

    def attachment_candidates(self, parent_item_key: str) -> list[AttachmentRecord]:
        """Return readable attachment candidates for a parent item."""
        # Snapshot first: readers on other threads must not iterate the dict
        # while a refresh mutates it.
        candidates = [
            attachment
            for attachment in list(self.attachments_by_key.values())
            if attachment.parent_item_key == parent_item_key and attachment.is_text_like()
        ]
        return sorted(candidates, key=_attachment_priority)

    def _assign_records(
        self,
        prepared: list[tuple[dict[str, object], int | None, str | None]],
        previous: "MetadataIndex",
    ) -> None:
        ordered = sorted(prepared, key=lambda value: str(value[0].get("key", "")))
        reserved_keys = self._reserved_lookup_keys()

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
            _discard_reserved_item(reserved_keys, item_key)
            citekey = self._dedupe_real_key(preferred, reserved_keys=reserved_keys)
            aliases = self._merged_aliases(previous_item, citekey)
            record = item_from_data(
                data,
                version,
                citation_key=citekey,
                generated_citation_key=False,
                aliases=aliases,
            )
            self.items_by_key[item_key] = record
            _add_reserved_item(reserved_keys, record)

        for data, version in generated_items:
            item_key = str(data.get("key", "") or "")
            previous_item = previous.items_by_key.get(item_key)
            _discard_reserved_item(reserved_keys, item_key)
            if (
                previous_item is not None
                and previous_item.generated_citation_key
                and self._citation_key_available(
                    previous_item.citation_key,
                    reserved_keys=reserved_keys,
                )
            ):
                citekey = previous_item.citation_key
            else:
                citekey = self._reserve_generated_key(data, reserved_keys=reserved_keys)
            aliases = previous_item.aliases[:] if previous_item is not None else []
            record = item_from_data(
                data,
                version,
                citation_key=citekey,
                generated_citation_key=True,
                aliases=aliases,
            )
            self.items_by_key[item_key] = record
            _add_reserved_item(reserved_keys, record)

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

    def _dedupe_real_key(
        self,
        preferred: str,
        *,
        reserved_keys: dict[str, set[str]],
    ) -> str:
        candidate = preferred.strip()
        if not candidate:
            candidate = "item"
        if self._citation_key_available(candidate, reserved_keys=reserved_keys):
            return candidate
        suffix = 2
        while True:
            candidate_with_suffix = f"{candidate}-{suffix}"
            if self._citation_key_available(candidate_with_suffix, reserved_keys=reserved_keys):
                return candidate_with_suffix
            suffix += 1

    def _reserve_generated_key(
        self,
        data: dict[str, object],
        *,
        reserved_keys: dict[str, set[str]],
    ) -> str:
        base = generated_base_key(data)
        for suffix in _alpha_suffixes():
            candidate = f"{base}{suffix}"
            if self._citation_key_available(candidate, reserved_keys=reserved_keys):
                return candidate
        raise RuntimeError("Unable to allocate a generated citation key.")

    def _citation_key_available(
        self,
        candidate: str,
        *,
        reserved_keys: dict[str, set[str]],
    ) -> bool:
        normalized = normalize_lookup_key(candidate)
        return normalized not in reserved_keys

    def _reserved_lookup_keys(self) -> dict[str, set[str]]:
        reserved_keys: dict[str, set[str]] = {}
        for item in self.items_by_key.values():
            _add_reserved_item(reserved_keys, item)
        return reserved_keys

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
        # Build into a local dict and swap at the end so concurrent lookups
        # never see a partially rebuilt map.
        citekey_map: dict[str, str] = {}
        for item in list(self.items_by_key.values()):
            citekey_map[normalize_lookup_key(item.citation_key)] = item.item_key
            for alias in item.aliases:
                normalized = normalize_lookup_key(alias)
                citekey_map.setdefault(normalized, item.item_key)
        self.citekey_to_item_key = citekey_map
        return self


def _item_version(raw_item: dict[str, object], data: dict[str, object]) -> int | None:
    raw_version = raw_item.get("version", data.get("version"))
    return None if raw_version in (None, "") else int(raw_version)


def _first_author_tokens(record: ItemRecord) -> list[str]:
    authors = [creator for creator in record.creators if creator.get("role") == "author"]
    first = (authors or record.creators or [{}])[0]
    return search_tokens(first.get("name", ""))


def _attachment_priority(attachment: AttachmentRecord) -> tuple[int, str]:
    if attachment.is_pdf():
        return (0, attachment.item_key)
    if attachment.is_text_like():
        return (1, attachment.item_key)
    return (2, attachment.item_key)


def _add_reserved_item(reserved_keys: dict[str, set[str]], item: ItemRecord) -> None:
    for lookup_key in [item.citation_key, *item.aliases]:
        normalized = normalize_lookup_key(lookup_key)
        if not normalized:
            continue
        reserved_keys.setdefault(normalized, set()).add(item.item_key)


def _discard_reserved_item(reserved_keys: dict[str, set[str]], item_key: str) -> None:
    for normalized, item_keys in list(reserved_keys.items()):
        item_keys.discard(item_key)
        if not item_keys:
            reserved_keys.pop(normalized, None)


def _alpha_suffixes() -> list[str]:
    suffixes = [""]
    alphabet = [chr(value) for value in range(ord("a"), ord("z") + 1)]
    suffixes.extend(alphabet)
    for first in alphabet:
        for second in alphabet:
            suffixes.append(f"{first}{second}")
    return suffixes
