"""Tests for read-only service behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zotero_fulltext.config import Settings
from zotero_fulltext.errors import NoFulltextError
from zotero_fulltext.index import MetadataIndex
from zotero_fulltext.service import ZoteroFulltextService


def make_item(
    key: str,
    *,
    title: str,
    citation_key: str | None = None,
    extra: str = "",
    version: int = 1,
    collections: list[str] | None = None,
    tags: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "version": version,
        "data": {
            "key": key,
            "version": version,
            "itemType": "journalArticle",
            "title": title,
            "date": "2020",
            "citationKey": citation_key,
            "extra": extra,
            "creators": [{"creatorType": "author", "lastName": "Smith"}],
            "collections": collections or [],
            "tags": tags or [],
        },
    }


def make_attachment(key: str, parent: str) -> dict[str, object]:
    return {
        "key": key,
        "version": 1,
        "data": {
            "key": key,
            "version": 1,
            "itemType": "attachment",
            "parentItem": parent,
            "title": "PDF",
            "contentType": "application/pdf",
            "linkMode": "imported_file",
        },
    }


class FakeClient:
    def __init__(self) -> None:
        self.fulltext_calls = 0
        self.search_payload: list[dict[str, object]] = []
        self.collections_payload: list[dict[str, object]] = []
        self.children_payload: dict[str, list[dict[str, object]]] = {}
        self.fulltexts: dict[str, dict[str, object]] = {}

    def fetch_all_items(self):
        return [], 0

    def get_changed_item_versions(self, since, *, if_modified_since_version=None):
        return False, {}, since

    def get_deleted(self, since):
        return [], since

    def get_items_by_keys(self, item_keys):
        return []

    def search_items(self, query, *, collection=None, tag=None, limit=10):
        return self.search_payload

    def list_collections(self):
        return self.collections_payload

    def get_children(self, item_key):
        return self.children_payload.get(item_key, [])

    def get_fulltext(self, attachment_key):
        self.fulltext_calls += 1
        if attachment_key not in self.fulltexts:
            raise NoFulltextError("Missing fulltext")
        return self.fulltexts[attachment_key]


class ZoteroFulltextServiceTest(unittest.TestCase):
    def make_settings(self, cache_dir: str) -> Settings:
        return Settings(
            api_base_url="http://127.0.0.1:23119/api",
            library_type="user",
            library_id="0",
            api_key=None,
            cache_dir=Path(cache_dir),
            index_refresh_min_interval_sec=999999,
            paragraph_cache_ttl_sec=60,
            paragraph_cache_size=16,
            default_search_limit=10,
            default_fulltext_limit=80,
            default_fulltext_context=1,
            startup_sync=False,
        )

    def test_lookup_and_search_return_strict_zero_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            service = ZoteroFulltextService(settings, client=client, index=MetadataIndex())
            lookup = service.lookup("missing2020")
            search = service.search("missing")
        self.assertFalse(lookup["found"])
        self.assertEqual(search["results"], [])

    def test_lookup_includes_resource_uris(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [make_item("AAA111", title="Paper", citation_key="paper2020")],
                5,
            )
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.lookup("paper2020")
        self.assertTrue(result["found"])
        self.assertEqual(result["item"]["item_uri"], "zotero://item/paper2020")
        self.assertEqual(result["item"]["fulltext_uri"], "zotero://fulltext/paper2020")

    def test_fulltext_uses_cached_paragraphs_on_warm_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("ATTPDF", "AAA111"),
                ],
                5,
            )
            client.fulltexts["ATTPDF"] = {
                "content": "Intro paragraph.\n\nResults paragraph.\n\nConclusion paragraph.",
                "indexedPages": 3,
                "totalPages": 3,
            }
            service = ZoteroFulltextService(settings, client=client, index=index)
            first = service.fulltext("paper2020")
            second = service.fulltext("paper2020")
        self.assertTrue(first["found"])
        self.assertEqual(client.fulltext_calls, 1)
        self.assertEqual(second["paragraph_count"], 3)

    def test_fulltext_search_reports_missing_fulltext_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("ATTPDF", "AAA111"),
                ],
                5,
            )
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.fulltext_search("paper2020", "results")
        self.assertEqual(result["error"], "NO_FULLTEXT_INDEX")
        self.assertEqual(result["matches"], [])

    def test_search_ranks_exact_citekey_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Exact", citation_key="paper2020"),
                    make_item("BBB222", title="Other", citation_key="other2020"),
                ],
                5,
            )
            client.search_payload = [
                make_item("BBB222", title="Other", citation_key="other2020"),
                make_item("AAA111", title="Exact", citation_key="paper2020"),
            ]
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.search("paper2020")
        self.assertEqual(result["results"][0]["citekey"], "paper2020")
        self.assertEqual(result["results"][0]["match_source"], "citekey")

    def test_exact_citekey_match_respects_collection_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Exact", citation_key="paper2020", collections=["COLL1"]),
                    make_item("BBB222", title="Other", citation_key="other2020", collections=["COLL2"]),
                ],
                5,
            )
            client.search_payload = []
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.search("paper2020", collection="COLL2")
        self.assertEqual(result["results"], [])

    def test_fulltext_tries_next_readable_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("A1PDF", "AAA111"),
                    make_attachment("B2PDF", "AAA111"),
                ],
                5,
            )
            client.fulltexts["B2PDF"] = {
                "content": "Only indexed copy.\n\nUseful results paragraph.",
                "indexedPages": 2,
                "totalPages": 2,
            }
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.fulltext("paper2020")
        self.assertTrue(result["found"])
        self.assertEqual(result["paragraph_count"], 2)
        self.assertEqual(client.fulltext_calls, 2)


if __name__ == "__main__":
    unittest.main()
