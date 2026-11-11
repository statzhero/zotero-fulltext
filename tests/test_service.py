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
    creators: list[dict[str, str]] | None = None,
    date: str = "2020",
) -> dict[str, object]:
    return {
        "key": key,
        "version": version,
        "data": {
            "key": key,
            "version": version,
            "itemType": "journalArticle",
            "title": title,
            "date": date,
            "citationKey": citation_key,
            "extra": extra,
            "creators": creators or [{"creatorType": "author", "lastName": "Smith"}],
            "collections": collections or [],
            "tags": tags or [],
        },
    }


def make_attachment(
    key: str, parent: str, *, content_type: str = "application/pdf"
) -> dict[str, object]:
    return {
        "key": key,
        "version": 1,
        "data": {
            "key": key,
            "version": 1,
            "itemType": "attachment",
            "parentItem": parent,
            "title": "PDF",
            "contentType": content_type,
            "linkMode": "imported_file",
        },
    }


class FakeClient:
    def __init__(self) -> None:
        self.fulltext_calls = 0
        self.search_calls = 0
        self.search_payload: list[dict[str, object]] = []
        self.collections_payload: list[dict[str, object]] = []
        self.children_payload: dict[str, list[dict[str, object]]] = {}
        self.fulltexts: dict[str, dict[str, object]] = {}
        self.fulltext_versions: dict[str, int] = {}
        self.all_items: list[dict[str, object]] = []
        self.library_version: int | None = None
        self.server_id: str | None = None

    def fetch_all_items(self):
        return self.all_items, self.library_version or 0

    def get_changed_item_versions(self, since, *, if_modified_since_version=None):
        # Mirrors Zotero: 304 whenever its version is not above the cursor.
        current = since if self.library_version is None else self.library_version
        return False, {}, current

    def get_deleted(self, since):
        return [], since

    def get_changed_fulltext(self, since):
        changed = {key: version for key, version in self.fulltext_versions.items() if version > since}
        return changed, self.server_id

    def get_items_by_keys(self, item_keys):
        return []

    def search_items(self, query, *, collection=None, tag=None, limit=10):
        # Zotero pages its quick search, so rows past ``limit`` never arrive.
        self.search_calls += 1
        return self.search_payload[:limit]

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
            max_paragraph_chars=1800,
            max_fulltext_chars=60000,
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

    def test_lookup_groups_creators_by_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            item = make_item("AAA111", title="Chapter", citation_key="chapter2020")
            item["data"]["creators"] = [
                {"creatorType": "author", "lastName": "Arbel"},
                {"creatorType": "editor", "lastName": "Kim"},
            ]
            index = MetadataIndex.rebuild_from_items([item], 5)
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.lookup("chapter2020")
        self.assertEqual(result["item"]["creators"], {"author": ["Arbel"], "editor": ["Kim"]})
        self.assertEqual(result["item"]["author_summary"], "Arbel")

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

    def test_reindexed_fulltext_evicted_without_metadata_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            settings.index_refresh_min_interval_sec = 0
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("ATTPDF", "AAA111"),
                ],
                5,
            )
            client.fulltexts["ATTPDF"] = {"content": "Old OCR text."}
            service = ZoteroFulltextService(settings, client=client, index=index)
            first = service.fulltext("paper2020")

            # Zotero re-indexes the attachment (e.g. re-OCR); no item
            # metadata changes, only the fulltext content version moves.
            client.fulltexts["ATTPDF"] = {"content": "New OCR text."}
            client.fulltext_versions["ATTPDF"] = 6
            second = service.fulltext("paper2020")
            third = service.fulltext("paper2020")
        self.assertEqual(first["paragraphs"][0]["text"], "Old OCR text.")
        self.assertEqual(second["paragraphs"][0]["text"], "New OCR text.")
        # The already-seen content version must not be replayed: the third
        # call is served from cache instead of re-fetching.
        self.assertEqual(third["paragraphs"][0]["text"], "New OCR text.")
        self.assertEqual(client.fulltext_calls, 2)

    def test_reset_library_version_triggers_full_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [make_item("AAA111", title="Old", citation_key="old2020", version=26851)],
                26853,
            )
            # Zotero's counter restarts far below the stored cursor, so the
            # incremental check answers "not modified" for the new item.
            client.library_version = 58
            client.all_items = [
                make_item("AAA111", title="Old", citation_key="old2020", version=0),
                make_item("BBB222", title="New", citation_key="new2026", version=58),
            ]
            service = ZoteroFulltextService(settings, client=client, index=index)
            refreshed = service.refresh_metadata(force=True)
            result = service.lookup("new2026")
            saved = MetadataIndex.load(settings.metadata_path)
        self.assertTrue(refreshed)
        self.assertTrue(result["found"])
        self.assertEqual(service.index.library_version, 58)
        self.assertEqual(saved.library_version, 58)

    def test_changed_server_id_triggers_full_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [make_item("AAA111", title="Old", citation_key="old2020")],
                5,
            )
            index.server_id = "old-db"
            # A different database whose counter happens to match ours.
            client.library_version = 5
            client.server_id = "new-db"
            client.all_items = [make_item("BBB222", title="New", citation_key="new2026")]
            service = ZoteroFulltextService(settings, client=client, index=index)
            refreshed = service.refresh_metadata(force=True)
            result = service.lookup("new2026")
        self.assertTrue(refreshed)
        self.assertTrue(result["found"])
        self.assertFalse(service.lookup("old2020")["found"])
        self.assertEqual(service.index.server_id, "new-db")

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

    def make_author_search_library(self, temp_dir: str) -> ZoteroFulltextService:
        """Mirror the live failure: Leuz and Wysocki (2016) plus 120 citing papers.

        Zotero's quick search returns each citing paper's attachment as its
        own row, newest first, and the cited item itself only after all of
        them, beyond the 100-row page the service requests.
        """
        authors = [
            {"creatorType": "author", "lastName": "Leuz"},
            {"creatorType": "author", "lastName": "Wysocki"},
        ]
        items = [
            make_item(
                "LEUZ01",
                title="The Economics of Disclosure and Financial Reporting Regulation",
                citation_key="leuz2016",
                creators=authors,
                date="2016",
            ),
            make_item(
                "LEUZ02",
                title="Earnings management and investor protection",
                citation_key="leuz2003",
                creators=[authors[0], {"creatorType": "author", "lastName": "Nanda"}, authors[1]],
                date="2003",
            ),
            make_item(
                "CETIN1",
                title="The Real Effects of Accounting on R&D Alliance Formation",
                citation_key="cetin2026",
                creators=[{"creatorType": "author", "lastName": "Çetin"}],
                date="2026",
            ),
            make_attachment("LEUZPDF", "LEUZ01"),
        ]
        citing_rows = []
        for number in range(120):
            item_key = f"CITE{number:03d}"
            items.append(
                make_item(
                    item_key,
                    title=f"Disclosure study {number}",
                    citation_key=f"citer{number}",
                    creators=[{"creatorType": "author", "lastName": f"Citer{number}"}],
                )
            )
            attachment = make_attachment(f"PDF{number:03d}", item_key)
            items.append(attachment)
            citing_rows.append(attachment)
        client = FakeClient()
        client.search_payload = [*citing_rows, items[0]]
        settings = self.make_settings(temp_dir)
        return ZoteroFulltextService(
            settings,
            client=client,
            index=MetadataIndex.rebuild_from_items(items, 5),
        )

    def test_author_search_ranks_item_above_citing_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.make_author_search_library(temp_dir)
            result = service.search("Leuz Wysocki", limit=25)
        self.assertEqual(result["results"][0]["citekey"], "leuz2016")
        self.assertEqual(result["results"][0]["match_source"], "metadata")
        self.assertEqual(result["results"][1]["citekey"], "leuz2003")
        self.assertEqual(result["count"], 25)
        self.assertEqual(
            {hit["match_source"] for hit in result["results"][2:]},
            {"attachment"},
        )

    def test_author_search_with_year_and_topic_words(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.make_author_search_library(temp_dir)
            with_year = service.search("Leuz Wysocki 2016", limit=5)
            long_query = service.search("Leuz Wysocki 2016 real-effects review JAR", limit=5)
        for result in (with_year, long_query):
            self.assertEqual(result["results"][0]["citekey"], "leuz2016")
            self.assertEqual(result["results"][0]["match_source"], "metadata")

    def test_author_search_ignores_diacritics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.make_author_search_library(temp_dir)
            plain = service.search("Cetin")
            accented = service.search("ÇETIN 2026")
        for result in (plain, accented):
            self.assertEqual(result["results"][0]["citekey"], "cetin2026")
            self.assertEqual(result["results"][0]["match_source"], "metadata")

    def test_full_metadata_page_skips_zotero_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.make_author_search_library(temp_dir)
            result = service.search("Leuz Wysocki", limit=2)
        self.assertEqual([hit["citekey"] for hit in result["results"]], ["leuz2016", "leuz2003"])
        self.assertEqual(service.client.search_calls, 0)

    def test_zotero_metadata_hits_rank_above_attachment_hits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            abstract_hit = make_item("ABS001", title="Unrelated title", citation_key="abs2020")
            items = [
                abstract_hit,
                make_item("CITE01", title="Another title", citation_key="cite2021"),
                make_attachment("PDF001", "CITE01"),
            ]
            # Zotero matched the first item through its abstract, which the
            # local index does not search; its row arrives after the PDF row.
            client.search_payload = [items[2], abstract_hit]
            service = ZoteroFulltextService(
                settings,
                client=client,
                index=MetadataIndex.rebuild_from_items(items, 5),
            )
            result = service.search("bunching")
        self.assertEqual(
            [(hit["citekey"], hit["match_source"]) for hit in result["results"]],
            [("abs2020", "metadata"), ("cite2021", "attachment")],
        )

    def test_metadata_search_respects_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            leuz = [{"creatorType": "author", "lastName": "Leuz"}]
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="One", citation_key="leuz2016", creators=leuz, collections=["COLL1"]),
                    make_item("BBB222", title="Two", citation_key="leuz2008", creators=leuz, collections=["COLL2"]),
                ],
                5,
            )
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.search("Leuz", collection="COLL2")
        self.assertEqual([hit["citekey"] for hit in result["results"]], ["leuz2008"])

    def test_lookup_miss_suggests_near_citekeys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.make_author_search_library(temp_dir)
            near = service.lookup("leuz2016a")
            unrelated = service.lookup("nobody2016")
        self.assertFalse(near["found"])
        self.assertIsNone(near["item"])
        self.assertEqual([candidate["citekey"] for candidate in near["candidates"]], ["leuz2016"])
        self.assertEqual(near["candidates"][0]["author_summary"], "Leuz & Wysocki")
        self.assertFalse(unrelated["found"])
        self.assertEqual(unrelated["candidates"], [])

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
            second = service.fulltext("paper2020")
        self.assertTrue(result["found"])
        self.assertEqual(result["paragraph_count"], 2)
        self.assertEqual(client.fulltext_calls, 2)
        self.assertEqual(second["paragraph_count"], 2)

    def test_fulltext_prefers_richest_attachment_over_key_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeClient()
            # APPDX sorts before PAPER by item key, but it is the short
            # supplemental appendix; PAPER holds the full article.
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("APPDX", "AAA111"),
                    make_attachment("PAPER", "AAA111"),
                ],
                5,
            )
            client.fulltexts["APPDX"] = {
                "content": "Supplemental appendix.\n\nExtra tables.",
            }
            client.fulltexts["PAPER"] = {
                "content": (
                    "Introduction to the full article.\n\n"
                    "Results section with substantial detail and discussion.\n\n"
                    "Conclusion of the full article."
                ),
            }
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.fulltext("paper2020")
            detail = service.lookup("paper2020")
        self.assertTrue(result["found"])
        self.assertEqual(result["paragraph_count"], 3)
        self.assertEqual(detail["item"]["attachment_key"], "PAPER")

    def read_pdf_and_snapshot(self, fulltexts: dict[str, dict[str, object]]) -> dict:
        """Read an item that has a PDF and a longer HTML snapshot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("PDFATT", "AAA111"),
                    make_attachment("SNAPSH", "AAA111", content_type="text/html"),
                ],
                5,
            )
            client.fulltexts.update(fulltexts)
            service = ZoteroFulltextService(
                self.make_settings(temp_dir), client=client, index=index
            )
            service.fulltext("paper2020")
            return service.lookup("paper2020")

    def test_fulltext_prefers_pdf_over_longer_html_snapshot(self) -> None:
        detail = self.read_pdf_and_snapshot(
            {
                "PDFATT": {"content": "The article."},
                "SNAPSH": {"content": "Site menu. Sign in. The article. Related links. Footer."},
            }
        )
        self.assertEqual(detail["item"]["attachment_key"], "PDFATT")

    def test_fulltext_falls_back_to_html_when_pdf_is_unindexed(self) -> None:
        detail = self.read_pdf_and_snapshot({"SNAPSH": {"content": "The article."}})
        self.assertEqual(detail["item"]["attachment_key"], "SNAPSH")

    def test_fulltext_splits_and_caps_large_text_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            settings.max_paragraph_chars = 20
            settings.max_fulltext_chars = 25
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Paper", citation_key="paper2020"),
                    make_attachment("ATTPDF", "AAA111"),
                ],
                5,
            )
            client.fulltexts["ATTPDF"] = {
                "content": (
                    "alpha beta gamma delta epsilon zeta eta theta iota kappa.\n\n"
                    "Second paragraph."
                ),
            }
            service = ZoteroFulltextService(settings, client=client, index=index)
            result = service.fulltext("paper2020")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_offset"], 1)
        self.assertLessEqual(result["returned_chars"], settings.max_fulltext_chars)
        self.assertTrue(all(
            len(paragraph["text"]) <= settings.max_paragraph_chars
            for paragraph in result["paragraphs"]
        ))

    def read_single_attachment(self, payload: dict[str, object]) -> tuple[dict, dict, dict]:
        """Return a cold read, a warm read, and an in-paper search for one PDF."""
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeClient()
            index = MetadataIndex.rebuild_from_items(
                [
                    make_item("AAA111", title="Book", citation_key="book2020"),
                    make_attachment("ATTPDF", "AAA111"),
                ],
                5,
            )
            client.fulltexts["ATTPDF"] = payload
            service = ZoteroFulltextService(
                self.make_settings(temp_dir), client=client, index=index
            )
            cold = service.fulltext("book2020")
            warm = service.fulltext("book2020")
            search = service.fulltext_search("book2020", "chapter")
        self.assertEqual(client.fulltext_calls, 1)
        return cold, warm, search

    def test_fulltext_flags_page_capped_index(self) -> None:
        cold, warm, search = self.read_single_attachment(
            {"content": "Chapter one.\n\nChapter two.", "indexedPages": 100, "totalPages": 435}
        )
        for result in (cold, warm, search):
            self.assertTrue(result["partial_index"])
            self.assertEqual(result["indexed_pages"], 100)
            self.assertEqual(result["total_pages"], 435)
        # Paging is complete even though the index is not.
        self.assertFalse(cold["truncated"])
        self.assertIsNone(cold["next_offset"])

    def test_fulltext_flags_character_capped_index(self) -> None:
        cold, _, search = self.read_single_attachment(
            {"content": "Chapter one.", "indexedChars": 500000, "totalChars": 750000}
        )
        for result in (cold, search):
            self.assertTrue(result["partial_index"])
            self.assertEqual(result["indexed_chars"], 500000)
            self.assertEqual(result["total_chars"], 750000)
            self.assertNotIn("indexed_pages", result)

    def test_fulltext_reports_complete_index(self) -> None:
        cold, warm, search = self.read_single_attachment(
            {"content": "Chapter one.", "indexedPages": 12, "totalPages": 12}
        )
        for result in (cold, warm, search):
            self.assertFalse(result["partial_index"])
            self.assertNotIn("indexed_pages", result)
            self.assertNotIn("total_pages", result)

    def test_fulltext_without_reported_counts_is_not_partial(self) -> None:
        cold, _, search = self.read_single_attachment({"content": "Chapter one."})
        for result in (cold, search):
            self.assertFalse(result["partial_index"])
            self.assertNotIn("indexed_pages", result)
            self.assertNotIn("total_chars", result)


if __name__ == "__main__":
    unittest.main()
