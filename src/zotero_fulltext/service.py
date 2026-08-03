"""High-level library service used by tools and resources."""

from __future__ import annotations

from time import monotonic
from typing import Any

from .cache import TTLCache
from .client import ZoteroClient, batched
from .config import Settings
from .errors import NoFulltextError, ZoteroClientError
from .index import MetadataIndex
from .models import AttachmentRecord, ItemRecord
from .text import extract_paragraphs, paragraph_slice, search_paragraphs


class ZoteroFulltextService:
    """Read-only, citekey-native service layer."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: ZoteroClient | None = None,
        index: MetadataIndex | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.client = client or ZoteroClient(self.settings)
        self.index = index or MetadataIndex.load(self.settings.metadata_path)
        self.paragraph_cache: TTLCache[str, list[str]] = TTLCache(
            self.settings.paragraph_cache_size,
            self.settings.paragraph_cache_ttl_sec,
        )
        self._last_refresh_check = 0.0

    def try_startup_sync(self) -> None:
        """Attempt an eager startup sync without failing server startup."""
        if not self.settings.startup_sync:
            return
        try:
            self.refresh_metadata(force=True)
        except ZoteroClientError:
            return

    def refresh_metadata(self, *, force: bool = False) -> bool:
        """Refresh the metadata index from Zotero."""
        now = monotonic()
        if (
            not force
            and self.index.library_version is not None
            and now - self._last_refresh_check < self.settings.index_refresh_min_interval_sec
        ):
            return False

        if self.index.library_version is None:
            items, version = self.client.fetch_all_items()
            self.index = MetadataIndex.rebuild_from_items(items, version, previous=self.index)
            self.index.save(self.settings.metadata_path)
            self._last_refresh_check = now
            return True

        previous_version = self.index.library_version
        changed, versions, current_version = self.client.get_changed_item_versions(
            previous_version,
            if_modified_since_version=previous_version,
        )
        if not changed:
            self._last_refresh_check = now
            return False

        deleted_item_keys, deleted_version = self.client.get_deleted(previous_version)
        deleted_item_key_set = set(deleted_item_keys)
        changed_item_keys = [key for key in versions if key not in deleted_item_key_set]
        changed_items: list[dict[str, Any]] = []
        for batch in batched(changed_item_keys, 50):
            changed_items.extend(self.client.get_items_by_keys(batch))

        # Never let the stored version move backwards: if Last-Modified-Version
        # or /deleted are unavailable, keeping the old version would replay the
        # same delta forever and could permanently skip deletions.
        next_version = max(
            current_version or 0,
            deleted_version or 0,
            previous_version or 0,
        )
        self.index.apply_updates(changed_items, deleted_item_keys, next_version)
        self._invalidate_changed_fulltext(previous_version)
        self.index.save(self.settings.metadata_path)
        self._last_refresh_check = now
        return True

    def _invalidate_changed_fulltext(self, since: int | None) -> None:
        """Evict cached paragraphs for attachments whose fulltext changed.

        Zotero re-indexes fulltext (e.g. after re-OCR) without necessarily
        touching item metadata, so the paragraph cache is refreshed from the
        dedicated ``/fulltext?since=`` endpoint. A changed ``Zotero-Server-ID``
        means the database was swapped, so the whole cache is dropped.
        """
        try:
            versions, server_id = self.client.get_changed_fulltext(since or 0)
        except ZoteroClientError:
            return
        if (
            server_id is not None
            and self.index.server_id
            and server_id != self.index.server_id
        ):
            self.paragraph_cache.clear()
        if server_id is not None:
            self.index.server_id = server_id
        for attachment_key in versions:
            self.paragraph_cache.delete(attachment_key)

    def library_summary(self) -> dict[str, Any]:
        """Return a lightweight snapshot of the indexed library."""
        self.refresh_metadata()
        return {
            "source": "zotero-local",
            "available": True,
            "library_type": self.settings.library_type,
            "library_id": self.settings.library_id,
            "api_base_url": self.settings.api_base_url,
            "indexed_items": len(self.index.items_by_key),
            "indexed_attachments": len(self.index.attachments_by_key),
            "known_citekeys": len(self.index.citekey_to_item_key),
            "library_version": self.index.library_version,
        }

    def lookup(self, citekey: str) -> dict[str, Any]:
        """Look up a single item by citekey."""
        self.refresh_metadata()
        record = self.index.get_by_citekey(citekey)
        if record is None:
            return {
                "source": "zotero-local",
                "found": False,
                "citekey": citekey,
                "item": None,
            }
        return {
            "source": "zotero-local",
            "found": True,
            "citekey": record.citation_key,
            "item": self._item_detail(record),
        }

    def search(
        self,
        query: str,
        *,
        collection: str | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Search Zotero metadata and indexed fulltext."""
        normalized_query = query.strip()
        if not normalized_query:
            return {
                "source": "zotero-local",
                "query": query,
                "count": 0,
                "results": [],
            }

        self.refresh_metadata()
        result_limit = max(1, min(25, limit or self.settings.default_search_limit))
        raw_results = self.client.search_items(
            normalized_query,
            collection=collection,
            tag=tag,
            limit=min(100, max(result_limit * 3, result_limit)),
        )

        exact_match = self.index.get_by_citekey(normalized_query)
        results: list[dict[str, Any]] = []
        seen_item_keys: set[str] = set()
        if exact_match is not None and self._record_matches_filters(
            exact_match,
            collection=collection,
            tag=tag,
        ):
            seen_item_keys.add(exact_match.item_key)
            results.append({**self._item_summary(exact_match), "match_source": "citekey"})

        for raw_result in raw_results:
            data = raw_result.get("data", raw_result)
            if not isinstance(data, dict):
                continue
            item_type = str(data.get("itemType", "") or "")
            item_key = (
                str(data.get("parentItem", "") or "")
                if item_type == "attachment"
                else str(data.get("key", "") or "")
            )
            if not item_key or item_key in seen_item_keys:
                continue
            record = self.index.items_by_key.get(item_key)
            if record is None:
                continue
            seen_item_keys.add(item_key)
            match_source = "attachment" if item_type == "attachment" else "metadata"
            results.append({**self._item_summary(record), "match_source": match_source})
            if len(results) >= result_limit:
                break

        return {
            "source": "zotero-local",
            "query": query,
            "collection": collection,
            "tag": tag,
            "count": len(results),
            "results": results,
            "exact_citekey_match": None if exact_match is None else exact_match.citation_key,
        }

    def collections(self) -> dict[str, Any]:
        """Return collections for the current library."""
        collections = self.client.list_collections()
        payload = []
        for collection in collections:
            data = collection.get("data", collection)
            meta = collection.get("meta", {})
            if not isinstance(data, dict):
                continue
            payload.append(
                {
                    "key": str(data.get("key", "") or ""),
                    "name": str(data.get("name", "") or ""),
                    "parent_collection": (
                        None
                        if data.get("parentCollection") in (None, "")
                        else str(data.get("parentCollection"))
                    ),
                    "item_count": meta.get("numItems"),
                }
            )
        return {
            "source": "zotero-local",
            "count": len(payload),
            "collections": payload,
        }

    def fulltext(self, citekey: str, *, offset: int = 0, limit: int | None = None) -> dict[str, Any]:
        """Return numbered paragraphs for a single citekey."""
        self.refresh_metadata()
        record = self.index.get_by_citekey(citekey)
        if record is None:
            return {
                "source": "zotero-local",
                "found": False,
                "citekey": citekey,
                "paragraphs": [],
            }
        paragraphs, error_code = self._paragraphs_for_record(record)
        if paragraphs is None:
            return {
                "source": "zotero-local",
                "found": True,
                "citekey": record.citation_key,
                "has_fulltext": False,
                "error": error_code,
                "item": self._item_summary(record),
                "paragraphs": [],
            }
        paragraph_limit = max(1, min(200, limit or self.settings.default_fulltext_limit))
        safe_offset = max(0, offset)
        returned_paragraphs = paragraph_slice(
            paragraphs,
            offset=safe_offset,
            limit=paragraph_limit,
            max_chars=max(1, self.settings.max_fulltext_chars),
        )
        next_offset = safe_offset + len(returned_paragraphs)
        return {
            "source": "zotero-local",
            "found": True,
            "citekey": record.citation_key,
            "has_fulltext": True,
            "item": self._item_summary(record),
            "offset": safe_offset,
            "limit": paragraph_limit,
            "paragraph_count": len(paragraphs),
            "returned_count": len(returned_paragraphs),
            "returned_chars": sum(len(paragraph["text"]) for paragraph in returned_paragraphs),
            "max_chars": max(1, self.settings.max_fulltext_chars),
            "truncated": next_offset < len(paragraphs),
            "next_offset": next_offset if next_offset < len(paragraphs) else None,
            "paragraphs": returned_paragraphs,
        }

    def fulltext_search(
        self,
        citekey: str,
        query: str,
        *,
        before: int | None = None,
        after: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search within a single item's fulltext."""
        self.refresh_metadata()
        record = self.index.get_by_citekey(citekey)
        if record is None:
            return {
                "source": "zotero-local",
                "found": False,
                "citekey": citekey,
                "query": query,
                "matches": [],
            }
        paragraphs, error_code = self._paragraphs_for_record(record)
        if paragraphs is None:
            return {
                "source": "zotero-local",
                "found": True,
                "citekey": record.citation_key,
                "query": query,
                "has_fulltext": False,
                "error": error_code,
                "matches": [],
            }
        context_before = self.settings.default_fulltext_context if before is None else before
        context_after = self.settings.default_fulltext_context if after is None else after
        matches = search_paragraphs(
            paragraphs,
            query,
            before=context_before,
            after=context_after,
            limit=max(1, min(50, limit)),
        )
        return {
            "source": "zotero-local",
            "found": True,
            "citekey": record.citation_key,
            "query": query,
            "has_fulltext": True,
            "item": self._item_summary(record),
            "count": len(matches),
            "matches": matches,
        }

    def hydrate_item_children(self, item_key: str) -> None:
        """Refresh child attachments for a specific item."""
        children = self.client.get_children(item_key)
        attachment_children = []
        for child in children:
            data = child.get("data", child)
            if not isinstance(data, dict):
                continue
            item_type = str(data.get("itemType", "") or "")
            if item_type == "attachment":
                attachment_children.append(child)
        if attachment_children:
            self.index.apply_updates(attachment_children, [], self.index.library_version)
            self.index.save(self.settings.metadata_path)

    def _paragraphs_for_record(self, record: ItemRecord) -> tuple[list[str] | None, str | None]:
        attachment_candidates = self.index.attachment_candidates(record.item_key)
        if not attachment_candidates:
            self.hydrate_item_children(record.item_key)
            attachment_candidates = self.index.attachment_candidates(record.item_key)
        if not attachment_candidates:
            return None, "NO_ATTACHMENT"
        # Warm path: a previously confirmed attachment whose paragraphs are
        # still cached needs no further Zotero calls.
        if record.attachment_key:
            cached = self.paragraph_cache.get(record.attachment_key)
            if cached is not None:
                return cached, None
        attachment_candidates = _prioritize_selected_attachment(
            attachment_candidates,
            record.attachment_key,
        )
        # Several attachments can share a parent (e.g. the article plus a
        # supplemental appendix), and they often carry near-identical titles
        # and content types. Pick the one with the most indexed text, which is
        # almost always the main document rather than a supplement.
        best_paragraphs: list[str] | None = None
        best_length = -1
        for attachment in attachment_candidates:
            try:
                fulltext = self.client.get_fulltext(attachment.item_key)
            except NoFulltextError:
                continue
            content = str(fulltext.get("content", "") or "")
            paragraphs = extract_paragraphs(
                content,
                max_chars=max(1, self.settings.max_paragraph_chars),
            )
            if not paragraphs:
                continue
            if len(content) > best_length:
                best_paragraphs = paragraphs
                best_length = len(content)
                record.attachment_key = attachment.item_key
        if best_paragraphs is None:
            return None, "NO_FULLTEXT_INDEX"
        self.paragraph_cache.set(record.attachment_key, best_paragraphs)
        return best_paragraphs, None

    def _record_matches_filters(
        self,
        record: ItemRecord,
        *,
        collection: str | None,
        tag: str | None,
    ) -> bool:
        if collection and collection not in record.collection_keys:
            return False
        if tag and tag not in record.tags:
            return False
        return True

    def _item_summary(self, record: ItemRecord) -> dict[str, Any]:
        return {
            "citekey": record.citation_key,
            "item_key": record.item_key,
            "item_uri": f"zotero://item/{record.citation_key}",
            "fulltext_uri": f"zotero://fulltext/{record.citation_key}",
            "title": record.title,
            "creators": record.creators_by_role,
            "author_summary": record.author_summary,
            "year": record.year,
            "item_type": record.item_type,
            "publication_title": record.publication_title,
            "has_fulltext": record.has_fulltext,
            "generated_citekey": record.generated_citation_key,
        }

    def _item_detail(self, record: ItemRecord) -> dict[str, Any]:
        payload = self._item_summary(record)
        payload.update(
            {
                "date": record.date,
                "abstract": record.abstract,
                "doi": record.doi,
                "url": record.url,
                "collections": record.collection_keys,
                "tags": record.tags,
                "attachment_key": record.attachment_key,
                "aliases": record.aliases,
            }
        )
        return payload


def _prioritize_selected_attachment(
    attachments: list[AttachmentRecord],
    selected_attachment_key: str | None,
) -> list[AttachmentRecord]:
    if not selected_attachment_key:
        return attachments
    return sorted(
        attachments,
        key=lambda attachment: 0 if attachment.item_key == selected_attachment_key else 1,
    )
